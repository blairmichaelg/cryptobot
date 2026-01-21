"""
Comprehensive test suite for LitePick bot functionality.

Tests cover:
- Login success/failure scenarios
- Balance extraction with various formats
- Timer parsing (HH:MM:SS, countdown)
- Claim success and error scenarios
- CAPTCHA solving integration
- Network error handling
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from faucets.litepick import LitePickBot
from faucets.base import ClaimResult
from core.config import BotSettings
from core.extractor import DataExtractor


@pytest.fixture
def mock_settings():
    """Create mock settings with LitePick configuration."""
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {"email": "test@example.com", "password": "password123"}
    settings.wallet_addresses = {"LTC": {"address": "LTC_ADDR_123", "min_withdraw": 0.005}}
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test_key_123"
    settings.capsolver_api_key = None
    return settings


@pytest.fixture
def mock_solver():
    """Create mock CAPTCHA solver."""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)
        solver_instance.set_faucet_name = MagicMock()
        solver_instance.set_proxy = MagicMock()
        yield solver_instance


@pytest.fixture
def mock_page():
    """Create mock Playwright page with common behaviors."""
    page = AsyncMock()
    page.title.return_value = "LitePick - Free Litecoin Faucet"
    page.url = "https://litepick.io/faucet.php"
    
    # Setup default locator chain
    default_locator = AsyncMock()
    default_locator.count = AsyncMock(return_value=0)
    default_locator.is_visible = AsyncMock(return_value=False)
    default_locator.text_content = AsyncMock(return_value="")
    default_locator.get_attribute = AsyncMock(return_value="")
    default_locator.fill = AsyncMock()
    default_locator.first = MagicMock()
    default_locator.first.is_visible = AsyncMock(return_value=False)
    default_locator.first.text_content = AsyncMock(return_value="")
    
    page.locator = MagicMock(return_value=default_locator)
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.content = AsyncMock(return_value="<html><body></body></html>")
    
    return page


@pytest.mark.asyncio
async def test_litepick_login_success(mock_settings, mock_page, mock_solver):
    """Test successful login flow."""
    # Setup email field
    email_field = AsyncMock()
    email_field.is_visible = AsyncMock(return_value=True)
    email_field.fill = AsyncMock()
    
    # Setup password field
    pass_field = AsyncMock()
    pass_field.is_visible = AsyncMock(return_value=True)
    pass_field.fill = AsyncMock()
    
    # Setup login button
    login_btn = AsyncMock()
    login_btn.is_visible = AsyncMock(return_value=True)
    
    # Setup logout link (indicates logged in)
    logout_link = AsyncMock()
    logout_link.is_visible = AsyncMock(return_value=True)
    
    # Setup captcha locator (no captcha present)
    no_captcha = AsyncMock()
    no_captcha.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "email" in selector.lower():
            return email_field
        elif "password" in selector.lower():
            return pass_field
        elif "login" in selector.lower() or "btn" in selector.lower():
            return login_btn
        elif "logout" in selector.lower():
            return logout_link
        elif "captcha" in selector.lower():
            return no_captcha
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = LitePickBot(mock_settings, mock_page)
    bot.human_type = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock()
    bot._navigate_with_retry = AsyncMock(return_value=True)
    
    result = await bot.login()
    
    assert result is True
    bot._navigate_with_retry.assert_called_once()
    bot.human_type.assert_called()
    bot.human_like_click.assert_called_once()


@pytest.mark.asyncio
async def test_litepick_login_no_credentials(mock_settings, mock_page, mock_solver):
    """Test login failure when no credentials are configured."""
    mock_settings.get_account.return_value = None
    
    bot = LitePickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_litepick_login_captcha_failure(mock_settings, mock_page, mock_solver):
    """Test login failure when CAPTCHA solving fails."""
    mock_solver.solve_captcha = AsyncMock(return_value=False)
    
    # Setup fields
    email_field = AsyncMock()
    email_field.is_visible = AsyncMock(return_value=True)
    
    pass_field = AsyncMock()
    pass_field.is_visible = AsyncMock(return_value=True)
    
    # CAPTCHA present
    captcha = AsyncMock()
    captcha.count = AsyncMock(return_value=1)
    captcha.first = AsyncMock()
    captcha.first.is_visible = AsyncMock(return_value=True)
    
    def locator_side_effect(selector):
        if "email" in selector.lower():
            return email_field
        elif "password" in selector.lower():
            return pass_field
        elif "captcha" in selector.lower() or "h-captcha" in selector.lower():
            return captcha
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = LitePickBot(mock_settings, mock_page)
    bot.human_type = AsyncMock()
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_litepick_claim_success(mock_settings, mock_page, mock_solver):
    """Test successful claim with balance and amount extraction."""
    # Setup timer (not present - ready to claim)
    timer_locator = AsyncMock()
    timer_locator.count = AsyncMock(return_value=0)
    
    # Setup claim button
    claim_btn = AsyncMock()
    claim_btn.is_visible = AsyncMock(return_value=True)
    claim_btn.count = AsyncMock(return_value=1)
    
    # Setup success message
    success_msg = AsyncMock()
    success_msg.count = AsyncMock(return_value=1)
    success_msg.first = AsyncMock()
    success_msg.first.text_content = AsyncMock(return_value="Congratulations! You won 0.00015 LTC")
    
    # Setup balance
    balance_ele = AsyncMock()
    balance_ele.count = AsyncMock(return_value=1)
    balance_ele.first = AsyncMock()
    balance_ele.first.is_visible = AsyncMock(return_value=True)
    balance_ele.first.text_content = AsyncMock(return_value="Balance: 0.0025 LTC")
    
    def locator_side_effect(selector):
        if "#time" in selector or "timer" in selector.lower():
            return timer_locator
        elif "button" in selector or "claim" in selector.lower():
            return claim_btn
        elif "alert-success" in selector or "success" in selector.lower():
            return success_msg
        elif "balance" in selector.lower():
            return balance_ele
        elif "captcha" in selector.lower():
            return AsyncMock(count=AsyncMock(return_value=0))
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = LitePickBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.get_timer = AsyncMock(return_value=0.0)
    bot.get_balance = AsyncMock(return_value="0.0025")
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Claimed"
    assert result.next_claim_minutes == 60
    assert "0.00015" in result.amount
    assert result.balance == "0.0025"
    bot.human_like_click.assert_called_once()


@pytest.mark.asyncio
async def test_litepick_claim_on_cooldown(mock_settings, mock_page, mock_solver):
    """Test claim when timer is still active."""
    bot = LitePickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.get_timer = AsyncMock(return_value=45.5)  # 45.5 minutes remaining
    bot.get_balance = AsyncMock(return_value="0.0025")
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Cooldown"
    assert result.next_claim_minutes == 45.5
    assert result.balance == "0.0025"


@pytest.mark.asyncio
async def test_litepick_claim_captcha_required(mock_settings, mock_page, mock_solver):
    """Test claim with CAPTCHA solving."""
    # CAPTCHA present
    captcha = AsyncMock()
    captcha.count = AsyncMock(return_value=1)
    captcha.first = AsyncMock()
    captcha.first.is_visible = AsyncMock(return_value=True)
    
    # Claim button
    claim_btn = AsyncMock()
    claim_btn.is_visible = AsyncMock(return_value=True)
    
    # Success message
    success_msg = AsyncMock()
    success_msg.count = AsyncMock(return_value=1)
    success_msg.first = AsyncMock()
    success_msg.first.text_content = AsyncMock(return_value="Success! 0.0001 LTC")
    
    def locator_side_effect(selector):
        if "captcha" in selector.lower():
            return captcha
        elif "button" in selector or "claim" in selector.lower():
            return claim_btn
        elif "alert" in selector or "success" in selector.lower():
            return success_msg
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = LitePickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.get_timer = AsyncMock(return_value=0.0)
    bot.get_balance = AsyncMock(return_value="0.0015")
    
    result = await bot.claim()
    
    assert result.success is True
    mock_solver.solve_captcha.assert_called_once()


@pytest.mark.asyncio
async def test_litepick_claim_captcha_failure(mock_settings, mock_page, mock_solver):
    """Test claim failure when CAPTCHA can't be solved."""
    mock_solver.solve_captcha = AsyncMock(return_value=False)
    
    # CAPTCHA present
    captcha = AsyncMock()
    captcha.count = AsyncMock(return_value=1)
    captcha.first = AsyncMock()
    captcha.first.is_visible = AsyncMock(return_value=True)
    
    def locator_side_effect(selector):
        if "captcha" in selector.lower():
            return captcha
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = LitePickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.get_timer = AsyncMock(return_value=0.0)
    
    result = await bot.claim()
    
    assert result.success is False
    assert result.status == "CAPTCHA Failed"
    assert result.next_claim_minutes == 5


