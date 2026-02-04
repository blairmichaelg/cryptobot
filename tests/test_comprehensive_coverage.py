"""
Comprehensive test suite for 100% coverage on critical functions.

This module tests all important functions across core modules including:
- core/extractor.py: DataExtractor
- core/config.py: BotSettings, AccountProfile
- core/orchestrator.py: Job, JobScheduler
- solvers/captcha.py: CaptchaSolver
- faucets/base.py: ClaimResult, FaucetBot
- browser/instance.py: BrowserManager
"""

import pytest
import asyncio
import json
import os
import time
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from dataclasses import dataclass


# =============================================================================
# EXTRACTOR TESTS - DataExtractor comprehensive coverage
# =============================================================================

class TestDataExtractorComprehensive:
    """Complete coverage for DataExtractor class."""
    
    def test_parse_timer_empty_string(self):
        """Test parse_timer_to_minutes with empty string."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("") == 0.0
    
    def test_parse_timer_none(self):
        """Test parse_timer_to_minutes with None."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes(None) == 0.0
    
    def test_parse_timer_whitespace_only(self):
        """Test parse_timer_to_minutes with whitespace."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("   ") == 0.0
    
    def test_parse_timer_mm_ss_format(self):
        """Test MM:SS format."""
        from core.extractor import DataExtractor
        result = DataExtractor.parse_timer_to_minutes("45:30")
        assert abs(result - 45.5) < 0.01
    
    def test_parse_timer_hh_mm_ss_format(self):
        """Test HH:MM:SS format."""
        from core.extractor import DataExtractor
        result = DataExtractor.parse_timer_to_minutes("01:30:00")
        assert result == 90.0
    
    def test_parse_timer_complex_hms(self):
        """Test complex HH:MM:SS format with all components."""
        from core.extractor import DataExtractor
        result = DataExtractor.parse_timer_to_minutes("02:15:30")
        # 2h * 60 + 15m + 30s/60 = 120 + 15 + 0.5 = 135.5
        assert abs(result - 135.5) < 0.01
    
    def test_parse_timer_days_hours_minutes(self):
        """Test 1d 5h 30m format."""
        from core.extractor import DataExtractor
        result = DataExtractor.parse_timer_to_minutes("1d 5h 30m")
        # 1 day = 1440 min, 5h = 300 min, 30m = 30 min
        assert result == 1440 + 300 + 30
    
    def test_parse_timer_just_seconds(self):
        """Test seconds only format."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("120 seconds") == 2.0
        assert DataExtractor.parse_timer_to_minutes("30s") == 0.5
        assert DataExtractor.parse_timer_to_minutes("60sec") == 1.0
    
    def test_parse_timer_just_minutes(self):
        """Test minutes only format."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("15 minutes") == 15.0
        assert DataExtractor.parse_timer_to_minutes("30m") == 30.0
        assert DataExtractor.parse_timer_to_minutes("45 min") == 45.0
    
    def test_parse_timer_just_hours(self):
        """Test hours only format."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("2 hours") == 120.0
        assert DataExtractor.parse_timer_to_minutes("1h") == 60.0
        assert DataExtractor.parse_timer_to_minutes("3 hour") == 180.0
    
    def test_parse_timer_just_days(self):
        """Test days only format."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("2 days") == 2 * 24 * 60
        assert DataExtractor.parse_timer_to_minutes("1d") == 24 * 60
        assert DataExtractor.parse_timer_to_minutes("3 day") == 3 * 24 * 60
    
    def test_parse_timer_plain_number(self):
        """Test plain number falls back to minutes."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("42") == 42.0
    
    def test_parse_timer_with_text_around_number(self):
        """Test timer with text context."""
        from core.extractor import DataExtractor
        result = DataExtractor.parse_timer_to_minutes("Next claim in 5 minutes")
        assert result == 5.0
    
    def test_parse_timer_invalid_text_returns_zero(self):
        """Test completely invalid text returns 0."""
        from core.extractor import DataExtractor
        assert DataExtractor.parse_timer_to_minutes("no numbers here") == 0.0
    
    def test_extract_balance_empty_string(self):
        """Test extract_balance with empty string."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance("") == "0"
    
    def test_extract_balance_none(self):
        """Test extract_balance with None."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance(None) == "0"
    
    def test_extract_balance_no_numbers(self):
        """Test extract_balance with no numbers."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance("no balance here") == "0"
    
    def test_extract_balance_with_commas(self):
        """Test extract_balance removes commas."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance("1,234,567.89") == "1234567.89"
    
    def test_extract_balance_scientific_notation(self):
        """Test extract_balance handles scientific notation."""
        from core.extractor import DataExtractor
        result = DataExtractor.extract_balance("3.8e-07")
        # Should convert to regular decimal
        assert "0.0000003" in result or "3.8e-07" in result.lower()
    
    def test_extract_balance_scientific_notation_positive(self):
        """Test extract_balance handles positive exponent."""
        from core.extractor import DataExtractor
        result = DataExtractor.extract_balance("1.5E+05")
        assert "150000" in result or "1.5E+05" in result.upper()
    
    def test_extract_balance_currency_symbols(self):
        """Test extract_balance strips currency symbols."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance("$123.45") == "123.45"
        assert DataExtractor.extract_balance("₿0.00123") == "0.00123"
    
    def test_extract_balance_integer_only(self):
        """Test extract_balance with integer."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance("500") == "500"
    
    def test_extract_balance_trailing_zeros_stripped(self):
        """Test trailing zeros are stripped."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance("123.4500") == "123.45"
    
    def test_extract_balance_with_text_context(self):
        """Test balance extraction from text context."""
        from core.extractor import DataExtractor
        assert DataExtractor.extract_balance("Your balance: 456.78 BTC") == "456.78"
    
    @pytest.mark.asyncio
    async def test_find_balance_selector_in_dom(self):
        """Test find_balance_selector_in_dom with mock page."""
        from core.extractor import DataExtractor
        
        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_page.locator.return_value = mock_locator
        
        result = await DataExtractor.find_balance_selector_in_dom(mock_page)
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_find_balance_selector_not_found(self):
        """Test find_balance_selector_in_dom when no match."""
        from core.extractor import DataExtractor
        
        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_page.locator.return_value = mock_locator
        
        result = await DataExtractor.find_balance_selector_in_dom(mock_page)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_find_timer_selector_in_dom(self):
        """Test find_timer_selector_in_dom with mock page."""
        from core.extractor import DataExtractor
        
        mock_page = AsyncMock()
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.is_visible = AsyncMock(return_value=True)
        mock_page.locator.return_value = mock_locator
        
        result = await DataExtractor.find_timer_selector_in_dom(mock_page)
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_find_timer_selector_exception_handled(self):
        """Test exception handling in find_timer_selector_in_dom."""
        from core.extractor import DataExtractor
        
        mock_page = AsyncMock()
        mock_page.locator.side_effect = Exception("Test error")
        
        # Should return None, not raise
        result = await DataExtractor.find_timer_selector_in_dom(mock_page)
        assert result is None


# =============================================================================
# CLAIM RESULT TESTS - faucets/base.py ClaimResult coverage
# =============================================================================

class TestClaimResultComprehensive:
    """Complete coverage for ClaimResult dataclass."""
    
    def test_claim_result_creation_basic(self):
        """Test basic ClaimResult creation."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(
            success=True,
            status="Claimed successfully",
            next_claim_minutes=60.0,
            amount="0.00001",
            balance="0.001"
        )
        
        assert result.success is True
        assert result.status == "Claimed successfully"
        assert result.next_claim_minutes == 60.0
        assert result.amount == "0.00001"
        assert result.balance == "0.001"
    
    def test_claim_result_default_values(self):
        """Test ClaimResult default values."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=False, status="Failed")
        
        assert result.next_claim_minutes == 0
        assert result.amount == "0"
        assert result.balance == "0"
        assert result.error_type is None
    
    def test_claim_result_validate_none_amount(self):
        """Test validate() handles None amount."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success")
        result.amount = None
        result = result.validate("TestFaucet")
        
        assert result.amount == "0"
    
    def test_claim_result_validate_none_balance(self):
        """Test validate() handles None balance."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success")
        result.balance = None
        result = result.validate("TestFaucet")
        
        assert result.balance == "0"
    
    def test_claim_result_validate_non_string_amount(self):
        """Test validate() converts non-string amount."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success", amount="0", balance="0")
        result.amount = 123.45
        result = result.validate("TestFaucet")
        
        assert result.amount == "123.45"
    
    def test_claim_result_validate_non_string_balance(self):
        """Test validate() converts non-string balance."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success", amount="0", balance="0")
        result.balance = 456.78
        result = result.validate("TestFaucet")
        
        assert result.balance == "456.78"
    
    def test_claim_result_validate_success_zero_amount_warning(self):
        """Test validate() warns on successful claim with zero amount."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success", amount="0", balance="0")
        result = result.validate("TestFaucet")
        
        # Should still return valid result
        assert result.amount == "0"


