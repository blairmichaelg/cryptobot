"""
Diagnostic script to capture state of failing faucets after CAPTCHA solve.
Saves screenshots and HTML to understand selector issues.
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def diagnose_faucet(faucet_name: str):
    """Diagnose a single faucet by capturing state after CAPTCHA solve."""
    from browser.instance import BrowserManager
    from solvers.captcha import CaptchaSolver
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Diagnosing {faucet_name}")
    logger.info(f"{'='*60}")
    
    try:
        # Import the faucet class
        if faucet_name == "FreeBitcoin":
            from faucets.freebitcoin import FreeBitcoinBot
            FaucetClass = FreeBitcoinBot
            profile = "blazefoley97@gmail.com"
        elif faucet_name == "Cointiply":
            from faucets.cointiply import CointiplyBot
            FaucetClass = CointiplyBot
            profile = "blazefoley97@gmail.com"
        elif faucet_name == "TronPick":
            from faucets.tronpick import TronPickBot
            FaucetClass = TronPickBot
            profile = "blazefoley97"
        elif faucet_name == "FaucetCrypto":
            from faucets.faucetcrypto import FaucetCryptoBot
            FaucetClass = FaucetCryptoBot
            profile = "blazefoley97@gmail.com"
        else:
            logger.error(f"Unknown faucet: {faucet_name}")
            return
        
        # Launch browser with proxy
        session_id = "diagtest"
        proxy_url = f"http://ub033d0d0583c05dd-zone-custom-session-{session_id}:ub033d0d0583c05dd@43.135.141.142:2334"
        
        manager = BrowserManager()
        await manager.launch()
        
        context = await manager.create_context(
            profile_name=profile,
            proxy=proxy_url,
            allow_sticky_proxy=False
        )
        page = await context.new_page()
        
        # Create faucet instance
        faucet = FaucetClass()
        faucet.page = page
        faucet.manager = manager
        faucet.solver = CaptchaSolver()
        
        # Navigate to faucet
        logger.info(f"Navigating to {faucet.base_url}...")
        await page.goto(faucet.base_url, wait_until="load", timeout=20000)
        await asyncio.sleep(3)
        
        # Close any popups
        if hasattr(faucet, 'close_popups'):
            try:
                await faucet.close_popups()
            except:
                pass
        
        # Take screenshot before CAPTCHA
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_dir = Path("diagnostic_screenshots")
        screenshot_dir.mkdir(exist_ok=True)
        
        await page.screenshot(path=screenshot_dir / f"{faucet_name}_{timestamp}_before.png", full_page=True)
        logger.info(f"Screenshot saved: {faucet_name}_{timestamp}_before.png")
        
        # Save HTML before
        html_before = await page.content()
        with open(screenshot_dir / f"{faucet_name}_{timestamp}_before.html", "w", encoding="utf-8") as f:
            f.write(html_before)
        
        # Look for CAPTCHA and solve it
        logger.info("Looking for CAPTCHA...")
        try:
            await faucet.solver.solve_captcha(page, timeout=90)
            logger.info("✅ CAPTCHA solved!")
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"CAPTCHA solve issue: {e}")
        
        # Take screenshot after CAPTCHA
        await page.screenshot(path=screenshot_dir / f"{faucet_name}_{timestamp}_after.png", full_page=True)
        logger.info(f"Screenshot saved: {faucet_name}_{timestamp}_after.png")
        
        # Save HTML after
        html_after = await page.content()
        with open(screenshot_dir / f"{faucet_name}_{timestamp}_after.html", "w", encoding="utf-8") as f:
            f.write(html_after)
        
        # Try to find all buttons
        logger.info("\nSearching for buttons...")
        all_buttons = await page.query_selector_all("button")
        logger.info(f"Found {len(all_buttons)} total buttons")
        
        for i, btn in enumerate(all_buttons[:20]):  # First 20 buttons
            try:
                text = await btn.text_content()
                is_visible = await btn.is_visible()
                is_disabled = await btn.is_disabled()
                classes = await btn.get_attribute("class") or ""
                btn_id = await btn.get_attribute("id") or ""
                btn_type = await btn.get_attribute("type") or ""
                
                logger.info(
                    f"  Button {i+1}: text='{text[:50] if text else ''}' "
                    f"visible={is_visible} disabled={is_disabled} "
                    f"id='{btn_id}' class='{classes}' type='{btn_type}'"
                )
            except:
                pass
        
        # Faucet-specific checks
        if faucet_name == "FreeBitcoin":
            logger.info("\nFreeBitcoin-specific checks:")
            roll_btn = page.locator("#free_play_form_button")
            count = await roll_btn.count()
            logger.info(f"  #free_play_form_button count: {count}")
            if count > 0:
                is_visible = await roll_btn.first.is_visible()
                is_disabled = await roll_btn.first.is_disabled()
                logger.info(f"  #free_play_form_button visible={is_visible} disabled={is_disabled}")
        
        elif faucet_name == "Cointiply":
            logger.info("\nCointiply-specific checks:")
            # Check for various roll button selectors
            selectors = [
                "button.faucet-roll",
                "button#roll-button", 
                "button:has-text('Roll')",
                ".roll-button",
                "button[onclick*='roll']"
            ]
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    count = await loc.count()
                    if count > 0:
                        is_visible = await loc.first.is_visible()
                        logger.info(f"  {sel}: count={count} visible={is_visible}")
                except Exception as e:
                    logger.info(f"  {sel}: error - {e}")
        
        elif faucet_name == "TronPick":
            logger.info("\nTronPick-specific checks:")
            # Check for claim button
            selectors = [
                "button:has-text('Claim')",
                "button.claim-button",
                "button[type='submit']",
                ".faucet-claim",
                "button:has-text('Get')"
            ]
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    count = await loc.count()
                    if count > 0:
                        is_visible = await loc.first.is_visible()
                        is_disabled = await loc.first.is_disabled()
                        logger.info(f"  {sel}: count={count} visible={is_visible} disabled={is_disabled}")
                except Exception as e:
                    logger.info(f"  {sel}: error - {e}")
        
        # Keep page open for manual inspection if needed
        logger.info(f"\n✅ Diagnosis complete for {faucet_name}")
        logger.info(f"Files saved in diagnostic_screenshots/")
        
        await manager.close()
        
    except Exception as e:
        logger.error(f"Diagnosis failed for {faucet_name}: {e}", exc_info=True)
        try:
            await manager.close()
        except:
            pass

async def main():
    """Run diagnostics on all failing faucets."""
    failing_faucets = [
        "FreeBitcoin",
        "Cointiply", 
        "TronPick",
        # "FaucetCrypto",  # Skip - just proxy timeouts
    ]
    
    for faucet in failing_faucets:
        await diagnose_faucet(faucet)
        await asyncio.sleep(5)  # Brief pause between faucets

if __name__ == "__main__":
    asyncio.run(main())