@pytest.mark.asyncio
async def test_litepick_claim_connection_failure(mock_settings, mock_page, mock_solver):
    """Test claim failure due to network issues."""
    bot = LitePickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=False)
    
    result = await bot.claim()
    
    assert result.success is False
    assert result.status == "Connection Failed"
    assert result.next_claim_minutes == 15


@pytest.mark.asyncio
async def test_litepick_balance_extraction():
    """Test balance extraction from various formats."""
    test_cases = [
        ("Balance: 0.00123 LTC", "0.00123"),
        ("0.00456", "0.00456"),
        ("Your balance: 1,234.56 LTC", "1234.56"),
        ("Balance 0", "0"),
        ("", "0"),
    ]
    
    for input_text, expected in test_cases:
        result = DataExtractor.extract_balance(input_text)
        assert result == expected, f"Failed for input: {input_text}"


@pytest.mark.asyncio
async def test_litepick_timer_parsing():
    """Test timer parsing from various formats."""
    test_cases = [
        ("59:59", 59.983333333333334),  # MM:SS
        ("01:30:00", 90.0),  # HH:MM:SS
        ("45 minutes", 45.0),
        ("1h 30m", 90.0),
        ("2h", 120.0),
        ("30", 30.0),  # Plain number
        ("", 0.0),  # Empty
    ]
    
    for input_text, expected in test_cases:
        result = DataExtractor.parse_timer_to_minutes(input_text)
        assert abs(result - expected) < 0.1, f"Failed for input: {input_text}, got {result}, expected {expected}"


