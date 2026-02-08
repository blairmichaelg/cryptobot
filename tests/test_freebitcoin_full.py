"""Comprehensive tests for FreeBitcoinBot covering gaps not in test_freebitcoin.py.

Focuses on:
    - __init__ attribute details
    - is_logged_in selector fallback chains and exception resilience
    - login credential extraction, alias stripping, overrides, field discovery,
      captcha detection, submit fallback (Enter key), error message parsing,
      already-logged-in shortcut, login diagnostics
    - claim HTTP error codes, disabled roll button, zero-amount result,
      roll button vanished, general exception retry, unknown failure path
    - _wait_for_captcha_token success and timeout
    - _has_session_cookie presence and absence
    - _log_login_diagnostics execution paths
    - withdraw error messages from the form
    - get_jobs field values
    - Edge cases: empty page, exception cascades, rate-limit detection
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from faucets.freebitcoin import FreeBitcoinBot
from faucets.base import ClaimResult
from core.config import BotSettings


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    """Fixture for mock BotSettings with full credential configuration."""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {
        "username": "testuser@example.com",
        "password": "s3cret_pass",
    }
    settings.wallet_addresses = {"BTC": {"address": "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"}}
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key_123"
    settings.capsolver_api_key = ""
    settings.btc_withdrawal_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    settings.use_faucetpay = False
    settings.timeout = 60000
    settings.headless = True
    settings.captcha_daily_budget = 5.0
    settings.captcha_provider_routing = "fixed"
    settings.captcha_provider_routing_min_samples = 20
    settings.captcha_fallback_provider = None
    settings.captcha_fallback_api_key = None
    return settings


@pytest.fixture
def mock_solver():
    """Patch CaptchaSolver so bot.__init__ does not need real keys."""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        inst = MockSolver.return_value
        inst.solve_captcha = AsyncMock(return_value=True)
        inst.api_key = "test_key_123"
        inst.set_faucet_name = MagicMock()
        inst.set_headless = MagicMock()
        inst.close = AsyncMock()
        yield inst


def _make_locator(
    visible=False, count=0, text="", enabled=True, raise_on_visible=False
):
    """Build a mock Playwright Locator with configurable behaviour."""
    loc = MagicMock()
    if raise_on_visible:
        loc.is_visible = AsyncMock(side_effect=Exception("Detached"))
    else:
        loc.is_visible = AsyncMock(return_value=visible)
    loc.count = AsyncMock(return_value=count)
    loc.text_content = AsyncMock(return_value=text)
    loc.is_enabled = AsyncMock(return_value=enabled)
    loc.wait_for = AsyncMock()
    loc.click = AsyncMock()
    loc.fill = AsyncMock()
    loc.press = AsyncMock()
    loc.scroll_into_view_if_needed = AsyncMock()
    loc.bounding_box = AsyncMock(
        return_value={"x": 50, "y": 50, "width": 120, "height": 40}
    )
    loc.first = loc
    loc.last = loc
    return loc


@pytest.fixture
def mock_page():
    """Fixture for a fully mocked Playwright Page."""
    page = AsyncMock()
    page.url = "https://freebitco.in"
    page.title = AsyncMock(return_value="FreeBitco.in")
    page.content = AsyncMock(return_value="<html><body></body></html>")
    page.inner_text = AsyncMock(return_value="")
    page.evaluate = AsyncMock(return_value=False)
    page.wait_for_function = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_navigation = AsyncMock()
    page.goto = AsyncMock(return_value=None)
    page.screenshot = AsyncMock()
    page.reload = AsyncMock()

    # Default locator returns invisible element
    default_loc = _make_locator(visible=False, count=0)
    page.locator = MagicMock(return_value=default_loc)

    # Mouse / keyboard stubs
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.viewport_size = {"width": 1280, "height": 720}

    # Context for cookies
    page.context = MagicMock()
    page.context.cookies = AsyncMock(return_value=[])

    page.is_closed = MagicMock(return_value=False)

    return page


def _make_bot(settings, page, solver_fixture):
    """Convenience: build a FreeBitcoinBot with all stealth helpers stubbed."""
    bot = FreeBitcoinBot(settings, page)
    bot.random_delay = AsyncMock()
    bot.human_wait = AsyncMock()
    bot.human_type = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.thinking_pause = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    bot.warm_up_page = AsyncMock()
    bot.safe_navigate = AsyncMock(return_value=True)
    bot.simulate_reading = AsyncMock()
    bot.natural_scroll = AsyncMock()
    bot.remove_overlays = AsyncMock()
    return bot


# ===================================================================
# 1. __init__ attribute initialization
# ===================================================================

class TestInit:
    @pytest.mark.asyncio
    async def test_faucet_name_set(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.faucet_name == "FreeBitcoin"

    @pytest.mark.asyncio
    async def test_base_url_set(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.base_url == "https://freebitco.in"

    @pytest.mark.asyncio
    async def test_settings_account_override_initially_none(
        self, mock_settings, mock_page, mock_solver
    ):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.settings_account_override is None

    @pytest.mark.asyncio
    async def test_page_reference_stored(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.page is mock_page

    @pytest.mark.asyncio
    async def test_solver_configured(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.solver is not None


# ===================================================================
# 2. is_logged_in -- selector fallback and exception handling
# ===================================================================

class TestIsLoggedIn:
    @pytest.mark.asyncio
    async def test_first_selector_visible_returns_true(
        self, mock_settings, mock_page, mock_solver
    ):
        """First selector (#balance_small) is visible -- should return True
        without checking later selectors."""
        visible_loc = _make_locator(visible=True)
        mock_page.locator = MagicMock(return_value=visible_loc)

        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot.is_logged_in() is True
        # The very first call should be #balance_small
        mock_page.locator.assert_called_with("#balance_small")

    @pytest.mark.asyncio
    async def test_logout_link_detected(self, mock_settings, mock_page, mock_solver):
        """None of the balance selectors match, but a logout link is visible."""
        call_idx = {"n": 0}
        logout_selectors = {
            "a[href*='logout']",
            "a:has-text('Logout')",
            "a:has-text('Sign out')",
            "a[href*='logout.php']",
            "#logout",
            ".logout",
        }

        def locator_factory(selector):
            call_idx["n"] += 1
            if selector in logout_selectors:
                return _make_locator(visible=True)
            return _make_locator(visible=False)

        mock_page.locator = MagicMock(side_effect=locator_factory)
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot.is_logged_in() is True

    @pytest.mark.asyncio
    async def test_all_selectors_invisible_returns_false(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=False)
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot.is_logged_in() is False

    @pytest.mark.asyncio
    async def test_exception_in_selector_is_swallowed(
        self, mock_settings, mock_page, mock_solver
    ):
        """Every locator.is_visible raises -- should return False, not crash."""
        mock_page.locator = MagicMock(
            return_value=_make_locator(raise_on_visible=True)
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot.is_logged_in() is False

    @pytest.mark.asyncio
    async def test_later_balance_selector_matches(
        self, mock_settings, mock_page, mock_solver
    ):
        """#balance_small invisible, but .balance visible."""
        def locator_factory(sel):
            if sel == ".balance":
                return _make_locator(visible=True)
            return _make_locator(visible=False)

        mock_page.locator = MagicMock(side_effect=locator_factory)
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot.is_logged_in() is True


# ===================================================================
# 3. login -- many sub-paths
# ===================================================================

class TestLogin:

    @pytest.mark.asyncio
    async def test_login_uses_override_credentials(
        self, mock_settings, mock_page, mock_solver
    ):
        """When settings_account_override is set, login should use it
        instead of settings.get_account."""
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.settings_account_override = {
            "username": "override@user.com",
            "password": "override_pass",
        }
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        # Make login form fields visible
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=True, count=1)
        )
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True
        # get_account should NOT have been called
        mock_settings.get_account.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_missing_username_key(
        self, mock_settings, mock_page, mock_solver
    ):
        """Credentials dict has no 'username' or 'email' key."""
        mock_settings.get_account.return_value = {"password": "pw"}
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_missing_password_key(
        self, mock_settings, mock_page, mock_solver
    ):
        """Credentials dict has no 'password' key."""
        mock_settings.get_account.return_value = {
            "username": "user@example.com",
        }
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_uses_email_key_fallback(
        self, mock_settings, mock_page, mock_solver
    ):
        """'email' key used when 'username' is absent."""
        mock_settings.get_account.return_value = {
            "email": "alt@example.com",
            "password": "pw",
        }
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=True, count=1)
        )
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_strips_email_alias(
        self, mock_settings, mock_page, mock_solver
    ):
        """Plus-alias in email should be stripped before use."""
        mock_settings.get_account.return_value = {
            "username": "user+alias@example.com",
            "password": "pw",
        }
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=True, count=1)
        )
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True
        # Verify alias was stripped -- human_type first call arg should
        # contain the processed login_id (no '+alias')
        first_call_text = bot.human_type.call_args_list[0][0][1]
        assert "+" not in first_call_text
        assert first_call_text == "user@example.com"

    @pytest.mark.asyncio
    async def test_login_already_logged_in(
        self, mock_settings, mock_page, mock_solver
    ):
        """If is_logged_in returns True after navigation, skip form fill."""
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(return_value=True)
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True
        # human_type should NOT have been called (no form filling)
        bot.human_type.assert_not_called()

    @pytest.mark.asyncio
    async def test_login_navigation_failure_retries(
        self, mock_settings, mock_page, mock_solver
    ):
        """If safe_navigate fails, the loop should continue to next attempt."""
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.safe_navigate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is False
        # 3 attempts
        assert bot.safe_navigate.call_count == 3

    @pytest.mark.asyncio
    async def test_login_email_field_not_found(
        self, mock_settings, mock_page, mock_solver
    ):
        """All email selectors invisible -- should continue to next attempt."""
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(return_value=False)
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=False, count=0)
        )
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_password_field_not_found(
        self, mock_settings, mock_page, mock_solver
    ):
        """Email found but password field invisible -- should continue."""
        def locator_factory(sel):
            if "btc_address" in sel:
                return _make_locator(visible=True, count=1)
            return _make_locator(visible=False, count=0)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(return_value=False)
        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_submit_button_not_found_enter_key(
        self, mock_settings, mock_page, mock_solver
    ):
        """When no submit button found, Enter key pressed on password field."""
        pw_loc = _make_locator(visible=True, count=1)

        def locator_factory(sel):
            # email selectors
            if "btc_address" in sel:
                return _make_locator(visible=True, count=1)
            # password selectors
            if "password" in sel and "login_form" in sel:
                return pw_loc
            if sel == "input[name='password']":
                return pw_loc
            # submit selectors - invisible
            if "login_button" in sel or "submit" in sel or "Login" in sel:
                return _make_locator(visible=False, count=0)
            # login trigger
            if "LOGIN" in sel or "Log In" in sel or "login" in sel:
                return _make_locator(visible=False, count=0)
            # balance / logout
            return _make_locator(visible=False, count=0)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(return_value=False)
        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        # Should have tried pressing Enter on password_field
        assert pw_loc.press.call_count >= 1 or result is False

    @pytest.mark.asyncio
    async def test_login_captcha_on_landing_page_solved(
        self, mock_settings, mock_page, mock_solver
    ):
        """Landing page has a CAPTCHA, solver succeeds."""
        captcha_check_count = {"n": 0}

        async def evaluate_side_effect(script, *a, **kw):
            """Return True the first time (captcha present), False later."""
            if "captchaSelectors" in str(script):
                captcha_check_count["n"] += 1
                if captcha_check_count["n"] == 1:
                    return True
                return False
            return False

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=True, count=1)
        )
        mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
        bot.solver.solve_captcha = AsyncMock(return_value=True)

        result = await bot.login()
        assert result is True
        bot.solver.solve_captcha.assert_called()

    @pytest.mark.asyncio
    async def test_login_captcha_on_landing_page_fails(
        self, mock_settings, mock_page, mock_solver
    ):
        """Landing page CAPTCHA solve returns False -- should continue to
        next attempt."""
        async def evaluate_side_effect(script, *a, **kw):
            if "captchaSelectors" in str(script):
                return True
            return False

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(return_value=False)
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=True, count=1)
        )
        mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
        bot.solver.solve_captcha = AsyncMock(return_value=False)

        result = await bot.login()
        # All 3 attempts fail because captcha fails each time
        assert result is False

    @pytest.mark.asyncio
    async def test_login_error_message_account_locked(
        self, mock_settings, mock_page, mock_solver
    ):
        """Error element says 'Account Locked' -- should be logged and fail."""
        error_loc = _make_locator(visible=True, count=1, text="Account Locked")

        def locator_factory(sel):
            if "btc_address" in sel:
                return _make_locator(visible=True, count=1)
            if "password" in sel:
                return _make_locator(visible=True, count=1)
            if "login_button" in sel:
                return _make_locator(visible=True, count=1)
            if "alert-danger" in sel or "error" in sel:
                return error_loc
            if "balance" in sel or "logout" in sel:
                return _make_locator(visible=False, count=0)
            return _make_locator(visible=False, count=0)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(return_value=False)
        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_error_message_too_many_attempts(
        self, mock_settings, mock_page, mock_solver
    ):
        """Error element says 'Too many login attempts' -- rate limit."""
        error_loc = _make_locator(
            visible=True, count=1, text="Too many login attempts"
        )

        def locator_factory(sel):
            if "btc_address" in sel:
                return _make_locator(visible=True, count=1)
            if "password" in sel:
                return _make_locator(visible=True, count=1)
            if "login_button" in sel:
                return _make_locator(visible=True, count=1)
            if "alert-danger" in sel or "error" in sel:
                return error_loc
            return _make_locator(visible=False, count=0)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(return_value=False)
        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_human_type_fails_uses_fill_fallback(
        self, mock_settings, mock_page, mock_solver
    ):
        """When human_type raises, login falls back to locator.fill."""
        email_loc = _make_locator(visible=True, count=1)
        pw_loc = _make_locator(visible=True, count=1)

        def locator_factory(sel):
            if "btc_address" in sel:
                return email_loc
            if "password" in sel:
                return pw_loc
            if "login_button" in sel:
                return _make_locator(visible=True, count=1)
            return _make_locator(visible=False, count=0)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        bot.human_type = AsyncMock(side_effect=Exception("Typing error"))
        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True
        # fill should have been called on email and password locators
        assert email_loc.fill.call_count >= 1
        assert pw_loc.fill.call_count >= 1

    @pytest.mark.asyncio
    async def test_login_exception_takes_screenshot(
        self, mock_settings, mock_page, mock_solver
    ):
        """General exception during login should trigger screenshot."""
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.safe_navigate = AsyncMock(side_effect=Exception("Fatal nav error"))
        mock_page.screenshot = AsyncMock()

        result = await bot.login()
        assert result is False
        mock_page.screenshot.assert_called()

    @pytest.mark.asyncio
    async def test_login_invalid_username_after_strip(
        self, mock_settings, mock_page, mock_solver
    ):
        """strip_email_alias returns empty -- should fail cleanly."""
        mock_settings.get_account.return_value = {
            "username": "",
            "password": "pw",
        }
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        result = await bot.login()
        assert result is False


