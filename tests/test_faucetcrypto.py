import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from faucets.faucetcrypto import FaucetCryptoBot
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
    page.url = "https://faucetcrypto.com"
    page.title.return_value = "FaucetCrypto"
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
    locator_mock.first.fill = AsyncMock()
    locator_mock.last = MagicMock()
    locator_mock.click = AsyncMock()
    page.locator.return_value = locator_mock
    
    page.query_selector = AsyncMock(return_value=None)
    page.goto = AsyncMock()
    page.fill = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.wait_for_selector = AsyncMock()
    
    return page


@pytest.mark.asyncio
async def test_faucetcrypto_initialization(mock_settings, mock_page, mock_solver):
    """Test FaucetCryptoBot initialization"""
    bot = FaucetCryptoBot(mock_settings, mock_page)
    
    assert bot.faucet_name == "FaucetCrypto"
    assert bot.base_url == "https://faucetcrypto.com"
    assert hasattr(bot, 'login')
    assert hasattr(bot, 'claim')


@pytest.mark.asyncio
async def test_faucetcrypto_login_no_credentials(mock_settings, mock_page, mock_solver):
    """Test login fails when no credentials are provided"""
    mock_settings.get_account.return_value = None
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_faucetcrypto_login_already_logged_in(mock_settings, mock_page, mock_solver):
    """Test login when already logged in"""
    mock_page.url = "https://faucetcrypto.com/dashboard"
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    
    result = await bot.login()
    
    assert result is True


@pytest.mark.asyncio
async def test_faucetcrypto_login_success(mock_settings, mock_page, mock_solver):
    """Test successful login"""
    mock_page.url = "https://faucetcrypto.com/login"
    
    email_input = MagicMock()
    email_input.first = MagicMock()
    email_input.first.fill = AsyncMock()
    
    password_input = MagicMock()
    password_input.first = MagicMock()
    password_input.first.fill = AsyncMock()
    
    login_btn = MagicMock()
    login_btn.first = MagicMock()
    
    def locator_side_effect(selector):
        if "email" in selector:
            return email_input
        elif "password" in selector:
            return password_input
        elif "Login" in selector or "Sign In" in selector:
            return login_btn
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.human_like_click = AsyncMock()
    
    result = await bot.login()
    
    assert result is True
    email_input.first.fill.assert_called_with("test@example.com")
    password_input.first.fill.assert_called_with("test_password")