# =============================================================================
# FAUCET BOT TESTS - faucets/base.py FaucetBot coverage
# =============================================================================

class TestFaucetBotComprehensive:
    """Complete coverage for FaucetBot base class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
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
        settings.get_account.return_value = {"username": "test", "password": "test"}
        return settings
    
    @pytest.fixture
    def mock_page(self):
        """Create mock page."""
        page = AsyncMock()
        page.url = "https://test.com"
        return page
    
    def test_faucet_bot_init(self, mock_settings, mock_page):
        """Test FaucetBot initialization."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        assert bot.settings == mock_settings
        assert bot.page == mock_page
        assert bot.solver is not None
        assert bot._faucet_name == "Generic"
    
    def test_faucet_bot_set_behavior_profile(self, mock_settings, mock_page):
        """Test set_behavior_profile method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        bot.set_behavior_profile(profile_hint="fast")
        assert bot.behavior_profile_name == "fast"
        
        bot.set_behavior_profile(profile_hint="cautious")
        assert bot.behavior_profile_name == "cautious"
    
    def test_faucet_bot_set_behavior_profile_by_name(self, mock_settings, mock_page):
        """Test set_behavior_profile with profile name generates consistent profile."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        bot.set_behavior_profile(profile_name="user123")
        first_profile = bot.behavior_profile_name
        
        # Same name should give same profile (seeded random)
        bot.set_behavior_profile(profile_name="user123")
        assert bot.behavior_profile_name == first_profile
    
    def test_faucet_bot_resolve_delay_range(self, mock_settings, mock_page):
        """Test _resolve_delay_range method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # With provided values
        min_s, max_s = bot._resolve_delay_range(1.0, 3.0)
        assert min_s == 1.0
        assert max_s == 3.0
        
        # With None values - uses profile default
        min_s, max_s = bot._resolve_delay_range(None, None)
        assert isinstance(min_s, float)
        assert isinstance(max_s, float)
    
    def test_faucet_bot_resolve_typing_range(self, mock_settings, mock_page):
        """Test _resolve_typing_range method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # With provided values
        delay_min, delay_max = bot._resolve_typing_range(50, 150)
        assert delay_min == 50
        assert delay_max == 150
        
        # With None values
        delay_min, delay_max = bot._resolve_typing_range(None, None)
        assert isinstance(delay_min, int)
        assert isinstance(delay_max, int)
    
    def test_faucet_bot_resolve_idle_duration(self, mock_settings, mock_page):
        """Test _resolve_idle_duration method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # With provided value
        duration = bot._resolve_idle_duration(5.0)
        assert duration == 5.0
        
        # With None
        duration = bot._resolve_idle_duration(None)
        assert isinstance(duration, float)
    
    def test_faucet_bot_resolve_reading_duration(self, mock_settings, mock_page):
        """Test _resolve_reading_duration method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        duration = bot._resolve_reading_duration(3.0)
        assert duration == 3.0
        
        duration = bot._resolve_reading_duration(None)
        assert isinstance(duration, float)
    
    def test_faucet_bot_resolve_focus_blur_delay(self, mock_settings, mock_page):
        """Test _resolve_focus_blur_delay method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        delay = bot._resolve_focus_blur_delay()
        assert isinstance(delay, float)
    
    @pytest.mark.asyncio
    async def test_faucet_bot_think_pause(self, mock_settings, mock_page):
        """Test think_pause method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        start = time.time()
        await bot.think_pause("pre_login")
        elapsed = time.time() - start
        
        # Should pause for some duration
        assert elapsed > 0
    
    def test_faucet_bot_faucet_name_property(self, mock_settings, mock_page):
        """Test faucet_name property getter/setter."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        bot.faucet_name = "TestFaucet"
        assert bot.faucet_name == "TestFaucet"
        assert bot._faucet_name == "TestFaucet"
    
    def test_faucet_bot_set_proxy(self, mock_settings, mock_page):
        """Test set_proxy method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        bot.set_proxy("http://proxy:8080")
        
        # Should set on solver
        assert bot.solver.proxy_string == "http://proxy:8080"
    
    def test_faucet_bot_strip_email_alias(self, mock_settings, mock_page):
        """Test strip_email_alias static method."""
        from faucets.base import FaucetBot
        
        # With alias
        result = FaucetBot.strip_email_alias("user+alias@example.com")
        assert result == "user@example.com"
        
        # Without alias
        result = FaucetBot.strip_email_alias("user@example.com")
        assert result == "user@example.com"
        
        # None
        result = FaucetBot.strip_email_alias(None)
        assert result is None
        
        # Empty
        result = FaucetBot.strip_email_alias("")
        assert result == ""
        
        # No @ symbol
        result = FaucetBot.strip_email_alias("notanemail")
        assert result == "notanemail"
    
    def test_faucet_bot_get_credentials(self, mock_settings, mock_page):
        """Test get_credentials method."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # From settings
        creds = bot.get_credentials("test_faucet")
        assert creds is not None
        
        # With override
        bot.settings_account_override = {"username": "override", "password": "override_pass"}
        creds = bot.get_credentials("test_faucet")
        assert creds["username"] == "override"
    
    def test_faucet_bot_classify_error_status_codes(self, mock_settings, mock_page):
        """Test classify_error with various status codes."""
        from faucets.base import FaucetBot
        from core.orchestrator import ErrorType
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # Server errors
        assert bot.classify_error(status_code=500) == ErrorType.FAUCET_DOWN
        assert bot.classify_error(status_code=502) == ErrorType.FAUCET_DOWN
        assert bot.classify_error(status_code=503) == ErrorType.FAUCET_DOWN
        assert bot.classify_error(status_code=504) == ErrorType.FAUCET_DOWN
        
        # Rate limit
        assert bot.classify_error(status_code=429) == ErrorType.RATE_LIMIT
        
        # Forbidden (proxy issue)
        assert bot.classify_error(status_code=403) == ErrorType.PROXY_ISSUE
    
    def test_faucet_bot_classify_error_exceptions(self, mock_settings, mock_page):
        """Test classify_error with various exceptions."""
        from faucets.base import FaucetBot
        from core.orchestrator import ErrorType
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # Timeout
        assert bot.classify_error(exception=Exception("timeout error")) == ErrorType.TRANSIENT
        
        # Connection errors
        assert bot.classify_error(exception=Exception("connection reset")) == ErrorType.TRANSIENT
        
        # Captcha failures
        assert bot.classify_error(exception=Exception("captcha failed")) == ErrorType.CAPTCHA_FAILED
        
        # Browser closed
        assert bot.classify_error(exception=Exception("target closed")) == ErrorType.TRANSIENT
    
    def test_faucet_bot_classify_error_page_content(self, mock_settings, mock_page):
        """Test classify_error with page content patterns."""
        from faucets.base import FaucetBot
        from core.orchestrator import ErrorType
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # Permanent failures
        assert bot.classify_error(page_content="Your account has been banned") == ErrorType.PERMANENT
        assert bot.classify_error(page_content="Account suspended") == ErrorType.PERMANENT
        
        # Rate limiting
        assert bot.classify_error(page_content="Too many requests, slow down") == ErrorType.RATE_LIMIT
        
        # Proxy detection
        assert bot.classify_error(page_content="VPN detected") == ErrorType.PROXY_ISSUE
        assert bot.classify_error(page_content="Proxy detected") == ErrorType.PROXY_ISSUE
        
        # Cloudflare
        assert bot.classify_error(page_content="Checking your browser, Ray ID") == ErrorType.RATE_LIMIT
    
    def test_faucet_bot_classify_error_unknown(self, mock_settings, mock_page):
        """Test classify_error returns UNKNOWN for unclassifiable errors."""
        from faucets.base import FaucetBot
        from core.orchestrator import ErrorType
        
        bot = FaucetBot(mock_settings, mock_page)
        
        assert bot.classify_error() == ErrorType.UNKNOWN
        assert bot.classify_error(page_content="Normal page content") == ErrorType.UNKNOWN
    
    def test_faucet_bot_create_error_result(self, mock_settings, mock_page):
        """Test create_error_result method."""
        from faucets.base import FaucetBot
        from core.orchestrator import ErrorType
        
        bot = FaucetBot(mock_settings, mock_page)
        
        # With auto-classification
        result = bot.create_error_result("Timeout error", 60, exception=Exception("timeout"))
        assert result.success is False
        assert result.error_type == ErrorType.TRANSIENT
        
        # With forced type
        result = bot.create_error_result("Custom error", force_error_type=ErrorType.PERMANENT)
        assert result.error_type == ErrorType.PERMANENT
        
        # With config error keyword
        result = bot.create_error_result("hCaptcha configuration error")
        assert result.error_type == ErrorType.CONFIG_ERROR


# =============================================================================
# CAPTCHA SOLVER TESTS - solvers/captcha.py coverage
# =============================================================================

class TestCaptchaSolverComprehensive:
    """Complete coverage for CaptchaSolver class."""
    
    def test_solver_init_with_api_key(self):
        """Test solver initialization with API key."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="test_key_32_chars_long_here123")
        
        assert solver.api_key == "test_key_32_chars_long_here123"
        assert solver.provider == "2captcha"
    
    def test_solver_init_without_api_key(self):
        """Test solver initialization without API key (manual mode)."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key=None)
        
        assert solver.api_key is None
    
    def test_solver_init_capsolver_provider(self):
        """Test solver with capsolver provider."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="test_key", provider="capsolver")
        
        assert solver.provider == "capsolver"
    
    def test_solver_init_twocaptcha_alias(self):
        """Test twocaptcha provider name normalization."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="test_key", provider="twocaptcha")
        
        assert solver.provider == "2captcha"
    
    def test_solver_set_faucet_name(self):
        """Test set_faucet_name method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_faucet_name("TestFaucet")
        
        assert solver.faucet_name == "TestFaucet"
        assert "TestFaucet" in solver.faucet_provider_stats
    
    def test_solver_set_proxy(self):
        """Test set_proxy method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_proxy("http://proxy:8080")
        
        assert solver.proxy_string == "http://proxy:8080"
    
    def test_solver_set_headless(self):
        """Test set_headless method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        solver.set_headless(True)
        
        assert solver.headless is True
        
        solver.set_headless(False)
        assert solver.headless is False
    
    def test_solver_set_fallback_provider(self):
        """Test set_fallback_provider method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="primary_key")
        solver.set_fallback_provider("capsolver", "fallback_key")
        
        assert solver.fallback_provider == "capsolver"
        assert solver.fallback_api_key == "fallback_key"
    
    def test_solver_budget_tracking(self):
        """Test budget tracking methods."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=1.0)
        
        # Initial state
        stats = solver.get_budget_stats()
        assert stats["daily_budget"] == 1.0
        assert stats["spent_today"] == 0.0
        
        # Record a solve
        solver._record_solve("turnstile", success=True)
        
        stats = solver.get_budget_stats()
        assert stats["spent_today"] > 0
    
    def test_solver_can_afford_solve(self):
        """Test _can_afford_solve method."""
        from solvers.captcha import CaptchaSolver
        
        # Low budget
        solver = CaptchaSolver(daily_budget=0.001)
        assert solver._can_afford_solve("turnstile") is False
        
        # Adequate budget
        solver = CaptchaSolver(daily_budget=10.0)
        assert solver._can_afford_solve("turnstile") is True
    
    def test_solver_can_afford_captcha(self):
        """Test can_afford_captcha method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        
        # Should be able to afford
        assert solver.can_afford_captcha("turnstile") is True
        
        # Exhaust budget
        solver._daily_spend = 4.998
        assert solver.can_afford_captcha("turnstile") is False
    
    def test_solver_daily_budget_reset(self):
        """Test daily budget resets on new day."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(daily_budget=5.0)
        solver._daily_spend = 3.0
        solver._budget_reset_date = "2000-01-01"  # Old date
        
        solver._check_and_reset_daily_budget()
        
        assert solver._daily_spend == 0.0
        assert solver._budget_reset_date == time.strftime("%Y-%m-%d")
    
    def test_solver_parse_proxy_http(self):
        """Test _parse_proxy with HTTP proxy."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        result = solver._parse_proxy("http://user:pass@host:8080")
        
        assert result["proxytype"] == "HTTP"
        assert "user:pass@host:8080" in result["proxy"]
    
    def test_solver_parse_proxy_socks5(self):
        """Test _parse_proxy with SOCKS5 proxy."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        result = solver._parse_proxy("socks5://user:pass@host:1080")
        
        assert result["proxytype"] == "SOCKS5"
    
    def test_solver_parse_proxy_no_protocol(self):
        """Test _parse_proxy without protocol prefix."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        result = solver._parse_proxy("user:pass@host:8080")
        
        assert result["proxytype"] == "HTTP"
    
    def test_solver_get_provider_stats(self):
        """Test get_provider_stats method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", provider="2captcha")
        solver.set_fallback_provider("capsolver", "fallback_key")
        
        stats = solver.get_provider_stats()
        
        assert stats["primary"] == "2captcha"
        assert stats["fallback"] == "capsolver"
        assert "providers" in stats
    
    def test_solver_record_provider_result(self):
        """Test _record_provider_result method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key")
        solver.set_faucet_name("TestFaucet")
        
        # Record success
        solver._record_provider_result("2captcha", "turnstile", success=True)
        
        assert solver.provider_stats["2captcha"]["solves"] == 1
        assert solver.faucet_provider_stats["TestFaucet"]["2captcha"]["solves"] == 1
        
        # Record failure
        solver._record_provider_result("2captcha", "turnstile", success=False)
        
        assert solver.provider_stats["2captcha"]["failures"] == 1
    
    def test_solver_expected_cost(self):
        """Test _expected_cost method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver(api_key="key", routing_min_samples=2)
        
        # Not enough samples
        cost = solver._expected_cost("2captcha", "turnstile")
        assert cost is None
        
        # Add samples
        for _ in range(5):
            solver._record_provider_result("2captcha", "turnstile", success=True)
        
        cost = solver._expected_cost("2captcha", "turnstile")
        assert cost is not None
    
    def test_solver_choose_provider_order(self):
        """Test _choose_provider_order method."""
        from solvers.captcha import CaptchaSolver
        
        # Non-adaptive mode
        solver = CaptchaSolver(api_key="key", adaptive_routing=False)
        order = solver._choose_provider_order("turnstile")
        assert order == ["2captcha"]
        
        # Adaptive mode (not enough samples for decision)
        solver = CaptchaSolver(api_key="key", adaptive_routing=True, routing_min_samples=1)
        solver.set_fallback_provider("capsolver", "key2")
        order = solver._choose_provider_order("turnstile")
        assert len(order) == 2
    
    @pytest.mark.asyncio
    async def test_solver_close(self):
        """Test close method."""
        from solvers.captcha import CaptchaSolver
        
        solver = CaptchaSolver()
        # Create a mock session
        solver.session = MagicMock()
        solver.session.closed = False
        solver.session.close = AsyncMock()
        
        await solver.close()
        
        solver.session.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_solver_context_manager(self):
        """Test async context manager."""
        from solvers.captcha import CaptchaSolver
        
        async with CaptchaSolver() as solver:
            assert solver is not None


