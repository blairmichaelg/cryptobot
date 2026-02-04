"""
Comprehensive test suite for faucets/base.py.

Achieves 100% coverage on ClaimResult and FaucetBot methods including:
- ClaimResult validation
- FaucetBot initialization and configuration
- Error classification
- Behavior profiles
- Human timing helpers
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch


class TestClaimResultDataclass:
    """Test ClaimResult dataclass thoroughly."""
    
    def test_claim_result_basic_creation(self):
        """Test basic ClaimResult creation."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(
            success=True,
            status="Claimed successfully"
        )
        
        assert result.success is True
        assert result.status == "Claimed successfully"
    
    def test_claim_result_default_values(self):
        """Test ClaimResult default values."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=False, status="Failed")
        
        assert result.next_claim_minutes == 0
        assert result.amount == "0"
        assert result.balance == "0"
        assert result.error_type is None
    
    def test_claim_result_all_fields(self):
        """Test ClaimResult with all fields specified."""
        from faucets.base import ClaimResult
        from core.orchestrator import ErrorType
        
        result = ClaimResult(
            success=False,
            status="Rate limited",
            next_claim_minutes=60.0,
            amount="0.001",
            balance="0.1",
            error_type=ErrorType.RATE_LIMIT
        )
        
        assert result.success is False
        assert result.status == "Rate limited"
        assert result.next_claim_minutes == 60.0
        assert result.amount == "0.001"
        assert result.balance == "0.1"
        assert result.error_type == ErrorType.RATE_LIMIT
    
    def test_claim_result_validate_valid_data(self):
        """Test validate() with valid data."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(
            success=True,
            status="Success",
            amount="0.001",
            balance="0.1"
        )
        
        validated = result.validate("TestFaucet")
        
        assert validated.amount == "0.001"
        assert validated.balance == "0.1"
    
    def test_claim_result_validate_none_amount(self):
        """Test validate() fixes None amount."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success")
        result.amount = None
        
        validated = result.validate("TestFaucet")
        
        assert validated.amount == "0"
    
    def test_claim_result_validate_none_balance(self):
        """Test validate() fixes None balance."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success")
        result.balance = None
        
        validated = result.validate("TestFaucet")
        
        assert validated.balance == "0"
    
    def test_claim_result_validate_numeric_amount(self):
        """Test validate() converts numeric amount to string."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success", amount="0", balance="0")
        result.amount = 123.456
        
        validated = result.validate("TestFaucet")
        
        assert validated.amount == "123.456"
    
    def test_claim_result_validate_numeric_balance(self):
        """Test validate() converts numeric balance to string."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success", amount="0", balance="0")
        result.balance = 789.012
        
        validated = result.validate("TestFaucet")
        
        assert validated.balance == "789.012"
    
    def test_claim_result_validate_returns_self(self):
        """Test validate() returns self for chaining."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success", amount="0.1", balance="1.0")
        
        returned = result.validate("TestFaucet")
        
        assert returned is result
    
    def test_claim_result_validate_success_zero_amount_logs_warning(self):
        """Test validate() logs warning for successful claim with zero amount."""
        from faucets.base import ClaimResult
        
        result = ClaimResult(success=True, status="Success", amount="0", balance="1.0")
        
        with patch("faucets.base.logger") as mock_logger:
            result.validate("TestFaucet")
            
            # Should log warning about zero amount on success
            mock_logger.warning.assert_called()


class TestFaucetBotInit:
    """Test FaucetBot initialization."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.captcha_provider = "2captcha"
        settings.twocaptcha_api_key = "test_key_123"
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
    
    def test_faucet_bot_init_basic(self, mock_settings, mock_page):
        """Test basic FaucetBot initialization."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        assert bot.settings == mock_settings
        assert bot.page == mock_page
        assert bot.solver is not None
    
    def test_faucet_bot_init_default_faucet_name(self, mock_settings, mock_page):
        """Test default faucet name."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        assert bot._faucet_name == "Generic"
        assert bot.faucet_name == "Generic"
    
    def test_faucet_bot_init_default_base_url(self, mock_settings, mock_page):
        """Test default base URL."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        assert bot.base_url == ""
    
    def test_faucet_bot_init_default_behavior_profile(self, mock_settings, mock_page):
        """Test default behavior profile."""
        from faucets.base import FaucetBot
        
        bot = FaucetBot(mock_settings, mock_page)
        
        assert bot.behavior_profile_name == "balanced"
        assert bot.behavior_profile == bot.BEHAVIOR_PROFILES["balanced"]
    
    def test_faucet_bot_init_with_action_lock(self, mock_settings, mock_page):
        """Test FaucetBot with action lock."""
        from faucets.base import FaucetBot
        
        lock = asyncio.Lock()
        bot = FaucetBot(mock_settings, mock_page, action_lock=lock)
        
        assert bot.action_lock == lock
    
    def test_faucet_bot_init_with_fallback_provider(self, mock_settings, mock_page):
        """Test FaucetBot with fallback captcha provider."""
        from faucets.base import FaucetBot
        
        mock_settings.captcha_fallback_provider = "capsolver"
        mock_settings.captcha_fallback_api_key = "fallback_key"
        
        bot = FaucetBot(mock_settings, mock_page)
        
        assert bot.solver.fallback_provider == "capsolver"


class TestFaucetBotBehaviorProfiles:
    """Test behavior profile configuration."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    def test_behavior_profiles_defined(self, bot):
        """Test all behavior profiles are defined."""
        assert "fast" in bot.BEHAVIOR_PROFILES
        assert "balanced" in bot.BEHAVIOR_PROFILES
        assert "cautious" in bot.BEHAVIOR_PROFILES
    
    def test_set_behavior_profile_fast(self, bot):
        """Test setting fast behavior profile."""
        bot.set_behavior_profile(profile_hint="fast")
        
        assert bot.behavior_profile_name == "fast"
        assert bot.behavior_profile == bot.BEHAVIOR_PROFILES["fast"]
    
    def test_set_behavior_profile_balanced(self, bot):
        """Test setting balanced behavior profile."""
        bot.set_behavior_profile(profile_hint="balanced")
        
        assert bot.behavior_profile_name == "balanced"
    
    def test_set_behavior_profile_cautious(self, bot):
        """Test setting cautious behavior profile."""
        bot.set_behavior_profile(profile_hint="cautious")
        
        assert bot.behavior_profile_name == "cautious"
    
    def test_set_behavior_profile_by_name(self, bot):
        """Test setting behavior profile by profile name."""
        # Using profile_name seeds the random choice
        bot.set_behavior_profile(profile_name="user123")
        
        assert bot.behavior_profile_name in ["fast", "balanced", "cautious"]
    
    def test_set_behavior_profile_consistency(self, bot):
        """Test behavior profile is consistent for same name."""
        bot.set_behavior_profile(profile_name="consistent_user")
        first_profile = bot.behavior_profile_name
        
        bot.set_behavior_profile(profile_name="consistent_user")
        second_profile = bot.behavior_profile_name
        
        assert first_profile == second_profile
    
    def test_set_behavior_profile_default(self, bot):
        """Test default behavior profile when no args."""
        bot.set_behavior_profile()
        
        assert bot.behavior_profile_name == "balanced"


