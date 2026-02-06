"""
Test script to inspect Cointiply selectors and update the bot.
"""
import asyncio
import logging
from playwright.async_api import async_playwright
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from browser.instance import BrowserManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_cointiply_login():
    """Inspect Cointiply login page to find current selectors."""
    
    logger.info("🔍 Inspecting Cointiply login page...")
    
    # Initialize settings
    settings = BotSettings()
    browser_manager = BrowserManager(headless=False)
    
    try:
        # Create a browser context
        context = await browser_manager.create_context()
        page = await browser_manager.new_page(context)
        
        # Navigate to login page
        logger.info("📄 Navigating to https://cointiply.com/login")
        await page.goto("https://cointiply.com/login", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)  # Wait for any dynamic content
        
        # Take screenshot
        screenshot_path = Path("logs/cointiply_login_page.png")
        await page.screenshot(path=str(screenshot_path))
        logger.info(f"📸 Screenshot saved to {screenshot_path}")
        
        # Check for common login selectors
        selectors_to_check = {
            "email_field": [
                'input[name="email"]',
                'input[type="email"]',
                'input[placeholder*="email" i]',
                'input[id*="email" i]',
                '#email',
                '.email-input',
                'input[autocomplete="username"]',
                'input[autocomplete="email"]'
            ],
            "password_field": [
                'input[name="password"]',
                'input[type="password"]',
                '#password',
                '.password-input',
                'input[autocomplete="current-password"]'
            ],
            "login_button": [
                'button:has-text("Login")',
                'button:has-text("Log in")',
                'button[type="submit"]',
                'input[type="submit"]',
                '.login-button',
                '#login-button',
                'button.btn-primary'
            ],
            "captcha": [
                'iframe[src*="hcaptcha"]',
                'iframe[src*="recaptcha"]',
                '.cf-turnstile',
                '#cf-turnstile',
                '[data-sitekey]'
            ]
        }
        
        results = {}
        
        for field_name, selectors in selectors_to_check.items():
            logger.info(f"\n🔎 Checking {field_name}:")
            found = []
            
            for selector in selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        is_visible = await page.locator(selector).first.is_visible()
                        logger.info(f"  ✅ Found: {selector} (count={count}, visible={is_visible})")
                        
                        # Get additional info for form fields
                        if 'input' in selector:
                            placeholder = await page.locator(selector).first.get_attribute("placeholder")
                            input_id = await page.locator(selector).first.get_attribute("id")
                            input_name = await page.locator(selector).first.get_attribute("name")
                            logger.info(f"     Placeholder: {placeholder}, ID: {input_id}, Name: {input_name}")
                        
                        found.append({
                            "selector": selector,
                            "count": count,
                            "visible": is_visible
                        })
                except Exception as e:
                    logger.debug(f"  ❌ Not found: {selector} ({e})")
            
            results[field_name] = found
        
        # Check page content for cloudflare/security
        content = await page.content()
        if "cloudflare" in content.lower():
            logger.warning("⚠️  Cloudflare detected in page content")
        if "just a moment" in content.lower():
            logger.warning("⚠️  Cloudflare challenge detected")
        if "verify you are human" in content.lower():
            logger.warning("⚠️  Human verification required")
        
        # Get page title and URL
        title = await page.title()
        url = page.url
        logger.info(f"\n📋 Page Info:")
        logger.info(f"   Title: {title}")
        logger.info(f"   URL: {url}")
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("SELECTOR SUMMARY:")
        logger.info("="*60)
        
        for field_name, found_selectors in results.items():
            if found_selectors:
                best = found_selectors[0]
                logger.info(f"\n{field_name.upper()}:")
                logger.info(f"  Best selector: {best['selector']}")
                logger.info(f"  Visible: {best['visible']}")
            else:
                logger.warning(f"\n{field_name.upper()}: ❌ NO SELECTORS FOUND")
        
        logger.info("\n" + "="*60)
        
        # Wait for manual inspection
        logger.info("\n⏸️  Browser will stay open for 30 seconds for manual inspection...")
        await asyncio.sleep(30)
        
        await context.close()
        await browser_manager.close()
        
    except Exception as e:
        logger.error(f"❌ Error during inspection: {e}", exc_info=True)

