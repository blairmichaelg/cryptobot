import asyncio
import logging
from core.config import BotSettings
from core.proxy_manager import ProxyManager
from core.logging_setup import setup_logging

async def main():
    setup_logging("INFO")
    logger = logging.getLogger(__name__)
    
    print("\n" + "="*50)
    print(" 🕵️  2Captcha Proxy Setup Check")
    print("="*50 + "\n")
    
    settings = BotSettings()
    
    if not settings.twocaptcha_api_key:
        print("❌ No 2Captcha API Key found in env!")
        return

    print(f"🔑 API Key detected: {settings.twocaptcha_api_key[:5]}...*****")
    
    manager = ProxyManager(settings)
    print("🔄 Attempting to fetch proxies from 2Captcha API...")
    
    success = await manager.fetch_proxies()
    
    if success:
        print(f"\n✅ SUCCESS! Found {len(manager.proxies)} proxies.")
        for p in manager.proxies:
            print(f"   - {p.ip}:{p.port} ({p.username})")
        
        print("\n✨ You are ready to enable USE_2CAPTCHA_PROXIES=True in your .env")
    else:
        print("\n⚠️  Could not fetch proxies automatically.")
        print("Possible reasons:")
        print("1. You have not purchased Residential/Mobile proxies on 2captcha.com")
        print("2. The API endpoint relies on a specific subscription type.")
        print("3. Your IP is not whitelisted in the dashboard.")
        
        print("\n🛠️  Recommendation:")
        print("   - Visit https://2captcha.com/proxies")
        print("   - Ensure you have active proxies.")
        print("   - If you have them but this script fails, contact support or check API docs.")

if __name__ == "__main__":
    asyncio.run(main())
