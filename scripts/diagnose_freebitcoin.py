"""
Quick diagnostic script for FreeBitcoin login issue (Task 1).
This script will connect to the live site and report what selectors are actually present.
"""
import asyncio
import logging
from pathlib import Path
import sys
import os

# Add parent to path
script_dir = Path(__file__).parent
repo_root = script_dir.parent
sys.path.insert(0, str(repo_root))

# Change to repo root for relative imports to work
os.chdir(repo_root)

from browser.instance import BrowserManager
from core.config import BotSettings
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def diagnose_freebitcoin():
    """Check FreeBitcoin site structure to identify correct selectors"""
    load_dotenv()
    
    logger.info("=" * 60)
    logger.info("FREEBITCOIN LOGIN DIAGNOSTIC (Task 1)")
    logger.info("=" * 60)
    
    browser = BrowserManager(headless=False)  # Visible for debugging
    await browser.launch()
    
    try:
        context = await browser.create_context(profile_name="freebitcoin_diagnostic")
        page = await browser.new_page(context)
        
        base_url = "https://freebitco.in"
        urls_to_check = [
            base_url,
            f"{base_url}/?op=login",
            f"{base_url}/signup-login/",
        ]
        
        for url in urls_to_check:
            logger.info(f"\n{'='*60}")
            logger.info(f"Checking URL: {url}")
            logger.info(f"{'='*60}")
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)  # Wait for any dynamic content
                
                logger.info(f"✅ Navigated to: {page.url}")
                
                # Check for login form elements
                email_selectors = [
                    "input[name='btc_address']",
                    "input#btc_address",
                    "input[type='email']",
                    "input[type='text']",
                    "input[placeholder*='email' i]",
                    "input[placeholder*='address' i]",
                ]
                
                password_selectors = [
                    "input[name='password']",
                    "input#password",
                    "input[type='password']",
                ]
                
                submit_selectors = [
                    "button[type='submit']",
                    "input[type='submit']",
                    "button:has-text('Login')",
                    "button:has-text('Log in')",
                    "button:has-text('Sign in')",
                ]
                
                logger.info("\n📧 Email/Username Field Check:")
                found_email = False
                for selector in email_selectors:
                    try:
                        elements = await page.locator(selector).all()
                        if elements:
                            for idx, el in enumerate(elements):
                                is_visible = await el.is_visible()
                                attrs = await el.evaluate("el => ({id: el.id, name: el.name, type: el.type, placeholder: el.placeholder})")
                                logger.info(f"  ✅ {selector}[{idx}]: visible={is_visible}, attrs={attrs}")
                                if is_visible:
                                    found_email = True
                    except Exception as e:
                        logger.debug(f"  ❌ {selector}: {e}")
                
                logger.info("\n🔒 Password Field Check:")
                found_password = False
                for selector in password_selectors:
                    try:
                        elements = await page.locator(selector).all()
                        if elements:
                            for idx, el in enumerate(elements):
                                is_visible = await el.is_visible()
                                attrs = await el.evaluate("el => ({id: el.id, name: el.name, type: el.type})")
                                logger.info(f"  ✅ {selector}[{idx}]: visible={is_visible}, attrs={attrs}")
                                if is_visible:
                                    found_password = True
                    except Exception as e:
                        logger.debug(f"  ❌ {selector}: {e}")
                
                logger.info("\n🔘 Submit Button Check:")
                found_submit = False
                for selector in submit_selectors:
                    try:
                        elements = await page.locator(selector).all()
                        if elements:
                            for idx, el in enumerate(elements):
                                is_visible = await el.is_visible()
                                text = await el.text_content() if is_visible else ""
                                logger.info(f"  ✅ {selector}[{idx}]: visible={is_visible}, text='{text}'")
                                if is_visible:
                                    found_submit = True
                    except Exception as e:
                        logger.debug(f"  ❌ {selector}: {e}")
                
                # Check for login triggers
                logger.info("\n🔗 Login Trigger Check:")
                login_triggers = [
                    "a[href*='login']",
                    "button:has-text('Login')",
                    "a:has-text('Login')",
                    "a:has-text('Sign in')",
                ]
                for selector in login_triggers:
                    try:
                        el = await page.locator(selector).first
                        if await el.is_visible(timeout=2000):
                            text = await el.text_content()
                            href = await el.get_attribute("href") or ""
                            logger.info(f"  ✅ {selector}: text='{text}', href='{href}'")
                    except Exception:
                        pass
                
                # Summary
                logger.info(f"\n{'='*60}")
                if found_email and found_password and found_submit:
                    logger.info(f"✅ {url}: Complete login form found!")
                    
                    # Take screenshot
                    screenshot_path = f"logs/freebitcoin_diagnostic_{url.split('/')[-1] or 'base'}.png"
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"📸 Screenshot saved: {screenshot_path}")
                    
                    break  # Found working page, stop checking
                elif found_email or found_password:
                    logger.warning(f"⚠️ {url}: Partial login form (email={found_email}, password={found_password}, submit={found_submit})")
                else:
                    logger.warning(f"❌ {url}: No login form elements found")
                
            except Exception as e:
                logger.error(f"Error checking {url}: {e}")
        
        logger.info(f"\n{'='*60}")
        logger.info("DIAGNOSTIC COMPLETE")
        logger.info("="*60)
        logger.info("\nNext steps:")
        logger.info("1. Review the output above for working selectors")
        logger.info("2. Check screenshots in logs/ directory")
        logger.info("3. Update freebitcoin.py with correct selectors")
        
    finally:
        await browser.close()

if __name__ == "__main__":
    asyncio.run(diagnose_freebitcoin())
