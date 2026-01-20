
import pytest
import asyncio
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import BotSettings
from browser.instance import BrowserManager
from faucets.firefaucet import FireFaucetBot
from core.proxy_manager import ProxyManager

@pytest.mark.asyncio
async def test_firefaucet_login_logic():
    """
    Test the FireFaucet login logic with a visible browser.
    This requires actual credentials in .env.
    """
    settings = BotSettings()
    # Force visible for debugging if needed, or keep headless for CI
    # settings.headless = False 
    
    proxy_manager = ProxyManager(settings)
    browser_manager = BrowserManager(
        headless=settings.headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    await browser_manager.launch()
    
    try:
        page = await browser_manager.create_context(profile_id="test_profile")
        bot = FireFaucetBot(settings, page)
        
        print(f"Testing Login for {bot.faucet_name}...")
        success = await bot.login()
        
        if success:
            print("✅ Login Successful!")
        else:
            print("❌ Login Failed.")
            
        assert success == True
        
    finally:
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(test_firefaucet_login_logic())
