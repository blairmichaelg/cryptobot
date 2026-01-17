
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from faucets.base import FaucetBot
from browser.instance import BrowserManager

@pytest.mark.asyncio
async def test_stealth_primitives():
    # Mock page and settings
    page = AsyncMock()
    page.viewport_size = {'width': 1920, 'height': 1080}
    
    # Setup locator mock
    locator_mock = AsyncMock()
    locator_mock.is_visible.return_value = True
    locator_mock.bounding_box.return_value = None
    page.locator.return_value = locator_mock
    
    settings = MagicMock()
    settings.captcha_provider = "2captcha"
    settings.twocaptcha_api_key = "test"
    
    bot = FaucetBot(settings, page)
    
    # Test human_type
    selector = "#email"
    text = "test@example.com"
    await bot.human_type(selector, text, delay_min=1, delay_max=1)
    
    # Verify we clicked and pressed keys
    assert page.locator.called
    # press should be called on the locator returned by page.locator()
    assert locator_mock.press.call_count == len(text)

@pytest.mark.asyncio
async def test_idle_mouse():
    page = AsyncMock()
    page.viewport_size = {'width': 800, 'height': 600}
    settings = MagicMock()
    bot = FaucetBot(settings, page)
    
    # Run idle mouse for a short duration
    await bot.idle_mouse(duration=0.1)
    
    # Verify mouse moved
    assert page.mouse.move.called

@pytest.mark.asyncio
async def test_browser_restart_logic():
    # Mock AsyncCamoufox
    bm = BrowserManager(headless=True)
    bm.camoufox = AsyncMock()
    bm.browser = AsyncMock()
    
    # Test check_health
    # Mock new_context to succeed
    bm.browser.new_context = AsyncMock()
    health = await bm.check_health()
    assert health is True
    
    # Mock restart
    bm.launch = AsyncMock()
    bm.close = AsyncMock()
    await bm.restart()
    assert bm.close.called
    assert bm.launch.called
