import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from faucets.litepick import LitePickBot
from faucets.tronpick import TronPickBot
from faucets.dogepick import DogePickBot
from core.config import BotSettings


class TestPickFaucetRegistration(unittest.IsolatedAsyncioTestCase):
    """Test registration functionality for Pick.io faucet family."""
    
    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.settings = MagicMock(spec=BotSettings)
        self.settings.captcha_provider = "capsolver"
        self.settings.capsolver_api_key = "test_key"
        self.settings.wallet_addresses = {
            "LTC": {"address": "LTC_TEST_ADDRESS", "min_withdraw": 0.005},
            "TRX": {"address": "TRX_TEST_ADDRESS", "min_withdraw": 10},
            "DOGE": {"address": "DOGE_TEST_ADDRESS", "min_withdraw": 5}
        }
        
        self.page = AsyncMock()
        self.page.title.return_value = "Pick Faucet"
        self.page.goto = AsyncMock()
        self.page.wait_for_load_state = AsyncMock()
        self.page.content = AsyncMock(return_value="<html><body>Registration successful</body></html>")
        
    async def test_registration_method_exists(self):
        """Test that registration method exists on PickFaucetBase."""
        bot = LitePickBot(self.settings, self.page)
        self.assertTrue(hasattr(bot, 'register'))
        self.assertTrue(callable(bot.register))
        
    async def test_registration_without_base_url_fails(self):
        """Test that registration fails without base_url."""
        bot = LitePickBot(self.settings, self.page)
        bot.base_url = ""  # Clear base URL
        result = await bot.register("test@example.com", "password123")
        self.assertFalse(result)
        
    async def test_all_pick_faucets_have_correct_base_urls(self):
        """Test that all Pick faucet bots have the correct base URLs."""
        from faucets.solpick import SolPickBot
        from faucets.binpick import BinPickBot
        from faucets.bchpick import BchPickBot
        from faucets.tonpick import TonPickBot
        from faucets.polygonpick import PolygonPickBot
        from faucets.dashpick import DashPickBot
        from faucets.ethpick import EthPickBot
        from faucets.usdpick import UsdPickBot
        
        expected_urls = {
            LitePickBot: "https://litepick.io",
            TronPickBot: "https://tronpick.io",
            DogePickBot: "https://dogepick.io",
            SolPickBot: "https://solpick.io",
            BinPickBot: "https://binpick.io",
            BchPickBot: "https://bchpick.io",
            TonPickBot: "https://tonpick.io",
            PolygonPickBot: "https://polygonpick.io",
            DashPickBot: "https://dashpick.io",
            EthPickBot: "https://ethpick.io",
            UsdPickBot: "https://usdpick.io",
        }
        
        for bot_class, expected_url in expected_urls.items():
            bot = bot_class(self.settings, self.page)
            self.assertEqual(bot.base_url, expected_url, 
                           f"{bot_class.__name__} has incorrect base_url")
            
    async def test_all_pick_faucets_have_registration_method(self):
        """Test that all Pick faucet bots inherit the registration method."""
        from faucets.solpick import SolPickBot
        from faucets.binpick import BinPickBot
        from faucets.bchpick import BchPickBot
        from faucets.tonpick import TonPickBot
        from faucets.polygonpick import PolygonPickBot
        from faucets.dashpick import DashPickBot
        from faucets.ethpick import EthPickBot
        from faucets.usdpick import UsdPickBot
        
        faucet_classes = [
            LitePickBot, TronPickBot, DogePickBot, SolPickBot, 
            BinPickBot, BchPickBot, TonPickBot, PolygonPickBot,
            DashPickBot, EthPickBot, UsdPickBot
        ]
        
        for bot_class in faucet_classes:
            bot = bot_class(self.settings, self.page)
            self.assertTrue(hasattr(bot, 'register'), 
                          f"{bot_class.__name__} missing register method")
            self.assertTrue(callable(bot.register),
                          f"{bot_class.__name__}.register is not callable")
            

if __name__ == "__main__":
    unittest.main()
