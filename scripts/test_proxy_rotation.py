import asyncio
import aiohttp
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestRotation")

# Base credentials from observation
BASE_USER = "ub033d0d0583c05dd-zone-custom"
PASS = "ub033d0d0583c05dd"
HOST = "170.106.118.114"
PORT = 2334

async def check_ip(proxy_url, name):
    try:
        async with aiohttp.ClientSession() as session:
            start = time.time()
            async with session.get("https://httpbin.org/ip", proxy=proxy_url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ip = data.get('origin')
                    logger.info(f"[{name}] Success! External IP: {ip}")
                    return ip
                else:
                    logger.error(f"[{name}] Status {resp.status}")
    except Exception as e:
        logger.error(f"[{name}] Failed: {e}")
    return None

async def main():
    # 1. Base
    base_url = f"http://{BASE_USER}:{PASS}@{HOST}:{PORT}"
    ip1 = await check_ip(base_url, "Base")
    
    # 2. Session 1
    # Guessing format: user-session-ID
    user_sess1 = f"{BASE_USER}-session-test1"
    url_sess1 = f"http://{user_sess1}:{PASS}@{HOST}:{PORT}"
    ip2 = await check_ip(url_sess1, "Session 1")
    
    # 3. Session 2
    user_sess2 = f"{BASE_USER}-session-test2"
    url_sess2 = f"http://{user_sess2}:{PASS}@{HOST}:{PORT}"
    ip3 = await check_ip(url_sess2, "Session 2")
    
    if ip1 and ip2 and ip1 != ip2:
        logger.info("✅ Rotation successful! IPs are different.")
    elif ip1 and ip2:
        logger.warning("⚠️ Rotation failed. IPs are same.")
    
if __name__ == "__main__":
    asyncio.run(main())
