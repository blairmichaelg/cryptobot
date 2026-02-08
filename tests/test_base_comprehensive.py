"""
Comprehensive test suite for faucets/base.py - FaucetBot class.

Covers all methods not tested by test_faucet_base_coverage.py, including:
- Navigation, proxy, health checking
- Human interaction simulation (typing, clicking, scrolling, mouse)
- Cloudflare challenge detection/handling
- Login/claim/withdraw wrappers and analytics
- Job creation, PTC, failure state detection
- Profile management and credential resolution
"""

import asyncio
import json
import math
import os
import random
import tempfile
import time

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from faucets.base import ClaimResult, FaucetBot
from core.orchestrator import ErrorType


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    """Standard mock settings for FaucetBot."""
    settings = MagicMock()
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key"
    settings.capsolver_api_key = None
    settings.captcha_daily_budget = 5.0
    settings.captcha_provider_routing = "fixed"
    settings.captcha_provider_routing_min_samples = 20
    settings.headless = True
    settings.captcha_fallback_provider = None
    settings.captcha_fallback_api_key = None
    settings.get_account.return_value = {"username": "testuser", "password": "testpass"}
    settings.faucetpay_email = "fp@test.com"
    settings.btc_address = "bc1qxyz"
    settings.ltc_address = "ltc1abc"
    settings.doge_address = "Dxyz"
    settings.trx_address = "Txyz"
    settings.eth_address = "0xabc"
    settings.prefer_wallet_addresses = False
    settings.wallet_addresses = {}
    settings.navigation_timeout = 120000
    settings.exploration_frequency_minutes = 120
    settings.use_faucetpay = True
    settings.faucetpay_btc_address = "bc1qxyz"
    settings.faucetpay_ltc_address = "ltc1abc"
    settings.faucetpay_doge_address = "Dxyz"
    settings.faucetpay_trx_address = "Txyz"
    settings.faucetpay_eth_address = "0xabc"
    settings.timeout = 60000
    settings.generic_min_withdraw = 1000
    return settings


@pytest.fixture
def mock_page():
    """Standard mock Playwright page."""
    page = AsyncMock()
    page.url = "https://testfaucet.com"
    page.title = AsyncMock(return_value="Test Faucet")
    page.content = AsyncMock(return_value="<html>Normal page</html>")
    page.is_closed = MagicMock(return_value=False)

    # viewport
    page.viewport_size = {"width": 1280, "height": 720}

    # Locator support
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=0)
    loc.is_visible = AsyncMock(return_value=False)
    loc.bounding_box = AsyncMock(return_value={"x": 100, "y": 100, "width": 80, "height": 30})
    loc.text_content = AsyncMock(return_value="")
    loc.click = AsyncMock()
    loc.fill = AsyncMock()
    page.locator = MagicMock(return_value=loc)
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.evaluate = AsyncMock(return_value=None)
    page.mouse = AsyncMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.keyboard = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.goto = AsyncMock()
    page.reload = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    return page


@pytest.fixture
def bot(mock_settings, mock_page):
    """Create a FaucetBot with standard mocks."""
    b = FaucetBot(mock_settings, mock_page)
    b.solver = MagicMock()
    b.solver.close = AsyncMock()
    return b


# ---------------------------------------------------------------------------
# get_withdrawal_address
# ---------------------------------------------------------------------------

class TestGetWithdrawalAddress:
    """Test withdrawal address resolution."""

    def test_btc_address(self, bot, mock_settings):
        """Returns BTC address from settings."""
        addr = bot.get_withdrawal_address("BTC")
        assert addr == "bc1qxyz"

    def test_ltc_address(self, bot, mock_settings):
        """Returns LTC address from settings."""
        addr = bot.get_withdrawal_address("LTC")
        assert addr == "ltc1abc"

    def test_coin_normalization(self, bot, mock_settings):
        """Normalizes LITE to LTC, TRON to TRX, etc."""
        addr = bot.get_withdrawal_address("LITE")
        assert addr == "ltc1abc"

    def test_trx_address(self, bot, mock_settings):
        """Returns TRX address."""
        addr = bot.get_withdrawal_address("TRX")
        assert addr == "Txyz"

    def test_unknown_coin_returns_none(self, bot, mock_settings):
        """Unknown coin with no address returns None."""
        mock_settings.wallet_addresses = {}
        mock_settings.faucetpay_unknown_coin_999_address = None
        mock_settings.unknown_coin_999_withdrawal_address = None
        addr = bot.get_withdrawal_address("UNKNOWN_COIN_999")
        assert addr is None

    def test_prefer_wallet_addresses(self, bot, mock_settings):
        """When prefer_wallet_addresses is True, uses wallet dict first."""
        mock_settings.prefer_wallet_addresses = True
        mock_settings.wallet_addresses = {"BTC": "wallet_btc_addr"}
        addr = bot.get_withdrawal_address("BTC")
        assert addr == "wallet_btc_addr"

    def test_wallet_addresses_nested_dict(self, bot, mock_settings):
        """Handles nested dict with 'address' key in wallet_addresses."""
        mock_settings.prefer_wallet_addresses = True
        mock_settings.wallet_addresses = {"BTC": {"address": "nested_addr"}}
        addr = bot.get_withdrawal_address("BTC")
        assert addr == "nested_addr"


# ---------------------------------------------------------------------------
# random_delay
# ---------------------------------------------------------------------------

