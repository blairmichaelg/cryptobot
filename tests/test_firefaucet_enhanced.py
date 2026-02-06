"""
Enhanced tests for FireFaucet bot - Testing improved functionality.

Tests cover:
- DataExtractor integration with fallback selectors
- Balance extraction with various formats
- Timer parsing with different formats
- CAPTCHA solving retry logic
- Network error handling and categorization
- Stealth features (human_type, idle_mouse)
"""
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call
from faucets.firefaucet import FireFaucetBot
from faucets.base import ClaimResult
from core.config import BotSettings
from core.extractor import DataExtractor


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
def mock_page():
    """Enhanced fixture for mock Playwright Page with proper async support"""
    page = AsyncMock()
    page.url = "https://firefaucet.win/faucet"
    page.title = AsyncMock(return_value="FireFaucet")
    page.content = AsyncMock(return_value="<html><body></body></html>")
    page.goto = AsyncMock()
    page.fill = AsyncMock()
    page.click = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.evaluate = AsyncMock()
    page.screenshot = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    
    # Setup default locator behavior
    def create_locator(selector):
        locator = MagicMock()
        locator.count = AsyncMock(return_value=0)
        locator.is_visible = AsyncMock(return_value=False)
        locator.first = MagicMock()
        locator.first.is_visible = AsyncMock(return_value=False)
        locator.first.text_content = AsyncMock(return_value="")
        locator.first.click = AsyncMock()
        locator.scroll_into_view_if_needed = AsyncMock()
        locator.bounding_box = AsyncMock(return_value=None)
        return locator
    
    page.locator = MagicMock(side_effect=create_locator)
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.viewport_size = {'width': 1920, 'height': 1080}
    
    return page


@pytest.mark.asyncio
async def test_balance_extraction_with_fallbacks(mock_settings, mock_page):
    """Test balance extraction uses fallback selectors when primary fails"""
    bot = FireFaucetBot(mock_settings, mock_page)
    
    # Setup: First selector fails, second succeeds
    def locator_side_effect(selector):
        loc = MagicMock()
        loc.count = AsyncMock()
        loc.is_visible = AsyncMock()
        loc.first = MagicMock()
        
        if selector == ".user-balance":
            # Primary selector fails
            loc.count.return_value = 0
            loc.first.is_visible.return_value = False
        elif selector == ".balance-text":
            # Fallback selector succeeds
            loc.count.return_value = 1
            loc.first.is_visible.return_value = True
            loc.first.text_content = AsyncMock(return_value="Balance: 1,234.56 BTC")
        else:
            loc.count.return_value = 0
            loc.first.is_visible.return_value = False
        return loc
    
    mock_page.locator.side_effect = locator_side_effect
    
    # Call get_balance with fallbacks
    balance = await bot.get_balance(".user-balance", fallback_selectors=[".balance-text", "[class*='balance']"])
    
    # Should extract numeric value
    assert balance == "1234.56"


@pytest.mark.asyncio
async def test_timer_extraction_with_fallbacks(mock_settings, mock_page):
    """Test timer extraction uses fallback selectors when primary fails"""
    bot = FireFaucetBot(mock_settings, mock_page)
    
    # Setup: First selector fails, second succeeds
    def locator_side_effect(selector):
        loc = MagicMock()
        loc.count = AsyncMock()
        loc.is_visible = AsyncMock()
        loc.first = MagicMock()
        
        if selector == ".fa-clock + span":
            # Primary selector fails
            loc.count.return_value = 0
            loc.first.is_visible.return_value = False
        elif selector == "#claim_timer":
            # Fallback selector succeeds
            loc.count.return_value = 1
            loc.first.is_visible.return_value = True
            loc.first.text_content = AsyncMock(return_value="15:30")
        else:
            loc.count.return_value = 0
            loc.first.is_visible.return_value = False
        return loc
    
    mock_page.locator.side_effect = locator_side_effect
    
    # Call get_timer with fallbacks
    timer_mins = await bot.get_timer(".fa-clock + span", fallback_selectors=["#claim_timer", ".timer"])
    
    # Should parse as 15 minutes 30 seconds = 15.5 minutes
    assert timer_mins == 15.5


@pytest.mark.asyncio
async def test_captcha_retry_logic(mock_settings, mock_page):
    """Test CAPTCHA solving with retry logic on failure"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        # First call fails, second succeeds
        solver_instance.solve_captcha = AsyncMock(side_effect=[False, True])
        
        bot = FireFaucetBot(mock_settings, mock_page)
        bot.solver = solver_instance
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)
        bot.random_delay = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.human_like_click = AsyncMock()
        
        # Setup page locators for claim flow
        def create_locator_for_claim(selector):
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            if "#get_reward_button" in selector or "Claim" in selector:
                loc.count = AsyncMock(return_value=1)
                loc.first = MagicMock()
                loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        
        mock_page.locator.side_effect = create_locator_for_claim
        
        # Execute claim
        result = await bot.claim()
        
        # Verify CAPTCHA solver was called twice (retry after failure)
        assert solver_instance.solve_captcha.call_count == 2


@pytest.mark.asyncio
async def test_captcha_retry_exhausted(mock_settings, mock_page):
    """Test CAPTCHA solving returns error when retries exhausted"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        # Both attempts fail
        solver_instance.solve_captcha = AsyncMock(return_value=False)
        
        bot = FireFaucetBot(mock_settings, mock_page)
        bot.solver = solver_instance
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)
        bot.random_delay = AsyncMock()
        bot.idle_mouse = AsyncMock()
        
        # Execute claim
        result = await bot.claim()
        
        # Should return error result
        assert result.success is False
        assert "CAPTCHA Failed" in result.status
        assert result.next_claim_minutes == 5


