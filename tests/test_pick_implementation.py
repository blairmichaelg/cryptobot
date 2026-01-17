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
    # Setup checks
    async def side_effect_visible():
        return True
    
    # After login, is_logged_in checks for logout link - using count()
    logout_link = AsyncMock()
    logout_link.count.side_effect = [0, 1] # First 0 (not logged in), then 1 (logged in)
    
    # Locator matching
    def locator_side_effect(selector):
        if "logout" in selector: return logout_link
        return AsyncMock()

    mock_page.locator.side_effect = locator_side_effect
    
    bot = LitePickBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock()
    
    result = await bot.login()
    
    assert result is True
    mock_page.goto.assert_called()
    bot.human_like_click.assert_called()

@pytest.mark.asyncio
async def test_pick_claim_success(mock_settings, mock_page, mock_solver):
    bot = LitePickBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.close_popups = AsyncMock()
    bot.handle_cloudflare = AsyncMock()
    
    # Mock Claim Button visibility
    claim_btn = AsyncMock()
    claim_btn.is_visible.return_value = True
    claim_btn.count.return_value = 1
    
    # Mock Success Message
    success_msg = AsyncMock()
    success_msg.count.return_value = 1
    success_msg.first.text_content.return_value = "You won 0.005 LTC"
    
    # Mock Balance
    balance_ele = AsyncMock()
    balance_ele.count.return_value = 1
    balance_ele.first.is_visible.return_value = True
    balance_ele.first.text_content.return_value = "0.01 LTC"
    
    def locator_side_effect(selector):
        if "button" in selector or "claim" in selector: return claim_btn
        if "alert-success" in selector: return success_msg
        if "balance" in selector: return balance_ele
        return AsyncMock()
        
    mock_page.locator.side_effect = locator_side_effect
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Claimed"
    assert "0.005" in result.amount
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
