"""
Test suite for SolPick faucet bot.

Validates login, balance extraction, timer parsing, claim cycle, and CAPTCHA handling.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from faucets.solpick import SolPickBot
from faucets.base import ClaimResult
from core.config import BotSettings
from core.extractor import DataExtractor


class TestSolPickBot(unittest.IsolatedAsyncioTestCase):
    """Test cases for SolPick bot functionality."""

    async def asyncSetUp(self):
        """Set up test fixtures before each test."""
        self.settings = MagicMock(spec=BotSettings)
        # Mock get_account to return dummy credentials
        self.settings.get_account.return_value = {
            "email": "test@example.com",
            "password": "testpassword123"
        }
        self.settings.captcha_provider = "2captcha"
        self.settings.twocaptcha_api_key = "test_api_key"
        self.settings.use_faucetpay = True
        self.settings.faucetpay_sol_address = "SolanaTestAddress123"
        
        self.page = AsyncMock()
        self.page.title.return_value = "SolPick - Free SOL Faucet"
        self.page.locator = MagicMock()
        
        # Default mock for is_visible
        is_vis = AsyncMock()
        is_vis.return_value = False
        self.page.locator.return_value.is_visible = is_vis

        # Default mock for text_content
        text_cont = AsyncMock()
        text_cont.return_value = ""
        self.page.locator.return_value.text_content = text_cont
        
        # Default mock for count
        count_mock = AsyncMock()
        count_mock.return_value = 0
        self.page.locator.return_value.count = count_mock

    async def test_solpick_initialization(self):
        """Test that SolPick initializes with correct attributes."""
        bot = SolPickBot(self.settings, self.page)
        
        self.assertEqual(bot.faucet_name, "SolPick")
        self.assertEqual(bot.base_url, "https://solpick.io")
        self.assertIsNotNone(bot.solver)

    async def test_login_success(self):
        """Test successful login flow."""
        bot = SolPickBot(self.settings, self.page)
        bot.random_delay = AsyncMock()
        bot.human_type = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.handle_cloudflare = AsyncMock()
        bot.close_popups = AsyncMock()
        bot._navigate_with_retry = AsyncMock(return_value=True)
        
        # Mock successful navigation and login
        self.page.wait_for_load_state = AsyncMock()
        
        # Mock logged in state
        logout_loc = AsyncMock()
        logout_loc.is_visible.return_value = True
        
        def locator_side_effect(selector):
            if "logout" in selector.lower():
                return logout_loc
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        result = await bot.login()
        
        self.assertTrue(result)
        bot._navigate_with_retry.assert_called_once()
        bot.human_type.assert_called()  # Should be called for email and password
        bot.idle_mouse.assert_called()  # Stealth behavior

    async def test_login_failure_no_credentials(self):
        """Test login fails when no credentials are found."""
        bot = SolPickBot(self.settings, self.page)
        bot._navigate_with_retry = AsyncMock(return_value=True)
        
        # Mock no credentials
        self.settings.get_account.return_value = None
        
        result = await bot.login()
        
        self.assertFalse(result)

    async def test_login_failure_navigation(self):
        """Test login fails when navigation fails."""
        bot = SolPickBot(self.settings, self.page)
        bot._navigate_with_retry = AsyncMock(return_value=False)
        
        result = await bot.login()
        
        self.assertFalse(result)

    async def test_balance_extraction_success(self):
        """Test balance extraction with various formats."""
        bot = SolPickBot(self.settings, self.page)
        
        # Mock balance element
        balance_loc = AsyncMock()
        balance_loc.is_visible.return_value = True
        balance_loc.text_content.return_value = "Balance: 0.00123456 SOL"
        
        def locator_side_effect(selector):
            if ".balance" in selector:
                return balance_loc
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        balance = await bot.get_balance()
        
        self.assertEqual(balance, "0.00123456")

    async def test_balance_extraction_with_commas(self):
        """Test balance extraction handles comma-separated numbers."""
        bot = SolPickBot(self.settings, self.page)
        
        balance_loc = AsyncMock()
        balance_loc.is_visible.return_value = True
        balance_loc.text_content.return_value = "1,234.567890"
        
        def locator_side_effect(selector):
            if ".balance" in selector:
                return balance_loc
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        balance = await bot.get_balance()
        
        self.assertEqual(balance, "1234.567890")

    async def test_balance_extraction_fallback(self):
        """Test balance returns '0' when extraction fails."""
        bot = SolPickBot(self.settings, self.page)
        
        # Mock no balance found
        balance_loc = AsyncMock()
        balance_loc.is_visible.return_value = False
        self.page.locator.return_value = balance_loc
        
        balance = await bot.get_balance()
        
        self.assertEqual(balance, "0")

    async def test_timer_parsing_mmss_format(self):
        """Test timer parsing for MM:SS format."""
        timer_text = "45:30"
        minutes = DataExtractor.parse_timer_to_minutes(timer_text)
        self.assertAlmostEqual(minutes, 45.5, places=1)

    async def test_timer_parsing_hhmmss_format(self):
        """Test timer parsing for HH:MM:SS format."""
        timer_text = "01:15:30"
        minutes = DataExtractor.parse_timer_to_minutes(timer_text)
        self.assertAlmostEqual(minutes, 75.5, places=1)

    async def test_timer_parsing_text_format(self):
        """Test timer parsing for '1h 30m' format."""
        timer_text = "1h 30m"
        minutes = DataExtractor.parse_timer_to_minutes(timer_text)
        self.assertEqual(minutes, 90.0)

    async def test_claim_on_cooldown(self):
        """Test claim returns cooldown when timer is active."""
        bot = SolPickBot(self.settings, self.page)
        bot.random_delay = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.handle_cloudflare = AsyncMock()
        bot.close_popups = AsyncMock()
        bot._navigate_with_retry = AsyncMock(return_value=True)
        
        # Mock timer visibility
        timer_loc = AsyncMock()
        timer_loc.count.return_value = 1
        timer_loc.first.text_content.return_value = "45:30"
        timer_loc.first.is_visible.return_value = True
        
        # Mock balance
        balance_loc = AsyncMock()
        balance_loc.is_visible.return_value = True
        balance_loc.text_content.return_value = "0.005 SOL"
        
        def locator_side_effect(selector):
            if "time" in selector.lower():
                return timer_loc
            if "balance" in selector:
                return balance_loc
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        result = await bot.claim()
        
        self.assertTrue(result.success)
        self.assertEqual(result.status, "Cooldown")
        self.assertAlmostEqual(result.next_claim_minutes, 45.5, places=1)

    async def test_claim_success(self):
        """Test successful claim flow."""
        bot = SolPickBot(self.settings, self.page)
        bot.random_delay = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.simulate_reading = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.handle_cloudflare = AsyncMock()
        bot.close_popups = AsyncMock()
        bot._navigate_with_retry = AsyncMock(return_value=True)
        bot.solver = AsyncMock()
        bot.solver.solve_captcha = AsyncMock(return_value=True)
        
        # Mock no timer (ready to claim)
        timer_loc = AsyncMock()
        timer_loc.count.return_value = 1
        timer_loc.first.text_content.return_value = ""
        
        # Mock no CAPTCHA visible
        captcha_loc = AsyncMock()
        captcha_loc.is_visible.return_value = False
        
        # Mock claim button visible
        claim_btn = AsyncMock()
        claim_btn.is_visible.return_value = True
        
        # Mock success message
        success_msg = AsyncMock()
        success_msg.count.return_value = 1
        success_msg.first.wait_for = AsyncMock()
        success_msg.first.text_content.return_value = "You won 0.00000250 SOL"
        
        # Mock balance
        balance_loc = AsyncMock()
        balance_loc.is_visible.return_value = True
        balance_loc.text_content.return_value = "0.00500250 SOL"
        
        # Mock new timer after claim
        new_timer_loc = AsyncMock()
        new_timer_loc.first.text_content.return_value = "60:00"
        
        def locator_side_effect(selector):
            if "time" in selector.lower() and "timer" in selector.lower():
                return timer_loc
            if "captcha" in selector.lower() or "turnstile" in selector.lower():
                return captcha_loc
            if "button" in selector.lower() or "claim" in selector.lower():
                return claim_btn
            if "success" in selector.lower() or "alert" in selector.lower():
                return success_msg
            if "balance" in selector:
                return balance_loc
            if "#time" in selector or ".timer" in selector:
                return new_timer_loc
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        result = await bot.claim()
        
        self.assertTrue(result.success)
        self.assertEqual(result.status, "Claimed")
        self.assertIn("0.00000250 SOL", result.amount)
        bot.human_like_click.assert_called_once()
        bot.solver.solve_captcha.assert_not_called()  # No CAPTCHA in this test

    async def test_claim_with_captcha(self):
        """Test claim flow with CAPTCHA solving."""
        bot = SolPickBot(self.settings, self.page)
        bot.random_delay = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.simulate_reading = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.handle_cloudflare = AsyncMock()
        bot.close_popups = AsyncMock()
        bot._navigate_with_retry = AsyncMock(return_value=True)
        bot.solver = AsyncMock()
        bot.solver.solve_captcha = AsyncMock(return_value=True)
        
        # Mock no timer
        timer_loc = AsyncMock()
        timer_loc.count.return_value = 0
        
        # Mock CAPTCHA visible
        captcha_loc = AsyncMock()
        captcha_loc.is_visible.return_value = True
        
        # Mock claim button
        claim_btn = AsyncMock()
        claim_btn.is_visible.return_value = True
        
        # Mock success message
        success_msg = AsyncMock()
        success_msg.count.return_value = 1
        success_msg.first.wait_for = AsyncMock()
        success_msg.first.text_content.return_value = "Claimed successfully!"
        
        def locator_side_effect(selector):
            if "captcha" in selector.lower() or "turnstile" in selector.lower():
                return captcha_loc
            if "button" in selector.lower():
                return claim_btn
            if "success" in selector.lower():
                return success_msg
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        result = await bot.claim()
        
        self.assertTrue(result.success)
        bot.solver.solve_captcha.assert_called_once()
        bot.simulate_reading.assert_called()  # Stealth behavior before CAPTCHA

    async def test_claim_button_not_found(self):
        """Test claim handles missing button gracefully."""
        bot = SolPickBot(self.settings, self.page)
        bot.random_delay = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.handle_cloudflare = AsyncMock()
        bot.close_popups = AsyncMock()
        bot._navigate_with_retry = AsyncMock(return_value=True)
        
        # Mock no timer
        timer_loc = AsyncMock()
        timer_loc.count.return_value = 0
        
        # Mock button not visible
        claim_btn = AsyncMock()
        claim_btn.is_visible.return_value = False
        
        # Mock page content with "already claimed"
        self.page.content.return_value = "<div>Already claimed, please wait</div>"
        
        def locator_side_effect(selector):
            if "button" in selector.lower():
                return claim_btn
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        result = await bot.claim()
        
        self.assertTrue(result.success)
        self.assertEqual(result.status, "Already Claimed")

    async def test_claim_network_failure(self):
        """Test claim handles network failures."""
        bot = SolPickBot(self.settings, self.page)
        bot._navigate_with_retry = AsyncMock(return_value=False)
        
        result = await bot.claim()
        
        self.assertFalse(result.success)
        self.assertEqual(result.status, "Connection Failed")
        self.assertEqual(result.next_claim_minutes, 15)

    async def test_claim_exception_handling(self):
        """Test claim handles exceptions gracefully and continues with degraded functionality."""
        bot = SolPickBot(self.settings, self.page)
        bot.handle_cloudflare = AsyncMock()
        bot.close_popups = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot._navigate_with_retry = AsyncMock(return_value=True)
        bot.simulate_reading = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.solver = AsyncMock()
        bot.solver.solve_captcha = AsyncMock(return_value=True)
        
        # Mock exception during timer check (but claim should continue)
        timer_loc = AsyncMock()
        timer_loc.count.side_effect = Exception("Test exception")
        
        # Mock no CAPTCHA
        captcha_loc = AsyncMock()
        captcha_loc.is_visible.return_value = False
        
        # Mock claim button visible
        claim_btn = AsyncMock()
        claim_btn.is_visible.return_value = True
        
        # Mock success message
        success_msg = AsyncMock()
        success_msg.count.return_value = 1
        success_msg.first.wait_for = AsyncMock()
        success_msg.first.text_content.return_value = "Claimed successfully"
        
        # Mock balance
        balance_loc = AsyncMock()
        balance_loc.is_visible.return_value = True
        balance_loc.text_content.return_value = "0.005 SOL"
        
        def locator_side_effect(selector):
            if "time" in selector.lower() and "timer" in selector.lower():
                return timer_loc
            if "captcha" in selector.lower() or "turnstile" in selector.lower():
                return captcha_loc
            if "button" in selector.lower():
                return claim_btn
            if "success" in selector.lower():
                return success_msg
            if "balance" in selector:
                return balance_loc
            return AsyncMock()
        
        self.page.locator.side_effect = locator_side_effect
        
        result = await bot.claim()
        
        # Should handle exception in timer check and still complete claim successfully
        self.assertTrue(result.success)
        self.assertEqual(result.status, "Claimed")

    async def test_is_logged_in_true(self):
        """Test is_logged_in returns True when logout link is visible."""
        bot = SolPickBot(self.settings, self.page)
        
        logout_loc = AsyncMock()
        logout_loc.is_visible.return_value = True
        self.page.locator.return_value = logout_loc
        
        result = await bot.is_logged_in()
        
        self.assertTrue(result)

    async def test_is_logged_in_false(self):
        """Test is_logged_in returns False when logout link is not visible."""
        bot = SolPickBot(self.settings, self.page)
        
        logout_loc = AsyncMock()
        logout_loc.is_visible.return_value = False
        self.page.locator.return_value = logout_loc
        
        result = await bot.is_logged_in()
        
        self.assertFalse(result)

    async def test_navigation_retry_success(self):
        """Test navigation retry succeeds after initial failure."""
        bot = SolPickBot(self.settings, self.page)
        
        # Mock navigation: fail once, then succeed
        response = AsyncMock()
        response.ok = True
        self.page.goto = AsyncMock(side_effect=[
            Exception("ERR_CONNECTION_CLOSED"),
            response
        ])
        
        result = await bot._navigate_with_retry("https://solpick.io/faucet.php", max_retries=2)
        
        self.assertTrue(result)
        self.assertEqual(self.page.goto.call_count, 2)

    async def test_navigation_retry_exhausted(self):
        """Test navigation returns False when all retries exhausted."""
        bot = SolPickBot(self.settings, self.page)
        
        # Mock navigation always fails
        self.page.goto = AsyncMock(side_effect=Exception("ERR_CONNECTION_CLOSED"))
        
        result = await bot._navigate_with_retry("https://solpick.io/faucet.php", max_retries=2)
        
        self.assertFalse(result)
        self.assertEqual(self.page.goto.call_count, 2)


if __name__ == "__main__":
    unittest.main()
