import asyncio
import aiohttp
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import BotSettings

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("DebugWhitelistAPI")

async def get_current_ip():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api64.ipify.org?format=json") as resp:
            data = await resp.json()
            return data["ip"]

async def test_endpoint(session, url, params=None):
    logger.info(f"Testing URL: {url}")
    try:
        async with session.get(url, params=params) as resp:
            text = await resp.text()
            logger.info(f"Status: {resp.status}")
            logger.info(f"Response: {text[:500]}")
            return text
    except Exception as e:
        logger.error(f"Error: {e}")
        return None

async def test_whitelist(session, key, ip):
    url = "https://api.2captcha.com/proxy/generate_white_list_connections"
    params = {
        "key": key,
        "country": "all",
        "protocol": "http",
        "connection_count": 10,
        "ip": ip
    }
    logger.info(f"Testing Whitelist URL: {url} with IP: {ip}")
    try:
        async with session.get(url, params=params) as resp:
            text = await resp.text()
            logger.info(f"Status: {resp.status}")
            logger.info(f"Response: {text}")
            return text
    except Exception as e:
        logger.error(f"Error: {e}")
        return None

async def main():
    settings = BotSettings()
    key = settings.twocaptcha_api_key
    if not key:
        logger.error("No 2Captcha API key found!")
        return

    current_ip = await get_current_ip()
    logger.info(f"Current IP: {current_ip}")

    async with aiohttp.ClientSession() as session:
        logger.info("Testing Account Info / Proxy List...")
        await test_endpoint(session, "https://api.2captcha.com/proxy", {"key": key})
        
        logger.info("Testing Guessed Whitelist Registration Endpoint...")
        await test_endpoint(session, "https://api.2captcha.com/proxy/create_white_list_ip", {"key": key, "ip": current_ip})

        await test_whitelist(session, key, current_ip)

if __name__ == "__main__":
    asyncio.run(main())
