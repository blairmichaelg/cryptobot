import asyncio
import aiohttp
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import BotSettings

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("DebugWhitelistParams")

async def get_current_ip():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api64.ipify.org?format=json") as resp:
            data = await resp.json()
            return data["ip"]

async def test_params(session, key, ip):
    url = "https://api.2captcha.com/proxy/generate_white_list_connections"
    param_names = ["ip", "ip_address", "ips", "whitelist_ip", "ip_white"]
    
    for name in param_names:
        params = {
            "key": key,
            "country": "all",
            "protocol": "http",
            "connection_count": 5,
            name: ip
        }
        logger.info(f"Testing paramagnetic: {name}={ip}")
        try:
            async with session.get(url, params=params) as resp:
                text = await resp.text()
                logger.info(f"Status: {resp.status} | Response: {text}")
        except Exception as e:
            logger.error(f"Error with {name}: {e}")

async def main():
    settings = BotSettings()
    key = settings.twocaptcha_api_key
    if not key: return
    current_ip = await get_current_ip()
    async with aiohttp.ClientSession() as session:
        await test_params(session, key, current_ip)

if __name__ == "__main__":
    asyncio.run(main())