# =============================================================================
# JOB AND SCHEDULER TESTS - core/orchestrator.py coverage
# =============================================================================

class TestJobComprehensive:
    """Complete coverage for Job dataclass."""
    
    def test_job_to_dict(self):
        """Test Job.to_dict method."""
        from core.orchestrator import Job
        from core.config import AccountProfile
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        job = Job(
            priority=1,
            next_run=1000.0,
            name="test_job",
            profile=profile,
            faucet_type="test_faucet",
            job_type="claim_wrapper",
            retry_count=2
        )
        
        d = job.to_dict()
        
        assert d["priority"] == 1
        assert d["next_run"] == 1000.0
        assert d["name"] == "test_job"
        assert d["faucet_type"] == "test_faucet"
        assert d["job_type"] == "claim_wrapper"
        assert d["retry_count"] == 2
        assert isinstance(d["profile"], dict)
    
    def test_job_from_dict(self):
        """Test Job.from_dict class method."""
        from core.orchestrator import Job
        
        data = {
            "priority": 2,
            "next_run": 2000.0,
            "name": "restored_job",
            "profile": {
                "faucet": "test",
                "username": "user",
                "password": "pass"
            },
            "faucet_type": "test_faucet",
            "job_type": "claim_wrapper",
            "retry_count": 1
        }
        
        job = Job.from_dict(data)
        
        assert job.priority == 2
        assert job.next_run == 2000.0
        assert job.name == "restored_job"
        assert job.profile.username == "user"
        assert job.retry_count == 1
    
    def test_job_comparison(self):
        """Test Job comparison operators."""
        from core.orchestrator import Job
        from core.config import AccountProfile
        
        profile = AccountProfile(faucet="test", username="user", password="pass")
        
        job1 = Job(priority=1, next_run=100.0, name="j1", profile=profile, faucet_type="f")
        job2 = Job(priority=2, next_run=50.0, name="j2", profile=profile, faucet_type="f")
        job3 = Job(priority=1, next_run=200.0, name="j3", profile=profile, faucet_type="f")
        
        # Lower priority number means higher priority
        assert job1 < job2
        
        # Same priority, earlier next_run comes first
        assert job1 < job3


