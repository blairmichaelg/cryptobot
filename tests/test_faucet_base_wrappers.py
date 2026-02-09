"""
Tests for FaucetBot wrappers (withdraw_wrapper, etc) in faucets/base.py.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.base import FaucetBot, ClaimResult

class TestFaucetBotWrappers:
    """Test FaucetBot wrappers."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance with mocks."""
        settings = MagicMock()
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "key"
        settings.capsolver_api_key = None
        settings.captcha_daily_budget = 5.0
        settings.captcha_provider_routing = "fixed"
        settings.captcha_provider_routing_min_samples = 20
        settings.headless = True
        settings.captcha_fallback_provider = None
        settings.captcha_fallback_api_key = None
        # Default threshold settings
        settings.generic_min_withdraw = 1000
        
        page = AsyncMock()
        
        bot = FaucetBot(settings, page)
        # Mock methods to avoid external calls
        bot.login_wrapper = AsyncMock(return_value=True)
        bot.get_balance = AsyncMock(return_value="1500.0")
        bot.withdraw = AsyncMock(return_value=ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440))
        
        return bot
    
    @pytest.mark.asyncio
    async def test_withdraw_wrapper_success(self, bot):
        """Test successful withdrawal."""
        # Mock analytics
        with patch("core.withdrawal_analytics.get_analytics") as mock_get_analytics:
            mock_analytics = MagicMock()
            mock_get_analytics.return_value = mock_analytics
            
            result = await bot.withdraw_wrapper(bot.page)
            
            # Should have called login
            bot.login_wrapper.assert_called_once()
            
            # Should have checked balance
            bot.get_balance.assert_called_once()
            
            # Should have called withdraw
            bot.withdraw.assert_called_once()
            
            # Should have recorded attempt and success
            mock_analytics.record_attempt.assert_called_once()
            mock_analytics.record_success.assert_called_once()
            
            assert result.success is True
            assert result.status == "Withdrawn"

    @pytest.mark.asyncio
    async def test_withdraw_wrapper_login_fail(self, bot):
        """Test withdrawal fails if login fails."""
        bot.login_wrapper.return_value = False
        
        result = await bot.withdraw_wrapper(bot.page)
        
        assert result.success is False
        assert result.status == "Login/Access Failed"
        
        # Should NOT proceed to balance or withdraw
        bot.get_balance.assert_not_called()
        bot.withdraw.assert_not_called()

    @pytest.mark.asyncio
    async def test_withdraw_wrapper_below_threshold(self, bot):
        """Test withdrawal skipped if balance below threshold."""
        bot.get_balance.return_value = "500.0"
        # Ensure setting exists
        bot.settings.generic_min_withdraw = 1000
        
        result = await bot.withdraw_wrapper(bot.page)
        
        assert result.success is True # technically success as we correctly decided not to withdraw
        assert "below threshold" in result.status
        
        # Should NOT call withdraw
        bot.withdraw.assert_not_called()

    @pytest.mark.asyncio
    async def test_withdraw_wrapper_withdraw_fail(self, bot):
        """Test withdrawal wrapper handles withdraw failure."""
        bot.withdraw.return_value = ClaimResult(success=False, status="Withdrawal Error")
        
        with patch("core.withdrawal_analytics.get_analytics") as mock_get_analytics:
            mock_analytics = MagicMock()
            mock_get_analytics.return_value = mock_analytics
            
            result = await bot.withdraw_wrapper(bot.page)
            
            assert result.success is False
            assert result.status == "Withdrawal Error"
            
            # Should record failure
            mock_analytics.record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_withdraw_wrapper_exception(self, bot):
        """Test withdrawal wrapper handles exceptions."""
        bot.get_balance.side_effect = Exception("Balance check failed")
        
        result = await bot.withdraw_wrapper(bot.page)
        
        assert result.success is False
        assert "Error" in result.status
