"""
Quick test script for individual faucet verification.
Run with visible browser to observe what's happening.
"""
import asyncio
import argparse
import logging
import json
import os
from core.config import BotSettings
from browser.instance import BrowserManager
from solvers.captcha import CaptchaSolver

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("FaucetTester")

# Faucet URLs for quick testing
FAUCET_URLS = {
    "firefaucet": "https://firefaucet.win",
    "fire_faucet": "https://firefaucet.win",
    "cointiply": "https://cointiply.com",
    "dutchy": "https://autofaucet.dutchycorp.space",
    "coinpayu": "https://coinpayu.com",
    "adbtc": "https://adbtc.top",
    "faucetcrypto": "https://faucetcrypto.com",
    "freebitcoin": "https://freebitco.in",
    "litepick": "https://litecoin.pickfaucet.io",
}


def load_faucet_config():
    """Load credentials from faucet_config.json."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "faucet_config.json"),
        os.path.join(os.path.dirname(__file__), "..", "..", "config", "faucet_config.json"),
    ]
    for config_path in candidates:
        config_path = os.path.abspath(config_path)
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def get_credentials(faucet_name: str, config: dict) -> dict:
    """Get credentials for a faucet from config."""
    accounts = config.get("accounts", {})
    
    # Normalize name (fire_faucet -> fire_faucet, firefaucet -> fire_faucet)
    name = faucet_name.lower().replace("firefaucet", "fire_faucet")
    
    if name in accounts:
        acc = accounts[name]
        return {
            "username": acc.get("username", ""),
            "password": acc.get("password", "")
        }
    return None


async def check_2captcha_balance(api_key: str) -> dict:
    """Check 2Captcha API balance and status."""
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://2captcha.com/res.php?key={api_key}&action=getbalance&json=1"
            async with session.get(url) as resp:
                data = await resp.json()
                if data.get("status") == 1:
                    return {"success": True, "balance": float(data["request"])}
                else:
                    return {"success": False, "error": data.get("request")}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def test_faucet(faucet_name: str, action: str = "check", headless: bool = False, use_proxy: bool = True):
    """
    Test a single faucet.
    
    Actions:
    - check: Just navigate and take screenshot
    - login: Attempt login flow
    - claim: Full claim attempt
    """
    settings = BotSettings()
    faucet_config = load_faucet_config()
    
    # Get URL
    base_url = FAUCET_URLS.get(faucet_name.lower())
    if not base_url:
        logger.error(f"Unknown faucet: {faucet_name}")
        logger.info(f"Available: {list(FAUCET_URLS.keys())}")
        return
    
    # Get credentials from faucet_config.json
    creds = get_credentials(faucet_name, faucet_config)
    if creds:
        logger.info(f"✅ Found credentials for {faucet_name}: {creds['username']}")
    else:
        logger.warning(f"⚠️ No credentials found for {faucet_name}")
    
    # Get 2Captcha key from config
    captcha_key = faucet_config.get("security", {}).get("captcha_solver", {}).get("api_key")
    if not captcha_key:
        captcha_key = settings.twocaptcha_api_key
    
    # Check 2Captcha first
    logger.info("Checking 2Captcha balance...")
    captcha_result = await check_2captcha_balance(captcha_key or "")
    if captcha_result["success"]:
        logger.info(f"✅ 2Captcha Balance: ${captcha_result['balance']:.2f}")
    else:
        logger.warning(f"⚠️ 2Captcha Check Failed: {captcha_result['error']}")
        logger.warning("CAPTCHA will need manual solving!")
    
    # Set cookie encryption key env var to avoid regenerating
    os.environ["CRYPTOBOT_COOKIE_KEY"] = "mRgSLNkLX4aQdi-shVgeEU1mosio2nD9ZGf2slK1To0="
    
    # Launch browser in VISIBLE mode
    logger.info(f"Launching browser for {faucet_name}...")
    
    # Try to get a residential proxy to bypass connection issues
    proxy_str = None
    if use_proxy:
        try:
            from core.proxy_manager import ProxyManager
            proxy_manager = ProxyManager(settings)
            if await proxy_manager.fetch_proxies(count=5):
                if proxy_manager.proxies:
                    proxy = proxy_manager.proxies[0]
                    proxy_str = proxy.to_string()
                    logger.info(f"🛡️ Using Residential Proxy: {proxy.ip}:{proxy.port}")
        except Exception as e:
            logger.warning(f"Failed to fetch proxies: {e}")

    browser_manager = BrowserManager(
        headless=headless,
        block_images=False,  # Show images for debugging
        block_media=True
    )
    
    try:
        await browser_manager.launch()
        context = await browser_manager.create_context(proxy=proxy_str, profile_name=f"test_{faucet_name}")
        page = await browser_manager.new_page(context)
        
        # Navigate and observe
        logger.info(f"Navigating to {base_url}...")
        
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
            logger.info(f"✅ Page loaded: {page.url}")
        except Exception as e:
            logger.error(f"❌ Navigation failed: {e}")
            
        # Take screenshot
        screenshot_path = f"c:/Users/azureuser/Repositories/cryptobot/{faucet_name}_test.png"
        await page.screenshot(path=screenshot_path)
        logger.info(f"📸 Screenshot saved: {screenshot_path}")
        
        # Check for Cloudflare
        content = await page.content()
        if "Just a moment" in content or "cf-turnstile" in content.lower():
            logger.warning("⚠️ Cloudflare challenge detected!")
            logger.info("Waiting 30s for Cloudflare to resolve...")
            await asyncio.sleep(30)
            
            content = await page.content()
            if "Just a moment" not in content:
                logger.info("✅ Cloudflare challenge passed!")
            else:
                logger.error("❌ Still stuck on Cloudflare")
        
        # Get page title and current URL
        title = await page.title()
        logger.info(f"Page Title: {title}")
        logger.info(f"Current URL: {page.url}")
        
        if action == "check":
            logger.info("Check complete. Browser will stay open for 30 seconds for inspection.")
            await asyncio.sleep(30)
            
        elif action == "login":
            logger.info("Attempting login flow...")
            
            if not creds:
                logger.error("❌ No credentials available for login test")
                await asyncio.sleep(10)
                return
            
            # Import the appropriate bot class
            from core.registry import get_faucet_class
            bot_class = get_faucet_class(faucet_name)
            
            if bot_class:
                bot = bot_class(settings, page)
                # Inject credentials from faucet_config.json
                bot.settings_account_override = creds
                
                # Try login
                success = await bot.login()
                if success:
                    logger.info("✅ LOGIN SUCCESSFUL!")
                    # Save cookies for future use
                    profile_name = f"{faucet_name}_{creds['username']}"
                    await browser_manager.save_cookies(context, profile_name)
                    logger.info(f"🍪 Cookies saved for {profile_name}")
                else:
                    logger.error("❌ Login failed - check selectors or credentials")
                    
                await asyncio.sleep(15)  # Let user see result
            else:
                logger.error(f"No bot class found for {faucet_name}")
                
        elif action == "claim":
            logger.info("Attempting full claim...")
            
            if not creds:
                logger.error("❌ No credentials available for claim test")
                await asyncio.sleep(10)
                return
            
            from core.registry import get_faucet_class
            bot_class = get_faucet_class(faucet_name)
            
            if bot_class:
                bot = bot_class(settings, page)
                bot.settings_account_override = creds
                
                # Login first
                if await bot.login():
                    logger.info("✅ Logged in, attempting claim...")
                    result = await bot.claim()
                    logger.info(f"Claim Result: {result}")
                    
                    # Record in analytics
                    from core.analytics import get_tracker
                    tracker = get_tracker()
                    tracker.record_claim(
                        faucet=faucet_name,
                        success=result.success,
                        amount=float(result.amount) if result.amount else 0,
                        currency="BTC"
                    )
                    logger.info("📊 Claim recorded in analytics")
                else:
                    logger.error("❌ Login failed, cannot claim")
                    
                await asyncio.sleep(15)
            else:
                logger.error(f"No bot class found for {faucet_name}")
                
    except Exception as e:
        logger.error(f"Test error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        logger.info("Closing browser...")
        await browser_manager.close()


async def main():
    parser = argparse.ArgumentParser(description="Test individual faucets")
    parser.add_argument("faucet", help="Faucet name to test")
    parser.add_argument(
        "--action", 
        choices=["check", "login", "claim"], 
        default="check",
        help="What to test"
    )
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--no-proxy", action="store_true", help="Disable proxy usage for this test")
    args = parser.parse_args()

    await test_faucet(args.faucet, args.action, args.headless, use_proxy=not args.no_proxy)


if __name__ == "__main__":
    asyncio.run(main())
