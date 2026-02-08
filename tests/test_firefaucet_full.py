"""Comprehensive tests for FireFaucetBot covering uncovered methods and edge cases.

Complements test_firefaucet.py and test_firefaucet_enhanced.py by testing:
    - detect_cloudflare_block: title checks, body text, iframe, CF elements, exceptions
    - bypass_cloudflare_with_retry: success/failure paths, turnstile solving, retries
    - _click_and_verify_claim: button countdown, JS fallback, multiple success strategies
    - _wait_for_button_countdown: countdown complete, timeout with force-enable
    - _check_page_text_success: phrase detection, amount extraction
    - _check_success_selectors: DOM-based success, error word filtering
    - _check_balance_change: balance changed vs unchanged
    - _debug_log_page_elements: page element enumeration
    - login edge cases: adblock redirect, cloudflare bypass, alternate selectors,
      disabled submit, form submit fallback, credentials override
    - claim edge cases: cloudflare on daily/faucet pages, error classification
    - claim_shortlinks: separate context, no links, analytics tracking
    - __init__: detailed attribute verification
    - get_jobs: priorities, timing, structure
    - view_ptc_ads: captcha handling, submit button missing
    - withdraw: no success message path
"""

import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from faucets.firefaucet import FireFaucetBot
from faucets.base import ClaimResult
from core.config import BotSettings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    """Fixture for mock BotSettings."""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {
        "username": "testuser",
        "password": "testpass",
    }
    settings.wallet_addresses = {"BTC": {"address": "ADDR"}}
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key"
    settings.capsolver_api_key = ""
    settings.timeout = 60000
    settings.enable_shortlinks = True
    return settings


def _make_locator(**overrides):
    """Helper: create a MagicMock locator with sensible async defaults."""
    loc = MagicMock()
    loc.count = AsyncMock(return_value=overrides.get("count", 0))
    loc.is_visible = AsyncMock(return_value=overrides.get("visible", False))
    loc.is_disabled = AsyncMock(return_value=overrides.get("disabled", False))
    loc.is_enabled = AsyncMock(return_value=overrides.get("enabled", True))
    loc.text_content = AsyncMock(return_value=overrides.get("text", ""))
    loc.get_attribute = AsyncMock(return_value=overrides.get("attr", None))
    loc.click = AsyncMock()
    loc.select_option = AsyncMock()
    loc.scroll_into_view_if_needed = AsyncMock()
    loc.bounding_box = AsyncMock(return_value=None)
    loc.all = AsyncMock(return_value=[])
    loc.nth = MagicMock(return_value=loc)

    first = MagicMock()
    first.is_visible = AsyncMock(return_value=overrides.get("visible", False))
    first.is_enabled = AsyncMock(return_value=overrides.get("enabled", True))
    first.text_content = AsyncMock(return_value=overrides.get("text", ""))
    first.get_attribute = AsyncMock(return_value=overrides.get("attr", None))
    first.click = AsyncMock()
    loc.first = first

    last = MagicMock()
    last.click = AsyncMock()
    loc.last = last

    return loc


@pytest.fixture
def mock_page():
    """Fixture for a fully mocked Playwright Page."""
    page = AsyncMock()
    page.url = "https://firefaucet.win"
    page.title = AsyncMock(return_value="FireFaucet")
    page.content = AsyncMock(return_value="<html></html>")
    page.goto = AsyncMock()
    page.reload = AsyncMock()
    page.fill = AsyncMock()
    page.click = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_function = AsyncMock()
    page.evaluate = AsyncMock(return_value="")
    page.screenshot = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.is_closed = MagicMock(return_value=False)
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.viewport_size = {"width": 1280, "height": 720}

    default_loc = _make_locator()
    page.locator = MagicMock(return_value=default_loc)

    # browser context for shortlinks
    context = MagicMock()
    context.browser = MagicMock()
    context.cookies = AsyncMock(return_value=[])
    context.add_cookies = AsyncMock()
    context.close = AsyncMock()
    new_ctx = MagicMock()
    new_ctx.new_page = AsyncMock(return_value=page)
    new_ctx.add_cookies = AsyncMock()
    new_ctx.close = AsyncMock()
    context.browser.new_context = AsyncMock(return_value=new_ctx)
    page.context = context

    return page


@pytest.fixture
def bot(mock_settings, mock_page):
    """Return a FireFaucetBot with common helpers mocked for speed."""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver = MockSolver.return_value
        solver.solve_captcha = AsyncMock(return_value=True)
        solver.close = AsyncMock()
        solver.set_faucet_name = MagicMock()

        b = FireFaucetBot(mock_settings, mock_page)
        # Speed up tests by stubbing expensive human-simulation helpers
        b.idle_mouse = AsyncMock()
        b.simulate_reading = AsyncMock()
        b.natural_scroll = AsyncMock()
        b.thinking_pause = AsyncMock()
        b.random_delay = AsyncMock()
        b.human_wait = AsyncMock()
        b.human_like_click = AsyncMock()
        b.warm_up_page = AsyncMock()
        b.remove_overlays = AsyncMock()
        return b


# ===================================================================
# 1. __init__ attribute verification
# ===================================================================

class TestInit:
    """Detailed __init__ attribute checks."""

    @pytest.mark.asyncio
    async def test_init_sets_faucet_name(self, bot):
        assert bot.faucet_name == "FireFaucet"

    @pytest.mark.asyncio
    async def test_init_sets_base_url(self, bot):
        assert bot.base_url == "https://firefaucet.win"

    @pytest.mark.asyncio
    async def test_init_sets_cloudflare_retry_count(self, bot):
        assert bot.cloudflare_retry_count == 0

    @pytest.mark.asyncio
    async def test_init_sets_max_cloudflare_retries(self, bot):
        assert bot.max_cloudflare_retries == 3


# ===================================================================
# 2. detect_cloudflare_block
# ===================================================================

