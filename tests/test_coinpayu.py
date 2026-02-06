import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.coinpayu import CoinPayUBot
from faucets.base import ClaimResult
from core.config import BotSettings
from core.extractor import DataExtractor


@pytest.fixture
def mock_settings():
    """Fixture for mock BotSettings"""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {"username": "test@example.com", "password": "test_password"}
    settings.wallet_addresses = {"LTC": {"address": "LTC_ADDRESS_123"}}
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key"
    settings.capsolver_api_key = ""
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
    page.url = "https://www.coinpayu.com"
    page.title.return_value = "CoinPayU"
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
    locator_mock.first.inner_text = AsyncMock(return_value="")
    locator_mock.first.click = AsyncMock()
    locator_mock.nth = MagicMock(return_value=locator_mock)
    page.locator.return_value = locator_mock
    
    page.query_selector = AsyncMock(return_value=None)
    page.goto = AsyncMock()
    page.fill = AsyncMock()
    page.click = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    
    return page


@pytest.mark.asyncio
async def test_coinpayu_initialization(mock_settings, mock_page, mock_solver):
    """Test CoinPayUBot initialization"""
    bot = CoinPayUBot(mock_settings, mock_page)
    
    assert bot.faucet_name == "CoinPayU"
    assert bot.base_url == "https://www.coinpayu.com"
    assert hasattr(bot, 'login')
    assert hasattr(bot, 'claim')


@pytest.mark.asyncio
async def test_coinpayu_login_no_credentials(mock_settings, mock_page, mock_solver):
    """Test login fails when no credentials are provided"""
    mock_settings.get_account.return_value = None
    
    bot = CoinPayUBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_coinpayu_login_already_logged_in(mock_settings, mock_page, mock_solver):
    """Test login when already logged in"""
    mock_page.url = "https://www.coinpayu.com/dashboard"
    
    bot = CoinPayUBot(mock_settings, mock_page)
    
    result = await bot.login()
    
    assert result is True


@pytest.mark.asyncio
async def test_coinpayu_login_success(mock_settings, mock_page, mock_solver):
    """Test successful login with new stealth features"""
    mock_page.url = "https://www.coinpayu.com/login"
    
    # Setup email and password field locators
    email_field_locator = MagicMock()
    email_field_locator.count = AsyncMock(return_value=1)
    email_field_locator.first = MagicMock()
    email_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    password_field_locator = MagicMock()
    password_field_locator.count = AsyncMock(return_value=1)
    password_field_locator.first = MagicMock()
    password_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    # Setup mock locators
    turnstile_locator = MagicMock()
    turnstile_locator.count = AsyncMock(return_value=0)
    
    alert_locator = MagicMock()
    alert_locator.count = AsyncMock(return_value=0)
    
    login_btn_locator = MagicMock()
    login_btn_locator.count = AsyncMock(return_value=1)
    login_btn_locator.first = MagicMock()
    login_btn_locator.first.is_visible = AsyncMock(return_value=True)
    login_btn_locator.first.click = AsyncMock()
    
    def locator_side_effect(selector):
        if "turnstile" in selector or "cf-turnstile" in selector:
            return turnstile_locator
        elif "alert-div" in selector or "alert-red" in selector:
            return alert_locator
        elif 'email' in selector.lower():
            return email_field_locator
        elif 'password' in selector.lower():
            return password_field_locator
        elif "Login" in selector or "btn" in selector or "submit" in selector:
            return login_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    
    result = await bot.login()
    
    assert result is True
    bot.human_type.assert_called()  # Should be called for email and password
    mock_page.wait_for_url.assert_called()
    bot.handle_cloudflare.assert_called()