class TestRandomDelay:
    """Test random_delay method."""

    @pytest.mark.asyncio
    async def test_random_delay_basic(self, bot):
        """Random delay completes without error."""
        bot.human_profile = None  # Use legacy path
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bot.random_delay(0.01, 0.02)
            mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_random_delay_with_human_profile(self, bot):
        """With human_profile set, uses HumanProfile delay."""
        bot.human_profile = "normal"
        with patch("faucets.base.HumanProfile") as mock_hp, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_hp.get_delay.return_value = (1.0, 2.0)
            mock_hp.should_idle.return_value = (False, 0)
            await bot.random_delay()

    @pytest.mark.asyncio
    async def test_random_delay_idle_pause(self, bot):
        """When HumanProfile says to idle, pauses and returns."""
        bot.human_profile = "distracted"
        with patch("faucets.base.HumanProfile") as mock_hp, \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_hp.get_delay.return_value = (1.0, 2.0)
            mock_hp.should_idle.return_value = (True, 3.0)
            await bot.random_delay()
            # Should sleep for idle duration
            mock_sleep.assert_called_once_with(3.0)


# ---------------------------------------------------------------------------
# thinking_pause
# ---------------------------------------------------------------------------

class TestThinkingPause:
    """Test thinking_pause method."""

    @pytest.mark.asyncio
    async def test_thinking_pause_no_profile(self, bot):
        """Without human_profile, uses fallback delay."""
        bot.human_profile = None
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bot.thinking_pause()
            mock_sleep.assert_called_once()
            delay = mock_sleep.call_args[0][0]
            assert 1.0 <= delay <= 3.0

    @pytest.mark.asyncio
    async def test_thinking_pause_with_profile(self, bot):
        """With human_profile, uses HumanProfile.get_thinking_pause."""
        bot.human_profile = "cautious"
        with patch("faucets.base.HumanProfile") as mock_hp, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_hp.get_thinking_pause.return_value = 2.5
            await bot.thinking_pause()


# ---------------------------------------------------------------------------
# warm_up_page
# ---------------------------------------------------------------------------

class TestWarmUpPage:
    """Test warm_up_page method."""

    @pytest.mark.asyncio
    async def test_warm_up_page_runs(self, bot, mock_page):
        """Warm-up page executes without error."""
        with patch("faucets.base.StealthHub") as mock_sh, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_sh.pre_navigation_warmup = AsyncMock()
            await bot.warm_up_page()

    @pytest.mark.asyncio
    async def test_warm_up_page_exception_caught(self, bot, mock_page):
        """Exceptions in warm_up_page are caught and don't propagate."""
        mock_page.mouse.move = AsyncMock(side_effect=Exception("Mouse error"))
        with patch("faucets.base.StealthHub") as mock_sh, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_sh.pre_navigation_warmup = AsyncMock()
            await bot.warm_up_page()  # Should not raise


# ---------------------------------------------------------------------------
# simulate_tab_activity
# ---------------------------------------------------------------------------

class TestSimulateTabActivity:
    """Test simulate_tab_activity method."""

    @pytest.mark.asyncio
    async def test_simulate_tab_activity_runs(self, bot, mock_page):
        """Tab activity simulation completes."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.simulate_tab_activity()
            mock_page.evaluate.assert_called()


# ---------------------------------------------------------------------------
# load_human_profile / get_or_create_human_profile
# ---------------------------------------------------------------------------

class TestLoadHumanProfile:
    """Test human profile loading."""

    def test_load_human_profile_new(self, bot):
        """Creates new profile when none exists."""
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("faucets.base.HumanProfile") as mock_hp:
            mock_hp.get_random_profile.return_value = "fast"
            bot.settings.config_dir = tmpdir
            profile = bot.load_human_profile("new_user")
            assert profile == "fast"
            assert bot.human_profile == "fast"

    def test_load_human_profile_existing(self, bot):
        """Loads existing profile from fingerprint file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fp_file = os.path.join(tmpdir, "profile_fingerprints.json")
            with open(fp_file, "w") as f:
                json.dump({"existing_user": {"human_profile": "cautious"}}, f)
            with patch("faucets.base.Path") as MockPath:
                # Make Path(__file__).parent.parent / "config" resolve to tmpdir
                mock_file_path = MagicMock()
                MockPath.return_value = mock_file_path
                from pathlib import Path as RealPath
                mock_file_path.parent.parent.__truediv__.return_value = RealPath(tmpdir)
                profile = bot.load_human_profile("existing_user")
            assert profile == "cautious"


# ---------------------------------------------------------------------------
# check_page_health
# ---------------------------------------------------------------------------

class TestCheckPageHealth:
    """Test check_page_health method."""

    @pytest.mark.asyncio
    async def test_page_healthy(self, bot, mock_page):
        """Returns True for healthy page."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        result = await bot.check_page_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_page_closed(self, bot, mock_page):
        """Returns False for closed page."""
        mock_page.is_closed.return_value = True
        result = await bot.check_page_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_page_none(self, bot):
        """Returns False when page is None."""
        bot.page = None
        result = await bot.check_page_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_page_timeout(self, bot, mock_page):
        """Returns False when page operation times out."""
        mock_page.evaluate = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await bot.check_page_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_page_exception(self, bot, mock_page):
        """Returns False on general exception."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("crashed"))
        result = await bot.check_page_health()
        assert result is False


# ---------------------------------------------------------------------------
# safe_page_operation
# ---------------------------------------------------------------------------