class TestDetectCloudflareBlock:
    """Test detect_cloudflare_block with various page states."""

    @pytest.mark.asyncio
    async def test_detects_just_a_moment_title(self, bot, mock_page):
        mock_page.title.return_value = "Just a moment..."
        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_security_check_title(self, bot, mock_page):
        mock_page.title.return_value = "Security Check Required"
        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_ddos_protection_title(self, bot, mock_page):
        mock_page.title.return_value = "DDoS Protection"
        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_attention_required_title(self, bot, mock_page):
        mock_page.title.return_value = "Attention Required"
        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_checking_your_browser_title(self, bot, mock_page):
        mock_page.title.return_value = "Checking your browser..."
        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_challenge_in_short_body_text(self, bot, mock_page):
        """Challenge patterns in short body text (< 1000 chars) trigger detection."""
        mock_page.title.return_value = "Normal Title"
        mock_page.evaluate.return_value = "please wait while we check your browser"
        mock_page.query_selector.return_value = None
        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_ignores_challenge_in_long_body_text(self, bot, mock_page):
        """Challenge patterns in long body (>= 1000 chars) are treated as normal page content."""
        mock_page.title.return_value = "Normal Title"
        long_body = "please wait while we check your browser " + ("x" * 1000)
        mock_page.evaluate.return_value = long_body
        mock_page.query_selector.return_value = None
        result = await bot.detect_cloudflare_block()
        assert result is False

    @pytest.mark.asyncio
    async def test_detects_turnstile_iframe(self, bot, mock_page):
        mock_page.title.return_value = "Normal Title"
        mock_page.evaluate.return_value = "nothing special " + ("x" * 1200)

        # First query_selector call = turnstile, return a truthy object
        turnstile_elem = MagicMock()
        mock_page.query_selector.side_effect = [turnstile_elem]

        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_cf_challenge_elements(self, bot, mock_page):
        mock_page.title.return_value = "Normal Title"
        mock_page.evaluate.return_value = "normal content " + ("x" * 1200)

        # First query = turnstile (None), second query = cf elements (truthy)
        cf_elem = MagicMock()
        mock_page.query_selector.side_effect = [None, cf_elem]

        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_cf_detected(self, bot, mock_page):
        mock_page.title.return_value = "FireFaucet - Dashboard"
        mock_page.evaluate.return_value = "welcome to firefaucet " + ("x" * 1200)
        mock_page.query_selector.return_value = None

        result = await bot.detect_cloudflare_block()
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, bot, mock_page):
        mock_page.title.side_effect = Exception("Page crashed")
        result = await bot.detect_cloudflare_block()
        assert result is False


# ===================================================================
# 3. bypass_cloudflare_with_retry
# ===================================================================

class TestBypassCloudflareWithRetry:
    """Test bypass_cloudflare_with_retry paths."""

    @pytest.mark.asyncio
    async def test_bypass_succeeds_on_first_attempt(self, bot, mock_page):
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        mock_page.query_selector.return_value = None  # no turnstile

        result = await bot.bypass_cloudflare_with_retry()
        assert result is True
        assert bot.cloudflare_retry_count == 0

    @pytest.mark.asyncio
    async def test_bypass_succeeds_on_second_attempt(self, bot, mock_page):
        # First attempt still blocked, second attempt clears
        bot.detect_cloudflare_block = AsyncMock(side_effect=[True, False])
        mock_page.query_selector.return_value = None

        result = await bot.bypass_cloudflare_with_retry()
        assert result is True

    @pytest.mark.asyncio
    async def test_bypass_fails_after_all_retries(self, bot, mock_page):
        bot.detect_cloudflare_block = AsyncMock(return_value=True)
        mock_page.query_selector.return_value = None

        result = await bot.bypass_cloudflare_with_retry()
        assert result is False
        assert bot.cloudflare_retry_count == 1

    @pytest.mark.asyncio
    async def test_bypass_solves_turnstile_successfully(self, bot, mock_page):
        """When turnstile is detected, solve it and succeed."""
        turnstile_elem = MagicMock()
        mock_page.query_selector.return_value = turnstile_elem
        bot.solver.solve_captcha = AsyncMock(return_value=True)
        # After solving, CF is no longer blocking
        bot.detect_cloudflare_block = AsyncMock(return_value=False)

        result = await bot.bypass_cloudflare_with_retry()
        assert result is True
        bot.solver.solve_captcha.assert_called()

    @pytest.mark.asyncio
    async def test_bypass_turnstile_solve_fails_retries(self, bot, mock_page):
        """When turnstile solving fails, the bot retries."""
        turnstile_elem = MagicMock()
        mock_page.query_selector.return_value = turnstile_elem
        bot.solver.solve_captcha = AsyncMock(return_value=False)
        bot.detect_cloudflare_block = AsyncMock(return_value=True)

        result = await bot.bypass_cloudflare_with_retry()
        assert result is False
        # Page should have been reloaded for retries
        assert mock_page.reload.call_count >= 1

    @pytest.mark.asyncio
    async def test_bypass_handles_exception_during_attempt(self, bot, mock_page):
        """Exception during an attempt should not crash; continues to next retry."""
        bot.detect_cloudflare_block = AsyncMock(
            side_effect=Exception("unexpected")
        )
        mock_page.query_selector.return_value = None

        result = await bot.bypass_cloudflare_with_retry()
        assert result is False


# ===================================================================
# 4. _check_page_text_success
# ===================================================================

class TestCheckPageTextSuccess:

    @pytest.mark.asyncio
    async def test_detects_claimed_successfully(self, bot, mock_page):
        mock_page.evaluate.return_value = "Congratulations! You claimed successfully 50 satoshi."
        bot.get_balance = AsyncMock(return_value="500")
        balance_selectors = [".user-balance", ".balance"]

        result = await bot._check_page_text_success(balance_selectors)
        assert result is not None
        assert result.success is True
        assert result.amount == "50"

    @pytest.mark.asyncio
    async def test_detects_reward_received(self, bot, mock_page):
        mock_page.evaluate.return_value = "reward received"
        bot.get_balance = AsyncMock(return_value="100")

        result = await bot._check_page_text_success([".bal"])
        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_returns_none_when_no_phrase_found(self, bot, mock_page):
        mock_page.evaluate.return_value = "nothing interesting on this page"

        result = await bot._check_page_text_success([".bal"])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, bot, mock_page):
        mock_page.evaluate.side_effect = Exception("DOM error")

        result = await bot._check_page_text_success([".bal"])
        assert result is None

    @pytest.mark.asyncio
    async def test_amount_defaults_to_unknown_without_match(self, bot, mock_page):
        mock_page.evaluate.return_value = "you got some coins!"
        bot.get_balance = AsyncMock(return_value="100")

        result = await bot._check_page_text_success([".bal"])
        assert result is not None
        assert result.amount == "unknown"


# ===================================================================
# 5. _check_success_selectors
# ===================================================================