@pytest.mark.asyncio
async def test_coinpayu_login_proxy_detected(mock_settings, mock_page, mock_solver):
    """Test login fails when proxy is detected"""
    mock_page.url = "https://www.coinpayu.com/login"
    
    # Setup error message locator
    alert_locator = MagicMock()
    alert_locator.count = AsyncMock(return_value=1)
    alert_locator.is_visible = AsyncMock(return_value=True)
    alert_locator.inner_text = AsyncMock(return_value="Proxy detected")
    
    login_btn_locator = MagicMock()
    login_btn_locator.count = AsyncMock(return_value=1)
    login_btn_locator.click = AsyncMock()
    
    def locator_side_effect(selector):
        if "alert-div" in selector or "alert-red" in selector:
            return alert_locator
        elif "Login" in selector:
            return login_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    bot.human_like_click = AsyncMock()
    
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_coinpayu_login_exception(mock_settings, mock_page, mock_solver):
    """Test login handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = CoinPayUBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_coinpayu_claim_success(mock_settings, mock_page, mock_solver):
    """Test successful claim with new timer and balance extraction"""
    # Setup balance locator
    balance_locator = MagicMock()
    balance_locator.count = AsyncMock(return_value=1)
    balance_locator.first = MagicMock()
    balance_locator.first.count = AsyncMock(return_value=1)
    balance_locator.first.is_visible = AsyncMock(return_value=True)
    balance_locator.first.text_content = AsyncMock(return_value="100.5 coins")
    
    # Setup timer locator (no timer active)
    timer_locator = MagicMock()
    timer_locator.count = AsyncMock(return_value=0)
    
    # Setup claim button locators
    claim_btn_locator = MagicMock()
    claim_btn_locator.count = AsyncMock(return_value=2)
    claim_btn_locator.nth = MagicMock(return_value=claim_btn_locator)
    
    final_btn_locator = MagicMock()
    final_btn_locator.count = AsyncMock(return_value=1)
    
    confirm_btn_locator = MagicMock()
    confirm_btn_locator.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "v2-dashboard-card-value" in selector or "balance" in selector:
            return balance_locator
        elif "timer" in selector or "countdown" in selector:
            return timer_locator
        elif "#claim-now" in selector:
            return final_btn_locator
        elif "Claim Now" in selector:
            return confirm_btn_locator
        elif "Claim" in selector:
            return claim_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100.5")
    bot.get_timer = AsyncMock(return_value=0.0)  # No timer active
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    
    result = await bot.claim()
    
    assert result.success is True
    assert "Claimed" in result.status
    assert result.next_claim_minutes == 60.0
    bot.get_timer.assert_called()  # Should check for timer
    bot.get_balance.assert_called()  # Should extract balance


@pytest.mark.asyncio
async def test_coinpayu_claim_exception(mock_settings, mock_page, mock_solver):
    """Test claim handles exceptions"""
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(side_effect=Exception("Error"))
    
    result = await bot.claim()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_coinpayu_view_ptc_ads(mock_settings, mock_page, mock_solver):
    """Test viewing PTC ads"""
    # Setup context for new page
    mock_context = MagicMock()
    mock_new_page = AsyncMock()
    mock_new_page.close = AsyncMock()
    
    expect_page = MagicMock()
    expect_page.value = asyncio.Future()
    expect_page.value.set_result(mock_new_page)
    mock_context.expect_page.return_value.__aenter__ = AsyncMock(return_value=expect_page)
    mock_context.expect_page.return_value.__aexit__ = AsyncMock()
    
    mock_page.context = mock_context
    
    # Setup ad items locator
    ad_items_locator = MagicMock()
    ad_items_locator.count = AsyncMock(side_effect=[2, 1, 0])  # Two ads, then one, then none
    ad_items_locator.first = MagicMock()
    ad_items_locator.first.locator = MagicMock()
    
    # Setup duration locator
    duration_locator = MagicMock()
    duration_locator.first = MagicMock()
    duration_locator.first.inner_text = AsyncMock(return_value="15 sec")
    ad_items_locator.first.locator.return_value = duration_locator
    
    # Setup title locator
    title_locator = MagicMock()
    title_locator.first = MagicMock()
    title_locator.first.click = AsyncMock()
    ad_items_locator.first.locator = MagicMock(return_value=title_locator)
    
    captcha_locator = MagicMock()
    captcha_locator.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "ags-list-box" in selector and "gray-all" in selector:
            return ad_items_locator
        elif "turnstile" in selector or "captcha" in selector:
            return captcha_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    mock_page.wait_for_selector = AsyncMock()
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    await bot.view_ptc_ads()
    
    # Verify method completed
    assert True


@pytest.mark.asyncio
async def test_coinpayu_transfer_faucet_to_main(mock_settings, mock_page, mock_solver):
    """Test transferring faucet to main balance"""
    transfer_btn_locator = MagicMock()
    transfer_btn_locator.count = AsyncMock(return_value=2)
    transfer_btn_locator.nth = MagicMock(return_value=transfer_btn_locator)
    
    confirm_locator = MagicMock()
    confirm_locator.count = AsyncMock(return_value=1)
    
    amount_input_locator = MagicMock()
    amount_input_locator.count = AsyncMock(return_value=1)
    amount_input_locator.get_attribute = AsyncMock(return_value="100")
    
    def locator_side_effect(selector):
        if "Transfer" in selector:
            return transfer_btn_locator
        elif "transfer-btn" in selector or "btn-primary" in selector:
            return confirm_locator
        elif "amount" in selector:
            return amount_input_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    
    result = await bot.transfer_faucet_to_main()
    
    assert result.success is True
    assert "Transferred" in result.status
    bot.handle_cloudflare.assert_called()


@pytest.mark.asyncio
async def test_coinpayu_transfer_exception(mock_settings, mock_page, mock_solver):
    """Test transfer handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = CoinPayUBot(mock_settings, mock_page)
    result = await bot.transfer_faucet_to_main()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_coinpayu_withdraw_success(mock_settings, mock_page, mock_solver):
    """Test successful withdrawal"""
    method_dropdown = MagicMock()
    method_dropdown.click = AsyncMock()
    
    option_locator = MagicMock()
    option_locator.count = AsyncMock(return_value=1)
    option_locator.first = MagicMock()
    option_locator.first.click = AsyncMock()
    
    confirm_btn = MagicMock()
    confirm_btn.count = AsyncMock(return_value=1)
    
    otp_field = MagicMock()
    otp_field.count = AsyncMock(return_value=0)
    
    final_btn = MagicMock()
    final_btn.last = MagicMock()
    
    def locator_side_effect(selector):
        if "select-method" in selector:
            return method_dropdown
        elif "Litecoin" in selector or "FaucetPay" in selector:
            return option_locator
        elif "Confirm" in selector and "2FA" not in selector:
            if "last" in str(selector):
                return final_btn
            return confirm_btn
        elif "google_code" in selector or "2FA" in selector:
            return otp_field
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "Withdrawn"