@pytest.mark.asyncio
async def test_network_error_categorization(mock_settings, mock_page):
    """Test network errors are categorized and have shorter retry times"""
    mock_page.goto.side_effect = Exception("Connection timeout")
    
    bot = FireFaucetBot(mock_settings, mock_page)
    result = await bot.claim()
    
    assert result.success is False
    assert "Network Error" in result.status
    assert result.next_claim_minutes == 5  # Short retry for network errors


@pytest.mark.asyncio
async def test_captcha_error_categorization(mock_settings, mock_page):
    """Test CAPTCHA errors have medium retry times"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(side_effect=Exception("Captcha service error"))
        
        bot = FireFaucetBot(mock_settings, mock_page)
        bot.solver = solver_instance
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)
        
        result = await bot.claim()
        
        assert result.success is False
        assert "CAPTCHA Error" in result.status
        assert result.next_claim_minutes == 10  # Medium retry for CAPTCHA errors


@pytest.mark.asyncio
async def test_human_type_called_for_login(mock_settings, mock_page):
    """Test that human_type is used instead of page.fill for login"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)

        bot = FireFaucetBot(mock_settings, mock_page)
        bot.solver = solver_instance
        bot.safe_navigate = AsyncMock(return_value=True)
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.human_type = AsyncMock()
        bot.idle_mouse = AsyncMock()
        bot.random_delay = AsyncMock()

        # Start on login page (not dashboard - otherwise login returns True immediately)
        mock_page.url = "https://firefaucet.win/login"
        mock_page.wait_for_selector = AsyncMock()

        # Mock submit button locator
        submit_btn = MagicMock()
        submit_btn.count = AsyncMock(return_value=1)
        submit_btn.is_disabled = AsyncMock(return_value=False)

        # Mock dashboard elements (not visible initially)
        dashboard_loc = MagicMock()
        dashboard_loc.count = AsyncMock(return_value=0)

        def create_locator(selector):
            loc = MagicMock()
            loc.count = AsyncMock(return_value=0)
            loc.first = MagicMock()
            loc.first.is_visible = AsyncMock(return_value=False)
            loc.first.text_content = AsyncMock(return_value="")
            if "submitbtn" in selector or 'submit' in selector:
                return submit_btn
            elif "user-balance" in selector or "level-progress" in selector or "dashboard" in selector:
                return dashboard_loc
            return loc

        mock_page.locator = MagicMock(side_effect=create_locator)

        # After human_like_click (submit), change URL to dashboard
        async def click_and_redirect(*args, **kwargs):
            mock_page.url = "https://firefaucet.win/dashboard"
        bot.human_like_click = AsyncMock(side_effect=click_and_redirect)

        result = await bot.login()

        # Verify human_type was called for both username and password
        assert bot.human_type.call_count >= 2
        # Verify idle_mouse was called for stealth
        assert bot.idle_mouse.call_count >= 2