class TestSafePageOperation:
    """Test safe_page_operation wrapper."""

    @pytest.mark.asyncio
    async def test_success(self, bot, mock_page):
        """Returns result on success."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        op = AsyncMock(return_value="result")
        result = await bot.safe_page_operation("test_op", op)
        assert result == "result"

    @pytest.mark.asyncio
    async def test_exception_returns_none(self, bot, mock_page):
        """Returns None on exception."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        op = AsyncMock(side_effect=Exception("fail"))
        result = await bot.safe_page_operation("test_op", op)
        assert result is None


# ---------------------------------------------------------------------------
# safe_click / safe_fill / safe_goto
# ---------------------------------------------------------------------------

class TestSafeOperations:
    """Test safe_click, safe_fill, safe_goto helpers."""

    @pytest.mark.asyncio
    async def test_safe_click_success(self, bot, mock_page):
        """safe_click returns True on success."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        loc = AsyncMock()
        loc.click = AsyncMock()
        result = await bot.safe_click(loc)
        assert result is True

    @pytest.mark.asyncio
    async def test_safe_click_string_selector(self, bot, mock_page):
        """safe_click with string selector creates locator."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        loc = AsyncMock()
        loc.click = AsyncMock()
        mock_page.locator.return_value = loc
        result = await bot.safe_click("#btn")
        assert result is True

    @pytest.mark.asyncio
    async def test_safe_fill_success(self, bot, mock_page):
        """safe_fill returns True on success."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        loc = AsyncMock()
        loc.fill = AsyncMock()
        result = await bot.safe_fill(loc, "text")
        assert result is True

    @pytest.mark.asyncio
    async def test_safe_goto_success(self, bot, mock_page):
        """safe_goto returns True on success."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        result = await bot.safe_goto("https://example.com")
        assert result is True


# ---------------------------------------------------------------------------
# human_like_click
# ---------------------------------------------------------------------------

class TestHumanLikeClick:
    """Test human_like_click method."""

    @pytest.mark.asyncio
    async def test_click_with_bounding_box(self, bot, mock_page):
        """Clicks with Bezier movement when bounding box available."""
        loc = AsyncMock()
        loc.scroll_into_view_if_needed = AsyncMock()
        loc.is_visible = AsyncMock(return_value=True)
        loc.bounding_box = AsyncMock(return_value={
            "x": 100, "y": 200, "width": 80, "height": 30
        })
        loc.click = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch.object(bot, "remove_overlays", new_callable=AsyncMock), \
             patch.object(bot, "_bezier_mouse_move", new_callable=AsyncMock):
            await bot.human_like_click(loc)
            mock_page.mouse.click.assert_called()

    @pytest.mark.asyncio
    async def test_click_fallback_no_bbox(self, bot, mock_page):
        """Falls back to simple click when no bounding box."""
        loc = AsyncMock()
        loc.scroll_into_view_if_needed = AsyncMock()
        loc.is_visible = AsyncMock(return_value=True)
        loc.bounding_box = AsyncMock(return_value=None)
        loc.click = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch.object(bot, "remove_overlays", new_callable=AsyncMock):
            await bot.human_like_click(loc)
            loc.click.assert_called()


# ---------------------------------------------------------------------------
# _bezier_mouse_move
# ---------------------------------------------------------------------------

class TestBezierMouseMove:
    """Test Bezier curve mouse movement."""

    @pytest.mark.asyncio
    async def test_bezier_move_basic(self, bot, mock_page):
        """Bezier movement produces multiple mouse moves."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot._bezier_mouse_move(0, 0, 100, 100)
            assert mock_page.mouse.move.call_count > 1

    @pytest.mark.asyncio
    async def test_bezier_move_zero_distance(self, bot, mock_page):
        """Zero-distance move still completes."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot._bezier_mouse_move(50, 50, 50, 50)


# ---------------------------------------------------------------------------
# remove_overlays
# ---------------------------------------------------------------------------

class TestRemoveOverlays:
    """Test overlay removal."""

    @pytest.mark.asyncio
    async def test_remove_overlays(self, bot, mock_page):
        """Overlay removal executes JS evaluation."""
        await bot.remove_overlays()
        mock_page.evaluate.assert_called()


# ---------------------------------------------------------------------------
# human_type
# ---------------------------------------------------------------------------

class TestHumanType:
    """Test human_type keystroke simulation."""

    @pytest.mark.asyncio
    async def test_human_type_basic(self, bot, mock_page):
        """Types text character by character."""
        loc = AsyncMock()
        loc.click = AsyncMock()
        loc.press_sequentially = AsyncMock()
        mock_page.locator.return_value = loc

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.human_type("#input", "hello")

    @pytest.mark.asyncio
    async def test_human_type_with_locator(self, bot, mock_page):
        """Works with Locator input (not string)."""
        loc = AsyncMock()
        loc.click = AsyncMock()
        loc.press_sequentially = AsyncMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.human_type(loc, "test")

    @pytest.mark.asyncio
    async def test_human_type_with_human_profile(self, bot, mock_page):
        """Uses HumanProfile typing speed when available."""
        bot.human_profile = "normal"
        loc = AsyncMock()
        loc.click = AsyncMock()
        loc.press_sequentially = AsyncMock()
        mock_page.locator.return_value = loc

        with patch("faucets.base.HumanProfile") as mock_hp, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_hp.get_typing_speed.return_value = (80, 150)
            await bot.human_type("#input", "hi")


# ---------------------------------------------------------------------------
# idle_mouse
# ---------------------------------------------------------------------------

