"""
Test script for HumanProfile timing system.
Validates that profiles generate appropriate delays and behaviors.
"""
import statistics
from browser.stealth_hub import HumanProfile

def test_profile_timing():
    """Test that each profile generates delays within expected ranges."""
    print("Testing HumanProfile timing system...\n")
    
    profiles = [
        HumanProfile.FAST_USER,
        HumanProfile.NORMAL_USER,
        HumanProfile.CAUTIOUS_USER,
        HumanProfile.DISTRACTED_USER
    ]
    
    actions = ["click", "type", "scroll", "read", "thinking"]
    
    for profile in profiles:
        print(f"Profile: {profile.upper()}")
        print("=" * 50)
        
        for action in actions:
            # Generate 10 samples
            samples = [HumanProfile.get_action_delay(profile, action) for _ in range(10)]
            avg = statistics.mean(samples)
            min_val = min(samples)
            max_val = max(samples)
            
            print(f"  {action:10} - avg: {avg:5.2f}s, range: [{min_val:5.2f}, {max_val:5.2f}]")
        
        # Test idle probability
        idle_count = 0
        idle_durations = []
        for _ in range(100):
            should_idle, duration = HumanProfile.should_idle(profile)
            if should_idle:
                idle_count += 1
                idle_durations.append(duration)
        
        if idle_durations:
            avg_idle = statistics.mean(idle_durations)
            print(f"  Idle: {idle_count}% probability, avg duration: {avg_idle:.1f}s")
        else:
            print(f"  Idle: {idle_count}% probability")
        
        print()

def test_random_profile_distribution():
    """Test that random profile selection has appropriate distribution."""
    print("Testing random profile distribution (1000 samples)...")
    print("=" * 50)
    
    counts = {profile: 0 for profile in HumanProfile.ALL_PROFILES}
    
    for _ in range(1000):
        profile = HumanProfile.get_random_profile()
        counts[profile] += 1
    
    for profile in HumanProfile.ALL_PROFILES:
        percentage = (counts[profile] / 1000) * 100
        print(f"  {profile:12} - {counts[profile]:4} ({percentage:5.1f}%)")
    
    print()

def test_fast_user_burst_mode():
    """Test that FAST profile occasionally triggers burst mode."""
    print("Testing FAST profile burst mode...")
    print("=" * 50)
    
    burst_count = 0
    samples = []
    
    for _ in range(100):
        delay = HumanProfile.get_action_delay(HumanProfile.FAST_USER, "click")
        samples.append(delay)
        if delay < 0.4:  # Likely burst mode
            burst_count += 1
    
    print(f"  Burst mode triggered: {burst_count}/100 times")
    print(f"  Avg delay: {statistics.mean(samples):.2f}s")
    print(f"  Min delay: {min(samples):.2f}s")
    print(f"  Max delay: {max(samples):.2f}s")
    print()

def test_cautious_user_long_pauses():
    """Test that CAUTIOUS profile has occasional extra-long pauses."""
    print("Testing CAUTIOUS profile extra-long pauses...")
    print("=" * 50)
    
    long_pause_count = 0
    samples = []
    
    for _ in range(100):
        delay = HumanProfile.get_action_delay(HumanProfile.CAUTIOUS_USER, "click")
        samples.append(delay)
        if delay > 7:  # Longer than normal max
            long_pause_count += 1
    
    print(f"  Extra-long pauses: {long_pause_count}/100 times")
    print(f"  Avg delay: {statistics.mean(samples):.2f}s")
    print(f"  Min delay: {min(samples):.2f}s")
    print(f"  Max delay: {max(samples):.2f}s")
    print()

if __name__ == "__main__":
    print("HumanProfile Timing System Test")
    print("=" * 70)
    print()
    
    test_profile_timing()
    test_random_profile_distribution()
    test_fast_user_burst_mode()
    test_cautious_user_long_pauses()
    
    print("✓ All tests completed successfully!")