class TestJobSchedulerComprehensive:
    """Complete coverage for JobScheduler class."""
    
    @pytest.fixture
    def mock_browser_manager(self):
        """Create mock browser manager."""
        manager = AsyncMock()
        return manager
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.max_concurrent_bots = 2
        settings.max_concurrent_per_profile = 1
        settings.alert_webhook_url = None
        settings.job_timeout_seconds = 600
        return settings
    
    def test_scheduler_init(self, mock_settings, mock_browser_manager):
        """Test JobScheduler initialization."""
        from core.orchestrator import JobScheduler
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        assert scheduler.settings == mock_settings
        assert scheduler.browser_manager == mock_browser_manager
        assert scheduler.queue == []
        assert scheduler.running_jobs == {}
    
    def test_scheduler_with_proxy_manager(self, mock_settings, mock_browser_manager):
        """Test JobScheduler with proxy manager."""
        from core.orchestrator import JobScheduler
        
        mock_proxy_manager = MagicMock()
        mock_proxy_manager.proxies = ["proxy1", "proxy2", "proxy3"]
        
        scheduler = JobScheduler(mock_settings, mock_browser_manager, mock_proxy_manager)
        
        assert scheduler.proxy_manager == mock_proxy_manager


# =============================================================================
# BROWSER MANAGER TESTS - browser/instance.py coverage
# =============================================================================

