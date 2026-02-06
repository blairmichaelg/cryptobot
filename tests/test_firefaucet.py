import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.firefaucet import FireFaucetBot
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
    page.url = "https://firefaucet.win"
    page.title.return_value = "FireFaucet"
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
    page.evaluate = AsyncMock()
    page.screenshot = AsyncMock()
    
    return page


@pytest.mark.asyncio
async def test_firefaucet_initialization(mock_settings, mock_page, mock_solver):
    """Test FireFaucetBot initialization"""
    bot = FireFaucetBot(mock_settings, mock_page)
    
    assert bot.faucet_name == "FireFaucet"
    assert bot.base_url == "https://firefaucet.win"
    assert hasattr(bot, 'login')
    assert hasattr(bot, 'claim')


@pytest.mark.asyncio
async def test_firefaucet_login_no_credentials(mock_settings, mock_page, mock_solver):
    """Test login fails when no credentials are provided"""
    mock_settings.get_account.return_value = None
    
    bot = FireFaucetBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_firefaucet_login_success_dashboard_url(mock_settings, mock_page, mock_solver):
    """Test successful login with dashboard URL detection"""
    # Set URL to dashboard immediately
    mock_page.url = "https://firefaucet.win/dashboard"
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.login()
    
    assert result is True


@pytest.mark.asyncio
async def test_firefaucet_login_success_dashboard_elements(mock_settings, mock_page, mock_solver):
    """Test successful login with dashboard elements detection"""
    mock_page.url = "https://firefaucet.win/login"
    
    dashboard_locator = MagicMock()
    dashboard_locator.count = AsyncMock(return_value=1)
    dashboard_locator.is_visible = AsyncMock(return_value=True)
    dashboard_locator.is_disabled = AsyncMock(return_value=False)
    dashboard_locator.scroll_into_view_if_needed = AsyncMock()
    dashboard_locator.bounding_box = AsyncMock(return_value={'x': 0, 'y': 0, 'width': 100, 'height': 50})
    dashboard_locator.click = AsyncMock()
    dashboard_locator.first = MagicMock()
    dashboard_locator.first.text_content = AsyncMock(return_value="")
    dashboard_locator.first.is_visible = AsyncMock(return_value=True)
    
    mock_page.locator.return_value = dashboard_locator
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.login()
    
    assert result is True


@pytest.mark.asyncio
async def test_firefaucet_login_success_logout_link(mock_settings, mock_page, mock_solver):
    """Test successful login with logout link detection"""
    mock_page.url = "https://firefaucet.win/login"
    
    logout_locator = MagicMock()
    logout_locator.count = AsyncMock(return_value=1)
    logout_locator.is_visible = AsyncMock(return_value=True)
    logout_locator.is_disabled = AsyncMock(return_value=False)
    logout_locator.scroll_into_view_if_needed = AsyncMock()
    logout_locator.bounding_box = AsyncMock(return_value={'x': 0, 'y': 0, 'width': 100, 'height': 50})
    logout_locator.click = AsyncMock()
    logout_locator.first = MagicMock()
    logout_locator.first.text_content = AsyncMock(return_value="")
    logout_locator.first.is_visible = AsyncMock(return_value=True)
    
    mock_page.locator.return_value = logout_locator
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.login()
    
    assert result is True


@pytest.mark.asyncio
async def test_firefaucet_login_error_message(mock_settings, mock_page, mock_solver):
    """Test login fails when error message is shown"""
    mock_page.url = "https://firefaucet.win/login"
    
    error_locator = MagicMock()
    error_locator.count = AsyncMock(return_value=1)
    error_locator.first = MagicMock()
    error_locator.first.text_content = AsyncMock(return_value="Invalid credentials")
    
    success_locator = MagicMock()
    success_locator.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "alert-danger" in selector or "error-message" in selector or "toast-error" in selector:
            return error_locator
        else:
            return success_locator
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_firefaucet_login_timeout(mock_settings, mock_page, mock_solver):
    """Test login timeout"""
    mock_page.url = "https://firefaucet.win/login"
    
    no_elements_locator = MagicMock()
    no_elements_locator.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = no_elements_locator
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.random_delay = AsyncMock()
    
    # Mock the time function to immediately timeout
    original_time = asyncio.get_event_loop().time
    
    async def mock_login_with_timeout():
        # Replace the time() calls with a mock that triggers timeout
        counter = [0]
        def time_mock():
            counter[0] += 1
            if counter[0] > 1:
                return 1000000  # Far in the future to trigger timeout
            return 0
        
        loop = asyncio.get_event_loop()
        loop.time = time_mock
        try:
            result = await bot.login()
            return result
        finally:
            loop.time = original_time
    
    result = await mock_login_with_timeout()
    
    assert result is False


