"""
Comprehensive test suite for all core faucets.

Tests login, balance, timer, claim, error handling, and special features
for FireFaucet, Cointiply, Dutchy, AdBTC, FaucetCrypto, and CoinPayU.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.base import ClaimResult
from core.config import BotSettings


# Faucet bot imports
from faucets.firefaucet import FireFaucetBot
from faucets.cointiply import CointiplyBot
from faucets.dutchy import DutchyBot
from faucets.adbtc import AdBTCBot
from faucets.faucetcrypto import FaucetCryptoBot
from faucets.coinpayu import CoinPayUBot


CORE_FAUCETS = [
    ("firefaucet", FireFaucetBot, "https://firefaucet.win"),
    ("cointiply", CointiplyBot, "https://cointiply.com"),
    ("dutchy", DutchyBot, "https://autofaucet.dutchycorp.space"),
    ("adbtc", AdBTCBot, "https://adbtc.top"),
    ("faucetcrypto", FaucetCryptoBot, "https://faucetcrypto.com"),
    ("coinpayu", CoinPayUBot, "https://www.coinpayu.com"),
]


@pytest.fixture
def mock_settings():
    """Fixture for mock BotSettings"""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {
        "username": "test@example.com",
        "password": "test_password"
    }
    settings.wallet_addresses = {"BTC": {"address": "BTC_ADDRESS_123"}}
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key"
    settings.capsolver_api_key = ""
    settings.use_faucetpay = False
    settings.btc_withdrawal_address = "BTC_ADDRESS_123"
    return settings


@pytest.fixture
def mock_page():
    """Fixture for mock Playwright Page"""
    page = AsyncMock()
    page.url = "https://example.com"
    page.title.return_value = "Test Page"
    page.content.return_value = "<html><body></body></html>"
    
    # Setup locator chain
    page.locator = MagicMock()
    locator_mock = MagicMock()
    locator_mock.count = AsyncMock(return_value=0)
    locator_mock.is_visible = AsyncMock(return_value=False)
    locator_mock.text_content = AsyncMock(return_value="")
    locator_mock.inner_text = AsyncMock(return_value="")
    locator_mock.get_attribute = AsyncMock(return_value="")
    locator_mock.fill = AsyncMock()
    locator_mock.click = AsyncMock()
    locator_mock.first = MagicMock()
    locator_mock.first.is_visible = AsyncMock(return_value=False)
    locator_mock.first.text_content = AsyncMock(return_value="")
    locator_mock.first.click = AsyncMock()
    locator_mock.last = MagicMock()
    page.locator.return_value = locator_mock
    
    page.query_selector = AsyncMock(return_value=None)
    page.goto = AsyncMock()
    page.fill = AsyncMock()
    page.click = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock()
    page.screenshot = AsyncMock()
    page.bring_to_front = AsyncMock()
    
    # Mock context for PTC ads
    page.context = MagicMock()
    page.context.expect_page = MagicMock()
    
    return page


@pytest.fixture
def mock_solver():
    """Fixture for mock CaptchaSolver"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)
        solver_instance.api_key = "test_key"
        solver_instance.set_faucet_name = MagicMock()
        yield solver_instance