class TestCheckSuccessSelectors:

    @pytest.mark.asyncio
    async def test_finds_success_element(self, bot, mock_page):
        success_loc = _make_locator(count=1, visible=True, text="Claimed 10 BTC!")
        mock_page.locator.return_value = success_loc

        found, msg = await bot._check_success_selectors()
        assert found is True
        assert "Claimed" in msg

    @pytest.mark.asyncio
    async def test_filters_out_error_words(self, bot, mock_page):
        """Elements containing 'error', 'fail', 'wait' etc. are skipped."""
        err_loc = _make_locator(count=1, visible=True, text="Please wait 10 seconds")
        mock_page.locator.return_value = err_loc

        found, _ = await bot._check_success_selectors()
        assert found is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_elements(self, bot, mock_page):
        empty_loc = _make_locator(count=0)
        mock_page.locator.return_value = empty_loc

        found, msg = await bot._check_success_selectors()
        assert found is False
        assert msg == ""

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, bot, mock_page):
        mock_page.locator.side_effect = Exception("DOM error")

        found, msg = await bot._check_success_selectors()
        assert found is False


# ===================================================================
# 6. _check_balance_change
# ===================================================================

class TestCheckBalanceChange:

    @pytest.mark.asyncio
    async def test_detects_balance_increase(self, bot):
        bot.get_balance = AsyncMock(return_value="150")
        changed, new_bal = await bot._check_balance_change(
            "100", [".user-balance", ".balance"]
        )
        assert changed is True
        assert new_bal == "150"

    @pytest.mark.asyncio
    async def test_no_change_returns_false(self, bot):
        bot.get_balance = AsyncMock(return_value="100")
        changed, bal = await bot._check_balance_change(
            "100", [".user-balance"]
        )
        assert changed is False
        assert bal == "100"

    @pytest.mark.asyncio
    async def test_zero_balance_returns_false(self, bot):
        bot.get_balance = AsyncMock(return_value="0")
        changed, bal = await bot._check_balance_change(
            "100", [".user-balance"]
        )
        assert changed is False

    @pytest.mark.asyncio
    async def test_exception_returns_false(self, bot):
        bot.get_balance = AsyncMock(side_effect=Exception("fail"))
        changed, bal = await bot._check_balance_change(
            "100", [".user-balance"]
        )
        assert changed is False
        assert bal == "100"


# ===================================================================
# 7. _wait_for_button_countdown
# ===================================================================