class TestIdleMouse:
    """Test idle_mouse simulation."""

    @pytest.mark.asyncio
    async def test_idle_mouse_basic(self, bot, mock_page):
        """Idle mouse moves within viewport."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.idle_mouse(0.5)
            assert mock_page.mouse.move.call_count > 0


# ---------------------------------------------------------------------------
# simulate_reading
# ---------------------------------------------------------------------------

class TestSimulateReading:
    """Test reading simulation."""

    @pytest.mark.asyncio
    async def test_simulate_reading_basic(self, bot, mock_page):
        """Reading simulation completes without error."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.simulate_reading(0.5)


# ---------------------------------------------------------------------------
# natural_scroll
# ---------------------------------------------------------------------------

class TestNaturalScroll:
    """Test physics-based scrolling."""

    @pytest.mark.asyncio
    async def test_scroll_down(self, bot, mock_page):
        """Scrolls down with momentum simulation."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.natural_scroll(300, direction=1)
            assert mock_page.mouse.wheel.call_count > 0

    @pytest.mark.asyncio
    async def test_scroll_up(self, bot, mock_page):
        """Scrolls up with momentum simulation."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.natural_scroll(200, direction=-1)

    @pytest.mark.asyncio
    async def test_scroll_exception_fallback(self, bot, mock_page):
        """Falls back gracefully on error without raising."""
        mock_page.mouse.wheel = AsyncMock(side_effect=Exception("wheel err"))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.natural_scroll(100)
            # Fallback also uses mouse.wheel, which fails silently
            assert mock_page.mouse.wheel.call_count > 0


# ---------------------------------------------------------------------------
# natural_mouse_drift
# ---------------------------------------------------------------------------

class TestNaturalMouseDrift:
    """Test Perlin-noise-like mouse drift."""

    @pytest.mark.asyncio
    async def test_drift_basic(self, bot, mock_page):
        """Mouse drift produces multiple moves."""
        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("time.time") as mock_time:
            # Simulate progression: start=0, 0.05, 0.10, 0.15, ... exceed duration
            mock_time.side_effect = [0.0] + [i * 0.05 for i in range(100)] + [10.0] * 10
            await bot.natural_mouse_drift(0.2)

    @pytest.mark.asyncio
    async def test_drift_exception_fallback(self, bot, mock_page):
        """Falls back to sleep on exception."""
        mock_page.mouse.move = AsyncMock(side_effect=Exception("drift err"))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bot.natural_mouse_drift(0.1)
            mock_sleep.assert_called()


# ---------------------------------------------------------------------------
# random_micro_interaction
# ---------------------------------------------------------------------------

class TestRandomMicroInteraction:
    """Test micro-interaction during waits."""

    @pytest.mark.asyncio
    async def test_micro_interaction_runs(self, bot, mock_page):
        """Micro-interaction completes without error."""
        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("random.random", return_value=0.05):  # Hover path
            await bot.random_micro_interaction()


# ---------------------------------------------------------------------------
# random_focus_blur
# ---------------------------------------------------------------------------

class TestRandomFocusBlur:
    """Test focus/blur simulation."""

    @pytest.mark.asyncio
    async def test_focus_blur_basic(self, bot, mock_page):
        """Focus blur executes JS events."""
        bot.human_profile = None
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.random_focus_blur()
            mock_page.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_focus_blur_with_profile(self, bot, mock_page):
        """Uses HumanProfile for away time."""
        bot.human_profile = "normal"
        with patch("faucets.base.HumanProfile") as mock_hp, \
             patch("asyncio.sleep", new_callable=AsyncMock):
            mock_hp.get_away_time.return_value = 2.0
            await bot.random_focus_blur()


# ---------------------------------------------------------------------------
# human_wait
# ---------------------------------------------------------------------------