@pytest.mark.asyncio
async def test_faucetcrypto_login_exception(mock_settings, mock_page, mock_solver):
    """Test login handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    result = await bot.login()
    
    assert result is False


@pytest.mark.asyncio
async def test_faucetcrypto_claim_success(mock_settings, mock_page, mock_solver):
    """Test successful claim"""
    claim_btn = MagicMock()
    claim_btn.count = AsyncMock(return_value=1)
    
    reward_btn = MagicMock()
    reward_btn.is_visible = AsyncMock(return_value=True)
    
    def locator_side_effect(selector):
        if "Ready To Claim" in selector:
            return claim_btn
        elif "Get Reward" in selector:
            return reward_btn
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot.human_like_click = AsyncMock()
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Claimed"


@pytest.mark.asyncio
async def test_faucetcrypto_claim_timer_active(mock_settings, mock_page, mock_solver):
    """Test claim when timer is active"""
    claim_btn = MagicMock()
    claim_btn.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = claim_btn
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot.get_timer = AsyncMock(return_value=15)
    
    result = await bot.claim()
    
    assert result.success is True
    assert result.status == "Timer Active"
    assert result.next_claim_minutes == 15


@pytest.mark.asyncio
async def test_faucetcrypto_claim_reward_button_not_found(mock_settings, mock_page, mock_solver):
    """Test claim when reward button is not found"""
    claim_btn = MagicMock()
    claim_btn.count = AsyncMock(return_value=1)
    
    reward_btn = MagicMock()
    reward_btn.is_visible = AsyncMock(return_value=False)
    
    def locator_side_effect(selector):
        if "Ready To Claim" in selector:
            return claim_btn
        elif "Get Reward" in selector:
            return reward_btn
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(return_value="100")
    bot.human_like_click = AsyncMock()
    
    result = await bot.claim()
    
    assert result.success is False
    assert result.status == "Reward Button Not Found"


@pytest.mark.asyncio
async def test_faucetcrypto_claim_exception(mock_settings, mock_page, mock_solver):
    """Test claim handles exceptions"""
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.get_balance = AsyncMock(side_effect=Exception("Error"))
    
    result = await bot.claim()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_faucetcrypto_view_ptc_ads(mock_settings, mock_page, mock_solver):
    """Test viewing PTC ads"""
    watch_btn = MagicMock()
    watch_btn.is_visible = AsyncMock(side_effect=[True, False])
    watch_btn.first = MagicMock()
    
    reward_btn = MagicMock()
    
    continue_btn = MagicMock()
    continue_btn.wait_for = AsyncMock()
    
    def locator_side_effect(selector):
        if "Watch" in selector:
            return watch_btn
        elif "Get Reward" in selector:
            return reward_btn
        elif "continue-button" in selector or "Continue" in selector:
            return continue_btn
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    await bot.view_ptc_ads()
    
    # Verify method completed
    assert True


@pytest.mark.asyncio
async def test_faucetcrypto_withdraw_success(mock_settings, mock_page, mock_solver):
    """Test successful withdrawal"""
    crypto_rows = MagicMock()
    crypto_rows.count = AsyncMock(return_value=1)
    crypto_rows.first = MagicMock()
    
    withdraw_btn = MagicMock()
    crypto_rows.first.locator.return_value = withdraw_btn
    
    next_btn = MagicMock()
    next_btn.is_visible = AsyncMock(return_value=True)
    
    max_btn = MagicMock()
    max_btn.is_visible = AsyncMock(return_value=True)
    
    amount_field = MagicMock()
    address_field = MagicMock()
    
    confirm_switch = MagicMock()
    confirm_switch.is_visible = AsyncMock(return_value=True)
    confirm_switch.click = AsyncMock()
    
    submit_btn = MagicMock()
    
    success_msg = MagicMock()
    success_msg.count = AsyncMock(return_value=1)
    
    def locator_side_effect(selector):
        if "crypto-row" in selector or "card:has" in selector:
            return crypto_rows
        elif "Next Step" in selector or "next-step" in selector:
            return next_btn
        elif "Max" in selector or "max-btn" in selector:
            return max_btn
        elif "amount" in selector:
            return amount_field
        elif "address" in selector or "wallet-address" in selector:
            return address_field
        elif "confirm-switch" in selector or "confirm-checkbox" in selector:
            return confirm_switch
        elif "Submit Withdrawal" in selector or "submit-btn" in selector:
            return submit_btn
        elif "alert-success" in selector or "toast-success" in selector:
            return success_msg
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_balance = AsyncMock(return_value="100")
    bot.get_withdrawal_address = MagicMock(return_value="BTC_ADDRESS_123")
    bot.human_like_click = AsyncMock()
    bot.human_type = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "Withdrawn"


@pytest.mark.asyncio
async def test_faucetcrypto_withdraw_no_balance(mock_settings, mock_page, mock_solver):
    """Test withdrawal when no balance is available"""
    crypto_rows = MagicMock()
    crypto_rows.count = AsyncMock(return_value=0)
    
    mock_page.locator.return_value = crypto_rows
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_balance = AsyncMock(return_value="0")
    
    result = await bot.withdraw()
    
    assert result.success is True
    assert result.status == "No Balance"


@pytest.mark.asyncio
async def test_faucetcrypto_withdraw_no_address(mock_settings, mock_page, mock_solver):
    """Test withdrawal when no address is configured"""
    crypto_rows = MagicMock()
    crypto_rows.count = AsyncMock(return_value=1)
    crypto_rows.first = MagicMock()
    
    withdraw_btn = MagicMock()
    crypto_rows.first.locator.return_value = withdraw_btn
    
    next_btn = MagicMock()
    next_btn.is_visible = AsyncMock(return_value=True)
    
    max_btn = MagicMock()
    max_btn.is_visible = AsyncMock(return_value=True)
    
    amount_field = MagicMock()
    address_field = MagicMock()
    
    def locator_side_effect(selector):
        if "crypto-row" in selector or "card:has" in selector:
            return crypto_rows
        elif "Next Step" in selector or "next-step" in selector:
            return next_btn
        elif "Max" in selector or "max-btn" in selector:
            return max_btn
        elif "amount" in selector:
            return amount_field
        elif "address" in selector or "wallet-address" in selector:
            return address_field
        return MagicMock()
    
    mock_page.locator.side_effect = locator_side_effect
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    bot.handle_cloudflare = AsyncMock()
    bot.get_balance = AsyncMock(return_value="100")
    bot.get_withdrawal_address = MagicMock(return_value=None)
    bot.human_like_click = AsyncMock()
    bot.random_delay = AsyncMock()
    
    result = await bot.withdraw()
    
    assert result.success is False
    assert result.status == "No Address"


@pytest.mark.asyncio
async def test_faucetcrypto_withdraw_exception(mock_settings, mock_page, mock_solver):
    """Test withdrawal handles exceptions"""
    mock_page.goto.side_effect = Exception("Network error")
    
    bot = FaucetCryptoBot(mock_settings, mock_page)
    result = await bot.withdraw()
    
    assert result.success is False
    assert "Error" in result.status


@pytest.mark.asyncio
async def test_faucetcrypto_get_jobs(mock_settings, mock_page, mock_solver):
    """Test get_jobs returns correct job structure"""
    bot = FaucetCryptoBot(mock_settings, mock_page)
    jobs = bot.get_jobs()
    
    assert len(jobs) == 3
    assert jobs[0].name == "FaucetCrypto Claim"
    assert jobs[1].name == "FaucetCrypto Withdraw"
    assert jobs[2].name == "FaucetCrypto PTC"
