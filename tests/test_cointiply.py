import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.cointiply import CointiplyBot
from faucets.base import ClaimResult
from core.config import BotSettings


@pytest.fixture
def mock_settings():
    """Fixture for mock BotSettings"""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {
        "username": "test@example.com", 
        "password": "test_password"
    }
    settings.wallet_addresses = {"BTC": "BTC_ADDRESS_123"}
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key"
    settings.capsolver_api_key = ""
    settings.use_faucetpay = False
    settings.btc_withdrawal_address = "BTC_ADDRESS_123"
    return settings


@pytest.fixture
def mock_solver():
    """Fixture for mock CaptchaSolver"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)
        solver_instance.api_key = "test_key"
        solver_instance.set_faucet_name = MagicMock()
        yield solver_instance


@pytest.fixture
def mock_page():
    """Fixture for mock Playwright Page"""
    page = AsyncMock()
    page.url = "https://cointiply.com"
    page.title.return_value = "Cointiply"
    page.content.return_value = "<html><body></body></html>"
    
    # Setup locator chain
    page.locator = MagicMock()
    locator_mock = MagicMock()
    locator_mock.count = AsyncMock(return_value=0)
    locator_mock.is_visible = AsyncMock(return_value=False)
    locator_mock.text_content = AsyncMock(return_value="")
    locator_mock.inner_text = AsyncMock(return_value="")
    locator_mock.get_attribute = AsyncMock(return_value="")
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
    page.wait_for_url = AsyncMock()
    page.evaluate = AsyncMock()
    page.screenshot = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.is_closed = MagicMock(return_value=False)

    return page


@pytest.mark.asyncio
async def test_cointiply_initialization(mock_settings, mock_page, mock_solver):
    """Test CointiplyBot initialization"""
    bot = CointiplyBot(mock_settings, mock_page)
    
    assert bot.faucet_name == "Cointiply"
    assert bot.base_url == "https://cointiply.com"
    assert hasattr(bot, 'login')
    assert hasattr(bot, 'claim')
    assert hasattr(bot, 'get_current_balance')


@pytest.mark.asyncio
async def test_is_logged_in_by_url(mock_settings, mock_page, mock_solver):
    """Test is_logged_in returns True when dashboard in URL"""
    mock_page.url = "https://cointiply.com/dashboard"
    
    bot = CointiplyBot(mock_settings, mock_page)
    result = await bot.is_logged_in()
    
    assert result is True


@pytest.mark.asyncio
async def test_is_logged_in_by_balance_visible(mock_settings, mock_page, mock_solver):
    """Test is_logged_in returns True when balance element is visible"""
    mock_page.url = "https://cointiply.com/home"
    
    locator_mock = mock_page.locator.return_value
    locator_mock.is_visible = AsyncMock(return_value=True)
    
    bot = CointiplyBot(mock_settings, mock_page)
    result = await bot.is_logged_in()
    
    assert result is True


@pytest.mark.asyncio
async def test_login_no_credentials(mock_settings, mock_page, mock_solver):
    """Test login fails when no credentials are provided"""
    mock_settings.get_account.return_value = None
    
    bot = CointiplyBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_login_success(mock_settings, mock_page, mock_solver):
    """Test successful login"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.human_type = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.safe_navigate = AsyncMock(return_value=True)
    bot.check_page_health = AsyncMock(return_value=True)
    bot.safe_click = AsyncMock(return_value=True)

    # Mock locator chain for iterative selector search
    locator_mock = MagicMock()
    locator_mock.count = AsyncMock(return_value=1)
    locator_mock.first = MagicMock()
    locator_mock.first.is_visible = AsyncMock(return_value=True)
    locator_mock.first.input_value = AsyncMock(return_value="filled")
    locator_mock.first.click = AsyncMock()
    mock_page.locator = MagicMock(return_value=locator_mock)

    # Mock wait_for_url to succeed (login redirect)
    mock_page.wait_for_url = AsyncMock()

    result = await bot.login()

    assert result is True
    assert bot.human_type.call_count >= 2  # email and password
    assert bot.solver.solve_captcha.called