class TestWaitForButtonCountdown:

    @pytest.mark.asyncio
    async def test_countdown_completes_normally(self, bot, mock_page):
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.wait_for_function.return_value = True

        await bot._wait_for_button_countdown(faucet_btn)

        mock_page.wait_for_function.assert_called_once()

    @pytest.mark.asyncio
    async def test_countdown_timeout_force_enables(self, bot, mock_page):
        """When countdown times out, the button should be force-enabled via JS."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.wait_for_function.side_effect = Exception("Timeout")

        await bot._wait_for_button_countdown(faucet_btn)

        # Verify JS evaluate was called to force-enable the button
        assert mock_page.evaluate.call_count >= 1


# ===================================================================
# 8. _click_and_verify_claim
# ===================================================================

class TestClickAndVerifyClaim:

    @pytest.mark.asyncio
    async def test_success_via_page_text(self, bot, mock_page):
        """Success detected through page text phrase."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.evaluate.return_value = "Congratulations! claimed successfully 25 satoshi"
        bot.get_balance = AsyncMock(return_value="200")

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance", ".balance"]
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_success_via_dom_selector(self, bot, mock_page):
        """Success detected through DOM success elements."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        # _check_page_text_success returns None (no phrase)
        mock_page.evaluate.return_value = "nothing useful"

        # Mock _check_success_selectors to return found
        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(
            return_value=(True, "Reward added!")
        )
        bot._check_balance_change = AsyncMock(
            return_value=(False, "100")
        )
        bot.get_balance = AsyncMock(return_value="200")

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is True
        assert result.status == "Claimed"

    @pytest.mark.asyncio
    async def test_success_via_balance_change(self, bot, mock_page):
        """Success detected through balance change."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(return_value=(False, ""))
        bot._check_balance_change = AsyncMock(return_value=(True, "200"))
        bot.get_balance = AsyncMock(return_value="200")

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_success_via_url_indicator(self, bot, mock_page):
        """Success detected through URL containing 'dashboard'."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.url = "https://firefaucet.win/dashboard"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(return_value=(False, ""))
        bot._check_balance_change = AsyncMock(return_value=(False, "100"))
        bot.get_balance = AsyncMock(return_value="100")

        # "Get reward" button should still be found for disappearance check
        get_reward_loc = _make_locator(count=0)
        mock_page.locator.return_value = get_reward_loc

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_success_via_button_disappeared(self, bot, mock_page):
        """Success detected because claim button disappeared."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.url = "https://firefaucet.win/faucet"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(return_value=(False, ""))
        bot._check_balance_change = AsyncMock(return_value=(False, "100"))

        # Button disappeared
        gone_loc = _make_locator(count=0)
        mock_page.locator.return_value = gone_loc
        bot.get_balance = AsyncMock(return_value="150")

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_failure_when_no_indicator_found(self, bot, mock_page):
        """Returns failure when no success indicator is found at all."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.url = "https://firefaucet.win/faucet"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(return_value=(False, ""))
        bot._check_balance_change = AsyncMock(return_value=(False, "100"))

        # Button still present
        still_loc = _make_locator(count=1)
        mock_page.locator.return_value = still_loc
        mock_page.evaluate.return_value = "some page text"

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is False
        assert result.status == "Faucet Ready but Failed"

    @pytest.mark.asyncio
    async def test_disabled_button_triggers_countdown_wait(self, bot, mock_page):
        """When button is disabled, _wait_for_button_countdown is called."""
        faucet_btn = _make_locator(count=1, enabled=False, text="Please Wait 9")
        faucet_btn.first.is_enabled = AsyncMock(return_value=False)
        faucet_btn.first.get_attribute = AsyncMock(return_value="true")
        mock_page.title.return_value = "FireFaucet"

        bot._wait_for_button_countdown = AsyncMock()
        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(return_value=(False, ""))
        bot._check_balance_change = AsyncMock(return_value=(False, "100"))
        gone_loc = _make_locator(count=0)
        mock_page.locator.return_value = gone_loc
        bot.get_balance = AsyncMock(return_value="150")

        await bot._click_and_verify_claim(faucet_btn, "100", [".user-balance"])

        bot._wait_for_button_countdown.assert_called_once_with(faucet_btn)

    @pytest.mark.asyncio
    async def test_js_click_fallback_when_text_unchanged(self, bot, mock_page):
        """When button text does not change to 'please wait', JS click is attempted."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        # After click, text still says "Get Reward" (not "please wait")
        faucet_btn.first.text_content = AsyncMock(return_value="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.url = "https://firefaucet.win/faucet"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(return_value=(False, ""))
        bot._check_balance_change = AsyncMock(return_value=(False, "100"))

        still_loc = _make_locator(count=1)
        mock_page.locator.return_value = still_loc
        mock_page.evaluate.return_value = ""

        await bot._click_and_verify_claim(faucet_btn, "100", [".bal"])

        # page.evaluate should be called for the JS click fallback
        assert mock_page.evaluate.call_count >= 1


# ===================================================================
# 9. _debug_log_page_elements
# ===================================================================

class TestDebugLogPageElements:

    @pytest.mark.asyncio
    async def test_logs_when_not_on_faucet_page(self, bot, mock_page):
        """Should note redirect when URL does not contain /faucet."""
        mock_page.url = "https://firefaucet.win/login"
        empty_loc = _make_locator(count=0)
        empty_loc.all = AsyncMock(return_value=[])
        mock_page.locator.return_value = empty_loc

        # Should not raise
        await bot._debug_log_page_elements()

    @pytest.mark.asyncio
    async def test_logs_buttons_and_links(self, bot, mock_page):
        mock_page.url = "https://firefaucet.win/faucet"

        btn_mock = MagicMock()
        btn_mock.text_content = AsyncMock(return_value="Submit")
        btn_mock.get_attribute = AsyncMock(return_value="submit-btn")
        btn_mock.is_visible = AsyncMock(return_value=True)

        btn_loc = _make_locator(count=1)
        btn_loc.all = AsyncMock(return_value=[btn_mock])

        link_loc = _make_locator(count=0)
        link_loc.all = AsyncMock(return_value=[])

        err_loc = _make_locator(count=0)
        err_loc.all = AsyncMock(return_value=[])

        def locator_dispatch(selector):
            if "input[type='submit']" in selector:
                return btn_loc
            elif "a.btn" in selector:
                return link_loc
            elif ".alert" in selector or ".error" in selector:
                return err_loc
            return _make_locator()

        mock_page.locator.side_effect = locator_dispatch
        await bot._debug_log_page_elements()

    @pytest.mark.asyncio
    async def test_handles_exception_in_debug_log(self, bot, mock_page):
        mock_page.url = "https://firefaucet.win/faucet"
        mock_page.locator.side_effect = Exception("DOM error")

        # Should not raise
        await bot._debug_log_page_elements()


# ===================================================================
# 10. Login edge cases
# ===================================================================

class TestLoginEdgeCases:

    @pytest.mark.asyncio
    async def test_login_already_logged_in_via_redirect(self, bot, mock_page):
        """If navigating to /login redirects away, treated as already logged in."""
        bot.safe_navigate = AsyncMock(return_value=True)
        mock_page.url = "https://firefaucet.win/dashboard"

        result = await bot.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_adblock_redirect(self, bot, mock_page):
        """Redirect to /adblock page causes login failure."""
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        mock_page.url = "https://firefaucet.win/login"

        # Dashboard elements not found
        no_el = _make_locator(count=0)
        mock_page.locator.return_value = no_el

        # After cloudflare, set URL to adblock
        original_url = mock_page.url

        async def side_effect_cf(*a, **kw):
            mock_page.url = "https://firefaucet.win/adblock"

        bot.handle_cloudflare.side_effect = side_effect_cf

        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_cloudflare_bypass_fails(self, bot, mock_page):
        """Login fails when cloudflare bypass fails."""
        bot.safe_navigate = AsyncMock(return_value=True)
        mock_page.url = "https://firefaucet.win/login"

        no_el = _make_locator(count=0)
        mock_page.locator.return_value = no_el

        bot.detect_cloudflare_block = AsyncMock(return_value=True)
        bot.bypass_cloudflare_with_retry = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_cloudflare_bypass_succeeds(self, bot, mock_page):
        """Login proceeds after cloudflare bypass succeeds."""
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.human_type = AsyncMock()
        mock_page.url = "https://firefaucet.win/login"

        no_el = _make_locator(count=0)
        dashboard_el = _make_locator(count=0)
        submit_btn = _make_locator(count=1, enabled=True)
        submit_btn.is_disabled = AsyncMock(return_value=False)

        def loc_dispatch(selector):
            if "submitbtn" in selector or "submit" in selector:
                return submit_btn
            if "user-balance" in selector or "dashboard" in selector:
                return dashboard_el
            return no_el

        mock_page.locator.side_effect = loc_dispatch
        bot.detect_cloudflare_block = AsyncMock(return_value=True)
        bot.bypass_cloudflare_with_retry = AsyncMock(return_value=True)

        # After submit, redirect to dashboard
        async def click_redirect(*a, **kw):
            mock_page.url = "https://firefaucet.win/dashboard"

        bot.human_like_click.side_effect = click_redirect

        result = await bot.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_uses_credentials_override(self, bot, mock_page, mock_settings):
        """When settings_account_override is set, it takes precedence."""
        bot.settings_account_override = {
            "username": "override_user",
            "password": "override_pass",
        }
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.human_type = AsyncMock()
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        mock_page.url = "https://firefaucet.win/login"

        no_el = _make_locator(count=0)
        submit_btn = _make_locator(count=1, enabled=True)
        submit_btn.is_disabled = AsyncMock(return_value=False)

        def loc_dispatch(selector):
            if "submitbtn" in selector or "submit" in selector:
                return submit_btn
            return no_el

        mock_page.locator.side_effect = loc_dispatch

        async def click_redirect(*a, **kw):
            mock_page.url = "https://firefaucet.win/dashboard"

        bot.human_like_click.side_effect = click_redirect

        result = await bot.login()
        assert result is True
        # Verify override credentials were used
        calls = bot.human_type.call_args_list
        assert any("override_user" in str(c) for c in calls)

    @pytest.mark.asyncio
    async def test_login_navigation_fails(self, bot, mock_page):
        """Login fails when safe_navigate returns False."""
        bot.safe_navigate = AsyncMock(return_value=False)

        result = await bot.login()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_submit_button_disabled_waits(self, bot, mock_page):
        """When submit button is disabled, wait_for_function is called."""
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.human_type = AsyncMock()
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        mock_page.url = "https://firefaucet.win/login"

        no_el = _make_locator(count=0)
        submit_btn = _make_locator(count=1, enabled=True)
        submit_btn.is_disabled = AsyncMock(return_value=True)

        def loc_dispatch(selector):
            if "submitbtn" in selector or "submit" in selector:
                return submit_btn
            return no_el

        mock_page.locator.side_effect = loc_dispatch

        async def click_redirect(*a, **kw):
            mock_page.url = "https://firefaucet.win/dashboard"

        bot.human_like_click.side_effect = click_redirect

        result = await bot.login()
        assert result is True
        # wait_for_function should have been called for the disabled button
        mock_page.wait_for_function.assert_called()

    @pytest.mark.asyncio
    async def test_login_no_submit_button_uses_form_submit(self, bot, mock_page):
        """When submit button is not found, JavaScript form.submit() is used."""
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.human_type = AsyncMock()
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        mock_page.url = "https://firefaucet.win/login"

        no_el = _make_locator(count=0)
        mock_page.locator.return_value = no_el

        async def click_redirect(*a, **kw):
            mock_page.url = "https://firefaucet.win/dashboard"

        # Will not be called (no submit button), but set up for post-login poll
        bot.human_like_click.side_effect = click_redirect

        # Simulate form submission redirecting to dashboard
        async def eval_side_effect(js, *a, **kw):
            if "forms[0].submit" in str(js):
                mock_page.url = "https://firefaucet.win/dashboard"
            return ""

        mock_page.evaluate.side_effect = eval_side_effect

        result = await bot.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_alternate_selectors_found(self, bot, mock_page):
        """When #username not found, alternate selectors are tried."""
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.human_type = AsyncMock()
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        mock_page.url = "https://firefaucet.win/login"

        # #username wait_for_selector raises
        mock_page.wait_for_selector.side_effect = Exception("Not found")

        alt_loc = _make_locator(count=1, visible=True)
        no_el = _make_locator(count=0)
        submit_btn = _make_locator(count=1, enabled=True)
        submit_btn.is_disabled = AsyncMock(return_value=False)

        def loc_dispatch(selector):
            if "input[name='username']" in selector:
                return alt_loc
            if "submitbtn" in selector or "submit" in selector:
                return submit_btn
            return no_el

        mock_page.locator.side_effect = loc_dispatch

        async def click_redirect(*a, **kw):
            mock_page.url = "https://firefaucet.win/dashboard"

        bot.human_like_click.side_effect = click_redirect

        result = await bot.login()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_error_message_detected_in_poll(self, bot, mock_page):
        """Error messages detected during post-login polling return False."""
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.human_type = AsyncMock()
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        mock_page.url = "https://firefaucet.win/login"

        no_el = _make_locator(count=0)
        submit_btn = _make_locator(count=1, enabled=True)
        submit_btn.is_disabled = AsyncMock(return_value=False)

        err_loc = _make_locator(
            count=1, visible=True, text="Invalid username or password"
        )

        def loc_dispatch(selector):
            if "submitbtn" in selector or "submit" in selector:
                return submit_btn
            if "alert-danger" in selector or "error-message" in selector:
                return err_loc
            return no_el

        mock_page.locator.side_effect = loc_dispatch

        result = await bot.login()
        assert result is False


# ===================================================================
# 11. Claim - Cloudflare and error classification
# ===================================================================

class TestClaimEdgeCases:

    @pytest.mark.asyncio
    async def test_claim_cloudflare_blocks_daily_page(self, bot, mock_page):
        """Cloudflare on daily page and bypass fails returns error."""
        bot.detect_cloudflare_block = AsyncMock(return_value=True)
        bot.bypass_cloudflare_with_retry = AsyncMock(return_value=False)

        result = await bot.claim()
        assert result.success is False
        assert result.status == "Cloudflare Block"
        assert result.next_claim_minutes == 15

    @pytest.mark.asyncio
    async def test_claim_cloudflare_blocks_faucet_page(self, bot, mock_page):
        """Cloudflare on faucet page returns error."""
        # Daily page OK
        bot.detect_cloudflare_block = AsyncMock(
            side_effect=[False, True]
        )
        bot.bypass_cloudflare_with_retry = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)

        result = await bot.claim()
        assert result.success is False
        assert result.status == "Cloudflare Block"

    @pytest.mark.asyncio
    async def test_claim_timeout_error_retries_in_5_min(self, bot, mock_page):
        """Timeout exceptions set next_claim_minutes to 5."""
        mock_page.goto.side_effect = Exception("Connection timeout reached")

        result = await bot.claim()
        assert result.success is False
        assert result.next_claim_minutes == 5
        assert "Network Error" in result.status

    @pytest.mark.asyncio
    async def test_claim_captcha_error_retries_in_10_min(self, bot, mock_page):
        """CAPTCHA exceptions set next_claim_minutes to 10."""
        mock_page.goto.side_effect = Exception("Captcha solver unavailable")

        result = await bot.claim()
        assert result.success is False
        assert result.next_claim_minutes == 10
        assert "CAPTCHA Error" in result.status

    @pytest.mark.asyncio
    async def test_claim_unknown_error_retries_in_30_min(self, bot, mock_page):
        """Unknown exceptions set next_claim_minutes to 30."""
        mock_page.goto.side_effect = Exception("Something unexpected")

        result = await bot.claim()
        assert result.success is False
        assert result.next_claim_minutes == 30

    @pytest.mark.asyncio
    async def test_claim_button_not_found_returns_failure(self, bot, mock_page):
        """When no faucet button selector matches, returns failure."""
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)

        no_btn = _make_locator(count=0)
        mock_page.locator.return_value = no_btn
        mock_page.evaluate.return_value = ""

        result = await bot.claim()
        assert result.success is False
        assert "Faucet Ready but Failed" in result.status

    @pytest.mark.asyncio
    async def test_claim_captcha_both_attempts_fail(self, bot, mock_page):
        """When CAPTCHA fails on both attempts, returns CAPTCHA Failed."""
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=False)

        no_btn = _make_locator(count=0)
        mock_page.locator.return_value = no_btn
        mock_page.evaluate.return_value = ""

        result = await bot.claim()
        assert result.success is False
        assert "CAPTCHA Failed" in result.status
        assert result.next_claim_minutes == 5

    @pytest.mark.asyncio
    async def test_claim_selects_turnstile_via_label(self, bot, mock_page):
        """Turnstile label is clicked when available on faucet page."""
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)

        turnstile_label = _make_locator(count=1, visible=True)
        no_btn = _make_locator(count=0)

        def loc_dispatch(sel):
            if "select-turnstile" in sel and "label" in sel:
                return turnstile_label
            return no_btn

        mock_page.locator.side_effect = loc_dispatch
        mock_page.evaluate.return_value = ""

        result = await bot.claim()
        turnstile_label.click.assert_called()