class TestHumanWait:
    """Test human_wait with micro-interactions."""

    @pytest.mark.asyncio
    async def test_short_wait(self, bot):
        """Short wait (< 3s) just sleeps directly."""
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await bot.human_wait(1.0, with_interactions=False)
            mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_long_wait_no_interactions(self, bot):
        """Long wait without interactions just sleeps in chunks."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.human_wait(5.0, with_interactions=False)

    @pytest.mark.asyncio
    async def test_long_wait_with_interactions(self, bot, mock_page):
        """Long wait with interactions calls micro-interactions."""
        with patch("asyncio.sleep", new_callable=AsyncMock), \
             patch.object(bot, "random_micro_interaction",
                          new_callable=AsyncMock) as mock_micro:
            await bot.human_wait(10.0, with_interactions=True)
            assert mock_micro.call_count >= 1


# ---------------------------------------------------------------------------
# handle_cloudflare
# ---------------------------------------------------------------------------

class TestHandleCloudflare:
    """Test Cloudflare challenge detection and handling."""

    @pytest.mark.asyncio
    async def test_no_cloudflare(self, bot, mock_page):
        """Returns True quickly when no CF detected."""
        mock_page.title = AsyncMock(return_value="Normal Page Title")
        mock_page.locator.return_value.count = AsyncMock(return_value=0)
        mock_page.locator.return_value.is_visible = AsyncMock(return_value=False)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await bot.handle_cloudflare(max_wait_seconds=5)
        assert result is True

    @pytest.mark.asyncio
    async def test_cloudflare_detected_then_clears(self, bot, mock_page):
        """CF challenge detected then resolves."""
        call_count = 0

        async def varying_title():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return "Just a moment..."
            return "Normal Page"

        mock_page.title = varying_title
        mock_page.locator.return_value.count = AsyncMock(return_value=0)
        mock_page.locator.return_value.is_visible = AsyncMock(return_value=False)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await bot.handle_cloudflare(max_wait_seconds=10)
        assert result is True

    @pytest.mark.asyncio
    async def test_page_crash_detection(self, bot, mock_page):
        """Returns False if page crashes during CF check."""
        with patch.object(bot, "detect_page_crash",
                          new_callable=AsyncMock, return_value=False):
            result = await bot.handle_cloudflare(max_wait_seconds=3)
        assert result is False


# ---------------------------------------------------------------------------
# detect_page_crash
# ---------------------------------------------------------------------------

class TestDetectPageCrash:
    """Test page crash detection."""

    @pytest.mark.asyncio
    async def test_healthy_page(self, bot, mock_page):
        """Returns True for responsive page."""
        mock_page.evaluate = AsyncMock(return_value="complete")
        result = await bot.detect_page_crash()
        assert result is True

    @pytest.mark.asyncio
    async def test_crashed_page_timeout(self, bot, mock_page):
        """Returns False when page times out."""
        mock_page.evaluate = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await bot.detect_page_crash()
        assert result is False

    @pytest.mark.asyncio
    async def test_crashed_page_exception(self, bot, mock_page):
        """Returns False on unexpected exception."""
        mock_page.evaluate = AsyncMock(side_effect=Exception("dead"))
        result = await bot.detect_page_crash()
        assert result is False


# ---------------------------------------------------------------------------
# safe_navigate
# ---------------------------------------------------------------------------

class TestSafeNavigate:
    """Test safe_navigate with retry logic."""

    @pytest.mark.asyncio
    async def test_success_first_attempt(self, bot, mock_page):
        """Succeeds on first navigation attempt."""
        result = await bot.safe_navigate("https://test.com")
        assert result is True
        mock_page.goto.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, bot, mock_page):
        """Retries on timeout, succeeds on second attempt."""
        mock_page.goto = AsyncMock(
            side_effect=[Exception("Timeout 60000ms exceeded"), None]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await bot.safe_navigate("https://test.com")
        assert result is True
        assert mock_page.goto.call_count == 2

    @pytest.mark.asyncio
    async def test_all_attempts_fail(self, bot, mock_page):
        """Returns False when all attempts fail."""
        mock_page.goto = AsyncMock(
            side_effect=[Exception("err1"), Exception("err2")]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await bot.safe_navigate("https://test.com")
        assert result is False

    @pytest.mark.asyncio
    async def test_timeout_error(self, bot, mock_page):
        """Handles timeout error with retry."""
        mock_page.goto = AsyncMock(
            side_effect=[Exception("Timeout 60000ms exceeded"), None]
        )
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await bot.safe_navigate("https://test.com")
        assert result is True


# ---------------------------------------------------------------------------
# close_popups
# ---------------------------------------------------------------------------

class TestClosePopups:
    """Test popup/cookie banner dismissal."""

    @pytest.mark.asyncio
    async def test_close_popups_runs(self, bot, mock_page):
        """Popup closing iterates selectors without error."""
        loc = AsyncMock()
        loc.is_visible = AsyncMock(return_value=False)
        mock_page.locator.return_value = loc
        await bot.close_popups()

    @pytest.mark.asyncio
    async def test_close_visible_popup(self, bot, mock_page):
        """Clicks visible popup dismiss button."""
        loc = AsyncMock()
        loc.is_visible = AsyncMock(return_value=True)
        loc.click = AsyncMock()
        mock_page.locator.return_value = loc
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.close_popups()


# ---------------------------------------------------------------------------
# check_failure_states
# ---------------------------------------------------------------------------

class TestCheckFailureStates:
    """Test failure state detection."""

    @pytest.mark.asyncio
    async def test_no_failure(self, bot, mock_page):
        """Returns None when page is healthy."""
        mock_page.title = AsyncMock(return_value="Normal Page")
        mock_page.content = AsyncMock(return_value="<html>Normal healthy page</html>")
        mock_page.locator.return_value.count = AsyncMock(return_value=0)
        mock_page.locator.return_value.is_visible = AsyncMock(return_value=False)
        mock_page.url = "https://faucet.com/claim"

        result = await bot.check_failure_states()
        assert result is None

    @pytest.mark.asyncio
    async def test_cloudflare_title(self, bot, mock_page):
        """Detects Cloudflare from page title."""
        mock_page.title = AsyncMock(return_value="Just a moment...")
        mock_page.content = AsyncMock(return_value="<html>Checking your browser</html>")
        result = await bot.check_failure_states()
        assert result is not None
        assert "Cloudflare" in result or "Maintenance" in result

    @pytest.mark.asyncio
    async def test_proxy_detected(self, bot, mock_page):
        """Detects proxy/VPN message in page content."""
        mock_page.title = AsyncMock(return_value="Normal Title")
        mock_page.content = AsyncMock(
            return_value="<html>VPN or proxy detected - access denied</html>"
        )
        mock_page.locator.return_value.count = AsyncMock(return_value=0)
        mock_page.url = "https://faucet.com"

        result = await bot.check_failure_states()
        assert result == "Proxy Detected"

    @pytest.mark.asyncio
    async def test_exception_caught(self, bot, mock_page):
        """Exception in sub-checks is caught and returns None."""
        mock_page.content = AsyncMock(return_value="<html>normal page</html>")
        mock_page.title = AsyncMock(return_value="Normal Page")
        mock_page.url = "https://faucet.com"
        # Force exception in the CF element check (which is in try/except)
        mock_page.locator.return_value.count = AsyncMock(
            side_effect=Exception("page dead")
        )
        mock_page.evaluate = AsyncMock(side_effect=Exception("page dead"))
        result = await bot.check_failure_states()
        assert result is None


# ---------------------------------------------------------------------------
# is_logged_in / login / claim / withdraw (abstract base methods)
# ---------------------------------------------------------------------------

class TestAbstractMethods:
    """Test base implementations of abstract methods."""

    @pytest.mark.asyncio
    async def test_is_logged_in_returns_false(self, bot):
        """Base is_logged_in returns False."""
        result = await bot.is_logged_in()
        assert result is False

    @pytest.mark.asyncio
    async def test_login_raises(self, bot):
        """Base login raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await bot.login()

    @pytest.mark.asyncio
    async def test_claim_raises(self, bot):
        """Base claim raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await bot.claim()

    @pytest.mark.asyncio
    async def test_withdraw_returns_not_implemented(self, bot):
        """Base withdraw returns failure result."""
        result = await bot.withdraw()
        assert result.success is False
        assert "Not Implemented" in result.status


# ---------------------------------------------------------------------------
# get_jobs
# ---------------------------------------------------------------------------

class TestGetJobs:
    """Test job creation for scheduler."""

    def test_basic_jobs(self, bot):
        """Creates claim + withdraw jobs."""
        bot.faucet_name = "TestFaucet"
        jobs = bot.get_jobs()
        assert len(jobs) >= 2
        assert any("Claim" in j.name for j in jobs)
        assert any("Withdraw" in j.name for j in jobs)

    def test_ptc_job_when_overridden(self, bot):
        """Creates PTC job when view_ptc_ads is overridden."""

        class PTCBot(FaucetBot):
            async def view_ptc_ads(self):
                pass  # Override the base

        ptc_bot = PTCBot(bot.settings, bot.page)
        ptc_bot.faucet_name = "PTCFaucet"
        jobs = ptc_bot.get_jobs()
        assert any("PTC" in j.name for j in jobs)


# ---------------------------------------------------------------------------
# view_ptc_ads / get_earning_tasks
# ---------------------------------------------------------------------------

class TestPTCAndTasks:
    """Test PTC and earning task methods."""

    @pytest.mark.asyncio
    async def test_view_ptc_ads_base(self, bot):
        """Base view_ptc_ads logs warning."""
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await bot.view_ptc_ads()

    def test_get_earning_tasks_no_ptc(self, bot):
        """Without PTC override, only claim task returned."""
        tasks = bot.get_earning_tasks()
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Faucet Claim"

    def test_get_earning_tasks_with_ptc(self, bot):
        """With PTC override, claim + PTC tasks returned."""

        class PTCBot(FaucetBot):
            async def view_ptc_ads(self):
                pass

        ptc_bot = PTCBot(bot.settings, bot.page)
        tasks = ptc_bot.get_earning_tasks()
        assert len(tasks) == 2
        assert any(t["name"] == "PTC Ads" for t in tasks)


# ---------------------------------------------------------------------------
# login_wrapper
# ---------------------------------------------------------------------------

class TestLoginWrapper:
    """Test login wrapper orchestration."""

    @pytest.mark.asyncio
    async def test_already_logged_in(self, bot, mock_page):
        """Returns True when already logged in."""
        with patch.object(bot, "is_logged_in", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "handle_cloudflare", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "warm_up_page", new_callable=AsyncMock), \
             patch.object(bot, "check_failure_states", new_callable=AsyncMock,
                          return_value=None), \
             patch.object(bot, "load_human_profile", return_value="fast"), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.login_wrapper()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_succeeds(self, bot, mock_page):
        """Returns True when login() succeeds."""
        with patch.object(bot, "is_logged_in", new_callable=AsyncMock,
                          return_value=False), \
             patch.object(bot, "login", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "handle_cloudflare", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "warm_up_page", new_callable=AsyncMock), \
             patch.object(bot, "check_failure_states", new_callable=AsyncMock,
                          return_value=None), \
             patch.object(bot, "load_human_profile", return_value="fast"), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.login_wrapper()
        assert result is True

    @pytest.mark.asyncio
    async def test_login_fails(self, bot, mock_page):
        """Returns False when login() fails twice."""
        with patch.object(bot, "is_logged_in", new_callable=AsyncMock,
                          return_value=False), \
             patch.object(bot, "login", new_callable=AsyncMock,
                          return_value=False), \
             patch.object(bot, "handle_cloudflare", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "warm_up_page", new_callable=AsyncMock), \
             patch.object(bot, "check_failure_states", new_callable=AsyncMock,
                          return_value=None), \
             patch.object(bot, "load_human_profile", return_value="fast"), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.login_wrapper()
        assert result is False

    @pytest.mark.asyncio
    async def test_failure_state_detected(self, bot, mock_page):
        """Reloads and retries on failure state."""
        call_count = 0

        async def varying_failure():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return "Proxy Detected"
            return None

        with patch.object(bot, "is_logged_in", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "handle_cloudflare", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "warm_up_page", new_callable=AsyncMock), \
             patch.object(bot, "check_failure_states",
                          side_effect=varying_failure), \
             patch.object(bot, "load_human_profile", return_value="fast"), \
             patch.object(bot, "natural_mouse_drift", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("random.random", return_value=0.99):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.login_wrapper()
        assert result is True


# ---------------------------------------------------------------------------
# claim_wrapper
# ---------------------------------------------------------------------------

class TestClaimWrapper:
    """Test claim_wrapper lifecycle."""

    @pytest.mark.asyncio
    async def test_successful_claim(self, bot, mock_page):
        """Full successful claim lifecycle."""
        claim_result = ClaimResult(
            success=True, status="Claimed!", amount="100", balance="500",
            next_claim_minutes=60
        )
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "claim", new_callable=AsyncMock,
                          return_value=claim_result), \
             patch.object(bot, "warm_up_page", new_callable=AsyncMock), \
             patch.object(bot, "_record_analytics", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("random.random", return_value=0.99):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.claim_wrapper(mock_page)

        assert result.success is True
        assert result.next_claim_minutes == 60

    @pytest.mark.asyncio
    async def test_claim_login_fails(self, bot, mock_page):
        """Returns failure when login fails."""
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=False), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.claim_wrapper(mock_page)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_claim_bool_result(self, bot, mock_page):
        """Converts bare bool True from claim() to ClaimResult."""
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "claim", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "warm_up_page", new_callable=AsyncMock), \
             patch.object(bot, "_record_analytics", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("random.random", return_value=0.99):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.claim_wrapper(mock_page)

        assert isinstance(result, ClaimResult)

    @pytest.mark.asyncio
    async def test_claim_exception(self, bot, mock_page):
        """Returns error result on claim exception."""
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "claim", new_callable=AsyncMock,
                          side_effect=Exception("claim crashed")), \
             patch.object(bot, "warm_up_page", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("random.random", return_value=0.99):
            bot.settings_account_override = {"username": "u", "password": "p"}
            result = await bot.claim_wrapper(mock_page)

        assert result.success is False
        assert result.error_type is not None


# ---------------------------------------------------------------------------
# withdraw_wrapper
# ---------------------------------------------------------------------------

class TestWithdrawWrapper:
    """Test withdraw_wrapper lifecycle."""

    @pytest.mark.asyncio
    async def test_successful_withdrawal(self, bot, mock_page):
        """Full successful withdrawal lifecycle."""
        wd_result = ClaimResult(
            success=True, status="Withdrawal sent",
            amount="1000", balance="500",
            next_claim_minutes=1440
        )
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "get_balance", new_callable=AsyncMock,
                          return_value="5000"), \
             patch.object(bot, "withdraw", new_callable=AsyncMock,
                          return_value=wd_result), \
             patch("asyncio.sleep", new_callable=AsyncMock), \
             patch("core.withdrawal_analytics.get_analytics") as mock_analytics:
            mock_tracker = MagicMock()
            mock_analytics.return_value = mock_tracker
            result = await bot.withdraw_wrapper(mock_page)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_withdrawal_login_fails(self, bot, mock_page):
        """Returns failure when login fails."""
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=False):
            result = await bot.withdraw_wrapper(mock_page)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_withdrawal_exception(self, bot, mock_page):
        """Exception from get_balance propagates (no top-level catch)."""
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "get_balance", new_callable=AsyncMock,
                          side_effect=Exception("balance err")):
            with pytest.raises(Exception, match="balance err"):
                await bot.withdraw_wrapper(mock_page)


# ---------------------------------------------------------------------------
# ptc_wrapper
# ---------------------------------------------------------------------------

class TestPtcWrapper:
    """Test PTC wrapper."""

    @pytest.mark.asyncio
    async def test_ptc_success(self, bot, mock_page):
        """PTC wrapper succeeds after login."""
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "view_ptc_ads", new_callable=AsyncMock):
            result = await bot.ptc_wrapper(mock_page)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_ptc_login_fails(self, bot, mock_page):
        """PTC wrapper fails when login fails."""
        with patch.object(bot, "login_wrapper", new_callable=AsyncMock,
                          return_value=False):
            result = await bot.ptc_wrapper(mock_page)

        assert result.success is False


# ---------------------------------------------------------------------------
# _record_analytics
# ---------------------------------------------------------------------------

class TestRecordAnalytics:
    """Test analytics recording."""

    @pytest.mark.asyncio
    async def test_record_success(self, bot):
        """Records claim analytics for successful result."""
        result = ClaimResult(
            success=True, status="Claimed 100 satoshi",
            amount="100", balance="5000", next_claim_minutes=60
        )
        bot.faucet_name = "FreeBitcoin"
        with patch("faucets.base.get_tracker") as mock_get:
            mock_tracker = MagicMock()
            mock_get.return_value = mock_tracker
            await bot._record_analytics(result)
            mock_tracker.record_claim.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_exception_caught(self, bot):
        """Analytics exceptions don't propagate."""
        result = ClaimResult(success=True, status="OK", amount="50")
        with patch("faucets.base.get_tracker",
                   side_effect=Exception("tracker err")):
            await bot._record_analytics(result)  # Should not raise