@pytest.mark.asyncio
async def test_coinpayu_withdraw_2fa_required(mock_settings, mock_page, mock_solver):
    """Test withdrawal when 2FA is required"""
    method_dropdown = MagicMock()
    method_dropdown.click = AsyncMock()
    
    option_locator = MagicMock()
    option_locator.count = AsyncMock(return_value=1)
    option_locator.first = MagicMock()
    option_locator.first.click = AsyncMock()
    
    confirm_btn = MagicMock()
    confirm_btn.count = AsyncMock(return_value=1)
    
    otp_field = MagicMock()
    otp_field.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "select-method" in selector:
            return method_dropdown
        elif "Litecoin" in selector or "FaucetPay" in selector:
            return option_locator
        elif "Confirm" in selector:
            return confirm_btn
        elif "google_code" in selector or "2FA" in selector:
            return otp_field
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is False
    assert result.status == "2FA Required"


@pytest.mark.asyncio
async def test_coinpayu_withdraw_exception(mock_settings, mock_page, mock_solver):
    """Test withdrawal handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = CoinPayUBot(mock_settings, mock_page)
    result = await bot.withdraw()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_coinpayu_get_jobs(mock_settings, mock_page, mock_solver):
    """Test get_jobs returns correct job structure"""
    bot = CoinPayUBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 4
    assert jobs[0].name == "CoinPayU Claim"
    assert jobs[1].name == "CoinPayU PTC"
    assert jobs[2].name == "CoinPayU Consolidate"
    assert jobs[3].name == "CoinPayU Withdraw"


@pytest.mark.asyncio
async def test_coinpayu_consolidate_wrapper(mock_settings, mock_page, mock_solver):
    """Test consolidate wrapper"""
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.login_wrapper = AsyncMock(return_value=False)
    
    result = await bot.consolidate_wrapper(mock_page)
    
    assert result.success is False
    assert result.status == "Login/Access Failed"


@pytest.mark.asyncio
async def test_coinpayu_claim_with_timer_active(mock_settings, mock_page, mock_solver):
    """Test claim when timer is still active"""
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100.5")
    bot.get_timer = AsyncMock(return_value=45.0)  # 45 minutes remaining
    bot.handle_cloudflare = AsyncMock(return_value=True)
    
    result = await bot.claim()
    
    assert result.success is False
    assert "Timer active" in result.status
    assert result.next_claim_minutes == 45.0


@pytest.mark.asyncio
async def test_coinpayu_balance_extraction():
    """Test balance extraction with DataExtractor"""
    # Test various balance formats
    test_cases = [
        ("100.5 BTC", "100.5"),
        ("Balance: 1,234.56", "1234.56"),
        ("0.00012345 LTC", "0.00012345"),
        ("1234", "1234"),
    ]
    
    for input_text, expected in test_cases:
        result = DataExtractor.extract_balance(input_text)
        assert result == expected, f"Failed for input: {input_text}"


@pytest.mark.asyncio
async def test_coinpayu_timer_extraction():
    """Test timer extraction with DataExtractor"""
    # Test various timer formats
    test_cases = [
        ("59:59", 59.983),  # MM:SS
        ("01:30:00", 90.0),  # HH:MM:SS
        ("1h 30m", 90.0),
        ("45 min", 45.0),
        ("120 seconds", 2.0),
        ("2 hours", 120.0),
    ]
    
    for input_text, expected in test_cases:
        result = DataExtractor.parse_timer_to_minutes(input_text)
        assert abs(result - expected) < 0.1, f"Failed for input: {input_text}. Got {result}, expected {expected}"


@pytest.mark.asyncio
async def test_coinpayu_login_retry_on_timeout(mock_settings, mock_page, mock_solver):
    """Test login retries on timeout"""
    # Setup: First 2 attempts timeout, 3rd succeeds
    attempt_counter = {'count': 0}
    
    async def navigate_side_effect(*args, **kwargs):
        attempt_counter['count'] += 1
        if attempt_counter['count'] <= 2:
            raise asyncio.TimeoutError()
        return None
    
    # Setup email and password field locators
    email_field_locator = MagicMock()
    email_field_locator.count = AsyncMock(return_value=1)
    email_field_locator.first = MagicMock()
    email_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    password_field_locator = MagicMock()
    password_field_locator.count = AsyncMock(return_value=1)
    password_field_locator.first = MagicMock()
    password_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    login_btn_locator = MagicMock()
    login_btn_locator.count = AsyncMock(return_value=1)
    login_btn_locator.first = MagicMock()
    login_btn_locator.first.is_visible = AsyncMock(return_value=True)
    
    turnstile_locator = MagicMock()
    turnstile_locator.count = AsyncMock(return_value=0)
    
    alert_locator = MagicMock()
    alert_locator.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if 'email' in selector.lower():
            return email_field_locator
        elif 'password' in selector.lower():
            return password_field_locator
        elif "turnstile" in selector or "cf-turnstile" in selector:
            return turnstile_locator
        elif "Login" in selector or "submit" in selector or "btn" in selector:
            return login_btn_locator
        elif "alert" in selector:
            return alert_locator
        return MagicMock()
    
    mock_page.url = "https://www.coinpayu.com/login"  # Start on login page
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.safe_navigate = AsyncMock(side_effect=navigate_side_effect)
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    
    # After 3rd attempt, switch to dashboard (logged in)
    async def wait_for_url_side_effect(*args, **kwargs):
        mock_page.url = "https://www.coinpayu.com/dashboard"
    
    mock_page.wait_for_url = AsyncMock(side_effect=wait_for_url_side_effect)
    
    result = await bot.login()
    
    assert result is True
    assert bot.safe_navigate.call_count == 3  # Should retry 3 times


@pytest.mark.asyncio
async def test_coinpayu_login_max_retries_exceeded(mock_settings, mock_page, mock_solver):
    """Test login fails after max retries"""
    mock_page.goto.side_effect = asyncio.TimeoutError()  # Always timeout
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    
    result = await bot.login()
    
    assert result is False
    assert mock_page.goto.call_count == 3  # Should try 3 times


@pytest.mark.asyncio
async def test_coinpayu_claim_no_buttons_available(mock_settings, mock_page, mock_solver):
    """Test claim when no claim buttons are available"""
    claim_btn_locator = MagicMock()
    claim_btn_locator.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "Claim" in selector:
            return claim_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot.get_timer = AsyncMock(return_value=0.0)
    bot.handle_cloudflare = AsyncMock(return_value=True)
    
    result = await bot.claim()
    
    assert result.success is False
    assert "No claims available" in result.status


@pytest.mark.asyncio
async def test_coinpayu_captcha_failure_handling(mock_settings, mock_page, mock_solver):
    """Test handling of CAPTCHA failures during claim"""
    # Setup mocks
    claim_btn_locator = MagicMock()
    claim_btn_locator.count = AsyncMock(return_value=1)
    claim_btn_locator.nth = MagicMock(return_value=claim_btn_locator)
    
    final_btn_locator = MagicMock()
    final_btn_locator.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "Claim" in selector:
            return claim_btn_locator
        elif "#claim-now" in selector:
            return final_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot.get_timer = AsyncMock(return_value=0.0)
    bot.handle_cloudflare = AsyncMock(return_value=True)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.idle_mouse = AsyncMock()
    
    # Mock CAPTCHA solver to fail
    bot.solver.solve_captcha = AsyncMock(return_value=False)
    
    result = await bot.claim()
    
    # Should still attempt to claim even if CAPTCHA solving fails
    assert bot.solver.solve_captcha.called


@pytest.mark.asyncio
async def test_coinpayu_login_fallback_selectors(mock_settings, mock_page, mock_solver):
    """Test login with fallback selectors when primary selector fails"""
    mock_page.url = "https://www.coinpayu.com/login"
    
    # Setup email and password field locators
    email_field_locator = MagicMock()
    email_field_locator.count = AsyncMock(return_value=1)
    email_field_locator.first = MagicMock()
    email_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    password_field_locator = MagicMock()
    password_field_locator.count = AsyncMock(return_value=1)
    password_field_locator.first = MagicMock()
    password_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    # Setup mock locators - primary selector fails, fallback succeeds
    primary_btn_locator = MagicMock()
    primary_btn_locator.count = AsyncMock(return_value=0)  # Primary selector not found
    
    fallback_btn_locator = MagicMock()
    fallback_btn_locator.count = AsyncMock(return_value=1)  # Fallback found
    fallback_btn_locator.first = MagicMock()
    fallback_btn_locator.first.is_visible = AsyncMock(return_value=True)
    fallback_btn_locator.first.click = AsyncMock()
    
    turnstile_locator = MagicMock()
    turnstile_locator.count = AsyncMock(return_value=0)
    
    alert_locator = MagicMock()
    alert_locator.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "turnstile" in selector or "cf-turnstile" in selector:
            return turnstile_locator
        elif "alert-div" in selector or "alert-red" in selector:
            return alert_locator
        elif 'email' in selector.lower():
            return email_field_locator
        elif 'password' in selector.lower():
            return password_field_locator
        elif 'button.btn-primary:has-text("Login")' in selector:
            return primary_btn_locator  # Primary fails
        elif "Login" in selector or "submit" in selector or "btn" in selector:
            return fallback_btn_locator  # Fallback works
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    
    result = await bot.login()
    
    # Should succeed using fallback selector
    assert result is True
    bot.human_like_click.assert_called()  # Should click the fallback button
    bot.handle_cloudflare.assert_called()


@pytest.mark.asyncio
async def test_coinpayu_login_post_captcha_dom_change(mock_settings, mock_page, mock_solver):
    """Test login handles DOM changes after CAPTCHA solve"""
    mock_page.url = "https://www.coinpayu.com/login"
    
    # Simulate CAPTCHA solving
    mock_page.wait_for_load_state = AsyncMock()
    
    # Setup email and password field locators
    email_field_locator = MagicMock()
    email_field_locator.count = AsyncMock(return_value=1)
    email_field_locator.first = MagicMock()
    email_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    password_field_locator = MagicMock()
    password_field_locator.count = AsyncMock(return_value=1)
    password_field_locator.first = MagicMock()
    password_field_locator.first.is_visible = AsyncMock(return_value=True)
    
    login_btn_locator = MagicMock()
    login_btn_locator.count = AsyncMock(return_value=1)
    login_btn_locator.first = MagicMock()
    login_btn_locator.first.is_visible = AsyncMock(return_value=True)
    login_btn_locator.first.click = AsyncMock()
    
    turnstile_locator = MagicMock()
    turnstile_locator.count = AsyncMock(return_value=1)  # CAPTCHA present
    
    alert_locator = MagicMock()
    alert_locator.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "turnstile" in selector or "cf-turnstile" in selector:
            return turnstile_locator
        elif "alert-div" in selector or "alert-red" in selector:
            return alert_locator
        elif 'email' in selector.lower():
            return email_field_locator
        elif 'password' in selector.lower():
            return password_field_locator
        elif "Login" in selector or "submit" in selector or "btn" in selector:
            return login_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    # Mock CAPTCHA solver to return success
    mock_solver.solve_captcha = AsyncMock(return_value=True)
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.solver = mock_solver
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock(return_value=True)
    
    result = await bot.login()
    
    # Should succeed and wait for DOM to stabilize after CAPTCHA
    assert result is True
    mock_page.wait_for_load_state.assert_called()  # Should wait for DOM changes
    bot.human_like_click.assert_called()  # Should click login button

