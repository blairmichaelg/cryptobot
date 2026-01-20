import asyncio
import logging
from core.proxy_manager import ProxyManager
from core.config import BotSettings

async def main():
    logging.basicConfig(level=logging.INFO)
    settings = BotSettings()
    pm = ProxyManager(settings)
    
    print("--- Fetching Proxies from 2Captcha ---")
    # This will use the whitelist API by default in our current implementation
    success = await pm.fetch_proxies(count=5)
    
    if success:
        print(f"Successfully fetched {len(pm.proxies)} proxies.")
        for p in pm.proxies:
            print(f"Proxy: {p.ip}:{p.port}")
        
        print("\n--- Validating Proxies ---")
        valid_count = await pm.validate_all_proxies()
        print(f"Valid proxies: {valid_count}")
    else:
        print("Failed to fetch proxies. Check whitelisting or API key.")

if __name__ == "__main__":
    asyncio.run(main())
