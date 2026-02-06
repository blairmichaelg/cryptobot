#!/usr/bin/env python3
"""Check if firefaucet page contains 'cloudflare' text"""
import asyncio
from browser.instance import BrowserManager

async def check():
    mgr = BrowserManager(headless=True)
    await mgr.launch()
    ctx = await mgr.create_context()
    page = await mgr.new_page(context=ctx)
    
    print("Navigating to firefaucet.win/faucet...")
    await page.goto('https://firefaucet.win/faucet', wait_until="domcontentloaded")
    await asyncio.sleep(5)
    
    # Get page text
    body_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
    
    # Check for cloudflare patterns
    patterns = ["cloudflare", "checking your browser", "just a moment", "ray id"]
    
    print(f"\n Page text length: {len(body_text)} chars")
    print("\nChecking for patterns:")
    for pattern in patterns:
        found = pattern in body_text
        print(f"  '{pattern}': {found}")
        if found:
            # Find context
            idx = body_text.find(pattern)
            context = body_text[max(0, idx-50):min(len(body_text), idx+50)]
            print(f"    Context: ...{context}...")
    
    # Check page title
    title = await page.title()
    print(f"\nPage title: {title}")
    
    # Check for actual Cloudflare challenge elements
    print("\nChecking for Cloudflare challenge elements:")
    turnstile = await page.query_selector("iframe[src*='turnstile']")
    print(f"  Turnstile iframe: {turnstile is not None}")
    
    cf_challenge = await page.query_selector("#cf-challenge-running")
    print(f"  CF challenge element: {cf_challenge is not None}")
    
    await mgr.close()

asyncio.run(check())
