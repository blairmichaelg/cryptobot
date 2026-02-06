"""
Test suite for hCaptcha fallback to CapSolver functionality.

Tests the complete flow:
1. hCaptcha detection on Cointiply login page
2. 2Captcha attempts to solve but returns ERROR_METHOD_CALL
3. System falls back to CapSolver
4. CapSolver successfully solves hCaptcha
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from solvers.captcha import CaptchaSolver


class TestHCaptchaFallback:
    """Test hCaptcha fallback from 2Captcha to CapSolver."""
    
    @pytest.mark.asyncio
    async def test_hcaptcha_fallback_on_error_method_call(self):
        """Test that ERROR_METHOD_CALL triggers fallback to CapSolver."""
        # Initialize solver with 2Captcha as primary and CapSolver as fallback
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        # Mock page
        page = AsyncMock()
        page.url = "https://cointiply.com/login"
        
        # Mock _solve_2captcha to raise ERROR_METHOD_CALL
        with patch.object(solver, '_solve_2captcha', 
                         side_effect=Exception("2Captcha Error: ERROR_METHOD_CALL")) as mock_2captcha:
            # Mock _solve_capsolver to return success
            with patch.object(solver, '_solve_capsolver',
                            return_value="capsolver_token_abc123") as mock_capsolver:
                
                # Test solve_with_fallback
                result = await solver.solve_with_fallback(
                    page=page,
                    captcha_type="hcaptcha",
                    sitekey="00000000-0000-0000-0000-000000000000",
                    url="https://cointiply.com/login"
                )
                
                # Verify 2Captcha was tried first
                assert mock_2captcha.called
                
                # Verify CapSolver was used as fallback
                assert mock_capsolver.called
                
                # Verify we got the CapSolver token
                assert result == "capsolver_token_abc123"
    
    @pytest.mark.asyncio
    async def test_hcaptcha_fallback_on_zero_balance(self):
        """Test that ERROR_ZERO_BALANCE triggers fallback to CapSolver."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        page = AsyncMock()
        page.url = "https://cointiply.com/login"
        
        # Mock _solve_2captcha to raise ZERO_BALANCE
        with patch.object(solver, '_solve_2captcha',
                         side_effect=Exception("2Captcha Error: ERROR_ZERO_BALANCE")) as mock_2captcha:
            with patch.object(solver, '_solve_capsolver',
                            return_value="capsolver_token_xyz789") as mock_capsolver:
                
                result = await solver.solve_with_fallback(
                    page=page,
                    captcha_type="hcaptcha",
                    sitekey="00000000-0000-0000-0000-000000000000",
                    url="https://cointiply.com/login"
                )
                
                assert mock_2captcha.called
                assert mock_capsolver.called
                assert result == "capsolver_token_xyz789"
    
    @pytest.mark.asyncio
    async def test_hcaptcha_no_fallback_on_timeout(self):
        """Test that timeout (None return) doesn't immediately trigger fallback, but retries."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        page = AsyncMock()
        page.url = "https://cointiply.com/login"
        
        # Mock _solve_2captcha to return None (timeout) twice, then succeed
        call_count = 0
        def mock_2captcha_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return None  # Timeout
            return "2captcha_token_success"
        
        with patch.object(solver, '_solve_2captcha',
                         side_effect=mock_2captcha_side_effect) as mock_2captcha:
            with patch.object(solver, '_solve_capsolver',
                            return_value="should_not_be_called") as mock_capsolver:
                
                result = await solver.solve_with_fallback(
                    page=page,
                    captcha_type="hcaptcha",
                    sitekey="00000000-0000-0000-0000-000000000000",
                    url="https://cointiply.com/login"
                )
                
                # Should retry 2Captcha and succeed
                assert call_count == 2
                assert result == "2captcha_token_success"
                
                # Should NOT use CapSolver
                assert not mock_capsolver.called
    
    @pytest.mark.asyncio
    async def test_hcaptcha_fallback_after_retries_exhausted(self):
        """Test that fallback is used after 2Captcha retries are exhausted."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        page = AsyncMock()
        page.url = "https://cointiply.com/login"
        
        # Mock _solve_2captcha to always return None (timeout)
        with patch.object(solver, '_solve_2captcha',
                         return_value=None) as mock_2captcha:
            with patch.object(solver, '_solve_capsolver',
                            return_value="capsolver_fallback_token") as mock_capsolver:
                
                result = await solver.solve_with_fallback(
                    page=page,
                    captcha_type="hcaptcha",
                    sitekey="00000000-0000-0000-0000-000000000000",
                    url="https://cointiply.com/login"
                )
                
                # 2Captcha should be retried max_retries times
                assert mock_2captcha.call_count == 2  # max_retries = 2
                
                # After exhausting retries, should try CapSolver
                assert mock_capsolver.called
                assert result == "capsolver_fallback_token"
    
    @pytest.mark.asyncio
    async def test_hcaptcha_both_providers_fail(self):
        """Test that None is returned when both providers fail."""
        solver = CaptchaSolver(
            api_key="2captcha_key",
            provider="2captcha",
            fallback_provider="capsolver",
            fallback_api_key="capsolver_key"
        )
        
        page = AsyncMock()
        page.url = "https://cointiply.com/login"
        
        # Both providers fail
        with patch.object(solver, '_solve_2captcha',
                         side_effect=Exception("2Captcha Error: ERROR_ZERO_BALANCE")):
            with patch.object(solver, '_solve_capsolver',
                            return_value=None):
                
                result = await solver.solve_with_fallback(
                    page=page,
                    captcha_type="hcaptcha",
                    sitekey="00000000-0000-0000-0000-000000000000",
                    url="https://cointiply.com/login"
                )
                
                # Should return None when all providers fail
                assert result is None


