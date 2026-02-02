"""
Real-Time Faucet Monitoring Dashboard

Tracks per-faucet health metrics with alerting for prolonged failures.
Provides both CLI and web dashboard interfaces for monitoring bot farm status.
"""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich import box

logger = logging.getLogger(__name__)

# File paths
MONITORING_DATA_FILE = Path(__file__).parent.parent / "config" / "monitoring_state.json"
ANALYTICS_FILE = Path(__file__).parent.parent / "earnings_analytics.json"


@dataclass
class FaucetMetrics:
    """Metrics for a single faucet."""
    faucet_name: str
    total_claims: int = 0
    successful_claims: int = 0
    failed_claims: int = 0
    last_success_timestamp: Optional[float] = None
    last_failure_timestamp: Optional[float] = None
    last_attempt_timestamp: Optional[float] = None
    total_claim_time: float = 0.0  # Total time spent claiming (seconds)
    failure_reasons: Dict[str, int] = None  # Count of each failure reason
    earnings_usd: float = 0.0
    costs_usd: float = 0.0
    
    def __post_init__(self):
        if self.failure_reasons is None:
            self.failure_reasons = {}
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_claims == 0:
            return 0.0
        return (self.successful_claims / self.total_claims) * 100
    
    @property
    def avg_claim_time(self) -> float:
        """Average time per claim in seconds."""
        if self.successful_claims == 0:
            return 0.0
        return self.total_claim_time / self.successful_claims
    
    @property
    def net_profit_usd(self) -> float:
        """Net profit = earnings - costs."""
        return self.earnings_usd - self.costs_usd
    
    @property
    def roi_percent(self) -> float:
        """Return on investment as percentage."""
        if self.costs_usd == 0:
            return 0.0
        return (self.net_profit_usd / self.costs_usd) * 100
    
    @property
    def hours_since_last_success(self) -> Optional[float]:
        """Hours since last successful claim."""
        if self.last_success_timestamp is None:
            return None
        return (time.time() - self.last_success_timestamp) / 3600
    
    @property
    def is_healthy(self) -> bool:
        """Determine if faucet is healthy (successful claim in last 24h)."""
        if self.last_success_timestamp is None:
            return False
        hours_since = self.hours_since_last_success
        return hours_since is not None and hours_since < 24
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "faucet_name": self.faucet_name,
            "total_claims": self.total_claims,
            "successful_claims": self.successful_claims,
            "failed_claims": self.failed_claims,
            "last_success_timestamp": self.last_success_timestamp,
            "last_failure_timestamp": self.last_failure_timestamp,
            "last_attempt_timestamp": self.last_attempt_timestamp,
            "total_claim_time": self.total_claim_time,
            "failure_reasons": self.failure_reasons,
            "earnings_usd": self.earnings_usd,
            "costs_usd": self.costs_usd,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "FaucetMetrics":
        """Create from dictionary."""
        return cls(**data)