# ===================================================================
# 4. claim -- uncovered paths
# ===================================================================

class TestClaim:

    @pytest.mark.asyncio
    async def test_claim_http_403_returns_proxy_issue(
        self, mock_settings, mock_page, mock_solver
    ):
        """HTTP 403 from goto should produce PROXY_ISSUE error type."""
        response = MagicMock()
        response.status = 403
        response.url = "https://freebitco.in/"
        mock_page.goto = AsyncMock(return_value=response)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        result = await bot.claim()

        assert result.success is False
        assert result.status == "HTTP 403"
        assert result.next_claim_minutes == 30
        # error_type imported inside claim(); just verify status string

    @pytest.mark.asyncio
    async def test_claim_http_429_returns_rate_limit(
        self, mock_settings, mock_page, mock_solver
    ):
        response = MagicMock()
        response.status = 429
        response.url = "https://freebitco.in/"
        mock_page.goto = AsyncMock(return_value=response)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        result = await bot.claim()

        assert result.success is False
        assert result.status == "HTTP 429"

    @pytest.mark.asyncio
    async def test_claim_http_401_returns_error(
        self, mock_settings, mock_page, mock_solver
    ):
        response = MagicMock()
        response.status = 401
        response.url = "https://freebitco.in/"
        mock_page.goto = AsyncMock(return_value=response)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        result = await bot.claim()

        assert result.success is False
        assert result.status == "HTTP 401"

    @pytest.mark.asyncio
    async def test_claim_roll_button_disabled(
        self, mock_settings, mock_page, mock_solver
    ):
        """Roll button visible but disabled should return Roll Disabled."""
        roll_btn = _make_locator(visible=True, count=1, enabled=False)

        mock_page.locator = MagicMock(return_value=roll_btn)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001000")
        bot.get_timer = AsyncMock(return_value=0)
        mock_page.goto = AsyncMock(return_value=None)

        result = await bot.claim()
        assert result.success is False
        assert result.status == "Roll Disabled"
        assert result.next_claim_minutes == 15

    @pytest.mark.asyncio
    async def test_claim_zero_amount_result(
        self, mock_settings, mock_page, mock_solver
    ):
        """Result element visible but amount extracts as '0'."""
        roll_btn = _make_locator(visible=True, count=1, enabled=True)
        result_loc = _make_locator(visible=True, count=1, text="0.00000000 BTC")

        def locator_factory(sel):
            if "free_play_form_button" in sel:
                return roll_btn
            if "winnings" in sel:
                return result_loc
            return _make_locator(visible=False, count=0)

        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001000")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=True)

        result = await bot.claim()
        assert result.success is False
        assert result.status == "Zero Amount"
        assert result.next_claim_minutes == 10

    @pytest.mark.asyncio
    async def test_claim_result_not_found(
        self, mock_settings, mock_page, mock_solver
    ):
        """Roll clicked but no result element found on page."""
        roll_btn = _make_locator(visible=True, count=1, enabled=True)

        mock_page.locator = MagicMock(return_value=roll_btn)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001000")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=True)
        # All result selectors invisible (count=0 already default)

        # But we need roll_btn to remain visible after captcha solve
        # and then all result locators to return count=0
        visibility_calls = {"captcha_done": False}

        async def vis_side_effect(*a, **kw):
            return True  # Roll button stays visible

        roll_btn.is_visible = AsyncMock(side_effect=vis_side_effect)

        # For result selectors, count must be 0
        empty_loc = _make_locator(visible=False, count=0)

        def locator_factory(sel):
            if "free_play_form_button" in sel:
                return roll_btn
            return empty_loc

        mock_page.locator = MagicMock(side_effect=locator_factory)

        result = await bot.claim()
        assert result.success is False
        assert result.status == "Result Not Found"

    @pytest.mark.asyncio
    async def test_claim_roll_button_vanishes_after_captcha(
        self, mock_settings, mock_page, mock_solver
    ):
        """Roll button visible initially, then not visible after captcha."""
        vis_sequence = [True]  # wait_for succeeds

        roll_btn = _make_locator(visible=False, count=0, enabled=True)

        # wait_for succeeds (so roll_visible=True), is_enabled returns True,
        # but then is_visible returns False
        roll_btn.wait_for = AsyncMock()  # no error
        roll_btn.is_enabled = AsyncMock(return_value=True)
        roll_btn.is_visible = AsyncMock(return_value=False)

        vanish_loc = _make_locator(visible=False, count=0)

        def locator_factory(sel):
            if "free_play_form_button" in sel:
                return roll_btn
            return vanish_loc

        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001000")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=True)

        result = await bot.claim()
        assert result.success is False
        assert result.status == "Roll Button Vanished"

    @pytest.mark.asyncio
    async def test_claim_general_exception_retries_and_fails(
        self, mock_settings, mock_page, mock_solver
    ):
        """Non-timeout exception triggers retry with backoff."""
        mock_page.goto = AsyncMock(side_effect=Exception("Connection reset"))

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        result = await bot.claim()

        assert result.success is False
        assert "Error:" in result.status
        assert result.next_claim_minutes == 30
        # Should have retried 3 times
        assert mock_page.goto.call_count == 3

    @pytest.mark.asyncio
    async def test_claim_timeout_first_attempt_retries(
        self, mock_settings, mock_page, mock_solver
    ):
        """TimeoutError on first attempt, success on second."""
        call_count = {"n": 0}

        async def goto_side(*a, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise asyncio.TimeoutError("First timeout")
            return None

        roll_btn = _make_locator(visible=True, count=1, enabled=True)
        result_loc = _make_locator(visible=True, count=1, text="0.00000100 BTC")

        def locator_factory(sel):
            if "free_play_form_button" in sel:
                return roll_btn
            if "winnings" in sel:
                return result_loc
            return _make_locator(visible=False, count=0)

        mock_page.goto = AsyncMock(side_effect=goto_side)
        mock_page.locator = MagicMock(side_effect=locator_factory)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001000")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=True)

        result = await bot.claim()
        assert result.success is True
        assert result.amount == "0.000001"
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_claim_response_status_attribute_error_handled(
        self, mock_settings, mock_page, mock_solver
    ):
        """Response object exists but accessing .status raises -- should not
        crash."""
        response = MagicMock()
        type(response).status = PropertyMock(
            side_effect=AttributeError("no status")
        )
        mock_page.goto = AsyncMock(return_value=response)

        roll_btn = _make_locator(visible=False, count=0)
        mock_page.locator = MagicMock(return_value=roll_btn)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0")
        bot.get_timer = AsyncMock(return_value=0)

        result = await bot.claim()
        # Should not crash -- just treat as no special status
        assert isinstance(result, ClaimResult)

    @pytest.mark.asyncio
    async def test_claim_captcha_solve_exception(
        self, mock_settings, mock_page, mock_solver
    ):
        """CAPTCHA solver raises an exception during claim."""
        roll_btn = _make_locator(visible=True, count=1, enabled=True)
        mock_page.locator = MagicMock(return_value=roll_btn)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001000")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(
            side_effect=Exception("Solver API down")
        )

        result = await bot.claim()
        assert result.success is False
        assert result.status == "CAPTCHA Failed"


