#!/usr/bin/env python3
"""
Test all faucets with the button enabling fix.
Tests each faucet with proxy rotation to find working IPs.
"""
import asyncio
import os
import logging
import random
import string
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# List of all faucets to test
FAUCETS = [
    ("firefaucet", "FireFaucetBot"),
    ("faucetcrypto", "FaucetCryptoBot"),
    ("freebitcoin", "FreeBitcoinBot"),
    ("cointiply", "CointiplyBot"),
    ("tronpick", "TronPickBot"),
    ("dogepick", "DogePickBot"),
    ("litepick", "LitePickBot"),
]

async def test_faucet(faucet_module, faucet_class, max_proxy_attempts=3):
    """Test a single faucet with proxy rotation"""
    from browser.instance import BrowserManager
    from core.config import BotSettings
    import importlib
    
    load_dotenv()
    settings = BotSettings()
    
    # Import faucet class dynamically
    module = importlib.import_module(f"faucets.{faucet_module}")
    FaucetClass = getattr(module, faucet_class)
    
    faucet_name = faucet_class.replace("Bot", "")
    
    for proxy_attempt in range(max_proxy_attempts):
        browser = BrowserManager(headless=True)
        
        try:
            await browser.launch()
            
            # Get credentials
            creds = settings.get_account(faucet_module.replace("_", ""))
            if not creds:
                logger.warning(f"[{faucet_name}] No credentials found")
                return {"success": False, "error": "No credentials"}
            
            # Generate fresh proxy session
            session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            proxy_url = f"http://ub033d0d0583c05dd-zone-custom-session-{session_id}:ub033d0d0583c05dd@43.135.141.142:2334"
            
            logger.info(f"[{faucet_name}] Attempt {proxy_attempt + 1}/{max_proxy_attempts} with session {session_id}")
            
            # Create context with fresh proxy
            context = await browser.create_context(
                profile_name=creds["username"],
                proxy=proxy_url,
                allow_sticky_proxy=False
            )
            page = await context.new_page()
            
            # Initialize faucet bot
            faucet = FaucetClass(settings, page)
            
            # Quick proxy test - try to navigate
            try:
                await page.goto(faucet.base_url, timeout=15000)
                title = await page.title()
                
                if "proxy" in title.lower() or "forbidden" in title.lower():
                    logger.warning(f"[{faucet_name}] Proxy blocked on attempt {proxy_attempt + 1}")
                    await browser.close()
                    await asyncio.sleep(2)
                    continue
                    
            except Exception as nav_err:
                if "PROXY_FORBIDDEN" in str(nav_err) or "403" in str(nav_err):
                    logger.warning(f"[{faucet_name}] Proxy error on attempt {proxy_attempt + 1}")
                    await browser.close()
                    await asyncio.sleep(2)
                    continue
                else:
                    raise
            
            # Try claim
            logger.info(f"[{faucet_name}] Attempting claim...")
            result = await faucet.claim()
            
            logger.info(f"[{faucet_name}] Result: {result.success} - {result.status}")
            
            if result.success:
                logger.info(f"✅ [{faucet_name}] SUCCESS with session {session_id}")
                await browser.close()
                return {"success": True, "status": result.status, "proxy_session": session_id}
            else:
                logger.warning(f"[{faucet_name}] Claim failed: {result.status}")
                
        except Exception as e:
            logger.error(f"[{faucet_name}] Error on attempt {proxy_attempt + 1}: {e}")
            
        finally:
            try:
                await browser.close()
            except:
                pass
            
        await asyncio.sleep(2)
    
    # All proxy attempts failed
    logger.error(f"❌ [{faucet_name}] Failed after {max_proxy_attempts} proxy attempts")
    return {"success": False, "error": "All proxy attempts failed"}

async def main():
    """Test all faucets"""
    logger.info("🚀 Testing all faucets with button enabling fix...")
    logger.info(f"Testing {len(FAUCETS)} faucets with up to 3 proxy rotations each\n")
    
    results = {}
    
    for faucet_module, faucet_class in FAUCETS:
        faucet_name = faucet_class.replace("Bot", "")
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {faucet_name}")
        logger.info(f"{'='*60}")
        
        result = await test_faucet(faucet_module, faucet_class)
        results[faucet_name] = result
        
        logger.info(f"\n{faucet_name} result: {result}\n")
        
        # Brief pause between faucets
        await asyncio.sleep(3)
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("FINAL RESULTS")
    logger.info("="*60)
    
    successful = [name for name, res in results.items() if res.get("success")]
    failed = [name for name, res in results.items() if not res.get("success")]
    
    logger.info(f"\n✅ Successful: {len(successful)}/{len(FAUCETS)}")
    for name in successful:
        logger.info(f"   - {name}: {results[name].get('status')} (proxy: {results[name].get('proxy_session')})")
    
    if failed:
        logger.info(f"\n❌ Failed: {len(failed)}/{len(FAUCETS)}")
        for name in failed:
            logger.info(f"   - {name}: {results[name].get('error')}")
    
    logger.info(f"\nSuccess rate: {len(successful)/len(FAUCETS)*100:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())
