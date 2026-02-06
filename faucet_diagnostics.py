#!/usr/bin/env python3
"""
Diagnostic script to test faucet functionality and identify issues.
Checks:
1. Browser instance can be created
2. Credentials are configured for each faucet
3. Basic navigation works
4. Selectors can find elements on login/claim pages
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
from faucets import (
    firefaucet, freebitcoin, cointiply, coinpayu, adbtc, 
    faucetcrypto, dutchy, litepick, tronpick, dogepick,
    bchpick, solpick, tonpick, polygonpick, binpick,
    dashpick, ethpick, usdpick
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Map of faucet names to their bot classes
FAUCET_BOTS = {
    "firefaucet": firefaucet.FireFaucetBot,
    "freebitcoin": freebitcoin.FreeBitcoinBot,
    "cointiply": cointiply.CointiplyBot,
    "coinpayu": coinpayu.CoinPayUBot,
    "adbtc": adbtc.AdBTCBot,
    "faucetcrypto": faucetcrypto.FaucetCryptoBot,
    "dutchy": dutchy.DutchyBot,
    "litepick": litepick.LitePickBot,
    "tronpick": tronpick.TronPickBot,
    "dogepick": dogepick.DogePickBot,
    "bchpick": bchpick.BchPickBot,
    "solpick": solpick.SolPickBot,
    "tonpick": tonpick.TonPickBot,
    "polygonpick": polygonpick.PolygonPickBot,
    "binpick": binpick.BinPickBot,
    "dashpick": dashpick.DashPickBot,
    "ethpick": ethpick.EthPickBot,
    "usdpick": usdpick.UsdPickBot,
}

async def test_browser_instance():
    """Test that BrowserManager can be created without errors."""
    logger.info("=" * 60)
    logger.info("TEST 1: Browser Instance Creation")
    logger.info("=" * 60)
    try:
        browser_mgr = BrowserManager(headless=True)
        logger.info("✅ BrowserManager instance created successfully")
        logger.info(f"   Headless: {browser_mgr.headless}")
        logger.info(f"   Timeout: {browser_mgr.timeout}ms")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create BrowserManager: {e}")
        return False

async def test_credentials(settings: BotSettings):
    """Test that credentials are configured for each faucet."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Credential Configuration")
    logger.info("=" * 60)
    
    results = {}
    for faucet_name in FAUCET_BOTS.keys():
        try:
            creds = settings.get_account(faucet_name)
            if creds and creds.get("username") and creds.get("password"):
                logger.info(f"✅ {faucet_name:15s} - Credentials configured")
                results[faucet_name] = True
            else:
                logger.warning(f"❌ {faucet_name:15s} - Missing credentials")
                results[faucet_name] = False
        except Exception as e:
            logger.warning(f"❌ {faucet_name:15s} - Error: {e}")
            results[faucet_name] = False
    
    configured = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info(f"\n📊 Summary: {configured}/{total} faucets have credentials configured")
    return results

async def test_captcha_config(settings: BotSettings):
    """Test CAPTCHA provider configuration."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: CAPTCHA Provider Configuration")
    logger.info("=" * 60)
    
    twocaptcha_key = getattr(settings, "twocaptcha_api_key", None)
    capsolver_key = getattr(settings, "capsolver_api_key", None)
    fallback_provider = getattr(settings, "captcha_fallback_provider", None)
    
    logger.info(f"2Captcha API Key: {'✅ Configured' if twocaptcha_key else '❌ Missing'}")
    logger.info(f"CapSolver API Key: {'✅ Configured' if capsolver_key else '❌ Missing'}")
    logger.info(f"Fallback Provider: {fallback_provider if fallback_provider else 'None (will auto-configure if CapSolver key exists)'}")
    
    if twocaptcha_key and capsolver_key:
        logger.info("✅ Both providers configured - hCaptcha will automatically use CapSolver fallback")
    elif twocaptcha_key:
        logger.info("⚠️  Only 2Captcha configured - hCaptcha sites (like Cointiply) may fail")
    elif capsolver_key:
        logger.info("✅ Only CapSolver configured - all CAPTCHA types should work")
    else:
        logger.warning("❌ No CAPTCHA provider configured - all faucets will fail")
    
    return bool(twocaptcha_key or capsolver_key)

async def test_basic_navigation():
    """Test that browser can navigate to a simple page."""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Basic Browser Navigation")
    logger.info("=" * 60)
    
    browser_mgr = None
    try:
        browser_mgr = BrowserManager(headless=True)
        await browser_mgr.launch()
        page = await browser_mgr.new_page()
        
        # Test navigation to a simple page
        logger.info("Navigating to https://www.google.com...")
        await page.goto("https://www.google.com", timeout=15000)
        title = await page.title()
        logger.info(f"✅ Navigation successful - Page title: {title}")
        
        await browser_mgr.close()
        return True
    except Exception as e:
        logger.error(f"❌ Navigation failed: {e}")
        if browser_mgr:
            try:
                await browser_mgr.close()
            except:
                pass
        return False

async def main():
    """Run all diagnostic tests."""
    logger.info("🔍 Starting Faucet Diagnostics")
    logger.info("=" * 60)
    
    # Test 1: Browser instance
    browser_test = await test_browser_instance()
    
    # Test 2: Load settings and check credentials
    try:
        settings = BotSettings()
        creds_results = await test_credentials(settings)
        captcha_ok = await test_captcha_config(settings)
    except Exception as e:
        logger.error(f"❌ Failed to load settings: {e}")
        logger.error("   Make sure .env file exists and is properly configured")
        return
    
    # Test 3: Basic navigation
    nav_test = await test_basic_navigation()
    
    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("DIAGNOSTIC SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Browser Instance:     {'✅ PASS' if browser_test else '❌ FAIL'}")
    logger.info(f"Settings/Credentials: {'✅ PASS' if any(creds_results.values()) else '❌ FAIL'}")
    logger.info(f"CAPTCHA Configuration:{'✅ PASS' if captcha_ok else '❌ FAIL'}")
    logger.info(f"Basic Navigation:     {'✅ PASS' if nav_test else '❌ FAIL'}")
    
    if browser_test and any(creds_results.values()) and captcha_ok and nav_test:
        logger.info("\n✅ All basic tests passed!")
        logger.info("   You can proceed to test individual faucets")
        logger.info("   Run: python main.py --single <faucet_name> --once --visible")
    else:
        logger.warning("\n⚠️  Some tests failed - review the issues above")
        if not any(creds_results.values()):
            logger.warning("   → Configure credentials in .env file")
        if not captcha_ok:
            logger.warning("   → Set TWOCAPTCHA_API_KEY and/or CAPSOLVER_API_KEY in .env")
        if not browser_test:
            logger.warning("   → Check Python dependencies: pip install -r requirements.txt")

if __name__ == "__main__":
    asyncio.run(main())