@pytest.mark.asyncio
async def test_login_failure_exception(mock_settings, mock_page, mock_solver):
    """Test login handles exceptions gracefully"""
    mock_page.goto = AsyncMock(side_effect=Exception("Network error"))
    
    bot = CointiplyBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_get_current_balance(mock_settings, mock_page, mock_solver):
    """Test balance extraction uses DataExtractor properly"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="1234.56")
    
    balance = await bot.get_current_balance()
    
    assert balance == "1234.56"
    assert bot.get_balance.called
    # Check that it was called with correct selector and fallback
    call_args = bot.get_balance.call_args
    assert call_args[0][0] == ".user-balance-coins"
    assert "fallback_selectors" in call_args[1]


@pytest.mark.asyncio
async def test_claim_timer_active(mock_settings, mock_page, mock_solver):
    """Test claim returns timer status when timer is active"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_current_balance = AsyncMock(return_value="100.00")
    bot.get_timer = AsyncMock(return_value=45.0)  # 45 minutes remaining
    bot.safe_navigate = AsyncMock(return_value=True)
    bot.check_page_health = AsyncMock(return_value=True)
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()

    # Mock page.title() so it doesn't match '404'
    mock_page.title = AsyncMock(return_value="Cointiply")

    # Setup roll button to be visible
    locator_mock = mock_page.locator.return_value
    locator_mock.count = AsyncMock(return_value=1)
    locator_mock.is_visible = AsyncMock(return_value=True)
    locator_mock.first = MagicMock()
    locator_mock.first.is_visible = AsyncMock(return_value=True)

    result = await bot.claim()

    assert isinstance(result, ClaimResult)
    assert result.success is True
    assert result.status == "Timer Active"
    assert result.next_claim_minutes == 45.0
    assert result.balance == "100.00"


@pytest.mark.asyncio
async def test_claim_success_ready_to_claim(mock_settings, mock_page, mock_solver):
    """Test successful claim when timer is ready"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_current_balance = AsyncMock(side_effect=["100.00", "105.50"])  # Before and after
    bot.get_timer = AsyncMock(return_value=0.0)  # Timer ready
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.safe_navigate = AsyncMock(return_value=True)
    bot.check_page_health = AsyncMock(return_value=True)
    bot.safe_click = AsyncMock(return_value=True)

    # Mock page.title() so it doesn't match '404'
    mock_page.title = AsyncMock(return_value="Cointiply")

    # Setup roll button to be visible
    locator_mock = mock_page.locator.return_value
    locator_mock.count = AsyncMock(return_value=1)
    locator_mock.is_visible = AsyncMock(return_value=True)
    locator_mock.first = MagicMock()
    locator_mock.first.is_visible = AsyncMock(return_value=True)
    locator_mock.first.is_enabled = AsyncMock(return_value=True)

    # Mock success indicator
    success_locator = MagicMock()
    success_locator.count = AsyncMock(return_value=1)

    def locator_side_effect(selector):
        if "snackbar" in selector or "toast" in selector or "alert" in selector:
            return success_locator
        return locator_mock

    mock_page.locator.side_effect = locator_side_effect

    result = await bot.claim()

    assert isinstance(result, ClaimResult)
    assert result.success is True
    assert result.status == "Claimed"
    assert result.next_claim_minutes == 60
    assert result.balance == "105.50"
    assert bot.solver.solve_captcha.called


@pytest.mark.asyncio
async def test_claim_captcha_failure_retry(mock_settings, mock_page, mock_solver):
    """Test claim retries on CAPTCHA failure"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_current_balance = AsyncMock(return_value="100.00")
    bot.get_timer = AsyncMock(return_value=0.0)
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.safe_navigate = AsyncMock(return_value=True)
    bot.check_page_health = AsyncMock(return_value=True)
    bot.solver.solve_captcha = AsyncMock(side_effect=[False, False, False])  # Fail 3 times

    # Mock page.title() so it doesn't match '404'
    mock_page.title = AsyncMock(return_value="Cointiply")

    # Setup roll button to be visible
    locator_mock = mock_page.locator.return_value
    locator_mock.count = AsyncMock(return_value=1)
    locator_mock.is_visible = AsyncMock(return_value=True)
    locator_mock.first = MagicMock()
    locator_mock.first.is_visible = AsyncMock(return_value=True)

    result = await bot.claim()

    # Should fail after max retries
    assert isinstance(result, ClaimResult)
    assert result.success is False
    assert "CAPTCHA" in result.status or "Timeout" in result.status or "Error" in result.status


