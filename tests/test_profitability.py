# pylint: disable=not-callable
"""
Test script for profitability tracking and prioritization.
"""
import asyncio
import time
from core.analytics import EarningsTracker, get_tracker
from core.config import BotSettings

async def test_profitability_tracking():
    """Test the profitability tracking functionality."""
    print("\n" + "="*60)
    print("PROFITABILITY TRACKING TEST")
    print("="*60)
    
    # Get or create tracker
    tracker = get_tracker()
    
    # Simulate some test claims with different performance profiles
    test_data = [
        # High performer: good ROI
        ("firefaucet", True, 1000, "BTC"),
        ("firefaucet", True, 1200, "BTC"),
        ("firefaucet", True, 950, "BTC"),
        
        # Medium performer: moderate ROI
        ("cointiply", True, 500, "BTC"),
        ("cointiply", False, 0, "BTC"),
        ("cointiply", True, 480, "BTC"),
        
        # Low performer: poor ROI
        ("test_low", True, 100, "BTC"),
        ("test_low", False, 0, "BTC"),
        ("test_low", False, 0, "BTC"),
        ("test_low", True, 90, "BTC"),
    ]
    
    print("\n1. Recording test claims...")
    for faucet, success, amount, currency in test_data:
        tracker.record_claim(faucet, success, amount, currency, allow_test=True)
        # Record costs for successful claims
        if success:
            tracker.record_cost("captcha", 0.003, faucet)
    
    print(f"   ✓ Recorded {len(test_data)} test claims")
    
    # Test individual faucet profitability
    print("\n2. Testing get_faucet_profitability()...")
    for faucet in ["firefaucet", "cointiply", "test_low"]:
        try:
            metrics = tracker.get_faucet_profitability(faucet, days=1)
            print(f"\n   {faucet}:")
            print(f"      Claims: {metrics['claim_count']} ({metrics['success_count']} successful)")
            print(f"      Success Rate: {metrics['success_rate']:.1f}%")
            print(f"      Earnings: ${metrics['total_earned_usd']:.6f}")
            print(f"      Costs: ${metrics['total_cost_usd']:.6f}")
            print(f"      Net Profit: ${metrics['net_profit_usd']:.6f}")
            print(f"      ROI: {metrics['roi_percentage']:.1f}%")
            print(f"      Profitability Score: {metrics['profitability_score']:.1f}")
        except Exception as e:
            print(f"   ✗ Error for {faucet}: {e}")
    
    # Test profitability report
    print("\n3. Testing get_profitability_report()...")
    try:
        report = tracker.get_profitability_report(days=1, min_claims=1)
        print(f"   ✓ Generated report with {len(report)} faucets")
        print("\n   Ranked by Profitability Score:")
        print("   " + "-"*56)
        print(f"   {'Faucet':<20} {'Score':<10} {'ROI':<10} {'Net Profit':<15}")
        print("   " + "-"*56)
        for entry in report:
            print(f"   {entry['faucet']:<20} {entry['profitability_score']:>7.1f}   "
                  f"{entry['roi_percentage']:>7.1f}%   ${entry['net_profit_usd']:>12.6f}")
    except Exception as e:
        print(f"   ✗ Error generating report: {e}")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60 + "\n")

async def test_priority_updates():
    """Test the priority update functionality (requires orchestrator)."""
    print("\n" + "="*60)
    print("PRIORITY UPDATE TEST (Simulation)")
    print("="*60)
    
    try:
        from core.orchestrator import JobScheduler
        from browser.instance import BrowserManager
        
        # Create minimal settings
        settings = BotSettings()
        
        # Create browser manager (won't actually launch browser)
        browser_manager = BrowserManager(settings)
        
        # Create scheduler
        scheduler = JobScheduler(settings, browser_manager, None)
        
        print("\n1. Testing update_job_priorities()...")
        update_fn = getattr(scheduler, "update_job_priorities", None)
        if not callable(update_fn):
            print("   ⚠️ update_job_priorities() not available on JobScheduler. Skipping test.")
            return
        assert callable(update_fn)
        update_fn()

        multipliers = getattr(scheduler, "faucet_priority_multipliers", {})
        print(f"\n2. Priority Multipliers: {len(multipliers)}")
        for faucet, multiplier in list(multipliers.items())[:5]:
            print(f"   {faucet}: {multiplier:.2f}")

        disabled = getattr(scheduler, "disabled_faucets", {})
        print(f"\n3. Disabled Faucets: {len(disabled)}")
        for faucet, timestamp in disabled.items():
            print(f"   {faucet}: disabled at {time.ctime(timestamp)}")
        
        print("\n✓ Priority update test complete")
        
    except Exception as e:
        print(f"\n✗ Priority update test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    print("\n🔬 Starting Profitability System Tests...\n")
    
    # Run tests
    asyncio.run(test_profitability_tracking())
    asyncio.run(test_priority_updates())
    
    print("\n✅ All tests complete!\n")