# ===================================================================
# 12. get_jobs
# ===================================================================

class TestGetJobs:

    def test_returns_five_jobs(self, bot):
        jobs = bot.get_jobs()
        assert len(jobs) == 5

    def test_job_names(self, bot):
        jobs = bot.get_jobs()
        names = [j.name for j in jobs]
        assert "FireFaucet Claim" in names
        assert "FireFaucet Daily Bonus" in names
        assert "FireFaucet PTC" in names
        assert "FireFaucet Shortlinks" in names
        assert "FireFaucet Withdraw" in names

    def test_job_priorities_ascending(self, bot):
        jobs = bot.get_jobs()
        priorities = [j.priority for j in jobs]
        assert priorities == sorted(priorities)

    def test_claim_job_runs_immediately(self, bot):
        jobs = bot.get_jobs()
        claim_job = [j for j in jobs if "Claim" in j.name][0]
        assert claim_job.next_run <= time.time() + 1

    def test_withdraw_job_runs_after_delay(self, bot):
        jobs = bot.get_jobs()
        wd_job = [j for j in jobs if "Withdraw" in j.name][0]
        assert wd_job.next_run > time.time()

    def test_all_jobs_have_fire_faucet_type(self, bot):
        jobs = bot.get_jobs()
        for j in jobs:
            assert j.faucet_type == "fire_faucet"


