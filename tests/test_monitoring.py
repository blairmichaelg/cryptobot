"""
Test script for the monitoring dashboard.

Generates sample data and displays the dashboard.
"""

import asyncio
import time
from core.monitoring import FaucetMonitor, MonitoringDashboard

def test_monitoring_dashboard():
    """Test the monitoring dashboard with sample data."""
    
    # Create monitor instance
    monitor = FaucetMonitor()
    
    # Update from analytics file (will load real data if available)
    monitor.update_from_analytics()
    
    # Check for alerts
    alerts = monitor.check_alerts()
    
    # Create and display dashboard
    dashboard = MonitoringDashboard(monitor)
    
    # Display 24h metrics
    print("\n" + "="*80)
    print("TESTING: 24-Hour Metrics")
    print("="*80 + "\n")
    dashboard.display(hours=24, show_all=True)
    
    # Show summary stats
    print("\n" + "="*80)
    print("TESTING: Summary Statistics")
    print("="*80 + "\n")
    stats = monitor.get_summary_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    # Show alerts
    print("\n" + "="*80)
    print(f"TESTING: Alerts ({len(alerts)} active)")
    print("="*80 + "\n")
    for alert in alerts:
        print(f"[{alert['severity'].upper()}] {alert['message']}")
    
    if not alerts:
        print("No active alerts")
    
    print("\n✅ Monitoring dashboard test complete!\n")

if __name__ == "__main__":
    test_monitoring_dashboard()
