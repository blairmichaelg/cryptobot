import sys
import os
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich import box

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analytics import get_tracker
from core.config import BotSettings

console = Console()

def generate_dashboard_layout() -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="stats", ratio=1),
        Layout(name="faucets", ratio=2)
    )
    return layout

def get_header() -> Panel:
    return Panel(
        f"[bold blue]Cryptobot ROI Dashboard[/] | [white]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]",
        box=box.DOUBLE
    )

def get_stats_panel(tracker) -> Panel:
    stats = tracker.get_session_stats()
    table = Table(show_header=False, box=None)
    table.add_row("Duration:", f"{stats['session_duration_hours']:.2f}h")
    table.add_row("Total Claims:", str(stats['total_claims']))
    table.add_row("Success Rate:", f"[bold {'green' if stats['success_rate'] > 80 else 'yellow' if stats['success_rate'] > 50 else 'red'}]{stats['success_rate']:.1f}%[/]")
    
    table.add_section()
    table.add_row("[bold]Earnings:[/]", "")
    for cur, amt in stats['earnings_by_currency'].items():
        table.add_row(f"  {cur}:", f"{amt:.8f}")
    
    return Panel(table, title="[bold]Session Summary[/]", border_style="blue")

def get_faucets_table(tracker) -> Table:
    faucet_stats = tracker.get_faucet_stats(24)
    hourly_rates = tracker.get_hourly_rate(hours=24)
    
    table = Table(title="[bold]Faucet Performance (Last 24h)[/]", box=box.ROUNDED)
    table.add_column("Faucet")
    table.add_column("Success/Total")
    table.add_column("Rate %", justify="right")
    table.add_column("Earnings/hr", justify="right")
    
    for faucet, stats in sorted(faucet_stats.items(), key=lambda x: x[1]['success_rate'], reverse=True):
        sr = stats['success_rate']
        color = "green" if sr > 80 else "yellow" if sr > 50 else "red"
        rate = hourly_rates.get(faucet, 0)
        
        table.add_row(
            faucet,
            f"{stats['success']}/{stats['total']}",
            f"[{color}]{sr:.1f}%[/]",
            f"{rate:.6f}"
        )
    
    return table

def main():
    tracker = get_tracker()
    layout = generate_dashboard_layout()
    
    with Live(layout, refresh_per_second=0.5, screen=True):
        while True:
            layout["header"].update(get_header())
            layout["stats"].update(get_stats_panel(tracker))
            layout["faucets"].update(get_faucets_table(tracker))
            layout["footer"].update(Panel(f"Press Ctrl+C to exit. Data file: {tracker.storage_file}", style="dim"))
            time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard closed.[/]")
