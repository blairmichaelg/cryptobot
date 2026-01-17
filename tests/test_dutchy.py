import pytest
import asyncio
from unittest.mock import MagicMock
from faucets.dutchy import DutchyBot
from core.config import BotSettings

@pytest.mark.asyncio
async def test_dutchy_structure():
    print("--- Testing DutchyBot Structure ---")
    
    # 1. Setup Mocks
    mock_page = MagicMock()
    mock_settings = MagicMock(spec=BotSettings)
    mock_settings.twocaptcha_api_key = "TEST_KEY"
    mock_settings.captcha_provider = "2captcha"
    
    # 2. Instantiate
    try:
        bot = DutchyBot(mock_settings, mock_page)
        print("✅ Instantiation successful")
    except Exception as e:
        pytest.fail(f"❌ Instantiation failed: {e}")

    # 3. Check Methods
    assert hasattr(bot, 'login'), "❌ Missing required method: login"
    assert hasattr(bot, 'claim'), "❌ Missing required method: claim"
    print("✅ Methods 'login' and 'claim' exist")

    # 4. Check Config
    assert bot.faucet_name == "DutchyCorp", f"❌ Config mismatch: {bot.faucet_name}"
    assert "dutchycorp.space" in bot.base_url, f"❌ Config mismatch: {bot.base_url}"
    print(f"✅ Config looks correct: {bot.base_url}")
