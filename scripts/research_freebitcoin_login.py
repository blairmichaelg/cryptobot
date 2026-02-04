#!/usr/bin/env python3
"""
Research FreeBitcoin login endpoint by manual inspection.
Find the actual login URL that works without signup redirect.
"""

import asyncio
import os
import sys
from pathlib import Path

os.environ['HEADLESS'] = 'false'

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from core.config import BotSettings

async def research_login_endpoint():
    """Research FreeBitcoin login endpoint."""
    
    print("\n" + "="*70)
    print("FREEBITCOIN LOGIN ENDPOINT RESEARCH")
    print("="*70)
    
    settings = BotSettings()
    username = settings.freebitcoin_username
    password = settings.freebitcoin_password
    
    if not username or not password:
        print("❌ No FreeBitcoin credentials configured")
        return
    
    urls_to_test = [
        ("https://freebitco.in", "Homepage"),
        ("https://freebitco.in/?op=home", "Home with op=home"),
        ("https://freebitco.in/?op=login", "Direct login op"),
        ("https://freebitco.in/login", "Login path"),
        ("https://freebitco.in/signin", "Signin path"),
        ("https://freebitco.in/signup/?op=home", "Signup with home"),
        ("https://freebitco.in/#login", "Homepage with #login"),
    ]
    
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        results = []
        
        for url, description in urls_to_test:
            print(f"\n{'='*70}")
            print(f"Testing: {description}")
            print(f"URL: {url}")
            print("="*70)
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                
                final_url = page.url
                print(f"Final URL: {final_url}")
                
                # Check for login form
                has_login = False
                login_indicators = [
                    'input[name="btc_address"]',
                    'input[name="password"]',
                    '#login_form',
                    '#login_button',
                ]
                
                for selector in login_indicators:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            visible = await element.is_visible()
                            if visible:
                                has_login = True
                                print(f"✅ Found login element: {selector}")
                                break
                    except:
                        pass
                
                # Check for signup indicators
                is_signup = False
                if '/signup' in final_url:
                    is_signup = True
                    print("⚠️  Redirected to signup page")
                
                # Check for CAPTCHA
                has_captcha = False
                try:
                    captcha_check = await page.evaluate("""
                        () => {
                            const selectors = [
                                'iframe[src*="turnstile"]',
                                'iframe[src*="hcaptcha"]',
                                'iframe[src*="recaptcha"]',
                                '.cf-turnstile',
                                '#int_page_captchas'
                            ];
                            for (const sel of selectors) {
                                if (document.querySelector(sel)) return true;
                            }
                            return false;
                        }
                    """)
                    has_captcha = captcha_check
                    if has_captcha:
                        print("🔒 CAPTCHA detected on page")
                except:
                    pass
                
                result = {
                    'url': url,
                    'description': description,
                    'final_url': final_url,
                    'has_login_form': has_login,
                    'is_signup_page': is_signup,
                    'has_captcha': has_captcha,
                    'redirected': url != final_url
                }
                results.append(result)
                
                if has_login:
                    print("✅ This URL shows login form")
                else:
                    print("❌ No login form visible")
                
                await asyncio.sleep(2)
                
            except Exception as e:
                print(f"❌ Error testing URL: {e}")
                results.append({
                    'url': url,
                    'description': description,
                    'error': str(e)
                })
        
        # Summary
        print("\n" + "="*70)
        print("RESEARCH SUMMARY")
        print("="*70)
        
        working_urls = [r for r in results if r.get('has_login_form')]
        captcha_urls = [r for r in results if r.get('has_captcha')]
        signup_redirects = [r for r in results if r.get('is_signup_page')]
        
        print(f"\n✅ URLs with login form ({len(working_urls)}):")
        for r in working_urls:
            print(f"   - {r['description']}: {r['url']}")
            if r.get('has_captcha'):
                print(f"     (Has CAPTCHA)")
        
        print(f"\n🔒 URLs with CAPTCHA ({len(captcha_urls)}):")
        for r in captcha_urls:
            print(f"   - {r['description']}")
        
        print(f"\n⚠️  URLs redirecting to signup ({len(signup_redirects)}):")
        for r in signup_redirects:
            print(f"   - {r['description']} -> {r['final_url']}")
        
        print("\n" + "="*70)
        print("RECOMMENDATION:")
        if working_urls:
            best_url = working_urls[0]
            print(f"✅ Use: {best_url['url']}")
            print(f"   Description: {best_url['description']}")
            if best_url.get('has_captcha'):
                print(f"   ⚠️  CAPTCHA must be solved BEFORE login form access")
        else:
            print("❌ No working login URLs found - manual inspection needed")
        
        print("\n⏸️  Browser kept open for manual inspection (60s)...")
        await asyncio.sleep(60)
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(research_login_endpoint())
