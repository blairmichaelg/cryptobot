import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.dutchy import DutchyBot
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
    page.url = "https://autofaucet.dutchycorp.space"
    page.title.return_value = "DutchyCorp"
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
    locator_mock.check = AsyncMock()
    page.locator.return_value = locator_mock
    
    page.query_selector = AsyncMock(return_value=None)
    page.goto = AsyncMock()
    page.fill = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_url = AsyncMock()
    
    return page


@pytest.mark.asyncio
async def test_dutchy_structure(mock_settings, mock_page, mock_solver):
    """Test DutchyBot structure and initialization"""
    print("--- Testing DutchyBot Structure ---")
    
    # Instantiate
    try:
        bot = DutchyBot(mock_settings, mock_page)
        print("✅ Instantiation successful")
    except Exception as e:
        pytest.fail(f"❌ Instantiation failed: {e}")

    # Check Methods
    assert hasattr(bot, 'login'), "❌ Missing required method: login"
    assert hasattr(bot, 'claim'), "❌ Missing required method: claim"
    print("✅ Methods 'login' and 'claim' exist")

    # Check Config
    assert bot.faucet_name == "DutchyCorp", f"❌ Config mismatch: {bot.faucet_name}"
    assert "dutchycorp.space" in bot.base_url, f"❌ Config mismatch: {bot.base_url}"
    print(f"✅ Config looks correct: {bot.base_url}")


@pytest.mark.asyncio
async def test_dutchy_login_no_credentials(mock_settings, mock_page, mock_solver):
    """Test login fails when no credentials are provided"""
    mock_settings.get_account.return_value = None
    
    bot = DutchyBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_dutchy_login_proxy_detected(mock_settings, mock_page, mock_solver):
    """Test login fails when proxy is detected"""
    mock_page.content.return_value = "<html><body>Proxy Detected</body></html>"
    
    bot = DutchyBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_dutchy_login_already_logged_in(mock_settings, mock_page, mock_solver):
    """Test login when already logged in"""
    logout_element = MagicMock()
    mock_page.query_selector.return_value = logout_element
    
    bot = DutchyBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is True


@pytest.mark.asyncio
async def test_dutchy_login_success(mock_settings, mock_page, mock_solver):
    """Test successful login"""
    mock_page.query_selector.return_value = None
    mock_page.content.return_value = "<html><body>Login page</body></html>"
    
    remember_checkbox = MagicMock()
    remember_checkbox.count = AsyncMock(return_value=1)
    remember_checkbox.check = AsyncMock()
    
    submit_btn = MagicMock()
    submit_btn.click = AsyncMock()
    
    def locator_side_effect(selector):
        if "remember_me" in selector:
            return remember_checkbox
        elif 'button[type="submit"]' in selector:
            return submit_btn
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = DutchyBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    
    result = await bot.login()
    
    assert result is True
    mock_page.fill.assert_called()
    mock_page.wait_for_url.assert_called()


