import pytest
import asyncio
from browser.instance import create_stealth_browser

@pytest.mark.asyncio
async def test_stealth_browser_launch():
    print("Launching browser...")
    try:
        # Use headless=True for CI/Testing environments to avoid UI popups
        async with await create_stealth_browser(headless=True) as browser:
            print("Browser launched.")
            page = await browser.new_page()
            response = await page.goto("https://example.com")
            print("Page loaded.")
            
            assert response.status == 200, f"❌ Failed to load page, status: {response.status}"
            assert await page.title() is not None
            
            print("✅ Browser launch and navigation successful")
            
    except Exception as e:
        pytest.fail(f"Error during browser test: {e}")