class TestBrowserManagerComprehensive:
    """Complete coverage for BrowserManager class."""
    
    def test_browser_manager_init_default(self):
        """Test BrowserManager initialization with defaults."""
        from browser.instance import BrowserManager
        
        manager = BrowserManager()
        
        assert manager.headless is True
        assert manager.proxy is None
        assert manager.block_images is True
        assert manager.block_media is True
    
    def test_browser_manager_init_custom(self):
        """Test BrowserManager initialization with custom settings."""
        from browser.instance import BrowserManager
        
        manager = BrowserManager(
            headless=False,
            proxy="http://proxy:8080",
            block_images=False,
            block_media=False,
            timeout=30000
        )
        
        assert manager.headless is False
        assert manager.proxy == "http://proxy:8080"
        assert manager.block_images is False
        assert manager.block_media is False
        assert manager.timeout == 30000
    
    def test_browser_manager_safe_json_write(self, tmp_path):
        """Test _safe_json_write method."""
        from browser.instance import BrowserManager
        
        manager = BrowserManager()
        filepath = str(tmp_path / "test.json")
        
        data = {"key": "value", "number": 123}
        manager._safe_json_write(filepath, data)
        
        # Verify file was written
        assert os.path.exists(filepath)
        
        with open(filepath, "r") as f:
            loaded = json.load(f)
        
        assert loaded == data
    
    def test_browser_manager_safe_json_read(self, tmp_path):
        """Test _safe_json_read method."""
        from browser.instance import BrowserManager
        
        manager = BrowserManager()
        filepath = str(tmp_path / "test.json")
        
        # Write test data
        data = {"test": "data"}
        with open(filepath, "w") as f:
            json.dump(data, f)
        
        # Read it back
        result = manager._safe_json_read(filepath)
        
        assert result == data
    
    def test_browser_manager_safe_json_read_missing(self, tmp_path):
        """Test _safe_json_read with missing file."""
        from browser.instance import BrowserManager
        
        manager = BrowserManager()
        filepath = str(tmp_path / "nonexistent.json")
        
        result = manager._safe_json_read(filepath)
        
        assert result is None
    
    def test_browser_manager_safe_json_read_corrupt(self, tmp_path):
        """Test _safe_json_read with corrupted JSON."""
        from browser.instance import BrowserManager
        
        manager = BrowserManager()
        filepath = str(tmp_path / "corrupt.json")
        
        # Write invalid JSON
        with open(filepath, "w") as f:
            f.write("not valid json {{{")
        
        result = manager._safe_json_read(filepath)
        
        # Should return None for corrupt file
        assert result is None
    
    def test_browser_manager_normalize_proxy_key(self):
        """Test _normalize_proxy_key method."""
        from browser.instance import BrowserManager
        
        manager = BrowserManager()
        
        # Empty proxy
        assert manager._normalize_proxy_key("") == ""
        assert manager._normalize_proxy_key(None) == ""


