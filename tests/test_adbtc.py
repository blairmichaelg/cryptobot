import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.adbtc import AdBTCBot
from faucets.base import ClaimResult
from core.config import BotSettings


@pytest.fixture
def mock_settings():
    """Fixture for mock BotSettings"""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {"username": "test@example.com", "password": "test_password"}
    settings.wallet_addresses = {"BTC": {"address": "BTC_ADDRESS_123"}}
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
    page.url = "https://adbtc.top"
    page.title.return_value = "AdBTC"
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
    locator_mock.select_option = AsyncMock()
    page.locator.return_value = locator_mock
    
    page.query_selector = AsyncMock(return_value=None)
    page.goto = AsyncMock()
    page.fill = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.screenshot = AsyncMock()
    
    return page


@pytest.mark.asyncio
async def test_adbtc_initialization(mock_settings, mock_page, mock_solver):
    """Test AdBTCBot initialization"""
    bot = AdBTCBot(mock_settings, mock_page)
    
    assert bot.faucet_name == "AdBTC"
    assert bot.base_url == "https://adbtc.top"
    assert hasattr(bot, 'login')
    assert hasattr(bot, 'claim')
    assert hasattr(bot, 'view_ptc_ads')
    assert hasattr(bot, 'withdraw')
    assert hasattr(bot, 'solve_math_captcha')


@pytest.mark.asyncio
async def test_adbtc_is_logged_in_true(mock_settings, mock_page, mock_solver):
    """Test is_logged_in returns True when on surf page"""
    mock_page.url = "https://adbtc.top/surf/browse"
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.is_logged_in()
    
    assert result is True


@pytest.mark.asyncio
async def test_adbtc_is_logged_in_balance_element(mock_settings, mock_page, mock_solver):
    """Test is_logged_in returns True when balance element is present"""
    balance_locator = MagicMock()
    balance_locator.count = AsyncMock(return_value=1)
    mock_page.locator.return_value = balance_locator
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.is_logged_in()
    
    assert result is True


@pytest.mark.asyncio
async def test_adbtc_login_no_credentials(mock_settings, mock_page, mock_solver):
    """Test login fails when no credentials are provided"""
    mock_settings.get_account.return_value = None
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_adbtc_login_already_logged_in(mock_settings, mock_page, mock_solver):
    """Test login when already logged in"""
    mock_page.url = "https://adbtc.top/surf/browse"
    
    # Mock is_logged_in to return True
    balance_locator = MagicMock()
    balance_locator.count = AsyncMock(return_value=1)
    mock_page.locator.return_value = balance_locator
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    
    result = await bot.login()
    
    assert result is True


@pytest.mark.asyncio
async def test_adbtc_login_success(mock_settings, mock_page, mock_solver):
    """Test successful login - after form submit, is_logged_in returns True"""
    mock_page.url = "https://adbtc.top/index/enter"
    mock_page.content.return_value = "<html><body>Login page</body></html>"
    mock_page.title.return_value = "AdBTC"

    # Track how many times locator is called to make is_logged_in work after submit
    call_count = {"balance": 0}

    # Setup mock locators for login flow
    def locator_side_effect(selector):
        locator = MagicMock()
        locator.count = AsyncMock(return_value=0)
        locator.is_visible = AsyncMock(return_value=False)
        locator.select_option = AsyncMock()
        locator.first = MagicMock()
        locator.first.click = AsyncMock()

        # Make is_logged_in return True after login form submission
        if ".balance-value" in selector or ".nomargbot" in selector:
            call_count["balance"] += 1
            if call_count["balance"] <= 1:
                # First call (initial check): not logged in
                locator.count = AsyncMock(return_value=0)
            else:
                # Second call (post-submit verification): logged in
                locator.count = AsyncMock(return_value=1)

        # Submit button should be found
        if 'type="submit"' in selector or "Login" in selector:
            locator.count = AsyncMock(return_value=1)

        # email/password fields should be found
        if 'name="email"' in selector or 'name="password"' in selector:
            locator.count = AsyncMock(return_value=1)

        return locator

    mock_page.locator.side_effect = locator_side_effect

    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.solve_math_captcha = AsyncMock()
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()

    result = await bot.login()

    assert result is True
    bot.human_type.assert_called()


@pytest.mark.asyncio
async def test_adbtc_login_proxy_detected(mock_settings, mock_page, mock_solver):
    """Test login fails when proxy is detected"""
    mock_page.url = "https://adbtc.top/index/enter"
    mock_page.content.return_value = "<html><body>Proxy detected - login blocked</body></html>"
    
    def locator_side_effect(selector):
        locator = MagicMock()
        locator.count = AsyncMock(return_value=0)
        locator.is_visible = AsyncMock(return_value=False)
        locator.select_option = AsyncMock()
        locator.first = MagicMock()
        locator.first.click = AsyncMock()
        return locator
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.solve_math_captcha = AsyncMock()
    bot.strip_email_alias = MagicMock(return_value="test@example.com")
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_adbtc_login_exception(mock_settings, mock_page, mock_solver):
    """Test login handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_adbtc_claim_success(mock_settings, mock_page, mock_solver):
    """Test successful claim"""
    balance_locator = MagicMock()
    balance_locator.count = AsyncMock(return_value=1)
    balance_locator.first.is_visible = AsyncMock(return_value=True)
    balance_locator.first.text_content = AsyncMock(return_value="0.0001 BTC")
    
    mock_page.locator.return_value = balance_locator
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.get_balance = AsyncMock(return_value="0.0001")
    bot.get_timer = AsyncMock(return_value=0)
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Ready for Surf Ads"
    assert result.balance == "0.0001"


@pytest.mark.asyncio
async def test_adbtc_claim_with_timer(mock_settings, mock_page, mock_solver):
    """Test claim when timer is active"""
    def locator_side_effect(selector):
        locator = MagicMock()
        if "#claim_timer" in selector:
            locator.count = AsyncMock(return_value=1)
            locator.first.is_visible = AsyncMock(return_value=True)
        else:
            locator.count = AsyncMock(return_value=0)
        return locator
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.get_balance = AsyncMock(return_value="0.0001")
    bot.get_timer = AsyncMock(return_value=15.5)
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Timer Active"
    assert result.next_claim_minutes == 15.5


@pytest.mark.asyncio
async def test_adbtc_claim_exception(mock_settings, mock_page, mock_solver):
    """Test claim handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.claim()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_adbtc_view_ptc_ads_no_ads(mock_settings, mock_page, mock_solver):
    """Test viewing PTC ads when no ads are available"""
    open_btn_locator = MagicMock()
    open_btn_locator.count = AsyncMock(return_value=0)  # No ads
    
    captcha_locator = MagicMock()
    captcha_locator.count = AsyncMock(return_value=0)
    
    start_btn_locator = MagicMock()
    start_btn_locator.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "Open" in selector:
            return open_btn_locator
        elif "captcha" in selector.lower() or "hcaptcha" in selector.lower():
            return captcha_locator
        elif "Click to start" in selector:
            return start_btn_locator
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    # This should complete without errors
    await bot.view_ptc_ads()
    
    # Verify method completed
    assert True


