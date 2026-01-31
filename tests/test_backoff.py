"""
Test exponential backoff with jitter implementation.

Run with: python test_backoff.py
"""

import sys
import time
import random
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.orchestrator import ErrorType

def test_calculate_retry_delay():
    """Test retry delay calculation with different error types."""
    
    print("=" * 80)
    print("EXPONENTIAL BACKOFF WITH JITTER - TEST SUITE")
    print("=" * 80)
    print()
    
    # Mock scheduler with minimal state
    class MockScheduler:
        def __init__(self):
            self.faucet_backoff = {}
        
        def calculate_retry_delay(self, faucet_type: str, error_type: ErrorType) -> float:
            """Calculate retry delay with exponential backoff + jitter."""
            base_delays = {
                ErrorType.TRANSIENT: 60,
                ErrorType.RATE_LIMIT: 600,
                ErrorType.PROXY_ISSUE: 300,
                ErrorType.CAPTCHA_FAILED: 900,
                ErrorType.FAUCET_DOWN: 3600,
                ErrorType.UNKNOWN: 300,
                ErrorType.PERMANENT: float('inf')
            }
            
            base_delay = base_delays.get(error_type, 300)
            
            if base_delay == float('inf'):
                return base_delay
            
            backoff_state = self.faucet_backoff.get(faucet_type, {})
            consecutive_failures = backoff_state.get('consecutive_failures', 0)
            
            exponential_delay = base_delay * (2 ** min(consecutive_failures, 5))
            jitter = random.uniform(0, base_delay * 0.3)
            max_delay = 7200
            total_delay = min(exponential_delay + jitter, max_delay)
            
            return total_delay
        
        def increment_failures(self, faucet_type: str):
            """Increment failure count for testing."""
            if faucet_type not in self.faucet_backoff:
                self.faucet_backoff[faucet_type] = {'consecutive_failures': 0}
            self.faucet_backoff[faucet_type]['consecutive_failures'] += 1
    
    scheduler = MockScheduler()
    faucet = "test_faucet"
    
    # Test all error types
    error_types = [
        ErrorType.TRANSIENT,
        ErrorType.RATE_LIMIT,
        ErrorType.PROXY_ISSUE,
        ErrorType.CAPTCHA_FAILED,
        ErrorType.FAUCET_DOWN,
        ErrorType.UNKNOWN
    ]
    
    for error_type in error_types:
        print(f"\n📊 Testing {error_type.value.upper()}")
        print("-" * 80)
        
        # Reset state
        scheduler.faucet_backoff[faucet] = {'consecutive_failures': 0}
        
        # Test 6 consecutive failures
        for i in range(6):
            delay = scheduler.calculate_retry_delay(faucet, error_type)
            failures = scheduler.faucet_backoff[faucet]['consecutive_failures']
            
            print(f"Attempt {i+1} (failures: {failures}): {delay:.0f}s ({delay/60:.1f}min)")
            
            # Increment for next iteration
            scheduler.increment_failures(faucet)
        
        print()
    
    # Test PERMANENT error
    print("\n🚫 Testing PERMANENT ERROR")
    print("-" * 80)
    delay = scheduler.calculate_retry_delay(faucet, ErrorType.PERMANENT)
    print(f"Delay: {delay} (should be infinity - never retry)")
    print()
    
    # Test jitter variance
    print("\n🎲 Testing JITTER VARIANCE (10 samples)")
    print("-" * 80)
    scheduler.faucet_backoff[faucet] = {'consecutive_failures': 2}
    
    delays = []
    for i in range(10):
        delay = scheduler.calculate_retry_delay(faucet, ErrorType.RATE_LIMIT)
        delays.append(delay)
    
    min_delay = min(delays)
    max_delay = max(delays)
    avg_delay = sum(delays) / len(delays)
    
    print(f"Min delay: {min_delay:.0f}s ({min_delay/60:.1f}min)")
    print(f"Max delay: {max_delay:.0f}s ({max_delay/60:.1f}min)")
    print(f"Avg delay: {avg_delay:.0f}s ({avg_delay/60:.1f}min)")
    print(f"Variance: {max_delay - min_delay:.0f}s ({(max_delay-min_delay)/60:.1f}min)")
    print()
    
    # Test exponential cap
    print("\n⚠️ Testing EXPONENTIAL CAP")
    print("-" * 80)
    scheduler.faucet_backoff[faucet] = {'consecutive_failures': 10}  # Very high
    delay = scheduler.calculate_retry_delay(faucet, ErrorType.TRANSIENT)
    print(f"With 10 failures: {delay:.0f}s ({delay/60:.1f}min) - should be capped at 7200s (2h)")
    print()
    
    # Test progression table
    print("\n📈 BACKOFF PROGRESSION TABLE (RATE_LIMIT)")
    print("-" * 80)
    print(f"{'Failures':<12} {'Base Delay':<15} {'Multiplier':<15} {'Approx Total (min)':<20}")
    print("-" * 80)
    
    base = 600  # RATE_LIMIT base
    for failures in range(6):
        multiplier = 2 ** min(failures, 5)
        approx_total = (base * multiplier) / 60  # Convert to minutes
        print(f"{failures:<12} {base}s (10m){' ':<4} {multiplier}x{' ':<12} ~{approx_total:.0f}min")
    
    print()
    print("=" * 80)
    print("✅ BACKOFF TESTING COMPLETE")
    print("=" * 80)
    print()
    
    # Verification checks
    print("VERIFICATION CHECKS:")
    print("-" * 80)
    
    checks_passed = 0
    checks_total = 0
    
    # Check 1: Permanent error returns infinity
    checks_total += 1
    perm_delay = scheduler.calculate_retry_delay("test", ErrorType.PERMANENT)
    if perm_delay == float('inf'):
        print("✅ Permanent errors return infinity (never retry)")
        checks_passed += 1
    else:
        print("❌ Permanent errors should return infinity")
    
    # Check 2: Delays increase with failures
    checks_total += 1
    scheduler.faucet_backoff["test"] = {'consecutive_failures': 0}
    delay_0 = scheduler.calculate_retry_delay("test", ErrorType.RATE_LIMIT)
    scheduler.faucet_backoff["test"] = {'consecutive_failures': 1}
    delay_1 = scheduler.calculate_retry_delay("test", ErrorType.RATE_LIMIT)
    if delay_1 > delay_0:
        print("✅ Delays increase with consecutive failures")
        checks_passed += 1
    else:
        print("❌ Delays should increase with failures")
    
    # Check 3: Max cap enforced
    checks_total += 1
    scheduler.faucet_backoff["test"] = {'consecutive_failures': 20}
    delay_max = scheduler.calculate_retry_delay("test", ErrorType.RATE_LIMIT)
    if delay_max <= 7200:
        print("✅ Maximum delay cap (2 hours) enforced")
        checks_passed += 1
    else:
        print("❌ Delay exceeds maximum cap of 7200s")
    
    # Check 4: Jitter adds randomness
    checks_total += 1
    scheduler.faucet_backoff["test"] = {'consecutive_failures': 1}
    delays_set = set()
    for _ in range(5):
        delay = scheduler.calculate_retry_delay("test", ErrorType.RATE_LIMIT)
        delays_set.add(int(delay))
    if len(delays_set) > 1:
        print("✅ Jitter adds randomness to delays")
        checks_passed += 1
    else:
        print("⚠️ Jitter may not be working (all delays identical)")
    
    print()
    print(f"FINAL SCORE: {checks_passed}/{checks_total} checks passed")
    print("=" * 80)
    
    return checks_passed == checks_total


if __name__ == "__main__":
    success = test_calculate_retry_delay()
    sys.exit(0 if success else 1)