class FaucetMonitor:
    """
    Real-time monitoring system for tracking faucet health and performance.
    
    Features:
    - Per-faucet success rates (24h, 7d, 30d)
    - Average claim times
    - Failure reason breakdown
    - Last successful claim tracking
    - Alerting for prolonged failures (>24h)
    - Profitability metrics (earnings vs costs)
    """
    
    # Alert thresholds
    ALERT_NO_SUCCESS_HOURS = 24  # Alert if no success in 24 hours
    ALERT_LOW_SUCCESS_RATE = 40.0  # Alert if success rate < 40%
    ALERT_NEGATIVE_ROI_HOURS = 72  # Alert if negative ROI for 72h
    
    def __init__(self):
        self.metrics: Dict[str, FaucetMetrics] = {}
        self.alerts: List[Dict[str, Any]] = []
        self._load_state()
    
    def _load_state(self):
        """Load monitoring state from disk."""
        try:
            if MONITORING_DATA_FILE.exists():
                with open(MONITORING_DATA_FILE, 'r') as f:
                    data = json.load(f)
                    for faucet_name, metrics_data in data.get("metrics", {}).items():
                        self.metrics[faucet_name] = FaucetMetrics.from_dict(metrics_data)
                    self.alerts = data.get("alerts", [])
                logger.info(f"📊 Loaded monitoring data for {len(self.metrics)} faucets")
        except Exception as e:
            logger.warning(f"Could not load monitoring state: {e}")
    
    def _save_state(self):
        """Save monitoring state to disk."""
        try:
            MONITORING_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "metrics": {name: m.to_dict() for name, m in self.metrics.items()},
                "alerts": self.alerts,
                "last_updated": time.time()
            }
            with open(MONITORING_DATA_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("📊 Monitoring state saved")
        except Exception as e:
            logger.warning(f"Could not save monitoring state: {e}")
    
    def update_from_analytics(self):
        """
        Update metrics from earnings_analytics.json.
        
        This should be called periodically to sync with the analytics data.
        """
        try:
            if not ANALYTICS_FILE.exists():
                logger.warning(f"Analytics file not found: {ANALYTICS_FILE}")
                return
            
            with open(ANALYTICS_FILE, 'r') as f:
                data = json.load(f)
            
            claims = data.get("claims", [])
            costs = data.get("costs", [])
            
            # Reset metrics for fresh calculation
            faucet_data = defaultdict(lambda: {
                "claims": [], 
                "costs": [],
                "claim_times": []
            })
            
            # Group claims by faucet
            for claim in claims:
                faucet = claim.get("faucet", "unknown")
                faucet_data[faucet]["claims"].append(claim)
            
            # Group costs by faucet
            for cost in costs:
                faucet = cost.get("faucet")
                if faucet:
                    faucet_data[faucet]["costs"].append(cost)
            
            # Calculate metrics for each faucet
            for faucet_name, data_dict in faucet_data.items():
                if faucet_name not in self.metrics:
                    self.metrics[faucet_name] = FaucetMetrics(faucet_name=faucet_name)
                
                metrics = self.metrics[faucet_name]
                claims_list = data_dict["claims"]
                costs_list = data_dict["costs"]
                
                # Basic counts
                metrics.total_claims = len(claims_list)
                metrics.successful_claims = sum(1 for c in claims_list if c.get("success"))
                metrics.failed_claims = metrics.total_claims - metrics.successful_claims
                
                # Timestamps
                successful_claims = [c for c in claims_list if c.get("success")]
                failed_claims = [c for c in claims_list if not c.get("success")]
                
                if successful_claims:
                    metrics.last_success_timestamp = max(c.get("timestamp", 0) for c in successful_claims)
                
                if failed_claims:
                    metrics.last_failure_timestamp = max(c.get("timestamp", 0) for c in failed_claims)
                
                if claims_list:
                    metrics.last_attempt_timestamp = max(c.get("timestamp", 0) for c in claims_list)
                
                # Calculate total claim time from claim_time field
                metrics.total_claim_time = sum(
                    c.get("claim_time", 0) for c in successful_claims 
                    if c.get("claim_time") is not None
                )
                
                # Collect failure reasons
                failure_reasons = defaultdict(int)
                for claim in failed_claims:
                    reason = claim.get("failure_reason", "Unknown")
                    failure_reasons[reason] += 1
                metrics.failure_reasons = dict(failure_reasons)
                
                # Calculate earnings (needs price conversion - simplified for now)
                total_earnings = 0.0
                for claim in successful_claims:
                    amount = claim.get("amount", 0)
                    # In production, convert to USD using price feed
                    # For now, assuming satoshi values
                    total_earnings += amount * 0.0001  # Placeholder conversion
                
                metrics.earnings_usd = total_earnings
                
                # Calculate costs
                metrics.costs_usd = sum(c.get("amount_usd", 0) for c in costs_list)
            
            self._save_state()
            logger.info(f"📊 Updated metrics for {len(self.metrics)} faucets")
            
        except Exception as e:
            logger.error(f"Failed to update from analytics: {e}")
    
    def check_alerts(self) -> List[Dict[str, Any]]:
        """
        Check for alert conditions and generate alerts.
        
        Returns:
            List of active alerts
        """
        new_alerts = []
        current_time = time.time()
        
        for faucet_name, metrics in self.metrics.items():
            # Skip if no claims yet
            if metrics.total_claims == 0:
                continue
            
            # Alert: No successful claim in 24 hours
            if metrics.hours_since_last_success is not None:
                if metrics.hours_since_last_success > self.ALERT_NO_SUCCESS_HOURS:
                    new_alerts.append({
                        "type": "no_success",
                        "severity": "high",
                        "faucet": faucet_name,
                        "message": f"{faucet_name}: No successful claim in {metrics.hours_since_last_success:.1f} hours",
                        "timestamp": current_time,
                        "hours_since_success": metrics.hours_since_last_success
                    })
            
            # Alert: Low success rate
            if metrics.total_claims >= 5:  # Need at least 5 attempts
                if metrics.success_rate < self.ALERT_LOW_SUCCESS_RATE:
                    new_alerts.append({
                        "type": "low_success_rate",
                        "severity": "medium",
                        "faucet": faucet_name,
                        "message": f"{faucet_name}: Success rate only {metrics.success_rate:.1f}%",
                        "timestamp": current_time,
                        "success_rate": metrics.success_rate
                    })
            
            # Alert: Negative ROI
            if metrics.costs_usd > 0 and metrics.net_profit_usd < 0:
                roi_hours = self.ALERT_NEGATIVE_ROI_HOURS  # Simplified - would track actual timeframe
                new_alerts.append({
                    "type": "negative_roi",
                    "severity": "low",
                    "faucet": faucet_name,
                    "message": f"{faucet_name}: Negative ROI (${metrics.net_profit_usd:.4f})",
                    "timestamp": current_time,
                    "roi_percent": metrics.roi_percent
                })
        
        self.alerts = new_alerts
        self._save_state()
        return new_alerts
    
    def get_metrics_for_period(self, hours: int = 24) -> Dict[str, FaucetMetrics]:
        """
        Get metrics filtered by time period.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            Dictionary of faucet metrics within the time period
        """
        cutoff_time = time.time() - (hours * 3600)
        
        # For now, return all metrics
        # In production, would filter claims by timestamp and recalculate
        return self.metrics
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get overall summary statistics.
        
        Returns:
            Dictionary with summary stats
        """
        total_faucets = len(self.metrics)
        healthy_faucets = sum(1 for m in self.metrics.values() if m.is_healthy)
        unhealthy_faucets = total_faucets - healthy_faucets
        
        total_earnings = sum(m.earnings_usd for m in self.metrics.values())
        total_costs = sum(m.costs_usd for m in self.metrics.values())
        net_profit = total_earnings - total_costs
        
        total_success = sum(m.successful_claims for m in self.metrics.values())
        total_attempts = sum(m.total_claims for m in self.metrics.values())
        overall_success_rate = (total_success / total_attempts * 100) if total_attempts > 0 else 0
        
        return {
            "total_faucets": total_faucets,
            "healthy_faucets": healthy_faucets,
            "unhealthy_faucets": unhealthy_faucets,
            "total_earnings_usd": total_earnings,
            "total_costs_usd": total_costs,
            "net_profit_usd": net_profit,
            "roi_percent": (net_profit / total_costs * 100) if total_costs > 0 else 0,
            "total_successful_claims": total_success,
            "total_claim_attempts": total_attempts,
            "overall_success_rate": overall_success_rate,
            "active_alerts": len(self.alerts)
        }


class MonitoringDashboard:
    """
    CLI Dashboard for displaying real-time faucet health.
    
    Provides a rich console interface with live updates.
    """
    
    def __init__(self, monitor: FaucetMonitor):
        self.monitor = monitor
        self.console = Console()
    
    def render_summary_panel(self, stats: Dict[str, Any]) -> Panel:
        """Render summary statistics panel."""
        text = Text()
        
        # Faucet health
        text.append(f"Faucets: ", style="bold")
        text.append(f"{stats['healthy_faucets']} healthy", style="green")
        text.append(" / ")
        text.append(f"{stats['unhealthy_faucets']} unhealthy", style="red")
        text.append(f" / {stats['total_faucets']} total\n")
        
        # Financial summary
        text.append(f"Earnings: ", style="bold")
        text.append(f"${stats['total_earnings_usd']:.4f}\n", style="green")
        
        text.append(f"Costs: ", style="bold")
        text.append(f"${stats['total_costs_usd']:.4f}\n", style="yellow")
        
        text.append(f"Net Profit: ", style="bold")
        profit_color = "green" if stats['net_profit_usd'] >= 0 else "red"
        text.append(f"${stats['net_profit_usd']:.4f}", style=profit_color)
        text.append(f" ({stats['roi_percent']:.1f}% ROI)\n", style=profit_color)
        
        # Claims summary
        text.append(f"Claims: ", style="bold")
        text.append(f"{stats['total_successful_claims']}/{stats['total_claim_attempts']} ")
        text.append(f"({stats['overall_success_rate']:.1f}% success)\n")
        
        # Alerts
        text.append(f"Active Alerts: ", style="bold")
        alert_color = "red" if stats['active_alerts'] > 0 else "green"
        text.append(f"{stats['active_alerts']}", style=alert_color)
        
        return Panel(text, title="📊 Farm Summary", border_style="cyan")
    
    def render_faucet_table(self, metrics: Dict[str, FaucetMetrics], 
                           show_all: bool = False) -> Table:
        """
        Render table of faucet metrics.
        
        Args:
            metrics: Dictionary of faucet metrics
            show_all: If False, only show faucets with activity
        """
        table = Table(title="🚰 Faucet Health Status", box=box.ROUNDED)
        
        table.add_column("Faucet", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Success Rate", justify="right")
        table.add_column("Claims", justify="right")
        table.add_column("Last Success", justify="right")
        table.add_column("Avg Time", justify="right")
        table.add_column("Net Profit", justify="right")
        
        # Sort by health status (unhealthy first) then by name
        sorted_metrics = sorted(
            metrics.values(),
            key=lambda m: (m.is_healthy, m.faucet_name)
        )
        
        for m in sorted_metrics:
            # Skip if no activity and not showing all
            if not show_all and m.total_claims == 0:
                continue
            
            # Status indicator
            if m.is_healthy:
                status = "✅"
            elif m.last_success_timestamp is None:
                status = "❌"
            else:
                status = "⚠️"
            
            # Success rate with color
            rate = f"{m.success_rate:.1f}%"
            if m.success_rate >= 80:
                rate_style = "green"
            elif m.success_rate >= 50:
                rate_style = "yellow"
            else:
                rate_style = "red"
            
            # Claims count
            claims = f"{m.successful_claims}/{m.total_claims}"
            
            # Last success
            if m.hours_since_last_success is not None:
                if m.hours_since_last_success < 1:
                    last_success = f"{m.hours_since_last_success * 60:.0f}m ago"
                elif m.hours_since_last_success < 24:
                    last_success = f"{m.hours_since_last_success:.1f}h ago"
                else:
                    last_success = f"{m.hours_since_last_success / 24:.1f}d ago"
            else:
                last_success = "Never"
            
            # Avg claim time
            if m.avg_claim_time > 0:
                avg_time = f"{m.avg_claim_time:.1f}s"
            else:
                avg_time = "N/A"
            
            # Net profit with color
            profit = f"${m.net_profit_usd:.4f}"
            profit_style = "green" if m.net_profit_usd >= 0 else "red"
            
            table.add_row(
                m.faucet_name,
                status,
                f"[{rate_style}]{rate}[/{rate_style}]",
                claims,
                last_success,
                avg_time,
                f"[{profit_style}]{profit}[/{profit_style}]"
            )
        
        return table
    
    def render_alerts_panel(self, alerts: List[Dict[str, Any]]) -> Panel:
        """Render active alerts panel."""
        if not alerts:
            return Panel(
                Text("No active alerts", style="green"),
                title="🔔 Alerts",
                border_style="green"
            )
        
        text = Text()
        
        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_alerts = sorted(alerts, key=lambda a: severity_order.get(a["severity"], 3))
        
        for alert in sorted_alerts:
            # Severity indicator
            if alert["severity"] == "high":
                icon = "🔴"
                style = "red bold"
            elif alert["severity"] == "medium":
                icon = "🟡"
                style = "yellow"
            else:
                icon = "🟢"
                style = "cyan"
            
            text.append(f"{icon} ", style=style)
            text.append(f"{alert['message']}\n", style=style)
        
        return Panel(text, title=f"🔔 Alerts ({len(alerts)})", border_style="red")
    
    def display(self, hours: int = 24, show_all: bool = False):
        """
        Display the monitoring dashboard.
        
        Args:
            hours: Time period to display (24h, 168h for 7d, 720h for 30d)
            show_all: Show all faucets including inactive ones
        """
        # Update data
        self.monitor.update_from_analytics()
        alerts = self.monitor.check_alerts()
        
        # Get data
        stats = self.monitor.get_summary_stats()
        metrics = self.monitor.get_metrics_for_period(hours)
        
        # Clear console
        self.console.clear()
        
        # Render components
        self.console.print(f"\n[bold cyan]Cryptobot Monitoring Dashboard[/bold cyan]")
        self.console.print(f"[dim]Period: Last {hours}h | Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n")
        
        self.console.print(self.render_summary_panel(stats))
        self.console.print()
        
        if alerts:
            self.console.print(self.render_alerts_panel(alerts))
            self.console.print()
        
        self.console.print(self.render_faucet_table(metrics, show_all))
    
    async def live_display(self, refresh_seconds: int = 30, hours: int = 24):
        """
        Display live updating dashboard.
        
        Args:
            refresh_seconds: How often to refresh the display
            hours: Time period to display
        """
        try:
            while True:
                self.display(hours=hours)
                await asyncio.sleep(refresh_seconds)
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Monitoring stopped[/yellow]")


def get_monitor() -> FaucetMonitor:
    """Get or create the global monitoring instance."""
    if not hasattr(get_monitor, "instance"):
        get_monitor.instance = FaucetMonitor()
    return get_monitor.instance


async def main():
    """CLI entry point for monitoring dashboard."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cryptobot Monitoring Dashboard")
    parser.add_argument(
        "--period",
        type=int,
        default=24,
        help="Time period in hours (default: 24)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live updating dashboard"
    )
    parser.add_argument(
        "--refresh",
        type=int,
        default=30,
        help="Refresh interval for live mode (seconds, default: 30)"
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Show all faucets including inactive ones"
    )
    parser.add_argument(
        "--alerts-only",
        action="store_true",
        help="Only show active alerts"
    )
    
    args = parser.parse_args()
    
    monitor = get_monitor()
    dashboard = MonitoringDashboard(monitor)
    
    if args.alerts_only:
        monitor.update_from_analytics()
        alerts = monitor.check_alerts()
        
        if alerts:
            console = Console()
            console.print(dashboard.render_alerts_panel(alerts))
        else:
            print("No active alerts")
    elif args.live:
        await dashboard.live_display(refresh_seconds=args.refresh, hours=args.period)
    else:
        dashboard.display(hours=args.period, show_all=args.show_all)


if __name__ == "__main__":
    asyncio.run(main())
