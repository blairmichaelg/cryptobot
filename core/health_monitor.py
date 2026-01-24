"""
Health Monitoring and Alerting System for Cryptobot

This module provides comprehensive health monitoring for the faucet worker service,
including service status checks, crash detection, automatic restarts, browser/proxy/faucet
health monitoring, and integration with Azure Monitor for alerting.

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
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

# Try to import Azure Monitor
try:
    from core.azure_monitor import initialize_azure_monitor, track_error, track_metric
    AZURE_MONITOR_AVAILABLE = True
except ImportError:
    AZURE_MONITOR_AVAILABLE = False

# Try to import requests for webhook notifications
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Try to import psutil for system metrics
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - system resource monitoring disabled")

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
    
    # Restart backoff configuration
    INITIAL_BACKOFF_SECONDS = 10
    BACKOFF_MULTIPLIER = 2
    MAX_BACKOFF_SECONDS = 300
    
    # Health check thresholds
    MIN_HEALTHY_PROXIES = 3
    MAX_BROWSER_CONTEXT_FAILURES = 3
    MIN_FAUCET_SUCCESS_RATE = 0.3  # 30% success rate
    MAX_MEMORY_PERCENT = 90
    MAX_CPU_PERCENT = 95
    MIN_DISK_GB = 2
    MAX_FAUCET_HISTORY = 10  # Track last 10 attempts per faucet
    ALERT_COOLDOWN_SECONDS = 3600  # 1 hour between duplicate alerts
    
    def __init__(self, log_file: Optional[str] = None, enable_azure: bool = True, 
                 browser_manager: Optional[Any] = None, proxy_manager: Optional[Any] = None):
        """
        Initialize health monitor
        
        Args:
            log_file: Path to health log file (default: logs/vm_health.log)
            enable_azure: Enable Azure Monitor integration
            browser_manager: Optional BrowserManager instance for browser health checks
            proxy_manager: Optional ProxyManager instance for proxy health checks
        """
        self.root_dir = Path(__file__).parent.parent
        self.log_file = Path(log_file) if log_file else self.root_dir / "logs" / "vm_health.log"
        self.heartbeat_file = self.root_dir / "logs" / "heartbeat.txt"
        self.service_name = "faucet_worker"
        self.restart_backoff_file = self.root_dir / "logs" / "restart_backoff.json"
        
        # Browser and proxy managers for advanced health checks
        self.browser_manager = browser_manager
        self.proxy_manager = proxy_manager
        
        # Health tracking
        self.browser_context_failures = 0
        self.faucet_attempt_history: Dict[str, List[bool]] = {}  # faucet -> [success/fail]
        self.last_browser_check = 0.0
        self.last_proxy_check = 0.0
        self.last_system_check = 0.0
        self.alert_cooldowns: Dict[str, float] = {}  # Alert deduplication
        
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
        self.backoff_seconds = self.INITIAL_BACKOFF_SECONDS
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
    
    async def check_browser_health(self) -> Dict[str, Any]:
        """
        Check if browser contexts are responding.
        
        Returns:
            Dict with browser health information
        """
        try:
            self.last_browser_check = time.time()
            
            if not self.browser_manager:
                return {"healthy": True, "message": "No browser manager configured"}
            
            # Check if browser instance exists
            if not hasattr(self.browser_manager, 'browser') or not self.browser_manager.browser:
                self.browser_context_failures += 1
                return {
                    "healthy": False,
                    "message": "Browser instance not running",
                    "consecutive_failures": self.browser_context_failures
                }
            
            # Try to check browser connectivity
            try:
                contexts = self.browser_manager.browser.contexts if hasattr(self.browser_manager.browser, 'contexts') else []
                context_count = len(contexts)
                
                # Reset failure count if browser is responsive
                if self.browser_context_failures > 0:
                    logger.info(f"Browser health recovered (previous failures: {self.browser_context_failures})")
                    self.browser_context_failures = 0
                
                return {
                    "healthy": True,
                    "context_count": context_count,
                    "consecutive_failures": 0,
                    "message": f"Browser healthy with {context_count} contexts"
                }
                
            except Exception as e:
                self.browser_context_failures += 1
                logger.warning(f"Browser context check failed ({self.browser_context_failures}/{self.MAX_BROWSER_CONTEXT_FAILURES}): {e}")
                
                return {
                    "healthy": self.browser_context_failures < self.MAX_BROWSER_CONTEXT_FAILURES,
                    "consecutive_failures": self.browser_context_failures,
                    "message": f"Browser context check failed: {e}"
                }
                
        except Exception as e:
            logger.error(f"Browser health check error: {e}")
            return {"healthy": False, "message": f"Health check error: {e}"}
    
    async def check_proxy_health(self) -> Dict[str, Any]:
        """
        Check proxy pool status.
        
        Returns:
            Dict with proxy pool information
        """
        try:
            self.last_proxy_check = time.time()
            
            if not self.proxy_manager:
                return {"healthy": True, "message": "No proxy manager configured"}
            
            total_proxies = len(self.proxy_manager.all_proxies)
            healthy_proxies = len(self.proxy_manager.proxies)
            dead_proxies = len(self.proxy_manager.dead_proxies)
            cooldown_proxies = len(self.proxy_manager.proxy_cooldowns)
            
            # Calculate average latency
            avg_latency = 0.0
            latency_count = 0
            for proxy_key, latencies in self.proxy_manager.proxy_latency.items():
                if latencies:
                    avg_latency += sum(latencies) / len(latencies)
                    latency_count += 1
            
            if latency_count > 0:
                avg_latency = avg_latency / latency_count
            
            is_healthy = healthy_proxies >= self.MIN_HEALTHY_PROXIES
            
            return {
                "healthy": is_healthy,
                "total": total_proxies,
                "healthy_count": healthy_proxies,
                "dead": dead_proxies,
                "cooldown": cooldown_proxies,
                "avg_latency_ms": round(avg_latency, 2),
                "message": f"{healthy_proxies}/{total_proxies} proxies healthy, avg latency {avg_latency:.0f}ms"
            }
            
        except Exception as e:
            logger.error(f"Proxy health check error: {e}")
            return {"healthy": False, "message": f"Health check error: {e}"}
    
    def record_faucet_attempt(self, faucet_type: str, success: bool):
        """
        Record a faucet claim attempt for health tracking.
        
        Args:
            faucet_type: Faucet identifier
            success: Whether the attempt succeeded
        """
        if faucet_type not in self.faucet_attempt_history:
            self.faucet_attempt_history[faucet_type] = []
        
        history = self.faucet_attempt_history[faucet_type]
        history.append(success)
        
        # Keep only recent history
        if len(history) > self.MAX_FAUCET_HISTORY:
            history.pop(0)
    
    async def check_faucet_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Check per-faucet success rate over last N attempts.
        
        Returns:
            Dict mapping faucet_type to health info
        """
        results = {}
        
        for faucet_type, history in self.faucet_attempt_history.items():
            if not history:
                continue
            
            success_count = sum(1 for s in history if s)
            total_count = len(history)
            success_rate = success_count / total_count if total_count > 0 else 0.0
            
            is_healthy = success_rate >= self.MIN_FAUCET_SUCCESS_RATE or total_count < 3
            
            results[faucet_type] = {
                "healthy": is_healthy,
                "success_count": success_count,
                "total_count": total_count,
                "success_rate": round(success_rate, 2),
                "message": f"{faucet_type}: {success_rate:.0%} success rate ({success_count}/{total_count})"
            }
        
        return results
    
    async def check_system_health(self) -> Dict[str, Any]:
        """
        Check system resources (memory, CPU, disk).
        
        Returns:
            Dict with system resource information
        """
        try:
            self.last_system_check = time.time()
            
            if not PSUTIL_AVAILABLE:
                return {"healthy": True, "message": "psutil not available"}
            
            # Get system metrics
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)
            disk = psutil.disk_usage('/')
            
            # Check thresholds
            memory_ok = memory.percent < self.MAX_MEMORY_PERCENT
            cpu_ok = cpu_percent < self.MAX_CPU_PERCENT
            disk_ok = (disk.free / (1024**3)) > self.MIN_DISK_GB  # GB
            
            is_healthy = memory_ok and cpu_ok and disk_ok
            
            issues = []
            if not memory_ok:
                issues.append(f"High memory usage: {memory.percent:.1f}%")
            if not cpu_ok:
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")
            if not disk_ok:
                issues.append(f"Low disk space: {disk.free/(1024**3):.1f}GB")
            
            message = "System healthy" if is_healthy else "; ".join(issues)
            
            return {
                "healthy": is_healthy,
                "memory_percent": round(memory.percent, 1),
                "cpu_percent": round(cpu_percent, 1),
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "message": message
            }
            
        except Exception as e:
            logger.error(f"System health check error: {e}")
            return {"healthy": False, "message": f"Health check error: {e}"}
    
    async def send_health_alert(self, severity: str, message: str, component: str = "general"):
        """
        Send health alert with deduplication.
        
        Args:
            severity: "INFO", "WARNING", or "CRITICAL"
            message: Alert message
            component: Component name for deduplication
        """
        alert_key = f"{component}:{severity}:{message}"
        
        # Check cooldown
        now = time.time()
        if alert_key in self.alert_cooldowns:
            if now - self.alert_cooldowns[alert_key] < self.ALERT_COOLDOWN_SECONDS:
                return  # Skip duplicate
        
        self.alert_cooldowns[alert_key] = now
        
        # Log alert
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        alert_msg = f"🚨 HEALTH ALERT [{severity}] {component}: {message} ({timestamp})"
        
        if severity == "CRITICAL":
            logger.critical(alert_msg)
        elif severity == "WARNING":
            logger.warning(alert_msg)
        else:
            logger.info(alert_msg)
    
    async def run_full_health_check(self) -> Dict[str, Any]:
        """
        Run all health checks and return comprehensive status.
        
        Returns:
            Dict with all health check results
        """
        logger.info("🏥 Running comprehensive health check...")
        
        # Run all checks
        browser_health = await self.check_browser_health()
        proxy_health = await self.check_proxy_health()
        faucet_health = await self.check_faucet_health()
        system_health = await self.check_system_health()
        
        # Determine overall health
        all_healthy = (
            browser_health.get("healthy", True) and
            proxy_health.get("healthy", True) and
            system_health.get("healthy", True) and
            all(fh.get("healthy", True) for fh in faucet_health.values())
        )
        
        # Generate alerts
        if not browser_health.get("healthy", True):
            if self.browser_context_failures >= self.MAX_BROWSER_CONTEXT_FAILURES:
                await self.send_health_alert(
                    "CRITICAL",
                    f"Browser context failed {self.browser_context_failures} times - restart needed",
                    "browser"
                )
            else:
                await self.send_health_alert("WARNING", browser_health.get("message", ""), "browser")
        
        if not proxy_health.get("healthy", True):
            await self.send_health_alert(
                "CRITICAL",
                f"Only {proxy_health.get('healthy_count', 0)} healthy proxies (minimum: {self.MIN_HEALTHY_PROXIES})",
                "proxy"
            )
        
        if not system_health.get("healthy", True):
            await self.send_health_alert("CRITICAL", system_health.get("message", ""), "system")
        
        for faucet_type, fh in faucet_health.items():
            if not fh.get("healthy", True):
                await self.send_health_alert("WARNING", fh.get("message", ""), f"faucet_{faucet_type}")
        
        # Compile results
        results = {
            "overall_healthy": all_healthy,
            "timestamp": time.time(),
            "browser": browser_health,
            "proxy": proxy_health,
            "system": system_health,
            "faucets": faucet_health
        }
        
        logger.info(f"✅ Health check complete - Overall: {'HEALTHY' if all_healthy else 'DEGRADED'}")
        return results
    
    def should_restart_browser(self) -> bool:
        """
        Determine if browser should be restarted.
        
        Returns:
            True if browser restart is recommended
        """
        return self.browser_context_failures >= self.MAX_BROWSER_CONTEXT_FAILURES
    
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
                timeout=timeout,
                check=False
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
    
    def send_webhook_notification(self, result: HealthCheckResult):
        """
        Send notification to webhook URL (Slack, Discord, Teams, etc.)
        
        Args:
            result: Health check result
        """
        webhook_url = os.getenv('ALERT_WEBHOOK_URL')
        if not webhook_url or not REQUESTS_AVAILABLE:
            return
        
        # Only send notifications for WARNING and CRITICAL
        if result.status == HealthStatus.HEALTHY:
            return
        
        try:
            # Determine emoji and color based on status
            if result.status == HealthStatus.CRITICAL:
                emoji = "🔴"
                color = "#FF0000"
            else:  # WARNING
                emoji = "⚠️"
                color = "#FFA500"
            
            # Build message
            message = f"{emoji} **Cryptobot Health Alert - {result.status.value}**\n\n"
            message += f"**Timestamp:** {result.timestamp}\n"
            message += f"**Service Active:** {'✅ Yes' if result.service_active else '❌ No'}\n"
            message += f"**Service Running:** {'✅ Yes' if result.service_running else '❌ No'}\n"
            message += f"**Disk Usage:** {result.disk_usage_percent}%\n"
            message += f"**Memory Usage:** {result.memory_usage_percent}%\n"
            message += f"**Heartbeat Age:** {result.heartbeat_age_seconds}s\n"
            
            if result.alerts:
                message += f"\n**Alerts:**\n"
                for alert in result.alerts:
                    message += f"• {alert}\n"
            
            # Try Slack format first (most common)
            slack_payload = {
                "attachments": [{
                    "color": color,
                    "title": f"{emoji} Cryptobot Health Alert",
                    "text": message,
                    "footer": "Cryptobot Health Monitor",
                    "ts": int(datetime.now().timestamp())
                }]
            }
            
            # Send to webhook
            response = requests.post(
                webhook_url,
                json=slack_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Sent webhook notification")
            else:
                logger.warning(f"Webhook returned status {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
    
    def send_email_notification(self, result: HealthCheckResult):
        """
        Send email notification (requires SMTP configuration)
        
        Args:
            result: Health check result
        """
        # Only send notifications for WARNING and CRITICAL
        if result.status == HealthStatus.HEALTHY:
            return
        
        email_to = os.getenv('ALERT_EMAIL')
        if not email_to:
            return
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Get SMTP configuration from environment
            smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_user = os.getenv('SMTP_USER')
            smtp_pass = os.getenv('SMTP_PASSWORD')
            
            if not smtp_user or not smtp_pass:
                logger.warning("SMTP credentials not configured, skipping email notification")
                return
            
            # Build email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{result.status.value}] Cryptobot Health Alert"
            msg['From'] = smtp_user
            msg['To'] = email_to
            
            # Build email body
            text = f"""
Cryptobot Health Alert

Status: {result.status.value}
Timestamp: {result.timestamp}

Service Active: {'Yes' if result.service_active else 'No'}
Service Running: {'Yes' if result.service_running else 'No'}
Disk Usage: {result.disk_usage_percent}%
Memory Usage: {result.memory_usage_percent}%
Heartbeat Age: {result.heartbeat_age_seconds}s

Alerts:
"""
            for alert in result.alerts:
                text += f"  • {alert}\n"
            
            part = MIMEText(text, 'plain')
            msg.attach(part)
            
            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            logger.info("Sent email notification")
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
    
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
            
            # Exponential backoff: configurable multiplier, max delay
            self.backoff_seconds = min(
                self.backoff_seconds * self.BACKOFF_MULTIPLIER, 
                self.MAX_BACKOFF_SECONDS
            )
            self._save_restart_state()
            
            return True
        else:
            logger.error("Service restart failed - service not running")
            return False
    
    def reset_backoff(self):
        """Reset the restart backoff counter"""
        self.restart_count = 0
        self.last_restart_time = None
        self.backoff_seconds = self.INITIAL_BACKOFF_SECONDS
        self._save_restart_state()
        logger.info("Reset restart backoff counter")
    
    def run_check(self, send_alerts: bool = False, auto_restart: bool = False) -> HealthCheckResult:
        """
        Run a single health check
        
        Args:
            send_alerts: Send alerts to Azure Monitor, webhook, and email
            auto_restart: Automatically restart service if critical
            
        Returns:
            HealthCheckResult
        """
        result = self.perform_health_check()
        
        # Send alerts if enabled
        if send_alerts:
            # Send to Azure Monitor if enabled
            if self.azure_enabled:
                self.send_azure_metrics(result)
            
            # Send webhook notification
            self.send_webhook_notification(result)
            
            # Send email notification
            self.send_email_notification(result)
        
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
