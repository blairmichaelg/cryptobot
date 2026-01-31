"""
Test script for HumanProfile integration with FaucetBot.
Validates that profiles are loaded and persisted correctly.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock
from playwright.async_api import Page
from faucets.base import FaucetBot
from core.config import BotSettings
from browser.stealth_hub import HumanProfile

async def test_profile_loading():
    """Test that FaucetBot loads and persists human profiles."""
    print("Testing HumanProfile integration with FaucetBot...")
    print("=" * 70)
    
    # Create mock settings and page
    settings = Mock(spec=BotSettings)
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key"
    settings.capsolver_api_key = None
    settings.captcha_daily_budget = 1.0
    settings.captcha_fallback_provider = None
    settings.captcha_fallback_api_key = None
    settings.get_account = Mock(return_value={'username': 'test_user@example.com', 'password': 'test123'})
    
    page = Mock(spec=Page)
    
    # Create bot instance
    bot = FaucetBot(settings, page)
    bot.faucet_name = "TestFaucet"
    
    print(f"\n1. Initial state - Profile: {bot.human_profile}")
    assert bot.human_profile is None, "Profile should be None initially"
    
    # Load profile
    print("\n2. Loading profile for 'test_user@example.com'...")
    profile = bot.load_human_profile('test_user@example.com')
    print(f"   Assigned profile: {profile}")
    assert profile in HumanProfile.ALL_PROFILES, f"Invalid profile: {profile}"
    assert bot.human_profile == profile, "Bot should store the profile"
    
    # Verify persistence
    fingerprint_file = Path(__file__).parent / "config" / "profile_fingerprints.json"
    if fingerprint_file.exists():
        with open(fingerprint_file, 'r') as f:
            fingerprints = json.load(f)
        
        print(f"\n3. Checking persistence in {fingerprint_file}...")
        assert 'test_user@example.com' in fingerprints, "Profile should be saved"
        assert fingerprints['test_user@example.com']['human_profile'] == profile, "Saved profile should match"
        print(f"   ✓ Profile persisted: {fingerprints['test_user@example.com']['human_profile']}")
    
    # Load again - should get same profile
    bot2 = FaucetBot(settings, page)
    bot2.faucet_name = "TestFaucet"
    profile2 = bot2.load_human_profile('test_user@example.com')
    
    print("\n4. Reloading profile for same user...")
    print(f"   First load:  {profile}")
    print(f"   Second load: {profile2}")
    assert profile == profile2, "Profile should be consistent across loads"
    print("   ✓ Profile consistency verified")
    
    # Test different user gets different profile (probabilistically)
    print("\n5. Testing different user...")
    bot3 = FaucetBot(settings, page)
    bot3.faucet_name = "TestFaucet"
    profile3 = bot3.load_human_profile('different_user@example.com')
    print(f"   User 1 profile: {profile}")
    print(f"   User 2 profile: {profile3}")
    # Note: might be same due to random chance, but should be independent
    
    # Test timing methods use profile
    print(f"\n6. Testing timing methods with profile '{profile}'...")
    
    # Get some sample timings
    delays = []
    for _ in range(5):
        delay = HumanProfile.get_action_delay(profile, "click")
        delays.append(delay)
    
    print(f"   Click delays: {[f'{d:.2f}s' for d in delays]}")
    print(f"   Avg: {sum(delays)/len(delays):.2f}s")
    
    thinking = HumanProfile.get_thinking_pause(profile)
    print(f"   Thinking pause: {thinking:.2f}s")
    
    should_idle, idle_duration = HumanProfile.should_idle(profile)
    if should_idle:
        print(f"   Idle detected: {idle_duration:.2f}s")
    else:
        print("   No idle (normal behavior)")
    
    print("\n" + "=" * 70)
    print("✓ All integration tests passed!")

if __name__ == "__main__":
    asyncio.run(test_profile_loading())
