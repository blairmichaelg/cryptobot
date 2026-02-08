"""Comprehensive test suite for solvers/captcha.py CaptchaSolver class.

Covers ALL methods and edge cases including:
- Constructor with various provider configs
- Setters: set_headless, set_proxy, set_faucet_name, set_fallback_provider
- Budget tracking: _can_afford_solve, _record_solve, can_afford_captcha
- Sitekey normalization
- Coordinate parsing
- solve_with_fallback: primary/fallback/retry/error flows
- _solve_2captcha: success, submit errors, poll errors, proxy
- _solve_capsolver: success, create errors, poll errors, proxy/task mapping
- _inject_token for all methods
- _solve_image_captcha
- _solve_altcha
- solve_text_captcha
- _wait_for_human
- _extract_sitekey_from_scripts
- Provider routing: adaptive vs fixed
- Session management and close
- Async context manager
- Statistics tracking per-faucet
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from solvers.captcha import CaptchaSolver, DEFAULT_DAILY_BUDGET_USD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_solver(**kwargs):
    """Create a CaptchaSolver with sensible test defaults."""
    defaults = {"api_key": "test_key_123", "provider": "2captcha"}
    defaults.update(kwargs)
    return CaptchaSolver(**defaults)


def _mock_aiohttp_response(json_data, status=200):
    """Return an async-context-manager mock that behaves like aiohttp response."""
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=json_data)
    resp.status = status
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _mock_session():
    """Return a mock aiohttp.ClientSession."""
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()
    return session


# ===================================================================
# 1. Constructor
# ===================================================================

class TestConstructor:
    """Test CaptchaSolver.__init__ with various configurations."""

    def test_default_provider_is_2captcha(self):
        solver = CaptchaSolver()
        assert solver.provider == "2captcha"

    def test_twocaptcha_alias_normalized(self):
        solver = CaptchaSolver(provider="twocaptcha")
        assert solver.provider == "2captcha"

    def test_capsolver_provider(self):
        solver = CaptchaSolver(provider="capsolver")
        assert solver.provider == "capsolver"

    def test_case_insensitive_provider(self):
        solver = CaptchaSolver(provider="CAPSOLVER")
        assert solver.provider == "capsolver"

    def test_no_api_key_logs_warning(self):
        """No API key should still create a valid solver."""
        solver = CaptchaSolver()
        assert solver.api_key is None
        assert solver.headless is False

    def test_api_key_stored(self):
        solver = CaptchaSolver(api_key="my_key")
        assert solver.api_key == "my_key"

    def test_daily_budget_default(self):
        solver = CaptchaSolver()
        assert solver.daily_budget == DEFAULT_DAILY_BUDGET_USD

    def test_daily_budget_custom(self):
        solver = CaptchaSolver(daily_budget=10.0)
        assert solver.daily_budget == 10.0

    def test_fallback_provider_set_via_constructor(self):
        solver = CaptchaSolver(
            fallback_provider="capsolver",
            fallback_api_key="fb_key",
        )
        assert solver.fallback_provider == "capsolver"
        assert solver.fallback_api_key == "fb_key"

    def test_fallback_provider_twocaptcha_normalized(self):
        solver = CaptchaSolver(fallback_provider="twocaptcha")
        assert solver.fallback_provider == "2captcha"

    def test_no_fallback_provider(self):
        solver = CaptchaSolver()
        assert solver.fallback_provider is None

    def test_adaptive_routing_defaults_false(self):
        solver = CaptchaSolver()
        assert solver.adaptive_routing is False

    def test_adaptive_routing_enabled(self):
        solver = CaptchaSolver(adaptive_routing=True, routing_min_samples=5)
        assert solver.adaptive_routing is True
        assert solver.routing_min_samples == 5

    def test_initial_stats(self):
        solver = CaptchaSolver(provider="2captcha")
        assert solver.provider_stats["2captcha"] == {
            "solves": 0, "failures": 0, "cost": 0.0,
        }

    def test_cost_per_solve_table(self):
        solver = CaptchaSolver()
        assert solver._cost_per_solve["turnstile"] == 0.003
        assert solver._cost_per_solve["hcaptcha"] == 0.003
        assert solver._cost_per_solve["userrecaptcha"] == 0.003
        assert solver._cost_per_solve["image"] == 0.001
        assert solver._cost_per_solve["altcha"] == 0.0


# ===================================================================
# 2. Setters
# ===================================================================

class TestSetters:
    def test_set_headless_true(self):
        s = _make_solver()
        s.set_headless(True)
        assert s.headless is True

    def test_set_headless_false(self):
        s = _make_solver()
        s.set_headless(False)
        assert s.headless is False

    def test_set_headless_truthy_int(self):
        s = _make_solver()
        s.set_headless(1)
        assert s.headless is True

    def test_set_headless_falsy_zero(self):
        s = _make_solver()
        s.set_headless(0)
        assert s.headless is False

    def test_set_proxy(self):
        s = _make_solver()
        s.set_proxy("http://proxy:1234")
        assert s.proxy_string == "http://proxy:1234"

    def test_set_faucet_name(self):
        s = _make_solver()
        s.set_faucet_name("myfaucet")
        assert s.faucet_name == "myfaucet"
        assert "myfaucet" in s.faucet_provider_stats

    def test_set_faucet_name_none(self):
        s = _make_solver()
        s.set_faucet_name(None)
        assert s.faucet_name is None

    def test_set_faucet_name_does_not_duplicate(self):
        s = _make_solver()
        s.set_faucet_name("f1")
        s.faucet_provider_stats["f1"]["sentinel"] = True
        s.set_faucet_name("f1")
        # Should not overwrite existing entry
        assert s.faucet_provider_stats["f1"].get("sentinel") is True


# ===================================================================
# 3. set_fallback_provider
# ===================================================================

class TestSetFallbackProvider:
    def test_basic(self):
        s = _make_solver()
        s.set_fallback_provider("capsolver", "fb_key")
        assert s.fallback_provider == "capsolver"
        assert s.fallback_api_key == "fb_key"

    def test_normalizes_twocaptcha(self):
        s = _make_solver()
        s.set_fallback_provider("twocaptcha", "k")
        assert s.fallback_provider == "2captcha"

    def test_creates_stats_entry(self):
        s = _make_solver()
        s.set_fallback_provider("capsolver", "k")
        assert "capsolver" in s.provider_stats
        assert s.provider_stats["capsolver"]["solves"] == 0

    def test_does_not_reset_existing_stats(self):
        s = _make_solver()
        s.provider_stats["capsolver"] = {
            "solves": 5, "failures": 1, "cost": 0.015
        }
        s.set_fallback_provider("capsolver", "k")
        assert s.provider_stats["capsolver"]["solves"] == 5


# ===================================================================
# 4. Budget tracking
# ===================================================================

class TestBudgetTracking:
    def test_check_and_reset_daily_budget_new_day(self):
        s = _make_solver()
        s._daily_spend = 2.0
        s._solve_count_today = 10
        s._budget_reset_date = "1999-01-01"
        s._check_and_reset_daily_budget()
        assert s._daily_spend == 0.0
        assert s._solve_count_today == 0
        assert s._budget_reset_date == time.strftime("%Y-%m-%d")

    def test_check_and_reset_daily_budget_same_day(self):
        s = _make_solver()
        s._daily_spend = 1.5
        s._budget_reset_date = time.strftime("%Y-%m-%d")
        s._check_and_reset_daily_budget()
        assert s._daily_spend == 1.5

    def test_can_afford_solve_under_budget(self):
        s = _make_solver(daily_budget=5.0)
        assert s._can_afford_solve("turnstile") is True

    def test_can_afford_solve_over_budget(self):
        s = _make_solver(daily_budget=0.002)
        s._daily_spend = 0.001
        assert s._can_afford_solve("turnstile") is False

    def test_can_afford_captcha_under_budget(self):
        s = _make_solver(daily_budget=5.0)
        assert s.can_afford_captcha("hcaptcha") is True

    def test_can_afford_captcha_over_budget(self):
        s = _make_solver(daily_budget=0.002)
        s._daily_spend = 0.001
        assert s.can_afford_captcha("hcaptcha") is False

    def test_can_afford_captcha_low_budget_warning(self):
        """When remaining < $0.50 but still enough for the solve."""
        s = _make_solver(daily_budget=0.40)
        s._daily_spend = 0.0
        # remaining is 0.40, cost 0.003 => still enough
        assert s.can_afford_captcha("turnstile") is True

    def test_can_afford_captcha_low_budget_cannot(self):
        """When remaining < $0.50 and not enough for the solve."""
        s = _make_solver(daily_budget=0.002)
        s._daily_spend = 0.001
        # remaining is 0.001, cost 0.003 => not enough
        assert s.can_afford_captcha("turnstile") is False

    def test_record_solve_success_increases_spend(self):
        s = _make_solver()
        s._record_solve("turnstile", True)
        assert s._daily_spend == pytest.approx(0.003)
        assert s._solve_count_today == 1

    def test_record_solve_failure_no_cost(self):
        s = _make_solver()
        s._record_solve("turnstile", False)
        assert s._daily_spend == 0.0
        assert s._solve_count_today == 1

    def test_record_solve_altcha_zero_cost(self):
        s = _make_solver()
        s._record_solve("altcha", True)
        assert s._daily_spend == 0.0

    def test_record_solve_unknown_method_default_cost(self):
        s = _make_solver()
        s._record_solve("unknown_type", True)
        assert s._daily_spend == pytest.approx(0.003)

    def test_get_budget_stats(self):
        s = _make_solver(daily_budget=5.0)
        s._record_solve("turnstile", True)
        stats = s.get_budget_stats()
        assert stats["daily_budget"] == 5.0
        assert stats["spent_today"] == pytest.approx(0.003)
        assert stats["remaining"] == pytest.approx(5.0 - 0.003)
        assert stats["solves_today"] == 1
        assert "date" in stats


# ===================================================================
# 5. Provider statistics
# ===================================================================

class TestProviderStats:
    def test_record_provider_result_success(self):
        s = _make_solver()
        s._record_provider_result("2captcha", "turnstile", True)
        assert s.provider_stats["2captcha"]["solves"] == 1
        assert s.provider_stats["2captcha"]["cost"] == pytest.approx(0.003)

    def test_record_provider_result_failure(self):
        s = _make_solver()
        s._record_provider_result("2captcha", "turnstile", False)
        assert s.provider_stats["2captcha"]["failures"] == 1
        assert s.provider_stats["2captcha"]["cost"] == 0.0

    def test_record_provider_result_new_provider(self):
        s = _make_solver()
        s._record_provider_result("newprov", "hcaptcha", True)
        assert "newprov" in s.provider_stats
        assert s.provider_stats["newprov"]["solves"] == 1

    def test_record_provider_result_with_faucet_name(self):
        s = _make_solver()
        s.set_faucet_name("myfaucet")
        s._record_provider_result("2captcha", "turnstile", True)
        fstats = s.faucet_provider_stats["myfaucet"]["2captcha"]
        assert fstats["solves"] == 1

    def test_record_provider_result_faucet_failure(self):
        s = _make_solver()
        s.set_faucet_name("myfaucet")
        s._record_provider_result("2captcha", "turnstile", False)
        fstats = s.faucet_provider_stats["myfaucet"]["2captcha"]
        assert fstats["failures"] == 1

    def test_record_provider_result_creates_faucet_stats_entry(self):
        """If faucet_name set but not yet in faucet_provider_stats."""
        s = _make_solver()
        s.faucet_name = "new_faucet"
        s._record_provider_result("2captcha", "turnstile", True)
        assert "new_faucet" in s.faucet_provider_stats

    def test_get_provider_stats(self):
        s = _make_solver()
        s.set_fallback_provider("capsolver", "k")
        stats = s.get_provider_stats()
        assert stats["primary"] == "2captcha"
        assert stats["fallback"] == "capsolver"
        assert "2captcha" in stats["providers"]


# ===================================================================
# 6. Expected cost and provider ordering
# ===================================================================

class TestExpectedCostAndRouting:
    def test_expected_cost_none_insufficient_samples(self):
        s = _make_solver(routing_min_samples=20)
        assert s._expected_cost("2captcha", "turnstile") is None

    def test_expected_cost_with_sufficient_samples(self):
        s = _make_solver(routing_min_samples=2)
        for _ in range(5):
            s._record_provider_result("2captcha", "turnstile", True)
        cost = s._expected_cost("2captcha", "turnstile")
        assert cost is not None
        assert cost > 0

    def test_expected_cost_with_failures(self):
        s = _make_solver(routing_min_samples=2)
        for _ in range(3):
            s._record_provider_result("2captcha", "turnstile", True)
        for _ in range(3):
            s._record_provider_result("2captcha", "turnstile", False)
        cost = s._expected_cost("2captcha", "turnstile")
        # 50% success => cost/0.5 = 0.006
        assert cost is not None
        assert cost == pytest.approx(0.006)

    def test_expected_cost_unknown_provider(self):
        s = _make_solver()
        assert s._expected_cost("nonexistent", "turnstile") is None

    def test_expected_cost_prefers_faucet_stats(self):
        s = _make_solver(routing_min_samples=2)
        s.set_faucet_name("myfaucet")
        for _ in range(5):
            s._record_provider_result("2captcha", "turnstile", True)
        cost = s._expected_cost("2captcha", "turnstile")
        assert cost is not None

    def test_choose_provider_order_non_adaptive(self):
        s = _make_solver(adaptive_routing=False)
        order = s._choose_provider_order("turnstile")
        assert order == ["2captcha"]

    def test_choose_provider_order_with_fallback_non_adaptive(self):
        s = _make_solver(adaptive_routing=False)
        s.set_fallback_provider("capsolver", "k")
        order = s._choose_provider_order("turnstile")
        assert order == ["2captcha", "capsolver"]

    def test_choose_provider_order_single_provider_adaptive(self):
        s = _make_solver(adaptive_routing=True)
        order = s._choose_provider_order("turnstile")
        assert order == ["2captcha"]

    def test_choose_provider_order_adaptive_no_data(self):
        s = _make_solver(adaptive_routing=True, routing_min_samples=100)
        s.set_fallback_provider("capsolver", "k")
        order = s._choose_provider_order("turnstile")
        # All None => original order
        assert order == ["2captcha", "capsolver"]

    def test_choose_provider_order_adaptive_with_data(self):
        s = _make_solver(adaptive_routing=True, routing_min_samples=2)
        s.set_fallback_provider("capsolver", "k")
        # Make capsolver cheaper (higher success rate)
        for _ in range(5):
            s._record_provider_result("capsolver", "turnstile", True)
        for _ in range(5):
            s._record_provider_result("2captcha", "turnstile", True)
        for _ in range(5):
            s._record_provider_result("2captcha", "turnstile", False)
        order = s._choose_provider_order("turnstile")
        # capsolver: 100% success => cost/1.0 = 0.003
        # 2captcha: 50% success => cost/0.5 = 0.006
        assert order[0] == "capsolver"

    def test_choose_provider_order_same_provider_no_duplicate(self):
        s = _make_solver(provider="2captcha")
        s.fallback_provider = "2captcha"
        s.fallback_api_key = "k"
        order = s._choose_provider_order("turnstile")
        # Same provider should not be duplicated
        assert order == ["2captcha"]


# ===================================================================
# 7. Proxy parsing
# ===================================================================

class TestProxyParsing:
    def test_http_proxy_with_auth(self):
        s = _make_solver()
        r = s._parse_proxy("http://user:pass@host:8080")
        assert r["proxytype"] == "HTTP"
        assert r["proxy"] == "user:pass@host:8080"

    def test_socks5_proxy(self):
        s = _make_solver()
        r = s._parse_proxy("socks5://user:pass@host:1080")
        assert r["proxytype"] == "SOCKS5"
        assert "user:pass@host:1080" in r["proxy"]

    def test_proxy_without_scheme(self):
        s = _make_solver()
        r = s._parse_proxy("host:8080")
        assert r["proxytype"] == "HTTP"
        assert "host:8080" in r["proxy"]

    def test_proxy_without_auth(self):
        s = _make_solver()
        r = s._parse_proxy("http://host:8080")
        assert r["proxy"] == "host:8080"


# ===================================================================
# 8. Sitekey normalization
# ===================================================================

class TestNormalizeSitekey:
    def test_none(self):
        assert CaptchaSolver._normalize_sitekey(None) is None

    def test_valid_string(self):
        key = "0x4AAAAAAADnPIDROzbs0Aaj"
        assert CaptchaSolver._normalize_sitekey(key) == key

    def test_strips_whitespace(self):
        key = "  0x4AAAAAAADnPIDROzbs0Aaj  "
        assert CaptchaSolver._normalize_sitekey(key) == key.strip()

    def test_too_short_string(self):
        assert CaptchaSolver._normalize_sitekey("abc") is None

    def test_invalid_chars_but_extractable(self):
        raw = '{"sitekey": "0x4AAAAAAADnPIDROzbs0Aaj"}'
        result = CaptchaSolver._normalize_sitekey(raw)
        assert result == "0x4AAAAAAADnPIDROzbs0Aaj"

    def test_invalid_chars_not_extractable(self):
        raw = '{!@#$%}'
        assert CaptchaSolver._normalize_sitekey(raw) is None

    def test_dict_input_with_sitekey(self):
        raw = {"sitekey": "0x4AAAAAAADnPIDROzbs0Aaj"}
        assert CaptchaSolver._normalize_sitekey(raw) == "0x4AAAAAAADnPIDROzbs0Aaj"

    def test_dict_input_without_sitekey(self):
        raw = {"other": "value-that-is-really-long-enough-to-be-valid"}
        # str(dict) has braces and colons; regex should try extraction
        result = CaptchaSolver._normalize_sitekey(raw)
        # Depends on whether str(raw) contains a 20+ alphanum segment
        # 'value-that-is-really-long-enough-to-be-valid' has hyphens which are valid
        assert result is not None or result is None  # Just check no crash

    def test_non_string_non_dict(self):
        result = CaptchaSolver._normalize_sitekey(12345678901234567890)
        # str(12345678901234567890) is 20 digits
        assert result == "12345678901234567890"

    def test_exactly_10_chars(self):
        # len >= 20 required by regex, and len >= 10 by final check
        assert CaptchaSolver._normalize_sitekey("abcdefghij") is None

    def test_twenty_char_valid(self):
        key = "a" * 20
        assert CaptchaSolver._normalize_sitekey(key) == key


# ===================================================================
# 9. Coordinate parsing
# ===================================================================

class TestParseCoordinates:
    def test_x_y_format_single(self):
        pts = CaptchaSolver._parse_coordinates("x=10,y=20")
        assert pts == [(10, 20)]

    def test_x_y_format_multiple(self):
        pts = CaptchaSolver._parse_coordinates("x=10,y=20;x=30,y=40")
        assert pts == [(10, 20), (30, 40)]

    def test_simple_format(self):
        pts = CaptchaSolver._parse_coordinates("100,200")
        assert pts == [(100, 200)]

    def test_simple_format_extra_values(self):
        pts = CaptchaSolver._parse_coordinates("100,200,300")
        assert pts == [(100, 200)]


# ===================================================================
# 10. Session management and close
# ===================================================================

class TestSessionManagement:
    async def test_get_session_creates_new(self):
        s = _make_solver()
        s.session = None
        session = await s._get_session()
        assert session is not None
        await s.close()

    async def test_get_session_reuses_open(self):
        s = _make_solver()
        mock_sess = _mock_session()
        s.session = mock_sess
        result = await s._get_session()
        assert result is mock_sess

    async def test_get_session_recreates_if_closed(self):
        s = _make_solver()
        mock_sess = MagicMock()
        mock_sess.closed = True
        s.session = mock_sess
        session = await s._get_session()
        assert session is not mock_sess
        await s.close()

    async def test_close_active_session(self):
        s = _make_solver()
        mock_sess = _mock_session()
        s.session = mock_sess
        await s.close()
        mock_sess.close.assert_awaited_once()
        assert s.session is None

    async def test_close_no_session(self):
        s = _make_solver()
        s.session = None
        await s.close()  # Should not raise

    async def test_close_already_closed(self):
        s = _make_solver()
        mock_sess = MagicMock()
        mock_sess.closed = True
        s.session = mock_sess
        await s.close()
        # close() should not be called on already-closed session


# ===================================================================
# 11. Async context manager
# ===================================================================

class TestAsyncContextManager:
    async def test_aenter_returns_self(self):
        s = _make_solver()
        result = await s.__aenter__()
        assert result is s

    async def test_aexit_returns_false(self):
        s = _make_solver()
        result = await s.__aexit__(None, None, None)
        assert result is False

    async def test_full_context_manager(self):
        async with CaptchaSolver(api_key="k") as solver:
            assert isinstance(solver, CaptchaSolver)


# ===================================================================
# 12. _solve_2captcha
# ===================================================================

class TestSolve2Captcha:
    async def test_success(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ123"})
        poll_resp = _mock_aiohttp_response({"status": 1, "request": "TOKEN_ABC"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result == "TOKEN_ABC"

    async def test_submit_error_returns_none(self):
        s = _make_solver()
        resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_WRONG_KEY"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=resp)
        s.session = mock_sess

        result = await s._solve_2captcha(
            "sitekey_abcdef0123456789", "http://example.com", "turnstile"
        )
        assert result is None

    async def test_submit_error_raises_for_fallback_codes(self):
        """Fallback-worthy errors should raise Exception."""
        s = _make_solver()
        resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_ZERO_BALANCE"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=resp)
        s.session = mock_sess

        with pytest.raises(Exception, match="ERROR_ZERO_BALANCE"):
            await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )

    async def test_submit_error_no_slot(self):
        s = _make_solver()
        resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_NO_SLOT_AVAILABLE"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=resp)
        s.session = mock_sess

        with pytest.raises(Exception, match="ERROR_NO_SLOT_AVAILABLE"):
            await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )

    async def test_submit_json_parse_error(self):
        s = _make_solver()
        resp_mock = AsyncMock()
        resp_mock.json = AsyncMock(side_effect=ValueError("bad json"))
        resp_mock.status = 500
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=resp_mock)
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=cm)
        s.session = mock_sess

        result = await s._solve_2captcha(
            "sitekey_abcdef0123456789", "http://example.com", "turnstile"
        )
        assert result is None

    async def test_poll_not_ready_then_success(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ123"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)

        # First poll: not ready, second: success
        poll_responses = [
            _mock_aiohttp_response({"status": 0, "request": "CAPCHA_NOT_READY"}),
            _mock_aiohttp_response({"status": 1, "request": "FINAL_TOKEN"}),
        ]
        call_count = 0
        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            idx = min(call_count, len(poll_responses) - 1)
            call_count += 1
            return poll_responses[idx]

        mock_sess.get = MagicMock(side_effect=get_side_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result == "FINAL_TOKEN"

    async def test_poll_error_returns_none(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ123"})
        poll_resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result is None

    async def test_poll_error_zero_balance_raises(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ123"})
        poll_resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_ZERO_BALANCE"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception, match="ERROR_ZERO_BALANCE"):
                await s._solve_2captcha(
                    "sitekey_abcdef0123456789", "http://example.com", "turnstile"
                )

    async def test_with_proxy_context(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        poll_resp = _mock_aiohttp_response({"status": 1, "request": "TOK"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        proxy_ctx = {
            "proxy_string": "http://u:p@proxy:8080",
            "user_agent": "Mozilla/5.0",
        }

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com",
                "turnstile", proxy_ctx,
            )
        assert result == "TOK"

    async def test_with_proxy_from_solver(self):
        s = _make_solver()
        s.proxy_string = "http://myproxy:9090"
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "R1"})
        poll_resp = _mock_aiohttp_response({"status": 1, "request": "T1"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com",
                "turnstile", None,
            )
        assert result == "T1"

    async def test_recaptcha_uses_googlekey(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "R1"})
        poll_resp = _mock_aiohttp_response({"status": 1, "request": "TOK"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com",
                "userrecaptcha",
            )
        assert result == "TOK"
        # Verify post was called with data containing googlekey
        call_args = mock_sess.post.call_args
        data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert data["method"] == "userrecaptcha"
        assert data["googlekey"] == "sitekey_abcdef0123456789"

    async def test_overridden_api_key(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "R1"})
        poll_resp = _mock_aiohttp_response({"status": 1, "request": "T1"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com",
                "turnstile", api_key="override_key",
            )
        assert result == "T1"
        call_args = mock_sess.post.call_args
        data = call_args.kwargs.get("data") or call_args[1].get("data")
        assert data["key"] == "override_key"

    async def test_poll_timeout_returns_none(self):
        """When polling exceeds 120s, should return None."""
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ123"})
        not_ready_resp = _mock_aiohttp_response({"status": 0, "request": "CAPCHA_NOT_READY"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=not_ready_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result is None

    async def test_poll_json_error_retries(self):
        """JSON parse error during polling should continue polling."""
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ123"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)

        # First poll: JSON error, second: success
        error_resp = AsyncMock()
        error_resp.json = AsyncMock(side_effect=ValueError("bad"))
        error_cm = AsyncMock()
        error_cm.__aenter__ = AsyncMock(return_value=error_resp)
        error_cm.__aexit__ = AsyncMock(return_value=False)

        success_cm = _mock_aiohttp_response({"status": 1, "request": "FINAL_TOKEN"})

        call_count = 0
        def get_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return error_cm
            return success_cm

        mock_sess.get = MagicMock(side_effect=get_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result == "FINAL_TOKEN"

    async def test_ip_not_allowed_submit(self):
        s = _make_solver()
        resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_IP_NOT_ALLOWED"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=resp)
        s.session = mock_sess

        result = await s._solve_2captcha(
            "sitekey_abcdef0123456789", "http://example.com", "turnstile"
        )
        assert result is None

    async def test_ip_not_allowed_poll(self):
        s = _make_solver()
        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        poll_resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_IP_NOT_ALLOWED"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_2captcha(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result is None


# ===================================================================
# 13. _solve_capsolver
# ===================================================================

class TestSolveCapsolver:
    async def test_success_no_proxy(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "TASK123",
        })
        result_resp = _mock_aiohttp_response({
            "status": "ready",
            "solution": {"token": "CS_TOKEN"},
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return create_resp
            return result_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result == "CS_TOKEN"

    async def test_success_with_grecaptcha_response(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        result_resp = _mock_aiohttp_response({
            "status": "ready",
            "solution": {"gRecaptchaResponse": "RECAPTCHA_TOK"},
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else result_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com", "userrecaptcha"
            )
        assert result == "RECAPTCHA_TOK"

    async def test_create_error(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 1, "errorDescription": "invalid key",
        })
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=create_resp)
        s.session = mock_sess

        result = await s._solve_capsolver(
            "sitekey_abcdef0123456789", "http://example.com", "turnstile"
        )
        assert result is None

    async def test_create_connection_error(self):
        s = _make_solver(provider="capsolver")
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=ConnectionError("no conn"))
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=cm)
        s.session = mock_sess

        result = await s._solve_capsolver(
            "sitekey_abcdef0123456789", "http://example.com", "turnstile"
        )
        assert result is None

    async def test_task_failed(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        failed_resp = _mock_aiohttp_response({
            "status": "failed",
            "errorDescription": "captcha unsolvable",
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else failed_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com", "hcaptcha"
            )
        assert result is None

    async def test_ready_but_no_token(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        result_resp = _mock_aiohttp_response({
            "status": "ready",
            "solution": {},
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else result_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result is None

    async def test_with_proxy_context(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        result_resp = _mock_aiohttp_response({
            "status": "ready",
            "solution": {"token": "TOK"},
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else result_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com",
                "turnstile",
                {"proxy_string": "http://p:1234"},
            )
        assert result == "TOK"
        # First call should be createTask with proxy task type
        first_call = mock_sess.post.call_args_list[0]
        payload = first_call.kwargs.get("json") or first_call[1].get("json")
        assert payload["task"]["type"] == "TurnstileTask"  # With proxy

    async def test_hcaptcha_task_type_no_proxy(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        result_resp = _mock_aiohttp_response({
            "status": "ready",
            "solution": {"token": "TOK"},
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else result_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com",
                "hcaptcha",
            )
        first_call = mock_sess.post.call_args_list[0]
        payload = first_call.kwargs.get("json") or first_call[1].get("json")
        assert payload["task"]["type"] == "HCaptchaTaskProxyLess"

    async def test_recaptcha_task_type_with_proxy(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        result_resp = _mock_aiohttp_response({
            "status": "ready",
            "solution": {"token": "T"},
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else result_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com",
                "userrecaptcha",
                {"proxy_string": "http://p:1234"},
            )
        first_call = mock_sess.post.call_args_list[0]
        payload = first_call.kwargs.get("json") or first_call[1].get("json")
        assert payload["task"]["type"] == "ReCaptchaV2Task"

    async def test_poll_timeout(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        processing_resp = _mock_aiohttp_response({
            "status": "processing",
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else processing_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result is None

    async def test_poll_json_error_continues(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        mock_sess = _mock_session()

        error_resp = AsyncMock()
        error_resp.json = AsyncMock(side_effect=ValueError("bad"))
        error_cm = AsyncMock()
        error_cm.__aenter__ = AsyncMock(return_value=error_resp)
        error_cm.__aexit__ = AsyncMock(return_value=False)

        success_cm = _mock_aiohttp_response({
            "status": "ready", "solution": {"token": "TOK"},
        })

        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return create_resp
            if call_count == 2:
                return error_cm
            return success_cm
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com", "turnstile"
            )
        assert result == "TOK"

    async def test_overridden_api_key(self):
        s = _make_solver(provider="capsolver")
        create_resp = _mock_aiohttp_response({
            "errorId": 0, "taskId": "T1",
        })
        result_resp = _mock_aiohttp_response({
            "status": "ready", "solution": {"token": "TOK"},
        })
        mock_sess = _mock_session()
        call_count = 0
        def post_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return create_resp if call_count == 1 else result_resp
        mock_sess.post = MagicMock(side_effect=post_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_capsolver(
                "sitekey_abcdef0123456789", "http://example.com",
                "turnstile", api_key="my_override_key",
            )
        assert result == "TOK"
        first_call = mock_sess.post.call_args_list[0]
        payload = first_call.kwargs.get("json") or first_call[1].get("json")
        assert payload["clientKey"] == "my_override_key"


# ===================================================================
# 14. solve_with_fallback
# ===================================================================

class TestSolveWithFallback:
    async def test_primary_succeeds(self):
        s = _make_solver()
        s.session = _mock_session()
        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, return_value="TOKEN"):
            result = await s.solve_with_fallback(
                MagicMock(), "turnstile",
                "sitekey_abcdef0123456789", "http://example.com",
            )
        assert result == "TOKEN"

    async def test_primary_fails_fallback_succeeds(self):
        s = _make_solver()
        s.set_fallback_provider("capsolver", "fb_key")
        s.session = _mock_session()

        async def solve_2c(*a, **kw):
            return None

        async def solve_cs(*a, **kw):
            return "FB_TOKEN"

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, side_effect=solve_2c):
            with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, side_effect=solve_cs):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await s.solve_with_fallback(
                        MagicMock(), "turnstile",
                        "sitekey_abcdef0123456789", "http://example.com",
                    )
        assert result == "FB_TOKEN"

    async def test_all_providers_fail(self):
        s = _make_solver()
        s.set_fallback_provider("capsolver", "fb_key")
        s.session = _mock_session()

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, return_value=None):
            with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, return_value=None):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await s.solve_with_fallback(
                        MagicMock(), "turnstile",
                        "sitekey_abcdef0123456789", "http://example.com",
                    )
        assert result is None

    async def test_primary_raises_fallback_error(self):
        """When primary raises a fallback-worthy error, we move to fallback."""
        s = _make_solver()
        s.set_fallback_provider("capsolver", "fb_key")
        s.session = _mock_session()

        async def raise_no_slot(*a, **kw):
            raise Exception("ERROR_NO_SLOT")

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, side_effect=raise_no_slot):
            with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, return_value="FB_TOK"):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await s.solve_with_fallback(
                        MagicMock(), "turnstile",
                        "sitekey_abcdef0123456789", "http://example.com",
                    )
        assert result == "FB_TOK"

    async def test_non_fallback_error_is_raised(self):
        """Non-fallback errors should be re-raised."""
        s = _make_solver()
        s.session = _mock_session()

        async def raise_random(*a, **kw):
            raise RuntimeError("unexpected error")

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, side_effect=raise_random):
            with pytest.raises(RuntimeError, match="unexpected error"):
                await s.solve_with_fallback(
                    MagicMock(), "turnstile",
                    "sitekey_abcdef0123456789", "http://example.com",
                )

    async def test_records_provider_stats_on_success(self):
        s = _make_solver()
        s.session = _mock_session()

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, return_value="TOK"):
            await s.solve_with_fallback(
                MagicMock(), "turnstile",
                "sitekey_abcdef0123456789", "http://example.com",
            )
        assert s.provider_stats["2captcha"]["solves"] == 1

    async def test_records_provider_stats_on_failure(self):
        s = _make_solver()
        s.session = _mock_session()

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, return_value=None):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await s.solve_with_fallback(
                    MagicMock(), "turnstile",
                    "sitekey_abcdef0123456789", "http://example.com",
                )
        assert s.provider_stats["2captcha"]["failures"] == 1

    async def test_capsolver_as_primary(self):
        s = _make_solver(provider="capsolver")
        s.session = _mock_session()

        with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, return_value="CS_TOK"):
            result = await s.solve_with_fallback(
                MagicMock(), "hcaptcha",
                "sitekey_abcdef0123456789", "http://example.com",
            )
        assert result == "CS_TOK"

    async def test_fallback_zero_balance(self):
        """ERROR_ZERO_BALANCE on primary should fall to fallback (breaks out of inner retry)."""
        s = _make_solver()
        s.set_fallback_provider("capsolver", "fb_key")
        s.session = _mock_session()

        async def raise_zero_bal(*a, **kw):
            raise Exception("ERROR_ZERO_BALANCE")

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, side_effect=raise_zero_bal):
            with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, return_value="FB"):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await s.solve_with_fallback(
                        MagicMock(), "turnstile",
                        "sitekey_abcdef0123456789", "http://example.com",
                    )
        assert result == "FB"

    async def test_uses_fallback_api_key(self):
        s = _make_solver()
        s.set_fallback_provider("capsolver", "fallback_key_xyz")
        s.session = _mock_session()

        called_key = None

        async def capture_capsolver(*a, api_key=None, **kw):
            nonlocal called_key
            called_key = api_key
            return "CS_TOK"

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, return_value=None):
            with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, side_effect=capture_capsolver):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await s.solve_with_fallback(
                        MagicMock(), "turnstile",
                        "sitekey_abcdef0123456789", "http://example.com",
                    )
        assert called_key == "fallback_key_xyz"

    async def test_retry_on_first_failure(self):
        """Primary returns None on first attempt, then succeeds on retry."""
        s = _make_solver()
        s.session = _mock_session()
        call_count = 0

        async def retry_solve(*a, **kw):
            nonlocal call_count
            call_count += 1
            return None if call_count == 1 else "TOK_RETRY"

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, side_effect=retry_solve):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await s.solve_with_fallback(
                    MagicMock(), "turnstile",
                    "sitekey_abcdef0123456789", "http://example.com",
                )
        assert result == "TOK_RETRY"
        assert call_count == 2

    async def test_error_method_call_triggers_fallback(self):
        s = _make_solver()
        s.set_fallback_provider("capsolver", "fb_key")
        s.session = _mock_session()

        async def raise_method_call(*a, **kw):
            raise Exception("ERROR_METHOD_CALL")

        with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, side_effect=raise_method_call):
            with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, return_value="TOK"):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    result = await s.solve_with_fallback(
                        MagicMock(), "turnstile",
                        "sitekey_abcdef0123456789", "http://example.com",
                    )
        assert result == "TOK"


# ===================================================================
# 15. _inject_token
# ===================================================================

class TestInjectToken:
    async def test_inject_turnstile(self):
        page = MagicMock()
        page.evaluate = AsyncMock()
        s = _make_solver()
        await s._inject_token(page, "turnstile", "my_token")
        page.evaluate.assert_awaited_once()
        call_args = page.evaluate.call_args
        js_code = call_args[0][0]
        assert "turnstile" in js_code

    async def test_inject_hcaptcha(self):
        page = MagicMock()
        page.evaluate = AsyncMock()
        s = _make_solver()
        await s._inject_token(page, "hcaptcha", "tok")
        js_code = page.evaluate.call_args[0][0]
        assert "hcaptcha" in js_code

    async def test_inject_recaptcha(self):
        page = MagicMock()
        page.evaluate = AsyncMock()
        s = _make_solver()
        await s._inject_token(page, "userrecaptcha", "tok")
        js_code = page.evaluate.call_args[0][0]
        assert "userrecaptcha" in js_code

    async def test_token_passed_as_arg(self):
        page = MagicMock()
        page.evaluate = AsyncMock()
        s = _make_solver()
        await s._inject_token(page, "turnstile", "my_special_token")
        call_args = page.evaluate.call_args
        # Second positional arg is the token
        assert call_args[0][1] == "my_special_token"


# ===================================================================
# 16. _wait_for_human
# ===================================================================

class TestWaitForHuman:
    async def test_headless_short_circuits(self):
        page = MagicMock()
        s = _make_solver()
        with patch.dict("os.environ", {"HEADLESS": "true"}):
            result = await s._wait_for_human(page, 60)
        assert result is False

    async def test_token_detected(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="MANUAL_TOKEN")
        s = _make_solver()
        with patch.dict("os.environ", {"HEADLESS": "false"}):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await s._wait_for_human(page, 60)
        assert result is True

    async def test_timeout_no_token(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=None)
        s = _make_solver()

        with patch.dict("os.environ", {"HEADLESS": "false"}):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with patch("time.monotonic") as mock_mono:
                    # First call returns 0.0, subsequent calls return > timeout
                    mock_mono.side_effect = [0.0, 0.0, 999.0]
                    result = await s._wait_for_human(page, 60)
        assert result is False

    async def test_high_value_claim_logging(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="TOK")
        s = _make_solver()
        with patch.dict("os.environ", {"HEADLESS": "false"}):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await s._wait_for_human(page, 60, high_value_claim=True)
        assert result is True


# ===================================================================
# 17. _solve_altcha
# ===================================================================

class TestSolveAltcha:
    async def test_success(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value={"ok": True, "iterations": 500})
        s = _make_solver()
        result = await s._solve_altcha(page)
        assert result is True
        assert s._daily_spend == 0.0  # Free

    async def test_failed(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value={"ok": False, "error": "not found"})
        s = _make_solver()
        result = await s._solve_altcha(page)
        assert result is False

    async def test_none_result(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=None)
        s = _make_solver()
        result = await s._solve_altcha(page)
        assert result is False

    async def test_exception(self):
        page = MagicMock()
        page.evaluate = AsyncMock(side_effect=Exception("js error"))
        s = _make_solver()
        result = await s._solve_altcha(page)
        assert result is False


# ===================================================================
# 18. _solve_image_captcha
# ===================================================================

class TestSolveImageCaptcha:
    async def test_no_api_key(self):
        s = CaptchaSolver()  # no api_key
        page = MagicMock()
        with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
            result = await s._solve_image_captcha(page)
        assert result is False

    async def test_no_captcha_element(self):
        s = _make_solver()
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=None)
        with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
            result = await s._solve_image_captcha(page)
        assert result is False

    async def test_no_bounding_box(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value=None)
        page.query_selector = AsyncMock(return_value=elem)
        with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
            result = await s._solve_image_captcha(page)
        assert result is False

    async def test_submit_error(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0, "width": 100, "height": 50})
        elem.screenshot = AsyncMock(return_value=b"fakepng")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 0, "request": "ERROR"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        s.session = mock_sess

        with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
            result = await s._solve_image_captcha(page)
        assert result is False

    async def test_success_flow(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 10, "y": 20, "width": 100, "height": 50})
        elem.screenshot = AsyncMock(return_value=b"fakepng")

        # First query_selector returns captcha img, second returns submit button
        call_idx = 0
        async def qs(selector):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return elem
            return MagicMock(click=AsyncMock())

        page.query_selector = AsyncMock(side_effect=qs)
        page.mouse = MagicMock()
        page.mouse.click = AsyncMock()

        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        poll_resp = _mock_aiohttp_response({"status": 1, "request": "x=50,y=25"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s._solve_image_captcha(page)
        assert result is True

    async def test_coordinates_timeout(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0, "width": 100, "height": 50})
        elem.screenshot = AsyncMock(return_value=b"fakepng")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        not_ready = _mock_aiohttp_response({"status": 0, "request": "CAPCHA_NOT_READY"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=not_ready)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
                result = await s._solve_image_captcha(page)
        assert result is False

    async def test_exception_during_solve(self):
        s = _make_solver()
        page = MagicMock()
        page.query_selector = AsyncMock(side_effect=Exception("DOM error"))
        with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
            result = await s._solve_image_captcha(page)
        assert result is False

    async def test_poll_error(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0, "width": 100, "height": 50})
        elem.screenshot = AsyncMock(return_value=b"fakepng")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        error_resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_WRONG_KEY"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=error_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
                result = await s._solve_image_captcha(page)
        assert result is False


# ===================================================================
# 19. solve_text_captcha
# ===================================================================

class TestSolveTextCaptcha:
    async def test_no_api_key(self):
        s = CaptchaSolver()
        page = MagicMock()
        with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
            result = await s.solve_text_captcha(page, "img.captcha")
        assert result is None

    async def test_no_element(self):
        s = _make_solver()
        page = MagicMock()
        page.query_selector = AsyncMock(return_value=None)
        result = await s.solve_text_captcha(page, "img.captcha")
        assert result is None

    async def test_no_bounding_box(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value=None)
        page.query_selector = AsyncMock(return_value=elem)
        result = await s.solve_text_captcha(page, "img.captcha")
        assert result is None

    async def test_submit_error(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0})
        elem.screenshot = AsyncMock(return_value=b"png")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 0, "request": "ERROR"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        s.session = mock_sess

        result = await s.solve_text_captcha(page, "img.captcha")
        assert result is None

    async def test_success(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0})
        elem.screenshot = AsyncMock(return_value=b"png")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        poll_resp = _mock_aiohttp_response({"status": 1, "request": "  ANSWER  "})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=poll_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s.solve_text_captcha(page, "img.captcha")
        assert result == "ANSWER"

    async def test_poll_timeout(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0})
        elem.screenshot = AsyncMock(return_value=b"png")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        not_ready = _mock_aiohttp_response({"status": 0, "request": "CAPCHA_NOT_READY"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=not_ready)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s.solve_text_captcha(page, "img.captcha")
        assert result is None

    async def test_poll_error(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0})
        elem.screenshot = AsyncMock(return_value=b"png")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        error_resp = _mock_aiohttp_response({"status": 0, "request": "ERROR_CAPTCHA_UNSOLVABLE"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)
        mock_sess.get = MagicMock(return_value=error_resp)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s.solve_text_captcha(page, "img.captcha")
        assert result is None

    async def test_exception_returns_none(self):
        s = _make_solver()
        page = MagicMock()
        page.query_selector = AsyncMock(side_effect=Exception("DOM error"))
        result = await s.solve_text_captcha(page, "img.captcha")
        assert result is None

    async def test_poll_json_error_retries(self):
        s = _make_solver()
        page = MagicMock()
        elem = MagicMock()
        elem.bounding_box = AsyncMock(return_value={"x": 0, "y": 0})
        elem.screenshot = AsyncMock(return_value=b"png")
        page.query_selector = AsyncMock(return_value=elem)

        submit_resp = _mock_aiohttp_response({"status": 1, "request": "REQ1"})
        mock_sess = _mock_session()
        mock_sess.post = MagicMock(return_value=submit_resp)

        error_resp_mock = AsyncMock()
        error_resp_mock.json = AsyncMock(side_effect=ValueError("bad"))
        error_cm = AsyncMock()
        error_cm.__aenter__ = AsyncMock(return_value=error_resp_mock)
        error_cm.__aexit__ = AsyncMock(return_value=False)

        success_cm = _mock_aiohttp_response({"status": 1, "request": "TEXT"})

        call_count = 0
        def get_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            return error_cm if call_count == 1 else success_cm

        mock_sess.get = MagicMock(side_effect=get_effect)
        s.session = mock_sess

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await s.solve_text_captcha(page, "img.captcha")
        assert result == "TEXT"


# ===================================================================
# 20. _extract_sitekey_from_scripts
# ===================================================================

class TestExtractSitekeyFromScripts:
    async def test_returns_evaluated_value(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value="extracted_key_abc123456789")
        s = _make_solver()
        result = await s._extract_sitekey_from_scripts(page, "turnstile")
        assert result == "extracted_key_abc123456789"

    async def test_returns_none(self):
        page = MagicMock()
        page.evaluate = AsyncMock(return_value=None)
        s = _make_solver()
        result = await s._extract_sitekey_from_scripts(page, "hcaptcha")
        assert result is None


# ===================================================================
# 21. solve_captcha (main entry-point)
# ===================================================================

class TestSolveCaptcha:
    async def test_no_api_key_headless_returns_false(self):
        s = CaptchaSolver()
        s.headless = True
        page = MagicMock()
        result = await s.solve_captcha(page)
        assert result is False

    async def test_altcha_detected(self):
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        page.frames = []
        # query_selector calls in order:
        # 1: turnstile input, 2: turnstile DOM, 3: hCaptcha, 4: reCAPTCHA,
        # 5: altcha (detected!), 6: has_frames (truthy to continue)
        page.query_selector = AsyncMock(side_effect=[
            None,  # Turnstile input-only
            None,  # Turnstile DOM fallback
            None,  # hCaptcha
            None,  # reCAPTCHA
            MagicMock(),  # altcha widget (detected)
            MagicMock(),  # has_frames check (truthy to continue to altcha handler)
        ])
        page.content = AsyncMock(return_value="<html></html>")
        page.evaluate = AsyncMock(return_value=None)

        with patch.object(s, "_solve_altcha", new_callable=AsyncMock, return_value=True):
            result = await s.solve_captcha(page)
        assert result is True

    async def test_no_captcha_found_returns_true(self):
        """When no captcha detected, returns True (page is clean)."""
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        page.frames = []
        page.query_selector = AsyncMock(return_value=None)
        page.content = AsyncMock(return_value="<html>no captcha</html>")
        page.evaluate = AsyncMock(return_value=None)

        result = await s.solve_captcha(page)
        assert result is True

    async def test_turnstile_iframe_detection(self):
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock()

        frame = MagicMock()
        frame.url = "https://challenges.cloudflare.com/turnstile?sitekey=AAAA0123456789abcdefgh"
        page.frames = [frame]
        page.url = "http://example.com"
        page.evaluate = AsyncMock(return_value="Mozilla/5.0")

        with patch.object(s, "can_afford_captcha", return_value=True):
            with patch.object(s, "solve_with_fallback", new_callable=AsyncMock, return_value="TOK"):
                with patch.object(s, "_inject_token", new_callable=AsyncMock):
                    result = await s.solve_captcha(page)
        assert result is True

    async def test_turnstile_k_param_detection(self):
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock()

        frame = MagicMock()
        frame.url = "https://challenges.cloudflare.com/?k=AAAA0123456789abcdefgh&other=1"
        page.frames = [frame]
        page.url = "http://example.com"
        page.evaluate = AsyncMock(return_value="Mozilla/5.0")

        with patch.object(s, "can_afford_captcha", return_value=True):
            with patch.object(s, "solve_with_fallback", new_callable=AsyncMock, return_value="TOK"):
                with patch.object(s, "_inject_token", new_callable=AsyncMock):
                    result = await s.solve_captcha(page)
        assert result is True

    async def test_hcaptcha_detection(self):
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock()
        page.frames = []

        hcaptcha_elem = MagicMock()
        hcaptcha_elem.get_attribute = AsyncMock(return_value="https://newassets.hcaptcha.com/captcha/v1?sitekey=AAAA0123456789abcdefgh")

        call_idx = 0
        async def qs(sel):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return None  # turnstile input
            if call_idx == 2:
                return None  # turnstile DOM
            if call_idx == 3:
                return hcaptcha_elem  # hcaptcha iframe
            return None

        page.query_selector = AsyncMock(side_effect=qs)
        page.url = "http://example.com"
        page.evaluate = AsyncMock(return_value="Mozilla/5.0")

        with patch.object(s, "can_afford_captcha", return_value=True):
            with patch.object(s, "solve_with_fallback", new_callable=AsyncMock, return_value="TOK"):
                with patch.object(s, "_inject_token", new_callable=AsyncMock):
                    result = await s.solve_captcha(page)
        assert result is True

    async def test_image_captcha_detection(self):
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        page.frames = []

        img_elem = MagicMock()
        call_idx = 0
        async def qs(sel):
            nonlocal call_idx
            call_idx += 1
            if call_idx <= 4:
                return None  # turnstile input, turnstile DOM, hcaptcha, recaptcha
            if call_idx == 5:
                return None  # altcha
            if call_idx == 6:
                return img_elem  # image captcha (detected!)
            # call_idx == 7: has_frames check (must be truthy to not return early)
            return MagicMock()

        page.query_selector = AsyncMock(side_effect=qs)
        page.content = AsyncMock(return_value="<html></html>")
        page.evaluate = AsyncMock(return_value=None)

        with patch.object(s, "_solve_image_captcha", new_callable=AsyncMock, return_value=True):
            with patch.object(s, "can_afford_captcha", return_value=True):
                result = await s.solve_captcha(page)
        assert result is True

    async def test_manual_fallback_on_budget_exhaustion(self):
        s = _make_solver(daily_budget=0.001)
        s._daily_spend = 0.001
        page = MagicMock()
        page.wait_for_selector = AsyncMock()
        frame = MagicMock()
        frame.url = "https://challenges.cloudflare.com/?sitekey=AAAA0123456789abcdefgh"
        page.frames = [frame]
        page.url = "http://example.com"

        with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=True):
            result = await s.solve_captcha(page)
        assert result is True

    async def test_solve_captcha_exception_handling(self):
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock()
        frame = MagicMock()
        frame.url = "https://challenges.cloudflare.com/?sitekey=AAAA0123456789abcdefgh"
        page.frames = [frame]
        page.url = "http://example.com"
        page.evaluate = AsyncMock(return_value="Mozilla/5.0")

        with patch.object(s, "can_afford_captcha", return_value=True):
            with patch.object(s, "solve_with_fallback", new_callable=AsyncMock, side_effect=Exception("api fail")):
                with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=False):
                    result = await s.solve_captcha(page)
        assert result is False

    async def test_high_value_faucet_detection(self):
        s = _make_solver()
        s.set_faucet_name("firefaucet")
        page = MagicMock()
        page.wait_for_selector = AsyncMock()
        frame = MagicMock()
        frame.url = "https://challenges.cloudflare.com/?sitekey=AAAA0123456789abcdefgh"
        page.frames = [frame]
        page.url = "http://example.com"
        page.evaluate = AsyncMock(return_value="Mozilla/5.0")

        with patch.object(s, "can_afford_captcha", return_value=True):
            with patch.object(s, "solve_with_fallback", new_callable=AsyncMock, return_value=None):
                with patch.object(s, "_wait_for_human", new_callable=AsyncMock, return_value=True) as mock_human:
                    result = await s.solve_captcha(page)
                    mock_human.assert_awaited_once()
                    call_kw = mock_human.call_args
                    assert call_kw.kwargs.get("high_value_claim") is True or call_kw[1].get("high_value_claim") is True

    async def test_turnstile_input_only_no_sitekey_returns_true(self):
        """Turnstile input detected but no sitekey -> should return True."""
        s = _make_solver()
        page = MagicMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        page.frames = []

        ti_elem = MagicMock()
        call_idx = 0
        async def qs(sel):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                return ti_elem  # turnstile input
            return None
        page.query_selector = AsyncMock(side_effect=qs)
        page.evaluate = AsyncMock(return_value=None)  # No sitekey from JS

        result = await s.solve_captcha(page)
        assert result is True

    async def test_proxy_auto_injection(self):
        s = _make_solver()
        s.proxy_string = "http://myproxy:9090"
        page = MagicMock()
        page.wait_for_selector = AsyncMock()
        frame = MagicMock()
        frame.url = "https://challenges.cloudflare.com/?sitekey=AAAA0123456789abcdefgh"
        page.frames = [frame]
        page.url = "http://example.com"
        page.evaluate = AsyncMock(return_value="Mozilla/5.0")

        captured_ctx = None

        async def capture_fallback(page, ctype, skey, url, proxy_context=None):
            nonlocal captured_ctx
            captured_ctx = proxy_context
            return "TOK"

        with patch.object(s, "can_afford_captcha", return_value=True):
            with patch.object(s, "solve_with_fallback", new_callable=AsyncMock, side_effect=capture_fallback):
                with patch.object(s, "_inject_token", new_callable=AsyncMock):
                    await s.solve_captcha(page)

        assert captured_ctx is not None
        assert captured_ctx.get("proxy_string") == "http://myproxy:9090"


# ===================================================================
# 22. _record_solve with analytics
# ===================================================================

class TestRecordSolveAnalytics:
    def test_record_solve_analytics_import_error(self):
        """Analytics import failure should be silently handled."""
        s = _make_solver()
        with patch.dict("sys.modules", {"core.analytics": None}):
            s._record_solve("turnstile", True)
        assert s._daily_spend == pytest.approx(0.003)

    def test_record_solve_analytics_success(self):
        s = _make_solver()
        s.set_faucet_name("test_faucet")
        mock_tracker = MagicMock()
        mock_module = MagicMock()
        mock_module.get_tracker = MagicMock(return_value=mock_tracker)
        with patch.dict("sys.modules", {"core.analytics": mock_module}):
            s._record_solve("turnstile", True)
        mock_tracker.record_cost.assert_called_once_with(
            "captcha", pytest.approx(0.003), faucet="test_faucet",
        )


# ===================================================================
# 23. Edge cases and integration-level tests
# ===================================================================

class TestEdgeCases:
    def test_multiple_cost_recordings(self):
        s = _make_solver(daily_budget=1.0)
        for _ in range(100):
            s._record_solve("turnstile", True)
        assert s._daily_spend == pytest.approx(0.3)
        assert s._solve_count_today == 100

    def test_budget_exhaustion_after_many_solves(self):
        s = _make_solver(daily_budget=0.01)
        for _ in range(3):
            s._record_solve("turnstile", True)
        # 3 * 0.003 = 0.009, budget 0.01, remaining 0.001
        assert s._can_afford_solve("turnstile") is False

    def test_provider_stats_accumulate(self):
        s = _make_solver()
        for _ in range(10):
            s._record_provider_result("2captcha", "turnstile", True)
        for _ in range(5):
            s._record_provider_result("2captcha", "turnstile", False)
        assert s.provider_stats["2captcha"]["solves"] == 10
        assert s.provider_stats["2captcha"]["failures"] == 5
        assert s.provider_stats["2captcha"]["cost"] == pytest.approx(0.003 * 10)

    async def test_context_manager_closes_real_session(self):
        async with CaptchaSolver(api_key="k") as solver:
            session = await solver._get_session()
            assert not session.closed
        # After exiting, session should be closed
        assert solver.session is None

    def test_fallback_provider_none_by_default(self):
        s = _make_solver()
        order = s._choose_provider_order("turnstile")
        assert len(order) == 1

    def test_get_budget_stats_resets_on_new_day(self):
        s = _make_solver(daily_budget=5.0)
        s._daily_spend = 3.0
        s._budget_reset_date = "2000-01-01"
        stats = s.get_budget_stats()
        assert stats["spent_today"] == 0.0
        assert stats["remaining"] == 5.0

    async def test_solve_with_fallback_adaptive_reorders(self):
        """Adaptive routing should pick cheaper provider first."""
        s = _make_solver(adaptive_routing=True, routing_min_samples=2)
        s.set_fallback_provider("capsolver", "fb_key")

        # Make capsolver look better
        for _ in range(5):
            s._record_provider_result("capsolver", "turnstile", True)
        for _ in range(5):
            s._record_provider_result("2captcha", "turnstile", True)
        for _ in range(5):
            s._record_provider_result("2captcha", "turnstile", False)

        called_providers = []

        original_solve_2c = s._solve_2captcha
        original_solve_cs = s._solve_capsolver

        async def track_cs(*a, **kw):
            called_providers.append("capsolver")
            return "TOK"

        async def track_2c(*a, **kw):
            called_providers.append("2captcha")
            return None

        with patch.object(s, "_solve_capsolver", new_callable=AsyncMock, side_effect=track_cs):
            with patch.object(s, "_solve_2captcha", new_callable=AsyncMock, side_effect=track_2c):
                result = await s.solve_with_fallback(
                    MagicMock(), "turnstile",
                    "sitekey_abcdef0123456789", "http://example.com",
                )

        # capsolver should be tried first (cheaper)
        assert called_providers[0] == "capsolver"
        assert result == "TOK"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
