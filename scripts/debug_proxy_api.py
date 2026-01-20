import asyncio
import aiohttp
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import BotSettings

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("DebugProxyAPI")

async def test_endpoint(session, url, params=None):
    logger.info(f"Testing URL: {url} with params keys: {list(params.keys()) if params else 'None'}")
    try:
        async with session.get(url, params=params) as resp:
            text = await resp.text()
            logger.info(f"Status: {resp.status}")
            logger.info(f"Response: {text[:200]}...")
            return text
    except Exception as e:
        logger.error(f"Error: {e}")
        return None

async def main():
    settings = BotSettings()
    key = settings.twocaptcha_api_key
    if not key:
        return

    async with aiohttp.ClientSession() as session:
        # Tries based on research
        await test_endpoint(session, "https://2captcha.com/res.php", {"key": key, "action": "getproxies", "json": 1})
        await test_endpoint(session, f"https://api.2captcha.com/proxy", {"key": key})
        # Try fetching actual list - common patterns
        await test_endpoint(session, f"https://api.2captcha.com/proxy/list", {"key": key})
        # Try traffic purchase endpoint usually needed to generate
        # Not going to buy traffic, just listing.

if __name__ == "__main__":
    asyncio.run(main())
