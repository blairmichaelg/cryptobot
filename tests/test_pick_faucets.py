import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
from faucets.litepick import LitePickBot
from faucets.pick_base import ClaimResult
from core.config import BotSettings

class TestPickFaucets(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = MagicMock(spec=BotSettings)
        # Mock get_account to return dummy credentials
        self.settings.get_account.return_value = {"email": "test@example.com", "password": "password"}
        self.settings.captcha_provider = "capsolver"
        self.settings.capsolver_api_key = "key"
        
        self.page = AsyncMock()
        self.page.title.return_value = "LitePick"
        self.page.locator = MagicMock()
        
        # Default mock for is_visible
        is_vis = AsyncMock()
        is_vis.return_value = False
        self.page.locator.return_value.is_visible = is_vis

        # Default mock for text_content
        text_cont = AsyncMock()
        text_cont.return_value = ""
        self.page.locator.return_value.text_content = text_cont
        
    async def test_litepick_claim_cooldown(self):
        bot = LitePickBot(self.settings, self.page)
        bot.random_delay = AsyncMock()
        
        # Mock timer visibility
        timer_loc = AsyncMock()
        timer_loc.text_content.return_value = "15:00"
        timer_loc.is_visible.return_value = True
        self.page.locator.return_value = timer_loc
        
        # Mock balance
        balance_loc = AsyncMock()
        balance_loc.count.return_value = 1
        balance_loc.is_visible.return_value = True
        balance_loc.text_content.return_value = "0.005 LTC"
        
        # This is a bit tricky since locator() is called multiple times
        # We can use side_effect if needed, but for a simple check:
        def locator_side_effect(selector):
            if "#time" in selector: return timer_loc
            if ".balance" in selector: return balance_loc
            return AsyncMock()

        self.page.locator.side_effect = locator_side_effect
        
        result = await bot.claim()
        self.assertEqual(result.status, "Cooldown")
        self.assertEqual(result.next_claim_minutes, 15.0)

    async def test_litepick_claim_success(self):
        bot = LitePickBot(self.settings, self.page)
        bot.random_delay = AsyncMock()
        
        # Mock no timer
        timer_loc = AsyncMock()
        timer_loc.text_content.return_value = ""
        timer_loc.is_visible.return_value = True
        
        # Mock claim button
        claim_btn = AsyncMock()
        claim_btn.is_visible.return_value = True
        
        # Mock success msg
        success_msg = AsyncMock()
        success_msg.count.return_value = 1
        success_msg.first.text_content.return_value = "You won 0.00000250 LTC"
        
        def locator_side_effect(selector):
            if "#time" in selector: return timer_loc
            if "button" in selector: return claim_btn
            if ".alert-success" in selector: return success_msg
            return AsyncMock()

        self.page.locator.side_effect = locator_side_effect
        
        # Mock human_like_click
        bot.human_like_click = AsyncMock()
        
        result = await bot.claim()
        self.assertTrue(result.success)
        self.assertEqual(result.status, "Claimed")
        self.assertIn("0.00000250 LTC", result.amount)

if __name__ == "__main__":
    unittest.main()