# ===================================================================
# 13. view_ptc_ads edge cases
# ===================================================================

class TestViewPtcAds:

    @pytest.mark.asyncio
    async def test_ptc_no_ads_available(self, bot, mock_page):
        """When no ad buttons found, exits gracefully."""
        no_ads = _make_locator(count=0)
        mock_page.locator.return_value = no_ads

        await bot.view_ptc_ads()
        # Should have navigated to PTC page
        mock_page.goto.assert_called()

    @pytest.mark.asyncio
    async def test_ptc_handles_captcha_on_ad(self, bot, mock_page):
        """Captcha on PTC ad page is solved."""
        ad_btn = _make_locator(count=1, visible=True)
        ad_btn_empty = _make_locator(count=0)
        captcha_img = _make_locator(count=1)
        submit_btn = _make_locator(count=1)
        no_loc = _make_locator(count=0)

        call_count = [0]

        def loc_dispatch(sel):
            if "div:nth-child(3) > a" in sel:
                call_count[0] += 1
                if call_count[0] <= 1:
                    return ad_btn
                return ad_btn_empty
            if "#description > img" in sel:
                return captcha_img
            if "#submit-button" in sel:
                return submit_btn
            return no_loc

        mock_page.locator.side_effect = loc_dispatch
        mock_page.query_selector.return_value = None

        await bot.view_ptc_ads()
        bot.solver.solve_captcha.assert_called()

    @pytest.mark.asyncio
    async def test_ptc_submit_button_not_found(self, bot, mock_page):
        """When submit button not found on ad, logs warning but continues."""
        ad_btn = _make_locator(count=1, visible=True)
        ad_btn_empty = _make_locator(count=0)
        no_captcha = _make_locator(count=0)
        no_submit = _make_locator(count=0)

        call_count = [0]

        def loc_dispatch(sel):
            if "div:nth-child(3) > a" in sel:
                call_count[0] += 1
                return ad_btn if call_count[0] <= 1 else ad_btn_empty
            if "#description > img" in sel:
                return no_captcha
            if "#submit-button" in sel:
                return no_submit
            return _make_locator()

        mock_page.locator.side_effect = loc_dispatch
        mock_page.query_selector.return_value = None

        await bot.view_ptc_ads()

    @pytest.mark.asyncio
    async def test_ptc_exception_handled(self, bot, mock_page):
        """Exception during PTC is caught and logged."""
        mock_page.goto.side_effect = Exception("PTC navigation failed")

        await bot.view_ptc_ads()  # should not raise


# ===================================================================
# 14. withdraw edge cases
# ===================================================================

class TestWithdrawEdgeCases:

    @pytest.mark.asyncio
    async def test_withdraw_no_success_message(self, bot, mock_page):
        """Withdrawal submitted but no success message returns failure."""
        coin_card = _make_locator(count=1)
        coin_btn = _make_locator(count=1)
        coin_card.first.locator = MagicMock(return_value=coin_btn)
        processor = _make_locator(count=1)
        submit = _make_locator(count=1)
        no_success = _make_locator(count=0)

        def loc_dispatch(sel):
            if ".card:has" in sel:
                return coin_card
            if "select[name='processor']" in sel:
                return processor
            if "Withdraw" in sel:
                return submit
            if "alert-success" in sel or "toast-success" in sel:
                return no_success
            return _make_locator()

        mock_page.locator.side_effect = loc_dispatch

        result = await bot.withdraw()
        assert result.success is False
        assert "no success message" in result.status

    @pytest.mark.asyncio
    async def test_withdraw_no_processor_select(self, bot, mock_page):
        """Withdrawal works without a processor select element."""
        coin_card = _make_locator(count=1)
        coin_btn = _make_locator(count=1)
        coin_card.first.locator = MagicMock(return_value=coin_btn)
        no_processor = _make_locator(count=0)
        submit = _make_locator(count=1)
        success_msg = _make_locator(count=1)

        def loc_dispatch(sel):
            if ".card:has" in sel:
                return coin_card
            if "select[name='processor']" in sel:
                return no_processor
            if "Withdraw" in sel:
                return submit
            if "alert-success" in sel or "toast-success" in sel:
                return success_msg
            return _make_locator()

        mock_page.locator.side_effect = loc_dispatch

        result = await bot.withdraw()
        assert result.success is True
        assert result.status == "Withdrawn"


# ===================================================================
# 15. daily_bonus_wrapper edge cases
# ===================================================================

class TestDailyBonusWrapper:

    @pytest.mark.asyncio
    async def test_daily_bonus_uses_turnstile_js_fallback(self, bot, mock_page):
        """When turnstile label is missing, JS fallback is used."""
        bot.login_wrapper = AsyncMock(return_value=True)

        no_unlock = _make_locator(count=0)
        no_label = _make_locator(count=0)
        turnstile_opt = _make_locator(count=1)
        claim_btn = _make_locator(count=1)

        def loc_dispatch(sel):
            if "a > button" in sel:
                return no_unlock
            if "label[for='select-turnstile']" in sel:
                return no_label
            if "#select-turnstile" in sel:
                return turnstile_opt
            if "form > button" in sel:
                return claim_btn
            return _make_locator()

        mock_page.locator.side_effect = loc_dispatch

        result = await bot.daily_bonus_wrapper(mock_page)
        assert result.success is True
        # JS evaluate should have been called for turnstile fallback
        mock_page.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_daily_bonus_not_available(self, bot, mock_page):
        """When claim button is missing, returns not available."""
        bot.login_wrapper = AsyncMock(return_value=True)

        no_loc = _make_locator(count=0)
        mock_page.locator.return_value = no_loc

        result = await bot.daily_bonus_wrapper(mock_page)
        assert result.success is False
        assert "Not Available" in result.status