@pytest.mark.asyncio
async def test_dutchy_login_exception(mock_settings, mock_page, mock_solver):
    """Test login handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = DutchyBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_dutchy_claim_success(mock_settings, mock_page, mock_solver):
    """Test successful claim"""
    bot = DutchyBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot._do_roll = AsyncMock()
    bot.claim_shortlinks = AsyncMock()
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Dutchy cycle complete"
    assert bot._do_roll.call_count == 2


@pytest.mark.asyncio
async def test_dutchy_claim_exception(mock_settings, mock_page, mock_solver):
    """Test claim handles exceptions"""
    bot = DutchyBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(side_effect=Exception("Error"))
    
    result = await bot.claim()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_dutchy_do_roll_cooldown(mock_settings, mock_page, mock_solver):
    """Test _do_roll when on cooldown"""
    bot = DutchyBot(mock_settings, mock_page)
    bot.close_popups = AsyncMock()
    bot.get_timer = AsyncMock(return_value=15)
    
    await bot._do_roll("roll.php", "Test Roll")
    
    # Should return early without clicking roll button
    bot.close_popups.assert_called()


@pytest.mark.asyncio
async def test_dutchy_do_roll_success(mock_settings, mock_page, mock_solver):
    """Test successful _do_roll"""
    unlock_btn = MagicMock()
    unlock_btn.count = AsyncMock(return_value=1)
    unlock_btn.is_visible = AsyncMock(return_value=True)
    
    boost_btn = MagicMock()
    boost_btn.count = AsyncMock(return_value=1)
    boost_btn.is_visible = AsyncMock(return_value=True)
    
    roll_btn = MagicMock()
    roll_btn.count = AsyncMock(return_value=1)
    roll_btn.first = MagicMock()
    
    success_msg = MagicMock()
    success_msg.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "unlockbutton" in selector:
            return unlock_btn
        elif "claim_boosted" in selector or "Boost" in selector:
            return boost_btn
        elif "Roll" in selector or "roll_button" in selector:
            return roll_btn
        elif "alert-success" in selector or "toast-success" in selector:
            return success_msg
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = DutchyBot(mock_settings, mock_page)
    bot.close_popups = AsyncMock()
    bot.get_timer = AsyncMock(return_value=0)
    bot.handle_cloudflare = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    await bot._do_roll("roll.php", "Test Roll")
    
    assert bot.human_like_click.called


@pytest.mark.asyncio
async def test_dutchy_claim_shortlinks(mock_settings, mock_page, mock_solver):
    """Test claiming shortlinks"""
    with patch("faucets.dutchy.ShortlinkSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve = AsyncMock(return_value=True)
        
        links_locator = MagicMock()
        links_locator.count = AsyncMock(side_effect=[2, 0])
        links_locator.nth = MagicMock(return_value=links_locator)
        links_locator.click = AsyncMock()
        
        mock_page.locator.return_value = links_locator
        
        bot = DutchyBot(mock_settings, mock_page)
        
        await bot.claim_shortlinks()
        
        # Verify method completed
        assert True


@pytest.mark.asyncio
async def test_dutchy_withdraw_success(mock_settings, mock_page, mock_solver):
    """Test successful withdrawal"""
    withdraw_btns = MagicMock()
    withdraw_btns.count = AsyncMock(return_value=2)
    withdraw_btns.nth = MagicMock(return_value=withdraw_btns)
    
    method_select = MagicMock()
    method_select.count = AsyncMock(return_value=1)
    method_select.select_option = AsyncMock()
    
    submit_btn = MagicMock()
    submit_btn.last = MagicMock()
    
    success_msg = MagicMock()
    success_msg.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "Withdraw" in selector and "button" in selector:
            return withdraw_btns
        elif "method" in selector or "withdrawal_method" in selector:
            return method_select
        elif "withdraw_button" in selector:
            return submit_btn
        elif "alert-success" in selector or "toast-success" in selector:
            return success_msg
        elif "tr:has" in selector:
            return MagicMock()
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = DutchyBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "Withdrawn"


@pytest.mark.asyncio
async def test_dutchy_withdraw_no_balance(mock_settings, mock_page, mock_solver):
    """Test withdrawal when no balance is available"""
    withdraw_btns = MagicMock()
    withdraw_btns.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = withdraw_btns
    
    bot = DutchyBot(mock_settings, mock_page)
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "No Balance"


@pytest.mark.asyncio
async def test_dutchy_withdraw_exception(mock_settings, mock_page, mock_solver):
    """Test withdrawal handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = DutchyBot(mock_settings, mock_page)
    result = await bot.withdraw()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_dutchy_get_jobs(mock_settings, mock_page, mock_solver):
    """Test get_jobs returns correct job structure"""
    bot = DutchyBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 2
    assert jobs[0].name == "DutchyCorp Claim"
    assert jobs[1].name == "DutchyCorp Withdraw"
