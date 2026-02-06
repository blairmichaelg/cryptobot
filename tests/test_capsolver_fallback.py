"""
Test suite for CapSolver fallback when 2Captcha returns ERROR_METHOD_CALL.

This specifically tests the hCaptcha support via CapSolver fallback mechanism
for Cointiply and other faucets that use hCaptcha.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from solvers.captcha import CaptchaSolver


class TestCapSolverFallback:
    """Test CapSolver fallback on ERROR_METHOD_CALL."""
    
    @pytest.mark.asyncio
    async def test_error_method_call_triggers_fallback(self):
        """Test that ERROR_METHOD_CALL from 2Captcha triggers CapSolver fallback."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        mock_page = AsyncMock()
        mock_page.url = "https://cointiply.com/login"
        
        # Mock _solve_2captcha to raise ERROR_METHOD_CALL
        with patch.object(solver, '_solve_2captcha', side_effect=Exception("ERROR_METHOD_CALL: hcaptcha not supported by 2Captcha")):
            # Mock _solve_capsolver to succeed
            with patch.object(solver, '_solve_capsolver', new_callable=AsyncMock) as mock_capsolver:
                mock_capsolver.return_value = "mock_hcaptcha_token_12345"
                
                result = await solver.solve_with_fallback(
                    page=mock_page,
                    captcha_type="hcaptcha",
                    sitekey="10000000-ffff-ffff-ffff-000000000001",
                    url="https://cointiply.com/login"
                )
                
                # Should succeed with CapSolver
                assert result == "mock_hcaptcha_token_12345"
                # CapSolver should have been called
                assert mock_capsolver.called
                # Should be called with correct parameters
                mock_capsolver.assert_called_once()
                call_args = mock_capsolver.call_args
                assert call_args[0][0] == "10000000-ffff-ffff-ffff-000000000001"  # sitekey
                assert call_args[0][1] == "https://cointiply.com/login"  # url
                assert call_args[0][2] == "hcaptcha"  # method
    
    @pytest.mark.asyncio
    async def test_2captcha_success_no_fallback(self):
        """Test that successful 2Captcha solve doesn't trigger fallback."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        
        # Mock _solve_2captcha to succeed
        with patch.object(solver, '_solve_2captcha', new_callable=AsyncMock) as mock_2captcha:
            mock_2captcha.return_value = "2captcha_token_success"
            
            with patch.object(solver, '_solve_capsolver', new_callable=AsyncMock) as mock_capsolver:
                result = await solver.solve_with_fallback(
                    page=mock_page,
                    captcha_type="turnstile",
                    sitekey="0x4AAAAAAA",
                    url="https://example.com"
                )
                
                # Should succeed with 2Captcha
                assert result == "2captcha_token_success"
                # CapSolver should NOT have been called
                assert not mock_capsolver.called
    
    @pytest.mark.asyncio
    async def test_both_providers_fail(self):
        """Test behavior when both 2Captcha and CapSolver fail."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        
        # Mock both providers to fail
        with patch.object(solver, '_solve_2captcha', side_effect=Exception("ERROR_METHOD_CALL: not supported")):
            with patch.object(solver, '_solve_capsolver', new_callable=AsyncMock) as mock_capsolver:
                mock_capsolver.return_value = None  # Capsolver also fails
                
                result = await solver.solve_with_fallback(
                    page=mock_page,
                    captcha_type="hcaptcha",
                    sitekey="test_key",
                    url="https://example.com"
                )
                
                # Should return None when all providers fail
                assert result is None
                # Both providers should have been tried
                assert mock_capsolver.called
    
    @pytest.mark.asyncio
    async def test_zero_balance_triggers_fallback(self):
        """Test that ERROR_ZERO_BALANCE from 2Captcha triggers fallback."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        
        # Mock _solve_2captcha to raise ZERO_BALANCE
        with patch.object(solver, '_solve_2captcha', side_effect=Exception("ERROR_ZERO_BALANCE")):
            with patch.object(solver, '_solve_capsolver', new_callable=AsyncMock) as mock_capsolver:
                mock_capsolver.return_value = "capsolver_success_token"
                
                result = await solver.solve_with_fallback(
                    page=mock_page,
                    captcha_type="hcaptcha",
                    sitekey="test_key",
                    url="https://example.com"
                )
                
                # Should succeed with CapSolver
                assert result == "capsolver_success_token"
                assert mock_capsolver.called
    
    @pytest.mark.asyncio
    async def test_no_slot_triggers_fallback(self):
        """Test that NO_SLOT error from 2Captcha triggers fallback."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        
        # Mock _solve_2captcha to raise NO_SLOT
        with patch.object(solver, '_solve_2captcha', side_effect=Exception("NO_SLOT available")):
            with patch.object(solver, '_solve_capsolver', new_callable=AsyncMock) as mock_capsolver:
                mock_capsolver.return_value = "capsolver_token"
                
                result = await solver.solve_with_fallback(
                    page=mock_page,
                    captcha_type="turnstile",
                    sitekey="test_key",
                    url="https://example.com"
                )
                
                # Should succeed with CapSolver
                assert result == "capsolver_token"
                assert mock_capsolver.called
    
    @pytest.mark.asyncio
    async def test_other_exception_propagates(self):
        """Test that non-fallback exceptions are propagated."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        
        # Mock _solve_2captcha to raise unexpected exception
        with patch.object(solver, '_solve_2captcha', side_effect=Exception("Network Error")):
            with pytest.raises(Exception) as exc_info:
                await solver.solve_with_fallback(
                    page=mock_page,
                    captcha_type="hcaptcha",
                    sitekey="test_key",
                    url="https://example.com"
                )
            
            # Should propagate the unexpected exception
            assert "Network Error" in str(exc_info.value)
    
    def test_set_fallback_provider(self):
        """Test set_fallback_provider method."""
        solver = CaptchaSolver(api_key="primary_key", provider="2captcha")
        
        # Initially no fallback
        assert solver.fallback_provider is None
        assert solver.fallback_api_key is None
        
        # Set fallback
        solver.set_fallback_provider("capsolver", "capsolver_key_123")
        
        assert solver.fallback_provider == "capsolver"
        assert solver.fallback_api_key == "capsolver_key_123"
        # Should initialize stats for fallback provider
        assert "capsolver" in solver.provider_stats
    
    def test_provider_stats_tracking(self):
        """Test that provider stats are tracked correctly."""
        solver = CaptchaSolver(
            api_key="primary_key",
            fallback_provider="capsolver",
            fallback_api_key="fallback_key"
        )
        
        # Record some results
        solver._record_provider_result("2captcha", "hcaptcha", success=False)
        solver._record_provider_result("capsolver", "hcaptcha", success=True)
        solver._record_provider_result("capsolver", "hcaptcha", success=True)
        
        stats = solver.get_provider_stats()
        
        assert stats["primary"] == "2captcha"
        assert stats["fallback"] == "capsolver"
        assert stats["providers"]["2captcha"]["failures"] == 1
        assert stats["providers"]["2captcha"]["solves"] == 0
        assert stats["providers"]["capsolver"]["solves"] == 2
        assert stats["providers"]["capsolver"]["failures"] == 0


class TestFaucetBotFallbackConfiguration:
    """Test FaucetBot initialization with fallback configuration."""
    
    def test_fallback_auto_configured_from_settings(self):
        """Test that FaucetBot auto-configures fallback from settings."""
        from faucets.base import FaucetBot
        from core.config import BotSettings
        
        # Mock settings with fallback provider
        settings = MagicMock(spec=BotSettings)
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "2captcha_key_123"
        settings.capsolver_api_key = "capsolver_key_456"
        settings.captcha_fallback_provider = "capsolver"
        settings.captcha_fallback_api_key = None  # Not explicitly set
        settings.captcha_daily_budget = 5.0
        settings.captcha_provider_routing = "fixed"
        settings.captcha_provider_routing_min_samples = 20
        settings.headless = True
        
        mock_page = AsyncMock()
        
        # Create FaucetBot
        bot = FaucetBot(settings, mock_page)
        
        # Check solver configuration
        assert bot.solver.api_key == "2captcha_key_123"
        assert bot.solver.provider == "2captcha"
        assert bot.solver.fallback_provider == "capsolver"
        # Should auto-select capsolver_api_key as fallback
        assert bot.solver.fallback_api_key == "capsolver_key_456"
    
    def test_fallback_explicit_api_key(self):
        """Test fallback with explicitly set API key."""
        from faucets.base import FaucetBot
        from core.config import BotSettings
        
        settings = MagicMock(spec=BotSettings)
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "2captcha_key"
        settings.capsolver_api_key = "capsolver_key_auto"
        settings.captcha_fallback_provider = "capsolver"
        settings.captcha_fallback_api_key = "capsolver_key_explicit"  # Explicitly set
        settings.captcha_daily_budget = 5.0
        settings.captcha_provider_routing = "fixed"
        settings.captcha_provider_routing_min_samples = 20
        settings.headless = True
        
        mock_page = AsyncMock()
        bot = FaucetBot(settings, mock_page)
        
        # Should use explicit key over auto-selected one
        assert bot.solver.fallback_api_key == "capsolver_key_explicit"
    
    def test_no_fallback_without_provider(self):
        """Test that fallback is not configured without fallback_provider."""
        from faucets.base import FaucetBot
        from core.config import BotSettings
        
        settings = MagicMock(spec=BotSettings)
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "2captcha_key"
        settings.capsolver_api_key = "capsolver_key"
        settings.captcha_fallback_provider = None  # No fallback provider
        settings.captcha_fallback_api_key = None
        settings.captcha_daily_budget = 5.0
        settings.captcha_provider_routing = "fixed"
        settings.captcha_provider_routing_min_samples = 20
        settings.headless = True
        
        mock_page = AsyncMock()
        bot = FaucetBot(settings, mock_page)
        
        # Should not have fallback configured
        assert bot.solver.fallback_provider is None
        assert bot.solver.fallback_api_key is None