@pytest.mark.asyncio
async def test_firefaucet_login_exception(mock_settings, mock_page, mock_solver):
    """Test login handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = FireFaucetBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_firefaucet_claim_success(mock_settings, mock_page, mock_solver):
    """Test successful claim"""
    # Fix async mocks needed by claim method
    mock_page.evaluate = AsyncMock(return_value="")
    mock_page.title = AsyncMock(return_value="FireFaucet")
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_page.wait_for_selector = AsyncMock()

    def create_default_locator():
        loc = MagicMock()
        loc.count = AsyncMock(return_value=0)
        loc.is_visible = AsyncMock(return_value=False)
        loc.first = MagicMock()
        loc.first.is_visible = AsyncMock(return_value=False)
        loc.first.text_content = AsyncMock(return_value="")
        loc.first.click = AsyncMock()
        loc.first.get_attribute = AsyncMock(return_value=None)
        loc.first.is_enabled = AsyncMock(return_value=True)
        loc.all = AsyncMock(return_value=[])
        loc.nth = MagicMock(return_value=loc)
        return loc

    # Setup faucet button (found by selector iteration)
    faucet_btn = create_default_locator()
    faucet_btn.count = AsyncMock(return_value=1)
    faucet_btn.first.is_visible = AsyncMock(return_value=True)
    faucet_btn.first.text_content = AsyncMock(return_value="Get Reward")
    faucet_btn.first.is_enabled = AsyncMock(return_value=True)
    faucet_btn.first.get_attribute = AsyncMock(return_value=None)

    # Setup success message (needs is_visible on the locator itself for .nth(i).is_visible() check)
    success_msg = create_default_locator()
    success_msg.count = AsyncMock(return_value=1)
    success_msg.is_visible = AsyncMock(return_value=True)
    success_msg.text_content = AsyncMock(return_value="Claimed successfully!")
    success_msg.first.is_visible = AsyncMock(return_value=True)
    success_msg.first.text_content = AsyncMock(return_value="Claimed successfully!")

    def locator_side_effect(selector):
        if "#get_reward_button" in selector:
            return faucet_btn
        elif "success" in selector.lower() or "alert-success" in selector:
            return success_msg
        elif "Get reward" in selector or "Get Reward" in selector or "Claim" in selector:
            return faucet_btn
        return create_default_locator()

    mock_page.locator.side_effect = locator_side_effect

    bot = FireFaucetBot(mock_settings, mock_page)
    bot.detect_cloudflare_block = AsyncMock(return_value=False)
    bot.handle_cloudflare = AsyncMock()
    bot.get_balance = AsyncMock(return_value="100")
    bot.get_timer = AsyncMock(return_value=0)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.simulate_reading = AsyncMock()

    result = await bot.claim()

    assert result.success is True
    assert result.status == "Claimed"


@pytest.mark.asyncio
async def test_firefaucet_claim_timer_active(mock_settings, mock_page, mock_solver):
    """Test claim when timer is active"""
    unlock_btn = MagicMock()
    unlock_btn.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = unlock_btn
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot.get_timer = AsyncMock(return_value=15)
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Timer Active"
    assert result.next_claim_minutes == 15


@pytest.mark.asyncio
async def test_firefaucet_claim_exception(mock_settings, mock_page, mock_solver):
    """Test claim handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = FireFaucetBot(mock_settings, mock_page)
    result = await bot.claim()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_firefaucet_view_ptc_ads(mock_settings, mock_page, mock_solver):
    """Test viewing PTC ads"""
    # Setup ad button
    ad_button = MagicMock()
    ad_button.count = AsyncMock(side_effect=[1, 0])
    ad_button.first = MagicMock()
    ad_button.first.click = AsyncMock()
    
    # Setup captcha image
    captcha_img = MagicMock()
    captcha_img.count = AsyncMock(return_value=0)
    
    # Setup submit button
    submit_btn = MagicMock()
    submit_btn.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "div:nth-child(3) > a" in selector:
            return ad_button
        elif "#description > img" in selector:
            return captcha_img
        elif "#submit-button" in selector:
            return submit_btn
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    await bot.view_ptc_ads()
    
    # Verify method completed
    assert True


@pytest.mark.asyncio
async def test_firefaucet_withdraw_success(mock_settings, mock_page, mock_solver):
    """Test successful withdrawal"""
    # Setup coin cards
    coin_card = MagicMock()
    coin_card.count = AsyncMock(return_value=1)
    coin_card.first = MagicMock()
    coin_card.first.locator = MagicMock()
    
    coin_btn = MagicMock()
    coin_btn.click = AsyncMock()
    coin_card.first.locator.return_value = coin_btn
    
    # Setup processor select
    processor = MagicMock()
    processor.count = AsyncMock(return_value=1)
    processor.select_option = AsyncMock()
    
    # Setup submit button
    submit = MagicMock()
    submit.last = MagicMock()
    
    # Setup success message
    success = MagicMock()
    success.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if ".card:has(button:has-text('Withdraw'))" in selector:
            return coin_card
        elif "select[name='processor']" in selector:
            return processor
        elif "Withdraw" in selector and "last" in str(selector):
            return submit
        elif "alert-success" in selector or "toast-success" in selector:
            return success
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "Withdrawn"


