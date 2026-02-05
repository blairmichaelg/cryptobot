"""
Diagnostic script to inspect FreeBitcoin.in login page structure and find correct selectors.
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
import json


async def main():
    print("\n" + "="*80)
    print("FREEBITCOIN LOGIN PAGE DIAGNOSTIC")
    print("="*80)
    
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    browser_mgr = BrowserManager(
        headless=headless,
        block_images=False,  # Don't block images for diagnostic
        block_media=False,
        timeout=120000
    )
    
    try:
        print("\n🌐 Launching browser...")
        await browser_mgr.launch()
        
        context = await browser_mgr.create_context(
            proxy=None,
            user_agent=None,
            profile_name="freebitcoin_diagnostic"
        )
        page = await browser_mgr.new_page(context=context)
        
        # Navigate to FreeBitcoin
        url = "https://freebitco.in"
        print(f"\n📍 Navigating to {url}...")
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"❌ Navigation failed: {e}")
            return
        
        # Wait for page to load
        await asyncio.sleep(5)
        
        current_url = page.url
        title = await page.title()
        print(f"✅ Current URL: {current_url}")
        print(f"✅ Page title: {title}")
        
        # Check for login trigger
        print("\n🔍 Checking for login triggers...")
        login_triggers = await page.evaluate("""
            () => {
                const selectors = [
                    'a:has-text("LOGIN")',
                    'a:has-text("Log In")',
                    'button:has-text("LOGIN")',
                    '[href*="login"]',
                    '.login-link',
                    '#login_link'
                ];
                
                const found = [];
                for (const sel of selectors) {
                    try {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) {
                            Array.from(els).forEach(el => {
                                found.push({
                                    selector: sel,
                                    tag: el.tagName,
                                    text: el.textContent.trim().substring(0, 50),
                                    href: el.href || null,
                                    visible: el.offsetParent !== null
                                });
                            });
                        }
                    } catch (e) {}
                }
                return found;
            }
        """)
        
        if login_triggers:
            print(f"Found {len(login_triggers)} login triggers:")
            for trigger in login_triggers:
                print(f"  - {trigger}")
        else:
            print("❌ No login triggers found")
        
        # Try to find and click login trigger
        print("\n🖱️  Attempting to click login trigger...")
        clicked = False
        for selector in ['a:has-text("LOGIN")', 'a:has-text("Log In")', '[href*="login"]']:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=3000):
                    await locator.click()
                    await asyncio.sleep(3)
                    clicked = True
                    print(f"✅ Clicked: {selector}")
                    break
            except Exception:
                continue
        
        if not clicked:
            print("⚠️  No login trigger clicked - checking if form is already visible...")
        
        # Check for input fields
        print("\n🔍 Checking for input fields...")
        inputs = await page.evaluate("""
            () => {
                const inputs = Array.from(document.querySelectorAll('input'));
                return inputs.map(el => ({
                    type: el.type,
                    name: el.name || null,
                    id: el.id || null,
                    placeholder: el.placeholder || null,
                    className: el.className || null,
                    visible: el.offsetParent !== null,
                    value: el.value ? '***hidden***' : '',
                    formAction: el.form ? el.form.action : null
                })).slice(0, 20);
            }
        """)
        
        print(f"Found {len(inputs)} input fields:")
        for inp in inputs:
            visible_mark = "✅" if inp['visible'] else "❌"
            print(f"  {visible_mark} type={inp['type']}, name={inp['name']}, id={inp['id']}, placeholder={inp['placeholder']}")
        
        # Check for specific login fields
        print("\n🔍 Checking for specific login field IDs...")
        login_fields = await page.evaluate("""
            () => {
                const selectors = [
                    '#login_form_btc_address',
                    '#login_form_password',
                    'input[name="btc_address"]',
                    'input[name="password"]',
                    '#email',
                    '#password',
                    '#login_button'
                ];
                
                const found = {};
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        found[sel] = {
                            exists: true,
                            visible: el.offsetParent !== null,
                            type: el.type || el.tagName,
                            name: el.name || null,
                            id: el.id || null
                        };
                    }
                }
                return found;
            }
        """)
        
        if login_fields:
            print("Found login fields:")
            for selector, info in login_fields.items():
                visible_mark = "✅" if info['visible'] else "❌ (hidden)"
                print(f"  {visible_mark} {selector}: {info}")
        else:
            print("❌ No known login fields found")
        
        # Check for captchas
        print("\n🔍 Checking for CAPTCHA elements...")
        captchas = await page.evaluate("""
            () => {
                const selectors = [
                    'iframe[src*="turnstile"]',
                    '.cf-turnstile',
                    'iframe[src*="hcaptcha"]',
                    'iframe[src*="recaptcha"]',
                    '.h-captcha',
                    '.g-recaptcha'
                ];
                
                const found = [];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        found.push({
                            selector: sel,
                            count: els.length,
                            visible: Array.from(els).some(el => el.offsetParent !== null)
                        });
                    }
                }
                return found;
            }
        """)
        
        if captchas:
            print(f"Found {len(captchas)} CAPTCHA types:")
            for cap in captchas:
                print(f"  - {cap}")
        else:
            print("No CAPTCHAs detected")
        
        # Take screenshot
        screenshot_path = "logs/freebitcoin_diagnostic.png"
        try:
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n📸 Screenshot saved: {screenshot_path}")
        except Exception as e:
            print(f"⚠️  Screenshot failed: {e}")
        
        # Save HTML
        html_path = "logs/freebitcoin_diagnostic.html"
        try:
            html = await page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"💾 HTML saved: {html_path}")
        except Exception as e:
            print(f"⚠️  HTML save failed: {e}")
        
        print("\n" + "="*80)
        print("✅ Diagnostic complete")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await browser_mgr.close()
        except Exception as e:
            print(f"Cleanup error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