@pytest.mark.asyncio
async def test_litepick_get_balance(mock_settings, mock_page, mock_solver):
    """Test balance retrieval with fallback selectors."""
    balance_ele = AsyncMock()
    balance_ele.count = AsyncMock(return_value=1)
    balance_ele.first = AsyncMock()
    balance_ele.first.is_visible = AsyncMock(return_value=True)
    balance_ele.first.text_content = AsyncMock(return_value="0.0045 LTC")
    
    mock_page.locator.return_value = balance_ele
    
    bot = LitePickBot(mock_settings, mock_page)
    
    result = await bot.get_balance()
    
    assert result == "0.0045"


@pytest.mark.asyncio
async def test_litepick_claim_button_not_found(mock_settings, mock_page, mock_solver):
    """Test claim when button is not visible (already claimed)."""
    claim_btn = AsyncMock()
    claim_btn.is_visible = AsyncMock(return_value=False)
    
    # No captcha
    no_captcha = AsyncMock()
    no_captcha.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "button" in selector or "claim" in selector.lower():
            return claim_btn
        elif "captcha" in selector.lower():
            return no_captcha
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = LitePickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.get_timer = AsyncMock(return_value=0.0)
    bot.get_balance = AsyncMock(return_value="0.003")
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Already Claimed"
    assert result.next_claim_minutes == 60


@pytest.mark.asyncio
async def test_litepick_claim_with_error_message(mock_settings, mock_page, mock_solver):
    """Test claim when site returns an error message."""
    # No timer
    bot = LitePickBot(mock_settings, mock_page)
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.handle_cloudflare = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot.human_like_click = AsyncMock()
    bot.get_timer = AsyncMock(return_value=0.0)
    
    # Claim button visible
    claim_btn = AsyncMock()
    claim_btn.is_visible = AsyncMock(return_value=True)
    
    # No success message
    success_msg = AsyncMock()
    success_msg.count = AsyncMock(return_value=0)
    
    # Error message present
    error_msg = AsyncMock()
    error_msg.count = AsyncMock(return_value=1)
    error_msg.first = AsyncMock()
    error_msg.first.text_content = AsyncMock(return_value="Too many requests. Try again later.")
    
    # No captcha
    no_captcha = AsyncMock()
    no_captcha.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "button" in selector or "claim" in selector.lower():
            return claim_btn
        elif "alert-danger" in selector or ".error" in selector:
            return error_msg
        elif "alert-success" in selector or ".alert" in selector or "success" in selector.lower():
            return success_msg
        elif "captcha" in selector.lower():
            return no_captcha
        return AsyncMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    result = await bot.claim()
    
    assert result.success is False
    assert "Too many requests" in result.status
    assert result.next_claim_minutes == 10