async def test_login_flow():
    """Test the actual login flow with credentials."""
    
    logger.info("🔐 Testing Cointiply login flow...")
    
    settings = BotSettings()
    creds = settings.get_account("cointiply")
    
    if not creds:
        logger.error("❌ No Cointiply credentials configured in .env")
        return
    
    logger.info(f"Using credentials: {creds['username']}")
    
    browser_manager = BrowserManager(headless=False)
    
    try:
        context = await browser_manager.create_context()
        page = await browser_manager.new_page(context)
        
        # Navigate
        logger.info("📄 Navigating to login page...")
        await page.goto("https://cointiply.com/login", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        # Fill email
        logger.info("📝 Filling email...")
        email_input = page.locator('input[name="email"]')
        await email_input.fill(creds['username'])
        await asyncio.sleep(1)
        
        # Fill password
        logger.info("📝 Filling password...")
        password_input = page.locator('input[name="password"]')
        await password_input.fill(creds['password'])
        await asyncio.sleep(1)
        
        # Take screenshot before submit
        await page.screenshot(path="logs/cointiply_before_submit.png")
        logger.info("📸 Screenshot saved: cointiply_before_submit.png")
        
        # Check for captcha
        captcha_iframe = page.locator('iframe[src*="hcaptcha"], iframe[src*="recaptcha"], .cf-turnstile')
        captcha_count = await captcha_iframe.count()
        if captcha_count > 0:
            logger.warning(f"⚠️  CAPTCHA detected! Count: {captcha_count}")
            logger.info("⏸️  Pausing for 60 seconds - solve captcha manually...")
            await asyncio.sleep(60)
        
        # Click login button
        logger.info("🖱️  Clicking login button...")
        login_button = page.locator('button:has-text("Login")')
        await login_button.click()
        
        # Wait for navigation or error
        logger.info("⏳ Waiting for login result...")
        await asyncio.sleep(5)
        
        # Check result
        url = page.url
        title = await page.title()
        
        logger.info(f"📋 After login:")
        logger.info(f"   URL: {url}")
        logger.info(f"   Title: {title}")
        
        # Take screenshot
        await page.screenshot(path="logs/cointiply_after_login.png")
        logger.info("📸 Screenshot saved: cointiply_after_login.png")
        
        # Check for success indicators
        if "dashboard" in url or "home" in url:
            logger.info("✅ Login appears successful (URL changed to dashboard/home)")
        else:
            logger.warning(f"⚠️  Login may have failed - still on: {url}")
            
            # Check for error messages
            error_selectors = ['.error-message', '.alert-danger', '.text-danger', '.error']
            for selector in error_selectors:
                error_elem = page.locator(selector)
                if await error_elem.count() > 0:
                    error_text = await error_elem.first.text_content()
                    logger.error(f"❌ Error message found: {error_text}")
        
        # Wait for inspection
        logger.info("\n⏸️  Browser will stay open for 30 seconds...")
        await asyncio.sleep(30)
        
        await context.close()
        await browser_manager.close()
        
    except Exception as e:
        logger.error(f"❌ Error during login test: {e}", exc_info=True)

async def main():
    """Main entry point."""
    print("="*60)
    print("COINTIPLY SELECTOR INSPECTOR")
    print("="*60)
    print("\nChoose an option:")
    print("1. Inspect login page selectors")
    print("2. Test actual login flow")
    print("3. Both")
    print()
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice in ["1", "3"]:
        await inspect_cointiply_login()
    
    if choice in ["2", "3"]:
        await test_login_flow()

if __name__ == "__main__":
    asyncio.run(main())