@pytest.mark.asyncio
async def test_adbtc_withdraw_success(mock_settings, mock_page, mock_solver):
    """Test successful withdrawal"""
    # Setup faucetpay button
    faucetpay_btn = MagicMock()
    faucetpay_btn.count = AsyncMock(return_value=1)
    faucetpay_btn.first = MagicMock()
    
    withdraw_confirm = MagicMock()
    withdraw_confirm.count = AsyncMock(return_value=1)
    
    pass_field = MagicMock()
    pass_field.count = AsyncMock(return_value=0)
    pass_field.is_visible = AsyncMock(return_value=False)
    
    mock_page.content = AsyncMock(return_value="<html><body>Withdrawal success</body></html>")
    mock_page.wait_for_load_state = AsyncMock()
    
    def locator_side_effect(selector):
        if "FaucetPay" in selector:
            return faucetpay_btn
        elif "Withdraw" in selector:
            return withdraw_confirm
        elif "password" in selector:
            return pass_field
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.get_credentials = MagicMock(return_value={"password": "test_password"})
    bot.human_type = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "Withdrawn"


@pytest.mark.asyncio
async def test_adbtc_withdraw_no_method(mock_settings, mock_page, mock_solver):
    """Test withdrawal when no method is available"""
    faucetpay_btn = MagicMock()
    faucetpay_btn.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = faucetpay_btn
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.idle_mouse = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is False
    assert result.status == "No Withdrawal Method Available"


@pytest.mark.asyncio
async def test_adbtc_withdraw_exception(mock_settings, mock_page, mock_solver):
    """Test withdrawal handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.withdraw()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_adbtc_solve_math_captcha_addition(mock_settings, mock_page, mock_solver):
    """Test solving math captcha with addition"""
    mock_page.content.return_value = "<html><body>Solve: 5 + 3 = </body></html>"
    
    answer_field = MagicMock()
    answer_field.count = AsyncMock(return_value=1)
    mock_page.locator.return_value = answer_field
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.human_type = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.solve_math_captcha()
    
    assert result is True
    bot.human_type.assert_called_once()
    # Verify it was called with '8'
    call_args = bot.human_type.call_args[0]
    assert call_args[1] == '8'


@pytest.mark.asyncio
async def test_adbtc_solve_math_captcha_subtraction(mock_settings, mock_page, mock_solver):
    """Test solving math captcha with subtraction"""
    mock_page.content.return_value = "<html><body>Solve: 10 - 4 = </body></html>"
    
    answer_field = MagicMock()
    answer_field.count = AsyncMock(return_value=1)
    mock_page.locator.return_value = answer_field
    
    bot = AdBTCBot(mock_settings, mock_page)
    bot.human_type = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.solve_math_captcha()
    
    assert result is True
    bot.human_type.assert_called_once()
    # Verify it was called with '6'
    call_args = bot.human_type.call_args[0]
    assert call_args[1] == '6'


@pytest.mark.asyncio
async def test_adbtc_solve_math_captcha_no_pattern(mock_settings, mock_page, mock_solver):
    """Test math captcha when no pattern is found"""
    mock_page.content.return_value = "<html><body>No math captcha here</body></html>"
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.solve_math_captcha()
    
    assert result is False


@pytest.mark.asyncio
async def test_adbtc_solve_math_captcha_exception(mock_settings, mock_page, mock_solver):
    """Test math captcha handles exceptions"""
    mock_page.content.side_effect = Exception("Error")
    
    bot = AdBTCBot(mock_settings, mock_page)
    result = await bot.solve_math_captcha()
    
    assert result is False


@pytest.mark.asyncio
async def test_adbtc_get_jobs(mock_settings, mock_page, mock_solver):
    """Test get_jobs returns correct job structure"""
    bot = AdBTCBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 3
    assert jobs[0].name == "AdBTC Claim"
    assert jobs[1].name == "AdBTC Withdraw"
    assert jobs[2].name == "AdBTC Surf"
    assert jobs[0].job_type == "claim_wrapper"
    assert jobs[1].job_type == "withdraw_wrapper"
    assert jobs[2].job_type == "ptc_wrapper"
    assert jobs[0].priority == 1
    assert jobs[1].priority == 5
    assert jobs[2].priority == 2
