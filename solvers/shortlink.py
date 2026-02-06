"""Generic shortlink traversal solver for Cryptobot Gen 3.0.

Many crypto faucets offer bonus earnings for completing shortlinks -- URLs
that pass through multiple intermediate pages with countdown timers,
CAPTCHAs, and redirect chains before arriving at a destination URL.

:class:`ShortlinkSolver` automates this multi-step process:
    1. Navigate to the shortlink URL.
    2. Wait for countdown timers (10--30 s typically).
    3. Solve any CAPTCHAs (Turnstile, hCaptcha, reCAPTCHA).
    4. Click through ``Continue`` / ``Get Link`` / ``Next`` buttons.
    5. Handle popups and redirects.
    6. Detect when the final destination (success URL) is reached.

The resource blocker is temporarily disabled during shortlink traversal
to avoid triggering adblock detection on intermediate pages.
"""

import asyncio
import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ShortlinkSolver:
    """Automated solver for multi-step crypto shortlinks.

    Args:
        page: Playwright ``Page`` instance to drive.
        blocker: Optional :class:`ResourceBlocker` -- disabled during traversal.
        captcha_solver: Optional :class:`CaptchaSolver` for embedded CAPTCHAs.

    Example::

        solver = ShortlinkSolver(page, blocker=blocker, captcha_solver=captcha)
        success = await solver.solve("https://shortlink.example.com/abc123")
    """
    def __init__(self, page: Page, blocker=None, captcha_solver=None):
        self.page = page
        self.blocker = blocker
        self.captcha_solver = captcha_solver
        
    async def solve(self, url: str, success_patterns: list = None) -> bool:
        """
        Traverse a shortlink until a success pattern is found in the URL.
        
        Args:
            url: The starting URL.
            success_patterns: List of string patterns to check in the URL to confirm success.
                              If None, defaults to common return URLs.
        """
        try:
            logger.info(f"🔗 Starting Shortlink: {url}")
            
            if not success_patterns:
                success_patterns = ["dutchycorp.space/shortlinks-wall.php", "firefaucet.win/shortlinks", "/shortlinks"]

            # Disable blocker if present to avoid adblock detection
            if self.blocker:
                logger.info("🔓 Disabling Resource Blocker for Shortlink...")
                self.blocker.enabled = False
                
            await self.page.goto(url)
            
            # Attempt generic traverse loop
            for step in range(20): # Increased steps for complex links
                # 1. Check for 'Success' indicators
                current_url = self.page.url
                if any(p in current_url for p in success_patterns):
                    logger.info(f"✅ Returned to Success URL: {current_url}")
                    return True
                
                # 2. Wait for Timer
                try:
                    timer_selectors = [
                        "#timer", ".timer", "#countdown", "div[id*='time']", 
                        "span[id*='time']", ".timer-text", "#please-wait",
                        "strong[id*='timer']", "b[id*='timer']"
                    ]
                    timer_found = False
                    for sel in timer_selectors:
                        timer_el = self.page.locator(sel)
                        if await timer_el.count() > 0 and await timer_el.first.is_visible():
                            text = await timer_el.first.text_content()
                            from core.extractor import DataExtractor
                            wait_min = DataExtractor.parse_timer_to_minutes(text)
                            if wait_min > 0:
                                wait_s = min(wait_min * 60, 65)  # Cap wait at 65s
                                logger.info(f"⏳ Timer found ({text}), waiting {wait_s:.1f}s...")
                                await asyncio.sleep(wait_s)
                                timer_found = True
                                break
                    if not timer_found:
                        # Sometimes timer is hidden or just "Please Wait" text
                        if "please wait" in (await self.page.content()).lower():
                             await asyncio.sleep(5)
                except Exception as e:
                    logger.debug(f"Timer detection error: {e}")

                # 3. Check for Captcha
                if self.captcha_solver:
                    # Check for visible captcha frames or containers
                    if await self.page.locator("iframe[src*='recaptcha'], iframe[src*='turnstile'], iframe[src*='hcaptcha'], .cf-turnstile").count() > 0:
                        logger.info("🧩 Captcha detected in shortlink. Attempting to solve...")
                        await self.captcha_solver.solve_captcha(self.page)
                        await asyncio.sleep(2)

                # 4. Click 'Next' / 'Get Link' / 'Continue'
                # Expanded priorities
                buttons = [
                    # ID based (Highest confidence)
                    "a#invisibleCaptchaShortlink", 
                    "button#submit-button",
                    "button#method_free",
                    "a#go-link",
                    
                    # Text based (High confidence)
                    "button:has-text('Get Link')",
                    "a:has-text('Get Link')",
                    "button:has-text('Continue')",
                    "a:has-text('Continue')",
                    "button:has-text('Next')", 
                    "a:has-text('Next')",
                    "button:has-text('Click here to continue')",
                    "a:has-text('Click here to continue')",
                    "div:has-text('Click here to continue')",
                    
                    # Class based (Medium confidence)
                    ".btn-success",
                    ".btn-primary", 
                    "input[type='submit']",
                    
                    # Image based (Low confidence, but necessary for some)
                    "img[alt='continue']",
                    "img[src*='continue']",
                    "img[src*='next']"
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
                                if box and (box['width'] < 5 or box['height'] < 5):
                                    continue
                                    
                                # Heuristic: Ignore if covered by another element (simple check)
                                # Playwright handles this mostly, but good to be explicit if needed
                                
                                logger.info(f"👆 Clicking {sel} (instance {i})...")
                                
                                # Standard click with popup handling
                                try:
                                    # Expect navigation or new page or just action
                                    # We don't strictly expect a new page, sometimes it is same page reload
                                    await target.click(timeout=3000)
                                    
                                    # Handling Popups:
                                    # Shortlinks AGGRESSIVELY open popups.
                                    # We can try to close the *new* page if it's not the target, 
                                    # but distinguishing popup vs next step is hard.
                                    # Best bet: Keep focus on the tab that initiated the click if possible,
                                    # or check if we were redirected.
                                    
                                    wait_start = asyncio.get_event_loop().time()
                                    while len(self.page.context.pages) > 1 and (asyncio.get_event_loop().time() - wait_start) < 5:
                                        # Close all pages except current one
                                        for p in self.page.context.pages:
                                            if p != self.page:
                                                await p.close()
                                        await asyncio.sleep(0.5)

                                except Exception:
                                    # Force click if blocked
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
                    # Check if we moved anyway (auto-redirect)
                    if any(p in self.page.url for p in success_patterns):
                        continue

            return False
            
        except Exception as e:
            logger.error(f"Shortlink Failed: {e}")
            return False
        finally:
            if self.blocker:
                logger.info("🔒 Re-enabling Resource Blocker...")
                self.blocker.enabled = True
