"""
Direct test of Cointiply login selectors - minimal dependencies.
"""
import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()

from browser.instance import BrowserManager
from core.config import BotSettings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_cointiply_direct():
    """Test Cointiply with direct browser access - no proxies."""
    
    logger.info("="*60)
    logger.info("COINTIPLY SELECTOR TEST - DIRECT MODE")
    logger.info("="*60)
    
    settings = BotSettings()
    creds = settings.get_account("cointiply")
    
    if not creds:
        logger.error("❌ No Cointiply credentials in .env")
        logger.info("Add: COINTIPLY_USERNAME=your@email.com")
        logger.info("Add: COINTIPLY_PASSWORD=yourpassword")
        return
    
    logger.info(f"✅ Credentials found for: {creds['username']}")
    
    # Create browser without proxy
    browser_manager = BrowserManager(headless=False, proxy=None)
    
    try:
        logger.info("\n� Launching browser...")
        await browser_manager.launch()
        
        logger.info("\n�📦 Creating browser context...")
        context = await browser_manager.create_context(proxy=None)
        page = await browser_manager.new_page(context)
        
        # Step 1: Navigate to login
        logger.info("\n📄 Navigating to https://cointiply.com/login ...")
        await page.goto("https://cointiply.com/login", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        # Take screenshot
        await page.screenshot(path="logs/cointiply_step1_loaded.png")
        logger.info("📸 Screenshot: logs/cointiply_step1_loaded.png")
        
        # Check page title
        title = await page.title()
        url = page.url
        logger.info(f"   Title: {title}")
        logger.info(f"   URL: {url}")
        
        # Step 2: Check selectors
        logger.info("\n🔍 Checking for login selectors...")
        
        email_selector = 'input[name="email"]'
        email_count = await page.locator(email_selector).count()
        logger.info(f"   Email field ({email_selector}): {email_count} found")
        
        password_selector = 'input[name="password"]'
        password_count = await page.locator(password_selector).count()
        logger.info(f"   Password field ({password_selector}): {password_count} found")
        
        login_selectors = [
            'form button[type="submit"]',
            'form input[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Log in")',
            'button:has-text("Sign In")',
            'button:has-text("Sign in")',
            'button.btn-primary',
            'button[type="submit"]'
        ]
        login_button_selector = None
        login_count = 0
        for selector in login_selectors:
            count = await page.locator(selector).count()
            if count > 0:
                login_button_selector = selector
                login_count = count
                break
        logger.info(f"   Login button ({login_button_selector}): {login_count} found")
        
        if email_count == 0 or password_count == 0:
            logger.error("\n❌ Login form not found! Possible causes:")
            logger.error("   - Cloudflare challenge blocking page")
            logger.error("   - Page structure changed")
            logger.error("   - JavaScript not loaded")
            
            # Check for cloudflare
            content = await page.content()
            if "cloudflare" in content.lower():
                logger.warning("⚠️  CLOUDFLARE DETECTED")
            if "just a moment" in content.lower():
                logger.warning("⚠️  CLOUDFLARE CHALLENGE PAGE")
            
            logger.info("\n⏸️  Browser will stay open for 60 seconds for manual inspection...")
            await asyncio.sleep(60)
            return
        
        # Step 3: Fill form
        logger.info("\n📝 Filling login form...")
        await page.locator(email_selector).fill(creds['username'])
        logger.info(f"   ✅ Filled email: {creds['username']}")
        await asyncio.sleep(1)
        
        await page.locator(password_selector).fill(creds['password'])
        logger.info("   ✅ Filled password")
        await asyncio.sleep(1)
        
        # Screenshot before submit
        await page.screenshot(path="logs/cointiply_step2_form_filled.png")
        logger.info("📸 Screenshot: logs/cointiply_step2_form_filled.png")
        
        # Step 4: Check for CAPTCHA
        logger.info("\n🤖 Checking for CAPTCHA...")
        captcha_found = False
        
        captcha_selectors = [
            ('iframe[src*="hcaptcha"]', 'hCaptcha'),
            ('iframe[src*="recaptcha"]', 'reCAPTCHA'),
            ('.cf-turnstile', 'Cloudflare Turnstile')
        ]
        
        for selector, name in captcha_selectors:
            count = await page.locator(selector).count()
            if count > 0:
                logger.warning(f"   ⚠️  {name} detected!")
                captcha_found = True
        
        if captcha_found:
            logger.info("\n⏸️  CAPTCHA detected - pausing for 60 seconds.")
            logger.info("   Please solve the CAPTCHA manually in the browser.")
            await asyncio.sleep(60)
        else:
            logger.info("   ✅ No CAPTCHA detected")
        
        # Step 5: Submit form
        logger.info("\n🖱️  Clicking login button...")
        if not login_button_selector:
            logger.error("\n❌ Login button not found - cannot submit form")
            logger.info("\n⏸️  Browser will stay open for 60 seconds for manual inspection...")
            await asyncio.sleep(60)
            return

        await page.locator(login_button_selector).first.click()
        
        # Wait for result
        logger.info("⏳ Waiting 10 seconds for login result...")
        await asyncio.sleep(10)
        
        # Check result
        final_url = page.url
        final_title = await page.title()
        
        await page.screenshot(path="logs/cointiply_step3_after_login.png")
        logger.info("📸 Screenshot: logs/cointiply_step3_after_login.png")
        
        logger.info(f"\n📋 After login:")
        logger.info(f"   URL: {final_url}")
        logger.info(f"   Title: {final_title}")
        
        if "dashboard" in final_url.lower() or "home" in final_url.lower():
            logger.info("\n✅ LOGIN SUCCESSFUL!")
            logger.info("   URL changed to dashboard/home")
            
            # Try to get balance
            logger.info("\n💰 Checking for balance...")
            balance_selectors = [
                ".user-balance-coins",
                ".user-balance",
                "[class*='balance']"
            ]
            
            for sel in balance_selectors:
                elem = page.locator(sel)
                if await elem.count() > 0:
                    try:
                        balance_text = await elem.first.text_content()
                        logger.info(f"   Balance ({sel}): {balance_text}")
                    except:
                        pass
        else:
            logger.warning(f"\n⚠️  Login may have failed - still on: {final_url}")
            
            # Check for error messages
            error_selectors = ['.error-message', '.alert-danger', '.text-danger', '[class*="error"]']
            for sel in error_selectors:
                elem = page.locator(sel)
                if await elem.count() > 0:
                    try:
                        error_text = await elem.first.text_content()
                        if error_text and error_text.strip():
                            logger.error(f"   ❌ Error message ({sel}): {error_text.strip()}")
                    except:
                        pass
        
        logger.info("\n⏸️  Browser will stay open for 30 seconds for inspection...")
        await asyncio.sleep(30)
        
        await context.close()
        await browser_manager.close()
        
        logger.info("\n✅ Test complete!")
        
    except Exception as e:
        logger.error(f"\n❌ Error during test: {e}", exc_info=True)
        logger.info("\n⏸️  Browser will stay open for 30 seconds...")
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(test_cointiply_direct())