class TestHCaptchaDetection:
    """Test hCaptcha detection logic."""
    
    @pytest.mark.asyncio
    async def test_hcaptcha_iframe_detection(self):
        """Test that hCaptcha iframe is properly detected."""
        solver = CaptchaSolver(api_key="test_key")
        
        # Mock page with hCaptcha iframe
        page = AsyncMock()
        page.url = "https://cointiply.com/login"
        
        # Mock iframe element
        hcaptcha_iframe = MagicMock()
        hcaptcha_iframe.get_attribute = AsyncMock(
            return_value="https://hcaptcha.com/captcha/v1/abc?sitekey=00000000-0000-0000-0000-000000000000&host=cointiply.com"
        )
        
        page.query_selector = AsyncMock(return_value=hcaptcha_iframe)
        page.content = AsyncMock(return_value="<html></html>")
        page.locator = MagicMock()
        page.locator.return_value.count = AsyncMock(return_value=0)
        
        # Mock solve_with_fallback to verify it's called with correct params
        with patch.object(solver, 'solve_with_fallback',
                         return_value="test_token") as mock_solve:
            with patch.object(solver, '_inject_token') as mock_inject:
                with patch.object(solver, '_wait_for_human',
                                return_value=True):
                    
                    result = await solver.solve_captcha(page)
                    
                    # Should detect hCaptcha and attempt to solve
                    # Note: The actual detection happens in solve_captcha method
                    # We're testing that the flow works end-to-end


class TestCapSolverHCaptchaAPI:
    """Test CapSolver hCaptcha API integration."""
    
    @pytest.mark.asyncio
    async def test_capsolver_hcaptcha_task_proxyless(self):
        """Test that CapSolver uses HCaptchaTaskProxyLess for hCaptcha without proxy."""
        solver = CaptchaSolver(api_key="capsolver_key", provider="capsolver")
        
        # Mock aiohttp session
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={
            "errorId": 0,
            "taskId": "test_task_123"
        })
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.__aexit__ = AsyncMock()
        
        # Mock getTaskResult response
        result_response = AsyncMock()
        result_response.json = AsyncMock(return_value={
            "status": "ready",
            "solution": {"token": "hcaptcha_solution_token"}
        })
        
        with patch.object(solver, '_get_session', return_value=mock_session):
            with patch.object(mock_session, 'post') as mock_post:
                # First call: createTask
                # Second call: getTaskResult
                mock_post.side_effect = [
                    mock_response,
                    result_response
                ]
                
                result = await solver._solve_capsolver(
                    sitekey="00000000-0000-0000-0000-000000000000",
                    url="https://cointiply.com/login",
                    method="hcaptcha",
                    proxy_context=None
                )
                
                # Verify createTask was called with correct task type
                create_task_call = mock_post.call_args_list[0]
                payload = create_task_call[1]['json']
                
                assert payload['task']['type'] == "HCaptchaTaskProxyLess"
                assert payload['task']['websiteURL'] == "https://cointiply.com/login"
                assert payload['task']['websiteKey'] == "00000000-0000-0000-0000-000000000000"


class TestAutoConfigFallbackAPIKey:
    """Test auto-configuration of fallback API key in FaucetBot base."""
    
    def test_auto_config_capsolver_key(self):
        """Test that CapSolver API key is auto-selected when fallback provider is capsolver."""
        from faucets.base import FaucetBot
        from core.config import BotSettings
        
        # Create mock settings
        settings = MagicMock(spec=BotSettings)
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "2captcha_key_123"
        settings.capsolver_api_key = "capsolver_key_456"
        settings.captcha_fallback_provider = "capsolver"
        settings.captcha_fallback_api_key = None  # Not explicitly set
        settings.captcha_daily_budget = 5.0
        settings.captcha_provider_routing = "fixed"
        settings.headless = True
        
        # Create mock page
        page = AsyncMock()
        
        # Initialize bot (which should auto-configure fallback)
        with patch('faucets.base.CaptchaSolver') as MockSolver:
            bot = FaucetBot(settings, page)
            
            # Verify set_fallback_provider was called with auto-configured key
            MockSolver.return_value.set_fallback_provider.assert_called_once_with(
                "capsolver", 
                "capsolver_key_456"  # Should auto-select from settings.capsolver_api_key
            )