@pytest.mark.asyncio
async def test_idle_mouse_called_during_claim(mock_settings, mock_page):
    """Test that idle_mouse is called during claim for stealth"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)
        
        bot = FireFaucetBot(mock_settings, mock_page)
        bot.solver = solver_instance
        bot.idle_mouse = AsyncMock()
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)
        bot.human_like_click = AsyncMock()
        bot.random_delay = AsyncMock()
        
        # Setup claim button
        def create_claim_locator(selector):
            loc = MagicMock()
            if "#get_reward_button" in selector:
                loc.count = AsyncMock(return_value=1)
            elif ".success_msg" in selector or "success" in selector:
                loc.count = AsyncMock(return_value=1)
                loc.first = MagicMock()
                loc.first.text_content = AsyncMock(return_value="Success!")
            else:
                loc.count = AsyncMock(return_value=0)
            return loc
        
        mock_page.locator.side_effect = create_claim_locator
        
        result = await bot.claim()
        
        # Verify idle_mouse was called for stealth (at least before and after CAPTCHA)
        assert bot.idle_mouse.call_count >= 2


@pytest.mark.asyncio
async def test_balance_updated_after_claim(mock_settings, mock_page):
    """Test that balance is re-extracted after successful claim"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)

        bot = FireFaucetBot(mock_settings, mock_page)
        bot.solver = solver_instance
        bot.idle_mouse = AsyncMock()
        bot.human_like_click = AsyncMock()
        bot.random_delay = AsyncMock()
        bot.detect_cloudflare_block = AsyncMock(return_value=False)
        bot.handle_cloudflare = AsyncMock()
        bot.simulate_reading = AsyncMock()

        # Fix async mocks for page methods used by claim
        mock_page.evaluate = AsyncMock(return_value="")
        mock_page.title = AsyncMock(return_value="FireFaucet")
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock()

        # Mock get_balance to return different values (before and after claim)
        balance_calls = ["100", "150"]
        bot.get_balance = AsyncMock(side_effect=balance_calls)
        bot.get_timer = AsyncMock(return_value=0)

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

        # Setup faucet button
        faucet_btn = create_default_locator()
        faucet_btn.count = AsyncMock(return_value=1)
        faucet_btn.first.is_visible = AsyncMock(return_value=True)
        faucet_btn.first.text_content = AsyncMock(return_value="Get Reward")
        faucet_btn.first.is_enabled = AsyncMock(return_value=True)
        faucet_btn.first.get_attribute = AsyncMock(return_value=None)

        # Setup success message (needs is_visible on the locator itself for .nth(i).is_visible() check)
        success_locator = create_default_locator()
        success_locator.count = AsyncMock(return_value=1)
        success_locator.is_visible = AsyncMock(return_value=True)
        success_locator.text_content = AsyncMock(return_value="Claim successful!")
        success_locator.first.is_visible = AsyncMock(return_value=True)
        success_locator.first.text_content = AsyncMock(return_value="Claim successful!")

        def create_locator(selector):
            if "#get_reward_button" in selector:
                return faucet_btn
            elif "success" in selector.lower() or "alert-success" in selector:
                return success_locator
            elif "Get reward" in selector or "Get Reward" in selector or "Claim" in selector:
                return faucet_btn
            return create_default_locator()

        mock_page.locator.side_effect = create_locator

        result = await bot.claim()

        # Verify balance was fetched at least twice (before claim + after success)
        assert bot.get_balance.call_count >= 2
        # Verify final balance in result
        assert result.balance == "150"


@pytest.mark.asyncio  
async def test_multiple_button_selectors_tried(mock_settings, mock_page):
    """Test that multiple button selectors are tried when primary fails"""
    with patch("faucets.base.CaptchaSolver") as MockSolver:
        solver_instance = MockSolver.return_value
        solver_instance.solve_captcha = AsyncMock(return_value=True)
        
        bot = FireFaucetBot(mock_settings, mock_page)
        bot.solver = solver_instance
        bot.idle_mouse = AsyncMock()
        bot.get_balance = AsyncMock(return_value="100")
        bot.get_timer = AsyncMock(return_value=0)
        bot.human_like_click = AsyncMock()
        bot.random_delay = AsyncMock()
        
        # Setup: Primary button selector fails, fallback succeeds
        selector_counts = {
            "#get_reward_button": 0,  # Primary fails
            "#faucet_btn": 0,         # Fallback 1 fails
            "button:has-text('Claim')": 1,  # Fallback 2 succeeds
        }
        
        def create_button_locator(selector):
            loc = MagicMock()
            count = selector_counts.get(selector, 0)
            loc.count = AsyncMock(return_value=count)
            if count > 0:
                loc.first = MagicMock()
                loc.first.is_visible = AsyncMock(return_value=True)
            return loc
        
        mock_page.locator.side_effect = create_button_locator
        
        result = await bot.claim()
        
        # Verify human_like_click was eventually called on the working selector
        assert bot.human_like_click.call_count >= 1


@pytest.mark.asyncio
async def test_dataextractor_timer_parsing():
    """Test DataExtractor parses various timer formats correctly"""
    # HH:MM:SS format
    assert DataExtractor.parse_timer_to_minutes("01:30:00") == 90.0
    
    # MM:SS format
    assert DataExtractor.parse_timer_to_minutes("15:30") == 15.5
    
    # Compound format
    assert DataExtractor.parse_timer_to_minutes("1h 30m") == 90.0
    assert DataExtractor.parse_timer_to_minutes("2h 15m 30s") == 135.5
    
    # Minutes only
    assert DataExtractor.parse_timer_to_minutes("45 minutes") == 45.0
    
    # Seconds only
    assert DataExtractor.parse_timer_to_minutes("120 seconds") == 2.0


@pytest.mark.asyncio
async def test_dataextractor_balance_extraction():
    """Test DataExtractor extracts balances from various formats"""
    # With commas
    assert DataExtractor.extract_balance("Balance: 1,234.56 BTC") == "1234.56"
    
    # Simple number
    assert DataExtractor.extract_balance("0.00012345") == "0.00012345"
    
    # With text before
    assert DataExtractor.extract_balance("Your balance is 999.99 satoshi") == "999.99"
    
    # Integer
    assert DataExtractor.extract_balance("1000") == "1000"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
