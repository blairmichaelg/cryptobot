"""
Analyze FireFaucet page to find correct claim interface.
Issue #86: Investigation of "0 buttons" problem on /faucet page.
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
from core.registry import get_faucet_class

async def analyze_firefaucet():
    """Navigate to FireFaucet and inspect available claim interfaces."""
    
    settings = BotSettings()
    browser_manager = BrowserManager(settings)
    
    try:
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
        
        # Try multiple endpoints
        endpoints = [
            "/",           # Dashboard
            "/faucet",     # Manual claim page
            "/start",      # Auto-faucet start
            "/claim",      # Direct claim
            "/auto",       # Auto page
        ]
        
        for endpoint in endpoints:
            try:
                print(f"\n=== Testing endpoint: {endpoint} ===")
                
                # Navigate
                full_url = f"https://firefaucet.win{endpoint}"
                print(f"Navigating to: {full_url}")
                await page.goto(full_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
                
                print(f"Final URL: {page.url}")
                
                # Count all interactive elements
                buttons = await page.query_selector_all('button')
                inputs_submit = await page.query_selector_all('input[type="submit"]')
                inputs_button = await page.query_selector_all('input[type="button"]')
                links_button = await page.query_selector_all('a.btn, a.button')
                
                print(f"Found elements:")
                print(f"  - <button> tags: {len(buttons)}")
                print(f"  - <input type='submit'>: {len(inputs_submit)}")
                print(f"  - <input type='button'>: {len(inputs_button)}")
                print(f"  - Links styled as buttons: {len(links_button)}")
                
                # Look for specific keywords
                keywords = ['claim', 'roll', 'faucet', 'submit', 'start', 'collect', 'get']
                for keyword in keywords:
                    elements = await page.query_selector_all(f'button:has-text("{keyword}"), input[value*="{keyword}" i], a:has-text("{keyword}")')
                    if elements:
                        print(f"  - Elements with '{keyword}': {len(elements)}")
                        for elem in elements[:3]:  # Show first 3
                            tag = await elem.evaluate('el => el.tagName')
                            text = await elem.text_content() or ""
                            value = await elem.get_attribute('value') or ""
                            print(f"    * <{tag}> text='{text.strip()}' value='{value}'")
                
                # Check for timer messages
                timer_selectors = [
                    'text=/wait/i',
                    'text=/available in/i', 
                    'text=/come back/i',
                    'text=/next claim/i',
                    '.timer',
                    '#timer',
                    '[data-timer]'
                ]
                
                print(f"\nTimer/cooldown messages:")
                for selector in timer_selectors:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            text = await elem.text_content()
                            print(f"  - Found: {text.strip()}")
                    except:
                        pass
                
                # Save screenshot
                screenshot_path = f"firefaucet_{endpoint.replace('/', '_') or 'root'}.png"
                await page.screenshot(path=screenshot_path)
                print(f"\n📸 Screenshot saved: {screenshot_path}")
                
                # Save HTML
                html = await page.content()
                html_path = f"firefaucet_{endpoint.replace('/', '_') or 'root'}.html"
                Path(html_path).write_text(html, encoding='utf-8')
                print(f"💾 HTML saved: {html_path}")
                
            except Exception as e:
                print(f"❌ Error on endpoint {endpoint}: {e}")
        
        print("\n=== Analysis Complete ===")
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(analyze_firefaucet())
