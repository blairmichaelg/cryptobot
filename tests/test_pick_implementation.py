import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

from faucets.litepick import LitePickBot
from faucets.base import ClaimResult
from core.config import BotSettings

@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=BotSettings)
    settings.get_account.return_value = {"email": "test@example.com", "password": "password"}
    settings.wallet_addresses = {"LTC": {"address": "LTC_ADDR_123"}}
    settings.captcha_provider = "capsolver"
    settings.capsolver_api_key = "key"
    return settings

@pytest.fixture
def mock_solver():
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)
        yield solver_instance

@pytest.fixture
def mock_page():
    page = AsyncMock()
    page.title.return_value = "LitePick"
    # Setup locator chain
    page.locator = MagicMock()
    page.locator.return_value.count = AsyncMock(return_value=0)
    page.locator.return_value.is_visible = AsyncMock(return_value=False)
    page.locator.return_value.text_content = AsyncMock(return_value="")
    page.locator.return_value.get_attribute = AsyncMock(return_value="")
    page.locator.return_value.first = MagicMock() # .first property
    page.locator.return_value.first.is_visible = AsyncMock(return_value=False)
    page.locator.return_value.first.text_content = AsyncMock(return_value="")
    
    # Mock query_selector to return None by default (not logged in)
    page.query_selector = AsyncMock(return_value=None)
    
    return page

@pytest.mark.asyncio
async def test_pick_login_success(mock_settings, mock_page, mock_solver):
    # Setup email field
    email_field = AsyncMock()
    email_field.is_visible = AsyncMock(return_value=True)
    
    # Setup password field
    pass_field = AsyncMock()
    pass_field.is_visible = AsyncMock(return_value=True)
    
    # Setup login button
    login_btn = AsyncMock()
    login_btn.is_visible = AsyncMock(return_value=True)
    
    # After login, is_logged_in checks for logout link
    logout_link = AsyncMock()
    logout_link.is_visible = AsyncMock(return_value=True)
    
    # No captcha present
    no_captcha = AsyncMock()
    no_captcha.count = AsyncMock(return_value=0)
    
    # Locator matching
    def locator_side_effect(selector):
        if "email" in selector.lower():
            return email_field
        elif "password" in selector.lower():
            return pass_field
        elif "logout" in selector.lower():
            return logout_link
        elif "login" in selector.lower() or "btn" in selector.lower():
            return login_btn
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
    bot._navigate_with_retry.assert_called()
    bot.human_like_click.assert_called()

@pytest.mark.asyncio
async def test_pick_claim_success(mock_settings, mock_page, mock_solver):
    bot = LitePickBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock()
    bot.idle_mouse = AsyncMock()
    bot._navigate_with_retry = AsyncMock(return_value=True)
    bot.get_timer = AsyncMock(return_value=0.0)
    bot.get_balance = AsyncMock(return_value="0.01")
    
    # Mock Claim Button visibility
    claim_btn = AsyncMock()
    claim_btn.is_visible = AsyncMock(return_value=True)
    claim_btn.count = AsyncMock(return_value=1)
    
    # Mock Success Message
    success_msg = AsyncMock()
    success_msg.count = AsyncMock(return_value=1)
    success_msg.first = AsyncMock()
    success_msg.first.text_content = AsyncMock(return_value="You won 0.005 LTC")
    
    # No captcha
    no_captcha = AsyncMock()
    no_captcha.count = AsyncMock(return_value=0)
    
    def locator_side_effect(selector):
        if "button" in selector or "claim" in selector:
            return claim_btn
        elif "alert-success" in selector or "success" in selector.lower():
            return success_msg
        elif "captcha" in selector.lower():
            return no_captcha
        return AsyncMock()
        
    mock_page.locator.side_effect = locator_side_effect
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Claimed"
    assert "0.00015" in result.amount or "0.005" in result.amount  # Allow for extraction or original
    assert result.balance == "0.01"

@pytest.mark.asyncio
async def test_pick_withdraw_success(mock_settings, mock_page, mock_solver):
    bot = LitePickBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.handle_cloudflare = AsyncMock()
    
    # Mock Balance for threshold check (if applicable, though pick.py might not check)
    balance_ele = AsyncMock()
    balance_ele.count.return_value = 1
    balance_ele.first.is_visible.return_value = True
    balance_ele.first.text_content.return_value = "0.05 LTC" # Above threshold
    
    # Mock Form Elements
    addr_input = AsyncMock()
    addr_input.count.return_value = 1
    addr_input.get_attribute.return_value = "" # Empty initially
    
    amount_input = AsyncMock()
    amount_input.count.return_value = 1
    
    submit_btn = AsyncMock()
    
    # Mock Success content
    mock_page.content.return_value = "<html><body>Withdrawal success</body></html>"
    
    def locator_side_effect(selector):
        if "balance" in selector: return balance_ele
        if "address" in selector: return addr_input
        if "amount" in selector: return amount_input
        if "Withdraw" in selector: return submit_btn
        return AsyncMock()
        
    mock_page.locator.side_effect = locator_side_effect
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "Withdrawn"
    # mock_page.fill.assert_called() # Incorrect - implementation uses locator.fill
    addr_input.fill.assert_called()
    bot.human_like_click.assert_called()
