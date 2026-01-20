import asyncio
import os
import sys
import logging

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import BotSettings
from core.proxy_manager import ProxyManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestProxyFetch")

async def main():
    logger.info("Initializing BotSettings...")
    settings = BotSettings()
    
    if not settings.twocaptcha_api_key:
        logger.error("❌ No 2Captcha API key found in settings/env.")
        return

    logger.info(f"API Key present: {settings.twocaptcha_api_key[:5]}...")
    
    logger.info("Initializing ProxyManager...")
    manager = ProxyManager(settings)
    
    logger.info("Attempting to fetch proxies from 2Captcha API...")
    count = await manager.fetch_proxies_from_api(quantity=10)
    
    if count > 0:
        logger.info(f"✅ Successfully fetched {count} proxies!")
        # Print first few
        for i, p in enumerate(manager.proxies[:3]):
            logger.info(f"  Proxy {i+1}: {p.to_string()}")
    else:
        logger.error("❌ Failed to fetch proxies. Check logs for details.")

if __name__ == "__main__":
    asyncio.run(main())
