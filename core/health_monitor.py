"""
Health Monitoring and Alerting System for Cryptobot

This module provides comprehensive health monitoring for the faucet worker service,
including service status checks, crash detection, automatic restarts, and integration
with Azure Monitor for alerting.

Usage:
    python -m core.health_monitor --daemon      # Run as daemon
    python -m core.health_monitor --check       # One-time check
    python -m core.health_monitor --alert       # Check and send alerts
"""

import os
import sys
import time
import logging
import subprocess
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from enum import Enum

# Try to import Azure Monitor
try:
    from core.azure_monitor import initialize_azure_monitor, track_error, track_metric
    AZURE_MONITOR_AVAILABLE = True
except ImportError:
    AZURE_MONITOR_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    timestamp: str
    status: HealthStatus
    service_active: bool
    service_running: bool
    crash_count: int
    disk_usage_percent: int
    memory_usage_percent: int
    heartbeat_age_seconds: int
    alerts: List[str]
    metrics: Dict[str, float]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result['status'] = self.status.value
        return result


class HealthMonitor:
    """Health monitoring system for Cryptobot"""
    
    def __init__(self, log_file: Optional[str] = None, enable_azure: bool = True):
        """
        Initialize health monitor
        
        Args:
            log_file: Path to health log file (default: logs/vm_health.log)
            enable_azure: Enable Azure Monitor integration
        """
        self.root_dir = Path(__file__).parent.parent
        self.log_file = Path(log_file) if log_file else self.root_dir / "logs" / "vm_health.log"
        self.heartbeat_file = self.root_dir / "logs" / "heartbeat.txt"
        self.service_name = "faucet_worker"
        self.restart_backoff_file = self.root_dir / "logs" / "restart_backoff.json"
        
        # Ensure logs directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure file logging
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)
        
        # Initialize Azure Monitor if available
        self.azure_enabled = False
        if enable_azure and AZURE_MONITOR_AVAILABLE:
            self.azure_enabled = initialize_azure_monitor()
            if self.azure_enabled:
                logger.info("Azure Monitor integration enabled")
        
        # Load restart backoff state
        self.restart_count = 0
        self.last_restart_time = None
        self.backoff_seconds = 10
        self._load_restart_state()
    
    def _load_restart_state(self):
        """Load restart backoff state from file"""
        if self.restart_backoff_file.exists():
            try:
                with open(self.restart_backoff_file, 'r') as f:
                    state = json.load(f)
                    self.restart_count = state.get('restart_count', 0)
                    last_restart = state.get('last_restart_time')
                    if last_restart:
                        self.last_restart_time = datetime.fromisoformat(last_restart)
                    self.backoff_seconds = state.get('backoff_seconds', 10)
            except Exception as e:
                logger.warning(f"Failed to load restart state: {e}")
    
    def _save_restart_state(self):
        """Save restart backoff state to file"""
        try:
            state = {
                'restart_count': self.restart_count,
                'last_restart_time': self.last_restart_time.isoformat() if self.last_restart_time else None,
                'backoff_seconds': self.backoff_seconds
            }
            with open(self.restart_backoff_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save restart state: {e}")
    
    def _run_command(self, cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
        """
        Run a shell command and return exit code, stdout, stderr
        
        Args:
            cmd: Command to run
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    def check_service_status(self) -> Tuple[bool, bool, int]:
        """
        Check systemd service status
        
        Returns:
            Tuple of (is_active, is_running, crash_count)
        """
        # Check if service is active
        exit_code, stdout, _ = self._run_command(f"systemctl is-active {self.service_name}")
        is_active = (exit_code == 0 and stdout == "active")
        
        # Check detailed status
        exit_code, stdout, _ = self._run_command(f"systemctl status {self.service_name} --no-pager")
        is_running = "active (running)" in stdout.lower()
        
        # Count restarts in the output
        crash_count = stdout.lower().count("restart")
        
        return is_active, is_running, crash_count
    
    def check_disk_usage(self) -> int:
        """
        Check disk usage percentage
        
        Returns:
            Disk usage percentage (0-100)
        """
        try:
            exit_code, stdout, _ = self._run_command("df -h / | tail -1 | awk '{print $5}' | sed 's/%//'")
            if exit_code == 0 and stdout:
                return int(stdout)
        except (ValueError, Exception) as e:
            logger.warning(f"Failed to check disk usage: {e}")
        return 0
    
    def check_memory_usage(self) -> int:
        """
        Check memory usage percentage
        
        Returns:
            Memory usage percentage (0-100)
        """
        try:
            exit_code, stdout, _ = self._run_command(
                "free | grep Mem | awk '{print int($3/$2 * 100)}'"
            )
            if exit_code == 0 and stdout:
                return int(stdout)
        except (ValueError, Exception) as e:
            logger.warning(f"Failed to check memory usage: {e}")
        return 0
    
    def check_heartbeat(self) -> int:
        """
        Check heartbeat file age
        
        Returns:
            Age of heartbeat file in seconds (-1 if not found)
        """
        # Check multiple possible heartbeat locations
        heartbeat_paths = [
            self.heartbeat_file,
            Path("/tmp/cryptobot_heartbeat"),
        ]
        
        for path in heartbeat_paths:
            if path.exists():
                try:
                    mtime = path.stat().st_mtime
                    age = int(time.time() - mtime)
                    return age
                except Exception as e:
                    logger.warning(f"Failed to check heartbeat at {path}: {e}")
        
        return -1  # Not found
    
    def check_service_logs(self) -> List[str]:
        """
        Check recent service logs for errors
        
        Returns:
            List of recent error messages
        """
        errors = []
        exit_code, stdout, _ = self._run_command(
            f"journalctl -u {self.service_name} -p err -n 5 --no-pager"
        )
        
        if exit_code == 0 and stdout and "No entries" not in stdout:
            # Parse error lines
            for line in stdout.split('\n'):
                if line.strip():
                    errors.append(line.strip())
        
        return errors
    
    def perform_health_check(self) -> HealthCheckResult:
        """
        Perform comprehensive health check
        
        Returns:
            HealthCheckResult with all health metrics
        """
        logger.info("Performing health check...")
        
        # Collect all metrics
        is_active, is_running, crash_count = self.check_service_status()
        disk_usage = self.check_disk_usage()
        memory_usage = self.check_memory_usage()
        heartbeat_age = self.check_heartbeat()
        
        # Determine overall status and collect alerts
        alerts = []
        status = HealthStatus.HEALTHY
        
        # Check service status
        if not is_active:
            status = HealthStatus.CRITICAL
            alerts.append("Service is not active")
        elif not is_running:
            status = HealthStatus.CRITICAL
            alerts.append("Service is not running")
        
        # Check for crash loops
        if crash_count > 5:
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.WARNING
            alerts.append(f"Service has restarted {crash_count} times - possible crash loop")
        
        # Check disk usage
        if disk_usage > 90:
            status = HealthStatus.CRITICAL
            alerts.append(f"Disk usage critical: {disk_usage}%")
        elif disk_usage > 80:
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.WARNING
            alerts.append(f"Disk usage high: {disk_usage}%")
        
        # Check memory usage
        if memory_usage > 90:
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.WARNING
            alerts.append(f"Memory usage high: {memory_usage}%")
        
        # Check heartbeat
        if heartbeat_age == -1:
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.WARNING
            alerts.append("No heartbeat file found")
        elif heartbeat_age > 300:  # 5 minutes
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.WARNING
            alerts.append(f"Heartbeat is stale ({heartbeat_age}s old)")
        
        # Check for recent errors
        recent_errors = self.check_service_logs()
        if recent_errors:
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.WARNING
            alerts.append(f"Found {len(recent_errors)} recent errors in logs")
        
        # Create result
        result = HealthCheckResult(
            timestamp=datetime.now().isoformat(),
            status=status,
            service_active=is_active,
            service_running=is_running,
            crash_count=crash_count,
            disk_usage_percent=disk_usage,
            memory_usage_percent=memory_usage,
            heartbeat_age_seconds=heartbeat_age,
            alerts=alerts,
            metrics={
                'disk_usage': disk_usage,
                'memory_usage': memory_usage,
                'heartbeat_age': heartbeat_age,
                'crash_count': crash_count,
            }
        )
        
        # Log result
        logger.info(f"Health check complete: {status.value}")
        if alerts:
            for alert in alerts:
                logger.warning(f"Alert: {alert}")
        
        return result
    
    def send_azure_metrics(self, result: HealthCheckResult):
        """
        Send metrics to Azure Monitor
        
        Args:
            result: Health check result
        """
        if not self.azure_enabled:
            return
        
        try:
            # Send metrics
            track_metric("health.disk_usage", result.disk_usage_percent)
            track_metric("health.memory_usage", result.memory_usage_percent)
            track_metric("health.heartbeat_age", result.heartbeat_age_seconds)
            track_metric("health.crash_count", result.crash_count)
            track_metric("health.service_active", 1 if result.service_active else 0)
            
            # Send errors for alerts
            if result.status == HealthStatus.CRITICAL:
                for alert in result.alerts:
                    track_error("health_critical", alert, "health_monitor")
            elif result.status == HealthStatus.WARNING:
                for alert in result.alerts:
                    track_error("health_warning", alert, "health_monitor")
                    
            logger.info("Sent metrics to Azure Monitor")
        except Exception as e:
            logger.error(f"Failed to send Azure metrics: {e}")
    
    def restart_service_with_backoff(self) -> bool:
        """
        Restart the service with exponential backoff
        
        Returns:
            True if restart was successful, False otherwise
        """
        # Check if we should restart based on backoff
        now = datetime.now()
        if self.last_restart_time:
            time_since_restart = (now - self.last_restart_time).total_seconds()
            if time_since_restart < self.backoff_seconds:
                logger.info(f"Skipping restart - backoff period ({self.backoff_seconds}s) not elapsed")
                return False
        
        logger.info(f"Attempting to restart service (attempt #{self.restart_count + 1})")
        
        # Restart the service
        exit_code, stdout, stderr = self._run_command(f"sudo systemctl restart {self.service_name}")
        
        if exit_code != 0:
            logger.error(f"Failed to restart service: {stderr}")
            return False
        
        # Wait a moment for service to start
        time.sleep(5)
        
        # Verify service is running
        is_active, is_running, _ = self.check_service_status()
        
        if is_active and is_running:
            logger.info("Service restarted successfully")
            
            # Update backoff state
            self.restart_count += 1
            self.last_restart_time = now
            
            # Exponential backoff: 10s, 20s, 40s, 80s, 160s, max 300s
            self.backoff_seconds = min(self.backoff_seconds * 2, 300)
            self._save_restart_state()
            
            return True
        else:
            logger.error("Service restart failed - service not running")
            return False
    
    def reset_backoff(self):
        """Reset the restart backoff counter"""
        self.restart_count = 0
        self.last_restart_time = None
        self.backoff_seconds = 10
        self._save_restart_state()
        logger.info("Reset restart backoff counter")
    
    def run_check(self, send_alerts: bool = False, auto_restart: bool = False) -> HealthCheckResult:
        """
        Run a single health check
        
        Args:
            send_alerts: Send alerts to Azure Monitor
            auto_restart: Automatically restart service if critical
            
        Returns:
            HealthCheckResult
        """
        result = self.perform_health_check()
        
        # Send to Azure Monitor if enabled
        if send_alerts and self.azure_enabled:
            self.send_azure_metrics(result)
        
        # Auto-restart if critical and enabled
        if auto_restart and result.status == HealthStatus.CRITICAL:
            if not result.service_active or not result.service_running:
                logger.warning("Service is critical - attempting automatic restart")
                self.restart_service_with_backoff()
        
        # If service is healthy, reset backoff
        if result.status == HealthStatus.HEALTHY:
            if self.restart_count > 0:
                self.reset_backoff()
        
        return result
    
    def run_daemon(self, check_interval: int = 60, auto_restart: bool = True):
        """
        Run health monitor as a daemon
        
        Args:
            check_interval: Seconds between health checks
            auto_restart: Automatically restart service on critical failures
        """
        logger.info(f"Starting health monitor daemon (check interval: {check_interval}s)")
        
        try:
            while True:
                result = self.run_check(send_alerts=True, auto_restart=auto_restart)
                
                # Log summary
                logger.info(
                    f"Status: {result.status.value}, "
                    f"Service: {'UP' if result.service_running else 'DOWN'}, "
                    f"Disk: {result.disk_usage_percent}%, "
                    f"Memory: {result.memory_usage_percent}%"
                )
                
                # Wait for next check
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            logger.info("Health monitor daemon stopped by user")
        except Exception as e:
            logger.error(f"Health monitor daemon error: {e}", exc_info=True)
            raise


def main():
    """Main entry point for health monitor CLI"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cryptobot Health Monitor")
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon with continuous monitoring'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Run a single health check'
    )
    parser.add_argument(
        '--alert',
        action='store_true',
        help='Send alerts to Azure Monitor'
    )
    parser.add_argument(
        '--restart',
        action='store_true',
        help='Auto-restart service on critical failures'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='Check interval in seconds for daemon mode (default: 60)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        help='Path to health log file'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    
    args = parser.parse_args()
    
    # Create health monitor
    monitor = HealthMonitor(log_file=args.log_file)
    
    if args.daemon:
        # Run as daemon
        monitor.run_daemon(
            check_interval=args.interval,
            auto_restart=args.restart
        )
    else:
        # Run single check
        result = monitor.run_check(
            send_alerts=args.alert,
            auto_restart=args.restart
        )
        
        # Output result
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"\nHealth Check Results ({result.timestamp})")
            print("=" * 60)
            print(f"Overall Status: {result.status.value}")
            print(f"Service Active: {result.service_active}")
            print(f"Service Running: {result.service_running}")
            print(f"Crash Count: {result.crash_count}")
            print(f"Disk Usage: {result.disk_usage_percent}%")
            print(f"Memory Usage: {result.memory_usage_percent}%")
            print(f"Heartbeat Age: {result.heartbeat_age_seconds}s")
            
            if result.alerts:
                print("\nAlerts:")
                for alert in result.alerts:
                    print(f"  • {alert}")
            else:
                print("\n✅ No alerts")
        
        # Exit with appropriate code
        sys.exit(0 if result.status == HealthStatus.HEALTHY else 1)


if __name__ == "__main__":
    main()