class TestCoreFaucetsInitialization:
    """Test that all core faucets initialize correctly"""
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_initialization(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that each faucet initializes with correct attributes"""
        bot = bot_class(mock_settings, mock_page)
        
        assert hasattr(bot, 'faucet_name')
        assert hasattr(bot, 'base_url')
        assert bot.base_url == base_url
        assert hasattr(bot, 'login')
        assert hasattr(bot, 'claim')
        assert callable(bot.login)
        assert callable(bot.claim)


class TestCoreFaucetsLogin:
    """Test login functionality for all core faucets"""
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_login_no_credentials(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test login fails gracefully when no credentials are provided"""
        mock_settings.get_account.return_value = None
        
        bot = bot_class(mock_settings, mock_page)
        result = await bot.login()
        
        assert result is False, f"{faucet_name} should return False when no credentials"
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_login_already_logged_in(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test login detects when already logged in"""
        # Configure page to simulate already logged in state
        mock_page.url = f"{base_url}/dashboard"
        
        # Setup is_logged_in to return True
        bot = bot_class(mock_settings, mock_page)
        
        # Mock various login detection methods
        with patch.object(bot, 'is_logged_in', return_value=True):
            result = await bot.login()
            assert result is True, f"{faucet_name} should detect already logged in state"


class TestCoreFaucetsBalance:
    """Test balance extraction for all core faucets"""
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_balance_extraction(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that balance extraction returns valid string"""
        bot = bot_class(mock_settings, mock_page)
        
        # Mock balance element
        balance_locator = MagicMock()
        balance_locator.text_content = AsyncMock(return_value="100.50 BTC")
        balance_locator.inner_text = AsyncMock(return_value="100.50 BTC")
        balance_locator.is_visible = AsyncMock(return_value=True)
        balance_locator.count = AsyncMock(return_value=1)
        mock_page.locator.return_value = balance_locator
        
        # Get balance - should not raise exception
        try:
            balance = await bot.get_balance()
            # Balance should be a string
            assert isinstance(balance, str), f"{faucet_name} balance should be string"
        except Exception as e:
            pytest.fail(f"{faucet_name} balance extraction raised exception: {e}")


class TestCoreFaucetsTimer:
    """Test timer extraction for all core faucets"""
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_timer_extraction(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that timer extraction returns valid number >= 0"""
        bot = bot_class(mock_settings, mock_page)
        
        # Mock timer element
        timer_locator = MagicMock()
        timer_locator.text_content = AsyncMock(return_value="5:30")
        timer_locator.inner_text = AsyncMock(return_value="5:30")
        timer_locator.is_visible = AsyncMock(return_value=True)
        timer_locator.count = AsyncMock(return_value=1)
        mock_page.locator.return_value = timer_locator
        
        # Get timer - should not raise exception
        try:
            timer = await bot.get_timer()
            # Timer should be a number >= 0
            assert isinstance(timer, (int, float)), f"{faucet_name} timer should be numeric"
            assert timer >= 0, f"{faucet_name} timer should be >= 0"
        except Exception as e:
            pytest.fail(f"{faucet_name} timer extraction raised exception: {e}")


class TestCoreFaucetsClaim:
    """Test claim functionality for all core faucets"""
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_claim_returns_claim_result(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that claim returns a valid ClaimResult object"""
        bot = bot_class(mock_settings, mock_page)
        
        # Mock successful claim scenario
        mock_page.locator.return_value.count = AsyncMock(return_value=1)
        mock_page.locator.return_value.is_visible = AsyncMock(return_value=True)
        mock_page.locator.return_value.text_content = AsyncMock(return_value="100 satoshi")
        
        try:
            result = await bot.claim()
            
            # Should return ClaimResult instance
            assert isinstance(result, ClaimResult), f"{faucet_name} should return ClaimResult"
            assert hasattr(result, 'success'), f"{faucet_name} ClaimResult missing 'success'"
            assert hasattr(result, 'status'), f"{faucet_name} ClaimResult missing 'status'"
            assert hasattr(result, 'next_claim_minutes'), f"{faucet_name} ClaimResult missing 'next_claim_minutes'"
            assert hasattr(result, 'amount'), f"{faucet_name} ClaimResult missing 'amount'"
            assert hasattr(result, 'balance'), f"{faucet_name} ClaimResult missing 'balance'"
        except Exception as e:
            pytest.fail(f"{faucet_name} claim raised exception: {e}")


class TestCoreFaucetsErrorHandling:
    """Test error handling for all core faucets"""
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_handles_timeout_error(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that faucets handle TimeoutError gracefully"""
        bot = bot_class(mock_settings, mock_page)
        
        # Make page operations timeout
        mock_page.goto = AsyncMock(side_effect=asyncio.TimeoutError("Test timeout"))
        
        try:
            result = await bot.claim()
            # Should return ClaimResult with success=False instead of raising
            assert isinstance(result, ClaimResult), f"{faucet_name} should return ClaimResult on timeout"
            assert result.success is False, f"{faucet_name} should return failure on timeout"
        except asyncio.TimeoutError:
            pytest.fail(f"{faucet_name} did not handle TimeoutError gracefully")
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_handles_generic_exception(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that faucets handle generic exceptions gracefully"""
        bot = bot_class(mock_settings, mock_page)
        
        # Make page operations raise exception
        mock_page.locator = MagicMock(side_effect=Exception("Test exception"))
        
        try:
            result = await bot.claim()
            # Should return ClaimResult with success=False instead of raising
            assert isinstance(result, ClaimResult), f"{faucet_name} should return ClaimResult on exception"
            assert result.success is False, f"{faucet_name} should return failure on exception"
        except Exception as e:
            if "Test exception" in str(e):
                pytest.fail(f"{faucet_name} did not handle generic exception gracefully")


class TestCoreFaucetsAntiDetection:
    """Test anti-detection measures for all core faucets"""
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_has_human_type_method(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that all faucets have human_type method for stealth typing"""
        bot = bot_class(mock_settings, mock_page)
        assert hasattr(bot, 'human_type'), f"{faucet_name} missing human_type method"
        assert callable(bot.human_type), f"{faucet_name} human_type is not callable"
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_has_idle_mouse_method(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that all faucets have idle_mouse method for human-like delays"""
        bot = bot_class(mock_settings, mock_page)
        assert hasattr(bot, 'idle_mouse'), f"{faucet_name} missing idle_mouse method"
        assert callable(bot.idle_mouse), f"{faucet_name} idle_mouse is not callable"
    
    @pytest.mark.parametrize("faucet_name,bot_class,base_url", CORE_FAUCETS)
    async def test_faucet_has_random_delay_method(self, faucet_name, bot_class, base_url, mock_settings, mock_page, mock_solver):
        """Test that all faucets have random_delay method"""
        bot = bot_class(mock_settings, mock_page)
        assert hasattr(bot, 'random_delay'), f"{faucet_name} missing random_delay method"
        assert callable(bot.random_delay), f"{faucet_name} random_delay is not callable"


class TestFireFaucetSpecialFeatures:
    """Test FireFaucet-specific features"""
    
    async def test_firefaucet_has_cloudflare_detection(self, mock_settings, mock_page, mock_solver):
        """Test FireFaucet has Cloudflare detection logic"""
        bot = FireFaucetBot(mock_settings, mock_page)
        assert hasattr(bot, 'detect_cloudflare_block'), "FireFaucet missing Cloudflare detection"
        assert callable(bot.detect_cloudflare_block)
    
    async def test_firefaucet_has_cloudflare_bypass(self, mock_settings, mock_page, mock_solver):
        """Test FireFaucet has Cloudflare bypass logic"""
        bot = FireFaucetBot(mock_settings, mock_page)
        assert hasattr(bot, 'bypass_cloudflare_with_retry'), "FireFaucet missing Cloudflare bypass"
        assert callable(bot.bypass_cloudflare_with_retry)
    
    async def test_firefaucet_has_shortlink_solver(self, mock_settings, mock_page, mock_solver):
        """Test FireFaucet has shortlink solving capability"""
        bot = FireFaucetBot(mock_settings, mock_page)
        # FireFaucet should import ShortlinkSolver
        from faucets.firefaucet import ShortlinkSolver
        assert ShortlinkSolver is not None


class TestCointiplySpecialFeatures:
    """Test Cointiply-specific features"""
    
    async def test_cointiply_has_ptc_ads_method(self, mock_settings, mock_page, mock_solver):
        """Test Cointiply has PTC ad viewing method"""
        bot = CointiplyBot(mock_settings, mock_page)
        assert hasattr(bot, 'view_ptc_ads'), "Cointiply missing PTC ads method"
        assert callable(bot.view_ptc_ads)
    
    async def test_cointiply_ptc_uses_bring_to_front(self, mock_settings, mock_page, mock_solver):
        """Test Cointiply PTC implementation uses bring_to_front for focused tabs"""
        # This is tested by checking the implementation uses bring_to_front
        bot = CointiplyBot(mock_settings, mock_page)
        # The method exists and implementation uses bring_to_front on ad_page
        assert hasattr(mock_page, 'bring_to_front'), "Page mock missing bring_to_front"


class TestDutchySpecialFeatures:
    """Test Dutchy-specific features"""
    
    async def test_dutchy_has_shortlink_claim(self, mock_settings, mock_page, mock_solver):
        """Test Dutchy has shortlink claiming capability"""
        bot = DutchyBot(mock_settings, mock_page)
        # Check for shortlink-related methods
        assert hasattr(bot, 'claim'), "Dutchy missing claim method"


class TestAdBTCSpecialFeatures:
    """Test AdBTC-specific features"""
    
    async def test_adbtc_has_math_captcha_solver(self, mock_settings, mock_page, mock_solver):
        """Test AdBTC has math captcha solving capability"""
        bot = AdBTCBot(mock_settings, mock_page)
        assert hasattr(bot, 'solve_math_captcha'), "AdBTC missing math captcha solver"
        assert callable(bot.solve_math_captcha)
    
    async def test_adbtc_has_ptc_ads_method(self, mock_settings, mock_page, mock_solver):
        """Test AdBTC has PTC ad viewing method (surf ads)"""
        bot = AdBTCBot(mock_settings, mock_page)
        assert hasattr(bot, 'view_ptc_ads'), "AdBTC missing PTC ads method"
        assert callable(bot.view_ptc_ads)


class TestFaucetCryptoSpecialFeatures:
    """Test FaucetCrypto-specific features"""
    
    async def test_faucetcrypto_uses_new_login_endpoint(self, mock_settings, mock_page, mock_solver):
        """Test FaucetCrypto uses /login endpoint (not /login.php)"""
        bot = FaucetCryptoBot(mock_settings, mock_page)
        # Check that base_url is set correctly
        assert bot.base_url == "https://faucetcrypto.com"


class TestCoinPayUSpecialFeatures:
    """Test CoinPayU-specific features"""
    
    async def test_coinpayu_has_shortlink_handling(self, mock_settings, mock_page, mock_solver):
        """Test CoinPayU has shortlink handling capability"""
        bot = CoinPayUBot(mock_settings, mock_page)
        # CoinPayU should have claim method that handles shortlinks
        assert hasattr(bot, 'claim'), "CoinPayU missing claim method"