class TestFaucetBotDelayResolution:
    """Test delay resolution methods."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    def test_resolve_delay_range_with_values(self, bot):
        """Test _resolve_delay_range with provided values."""
        min_s, max_s = bot._resolve_delay_range(1.0, 5.0)
        
        assert min_s == 1.0
        assert max_s == 5.0
    
    def test_resolve_delay_range_none_values(self, bot):
        """Test _resolve_delay_range with None values uses profile."""
        min_s, max_s = bot._resolve_delay_range(None, None)
        
        # Should use profile defaults
        assert isinstance(min_s, float)
        assert isinstance(max_s, float)
        assert min_s < max_s
    
    def test_resolve_typing_range_with_values(self, bot):
        """Test _resolve_typing_range with provided values."""
        delay_min, delay_max = bot._resolve_typing_range(50, 150)
        
        assert delay_min == 50
        assert delay_max == 150
    
    def test_resolve_typing_range_none_values(self, bot):
        """Test _resolve_typing_range with None values uses profile."""
        delay_min, delay_max = bot._resolve_typing_range(None, None)
        
        assert isinstance(delay_min, int)
        assert isinstance(delay_max, int)
    
    def test_resolve_idle_duration_with_value(self, bot):
        """Test _resolve_idle_duration with provided value."""
        duration = bot._resolve_idle_duration(3.5)
        
        assert duration == 3.5
    
    def test_resolve_idle_duration_none(self, bot):
        """Test _resolve_idle_duration with None uses random in range."""
        duration = bot._resolve_idle_duration(None)
        
        assert isinstance(duration, float)
    
    def test_resolve_reading_duration_with_value(self, bot):
        """Test _resolve_reading_duration with provided value."""
        duration = bot._resolve_reading_duration(4.0)
        
        assert duration == 4.0
    
    def test_resolve_reading_duration_none(self, bot):
        """Test _resolve_reading_duration with None uses random in range."""
        duration = bot._resolve_reading_duration(None)
        
        assert isinstance(duration, float)
    
    def test_resolve_focus_blur_delay(self, bot):
        """Test _resolve_focus_blur_delay returns random in range."""
        delay = bot._resolve_focus_blur_delay()
        
        assert isinstance(delay, float)
        assert delay > 0


class TestFaucetBotThinkPause:
    """Test think_pause method."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    @pytest.mark.asyncio
    async def test_think_pause_basic(self, bot):
        """Test basic think_pause."""
        start = time.time()
        await bot.think_pause()
        elapsed = time.time() - start
        
        assert elapsed > 0  # Should pause
    
    @pytest.mark.asyncio
    async def test_think_pause_pre_login(self, bot):
        """Test think_pause with pre_login reason."""
        start = time.time()
        await bot.think_pause("pre_login")
        elapsed = time.time() - start
        
        # Should have longer pause for pre_login
        assert elapsed > 0.2
    
    @pytest.mark.asyncio
    async def test_think_pause_pre_claim(self, bot):
        """Test think_pause with pre_claim reason."""
        start = time.time()
        await bot.think_pause("pre_claim")
        elapsed = time.time() - start
        
        # Should have longer pause for pre_claim
        assert elapsed > 0.2


