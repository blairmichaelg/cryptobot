import asyncio
import os
import sys
import logging
import json
import aiohttp
from typing import List

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Diagnostics")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from core.config import CONFIG_DIR, BotSettings
from browser.instance import create_stealth_browser

PROXIES_FILE = os.path.join(CONFIG_DIR, "proxies.txt")
ANALYTICS_FILE = os.path.join(BASE_DIR, "earnings_analytics.json")

def check_proxies():
    logger.info("--- Checking Proxies ---")
    if not os.path.exists(PROXIES_FILE):
        logger.error(f"❌ Proxies file not found: {PROXIES_FILE}")
        return False
    
    with open(PROXIES_FILE, "r") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    
    count = len(lines)
    logger.info(f"Found {count} proxies in proxies.txt")
    
    if count == 0:
        logger.error("❌ No proxies found! Please add residential proxies.")
        return False
    elif count < 3:
        logger.warning(f"⚠️ Only {count} proxies found. Recommended: 3+ for better rotation and stealth.")
    else:
        logger.info("✅ Proxy count sufficient.")

    return True

async def test_proxy_connection():
    logger.info("--- Testing Proxy Connection (Sample) ---")
    if not os.path.exists(PROXIES_FILE):
        return

    with open(PROXIES_FILE, "r") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    
    if not lines:
        return

    # Test first proxy
    proxy_str = lines[0]
    logger.info(f"Testing first proxy: {proxy_str}")
    
    try:
        if "://" not in proxy_str:
            proxy_url = f"http://{proxy_str}"
        else:
            proxy_url = proxy_str

        async with aiohttp.ClientSession() as session:
            start = asyncio.get_event_loop().time()
            async with session.get("https://httpbin.org/ip", proxy=proxy_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    latency = (asyncio.get_event_loop().time() - start) * 1000
                    logger.info(f"✅ Proxy connection successful! IP: {data.get('origin')} (Latency: {latency:.0f}ms)")
                else:
                    logger.error(f"❌ Proxy returned status: {resp.status}")
    except Exception as e:
        logger.error(f"❌ Proxy connection failed: {e}")

async def check_browser():
    logger.info("--- Checking Browser Stealth ---")
    try:
        async with await create_stealth_browser(headless=True) as browser:
            page = await browser.new_page()
            await page.goto("https://bot.sannysoft.com/") # Lightweight fingerprint test
            
            # Simple check
            webdriver = await page.evaluate("navigator.webdriver")
            logger.info(f"Navigator.webdriver detected: {webdriver}")
            
            if webdriver:
                logger.warning("⚠️ Stealth check failed: navigator.webdriver is true")
            else:
                logger.info("✅ Basic stealth check passed (webdriver false)")
                
    except Exception as e:
        logger.error(f"❌ Browser launch failed: {e}")

def check_permissions():
    logger.info("--- Checking Permissions ---")
    try:
        # Try to append to analytics file
        with open(ANALYTICS_FILE, "a") as f:
            pass
        logger.info(f"✅ Write permission confirmed for {ANALYTICS_FILE}")
    except Exception as e:
        logger.error(f"❌ Write permission failed: {e}")

async def main():
    logger.info("Starting Environment Check...")
    
    proxies_ok = check_proxies()
    check_permissions()
    
    if proxies_ok:
        await test_proxy_connection()
    
    await check_browser()
    
    logger.info("Diagnostics complete.")

if __name__ == "__main__":
    asyncio.run(main())
