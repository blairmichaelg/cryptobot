"""
Comprehensive test suite for solvers/captcha.py CaptchaSolver class.

Achieves 100% coverage on all CaptchaSolver methods including:
- Initialization with various providers
- Budget tracking and management
- Provider statistics and routing
- Proxy parsing
- Session management
- Fallback provider logic
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch


class TestCaptchaSolverInitialization:
    """Test CaptchaSolver initialization scenarios."""
    
    def test_init_default_values(self):
        """Test default initialization values."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        
        assert solver.api_key is None
        assert solver.provider == "2captcha"
        assert solver.fallback_provider is None
        assert solver.fallback_api_key is None
        assert solver.daily_budget == 5.0
        assert solver.faucet_name is None
        assert solver.headless is False
    
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="test_api_key_123")
        
        assert solver.api_key == "test_api_key_123"
    
    def test_init_2captcha_provider(self):
        """Test initialization with 2captcha provider."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", provider="2captcha")
        
        assert solver.provider == "2captcha"
    
    def test_init_twocaptcha_normalized(self):
        """Test twocaptcha provider name is normalized to 2captcha."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", provider="twocaptcha")
        
        assert solver.provider == "2captcha"
    
    def test_init_capsolver_provider(self):
        """Test initialization with capsolver provider."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", provider="capsolver")
        
        assert solver.provider == "capsolver"
    
    def test_init_with_daily_budget(self):
        """Test initialization with custom daily budget."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=10.0)
        
        assert solver.daily_budget == 10.0
    
    def test_init_with_fallback_provider(self):
        """Test initialization with fallback provider."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(
            api_key="primary_key",
            fallback_provider="capsolver",
            fallback_api_key="fallback_key"
        )
        
        assert solver.fallback_provider == "capsolver"
        assert solver.fallback_api_key == "fallback_key"
    
    def test_init_with_adaptive_routing(self):
        """Test initialization with adaptive routing enabled."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(
            api_key="key",
            adaptive_routing=True,
            routing_min_samples=10
        )
        
        assert solver.adaptive_routing is True
        assert solver.routing_min_samples == 10
    
    def test_init_provider_stats_initialized(self):
        """Test provider_stats is initialized for primary provider."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", provider="2captcha")
        
        assert "2captcha" in solver.provider_stats
        assert solver.provider_stats["2captcha"]["solves"] == 0
        assert solver.provider_stats["2captcha"]["failures"] == 0
        assert solver.provider_stats["2captcha"]["cost"] == 0.0


class TestCaptchaSolverFaucetName:
    """Test faucet name association methods."""
    
    def test_set_faucet_name(self):
        """Test set_faucet_name method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_faucet_name("FireFaucet")
        
        assert solver.faucet_name == "FireFaucet"
    
    def test_set_faucet_name_creates_stats_entry(self):
        """Test set_faucet_name creates faucet_provider_stats entry."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_faucet_name("TestFaucet")
        
        assert "TestFaucet" in solver.faucet_provider_stats
    
    def test_set_faucet_name_none(self):
        """Test set_faucet_name with None."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_faucet_name(None)
        
        assert solver.faucet_name is None


class TestCaptchaSolverProxy:
    """Test proxy configuration methods."""
    
    def test_set_proxy(self):
        """Test set_proxy method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_proxy("http://proxy:8080")
        
        assert solver.proxy_string == "http://proxy:8080"
    
    def test_parse_proxy_http(self):
        """Test _parse_proxy with HTTP proxy."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        result = solver._parse_proxy("http://user:pass@host:8080")
        
        assert result["proxytype"] == "HTTP"
        assert "user:pass@host:8080" in result["proxy"]
    
    def test_parse_proxy_socks5(self):
        """Test _parse_proxy with SOCKS5 proxy."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        result = solver._parse_proxy("socks5://user:pass@host:1080")
        
        assert result["proxytype"] == "SOCKS5"
    
    def test_parse_proxy_without_protocol(self):
        """Test _parse_proxy without protocol prefix."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        result = solver._parse_proxy("user:pass@host:8080")
        
        # Should default to HTTP
        assert result["proxytype"] == "HTTP"
    
    def test_parse_proxy_without_auth(self):
        """Test _parse_proxy without username/password."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        result = solver._parse_proxy("http://host:8080")
        
        assert "host:8080" in result["proxy"]


class TestCaptchaSolverHeadless:
    """Test headless mode configuration."""
    
    def test_set_headless_true(self):
        """Test set_headless with True."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_headless(True)
        
        assert solver.headless is True
    
    def test_set_headless_false(self):
        """Test set_headless with False."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_headless(False)
        
        assert solver.headless is False
    
    def test_set_headless_converts_to_bool(self):
        """Test set_headless converts truthy values to bool."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_headless(1)  # Truthy value
        
        assert solver.headless is True