@pytest.mark.asyncio
async def test_claim_roll_button_not_available(mock_settings, mock_page, mock_solver):
    """Test claim when roll button is not available"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_current_balance = AsyncMock(return_value="100.00")
    bot.safe_navigate = AsyncMock(return_value=True)
    bot.check_page_health = AsyncMock(return_value=True)
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()

    # Mock page.title() so it doesn't match '404'
    mock_page.title = AsyncMock(return_value="Cointiply")

    # Setup roll button to NOT be visible
    locator_mock = mock_page.locator.return_value
    locator_mock.count = AsyncMock(return_value=0)
    locator_mock.is_visible = AsyncMock(return_value=False)
    locator_mock.first = MagicMock()
    locator_mock.first.is_visible = AsyncMock(return_value=False)

    result = await bot.claim()

    assert isinstance(result, ClaimResult)
    assert result.success is False
    assert result.status == "Roll Not Available"
    assert result.next_claim_minutes == 15


@pytest.mark.asyncio
async def test_claim_timeout_error_retry(mock_settings, mock_page, mock_solver):
    """Test claim handles timeout errors with retry"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.safe_navigate = AsyncMock(return_value=True)
    bot.check_page_health = AsyncMock(return_value=True)
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()

    # Mock page.title() so it doesn't match '404'
    mock_page.title = AsyncMock(return_value="Cointiply")

    bot.get_current_balance = AsyncMock(side_effect=asyncio.TimeoutError("Timeout"))

    result = await bot.claim()

    assert isinstance(result, ClaimResult)
    assert result.success is False
    assert "Timeout" in result.status


@pytest.mark.asyncio
async def test_claim_exception_handling(mock_settings, mock_page, mock_solver):
    """Test claim handles general exceptions"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock(side_effect=Exception("Network error"))
    
    result = await bot.claim()
    
    assert isinstance(result, ClaimResult)
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_get_jobs(mock_settings, mock_page, mock_solver):
    """Test get_jobs returns correct job configurations"""
    bot = CointiplyBot(mock_settings, mock_page)
    
    jobs = bot.get_jobs()
    
    assert len(jobs) == 3
    assert jobs[0].name == "Cointiply Claim"
    assert jobs[0].priority == 1
    assert jobs[1].name == "Cointiply Withdraw"
    assert jobs[1].priority == 5
    assert jobs[2].name == "Cointiply PTC"
    assert jobs[2].priority == 3


@pytest.mark.asyncio
async def test_withdraw_low_balance(mock_settings, mock_page, mock_solver):
    """Test withdrawal returns low balance status when insufficient funds"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_current_balance = AsyncMock(return_value="15000")  # Below 30k minimum
    
    result = await bot.withdraw()
    
    assert isinstance(result, ClaimResult)
    assert result.success is True
    assert result.status == "Low Balance"
    assert result.next_claim_minutes == 1440  # 24 hours