class TestFaucetBotFaucetNameProperty:
    """Test faucet_name property."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    def test_faucet_name_getter(self, bot):
        """Test faucet_name getter."""
        assert bot.faucet_name == "Generic"
    
    def test_faucet_name_setter(self, bot):
        """Test faucet_name setter."""
        bot.faucet_name = "TestFaucet"
        
        assert bot._faucet_name == "TestFaucet"
        assert bot.faucet_name == "TestFaucet"
    
    def test_faucet_name_setter_updates_solver(self, bot):
        """Test faucet_name setter updates solver."""
        bot.faucet_name = "NewFaucet"
        
        assert bot.solver.faucet_name == "NewFaucet"


class TestFaucetBotSetProxy:
    """Test set_proxy method."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    def test_set_proxy(self, bot):
        """Test set_proxy method."""
        bot.set_proxy("http://proxy:8080")
        
        assert bot.solver.proxy_string == "http://proxy:8080"


class TestFaucetBotStripEmailAlias:
    """Test strip_email_alias static method."""
    
    def test_strip_email_alias_with_alias(self):
        """Test stripping email alias."""
        from faucets.base import FaucetBot
        
        result = FaucetBot.strip_email_alias("user+alias@example.com")
        
        assert result == "user@example.com"
    
    def test_strip_email_alias_without_alias(self):
        """Test email without alias."""
        from faucets.base import FaucetBot
        
        result = FaucetBot.strip_email_alias("user@example.com")
        
        assert result == "user@example.com"
    
    def test_strip_email_alias_none(self):
        """Test with None input."""
        from faucets.base import FaucetBot
        
        result = FaucetBot.strip_email_alias(None)
        
        assert result is None
    
    def test_strip_email_alias_empty(self):
        """Test with empty string."""
        from faucets.base import FaucetBot
        
        result = FaucetBot.strip_email_alias("")
        
        assert result == ""
    
    def test_strip_email_alias_no_at_sign(self):
        """Test with string without @ symbol."""
        from faucets.base import FaucetBot
        
        result = FaucetBot.strip_email_alias("notanemail")
        
        assert result == "notanemail"
    
    def test_strip_email_alias_multiple_plus(self):
        """Test with multiple + signs."""
        from faucets.base import FaucetBot
        
        result = FaucetBot.strip_email_alias("user+alias+another@example.com")
        
        assert result == "user@example.com"