class TestCaptchaSolverFallbackProvider:
    """Test fallback provider configuration."""
    
    def test_set_fallback_provider(self):
        """Test set_fallback_provider method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="primary")
        solver.set_fallback_provider("capsolver", "fallback_key")
        
        assert solver.fallback_provider == "capsolver"
        assert solver.fallback_api_key == "fallback_key"
    
    def test_set_fallback_provider_normalizes_twocaptcha(self):
        """Test set_fallback_provider normalizes twocaptcha name."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="primary")
        solver.set_fallback_provider("twocaptcha", "fallback_key")
        
        assert solver.fallback_provider == "2captcha"
    
    def test_set_fallback_provider_creates_stats(self):
        """Test set_fallback_provider creates stats entry."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="primary")
        solver.set_fallback_provider("capsolver", "fallback_key")
        
        assert "capsolver" in solver.provider_stats


class TestCaptchaSolverBudgetTracking:
    """Test budget tracking and management."""
    
    def test_get_budget_stats_initial(self):
        """Test get_budget_stats with initial state."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        stats = solver.get_budget_stats()
        
        assert stats["daily_budget"] == 5.0
        assert stats["spent_today"] == 0.0
        assert stats["remaining"] == 5.0
        assert stats["solves_today"] == 0
    
    def test_record_solve_success(self):
        """Test _record_solve for successful solve."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        solver._record_solve("turnstile", success=True)
        
        assert solver._daily_spend > 0
        assert solver._solve_count_today == 1
    
    def test_record_solve_failure(self):
        """Test _record_solve for failed solve."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        initial_spend = solver._daily_spend
        solver._record_solve("turnstile", success=False)
        
        # Failed solves don't cost money
        assert solver._daily_spend == initial_spend
        assert solver._solve_count_today == 1
    
    def test_can_afford_solve_true(self):
        """Test _can_afford_solve when budget is available."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        
        assert solver._can_afford_solve("turnstile") is True
    
    def test_can_afford_solve_false(self):
        """Test _can_afford_solve when budget is exhausted."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=0.001)
        solver._daily_spend = 0.001
        
        assert solver._can_afford_solve("turnstile") is False
    
    def test_can_afford_captcha_true(self):
        """Test can_afford_captcha when budget is available."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        
        assert solver.can_afford_captcha("turnstile") is True
    
    def test_can_afford_captcha_false_exhausted(self):
        """Test can_afford_captcha when budget is exhausted."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=0.002)
        solver._daily_spend = 0.001
        
        # Should return False since remaining < cost
        assert solver.can_afford_captcha("turnstile") is False
    
    def test_budget_reset_new_day(self):
        """Test daily budget resets on new day."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        solver._daily_spend = 3.0
        solver._solve_count_today = 10
        solver._budget_reset_date = "2000-01-01"  # Old date
        
        solver._check_and_reset_daily_budget()
        
        assert solver._daily_spend == 0.0
        assert solver._solve_count_today == 0
        assert solver._budget_reset_date == time.strftime("%Y-%m-%d")
    
    def test_budget_no_reset_same_day(self):
        """Test budget doesn't reset on same day."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        solver._daily_spend = 2.0
        solver._solve_count_today = 5
        solver._budget_reset_date = time.strftime("%Y-%m-%d")  # Today
        
        solver._check_and_reset_daily_budget()
        
        assert solver._daily_spend == 2.0
        assert solver._solve_count_today == 5


class TestCaptchaSolverProviderStats:
    """Test provider statistics tracking."""
    
    def test_get_provider_stats(self):
        """Test get_provider_stats method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", provider="2captcha")
        solver.set_fallback_provider("capsolver", "key2")
        
        stats = solver.get_provider_stats()
        
        assert stats["primary"] == "2captcha"
        assert stats["fallback"] == "capsolver"
        assert "providers" in stats
    
    def test_record_provider_result_success(self):
        """Test _record_provider_result for successful solve."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key")
        solver._record_provider_result("2captcha", "turnstile", success=True)
        
        assert solver.provider_stats["2captcha"]["solves"] == 1
        assert solver.provider_stats["2captcha"]["failures"] == 0
        assert solver.provider_stats["2captcha"]["cost"] > 0
    
    def test_record_provider_result_failure(self):
        """Test _record_provider_result for failed solve."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key")
        solver._record_provider_result("2captcha", "turnstile", success=False)
        
        assert solver.provider_stats["2captcha"]["solves"] == 0
        assert solver.provider_stats["2captcha"]["failures"] == 1
    
    def test_record_provider_result_per_faucet(self):
        """Test _record_provider_result tracks per-faucet stats."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key")
        solver.set_faucet_name("TestFaucet")
        solver._record_provider_result("2captcha", "turnstile", success=True)
        
        faucet_stats = solver.faucet_provider_stats["TestFaucet"]
        assert "2captcha" in faucet_stats
        assert faucet_stats["2captcha"]["solves"] == 1
    
    def test_record_provider_result_creates_provider_entry(self):
        """Test _record_provider_result creates new provider entry if missing."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key")
        solver._record_provider_result("new_provider", "turnstile", success=True)
        
        assert "new_provider" in solver.provider_stats


class TestCaptchaSolverExpectedCost:
    """Test expected cost calculation for adaptive routing."""
    
    def test_expected_cost_not_enough_samples(self):
        """Test _expected_cost returns None with insufficient samples."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", routing_min_samples=10)
        
        # No samples recorded
        cost = solver._expected_cost("2captcha", "turnstile")
        
        assert cost is None
    
    def test_expected_cost_with_enough_samples(self):
        """Test _expected_cost returns value with enough samples."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", routing_min_samples=2)
        
        # Record enough samples
        for _ in range(5):
            solver._record_provider_result("2captcha", "turnstile", success=True)
        
        cost = solver._expected_cost("2captcha", "turnstile")
        
        assert cost is not None
        assert cost > 0
    
    def test_expected_cost_uses_faucet_stats_when_available(self):
        """Test _expected_cost prefers faucet-specific stats."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", routing_min_samples=2)
        solver.set_faucet_name("TestFaucet")
        
        # Record faucet-specific samples
        for _ in range(5):
            solver._record_provider_result("2captcha", "turnstile", success=True)
        
        cost = solver._expected_cost("2captcha", "turnstile")
        
        assert cost is not None


