"""
Profitability Analytics Dashboard Builder

Consolidates earnings and withdrawal data to generate comprehensive
profitability reports with rich-formatted panels.
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box

logger = logging.getLogger(__name__)


class DashboardBuilder:
    """
    Builds comprehensive profitability analytics dashboard.
    
    Consolidates data from:
    - earnings_analytics.json (claim records and costs)
    - withdrawal_analytics.db (withdrawal transactions)
    
    Displays:
    - Summary metrics (earnings USD, costs, net profit, ROI %)
    - Per-faucet earnings table
    - Monthly projections
    - Cost breakdown
    - Withdrawal performance
    """
    
    def __init__(self, hours: int = 24):
        """
        Initialize dashboard builder.
        
        Args:
            hours: Time window for analysis (default 24 hours)
        """
        self.hours = hours
        self.cutoff_time = time.time() - (hours * 3600)
        
        # File paths
        self.earnings_file = os.path.join(
            os.path.dirname(__file__), "..", "earnings_analytics.json"
        )
        self.withdrawal_db = os.path.join(
            os.path.dirname(__file__), "..", "withdrawal_analytics.db"
        )
        
        # Data storage
        self.claims_data: List[Dict] = []
        self.costs_data: List[Dict] = []
        self.withdrawal_data: List[Dict] = []
        
        # Configuration thresholds
        self.low_success_rate_threshold = 40.0  # %
        self.min_claims_for_stats = 10
        
    async def load_data(self) -> Tuple[bool, bool]:
        """
        Load data from earnings and withdrawal sources.
        
        Returns:
            Tuple of (earnings_loaded, withdrawals_loaded)
        """
        earnings_loaded = self._load_earnings_data()
        withdrawals_loaded = self._load_withdrawal_data()
        
        return earnings_loaded, withdrawals_loaded
    
    def _load_earnings_data(self) -> bool:
        """Load earnings data from JSON file."""
        try:
            if not os.path.exists(self.earnings_file):
                logger.warning(f"Earnings file not found: {self.earnings_file}")
                return False
            
            with open(self.earnings_file, "r") as f:
                data = json.load(f)
                
            # Filter by time window
            all_claims = data.get("claims", [])
            all_costs = data.get("costs", [])
            
            self.claims_data = [
                c for c in all_claims 
                if c.get("timestamp", 0) >= self.cutoff_time
            ]
            self.costs_data = [
                c for c in all_costs
                if c.get("timestamp", 0) >= self.cutoff_time
            ]
            
            logger.info(
                f"Loaded {len(self.claims_data)} claims and {len(self.costs_data)} costs"
            )
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted earnings file: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load earnings data: {e}")
            return False
    
    def _load_withdrawal_data(self) -> bool:
        """Load withdrawal data from SQLite database."""
        try:
            if not os.path.exists(self.withdrawal_db):
                logger.warning(f"Withdrawal DB not found: {self.withdrawal_db}")
                return False
            
            conn = sqlite3.connect(self.withdrawal_db)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    timestamp, faucet, cryptocurrency, amount,
                    network_fee, platform_fee, withdrawal_method, status
                FROM withdrawals
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            """, (self.cutoff_time,))
            
            columns = ["timestamp", "faucet", "cryptocurrency", "amount",
                      "network_fee", "platform_fee", "withdrawal_method", "status"]
            
            self.withdrawal_data = [
                dict(zip(columns, row)) for row in cursor.fetchall()
            ]
            
            conn.close()
            
            logger.info(f"Loaded {len(self.withdrawal_data)} withdrawals")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load withdrawal data: {e}")
            return False
    
    async def _convert_to_usd(self, amount: float, currency: str) -> float:
        """
        Convert cryptocurrency amount to USD using price feed.
        
        Args:
            amount: Amount in smallest unit (satoshi, wei, etc.)
            currency: Currency code (BTC, LTC, etc.)
            
        Returns:
            USD value
        """
        try:
            from core.analytics import get_price_feed
            
            price_feed = get_price_feed()
            usd_value = await price_feed.convert_to_usd(amount, currency)
            return usd_value
        except Exception as e:
            logger.warning(f"Price conversion failed for {currency}: {e}")
            return 0.0
    
    async def calculate_summary_metrics(self) -> Dict[str, Any]:
        """
        Calculate overall summary metrics.
        
        Returns:
            Dict with total_earnings_usd, total_costs_usd, net_profit_usd, roi_percent
        """
        # Calculate earnings by currency
        earnings_by_currency = defaultdict(float)
        
        for claim in self.claims_data:
            if claim.get("success", False):
                currency = claim.get("currency", "unknown").upper()
                amount = claim.get("amount", 0.0)
                if currency != "UNKNOWN":
                    earnings_by_currency[currency] += amount
        
        # Convert all earnings to USD concurrently
        conversion_tasks = [
            self._convert_to_usd(amount, currency)
            for currency, amount in earnings_by_currency.items()
        ]
        
        usd_values = await asyncio.gather(*conversion_tasks, return_exceptions=True)
        
        total_earnings_usd = sum(
            val for val in usd_values
            if not isinstance(val, Exception) and val is not None
        )
        
        # Calculate costs
        total_costs_usd = sum(
            cost.get("amount_usd", 0.0) for cost in self.costs_data
        )
        
        # Calculate net profit and ROI
        net_profit_usd = total_earnings_usd - total_costs_usd
        roi_percent = (
            (total_earnings_usd / total_costs_usd - 1) * 100
            if total_costs_usd > 0 else 0.0
        )
        
        return {
            "total_earnings_usd": total_earnings_usd,
            "total_costs_usd": total_costs_usd,
            "net_profit_usd": net_profit_usd,
            "roi_percent": roi_percent,
            "total_claims": len(self.claims_data),
            "successful_claims": sum(
                1 for c in self.claims_data if c.get("success", False)
            )
        }
    
    def calculate_faucet_stats(self) -> Dict[str, Dict]:
        """
        Calculate per-faucet statistics.
        
        Returns:
            Dict mapping faucet name to stats dict
        """
        stats = defaultdict(lambda: {
            "total_claims": 0,
            "successful_claims": 0,
            "success_rate": 0.0,
            "earnings_crypto": defaultdict(float),
            "costs_usd": 0.0
        })
        
        # Process claims
        for claim in self.claims_data:
            faucet = claim.get("faucet", "unknown")
            stats[faucet]["total_claims"] += 1
            
            if claim.get("success", False):
                stats[faucet]["successful_claims"] += 1
                currency = claim.get("currency", "unknown").upper()
                amount = claim.get("amount", 0.0)
                if currency != "UNKNOWN":
                    stats[faucet]["earnings_crypto"][currency] += amount
        
        # Process costs
        for cost in self.costs_data:
            faucet = cost.get("faucet")
            if faucet:
                stats[faucet]["costs_usd"] += cost.get("amount_usd", 0.0)
        
        # Calculate success rates
        for faucet in stats:
            total = stats[faucet]["total_claims"]
            if total > 0:
                stats[faucet]["success_rate"] = (
                    stats[faucet]["successful_claims"] / total * 100
                )
        
        return dict(stats)
    
    async def calculate_faucet_earnings_usd(
        self, 
        faucet_stats: Dict[str, Dict]
    ) -> Dict[str, float]:
        """
        Convert faucet earnings to USD.
        
        Args:
            faucet_stats: Stats dict from calculate_faucet_stats
            
        Returns:
            Dict mapping faucet name to total USD earnings
        """
        earnings_usd = {}
        
        for faucet, stats in faucet_stats.items():
            total_usd = 0.0
            
            # Convert each currency to USD
            for currency, amount in stats["earnings_crypto"].items():
                usd_value = await self._convert_to_usd(amount, currency)
                total_usd += usd_value
            
            earnings_usd[faucet] = total_usd
        
        return earnings_usd
    
    def build_summary_panel(self, metrics: Dict[str, Any]) -> Panel:
        """Create summary metrics panel."""
        earnings = metrics["total_earnings_usd"]
        costs = metrics["total_costs_usd"]
        profit = metrics["net_profit_usd"]
        roi = metrics["roi_percent"]
        
        # Color coding based on profitability
        profit_color = "green" if profit > 0 else "red" if profit < 0 else "yellow"
        roi_color = "green" if roi > 0 else "red" if roi < 0 else "yellow"
        
        content = (
            f"[cyan]Total Earnings:[/cyan]  [white]${earnings:.4f} USD[/white]\n"
            f"[cyan]Total Costs:[/cyan]     [white]${costs:.4f} USD[/white]\n"
            f"[cyan]Net Profit:[/cyan]      [{profit_color}]${profit:.4f} USD[/{profit_color}]\n"
            f"[cyan]ROI:[/cyan]             [{roi_color}]{roi:+.2f}%[/{roi_color}]\n"
            f"[cyan]Total Claims:[/cyan]    [white]{metrics['total_claims']} "
            f"({metrics['successful_claims']} successful)[/white]"
        )
        
        return Panel(
            content,
            title=f"[bold]Summary Metrics (Last {self.hours}h)[/bold]",
            border_style="blue",
            box=box.ROUNDED
        )
    
    async def build_faucet_table(
        self, 
        faucet_stats: Dict[str, Dict],
        earnings_usd: Dict[str, float]
    ) -> Table:
        """Create per-faucet earnings table."""
        table = Table(
            title=f"Per-Faucet Performance (Last {self.hours}h)",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("Faucet", style="cyan", no_wrap=True)
        table.add_column("Claims", justify="right")
        table.add_column("Success %", justify="right")
        table.add_column("Earnings USD", justify="right")
        table.add_column("Costs USD", justify="right")
        table.add_column("Net Profit", justify="right")
        table.add_column("Hourly Rate", justify="right")
        
        # Sort by net profit (descending)
        sorted_faucets = sorted(
            faucet_stats.items(),
            key=lambda x: earnings_usd.get(x[0], 0.0) - x[1]["costs_usd"],
            reverse=True
        )
        
        for faucet, stats in sorted_faucets:
            # Skip if insufficient data
            if stats["total_claims"] < self.min_claims_for_stats:
                continue
            
            earnings = earnings_usd.get(faucet, 0.0)
            costs = stats["costs_usd"]
            net_profit = earnings - costs
            hourly_rate = net_profit / self.hours if self.hours > 0 else 0.0
            success_rate = stats["success_rate"]
            
            # Color coding
            profit_color = "green" if net_profit > 0 else "red" if net_profit < 0 else "yellow"
            success_color = (
                "green" if success_rate >= 70 else
                "yellow" if success_rate >= self.low_success_rate_threshold else
                "red"
            )
            
            table.add_row(
                faucet,
                f"{stats['successful_claims']}/{stats['total_claims']}",
                f"[{success_color}]{success_rate:.1f}%[/{success_color}]",
                f"${earnings:.4f}",
                f"${costs:.4f}",
                f"[{profit_color}]${net_profit:.4f}[/{profit_color}]",
                f"${hourly_rate:.4f}/hr"
            )
        
        return table
    
    def build_monthly_projection_panel(
        self, 
        metrics: Dict[str, Any]
    ) -> Panel:
        """Create monthly projection panel."""
        # Project to 30 days based on current rate
        daily_profit = metrics["net_profit_usd"] / self.hours * 24
        monthly_projection = daily_profit * 30
        
        # Color based on projection
        color = "green" if monthly_projection > 0 else "red" if monthly_projection < 0 else "yellow"
        
        # Profitability alerts
        alerts = []
        
        if metrics["roi_percent"] < 0:
            alerts.append("[red]⚠️  NEGATIVE ROI - System is losing money[/red]")
        elif metrics["roi_percent"] < 20:
            alerts.append("[yellow]⚠️  Low ROI - Consider optimization[/yellow]")
        
        # Check success rate
        if metrics["total_claims"] > 0:
            overall_success_rate = (
                metrics["successful_claims"] / metrics["total_claims"] * 100
            )
            if overall_success_rate < self.low_success_rate_threshold:
                alerts.append(
                    f"[yellow]⚠️  Low success rate: {overall_success_rate:.1f}%[/yellow]"
                )
        
        alert_text = "\n".join(alerts) if alerts else "[green]✅ All systems healthy[/green]"
        
        content = (
            f"[cyan]Daily Profit:[/cyan]    [{color}]${daily_profit:.4f}[/{color}]\n"
            f"[cyan]30-Day Projection:[/cyan] [{color}]${monthly_projection:.4f}[/{color}]\n\n"
            f"[bold]Alerts:[/bold]\n{alert_text}"
        )
        
        return Panel(
            content,
            title="[bold]Monthly Projections & Alerts[/bold]",
            border_style="yellow",
            box=box.ROUNDED
        )
    
    def build_cost_breakdown_table(self) -> Table:
        """Create cost breakdown table by faucet."""
        table = Table(
            title=f"Cost Breakdown (Last {self.hours}h)",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("Faucet", style="cyan", no_wrap=True)
        table.add_column("Type", style="white")
        table.add_column("Count", justify="right")
        table.add_column("Total Cost USD", justify="right")
        table.add_column("Avg Cost USD", justify="right")
        
        # Aggregate costs by faucet and type
        cost_aggregates = defaultdict(lambda: defaultdict(lambda: {
            "count": 0,
            "total": 0.0
        }))
        
        for cost in self.costs_data:
            faucet = cost.get("faucet", "global")
            cost_type = cost.get("type", "unknown")
            amount = cost.get("amount_usd", 0.0)
            
            cost_aggregates[faucet][cost_type]["count"] += 1
            cost_aggregates[faucet][cost_type]["total"] += amount
        
        # Sort by total cost (descending)
        for faucet in sorted(
            cost_aggregates.keys(),
            key=lambda f: sum(
                v["total"] for v in cost_aggregates[f].values()
            ),
            reverse=True
        ):
            for cost_type, data in cost_aggregates[faucet].items():
                count = data["count"]
                total = data["total"]
                avg = total / count if count > 0 else 0.0
                
                table.add_row(
                    faucet,
                    cost_type,
                    str(count),
                    f"${total:.4f}",
                    f"${avg:.4f}"
                )
        
        if not cost_aggregates:
            table.add_row("No data", "-", "-", "-", "-")
        
        return table
    
    def build_withdrawal_table(self) -> Table:
        """Create withdrawal performance table."""
        table = Table(
            title=f"Withdrawal Performance (Last {self.hours}h)",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )
        
        table.add_column("Faucet", style="cyan", no_wrap=True)
        table.add_column("Cryptocurrency", style="white")
        table.add_column("Amount", justify="right")
        table.add_column("Fees", justify="right")
        table.add_column("Net", justify="right")
        table.add_column("Status", justify="center")
        
        for withdrawal in self.withdrawal_data[:20]:  # Show last 20
            faucet = withdrawal["faucet"]
            crypto = withdrawal["cryptocurrency"]
            amount = withdrawal["amount"]
            total_fee = withdrawal["network_fee"] + withdrawal["platform_fee"]
            net = amount - total_fee
            status = withdrawal["status"]
            
            status_color = (
                "green" if status == "success" else
                "red" if status == "failed" else
                "yellow"
            )
            
            table.add_row(
                faucet,
                crypto,
                f"{amount:.8f}",
                f"{total_fee:.8f}",
                f"{net:.8f}",
                f"[{status_color}]{status}[/{status_color}]"
            )
        
        if not self.withdrawal_data:
            table.add_row(
                "No withdrawals", "-", "-", "-", "-", "-"
            )
        
        return table
    
    async def build_dashboard(self) -> None:
        """
        Build and display the complete dashboard.
        
        This is the main entry point for dashboard generation.
        """
        console = Console()
        
        # Load data
        console.print("\n[cyan]Loading analytics data...[/cyan]")
        earnings_ok, withdrawals_ok = await self.load_data()
        
        if not earnings_ok and not withdrawals_ok:
            console.print(
                Panel(
                    "[red]No data available[/red]\n\n"
                    "Please ensure the bot has been running and generating data:\n"
                    "- earnings_analytics.json\n"
                    "- withdrawal_analytics.db",
                    title="[bold red]Error[/bold red]",
                    border_style="red"
                )
            )
            return
        
        # Calculate metrics
        console.print("[cyan]Calculating profitability metrics...[/cyan]")
        
        summary_metrics = await self.calculate_summary_metrics()
        faucet_stats = self.calculate_faucet_stats()
        earnings_usd = await self.calculate_faucet_earnings_usd(faucet_stats)
        
        # Build panels and tables
        console.print("\n")
        console.print("=" * 80)
        console.print(
            f"[bold cyan]CRYPTOBOT PROFITABILITY DASHBOARD[/bold cyan]",
            justify="center"
        )
        console.print(
            f"[white]Analysis Period: Last {self.hours} hours | "
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/white]",
            justify="center"
        )
        console.print("=" * 80)
        console.print()
        
        # 1. Summary Panel
        summary_panel = self.build_summary_panel(summary_metrics)
        console.print(summary_panel)
        console.print()
        
        # 2. Faucet Performance Table
        if faucet_stats:
            faucet_table = await self.build_faucet_table(faucet_stats, earnings_usd)
            console.print(faucet_table)
            console.print()
        else:
            console.print("[yellow]No faucet data available for this period[/yellow]\n")
        
        # 3. Monthly Projections
        projection_panel = self.build_monthly_projection_panel(summary_metrics)
        console.print(projection_panel)
        console.print()
        
        # 4. Cost Breakdown
        if self.costs_data:
            cost_table = self.build_cost_breakdown_table()
            console.print(cost_table)
            console.print()
        else:
            console.print("[yellow]No cost data available for this period[/yellow]\n")
        
        # 5. Withdrawal Performance
        if withdrawals_ok and self.withdrawal_data:
            withdrawal_table = self.build_withdrawal_table()
            console.print(withdrawal_table)
            console.print()
        else:
            console.print("[yellow]No withdrawal data available for this period[/yellow]\n")
        
        console.print("=" * 80)
        console.print()