# =============================================================================
# ANALYTICS TESTS - core/analytics.py additional coverage
# =============================================================================

class TestAnalyticsComprehensive:
    """Additional coverage for analytics module."""
    
    @pytest.fixture
    def temp_analytics_file(self, tmp_path):
        """Create temporary analytics file path."""
        return str(tmp_path / "test_analytics.json")
    
    def test_price_feed_currency_decimals(self):
        """Test CryptoPriceFeed currency decimal configuration."""
        from core.analytics import CryptoPriceFeed
        
        feed = CryptoPriceFeed()
        
        # Check all currencies have decimals defined
        assert feed.CURRENCY_DECIMALS["BTC"] == 8
        assert feed.CURRENCY_DECIMALS["ETH"] == 18
        assert feed.CURRENCY_DECIMALS["DOGE"] == 8
        assert feed.CURRENCY_DECIMALS["TRX"] == 6
    
    def test_price_feed_currency_ids(self):
        """Test CryptoPriceFeed CoinGecko ID mappings."""
        from core.analytics import CryptoPriceFeed
        
        feed = CryptoPriceFeed()
        
        assert feed.CURRENCY_IDS["BTC"] == "bitcoin"
        assert feed.CURRENCY_IDS["LTC"] == "litecoin"
        assert feed.CURRENCY_IDS["ETH"] == "ethereum"
    
    @pytest.mark.asyncio
    async def test_price_feed_get_price_unknown_currency(self):
        """Test get_price with unknown currency."""
        from core.analytics import CryptoPriceFeed
        
        feed = CryptoPriceFeed()
        
        result = await feed.get_price("UNKNOWN_COIN")
        
        assert result is None
    
    def test_earnings_tracker_record_claim_saves(self, temp_analytics_file):
        """Test that record_claim saves to file."""
        from core.analytics import EarningsTracker
        
        tracker = EarningsTracker(storage_file=temp_analytics_file)
        tracker.record_claim("test_faucet", True, 0.001, "BTC", allow_test=True)
        
        assert os.path.exists(temp_analytics_file)
        
        with open(temp_analytics_file, "r") as f:
            data = json.load(f)
        
        assert len(data["claims"]) == 1
        assert data["claims"][0]["faucet"] == "test_faucet"