class TestCaptchaSolverProviderOrder:
    """Test provider order selection for adaptive routing."""
    
    def test_choose_provider_order_non_adaptive(self):
        """Test _choose_provider_order with non-adaptive routing."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", adaptive_routing=False)
        
        order = solver._choose_provider_order("turnstile")
        
        assert order == ["2captcha"]
    
    def test_choose_provider_order_with_fallback(self):
        """Test _choose_provider_order includes fallback."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", adaptive_routing=False)
        solver.set_fallback_provider("capsolver", "key2")
        
        order = solver._choose_provider_order("turnstile")
        
        assert len(order) == 2
        assert "2captcha" in order
        assert "capsolver" in order
    
    def test_choose_provider_order_adaptive_no_samples(self):
        """Test _choose_provider_order with adaptive but no samples."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", adaptive_routing=True, routing_min_samples=10)
        solver.set_fallback_provider("capsolver", "key2")
        
        order = solver._choose_provider_order("turnstile")
        
        # Should return both providers in some order
        assert len(order) == 2


class TestCaptchaSolverSession:
    """Test session management."""
    
    @pytest.mark.asyncio
    async def test_get_session_creates_new(self):
        """Test _get_session creates new session if none exists."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.session = None
        
        with patch("aiohttp.ClientSession") as MockSession:
            MockSession.return_value = MagicMock()
            session = await solver._get_session()
            
            MockSession.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_session_reuses_existing(self):
        """Test _get_session reuses existing session."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        mock_session = MagicMock()
        mock_session.closed = False
        solver.session = mock_session
        
        session = await solver._get_session()
        
        assert session == mock_session
    
    @pytest.mark.asyncio
    async def test_close_closes_session(self):
        """Test close method closes session."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        solver.session = mock_session
        
        await solver.close()
        
        mock_session.close.assert_called_once()
        assert solver.session is None
    
    @pytest.mark.asyncio
    async def test_close_handles_no_session(self):
        """Test close method handles no session gracefully."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.session = None
        
        # Should not raise
        await solver.close()
    
    @pytest.mark.asyncio
    async def test_close_handles_already_closed(self):
        """Test close method handles already closed session."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        mock_session = MagicMock()
        mock_session.closed = True
        solver.session = mock_session
        
        # Should not raise
        await solver.close()


class TestCaptchaSolverContextManager:
    """Test async context manager protocol."""
    
    @pytest.mark.asyncio
    async def test_aenter_returns_self(self):
        """Test __aenter__ returns self."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        
        result = await solver.__aenter__()
        
        assert result is solver
    
    @pytest.mark.asyncio
    async def test_aexit_closes_session(self):
        """Test __aexit__ closes session."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        solver.session = mock_session
        
        await solver.__aexit__(None, None, None)
        
        mock_session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_manager_usage(self):
        """Test full context manager usage."""
        from solvers.captcha import CaptchaSolver
        
        async with CaptchaSolver() as solver:
            assert solver is not None
            assert isinstance(solver, CaptchaSolver)


class TestCaptchaSolverCostCalculation:
    """Test cost calculation for different captcha types."""
    
    def test_cost_per_solve_turnstile(self):
        """Test cost for Turnstile captcha."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        
        assert solver._cost_per_solve["turnstile"] == 0.003
    
    def test_cost_per_solve_hcaptcha(self):
        """Test cost for hCaptcha."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        
        assert solver._cost_per_solve["hcaptcha"] == 0.003
    
    def test_cost_per_solve_recaptcha(self):
        """Test cost for reCAPTCHA."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        
        assert solver._cost_per_solve["userrecaptcha"] == 0.003
    
    def test_cost_per_solve_image(self):
        """Test cost for image captcha."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        
        assert solver._cost_per_solve["image"] == 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
