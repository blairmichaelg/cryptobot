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

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ShortlinkSolver:
    """Automated solver for multi-step crypto shortlinks.

    Navigates through intermediate pages, waits for countdown timers,
    solves embedded CAPTCHAs, clicks continuation buttons, and closes
    popup windows until the final destination URL is reached.

    Args:
        page: Playwright ``Page`` instance to drive.
        blocker: Optional resource blocker -- disabled during traversal
            to avoid adblock detection on intermediate pages.
        captcha_solver: Optional :class:`CaptchaSolver` used to handle
            embedded CAPTCHAs encountered on intermediate pages.

    Example::

        solver = ShortlinkSolver(page, blocker=blocker,
                                 captcha_solver=captcha)
        success = await solver.solve(
            "https://shortlink.example.com/abc123"
        )
    """

    def __init__(
        self,
        page: Page,
        blocker: Optional[Any] = None,
        captcha_solver: Optional[Any] = None,
    ) -> None:
        """Initialise the ShortlinkSolver.

        Args:
            page: Playwright ``Page`` instance to drive.
            blocker: Optional resource blocker to disable during
                traversal.
            captcha_solver: Optional CAPTCHA solver for embedded
                challenges.
        """
        self.page = page
        self.blocker = blocker
        self.captcha_solver = captcha_solver

    async def solve(
        self,
        url: str,
        success_patterns: Optional[List[str]] = None,
    ) -> bool:
        """Traverse a shortlink until a success URL pattern is matched.

        Iterates through up to 20 intermediate pages, handling timers,
        CAPTCHAs, and navigation buttons at each step.

        Args:
            url: The starting shortlink URL.
            success_patterns: URL substrings that indicate successful
                traversal.  Defaults to common faucet return URLs when
                ``None``.

        Returns:
            ``True`` if a success pattern was found in the final URL,
            ``False`` if all steps were exhausted or an error occurred.
        """
        try:
            logger.info("Starting Shortlink: %s", url)

            if not success_patterns:
                success_patterns = [
                    "dutchycorp.space/shortlinks-wall.php",
                    "firefaucet.win/shortlinks",
                    "/shortlinks",
                ]

            # Disable blocker if present to avoid adblock detection
            if self.blocker:
                logger.info(
                    "Disabling Resource Blocker for Shortlink..."
                )
                self.blocker.enabled = False

            await self.page.goto(url)

            # Attempt generic traverse loop
            for step in range(20):
                # 1. Check for 'Success' indicators
                current_url = self.page.url
                if any(p in current_url for p in success_patterns):
                    logger.info(
                        "Returned to Success URL: %s", current_url
                    )
                    return True

                # 2. Wait for Timer
                await self._handle_timer()

                # 3. Check for Captcha
                await self._handle_captcha()

                # 4. Click 'Next' / 'Get Link' / 'Continue'
                clicked = await self._click_continue_button()

                if not clicked:
                    await asyncio.sleep(2)
                    # Check if we moved anyway (auto-redirect)
                    if any(
                        p in self.page.url
                        for p in success_patterns
                    ):
                        continue

            return False

        except Exception as e:
            logger.error("Shortlink Failed: %s", e)
            return False
        finally:
            if self.blocker:
                logger.info("Re-enabling Resource Blocker...")
                self.blocker.enabled = True

    async def _handle_timer(self) -> None:
        """Detect and wait for countdown timers on the current page.

        Searches for common timer selectors and waits for the countdown
        to complete.  Falls back to a short sleep if a ``please wait``
        message is detected without a visible timer element.
        """
        try:
            timer_selectors = [
                "#timer", ".timer", "#countdown",
                "div[id*='time']", "span[id*='time']",
                ".timer-text", "#please-wait",
                "strong[id*='timer']", "b[id*='timer']",
            ]
            timer_found = False
            for sel in timer_selectors:
                timer_el = self.page.locator(sel)
                if (
                    await timer_el.count() > 0
                    and await timer_el.first.is_visible()
                ):
                    text = await timer_el.first.text_content()
                    from core.extractor import DataExtractor
                    wait_min = DataExtractor.parse_timer_to_minutes(
                        text
                    )
                    if wait_min > 0:
                        wait_s = min(wait_min * 60, 65)
                        logger.info(
                            "Timer found (%s), waiting %.1fs...",
                            text,
                            wait_s,
                        )
                        await asyncio.sleep(wait_s)
                        timer_found = True
                        break
            if not timer_found:
                page_content = await self.page.content()
                if "please wait" in page_content.lower():
                    await asyncio.sleep(5)
        except Exception as e:
            logger.debug("Timer detection error: %s", e)

    async def _handle_captcha(self) -> None:
        """Detect and solve any embedded CAPTCHAs on the current page.

        Checks for reCAPTCHA, Turnstile, or hCaptcha iframes and uses
        the configured :attr:`captcha_solver` to solve them if present.
        """
        if not self.captcha_solver:
            return

        captcha_selector = (
            "iframe[src*='recaptcha'], "
            "iframe[src*='turnstile'], "
            "iframe[src*='hcaptcha'], "
            ".cf-turnstile"
        )
        if await self.page.locator(captcha_selector).count() > 0:
            logger.info(
                "Captcha detected in shortlink. "
                "Attempting to solve..."
            )
            await self.captcha_solver.solve_captcha(self.page)
            await asyncio.sleep(2)

    async def _click_continue_button(self) -> bool:
        """Find and click the next continuation button on the page.

        Iterates through a prioritised list of button selectors (by ID,
        text content, CSS class, and image attributes) and clicks the
        first visible, enabled element that passes size heuristics.
        Popup windows opened by the click are automatically closed.

        Returns:
            ``True`` if a button was clicked, ``False`` otherwise.
        """
        buttons = [
            # ID based (highest confidence)
            "a#invisibleCaptchaShortlink",
            "button#submit-button",
            "button#method_free",
            "a#go-link",
            # Text based (high confidence)
            "button:has-text('Get Link')",
            "a:has-text('Get Link')",
            "button:has-text('Continue')",
            "a:has-text('Continue')",
            "button:has-text('Next')",
            "a:has-text('Next')",
            "button:has-text('Click here to continue')",
            "a:has-text('Click here to continue')",
            "div:has-text('Click here to continue')",
            # Class based (medium confidence)
            ".btn-success",
            ".btn-primary",
            "input[type='submit']",
            # Image based (low confidence)
            "img[alt='continue']",
            "img[src*='continue']",
            "img[src*='next']",
        ]

        for sel in buttons:
            try:
                targets = self.page.locator(sel)
                count = await targets.count()
                for i in range(count):
                    target = targets.nth(i)
                    if not (
                        await target.is_visible()
                        and await target.is_enabled()
                    ):
                        continue

                    # Ignore suspiciously small elements
                    box = await target.bounding_box()
                    if box and (
                        box["width"] < 5 or box["height"] < 5
                    ):
                        continue

                    logger.info(
                        "Clicking %s (instance %d)...", sel, i
                    )

                    try:
                        await target.click(timeout=3000)
                        await self._close_popups()
                    except Exception:
                        await target.click(
                            timeout=3000, force=True
                        )

                    await asyncio.sleep(4)
                    return True
            except Exception:
                continue

        return False

    async def _close_popups(self) -> None:
        """Close any popup windows opened by a button click.

        Waits up to 5 seconds and closes all browser context pages
        except the primary page.
        """
        wait_start = asyncio.get_event_loop().time()
        while (
            len(self.page.context.pages) > 1
            and (asyncio.get_event_loop().time() - wait_start) < 5
        ):
            for p in self.page.context.pages:
                if p != self.page:
                    await p.close()
            await asyncio.sleep(0.5)
