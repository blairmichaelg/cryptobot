import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.coinpayu import CoinPayUBot
from faucets.base import ClaimResult
from core.config import BotSettings


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
    """Test successful login"""
    mock_page.url = "https://www.coinpayu.com/login"
    
    # Setup mock locators
    turnstile_locator = MagicMock()
    turnstile_locator.count = AsyncMock(return_value=0)
    
    alert_locator = MagicMock()
    alert_locator.count = AsyncMock(return_value=0)
    
    login_btn_locator = MagicMock()
    login_btn_locator.count = AsyncMock(return_value=1)
    login_btn_locator.click = AsyncMock()
    
    def locator_side_effect(selector):
        if "turnstile" in selector or "cf-turnstile" in selector:
            return turnstile_locator
        elif "alert-div" in selector or "alert-red" in selector:
            return alert_locator
        elif "Login" in selector:
            return login_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    bot.human_like_click = AsyncMock()
    
    result = await bot.login()
    
    assert result is True
    mock_page.fill.assert_called()
    mock_page.wait_for_url.assert_called()


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
    """Test successful claim"""
    # Setup balance locator
    balance_locator = MagicMock()
    balance_locator.count = AsyncMock(return_value=1)
    balance_locator.first = MagicMock()
    balance_locator.first.inner_text = AsyncMock(return_value="100 coins")
    
    # Setup claim button locators
    claim_btn_locator = MagicMock()
    claim_btn_locator.count = AsyncMock(return_value=2)
    claim_btn_locator.nth = MagicMock(return_value=claim_btn_locator)
    
    final_btn_locator = MagicMock()
    final_btn_locator.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "v2-dashboard-card-value" in selector:
            return balance_locator
        elif "Claim" in selector and "claim-now" not in selector:
            return claim_btn_locator
        elif "claim-now" in selector or "Claim Now" in selector:
            return final_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.claim()
    
    assert result.success is True
    assert "Claimed" in result.status


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
    amount_input_locator.get_attribute = AsyncMock(return_value="100")
    
    def locator_side_effect(selector):
        if "Transfer" in selector:
            return transfer_btn_locator
        elif "transfer-btn" in selector:
            return confirm_locator
        elif "amount" in selector:
            return amount_input_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = CoinPayUBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    
    result = await bot.transfer_faucet_to_main()
    
    assert result.success is True
    assert "Transferred" in result.status


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
