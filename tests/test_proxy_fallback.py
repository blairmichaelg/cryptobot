"""
Test script for dead proxy fallback logic.

This script validates that the proxy manager correctly:
1. Filters out dead proxies during assignment
2. Filters out proxies in cooldown
3. Provides proper fallback when all proxies are dead/cooldown
4. Logs warnings when no healthy proxies available
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.proxy_manager import ProxyManager, Proxy
from core.config import BotSettings, AccountProfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_dead_proxy_filtering():
    """Test that dead proxies are filtered during assignment."""
    logger.info("=" * 60)
    logger.info("TEST 1: Dead Proxy Filtering During Assignment")
    logger.info("=" * 60)
    
    # Create a minimal settings object
    settings = BotSettings()
    settings.use_2captcha_proxies = False  # Don't fetch from API
    settings.proxy_provider = "manual"
    
    # Create proxy manager
    pm = ProxyManager(settings)
    
    # Manually add some test proxies
    pm.all_proxies = [
        Proxy(ip="1.1.1.1", port=8888, username="user1", password="pass1"),
        Proxy(ip="2.2.2.2", port=8888, username="user2", password="pass2"),
        Proxy(ip="3.3.3.3", port=8888, username="user3", password="pass3"),
    ]
    pm.proxies = list(pm.all_proxies)
    
    # Mark first proxy as dead
    dead_key = pm._proxy_key(pm.proxies[0])
    pm.dead_proxies.append(dead_key)
    logger.info(f"Marked proxy as dead: {dead_key}")
    
    # Create test profiles
    profiles = [
        AccountProfile(username="test1", password="pass1", faucet="testfaucet"),
        AccountProfile(username="test2", password="pass2", faucet="testfaucet"),
    ]
    
    # Assign proxies
    pm.assign_proxies(profiles)
    
    # Verify dead proxy was not assigned
    assigned_keys = set()
    for profile in profiles:
        if profile.proxy:
            # Normalize proxy string to key format
            key = profile.proxy.split("://", 1)[1] if "://" in profile.proxy else profile.proxy
            assigned_keys.add(key)
    
    if dead_key in assigned_keys:
        logger.error("❌ FAILED: Dead proxy was assigned!")
        return False
    else:
        logger.info("✅ PASSED: Dead proxy was not assigned")
        return True


async def test_cooldown_proxy_filtering():
    """Test that proxies in cooldown are filtered during assignment."""
    logger.info("=" * 60)
    logger.info("TEST 2: Cooldown Proxy Filtering During Assignment")
    logger.info("=" * 60)
    
    settings = BotSettings()
    settings.use_2captcha_proxies = False
    settings.proxy_provider = "manual"
    
    pm = ProxyManager(settings)
    
    # Add test proxies
    pm.all_proxies = [
        Proxy(ip="1.1.1.1", port=8888, username="user1", password="pass1"),
        Proxy(ip="2.2.2.2", port=8888, username="user2", password="pass2"),
        Proxy(ip="3.3.3.3", port=8888, username="user3", password="pass3"),
    ]
    pm.proxies = list(pm.all_proxies)
    
    # Put first proxy in cooldown for 1 hour
    cooldown_key = pm._proxy_key(pm.proxies[0])
    pm.proxy_cooldowns[cooldown_key] = time.time() + 3600  # 1 hour from now
    logger.info(f"Put proxy in cooldown: {cooldown_key}")
    
    # Create test profiles
    profiles = [
        AccountProfile(username="test1", password="pass1", faucet="testfaucet"),
        AccountProfile(username="test2", password="pass2", faucet="testfaucet"),
    ]
    
    # Assign proxies
    pm.assign_proxies(profiles)
    
    # Verify cooldown proxy was not assigned
    assigned_keys = set()
    for profile in profiles:
        if profile.proxy:
            key = profile.proxy.split("://", 1)[1] if "://" in profile.proxy else profile.proxy
            assigned_keys.add(key)
    
    if cooldown_key in assigned_keys:
        logger.error("❌ FAILED: Cooldown proxy was assigned!")
        return False
    else:
        logger.info("✅ PASSED: Cooldown proxy was not assigned")
        return True


async def test_all_proxies_dead_fallback():
    """Test behavior when all proxies are dead."""
    logger.info("=" * 60)
    logger.info("TEST 3: All Proxies Dead Fallback")
    logger.info("=" * 60)
    
    settings = BotSettings()
    settings.use_2captcha_proxies = False
    settings.proxy_provider = "manual"
    
    pm = ProxyManager(settings)
    
    # Add test proxies
    pm.all_proxies = [
        Proxy(ip="1.1.1.1", port=8888, username="user1", password="pass1"),
        Proxy(ip="2.2.2.2", port=8888, username="user2", password="pass2"),
    ]
    pm.proxies = list(pm.all_proxies)
    
    # Mark ALL proxies as dead
    for proxy in pm.proxies:
        key = pm._proxy_key(proxy)
        pm.dead_proxies.append(key)
        logger.info(f"Marked proxy as dead: {key}")
    
    # Create test profile
    profiles = [
        AccountProfile(username="test1", password="pass1", faucet="testfaucet"),
    ]
    
    # Try to assign proxies - should fail gracefully
    pm.assign_proxies(profiles)
    
    # Verify no proxy was assigned
    if profiles[0].proxy is None:
        logger.info("✅ PASSED: No proxy assigned when all are dead")
        return True
    else:
        logger.error(f"❌ FAILED: Dead proxy assigned: {profiles[0].proxy}")
        return False


async def test_rotate_with_dead_proxy():
    """Test proxy rotation when current proxy is dead."""
    logger.info("=" * 60)
    logger.info("TEST 4: Rotate Away From Dead Proxy")
    logger.info("=" * 60)
    
    settings = BotSettings()
    settings.use_2captcha_proxies = False
    settings.proxy_provider = "manual"
    
    pm = ProxyManager(settings)
    
    # Add test proxies
    pm.all_proxies = [
        Proxy(ip="1.1.1.1", port=8888, username="user1", password="pass1"),
        Proxy(ip="2.2.2.2", port=8888, username="user2", password="pass2"),
        Proxy(ip="3.3.3.3", port=8888, username="user3", password="pass3"),
    ]
    pm.proxies = list(pm.all_proxies)
    
    # Create test profile with assigned proxy
    profile = AccountProfile(username="test1", password="pass1", faucet="testfaucet")
    profile.proxy = pm.proxies[0].to_string()
    original_proxy = profile.proxy
    logger.info(f"Profile initially assigned to: {original_proxy}")
    
    # Mark current proxy as dead
    dead_key = pm._proxy_key(pm.proxies[0])
    pm.dead_proxies.append(dead_key)
    logger.info(f"Marked current proxy as dead: {dead_key}")
    
    # Rotate proxy
    new_proxy = pm.rotate_proxy(profile)
    
    # Verify we got a different, healthy proxy
    if new_proxy and new_proxy != original_proxy:
        new_key = new_proxy.split("://", 1)[1] if "://" in new_proxy else new_proxy
        if new_key not in pm.dead_proxies:
            logger.info(f"✅ PASSED: Rotated to healthy proxy: {new_proxy}")
            return True
        else:
            logger.error(f"❌ FAILED: Rotated to another dead proxy: {new_proxy}")
            return False
    else:
        logger.error(f"❌ FAILED: Rotation failed or returned same proxy")
        return False


async def test_stats_dead_flag():
    """Test that get_proxy_stats correctly reports is_dead status."""
    logger.info("=" * 60)
    logger.info("TEST 5: Proxy Stats Dead Flag")
    logger.info("=" * 60)
    
    settings = BotSettings()
    settings.use_2captcha_proxies = False
    settings.proxy_provider = "manual"
    
    pm = ProxyManager(settings)
    
    # Add test proxies
    test_proxy = Proxy(ip="1.1.1.1", port=8888, username="user1", password="pass1")
    pm.all_proxies = [test_proxy]
    pm.proxies = list(pm.all_proxies)
    
    # Check stats for alive proxy
    stats = pm.get_proxy_stats(test_proxy)
    if stats["is_dead"]:
        logger.error("❌ FAILED: Alive proxy reported as dead")
        return False
    logger.info("✅ Alive proxy correctly reported as alive")
    
    # Mark proxy as dead
    dead_key = pm._proxy_key(test_proxy)
    pm.dead_proxies.append(dead_key)
    
    # Check stats again
    stats = pm.get_proxy_stats(test_proxy)
    if not stats["is_dead"]:
        logger.error("❌ FAILED: Dead proxy reported as alive")
        return False
    
    logger.info("✅ PASSED: Dead proxy correctly reported in stats")
    return True


async def main():
    """Run all tests."""
    logger.info("Starting proxy fallback logic tests...")
    logger.info("")
    
    results = []
    
    # Run all tests
    results.append(await test_dead_proxy_filtering())
    logger.info("")
    
    results.append(await test_cooldown_proxy_filtering())
    logger.info("")
    
    results.append(await test_all_proxies_dead_fallback())
    logger.info("")
    
    results.append(await test_rotate_with_dead_proxy())
    logger.info("")
    
    results.append(await test_stats_dead_flag())
    logger.info("")
    
    # Summary
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    passed = sum(results)
    total = len(results)
    logger.info(f"Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("✅ ALL TESTS PASSED")
        return 0
    else:
        logger.error(f"❌ {total - passed} TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