@pytest.mark.asyncio
async def test_firefaucet_withdraw_no_balance(mock_settings, mock_page, mock_solver):
    """Test withdrawal when no balance is available"""
    coin_card = MagicMock()
    coin_card.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = coin_card
    
    bot = FireFaucetBot(mock_settings, mock_page)
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "No Balance"


@pytest.mark.asyncio
async def test_firefaucet_withdraw_exception(mock_settings, mock_page, mock_solver):
    """Test withdrawal handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = FireFaucetBot(mock_settings, mock_page)
    result = await bot.withdraw()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_firefaucet_daily_bonus_wrapper_success(mock_settings, mock_page, mock_solver):
    """Test daily bonus wrapper success"""
    unlock_btn = MagicMock()
    unlock_btn.count = AsyncMock(return_value=1)
    unlock_btn.is_visible = AsyncMock(return_value=True)
    
    turnstile_opt = MagicMock()
    turnstile_opt.count = AsyncMock(return_value=1)
    turnstile_opt.click = AsyncMock()
    
    claim_btn = MagicMock()
    claim_btn.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "button" in selector and "center" in selector and "a" in selector:
            return unlock_btn
        elif "select-turnstile" in selector:
            return turnstile_opt
        elif "form > button" in selector:
            return claim_btn
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.login_wrapper = AsyncMock(return_value=True)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.daily_bonus_wrapper(mock_page)
    
    assert result.success is True
    assert result.status == "Daily Bonus Claimed"


@pytest.mark.asyncio
async def test_firefaucet_daily_bonus_wrapper_login_failed(mock_settings, mock_page, mock_solver):
    """Test daily bonus wrapper when login fails"""
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.login_wrapper = AsyncMock(return_value=False)
    
    result = await bot.daily_bonus_wrapper(mock_page)
    
    assert result.success is False
    assert result.status == "Login Failed"


@pytest.mark.asyncio
async def test_firefaucet_daily_bonus_wrapper_exception(mock_settings, mock_page, mock_solver):
    """Test daily bonus wrapper handles exceptions"""
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.login_wrapper = AsyncMock(return_value=True)
    mock_page.goto.side_effect = Exception("Network error")
    
    result = await bot.daily_bonus_wrapper(mock_page)
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_firefaucet_shortlinks_wrapper_success(mock_settings, mock_page, mock_solver):
    """Test shortlinks wrapper success"""
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.login_wrapper = AsyncMock(return_value=True)
    bot.claim_shortlinks = AsyncMock()
    
    result = await bot.shortlinks_wrapper(mock_page)
    
    assert result.success is True
    assert result.status == "Shortlinks Processed"


@pytest.mark.asyncio
async def test_firefaucet_shortlinks_wrapper_login_failed(mock_settings, mock_page, mock_solver):
    """Test shortlinks wrapper when login fails"""
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.login_wrapper = AsyncMock(return_value=False)
    
    result = await bot.shortlinks_wrapper(mock_page)
    
    assert result.success is False
    assert result.status == "Login Failed"


@pytest.mark.asyncio
async def test_firefaucet_shortlinks_wrapper_exception(mock_settings, mock_page, mock_solver):
    """Test shortlinks wrapper handles exceptions"""
    bot = FireFaucetBot(mock_settings, mock_page)
    bot.login_wrapper = AsyncMock(return_value=True)
    bot.claim_shortlinks = AsyncMock(side_effect=Exception("Network error"))
    
    result = await bot.shortlinks_wrapper(mock_page)
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_firefaucet_claim_shortlinks(mock_settings, mock_page, mock_solver):
    """Test claiming shortlinks"""
    # Mock shortlink solver
    with patch("faucets.firefaucet.ShortlinkSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve = AsyncMock(return_value=True)
        
        links_locator = MagicMock()
        links_locator.count = AsyncMock(side_effect=[2, 0])
        links_locator.nth = MagicMock(return_value=links_locator)
        links_locator.click = AsyncMock()
        
        mock_page.locator.return_value = links_locator
        
        bot = FireFaucetBot(mock_settings, mock_page)
        
        await bot.claim_shortlinks()
        
        # Verify method completed
        assert True


@pytest.mark.asyncio
async def test_firefaucet_get_jobs(mock_settings, mock_page, mock_solver):
    """Test get_jobs returns correct job structure"""
    bot = FireFaucetBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 5
    assert jobs[0].name == "FireFaucet Claim"
    assert jobs[1].name == "FireFaucet Daily Bonus"
    assert jobs[2].name == "FireFaucet PTC"
    assert jobs[3].name == "FireFaucet Shortlinks"
    assert jobs[4].name == "FireFaucet Withdraw"