# =============================================================================
# ACCOUNT PROFILE TESTS - Additional coverage
# =============================================================================

class TestAccountProfileComprehensive:
    """Additional coverage for AccountProfile."""
    
    def test_account_profile_proxy_pool(self):
        """Test AccountProfile with proxy pool."""
        from core.config import AccountProfile
        
        profile = AccountProfile(
            faucet="test",
            username="user",
            password="pass",
            proxy_pool=["proxy1:8080", "proxy2:8080", "proxy3:8080"],
            proxy_rotation_strategy="round_robin"
        )
        
        assert len(profile.proxy_pool) == 3
        assert profile.proxy_rotation_strategy == "round_robin"
    
    def test_account_profile_residential_proxy(self):
        """Test AccountProfile with residential proxy flag."""
        from core.config import AccountProfile
        
        profile = AccountProfile(
            faucet="test",
            username="user",
            password="pass",
            residential_proxy=True
        )
        
        assert profile.residential_proxy is True
    
    def test_account_profile_behavior_profile(self):
        """Test AccountProfile with behavior profile."""
        from core.config import AccountProfile
        
        profile = AccountProfile(
            faucet="test",
            username="user",
            password="pass",
            behavior_profile="cautious"
        )
        
        assert profile.behavior_profile == "cautious"