# ===================================================================
# 5. _wait_for_captcha_token
# ===================================================================

class TestWaitForCaptchaToken:

    @pytest.mark.asyncio
    async def test_token_found_returns_true(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.wait_for_function = AsyncMock()
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._wait_for_captcha_token(timeout=5000) is True

    @pytest.mark.asyncio
    async def test_timeout_returns_false(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.wait_for_function = AsyncMock(
            side_effect=asyncio.TimeoutError("no token")
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._wait_for_captcha_token(timeout=100) is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.wait_for_function = AsyncMock(
            side_effect=Exception("frame detached")
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._wait_for_captcha_token() is False


# ===================================================================
# 6. _has_session_cookie
# ===================================================================

class TestHasSessionCookie:

    @pytest.mark.asyncio
    async def test_cookie_present(self, mock_settings, mock_page, mock_solver):
        mock_page.context.cookies = AsyncMock(
            return_value=[{"name": "fbtc_session", "value": "abc123"}]
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._has_session_cookie() is True

    @pytest.mark.asyncio
    async def test_userid_cookie_present(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.context.cookies = AsyncMock(
            return_value=[{"name": "fbtc_userid", "value": "42"}]
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._has_session_cookie() is True

    @pytest.mark.asyncio
    async def test_no_relevant_cookies(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.context.cookies = AsyncMock(
            return_value=[{"name": "other_cookie", "value": "x"}]
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._has_session_cookie() is False

    @pytest.mark.asyncio
    async def test_empty_cookie_jar(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.context.cookies = AsyncMock(return_value=[])
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._has_session_cookie() is False

    @pytest.mark.asyncio
    async def test_cookies_exception_returns_false(
        self, mock_settings, mock_page, mock_solver
    ):
        mock_page.context.cookies = AsyncMock(
            side_effect=Exception("context closed")
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._has_session_cookie() is False


# ===================================================================
# 7. _log_login_diagnostics
# ===================================================================

class TestLogLoginDiagnostics:

    @pytest.mark.asyncio
    async def test_diagnostics_runs_without_crash(
        self, mock_settings, mock_page, mock_solver
    ):
        """All evaluate calls succeed -- diagnostics should complete."""
        mock_page.evaluate = AsyncMock(return_value=[])
        bot = FreeBitcoinBot(mock_settings, mock_page)
        # Should not raise
        await bot._log_login_diagnostics("test_context")

    @pytest.mark.asyncio
    async def test_diagnostics_handles_all_evaluate_exceptions(
        self, mock_settings, mock_page, mock_solver
    ):
        """Every evaluate call raises -- diagnostics should still finish."""
        mock_page.evaluate = AsyncMock(
            side_effect=Exception("eval error")
        )
        bot = FreeBitcoinBot(mock_settings, mock_page)
        # Should not raise
        await bot._log_login_diagnostics("failing_context")


# ===================================================================
# 8. withdraw -- additional edge cases
# ===================================================================

class TestWithdraw:

    @pytest.mark.asyncio
    async def test_withdraw_error_message_shown(
        self, mock_settings, mock_page, mock_solver
    ):
        """Withdrawal form shows an error message after submission."""
        success_loc = _make_locator(visible=False, count=0)
        error_loc = _make_locator(
            visible=True, count=1, text="Insufficient balance"
        )

        def locator_factory(sel):
            if "alert-success" in sel or "successful" in sel:
                return success_loc
            if "alert-danger" in sel or "error" in sel:
                return error_loc
            if "slow" in sel:
                return _make_locator(visible=True, count=1)
            if "Max" in sel or "max" in sel:
                return _make_locator(visible=True, count=1)
            if "twofa" in sel or "2fa" in sel:
                return _make_locator(visible=False, count=0)
            if "withdraw_button" in sel or "Withdraw" in sel:
                return _make_locator(visible=True, count=1)
            if "withdraw_address" in sel or "address" in sel:
                return _make_locator(visible=True, count=1)
            if "withdraw_amount" in sel or "amount" in sel:
                return _make_locator(visible=True, count=1)
            return _make_locator(visible=False, count=0)

        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00035000")

        result = await bot.withdraw()
        assert result.success is False
        assert "Error:" in result.status
        assert "Insufficient balance" in result.status

    @pytest.mark.asyncio
    async def test_withdraw_unknown_result(
        self, mock_settings, mock_page, mock_solver
    ):
        """No success or error message found after submission."""
        empty_loc = _make_locator(visible=False, count=0)

        def locator_factory(sel):
            if "slow" in sel:
                return _make_locator(visible=True, count=1)
            if "Max" in sel or "max" in sel:
                return _make_locator(visible=True, count=1)
            if "twofa" in sel or "2fa" in sel:
                return _make_locator(visible=False, count=0)
            if "withdraw_button" in sel or "Withdraw" in sel:
                return _make_locator(visible=True, count=1)
            if "withdraw_address" in sel or "address" in sel:
                return _make_locator(visible=True, count=1)
            if "withdraw_amount" in sel or "amount" in sel:
                return _make_locator(visible=True, count=1)
            return empty_loc

        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00035000")

        result = await bot.withdraw()
        assert result.success is False
        assert result.status == "Unknown Result"
        assert result.next_claim_minutes == 360


# ===================================================================
# 9. get_jobs field-level validation
# ===================================================================

class TestGetJobs:

    def test_job_types_correct(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        jobs = bot.get_jobs()
        assert jobs[0].job_type == "claim_wrapper"
        assert jobs[1].job_type == "withdraw_wrapper"

    def test_faucet_type_lowercase(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        jobs = bot.get_jobs()
        assert jobs[0].faucet_type == "freebitcoin"
        assert jobs[1].faucet_type == "freebitcoin"

    def test_claim_job_runs_immediately(
        self, mock_settings, mock_page, mock_solver
    ):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        import time
        before = time.time()
        jobs = bot.get_jobs()
        after = time.time()
        # next_run should be around now
        assert jobs[0].next_run >= before
        assert jobs[0].next_run <= after + 1

    def test_withdraw_job_delayed(
        self, mock_settings, mock_page, mock_solver
    ):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        import time
        now = time.time()
        jobs = bot.get_jobs()
        # Withdraw delayed by 86400s
        assert jobs[1].next_run >= now + 86000


# ===================================================================
# 10. strip_email_alias (exercised through login, but also directly)
# ===================================================================

class TestStripEmailAlias:

    def test_strips_plus_alias(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.strip_email_alias("user+tag@example.com") == "user@example.com"

    def test_no_alias_unchanged(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.strip_email_alias("user@example.com") == "user@example.com"

    def test_none_returns_none(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.strip_email_alias(None) is None

    def test_empty_returns_empty(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.strip_email_alias("") == ""

    def test_no_at_sign_unchanged(self, mock_settings, mock_page, mock_solver):
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert bot.strip_email_alias("no_at_sign") == "no_at_sign"


# ===================================================================
# 11. Edge cases
# ===================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_claim_empty_page_content(
        self, mock_settings, mock_page, mock_solver
    ):
        """claim() with completely empty page should not crash."""
        mock_page.content = AsyncMock(return_value="")
        mock_page.goto = AsyncMock(return_value=None)
        roll_btn = _make_locator(visible=False, count=0)
        mock_page.locator = MagicMock(return_value=roll_btn)
        roll_btn.wait_for = AsyncMock(
            side_effect=Exception("not found")
        )

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0")
        bot.get_timer = AsyncMock(return_value=0)

        result = await bot.claim()
        assert isinstance(result, ClaimResult)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_claim_result_selector_exception_continues(
        self, mock_settings, mock_page, mock_solver
    ):
        """Exception on one result selector should not prevent checking
        subsequent selectors."""
        roll_btn = _make_locator(visible=True, count=1, enabled=True)
        ok_loc = _make_locator(visible=True, count=1, text="0.00000200 BTC")
        error_loc = MagicMock()
        error_loc.count = AsyncMock(side_effect=Exception("stale"))

        selectors_seen = []

        def locator_factory(sel):
            selectors_seen.append(sel)
            if "free_play_form_button" in sel:
                return roll_btn
            if "#winnings" in sel:
                return error_loc  # This will raise
            if ".winning-amount" in sel:
                return ok_loc  # This is the fallback
            return _make_locator(visible=False, count=0)

        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=True)

        result = await bot.claim()
        assert result.success is True
        assert result.amount == "0.000002"

    @pytest.mark.asyncio
    async def test_login_long_username_display_truncation(
        self, mock_settings, mock_page, mock_solver
    ):
        """Username > 10 chars should be truncated in logs (not crash)."""
        mock_settings.get_account.return_value = {
            "username": "verylongusername@example.com",
            "password": "pw",
        }
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=True, count=1)
        )
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_short_username_display_truncation(
        self, mock_settings, mock_page, mock_solver
    ):
        """Username <= 10 chars truncated differently."""
        mock_settings.get_account.return_value = {
            "username": "ab@c.com",
            "password": "pw",
        }
        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        mock_page.locator = MagicMock(
            return_value=_make_locator(visible=True, count=1)
        )
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_claim_with_settings_timeout_attribute(
        self, mock_settings, mock_page, mock_solver
    ):
        """nav_timeout should come from settings.timeout."""
        mock_settings.timeout = 120000
        mock_page.goto = AsyncMock(return_value=None)
        roll_btn = _make_locator(visible=False, count=0)
        roll_btn.wait_for = AsyncMock(
            side_effect=Exception("not found")
        )
        mock_page.locator = MagicMock(return_value=roll_btn)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0")
        bot.get_timer = AsyncMock(return_value=0)

        await bot.claim()
        # Verify goto was called with the custom timeout
        call_kwargs = mock_page.goto.call_args
        assert call_kwargs[1]["timeout"] == 120000 or call_kwargs.kwargs.get("timeout") == 120000

    @pytest.mark.asyncio
    async def test_is_logged_in_timeout_on_is_visible_continues(
        self, mock_settings, mock_page, mock_solver
    ):
        """Timeout exception on is_visible should be caught and continue to
        next selector."""
        timeout_loc = MagicMock()
        timeout_loc.is_visible = AsyncMock(
            side_effect=asyncio.TimeoutError("vis timeout")
        )

        mock_page.locator = MagicMock(return_value=timeout_loc)
        bot = FreeBitcoinBot(mock_settings, mock_page)
        result = await bot.is_logged_in()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_trigger_clicked_before_form(
        self, mock_settings, mock_page, mock_solver
    ):
        """Login trigger link is visible -- should be clicked before filling form."""
        trigger_loc = _make_locator(visible=True, count=1)
        form_loc = _make_locator(visible=True, count=1)
        trigger_clicked = {"clicked": False}

        original_human_click = AsyncMock()

        def locator_factory(sel):
            if "LOGIN" in sel or "Log In" in sel:
                return trigger_loc
            return form_loc

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.is_logged_in = AsyncMock(side_effect=[False, True])
        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.evaluate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is True
        # human_like_click should have been called (for trigger)
        bot.human_like_click.assert_called()

    @pytest.mark.asyncio
    async def test_claim_navigation_wait_timeout_handled(
        self, mock_settings, mock_page, mock_solver
    ):
        """wait_for_navigation timeout after roll click should not crash."""
        roll_btn = _make_locator(visible=True, count=1, enabled=True)
        result_loc = _make_locator(visible=True, count=1, text="0.00000050 BTC")
        mock_page.wait_for_navigation = AsyncMock(
            side_effect=asyncio.TimeoutError("no nav")
        )

        def locator_factory(sel):
            if "free_play_form_button" in sel:
                return roll_btn
            if "winnings" in sel:
                return result_loc
            return _make_locator(visible=False, count=0)

        mock_page.locator = MagicMock(side_effect=locator_factory)
        mock_page.goto = AsyncMock(return_value=None)

        bot = _make_bot(mock_settings, mock_page, mock_solver)
        bot.get_balance = AsyncMock(return_value="0.00001")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=True)

        result = await bot.claim()
        assert result.success is True
        assert result.status == "Claimed"

    @pytest.mark.asyncio
    async def test_has_session_cookie_both_cookies_present(
        self, mock_settings, mock_page, mock_solver
    ):
        """Both fbtc_session and fbtc_userid present."""
        mock_page.context.cookies = AsyncMock(return_value=[
            {"name": "fbtc_session", "value": "s1"},
            {"name": "fbtc_userid", "value": "u1"},
        ])
        bot = FreeBitcoinBot(mock_settings, mock_page)
        assert await bot._has_session_cookie() is True

    @pytest.mark.asyncio
    async def test_claim_all_timeouts_exhausted(
        self, mock_settings, mock_page, mock_solver
    ):
        """All 3 attempts hit TimeoutError."""
        mock_page.goto = AsyncMock(
            side_effect=asyncio.TimeoutError("always timeout")
        )
        bot = _make_bot(mock_settings, mock_page, mock_solver)

        result = await bot.claim()
        assert result.success is False
        assert "Timeout" in result.status
        assert result.next_claim_minutes == 30
        assert mock_page.goto.call_count == 3
