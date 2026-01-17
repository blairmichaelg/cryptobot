import asyncio
import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)

class ShortlinkSolver:
    """
    Generic solver for crypto shortlinks.
    
    This solver handles the complex multi-step process of traversing crypto shortlinks,
    which typically involve:
    1. Waiting for countdown timers (10-30 seconds)
    2. Solving captchas (Turnstile, hCaptcha, reCaptcha)
    3. Clicking through multiple "Continue", "Get Link", or "Next" buttons
    4. Handling popup windows and redirects
    5. Detecting when the final destination is reached
    
    The solver uses standardized DataExtractor methods for timer parsing and implements
    heuristics to avoid clicking on ad elements or decoy buttons.
    
    Args:
        page: The Playwright Page instance to control
        blocker: Optional resource blocker (disabled during shortlink traversal to avoid detection)
        captcha_solver: Optional CaptchaSolver instance for handling captchas
        
    Example:
        >>> solver = ShortlinkSolver(page, blocker=blocker, captcha_solver=captcha)
        >>> success = await solver.solve("https://shortlink.example.com/abc123")
    """
    def __init__(self, page: Page, blocker=None, captcha_solver=None):
        self.page = page
        self.blocker = blocker
        self.captcha_solver = captcha_solver
        
    async def solve(self, url: str) -> bool:
        try:
            logger.info(f"🔗 Starting Shortlink: {url}")
            
            # Disable blocker if present to avoid adblock detection
            if self.blocker:
                logger.info("🔓 Disabling Resource Blocker for Shortlink...")
                self.blocker.enabled = False
                
            await self.page.goto(url)
            
            # Attempt generic traverse loop
            for step in range(12): # Increased steps for complex links
                # 1. Check for common 'Success' indicators
                if any(x in self.page.url for x in ["dutchycorp.space/shortlinks-wall.php", "firefaucet.win/shortlinks"]):
                    logger.info("✅ Returned to Shortlinks Wall!")
                    return True
                
                # 2. Wait for Timer
                # Use standardized extraction logic
                try:
                    timer_selectors = ["#timer", ".timer", "#countdown", "div[id*='time']", "span[id*='time']", ".timer-text"]
                    timer_found = False
                    for sel in timer_selectors:
                        # We use the page object since we don't have a FaucetBot instance easily here,
                        # or we can just import the logic.
                        timer_el = self.page.locator(sel)
                        if await timer_el.count() > 0 and await timer_el.first.is_visible():
                            text = await timer_el.first.text_content()
                            from core.extractor import DataExtractor
                            wait_min = DataExtractor.parse_timer_to_minutes(text)
                            if wait_min > 0:
                                wait_s = min(wait_min * 60, 45)  # Wait up to 45s
                                logger.info(f"⏳ Timer found ({text}), waiting {wait_s:.1f}s...")
                                await asyncio.sleep(wait_s)
                                timer_found = True
                                break
                    if not timer_found:
                        logger.debug(f"No timer found on step {step}, continuing...")
                        await asyncio.sleep(2)
                except Exception as e:
                    logger.debug(f"Timer detection error: {e}")

                # 3. Check for Captcha
                if self.captcha_solver and await self.page.query_selector("iframe[src*='recaptcha'], iframe[src*='turnstile'], iframe[src*='hcaptcha'], .cf-turnstile"):
                    logger.info("🧩 Captcha detected in shortlink. Attempting to solve...")
                    await self.captcha_solver.solve_captcha(self.page)
                    await asyncio.sleep(3)

                # 4. Click 'Next' / 'Get Link'
                # Common patterns with priorities, avoiding obvious ads
                buttons = [
                    "button:has-text('Get Link')",
                    "a:has-text('Get Link')",
                    "button:has-text('Continue')",
                    "a:has-text('Continue')",
                    "button:has-text('Next')",
                    "a:has-text('Next')",
                    "button:has-text('Verify')",
                    "a:id('go-link')", # Specific common id
                    ".btn-success",
                    "#submit-button",
                    ".next-button"
                ]
                
                clicked = False
                for sel in buttons:
                    try:
                        targets = self.page.locator(sel)
                        count = await targets.count()
                        for i in range(count):
                            target = targets.nth(i)
                            if await target.is_visible() and await target.is_enabled():
                                # Heuristic: Ignore suspicious small boxes or hidden elements
                                box = await target.bounding_box()
                                if box and (box['width'] < 10 or box['height'] < 10):
                                    continue
                                    
                                logger.info(f"👆 Clicking {sel} (instance {i})...")
                                
                                # Standard click with popup removal
                                try:
                                    async with self.page.context.expect_page(timeout=4000) as new_page_info:
                                        await target.click(timeout=3000)
                                    p = await new_page_info.value
                                    logger.info("🗑️ Closing popup window.")
                                    await p.close()
                                except Exception:
                                    # No popup or timed out, assume click worked
                                    await target.click(timeout=3000, force=True)
                                
                                clicked = True
                                await asyncio.sleep(4)
                                break
                        if clicked:
                            break
                    except Exception:
                        continue
                
                if not clicked:
                    await asyncio.sleep(2)
                    # Check if we moved anyway
                    if any(x in self.page.url for x in ["dutchycorp.space", "firefaucet.win"]):
                        continue

            return False
            
        except Exception as e:
            logger.error(f"Shortlink Failed: {e}")
            return False
        finally:
            if self.blocker:
                logger.info("🔒 Re-enabling Resource Blocker...")
                self.blocker.enabled = True
