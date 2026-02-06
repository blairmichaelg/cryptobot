"""
Analyze FireFaucet page to find correct claim interface.
Issue #86: Investigation of "0 buttons" problem on /faucet page.

This diagnostic tool navigates to different FireFaucet endpoints and captures:
- Page content (HTML)
- Screenshots
- Interactive element counts
- Timer/cooldown messages
- CAPTCHA presence

Usage:
    python analyze_firefaucet_page.py

Requirements:
    - Valid FireFaucet credentials in .env file
    - HEADLESS=true for server environments
"""
import asyncio
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
from core.registry import get_faucet_class

async def analyze_firefaucet():
    """Navigate to FireFaucet and inspect available claim interfaces."""
    
    settings = BotSettings()
    browser_manager = BrowserManager(settings)
    
    # Create output directory for results
    output_dir = Path("firefaucet_analysis")
    output_dir.mkdir(exist_ok=True)
    
    try:
        # Launch browser first
        print("🚀 Launching browser...")
        await browser_manager.launch()
        
        # Create fresh context
        context = await browser_manager.create_context(profile_name=None)
        page = await context.new_page()
        
        # Get FireFaucet credentials
        firefaucet_class = get_faucet_class("firefaucet")
        bot = firefaucet_class(page, settings)
        
        print("\n=== STEP 1: Login to FireFaucet ===")
        login_result = await bot.login()
        print(f"Login result: {login_result}")
        
        if not login_result:
            print("❌ Login failed, stopping")
            return
        
        print("\n=== STEP 2: Check current URL ===")
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # Save post-login state
        print("\n📸 Saving post-login dashboard state...")
        await page.screenshot(path=output_dir / "00_post_login_dashboard.png")
        html = await page.content()
        (output_dir / "00_post_login_dashboard.html").write_text(html, encoding='utf-8')
        
        # Try multiple endpoints
        endpoints = [
            ("/", "Dashboard"),
            ("/faucet", "Manual claim page"),
            ("/start", "Auto-faucet start"),
            ("/claim", "Direct claim (if exists)"),
            ("/auto", "Auto page (if exists)"),
        ]
        
        for idx, (endpoint, description) in enumerate(endpoints, 1):
            try:
                print(f"\n{'='*60}")
                print(f"=== ENDPOINT {idx}: {endpoint} - {description} ===")
                print(f"{'='*60}")
                
                # Navigate
                full_url = f"https://firefaucet.win{endpoint}"
                print(f"🌐 Navigating to: {full_url}")
                await page.goto(full_url, wait_until='domcontentloaded', timeout=30000)
                
                # Wait for JavaScript to execute
                print("⏳ Waiting for dynamic content (5s)...")
                await asyncio.sleep(5)
                
                print(f"✅ Final URL: {page.url}")
                print(f"📄 Page title: {await page.title()}")
                
                # Count all interactive elements
                buttons = await page.query_selector_all('button')
                inputs_submit = await page.query_selector_all('input[type="submit"]')
                inputs_button = await page.query_selector_all('input[type="button"]')
                links_button = await page.query_selector_all('a.btn, a.button')
                all_links = await page.query_selector_all('a')
                
                print(f"\n📊 Interactive Elements:")
                print(f"  - <button> tags: {len(buttons)}")
                print(f"  - <input type='submit'>: {len(inputs_submit)}")
                print(f"  - <input type='button'>: {len(inputs_button)}")
                print(f"  - Links styled as buttons (.btn, .button): {len(links_button)}")
                print(f"  - All links: {len(all_links)}")
                
                # Check for CAPTCHA frames
                captcha_frames = await page.query_selector_all('iframe[src*="captcha"], iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"]')
                print(f"  - CAPTCHA iframes: {len(captcha_frames)}")
                
                # Look for specific keywords
                print(f"\n🔍 Keyword Analysis:")
                keywords = ['claim', 'roll', 'faucet', 'submit', 'start', 'collect', 'get', 'reward']
                for keyword in keywords:
                    # Try to find elements containing this keyword
                    try:
                        elements = await page.query_selector_all(
                            f'button:has-text("{keyword}"), '
                            f'input[value*="{keyword}" i], '
                            f'a:has-text("{keyword}")'
                        )
                        if elements:
                            print(f"  ✓ '{keyword}': {len(elements)} element(s)")
                            for elem in elements[:3]:  # Show first 3
                                try:
                                    tag = await elem.evaluate('el => el.tagName')
                                    text = await elem.text_content() or ""
                                    value = await elem.get_attribute('value') or ""
                                    id_attr = await elem.get_attribute('id') or ""
                                    class_attr = await elem.get_attribute('class') or ""
                                    print(f"      * <{tag}> id='{id_attr}' text='{text.strip()[:50]}' value='{value}'")
                                except:
                                    pass
                    except Exception as e:
                        pass
                
                # Check for timer messages
                print(f"\n⏱️  Timer/Cooldown Messages:")
                timer_selectors = [
                    'text=/wait/i',
                    'text=/available in/i', 
                    'text=/come back/i',
                    'text=/next claim/i',
                    'text=/minutes/i',
                    '.timer',
                    '#timer',
                    '[data-timer]',
                    '[id*="timer"]',
                    '[class*="countdown"]'
                ]
                
                found_timer = False
                for selector in timer_selectors:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            text = await elem.text_content()
                            if text and text.strip():
                                print(f"  ✓ {selector}: {text.strip()}")
                                found_timer = True
                    except:
                        pass
                
                if not found_timer:
                    print(f"  ✗ No timer messages found")
                
                # Check for error/alert messages
                print(f"\n⚠️  Alert/Error Messages:")
                alert_selectors = ['.alert', '.error', '.warning', '.toast', '[class*="alert"]', '[class*="error"]']
                found_alert = False
                for selector in alert_selectors:
                    try:
                        elems = await page.query_selector_all(selector)
                        for elem in elems:
                            text = await elem.text_content()
                            if text and text.strip():
                                print(f"  ⚠  {selector}: {text.strip()[:100]}")
                                found_alert = True
                    except:
                        pass
                
                if not found_alert:
                    print(f"  ✓ No alert messages")
                
                # Save screenshot and HTML
                safe_name = endpoint.replace('/', '_') or 'root'
                screenshot_path = output_dir / f"{idx:02d}_{safe_name}.png"
                html_path = output_dir / f"{idx:02d}_{safe_name}.html"
                
                await page.screenshot(path=screenshot_path, full_page=True)
                html = await page.content()
                html_path.write_text(html, encoding='utf-8')
                
                print(f"\n💾 Saved:")
                print(f"  📸 Screenshot: {screenshot_path}")
                print(f"  📄 HTML: {html_path}")
                
            except Exception as e:
                print(f"❌ Error on endpoint {endpoint}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*60}")
        print("=== Analysis Complete ===")
        print(f"{'='*60}")
        print(f"\n📁 All results saved to: {output_dir.absolute()}")
        print(f"\nNext steps:")
        print(f"  1. Review screenshots to identify the correct claim interface")
        print(f"  2. Examine HTML files for button/form selectors")
        print(f"  3. Update faucets/firefaucet.py with correct endpoint and selectors")
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(analyze_firefaucet())