# ---------------------------------------------------------------------------
# _normalize_claim_amount
# ---------------------------------------------------------------------------

class TestNormalizeClaimAmount:
    """Test amount normalization for analytics."""

    def test_zero_amount(self, bot):
        """Zero returns zero."""
        assert bot._normalize_claim_amount(0.0, "0", "BTC") == 0.0

    def test_fractional_btc(self, bot):
        """Fractional BTC normalized to satoshis."""
        result = bot._normalize_claim_amount(0.00000100, "0.00000100", "BTC")
        assert result == pytest.approx(100.0, rel=0.1)

    def test_whole_satoshis(self, bot):
        """Integer satoshis stay as-is."""
        result = bot._normalize_claim_amount(100, "100", "BTC")
        assert result == 100.0

    def test_negative_amount(self, bot):
        """Negative returns the value directly."""
        result = bot._normalize_claim_amount(-5.0, "-5", "BTC")
        assert result == -5.0


# ---------------------------------------------------------------------------
# _detect_currency_from_text
# ---------------------------------------------------------------------------

class TestDetectCurrencyFromText:
    """Test currency detection from text."""

    def test_btc_symbol(self):
        """Detects BTC from text."""
        assert FaucetBot._detect_currency_from_text("Claimed 100 BTC") == "BTC"

    def test_litecoin_name(self):
        """Detects LTC from 'Litecoin' name."""
        assert FaucetBot._detect_currency_from_text("Litecoin faucet") == "LTC"

    def test_satoshi(self):
        """Detects BTC from 'satoshi' reference."""
        result = FaucetBot._detect_currency_from_text("Earned 50 satoshi")
        assert result == "BTC"

    def test_unknown(self):
        """Returns None for unrecognizable text."""
        assert FaucetBot._detect_currency_from_text("random text") is None

    def test_doge(self):
        """Detects DOGE."""
        assert FaucetBot._detect_currency_from_text("DOGE balance: 100") == "DOGE"