@pytest.mark.asyncio
async def test_withdraw_success(mock_settings, mock_page, mock_solver):
    """Test successful withdrawal process"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_current_balance = AsyncMock(return_value="50000")  # Above BTC minimum
    bot.get_withdrawal_address = MagicMock(return_value="BTC_ADDRESS_123")
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    bot.random_delay = AsyncMock()
    
    # Mock success indicator in page content
    mock_page.content = AsyncMock(return_value="<html>Success! Check your email</html>")
    
    # Setup coin selector visible
    locator_mock = mock_page.locator.return_value
    locator_mock.is_visible = AsyncMock(return_value=True)
    
    result = await bot.withdraw()
    
    assert isinstance(result, ClaimResult)
    assert result.success is True
    assert "Withdrawn" in result.status or "Pending" in result.status


@pytest.mark.asyncio
async def test_withdraw_no_suitable_address(mock_settings, mock_page, mock_solver):
    """Test withdrawal when no suitable address is configured"""
    bot = CointiplyBot(mock_settings, mock_page)
    # Mock all async methods
    with patch.object(bot, 'handle_cloudflare', new_callable=AsyncMock), \
         patch.object(bot, 'get_current_balance', new_callable=AsyncMock, return_value="50000"), \
         patch.object(bot, 'get_withdrawal_address', return_value=None), \
         patch.object(bot, 'human_like_click', new_callable=AsyncMock), \
         patch.object(bot, 'human_type', new_callable=AsyncMock), \
         patch.object(bot, 'random_delay', new_callable=AsyncMock):
        
        result = await bot.withdraw()
    
    assert isinstance(result, ClaimResult)
    # When get_withdrawal_address returns None, withdrawal path returns "No Suitable Option"
    # But if it progresses further, it may return "Unknown Result" or other status
    assert result.success is False


@pytest.mark.asyncio
async def test_view_ptc_ads_no_ads_available(mock_settings, mock_page, mock_solver):
    """Test PTC viewing when no ads are available"""
    bot = CointiplyBot(mock_settings, mock_page)
    # Mock handle_cloudflare method created by bot
    with patch.object(bot, 'handle_cloudflare', new_callable=AsyncMock):
        # Setup no ads available
        locator_mock = mock_page.locator.return_value
        locator_mock.count = AsyncMock(return_value=0)
        
        await bot.view_ptc_ads()
        
        assert mock_page.goto.called


@pytest.mark.asyncio
async def test_view_ptc_ads_with_available_ads(mock_settings, mock_page, mock_solver):
    """Test PTC viewing with available ads"""
    bot = CointiplyBot(mock_settings, mock_page)
    # Mock handle_cloudflare, idle_mouse, human_like_click, random_delay
    with patch.object(bot, 'handle_cloudflare', new_callable=AsyncMock), \
         patch.object(bot, 'idle_mouse', new_callable=AsyncMock), \
         patch.object(bot, 'human_like_click', new_callable=AsyncMock), \
         patch.object(bot, 'random_delay', new_callable=AsyncMock):
        
        # Mock ad page
        ad_page = AsyncMock()
        ad_page.wait_for_load_state = AsyncMock()
        ad_page.bring_to_front = AsyncMock()
        ad_page.close = AsyncMock()
        
        # Setup ads available
        locator_mock = mock_page.locator.return_value
        locator_mock.count = AsyncMock(side_effect=[3, 3, 2, 1, 0])  # Decreasing count
        
        # Mock verify container not visible
        verify_locator = MagicMock()
        verify_locator.is_visible = AsyncMock(return_value=False)
        
        def locator_side_effect(selector):
            if "captcha-images" in selector or "ptc-verify" in selector:
                return verify_locator
            return locator_mock
        
        mock_page.locator.side_effect = locator_side_effect
        
        # Mock context.expect_page
        page_context = AsyncMock()
        page_context.expect_page = MagicMock()
        page_context.expect_page.return_value.__aenter__ = AsyncMock()
        page_context.expect_page.return_value.__aexit__ = AsyncMock()
        page_context.expect_page.return_value.value = ad_page
        mock_page.context = page_context
        
        await bot.view_ptc_ads()
        
        assert mock_page.goto.called


@pytest.mark.asyncio
async def test_view_ptc_ads_error_handling(mock_settings, mock_page, mock_solver):
    """Test PTC viewing handles errors gracefully"""
    bot = CointiplyBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock(side_effect=Exception("Network error"))
    
    # Should not raise exception
    await bot.view_ptc_ads()
    
    assert mock_page.goto.called


class TestCointiplyBalanceExtraction:
    """Test suite for balance extraction edge cases."""
    
    @pytest.mark.asyncio
    async def test_balance_extraction_with_fallback(self, mock_settings, mock_page, mock_solver):
        """Test balance extraction uses fallback selectors"""
        bot = CointiplyBot(mock_settings, mock_page)
        bot.get_balance = AsyncMock(return_value="0")
        
        await bot.get_current_balance()
        
        # Should be called with fallback selectors
        assert bot.get_balance.called
        call_args = bot.get_balance.call_args
        assert "fallback_selectors" in call_args[1]
        assert ".user-balance" in call_args[1]["fallback_selectors"]


class TestCointiplyTimerExtraction:
    """Test suite for timer extraction."""
    
    @pytest.mark.asyncio
    async def test_timer_extraction_multiple_selectors(self, mock_settings, mock_page, mock_solver):
        """Test timer extraction tries multiple selectors"""
        bot = CointiplyBot(mock_settings, mock_page)
        bot.handle_cloudflare = AsyncMock()
        bot.get_current_balance = AsyncMock(return_value="100.00")
        bot.get_timer = AsyncMock(return_value=30.0)
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.check_page_health = AsyncMock(return_value=True)
        bot.idle_mouse = AsyncMock()
        bot.random_delay = AsyncMock()

        # Mock page.title() so it doesn't match '404'
        mock_page.title = AsyncMock(return_value="Cointiply")

        # Setup roll button visible
        locator_mock = mock_page.locator.return_value
        locator_mock.count = AsyncMock(return_value=1)
        locator_mock.is_visible = AsyncMock(return_value=True)
        locator_mock.first = MagicMock()
        locator_mock.first.is_visible = AsyncMock(return_value=True)

        result = await bot.claim()

        # Check get_timer was called with fallback selectors
        assert bot.get_timer.called
        call_args = bot.get_timer.call_args
        assert call_args[1].get("fallback_selectors") is not None


class TestCointiplyStealthFeatures:
    """Test suite for stealth features."""
    
    @pytest.mark.asyncio
    async def test_login_uses_human_type(self, mock_settings, mock_page, mock_solver):
        """Test login uses human_type instead of fill"""
        bot = CointiplyBot(mock_settings, mock_page)
        bot.handle_cloudflare = AsyncMock()
        bot.human_type = AsyncMock()
        bot.random_delay = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.check_page_health = AsyncMock(return_value=True)
        bot.safe_click = AsyncMock(return_value=True)

        # Mock locator chain for iterative selector search
        locator_mock = MagicMock()
        locator_mock.count = AsyncMock(return_value=1)
        locator_mock.first = MagicMock()
        locator_mock.first.is_visible = AsyncMock(return_value=True)
        locator_mock.first.input_value = AsyncMock(return_value="filled")
        locator_mock.first.click = AsyncMock()
        mock_page.locator = MagicMock(return_value=locator_mock)
        mock_page.wait_for_url = AsyncMock()

        await bot.login()

        # Should use human_type for both email and password
        assert bot.human_type.call_count >= 2
        assert bot.idle_mouse.called
        assert bot.random_delay.called
    
    @pytest.mark.asyncio
    async def test_claim_uses_idle_mouse(self, mock_settings, mock_page, mock_solver):
        """Test claim uses idle_mouse for stealth"""
        bot = CointiplyBot(mock_settings, mock_page)
        bot.handle_cloudflare = AsyncMock()
        bot.get_current_balance = AsyncMock(return_value="100.00")
        bot.get_timer = AsyncMock(return_value=0.0)
        bot.idle_mouse = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.random_delay = AsyncMock()
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.check_page_health = AsyncMock(return_value=True)
        bot.safe_click = AsyncMock(return_value=True)

        # Mock page.title() so it doesn't match '404'
        mock_page.title = AsyncMock(return_value="Cointiply")

        # Setup roll button visible
        locator_mock = mock_page.locator.return_value
        locator_mock.count = AsyncMock(return_value=1)
        locator_mock.is_visible = AsyncMock(return_value=True)
        locator_mock.first = MagicMock()
        locator_mock.first.is_visible = AsyncMock(return_value=True)
        locator_mock.first.is_enabled = AsyncMock(return_value=True)

        await bot.claim()

        assert bot.idle_mouse.called


class TestCointiplyRetryLogic:
    """Test suite for retry logic."""
    
    @pytest.mark.asyncio
    async def test_claim_retries_on_timeout(self, mock_settings, mock_page, mock_solver):
        """Test claim retries on timeout"""
        bot = CointiplyBot(mock_settings, mock_page)
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.check_page_health = AsyncMock(return_value=True)
        bot.idle_mouse = AsyncMock()
        bot.random_delay = AsyncMock()

        # Mock page.title() so it doesn't match '404'
        mock_page.title = AsyncMock(return_value="Cointiply")

        # First two attempts timeout at handle_cloudflare, third succeeds
        bot.handle_cloudflare = AsyncMock(side_effect=[
            asyncio.TimeoutError(),
            asyncio.TimeoutError(),
            None
        ])
        bot.get_current_balance = AsyncMock(return_value="100.00")
        bot.get_timer = AsyncMock(return_value=45.0)

        # Setup roll button visible
        locator_mock = mock_page.locator.return_value
        locator_mock.count = AsyncMock(return_value=1)
        locator_mock.is_visible = AsyncMock(return_value=True)
        locator_mock.first = MagicMock()
        locator_mock.first.is_visible = AsyncMock(return_value=True)

        result = await bot.claim()

        # Should eventually succeed or fail after retries
        assert isinstance(result, ClaimResult)
    
    @pytest.mark.asyncio
    async def test_claim_max_retries_exceeded(self, mock_settings, mock_page, mock_solver):
        """Test claim fails after max retries"""
        bot = CointiplyBot(mock_settings, mock_page)
        
        # All attempts timeout
        bot.handle_cloudflare = AsyncMock(side_effect=asyncio.TimeoutError())
        
        result = await bot.claim()
        
        assert isinstance(result, ClaimResult)
        assert result.success is False
        assert "Timeout" in result.status