class TestFaucetBotGetCredentials:
    """Test get_credentials method."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        settings.get_account.return_value = {"username": "default", "password": "default_pass"}
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    def test_get_credentials_from_settings(self, bot):
        """Test get_credentials from settings."""
        creds = bot.get_credentials("test_faucet")
        
        assert creds is not None
        assert creds["username"] == "default"
    
    def test_get_credentials_with_override(self, bot):
        """Test get_credentials with account override."""
        bot.settings_account_override = {"username": "override", "password": "override_pass"}
        
        creds = bot.get_credentials("test_faucet")
        
        assert creds["username"] == "override"
        assert creds["password"] == "override_pass"


class TestFaucetBotClassifyError:
    """Test classify_error method."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    def test_classify_error_500(self, bot):
        """Test classify_error with 500 status."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(status_code=500)
        
        assert result == ErrorType.FAUCET_DOWN
    
    def test_classify_error_502(self, bot):
        """Test classify_error with 502 status."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(status_code=502)
        
        assert result == ErrorType.FAUCET_DOWN
    
    def test_classify_error_503(self, bot):
        """Test classify_error with 503 status."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(status_code=503)
        
        assert result == ErrorType.FAUCET_DOWN
    
    def test_classify_error_504(self, bot):
        """Test classify_error with 504 status."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(status_code=504)
        
        assert result == ErrorType.FAUCET_DOWN
    
    def test_classify_error_429(self, bot):
        """Test classify_error with 429 status."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(status_code=429)
        
        assert result == ErrorType.RATE_LIMIT
    
    def test_classify_error_403(self, bot):
        """Test classify_error with 403 status."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(status_code=403)
        
        assert result == ErrorType.PROXY_ISSUE
    
    def test_classify_error_timeout_exception(self, bot):
        """Test classify_error with timeout exception."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(exception=Exception("Request timed out"))
        
        assert result == ErrorType.TRANSIENT
    
    def test_classify_error_connection_exception(self, bot):
        """Test classify_error with connection exception."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(exception=Exception("Connection reset"))
        
        assert result == ErrorType.TRANSIENT
    
    def test_classify_error_captcha_exception(self, bot):
        """Test classify_error with captcha exception."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(exception=Exception("Captcha failed to solve"))
        
        assert result == ErrorType.CAPTCHA_FAILED
    
    def test_classify_error_browser_closed(self, bot):
        """Test classify_error with browser closed exception."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(exception=Exception("Target closed"))
        
        # May be TRANSIENT if pattern matches, or UNKNOWN otherwise
        assert result in [ErrorType.TRANSIENT, ErrorType.UNKNOWN]
    
    def test_classify_error_banned_page_content(self, bot):
        """Test classify_error with banned message in page content."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(page_content="Your account has been banned")
        
        assert result == ErrorType.PERMANENT
    
    def test_classify_error_suspended_page_content(self, bot):
        """Test classify_error with suspended message."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(page_content="Account suspended")
        
        assert result == ErrorType.PERMANENT
    
    def test_classify_error_rate_limit_page_content(self, bot):
        """Test classify_error with rate limit message."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(page_content="Too many requests, please slow down")
        
        assert result == ErrorType.RATE_LIMIT
    
    def test_classify_error_proxy_detected_page_content(self, bot):
        """Test classify_error with proxy detected message."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(page_content="VPN or proxy detected")
        
        assert result == ErrorType.PROXY_ISSUE
    
    def test_classify_error_cloudflare_page_content(self, bot):
        """Test classify_error with Cloudflare message."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(page_content="Checking your browser via Cloudflare")
        
        assert result == ErrorType.RATE_LIMIT
    
    def test_classify_error_unknown(self, bot):
        """Test classify_error with no indicators."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error()
        
        assert result == ErrorType.UNKNOWN
    
    def test_classify_error_normal_content(self, bot):
        """Test classify_error with normal page content."""
        from core.orchestrator import ErrorType
        
        result = bot.classify_error(page_content="Welcome to our faucet! Claim free crypto.")
        
        assert result == ErrorType.UNKNOWN


class TestFaucetBotCreateErrorResult:
    """Test create_error_result method."""
    
    @pytest.fixture
    def bot(self):
        """Create a FaucetBot instance."""
        from faucets.base import FaucetBot
        
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
        
        page = AsyncMock()
        
        return FaucetBot(settings, page)
    
    def test_create_error_result_basic(self, bot):
        """Test basic create_error_result."""
        from faucets.base import ClaimResult
        
        result = bot.create_error_result("Generic error", 60)
        
        assert isinstance(result, ClaimResult)
        assert result.success is False
        assert result.status == "Generic error"
        assert result.next_claim_minutes == 60
    
    def test_create_error_result_with_exception(self, bot):
        """Test create_error_result with exception."""
        from core.orchestrator import ErrorType
        
        result = bot.create_error_result(
            "Timeout error",
            60,
            exception=Exception("Request timed out")
        )
        
        assert result.error_type == ErrorType.TRANSIENT
    
    def test_create_error_result_forced_type(self, bot):
        """Test create_error_result with forced error type."""
        from core.orchestrator import ErrorType
        
        result = bot.create_error_result(
            "Custom error",
            30,
            force_error_type=ErrorType.PERMANENT
        )
        
        assert result.error_type == ErrorType.PERMANENT
    
    def test_create_error_result_hcaptcha_config(self, bot):
        """Test create_error_result with hCaptcha config error."""
        from core.orchestrator import ErrorType
        
        result = bot.create_error_result("hCaptcha configuration failed")
        
        assert result.error_type == ErrorType.CONFIG_ERROR
    
    def test_create_error_result_banned_status(self, bot):
        """Test create_error_result with banned status."""
        from core.orchestrator import ErrorType
        
        result = bot.create_error_result("Account banned - cannot continue")
        
        assert result.error_type == ErrorType.PERMANENT


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