# =============================================================================
# BOT SETTINGS TESTS - Additional coverage
# =============================================================================

class TestBotSettingsComprehensive:
    """Additional coverage for BotSettings."""
    
    def test_bot_settings_filter_profiles_no_canary(self):
        """Test filter_profiles without canary mode."""
        from core.config import BotSettings, AccountProfile
        
        profiles = [
            AccountProfile(faucet="test1", username="user1", password="pass1"),
            AccountProfile(faucet="test2", username="user2", password="pass2")
        ]
        
        settings = BotSettings(canary_only=False)
        filtered = settings.filter_profiles(profiles)
        
        assert len(filtered) == 2
    
    def test_bot_settings_filter_profiles_with_canary(self):
        """Test filter_profiles with canary mode enabled."""
        from core.config import BotSettings, AccountProfile
        
        profiles = [
            AccountProfile(faucet="firefaucet", username="fire_user", password="pass1"),
            AccountProfile(faucet="cointiply", username="coin_user", password="pass2"),
            AccountProfile(faucet="test", username="canary_target", password="pass3")
        ]
        
        settings = BotSettings()
        settings.canary_only = True
        settings.canary_profile = "canary"
        
        filtered = settings.filter_profiles(profiles)
        
        # Should only include profiles matching "canary"
        assert len(filtered) == 1
        assert filtered[0].username == "canary_target"
    
    def test_bot_settings_pick_faucet_fallbacks(self, monkeypatch):
        """Test Pick.io faucet legacy credential fallbacks."""
        from core.config import BotSettings
        
        monkeypatch.setenv("LITEPICK_USERNAME", "lite_user")
        monkeypatch.setenv("LITEPICK_PASSWORD", "lite_pass")
        
        settings = BotSettings()
        account = settings.get_account("litepick")
        
        assert account is not None
        assert account["email"] == "lite_user"
        assert account["password"] == "lite_pass"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
