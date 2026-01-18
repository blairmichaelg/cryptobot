#!/usr/bin/env python3
"""
Demonstration script for WithdrawalAnalytics module.

This shows how to use the analytics system to track withdrawals,
calculate profitability, and get recommendations.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.withdrawal_analytics import get_analytics


def demo_basic_usage():
    """Demonstrate basic analytics usage."""
    print("=" * 60)
    print("WITHDRAWAL ANALYTICS DEMO")
    print("=" * 60)
    print()
    
    # Get analytics instance
    analytics = get_analytics()
    
    # Record some example withdrawals
    print("📝 Recording example withdrawals...\n")
    
    analytics.record_withdrawal(
        faucet="FreeBitcoin",
        cryptocurrency="BTC",
        amount=0.00015,
        network_fee=0.000015,
        platform_fee=0.000005,
        withdrawal_method="faucetpay",
        status="success",
        balance_before=0.0005,
        balance_after=0.00035,
        notes="Hourly roll withdrawal"
    )
    
    analytics.record_withdrawal(
        faucet="LitePick",
        cryptocurrency="LTC",
        amount=0.05,
        network_fee=0.005,
        platform_fee=0.0,
        withdrawal_method="direct",
        status="success",
        balance_before=0.1,
        balance_after=0.05,
        tx_id="ltc_tx_12345"
    )
    
    analytics.record_withdrawal(
        faucet="DogePick",
        cryptocurrency="DOGE",
        amount=100.0,
        network_fee=1.0,
        platform_fee=0.0,
        withdrawal_method="faucetpay",
        status="success",
        balance_before=200.0,
        balance_after=100.0
    )
    
    print("✅ Recorded 3 withdrawals\n")
    
    # Calculate effective rates
    print("📊 Calculating effective rates...\n")
    rates = analytics.calculate_effective_rate(hours=24)
    
    print(f"Total Earned:    {rates['total_earned']:.8f}")
    print(f"Total Fees:      {rates['total_fees']:.8f}")
    print(f"Net Profit:      {rates['net_profit']:.8f}")
    print(f"Fee Percentage:  {rates['fee_percentage']:.2f}%")
    print(f"Hourly Rate:     {rates['hourly_rate']:.8f}")
    print()
    
    # Get faucet performance
    print("🏆 Faucet Performance Breakdown:\n")
    performance = analytics.get_faucet_performance(hours=24)
    
    for faucet, stats in performance.items():
        print(f"{faucet}:")
        print(f"  Success Rate:   {stats['success_rate']:.1f}%")
        print(f"  Total Earned:   {stats['total_earned']:.8f}")
        print(f"  Net Profit:     {stats['net_profit']:.8f}")
        print(f"  Fee %:          {stats['fee_percentage']:.2f}%")
        print()
    
    # Get recommendation
    print("💡 Withdrawal Recommendations:\n")
    
    # Check recommendation for FreeBitcoin
    rec = analytics.recommend_withdrawal_strategy(
        current_balance=0.0005,
        cryptocurrency="BTC",
        faucet="FreeBitcoin"
    )
    
    print(f"FreeBitcoin (0.0005 BTC balance):")
    print(f"  Action:         {rec['action'].upper()}")
    print(f"  Reason:         {rec['reason']}")
    print(f"  Best Method:    {rec['optimal_method']}")
    print(f"  Best Timing:    {rec['optimal_timing']}")
    print()
    
    # Generate report
    print("=" * 60)
    print("📈 DAILY REPORT")
    print("=" * 60)
    print()
    
    report = analytics.generate_report(period="daily")
    print(report)
    
    # Show withdrawal history
    print("\n" + "=" * 60)
    print("📜 RECENT WITHDRAWAL HISTORY")
    print("=" * 60)
    print()
    
    history = analytics.get_withdrawal_history(limit=5)
    for record in history:
        print(f"[{record['faucet']}] {record['amount']:.8f} {record['cryptocurrency']}")
        print(f"  Status: {record['status']} | Method: {record['withdrawal_method']}")
        print(f"  Fees: {record['network_fee'] + record['platform_fee']:.8f}")
        if record['tx_id']:
            print(f"  TX ID: {record['tx_id']}")
        print()


if __name__ == "__main__":
    demo_basic_usage()
