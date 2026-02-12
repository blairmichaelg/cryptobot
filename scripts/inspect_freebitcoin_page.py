#!/usr/bin/env python3
"""
Script to inspect FreeBitcoin page structure and find correct selectors.
Run: HEADLESS=false python3 scripts/inspect_freebitcoin_page.py
"""
import asyncio
from pathlib import Path
import sys
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


async def inspect_page():
    """Login to FreeBitcoin and inspect page structure."""
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0'
        )
        page = await context.new_page()
        
        print("[+] Navigating to FreeBitcoin...")
        await page.goto('https://freebitco.in/', wait_until='domcontentloaded')
        await asyncio.sleep(5)
        
        print("\n[+] Extracting page structure...")
        
        # Check for balance element
        balance_js = await page.evaluate("""
            () => {
                const balance = document.querySelector('#balance');
                if (!balance) return null;
                return {
                    text: balance.textContent?.trim(),
                    html: balance.outerHTML,
                    visible: balance.offsetParent !== null
                };
            }
        """)
        print(f"\n[BALANCE] {balance_js}")
        
        # Check for timer element
        timer_js = await page.evaluate("""
            () => {
                const timer = document.querySelector('#time_remaining');
                if (!timer) return {found: false};
                return {
                    found: true,
                    text: timer.textContent?.trim(),
                    html: timer.outerHTML,
                    visible: timer.offsetParent !== null,
                    parent: timer.parentElement?.outerHTML
                };
            }
        """)
        print(f"\n[TIMER #time_remaining] {timer_js}")
        
        # Check for ROLL button
        roll_js = await page.evaluate("""
            () => {
                const btn = document.querySelector('#free_play_form_button');
                if (!btn) return {found: false};
                return {
                    found: true,
                    type: btn.type,
                    value: btn.value,
                    disabled: btn.disabled,
                    html: btn.outerHTML,
                    visible: btn.offsetParent !== null
                };
            }
        """)
        print(f"\n[ROLL BUTTON] {roll_js}")
        
        # Check for result/winnings element
        winnings_js = await page.evaluate("""
            () => {
                const win = document.querySelector('#winnings');
                if (!win) return {found: false};
                return {
                    found: true,
                    text: win.textContent?.trim(),
                    html: win.outerHTML,
                    visible: win.offsetParent !== null
                };
            }
        """)
        print(f"\n[WINNINGS] {winnings_js}")
        
        # Take screenshot
        screenshot_path = Path("claims") / f"freebitcoin_inspect_{int(datetime.now().timestamp())}.png"
        screenshot_path.parent.mkdir(exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\n[+] Screenshot saved: {screenshot_path}")
        
        print("\n[+] Press Enter to close browser...")
        input()
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect_page())