# ===================================================================
# 16. claim_shortlinks
# ===================================================================

class TestClaimShortlinks:

    @pytest.mark.asyncio
    async def test_no_shortlinks_available(self, bot, mock_page):
        """Returns success with 'No shortlinks' when none found."""
        no_links = _make_locator(count=0)
        mock_page.locator.return_value = no_links

        result = await bot.claim_shortlinks(separate_context=False)
        assert result.success is True
        assert "No shortlinks" in result.status

    @pytest.mark.asyncio
    async def test_shortlinks_exception_handled(self, bot, mock_page):
        """Exceptions during shortlink processing return error result."""
        mock_page.goto.side_effect = Exception("Navigation failed")

        result = await bot.claim_shortlinks(separate_context=False)
        assert result.success is False
        assert "Error" in result.status

    @pytest.mark.asyncio
    async def test_shortlinks_solver_failure(self, bot, mock_page):
        """When shortlink solver fails, reports failure but continues."""
        with patch("faucets.firefaucet.ShortlinkSolver") as MockSL:
            sl = MockSL.return_value
            sl.solve = AsyncMock(return_value=False)

            links = _make_locator(count=1)
            links.nth = MagicMock(return_value=links)
            links.click = AsyncMock()
            links.get_attribute = AsyncMock(return_value="0.0001")

            no_links = _make_locator(count=0)

            call_count = [0]

            def loc_dispatch(sel):
                if "Visit Link" in sel or "shortlink" in sel:
                    call_count[0] += 1
                    return links if call_count[0] <= 2 else no_links
                return _make_locator()

            mock_page.locator.side_effect = loc_dispatch
            mock_page.query_selector.return_value = None

            result = await bot.claim_shortlinks(separate_context=False)
            # Even with solver failure, should not crash
            assert result.success is True

    @pytest.mark.asyncio
    async def test_shortlinks_solver_success_records_earnings(self, bot, mock_page):
        """Successful shortlink solving records earnings."""
        with patch("faucets.firefaucet.ShortlinkSolver") as MockSL:
            sl = MockSL.return_value
            sl.solve = AsyncMock(return_value=True)

            links = _make_locator(count=1)
            links.nth = MagicMock(return_value=links)
            links.click = AsyncMock()
            links.get_attribute = AsyncMock(return_value="0.0005")

            no_links = _make_locator(count=0)
            call_count = [0]

            def loc_dispatch(sel):
                if "Visit Link" in sel or "shortlink" in sel:
                    call_count[0] += 1
                    return links if call_count[0] <= 2 else no_links
                return _make_locator()

            mock_page.locator.side_effect = loc_dispatch
            mock_page.query_selector.return_value = None

            result = await bot.claim_shortlinks(separate_context=False)
            assert result.success is True
            assert result.amount > 0


# ===================================================================
# 17. shortlinks_wrapper
# ===================================================================

class TestShortlinksWrapper:

    @pytest.mark.asyncio
    async def test_shortlinks_wrapper_sets_page(self, bot, mock_page):
        """shortlinks_wrapper sets self.page to the provided page."""
        new_page = AsyncMock()
        bot.login_wrapper = AsyncMock(return_value=True)
        bot.claim_shortlinks = AsyncMock(return_value=ClaimResult(
            success=True, status="OK"
        ))

        result = await bot.shortlinks_wrapper(new_page)
        assert bot.page is new_page
        assert result.success is True


# ===================================================================
# 18. Turnstile-specific detection in detect_cloudflare_block
# ===================================================================

class TestTurnstileDetection:

    @pytest.mark.asyncio
    async def test_detects_verify_you_are_human_in_body(self, bot, mock_page):
        mock_page.title.return_value = "Normal Page"
        mock_page.evaluate.return_value = "verify you are human"
        mock_page.query_selector.return_value = None

        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_this_process_is_automatic(self, bot, mock_page):
        mock_page.title.return_value = "Normal Page"
        mock_page.evaluate.return_value = "this process is automatic"
        mock_page.query_selector.return_value = None

        result = await bot.detect_cloudflare_block()
        assert result is True

    @pytest.mark.asyncio
    async def test_detects_enable_javascript_and_cookies(self, bot, mock_page):
        mock_page.title.return_value = "Normal Page"
        mock_page.evaluate.return_value = "enable javascript and cookies to continue"
        mock_page.query_selector.return_value = None

        result = await bot.detect_cloudflare_block()
        assert result is True


# ===================================================================
# 19. Claim success with amount extraction from success message
# ===================================================================