# ---------------------------------------------------------------------------
# _get_cryptocurrency_for_faucet
# ---------------------------------------------------------------------------

class TestGetCryptocurrencyForFaucet:
    """Test faucet name to cryptocurrency mapping."""

    def test_bitcoin_faucet(self, bot):
        """Detects BTC from faucet name."""
        bot.faucet_name = "FreeBitcoin"
        assert bot._get_cryptocurrency_for_faucet() == "BTC"

    def test_litecoin_faucet(self, bot):
        """Detects LTC from faucet name."""
        bot.faucet_name = "LitePick"
        assert bot._get_cryptocurrency_for_faucet() == "LTC"

    def test_unknown_faucet(self, bot):
        """Returns UNKNOWN for unknown faucet."""
        bot.faucet_name = "SomeRandomFaucet"
        assert bot._get_cryptocurrency_for_faucet() == "UNKNOWN"


# ---------------------------------------------------------------------------
# get_timer / get_balance
# ---------------------------------------------------------------------------

class TestGetTimerAndBalance:
    """Test timer and balance extraction."""

    @pytest.mark.asyncio
    async def test_get_timer_returns_float(self, bot, mock_page):
        """get_timer returns float minutes."""
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=1)
        loc.text_content = AsyncMock(return_value="59:30")
        mock_page.locator.return_value = loc

        result = await bot.get_timer(".timer")
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_get_timer_not_found(self, bot, mock_page):
        """get_timer returns 0.0 when selector not found."""
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=0)
        loc.text_content = AsyncMock(return_value="")
        mock_page.locator.return_value = loc

        with patch("faucets.base.DataExtractor") as mock_de:
            mock_de.return_value.find_timer_selector_in_dom = AsyncMock(
                return_value=None
            )
            result = await bot.get_timer(".timer")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_get_balance_returns_string(self, bot, mock_page):
        """get_balance returns balance string."""
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=1)
        loc.first = AsyncMock()
        loc.first.is_visible = AsyncMock(return_value=True)
        loc.first.text_content = AsyncMock(return_value="1,234.56")
        mock_page.locator.return_value = loc

        result = await bot.get_balance(".balance")
        assert "1234" in result or "1,234" in result

    @pytest.mark.asyncio
    async def test_get_balance_not_found(self, bot, mock_page):
        """get_balance returns '0' when not found."""
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=0)
        loc.text_content = AsyncMock(return_value="")
        mock_page.locator.return_value = loc

        with patch("faucets.base.DataExtractor") as mock_de:
            mock_de.return_value.find_balance_selector_in_dom = AsyncMock(
                return_value=None
            )
            result = await bot.get_balance(".balance")
        assert result == "0"


