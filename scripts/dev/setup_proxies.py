import asyncio
import logging
from core.config import BotSettings
from core.proxy_manager import ProxyManager
from core.logging_setup import setup_logging

async def main():
    setup_logging("INFO")
    logger = logging.getLogger(__name__)
    
    print("\n" + "="*50)
    print(" [~] 2Captcha Proxy Setup Check")
    print("="*50 + "\n")
    
    settings = BotSettings()
    
    if not settings.twocaptcha_api_key:
        print("❌ No 2Captcha API Key found in env!")
        return

    print(f"[KEY] API Key detected: {settings.twocaptcha_api_key[:5]}...*****")
    
    manager = ProxyManager(settings)
    print(f"[FILE] checking {settings.residential_proxies_file}...")
    
    # Force reload
    count = manager.load_proxies_from_file()
    
    if count > 0:
        print(f"\n[OK] SUCCESS! Loaded {count} proxies from file.")
        for p in manager.proxies:
            print(f"   - {p.to_string()}")
        
        print("\n[!] You are ready to enable USE_2CAPTCHA_PROXIES=True in your .env")
        
        # Test validation
        print("\n[?] Validating connectivity...")
        asyncio.create_task(manager.validate_all_proxies())
        # Just wait a bit for logs
        await asyncio.sleep(5)
        
    else:
        print("\n[WARN] No proxies found in proxies.txt")
        print(f"-> Please edit {settings.residential_proxies_file}")
        print("   Add your proxies in format: user:pass@ip:port")
        print("   Get them from: https://2captcha.com/proxies (Residential)")

if __name__ == "__main__":
    asyncio.run(main())