class TestClaimAmountExtraction:

    @pytest.mark.asyncio
    async def test_amount_extracted_from_success_message(self, bot, mock_page):
        """Amount regex is applied to success message text."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.url = "https://firefaucet.win/faucet"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(
            return_value=(True, "You received 42.5 satoshi!")
        )
        bot._check_balance_change = AsyncMock(
            return_value=(False, "100")
        )
        bot.get_balance = AsyncMock(return_value="142")

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is True
        assert result.amount == "42.5"

    @pytest.mark.asyncio
    async def test_amount_unknown_when_no_regex_match(self, bot, mock_page):
        """When success message has no parseable amount, 'unknown' is returned."""
        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.url = "https://firefaucet.win/faucet"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(
            return_value=(True, "Reward added to your account!")
        )
        bot._check_balance_change = AsyncMock(
            return_value=(False, "100")
        )
        bot.get_balance = AsyncMock(return_value="142")

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is True
        assert result.amount == "unknown"


# ===================================================================
# 20. Claim shortlinks with shortlinks disabled
# ===================================================================

class TestClaimShortlinksDisabled:

    @pytest.mark.asyncio
    async def test_shortlinks_not_started_when_disabled(self, bot, mock_page, mock_settings):
        """When enable_shortlinks is False, shortlinks task is not spawned."""
        mock_settings.enable_shortlinks = False
        bot.settings = mock_settings

        faucet_btn = _make_locator(count=1, enabled=True, text="Get Reward")
        mock_page.title.return_value = "FireFaucet"
        mock_page.url = "https://firefaucet.win/faucet"

        bot._check_page_text_success = AsyncMock(return_value=None)
        bot._check_success_selectors = AsyncMock(
            return_value=(True, "Claimed successfully!")
        )
        bot._check_balance_change = AsyncMock(
            return_value=(False, "100")
        )
        bot.get_balance = AsyncMock(return_value="150")
        bot.claim_shortlinks = AsyncMock()

        result = await bot._click_and_verify_claim(
            faucet_btn, "100", [".user-balance"]
        )
        assert result.success is True
        # claim_shortlinks should NOT have been called
        bot.claim_shortlinks.assert_not_called()


# ===================================================================
# 21. Claim timer active path
# ===================================================================

class TestClaimTimerActive:

    @pytest.mark.asyncio
    async def test_claim_returns_timer_active_with_balance(self, bot, mock_page):
        """When timer > 0, returns success=True with Timer Active status."""
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.get_balance = AsyncMock(return_value="500")
        bot.get_timer = AsyncMock(return_value=25)

        no_loc = _make_locator(count=0)
        mock_page.locator.return_value = no_loc

        result = await bot.claim()
        assert result.success is True
        assert result.status == "Timer Active"
        assert result.next_claim_minutes == 25
        assert result.balance == "500"


# ===================================================================
# 22. Bypass cloudflare retry count increment
# ===================================================================

class TestBypassRetryCount:

    @pytest.mark.asyncio
    async def test_retry_count_incremented_on_failure(self, bot, mock_page):
        assert bot.cloudflare_retry_count == 0
        bot.detect_cloudflare_block = AsyncMock(return_value=True)
        mock_page.query_selector.return_value = None

        await bot.bypass_cloudflare_with_retry()
        assert bot.cloudflare_retry_count == 1

        await bot.bypass_cloudflare_with_retry()
        assert bot.cloudflare_retry_count == 2

    @pytest.mark.asyncio
    async def test_retry_count_reset_on_success(self, bot, mock_page):
        bot.cloudflare_retry_count = 5
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        mock_page.query_selector.return_value = None

        await bot.bypass_cloudflare_with_retry()
        assert bot.cloudflare_retry_count == 0


# ===================================================================
# 23. Login CAPTCHA handling
# ===================================================================

class TestLoginCaptchaHandling:

    @pytest.mark.asyncio
    async def test_login_proceeds_when_captcha_fails(self, bot, mock_page):
        """Login still attempts submit even if CAPTCHA fails (warning logged)."""
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.human_type = AsyncMock()
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.solver.solve_captcha = AsyncMock(return_value=False)
        mock_page.url = "https://firefaucet.win/login"

        submit_btn = _make_locator(count=1, enabled=True)
        submit_btn.is_disabled = AsyncMock(return_value=False)
        no_el = _make_locator(count=0)

        def loc_dispatch(sel):
            if "submitbtn" in sel or "submit" in sel:
                return submit_btn
            return no_el

        mock_page.locator.side_effect = loc_dispatch

        async def on_click(*a, **kw):
            mock_page.url = "https://firefaucet.win/dashboard"

        bot.human_like_click.side_effect = on_click

        result = await bot.login()
        # Login should still proceed despite CAPTCHA failure
        assert result is True
        # CAPTCHA solver should have been called
        bot.solver.solve_captcha.assert_called()


# ===================================================================
# 24. daily_bonus_wrapper unlocks daily bonus
# ===================================================================

class TestDailyBonusUnlock:

    @pytest.mark.asyncio
    async def test_daily_bonus_clicks_unlock_button(self, bot, mock_page):
        """When unlock button is visible, it is clicked."""
        bot.login_wrapper = AsyncMock(return_value=True)

        unlock = _make_locator(count=1, visible=True)
        no_label = _make_locator(count=0)
        no_turnstile = _make_locator(count=0)
        claim_btn = _make_locator(count=1)

        def loc_dispatch(sel):
            if "a > button" in sel:
                return unlock
            if "label[for='select-turnstile']" in sel:
                return no_label
            if "#select-turnstile" in sel:
                return no_turnstile
            if "form > button" in sel:
                return claim_btn
            return _make_locator()

        mock_page.locator.side_effect = loc_dispatch

        result = await bot.daily_bonus_wrapper(mock_page)
        assert result.success is True
        bot.human_like_click.assert_called()


# ===================================================================
# 25. claim full flow with faucet button found
# ===================================================================

class TestClaimFullFlow:

    @pytest.mark.asyncio
    async def test_claim_full_success_flow(self, bot, mock_page):
        """End-to-end claim: daily page -> faucet page -> button -> success."""
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.get_balance = AsyncMock(side_effect=["100", "150"])
        bot.get_timer = AsyncMock(return_value=0)
        bot.solver.solve_captcha = AsyncMock(return_value=True)

        # Turnstile label not found, select-turnstile found
        turnstile_label = _make_locator(count=0)
        turnstile_opt = _make_locator(count=1)
        no_loc = _make_locator(count=0)

        faucet_btn = _make_locator(count=1, visible=True, enabled=True, text="Get Reward")
        faucet_btn.first.get_attribute = AsyncMock(return_value=None)

        def loc_dispatch(sel):
            if "label[for='select-turnstile']" in sel:
                return turnstile_label
            if "#select-turnstile" in sel:
                return turnstile_opt
            if "#get_reward_button" in sel:
                return faucet_btn
            return no_loc

        mock_page.locator.side_effect = loc_dispatch
        mock_page.evaluate.return_value = ""
        mock_page.title.return_value = "FireFaucet"

        # Mock _click_and_verify_claim to return success
        bot._click_and_verify_claim = AsyncMock(
            return_value=ClaimResult(
                success=True,
                status="Claimed",
                next_claim_minutes=30,
                amount="50",
                balance="150",
            )
        )

        result = await bot.claim()
        assert result.success is True
        assert result.status == "Claimed"

    @pytest.mark.asyncio
    async def test_claim_screenshot_on_exception(self, bot, mock_page):
        """Exception during claim triggers screenshot."""
        mock_page.goto.side_effect = Exception("Something broke")

        result = await bot.claim()
        mock_page.screenshot.assert_called()
        assert result.success is False


# ===================================================================
# 26. Shortlinks wrapper exception path
# ===================================================================

class TestShortlinksWrapperExceptionPath:

    @pytest.mark.asyncio
    async def test_shortlinks_error_returned_on_exception(self, bot, mock_page):
        bot.login_wrapper = AsyncMock(return_value=True)
        bot.claim_shortlinks = AsyncMock(
            side_effect=Exception("shortlink nav error")
        )

        result = await bot.shortlinks_wrapper(mock_page)
        assert result.success is False
        assert "Error" in result.status
        assert result.next_claim_minutes == 120