# ---------------------------------------------------------------------------
# run (legacy entry point)
# ---------------------------------------------------------------------------

class TestRun:
    """Test the legacy run() method."""

    @pytest.mark.asyncio
    async def test_run_success(self, bot, mock_page):
        """Full run completes with successful claim."""
        claim_result = ClaimResult(
            success=True, status="OK", amount="100",
            next_claim_minutes=60
        )
        with patch.object(bot, "login", new_callable=AsyncMock,
                          return_value=True), \
             patch.object(bot, "close_popups", new_callable=AsyncMock), \
             patch.object(bot, "random_delay", new_callable=AsyncMock), \
             patch.object(bot, "claim", new_callable=AsyncMock,
                          return_value=claim_result), \
             patch.object(bot, "_record_analytics", new_callable=AsyncMock):
            result = await bot.run()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_login_fails(self, bot, mock_page):
        """Run returns failure when login fails."""
        with patch.object(bot, "login", new_callable=AsyncMock,
                          return_value=False):
            result = await bot.run()

        assert result.success is False


# ---------------------------------------------------------------------------
# _configure_solver – capsolver provider path
# ---------------------------------------------------------------------------

class TestConfigureSolverCapsolver:
    """Test solver configuration with capsolver."""

    def test_capsolver_provider(self, mock_page):
        """Configures solver with capsolver provider."""
        settings = MagicMock()
        settings.captcha_provider = "capsolver"
        settings.capsolver_api_key = "cs_key"
        settings.twocaptcha_api_key = None
        settings.captcha_daily_budget = 5.0
        settings.captcha_provider_routing = "fixed"
        settings.captcha_provider_routing_min_samples = 20
        settings.headless = True
        settings.captcha_fallback_provider = None
        settings.captcha_fallback_api_key = None

        bot = FaucetBot(settings, mock_page)
        assert bot.solver is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
