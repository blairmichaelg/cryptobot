"""
Tests for DutchyCorp logic (selectors, flow) without browser execution.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.dutchy import DutchyBot, ClaimResult

class TestDutchyLogic:
    @pytest.fixture
    def bot(self):
        settings = MagicMock()
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "key"
        page = AsyncMock()
        return DutchyBot(settings, page)

    @pytest.mark.asyncio
    async def test_get_jobs(self, bot):
        """Verify job scheduling logic."""
        jobs = bot.get_jobs()
        assert len(jobs) == 2
        assert jobs[0].name == "DutchyCorp Claim"
        assert jobs[1].name == "DutchyCorp Withdraw"

    @pytest.mark.asyncio
    async def test_claim_cycle_logic(self, bot):
        """Verify the claim cycle orchestration."""
        # Mock helper methods to avoid external calls/browsers
        bot.get_balance = AsyncMock(return_value="1000")
        bot._do_roll = AsyncMock(side_effect=[30.0, 30.0]) # Both rolls on cooldown
        bot.claim_shortlinks = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.random_delay = AsyncMock()
        
        # Mock random to avoid sleep
        with patch('random.uniform', return_value=0.1):
            result = await bot.claim()
            
            assert result.success is True
            assert result.status == "Dutchy cycle complete"
            # Should take the minimum wait time from rolls (30.0)
            assert result.next_claim_minutes == 30.0
            
            # Verify execution order
            assert bot._do_roll.call_count == 2
            bot.claim_shortlinks.assert_called_once()

    @pytest.mark.asyncio
    async def test_do_roll_cooldown(self, bot):
        """Verify _do_roll handles cooldowns correctly."""
        bot.page.goto = AsyncMock()
        bot.close_popups = AsyncMock()
        bot.warm_up_page = AsyncMock()
        # Mock timer finding
        bot.get_timer = AsyncMock(return_value=15.5)
        
        with patch('random.uniform', return_value=0.1):
            wait_time = await bot._do_roll("roll.php", "Test Roll")
            
            assert wait_time == 15.5
            # Should NOT attempt to click buttons if cooldown found
            bot.human_like_click.assert_not_called()

    @pytest.mark.asyncio
    async def test_do_roll_success(self, bot):
        """Verify _do_roll attempts claim if no timer."""
        bot.page.goto = AsyncMock()
        bot.close_popups = AsyncMock()
        bot.warm_up_page = AsyncMock()
        bot.get_timer = AsyncMock(return_value=0) # No cooldown
        bot.solver.solve_captcha = AsyncMock(return_value=True)
        bot.human_like_click = AsyncMock()
        
        # Mock finding the roll button
        mock_btn = AsyncMock()
        mock_btn.count = AsyncMock(return_value=1)
        mock_btn.is_visible = AsyncMock(return_value=True)
        bot.page.locator.return_value = mock_btn
        
        with patch('random.uniform', return_value=0.1):
            wait_time = await bot._do_roll("roll.php", "Test Roll")
            
            # Should return None (indicating attempt made)
            assert wait_time is None
            # Should click roll button
            bot.human_like_click.assert_called()
