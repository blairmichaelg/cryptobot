# pylint: disable=protected-access
"""
Comprehensive tests for TronPick bot functionality.

Tests cover:
- Login success and failure scenarios
- Balance extraction with various formats
- Timer parsing (HH:MM:SS, countdown, compound formats)
- Claim workflow with CAPTCHA solving
- Error handling and retry logic
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from faucets.tronpick import TronPickBot
from faucets.base import ClaimResult
from core.config import BotSettings


@pytest.fixture
def mock_settings():
    """Mock BotSettings with TronPick credentials."""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {
        "email": "test@example.com",
        "password": "testpassword123"
    }
    settings.wallet_addresses = {"TRX": {"address": "TRX_TEST_ADDRESS_123"}}
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_api_key"
    settings.use_faucetpay = True
    settings.faucetpay_trx_address = "FP_TRX_ADDRESS"
    return settings


@pytest.fixture
def mock_solver():
    """Mock CAPTCHA solver."""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)
        solver_instance.set_faucet_name = MagicMock()
        solver_instance.set_proxy = MagicMock()
        yield solver_instance


@pytest.fixture
def mock_page():
    """Mock Playwright Page with common TronPick elements."""
    page = AsyncMock()
    page.title.return_value = "TronPick"
    page.viewport_size = {"width": 1920, "height": 1080}
    
    # Setup locator chain
    page.locator = MagicMock()
    page.locator.return_value.count = AsyncMock(return_value=0)
    page.locator.return_value.is_visible = AsyncMock(return_value=False)
    page.locator.return_value.text_content = AsyncMock(return_value="")
    page.locator.return_value.get_attribute = AsyncMock(return_value="")
    page.locator.return_value.first = MagicMock()
    page.locator.return_value.first.is_visible = AsyncMock(return_value=False)
    page.locator.return_value.first.text_content = AsyncMock(return_value="")
    page.locator.return_value.fill = AsyncMock()
    page.locator.return_value.click = AsyncMock()
    page.locator.return_value.scroll_into_view_if_needed = AsyncMock()
    page.locator.return_value.bounding_box = AsyncMock(return_value=None)
    
    # Mock navigation
    page.goto = AsyncMock(return_value=MagicMock(ok=True))
    page.wait_for_load_state = AsyncMock()
    page.content = AsyncMock(return_value="<html></html>")
    
    # Mock mouse and keyboard
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    
    page.evaluate = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    
    return page


@pytest.mark.asyncio
async def test_tronpick_init(mock_settings, mock_page, mock_solver):
    """Test TronPickBot initialization."""
    bot = TronPickBot(mock_settings, mock_page)
    
    assert bot.faucet_name == "TronPick"
    assert bot.base_url == "https://tronpick.io"
    assert bot.min_claim_amount == 0.001
    assert bot.claim_interval_minutes == 60


@pytest.mark.asyncio
async def test_tronpick_login_success(mock_settings, mock_page, mock_solver):
    """Test successful login flow."""
    # Mock email and password fields
    email_field = AsyncMock()
    email_field.count = AsyncMock(return_value=1)
    email_field.fill = AsyncMock()
    
    pass_field = AsyncMock()
    pass_field.count = AsyncMock(return_value=1)
    pass_field.fill = AsyncMock()
    
    login_btn = AsyncMock()
    login_btn.is_visible = AsyncMock(return_value=True)
    
    # Mock logout link (indicates logged in state)
    # is_logged_in is called once after login attempt
    logout_link = AsyncMock()
    logout_link.is_visible = AsyncMock(return_value=True)  # Logged in after login
    
    def locator_side_effect(selector):
        if "email" in selector:
            return email_field
        elif "password" in selector:
            return pass_field
        elif "Logout" in selector or "logout" in selector:
            return logout_link
        elif "Login" in selector or "btn" in selector:
            return login_btn
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot._navigate_with_retry = AsyncMock(return_value=True)
    
    result = await bot.login()
    
    assert result is True
    bot._navigate_with_retry.assert_called()
    email_field.fill.assert_called_with("test@example.com")
    pass_field.fill.assert_called_with("testpassword123")
    bot.human_like_click.assert_called()


@pytest.mark.asyncio
async def test_tronpick_login_failure(mock_settings, mock_page, mock_solver):
    """Test login failure (credentials rejected)."""
    email_field = AsyncMock()
    email_field.count = AsyncMock(return_value=1)
    email_field.fill = AsyncMock()
    
    pass_field = AsyncMock()
    pass_field.count = AsyncMock(return_value=1)
    pass_field.fill = AsyncMock()
    
    login_btn = AsyncMock()
    login_btn.is_visible = AsyncMock(return_value=True)
    
    # Logout link never becomes visible
    logout_link = AsyncMock()
    logout_link.is_visible = AsyncMock(return_value=False)
    
    def locator_side_effect(selector):
        if "email" in selector:
            return email_field
        elif "password" in selector:
            return pass_field
        elif "Logout" in selector or "logout" in selector:
            return logout_link
        elif "Login" in selector or "btn" in selector:
            return login_btn
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.human_like_click = AsyncMock()
    
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_get_balance_standard_format(mock_settings, mock_page, mock_solver):
    """Test balance extraction with standard format."""
    balance_element = AsyncMock()
    balance_element.count = AsyncMock(return_value=1)
    balance_element.first = MagicMock()
    balance_element.first.is_visible = AsyncMock(return_value=True)
    balance_element.first.text_content = AsyncMock(return_value="Balance: 0.125 TRX")
    
    def locator_side_effect(selector):
        if "balance" in selector.lower():
            return balance_element
        elem = AsyncMock()
        elem.count = AsyncMock(return_value=0)
        return elem
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    balance = await bot.get_balance()
    
    assert balance == "0.125"


@pytest.mark.asyncio
async def test_get_balance_with_commas(mock_settings, mock_page, mock_solver):
    """Test balance extraction with comma separators."""
    balance_element = AsyncMock()
    balance_element.count = AsyncMock(return_value=1)
    balance_element.first = MagicMock()
    balance_element.first.is_visible = AsyncMock(return_value=True)
    balance_element.first.text_content = AsyncMock(return_value="1,234.567 TRX")
    
    def locator_side_effect(selector):
        if "balance" in selector.lower():
            return balance_element
        elem = AsyncMock()
        elem.count = AsyncMock(return_value=0)
        return elem
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    balance = await bot.get_balance()
    
    assert balance == "1234.567"


@pytest.mark.asyncio
async def test_get_balance_not_found(mock_settings, mock_page, mock_solver):
    """Test balance extraction when element not found."""
    no_element = AsyncMock()
    no_element.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = no_element
    
    bot = TronPickBot(mock_settings, mock_page)
    balance = await bot.get_balance()
    
    assert balance == "0"


@pytest.mark.asyncio
async def test_get_timer_hms_format(mock_settings, mock_page, mock_solver):
    """Test timer extraction with HH:MM:SS format."""
    timer_element = AsyncMock()
    timer_element.count = AsyncMock(return_value=1)
    timer_element.first.text_content = AsyncMock(return_value="01:30:45")
    
    def locator_side_effect(selector):
        if "time" in selector.lower():
            return timer_element
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    minutes = await bot.get_timer()
    
    # 1h 30m 45s = 90.75 minutes
    assert 90.7 < minutes < 90.8


@pytest.mark.asyncio
async def test_get_timer_ms_format(mock_settings, mock_page, mock_solver):
    """Test timer extraction with MM:SS format."""
    timer_element = AsyncMock()
    timer_element.count = AsyncMock(return_value=1)
    timer_element.first.text_content = AsyncMock(return_value="45:30")
    
    def locator_side_effect(selector):
        if "time" in selector.lower():
            return timer_element
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    minutes = await bot.get_timer()
    
    # 45m 30s = 45.5 minutes
    assert 45.4 < minutes < 45.6


@pytest.mark.asyncio
async def test_get_timer_compound_format(mock_settings, mock_page, mock_solver):
    """Test timer extraction with compound format (1h 30m)."""
    timer_element = AsyncMock()
    timer_element.count = AsyncMock(return_value=1)
    timer_element.first.text_content = AsyncMock(return_value="1h 30m")
    
    def locator_side_effect(selector):
        if "time" in selector.lower():
            return timer_element
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    minutes = await bot.get_timer()
    
    assert minutes == 90.0


@pytest.mark.asyncio
async def test_get_timer_no_timer(mock_settings, mock_page, mock_solver):
    """Test timer extraction when no timer present (ready to claim)."""
    no_element = AsyncMock()
    no_element.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = no_element
    
    bot = TronPickBot(mock_settings, mock_page)
    minutes = await bot.get_timer()
    
    assert minutes == 0.0


@pytest.mark.asyncio
async def test_claim_success(mock_settings, mock_page, mock_solver):
    """Test successful claim with CAPTCHA solving."""
    # Mock balance
    balance_element = AsyncMock()
    balance_element.count = AsyncMock(return_value=1)
    balance_element.first.is_visible = AsyncMock(return_value=True)
    balance_element.first.text_content = AsyncMock(return_value="0.125 TRX")
    
    # Mock timer (no cooldown)
    timer_element = AsyncMock()
    timer_element.count = AsyncMock(return_value=0)
    
    # Mock CAPTCHA present
    captcha_element = AsyncMock()
    captcha_element.count = AsyncMock(return_value=1)
    
    # Mock claim button
    claim_btn = AsyncMock()
    claim_btn.is_visible = AsyncMock(return_value=True)
    claim_btn.scroll_into_view_if_needed = AsyncMock()
    claim_btn.bounding_box = AsyncMock(return_value={
        'x': 100, 'y': 200, 'width': 150, 'height': 50
    })
    
    # Mock success message
    success_msg = AsyncMock()
    success_msg.count = AsyncMock(return_value=1)
    success_msg.first.text_content = AsyncMock(return_value="You won 0.015 TRX!")
    
    def locator_side_effect(selector):
        if "balance" in selector.lower():
            return balance_element
        elif "time" in selector.lower():
            return timer_element
        elif "captcha" in selector.lower():
            return captcha_element
        elif "claim" in selector.lower() or "btn" in selector.lower() or "Roll" in selector:
            return claim_btn
        elif "success" in selector.lower():
            return success_msg
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.human_like_click = AsyncMock()
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Claimed"
    assert "0.015" in result.amount
    assert result.next_claim_minutes == 60
    bot.solver.solve_captcha.assert_called()


@pytest.mark.asyncio
async def test_claim_on_cooldown(mock_settings, mock_page, mock_solver):
    """Test claim when faucet is on cooldown."""
    # Mock balance
    balance_element = AsyncMock()
    balance_element.count = AsyncMock(return_value=1)
    balance_element.first = MagicMock()
    balance_element.first.is_visible = AsyncMock(return_value=True)
    balance_element.first.text_content = AsyncMock(return_value="0.100 TRX")
    
    # Mock timer (45 minutes remaining)
    timer_element = AsyncMock()
    timer_element.count = AsyncMock(return_value=1)
    timer_element.first = MagicMock()
    timer_element.first.text_content = AsyncMock(return_value="45:00")
    
    def locator_side_effect(selector):
        if "balance" in selector.lower():
            return balance_element
        elif "time" in selector.lower():
            return timer_element
        elem = AsyncMock()
        elem.count = AsyncMock(return_value=0)
        return elem
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Cooldown"
    assert 44.9 < result.next_claim_minutes < 45.1
    assert result.balance == "0.100"


@pytest.mark.asyncio
async def test_claim_captcha_failure(mock_settings, mock_page, mock_solver):
    """Test claim when CAPTCHA solving fails."""
    # Mock balance
    balance_element = AsyncMock()
    balance_element.count = AsyncMock(return_value=1)
    balance_element.first.is_visible = AsyncMock(return_value=True)
    balance_element.first.text_content = AsyncMock(return_value="0.080 TRX")
    
    # Mock timer (no cooldown)
    timer_element = AsyncMock()
    timer_element.count = AsyncMock(return_value=0)
    
    # Mock CAPTCHA present
    captcha_element = AsyncMock()
    captcha_element.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "balance" in selector.lower():
            return balance_element
        elif "time" in selector.lower():
            return timer_element
        elif "captcha" in selector.lower():
            return captcha_element
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    # Make CAPTCHA solving fail
    mock_solver.solve_captcha = AsyncMock(return_value=False)
    
    bot = TronPickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    bot.solver = mock_solver
    
    result = await bot.claim()
    
    assert result.success is False
    assert result.status == "CAPTCHA Failed"
    assert result.next_claim_minutes == 10


@pytest.mark.asyncio
async def test_claim_navigation_failure(mock_settings, mock_page, mock_solver):
    """Test claim when navigation fails."""
    bot = TronPickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=False)
    
    # Mock balance for error reporting
    balance_element = AsyncMock()
    balance_element.count = AsyncMock(return_value=1)
    balance_element.first.is_visible = AsyncMock(return_value=True)
    balance_element.first.text_content = AsyncMock(return_value="0.050 TRX")
    
    def locator_side_effect(selector):
        if "balance" in selector.lower():
            return balance_element
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    result = await bot.claim()
    
    assert result.success is False
    assert result.status == "Navigation Failed"
    assert result.next_claim_minutes == 15


@pytest.mark.asyncio
async def test_claim_button_not_found(mock_settings, mock_page, mock_solver):
    """Test claim when claim button is not visible."""
    # Mock balance
    balance_element = AsyncMock()
    balance_element.count = AsyncMock(return_value=1)
    balance_element.first = MagicMock()
    balance_element.first.is_visible = AsyncMock(return_value=True)
    balance_element.first.text_content = AsyncMock(return_value="0.090 TRX")
    
    # Mock timer (no cooldown)
    timer_element = AsyncMock()
    timer_element.count = AsyncMock(return_value=0)
    
    # Mock CAPTCHA not present
    captcha_element = AsyncMock()
    captcha_element.count = AsyncMock(return_value=0)
    
    # Mock claim button not visible
    claim_btn = AsyncMock()
    claim_btn.is_visible = AsyncMock(return_value=False)
    
    def locator_side_effect(selector):
        if "balance" in selector.lower():
            return balance_element
        elif "time" in selector.lower():
            return timer_element
        elif "captcha" in selector.lower():
            return captcha_element
        elif "claim" in selector.lower() or "btn" in selector.lower():
            return claim_btn
        elem = AsyncMock()
        elem.count = AsyncMock(return_value=0)
        return elem
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = TronPickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.claim()
    
    assert result.success is False
    assert result.status == "Button Not Found"
    assert result.next_claim_minutes == 60
