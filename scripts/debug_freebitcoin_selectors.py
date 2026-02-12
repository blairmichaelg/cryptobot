#!/usr/bin/env python3
"""
Debug script to find correct FreeBitcoin selectors.
Logs into account and dumps actual page structure.
"""
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

async def debug_selectors():
    """Login and inspect FreeBitcoin page structure."""
    async with async_playwright() as p:
        browser = await p.firefox.launch(
            headless=True,
            args=['--no-sandbox']
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0'
        )
        
        page = await context.new_page()
        
        print("\n[1] Navigating to FreeBitcoin...")
        await page.goto('https://freebitco.in/', wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(5)
        
        print("\n[2] Checking login state...")
        # Check if already logged in
        is_logged_in = await page.evaluate("""
            () => {
                const balance = document.querySelector('#balance');
                const rollBtn = document.querySelector('#free_play_form_button');
                return !!(balance || rollBtn);
            }
        """)
        
        if not is_logged_in:
            print("[2] Not logged in, attempting login...")
            email = os.getenv('FREEBITCOIN_USERNAME')
            password = os.getenv('FREEBITCOIN_PASSWORD')
            
            if not email or not password:
                print("ERROR: FREEBITCOIN_USERNAME and FREEBITCOIN_PASSWORD must be set in .env")
                await browser.close()
                return
            
            # Try to find and fill login form
            try:
                await page.fill('input[name="btc_address"]', email)
                await page.fill('input[name="password"]', password)
                await page.click('input[type="submit"]')
                await asyncio.sleep(5)
                print("[2] Login attempted")
            except Exception as e:
                print(f"[2] Login failed: {e}")
        else:
            print("[2] Already logged in!")
        
        print("\n[3] Extracting page structure...")
        
        # Get comprehensive element info
        elements_info = await page.evaluate("""
            () => {
                const info = {
                    url: window.location.href,
                    title: document.title,
                    elements: {}
                };
                
                // Check balance element
                const balance = document.querySelector('#balance');
                info.elements.balance = balance ? {
                    exists: true,
                    text: balance.textContent?.trim(),
                    visible: balance.offsetParent !== null,
                    html: balance.outerHTML
                } : {exists: false};
                
                // Check timer element
                const timer = document.querySelector('#time_remaining');
                info.elements.time_remaining = timer ? {
                    exists: true,
                    text: timer.textContent?.trim(),
                    visible: timer.offsetParent !== null,
                    html: timer.outerHTML,
                    parentHTML: timer.parentElement?.outerHTML?.substring(0, 500)
                } : {exists: false};
                
                // Check roll button
                const rollBtn = document.querySelector('#free_play_form_button');
                info.elements.roll_button = rollBtn ? {
                    exists: true,
                    type: rollBtn.type,
                    value: rollBtn.value,
                    disabled: rollBtn.disabled,
                    visible: rollBtn.offsetParent !== null,
                    html: rollBtn.outerHTML
                } : {exists: false};
                
                // Search for any countdown-related elements
                const countdowns = [];
                document.querySelectorAll('[class*="countdown"], [id*="countdown"], [class*="timer"], [id*="timer"]').forEach(el => {
                    countdowns.push({
                        tag: el.tagName,
                        id: el.id,
                        classes: el.className,
                        text: el.textContent?.trim()?.substring(0, 100),
                        visible: el.offsetParent !== null
                    });
                });
                info.elements.countdown_elements = countdowns;
                
                // Get all form elements
                const forms = [];
                document.querySelectorAll('form').forEach(form => {
                    forms.push({
                        id: form.id,
                        action: form.action,
                        inputs: Array.from(form.querySelectorAll('input')).map(inp => ({
                            name: inp.name,
                            type: inp.type,
                            id: inp.id,
                            value: inp.value?.substring(0, 50),
                            disabled: inp.disabled
                        }))
                    });
                });
                info.forms = forms;
                
                return info;
            }
        """)
        
        print("\n" + "="*80)
        print("PAGE STRUCTURE ANALYSIS")
        print("="*80)
        print(f"\nURL: {elements_info['url']}")
        print(f"Title: {elements_info['title']}")
        
        print("\n--- BALANCE ELEMENT (#balance) ---")
        if elements_info['elements']['balance']['exists']:
            bal = elements_info['elements']['balance']
            print(f"  Text: {bal['text']}")
            print(f"  Visible: {bal['visible']}")
            print(f"  HTML: {bal['html']}")
        else:
            print("  NOT FOUND")
        
        print("\n--- TIMER ELEMENT (#time_remaining) ---")
        if elements_info['elements']['time_remaining']['exists']:
            timer = elements_info['elements']['time_remaining']
            print(f"  Text: {timer['text']}")
            print(f"  Visible: {timer['visible']}")
            print(f"  HTML: {timer['html']}")
            print(f"  Parent: {timer.get('parentHTML', 'N/A')}")
        else:
            print("  NOT FOUND")
        
        print("\n--- ROLL BUTTON (#free_play_form_button) ---")
        if elements_info['elements']['roll_button']['exists']:
            btn = elements_info['elements']['roll_button']
            print(f"  Type: {btn['type']}")
            print(f"  Value: {btn['value']}")
            print(f"  Disabled: {btn['disabled']}")
            print(f"  Visible: {btn['visible']}")
            print(f"  HTML: {btn['html']}")
        else:
            print("  NOT FOUND")
        
        print("\n--- COUNTDOWN/TIMER ELEMENTS ---")
        if elements_info['elements']['countdown_elements']:
            for i, el in enumerate(elements_info['elements']['countdown_elements'], 1):
                print(f"\n  Element {i}:")
                print(f"    Tag: {el['tag']}")
                print(f"    ID: {el['id']}")
                print(f"    Classes: {el['classes']}")
                print(f"    Text: {el['text']}")
                print(f"    Visible: {el['visible']}")
        else:
            print("  NONE FOUND")
        
        print("\n--- FORMS ---")
        for i, form in enumerate(elements_info.get('forms', []), 1):
            print(f"\n  Form {i}:")
            print(f"    ID: {form['id']}")
            print(f"    Action: {form['action']}")
            print(f"    Inputs: {len(form['inputs'])}")
            for inp in form['inputs'][:5]:  # Show first 5 inputs
                print(f"      - {inp['type']}: {inp['name']} (id={inp['id']}, disabled={inp['disabled']})")
        
        # Take screenshot
        print("\n[4] Taking screenshot...")
        screenshot_path = Path('debug_freebitcoin.png')
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"    Saved: {screenshot_path.absolute()}")
        
        # Save HTML
        print("\n[5] Saving HTML...")
        html_content = await page.content()
        html_path = Path('debug_freebitcoin.html')
        html_path.write_text(html_content, encoding='utf-8')
        print(f"    Saved: {html_path.absolute()}")
        
        await browser.close()
        
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        print("\nFiles created:")
        print(f"  - {screenshot_path.absolute()}")
        print(f"  - {html_path.absolute()}")
        print("\nReview these files to find correct selectors!")


if __name__ == "__main__":
    asyncio.run(debug_selectors())
