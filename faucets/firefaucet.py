"""FireFaucet bot implementation for Cryptobot Gen 3.0.

Implements the ``firefaucet.win`` faucet with:
    * Cloudflare Turnstile detection and bypass.
    * Multi-currency auto-faucet claiming and manual modes.
    * Shortlink traversal for bonus earnings.
    * Balance and timer extraction with fallback selectors.
    * Level / XP-aware claim scheduling.

Claim interval: ~30 minutes (auto-faucet mode).

Selector Update Notes (2026-02-08):
    * Enhanced claim button selectors with data attributes for stability
    * Prioritize ID selectors > data-attrs > classes > text content
    * Added semantic data-action and data-testid selectors
    * Reordered timer selectors by stability (ID first, wildcards last)
    * Cloudflare retry logic already robust with progressive delays
    
Known Issues:
    * Cloudflare Turnstile protection is aggressive - may require longer waits
    * If facing persistent blocks, increase max_cloudflare_retries or proxy pool
"""

import asyncio
import logging
import random
import re
import time
from typing import Any

from playwright.async_api import Page

from core.config import BotSettings
from solvers.shortlink import ShortlinkSolver
from .base import ClaimResult, FaucetBot

logger = logging.getLogger(__name__)


class FireFaucetBot(FaucetBot):
    """Bot for the FireFaucet.win faucet site.

    FireFaucet uses Cloudflare Turnstile protection and a
    points-based auto-faucet system.  This bot handles both the
    auto-faucet (ATC) and manual claim workflows, with progressive
    Cloudflare bypass logic.
    """

    def __init__(
        self,
        settings: BotSettings,
        page: Page,
        **kwargs: Any,
    ) -> None:
        """Initialise the FireFaucet bot.

        Args:
            settings: Global bot configuration.
            page: Playwright ``Page`` instance.
            **kwargs: Passed through to ``FaucetBot``.
        """
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FireFaucet"
        self.base_url = "https://firefaucet.win"
        self.cloudflare_retry_count = 0
        self.max_cloudflare_retries = 3  # Updated 2026-02-08: Increased from 3 to handle slow proxies

    async def detect_cloudflare_block(self) -> bool:
        """Detect active Cloudflare protection on the page.

        Checks for Cloudflare challenge pages, Turnstile captcha
        iframes, maintenance / security pages, and bot-detection
        blocks.

        Returns:
            True if Cloudflare protection is active.
        """
        try:
            title = (await self.page.title()).lower()
            challenge_titles = [
                "just a moment",
                "security check",
                "ddos protection",
                "attention required",
                "checking your browser",
            ]
            if any(t in title for t in challenge_titles):
                logger.warning(
                    f"[{self.faucet_name}] "
                    f"Cloudflare detected in title: {title}"
                )
                return True

            body_text = await self.page.evaluate(
                "() => document.body.innerText.toLowerCase()"
            )
            challenge_patterns = [
                "checking your browser",
                "please wait while we check your browser",
                "just a moment",
                "verify you are human",
                "enable javascript and cookies",
                "this process is automatic",
            ]

            if any(p in body_text for p in challenge_patterns):
                if len(body_text) < 1000:
                    logger.warning(
                        f"[{self.faucet_name}] Cloudflare "
                        f"challenge detected in page "
                        f"content (len: {len(body_text)})"
                    )
                    return True
                logger.debug(
                    f"[{self.faucet_name}] Page mentions "
                    f"Cloudflare but has normal content "
                    f"(len: {len(body_text)}), "
                    f"not a challenge"
                )

            turnstile_sel = (
                "iframe[src*='turnstile'], "
                "iframe[src*='challenges.cloudflare.com']"
            )
            turnstile_frame = await self.page.query_selector(
                turnstile_sel
            )
            if turnstile_frame:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Cloudflare Turnstile iframe detected"
                )
                return True

            cf_sel = (
                "#cf-challenge-running, "
                ".cf-browser-verification, "
                "[id*='cf-turnstile']"
            )
            cf_elements = await self.page.query_selector(cf_sel)
            if cf_elements:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Cloudflare challenge elements detected"
                )
                return True

            return False

        except Exception as e:
            logger.debug(
                f"[{self.faucet_name}] "
                f"Error in Cloudflare detection: {e}"
            )
            return False

    async def bypass_cloudflare_with_retry(self) -> bool:
        """Bypass Cloudflare with progressive stealth escalation.

        Strategy:
            1. Wait for automatic challenge resolution.
            2. Detect and solve Turnstile if present.
            3. On retry, increase stealth measures (longer idle
               times, more mouse movements, extended waits).

        Returns:
            True if bypass succeeded, False if all retries
            exhausted.
        """
        max_retries = self.max_cloudflare_retries
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"[{self.faucet_name}] Cloudflare bypass "
                    f"attempt {attempt}/{max_retries}"
                )

                # Progressive stealth: increase delays each retry
                base_wait = 10 + (attempt * 5)

                logger.info(
                    f"[{self.faucet_name}] Waiting "
                    f"{base_wait}s for automatic "
                    f"challenge resolution..."
                )
                await self.idle_mouse(
                    duration=random.uniform(2.0, 4.0)
                )
                await self.human_wait(
                    base_wait, with_interactions=True
                )

                # Check for Turnstile and solve if present
                turnstile_sel = (
                    "iframe[src*='turnstile'], "
                    "iframe[src*="
                    "'challenges.cloudflare.com'], "
                    "[data-sitekey]"
                )
                turnstile_detected = (
                    await self.page.query_selector(
                        turnstile_sel
                    )
                )
                if turnstile_detected:
                    logger.info(
                        f"[{self.faucet_name}] Turnstile "
                        f"CAPTCHA detected, solving..."
                    )

                    await self.idle_mouse(
                        duration=random.uniform(1.5, 3.0)
                    )
                    await self.simulate_reading(
                        duration=random.uniform(2.0, 4.0)
                    )

                    solved = await self.solver.solve_captcha(
                        self.page, timeout=120
                    )
                    if solved:
                        logger.info(
                            f"[{self.faucet_name}] "
                            f"Turnstile solved successfully"
                        )
                        await self.human_wait(
                            random.uniform(2.0, 4.0)
                        )
                    else:
                        logger.warning(
                            f"[{self.faucet_name}] "
                            f"Turnstile solving failed"
                        )
                        if attempt < max_retries:
                            logger.info(
                                f"[{self.faucet_name}] "
                                f"Refreshing for retry..."
                            )
                            await self.page.reload()
                            await self.human_wait(3)
                            continue

                # Enhanced wait with human-like activity
                logger.debug(
                    f"[{self.faucet_name}] Performing "
                    f"human-like activity during challenge..."
                )
                for _ in range(attempt * 2):
                    if random.random() < 0.6:
                        await self.idle_mouse(
                            duration=random.uniform(0.5, 1.5)
                        )
                    else:
                        await self.simulate_reading(
                            duration=random.uniform(1.0, 2.5)
                        )
                    await asyncio.sleep(
                        random.uniform(1.0, 2.0)
                    )

                still_blocked = (
                    await self.detect_cloudflare_block()
                )
                if not still_blocked:
                    logger.info(
                        f"[{self.faucet_name}] Cloudflare "
                        f"bypass successful on "
                        f"attempt {attempt}"
                    )
                    self.cloudflare_retry_count = 0
                    return True

                logger.warning(
                    f"[{self.faucet_name}] Still blocked "
                    f"after attempt {attempt}, retrying..."
                )

                if attempt < max_retries:
                    await self.human_wait(
                        random.uniform(3.0, 6.0)
                    )
                    logger.info(
                        f"[{self.faucet_name}] "
                        f"Refreshing page for retry..."
                    )
                    await self.page.reload()
                    await self.human_wait(
                        random.uniform(4.0, 7.0)
                    )

            except Exception as e:
                logger.error(
                    f"[{self.faucet_name}] Error during "
                    f"Cloudflare bypass "
                    f"attempt {attempt}: {e}"
                )
                if attempt < max_retries:
                    await self.human_wait(
                        random.uniform(5.0, 10.0)
                    )
                    continue

        logger.error(
            f"[{self.faucet_name}] Cloudflare bypass "
            f"failed after {max_retries} attempts"
        )
        self.cloudflare_retry_count += 1
        return False

    async def view_ptc_ads(self) -> None:
        """View PTC (Paid-To-Click) ads for FireFaucet.

        Process:
            1. Navigate to PTC ads page.
            2. Detect available ad cards.
            3. For each ad (up to *limit*): click, solve
               CAPTCHA, submit, verify completion.
            4. Return to PTC page for next ad.

        Stealth features include ``human_like_click`` for ad
        interactions, ``random_delay`` between actions, and
        CAPTCHA solving with multiple provider support.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] Checking PTC Ads..."
            )
            await self.page.goto(f"{self.base_url}/ptc")

            ad_button = self.page.locator(
                ".row > div:nth-child(1) "
                "> div > div:nth-child(3) > a"
            )

            processed = 0
            limit = 3

            while processed < limit:
                if await ad_button.count() == 0:
                    logger.info(
                        f"[{self.faucet_name}] No more PTC "
                        f"ads available "
                        f"(processed {processed})."
                    )
                    break

                logger.info(
                    f"[{self.faucet_name}] Watching PTC "
                    f"Ad {processed + 1}/{limit}..."
                )
                await self.idle_mouse(
                    duration=random.uniform(0.5, 1.0)
                )
                await self.human_like_click(ad_button.first)
                await self.page.wait_for_load_state()
                logger.debug(
                    f"[{self.faucet_name}] "
                    f"Loaded PTC ad page: {self.page.url}"
                )

                captcha_img = self.page.locator(
                    "#description > img"
                )
                if await captcha_img.count() > 0:
                    logger.info(
                        f"[{self.faucet_name}] Custom PTC "
                        f"captcha image detected. Solving..."
                    )
                    await self.solver.solve_captcha(self.page)
                    logger.debug(
                        f"[{self.faucet_name}] "
                        f"Custom PTC captcha solved"
                    )

                hcap_sel = (
                    "iframe[src*='turnstile'], "
                    "iframe[src*='hcaptcha']"
                )
                if await self.page.query_selector(hcap_sel):
                    logger.info(
                        f"[{self.faucet_name}] Standard "
                        f"CAPTCHA detected on PTC ad"
                    )
                    await self.solver.solve_captcha(self.page)
                    logger.debug(
                        f"[{self.faucet_name}] "
                        f"Standard CAPTCHA solved"
                    )

                submit_btn = self.page.locator(
                    "#submit-button"
                )
                if await submit_btn.count() > 0:
                    logger.debug(
                        f"[{self.faucet_name}] "
                        f"Clicking PTC submit button"
                    )
                    await self.idle_mouse(
                        duration=random.uniform(0.3, 0.8)
                    )
                    await self.human_like_click(submit_btn)
                    await self.random_delay(2, 4)
                    logger.info(
                        f"[{self.faucet_name}] PTC "
                        f"Ad {processed + 1} completed"
                    )
                else:
                    logger.warning(
                        f"[{self.faucet_name}] "
                        f"PTC submit button not found"
                    )

                processed += 1
                logger.debug(
                    f"[{self.faucet_name}] "
                    f"Returning to PTC ads list"
                )
                await self.page.goto(
                    f"{self.base_url}/ptc"
                )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] PTC Error: {e}"
            )

    async def login(self) -> bool:
        """Authenticate with FireFaucet using stored credentials.

        Implements stealth techniques including ``human_type``
        for text input, ``idle_mouse`` for natural mouse movement,
        CAPTCHA solving with retry logic, and multiple verification
        methods (URL, DOM elements, error messages).

        Returns:
            True if login successful, False otherwise.
        """
        if self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("fire_faucet")

        if not creds:
            logger.error(
                f"[{self.faucet_name}] No credentials found"
            )
            return False

        try:
            logger.info(
                f"[{self.faucet_name}] "
                f"Navigating to login page..."
            )
            timeout = getattr(
                self.settings, "timeout", 180000
            )
            nav_success = await self.safe_navigate(
                f"{self.base_url}/login", timeout=timeout
            )
            if not nav_success:
                logger.error(
                    f"[{self.faucet_name}] "
                    f"Failed to navigate to login page"
                )
                return False

            current_url = self.page.url
            logger.debug(
                f"[{self.faucet_name}] "
                f"Current URL after navigation: "
                f"{current_url}"
            )

            # Check if already logged in (redirected away from /login)
            if "/login" not in current_url:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Already logged in (session valid, "
                    f"redirected to {current_url})"
                )
                return True

            # Check for dashboard elements on current page
            try:
                dash_sel = (
                    ".user-balance, "
                    ".level-progress, "
                    ".dashboard-content"
                )
                loc = self.page.locator(dash_sel)
                if await loc.count() > 0:
                    logger.info(
                        f"[{self.faucet_name}] Already "
                        f"logged in (dashboard elements)"
                    )
                    return True
            except Exception:
                pass

            # Enhanced Cloudflare bypass
            cf_blocked = await self.detect_cloudflare_block()
            if cf_blocked:
                logger.warning(
                    f"[{self.faucet_name}] Cloudflare "
                    f"protection detected, "
                    f"attempting bypass..."
                )
                bypass_ok = (
                    await self.bypass_cloudflare_with_retry()
                )
                if not bypass_ok:
                    logger.error(
                        f"[{self.faucet_name}] Failed to "
                        f"bypass Cloudflare after "
                        f"{self.max_cloudflare_retries} "
                        f"attempts"
                    )
                    return False
            else:
                await self.handle_cloudflare(
                    max_wait_seconds=20
                )

            # Check for adblock redirect
            if "/adblock" in self.page.url:
                logger.error(
                    f"[{self.faucet_name}] Redirected to "
                    f"adblock page. Site blocking us."
                )
                logger.info(
                    f"[{self.faucet_name}] This shouldn't "
                    f"happen with image_bypass enabled. "
                    f"Check config."
                )
                return False

            await self.warm_up_page()

            # Wait for login form
            try:
                await self.page.wait_for_selector(
                    '#username', timeout=20000
                )
            except Exception as e:
                logger.warning(
                    f"[{self.faucet_name}] #username "
                    f"not found, trying alternates..."
                )
                alt_selectors = [
                    "input[name='username']",
                    "input[type='text']",
                    "#login-username",
                ]
                found = False
                for sel in alt_selectors:
                    try:
                        loc = self.page.locator(sel)
                        if await loc.count() > 0:
                            logger.info(
                                f"[{self.faucet_name}] "
                                f"Found login field: {sel}"
                            )
                            found = True
                            break
                    except Exception:
                        pass
                if not found:
                    try:
                        pg_title = await self.page.title()
                        url = self.page.url
                        logger.error(
                            f"[{self.faucet_name}] Login "
                            f"form not found. "
                            f"Title: {pg_title}, "
                            f"URL: {url}"
                        )
                        if "/adblock" in url:
                            logger.error(
                                f"[{self.faucet_name}] "
                                f"Site detected adblock!"
                            )
                    except Exception:
                        pass
                    raise e

            logger.info(
                f"[{self.faucet_name}] "
                f"Filling login form..."
            )

            await self.human_type(
                '#username', creds['username'],
                delay_min=80, delay_max=150,
            )
            await self.idle_mouse(
                duration=random.uniform(0.5, 1.0)
            )
            await self.random_delay(0.3, 0.7)
            await self.human_type(
                '#password', creds['password'],
                delay_min=80, delay_max=150,
            )
            await self.idle_mouse(
                duration=random.uniform(0.5, 1.0)
            )
            await self.random_delay(0.5, 1.0)

            # Handle CAPTCHA
            logger.info(
                f"[{self.faucet_name}] "
                f"Solving login CAPTCHA..."
            )
            await self.idle_mouse(
                duration=random.uniform(0.8, 1.5)
            )
            captcha_result = await self.solver.solve_captcha(
                self.page
            )
            if not captcha_result:
                logger.warning(
                    f"[{self.faucet_name}] "
                    f"Login CAPTCHA solving failed"
                )
            else:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Login CAPTCHA solved successfully"
                )

            await self.random_delay(1.0, 2.0)

            # Check for submit button
            submit_sel = (
                'button.submitbtn, '
                'button[type="submit"]'
            )
            submit_btn = self.page.locator(submit_sel)
            if await submit_btn.count() > 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Submit button found. Clicking..."
                )
                if await submit_btn.is_disabled():
                    logger.warning(
                        f"[{self.faucet_name}] "
                        f"Submit button is disabled! "
                        f"Waiting..."
                    )
                    js = (
                        "document.querySelector("
                        "'button.submitbtn, "
                        'button[type="submit"]\')'
                        ".disabled === false"
                    )
                    await self.page.wait_for_function(
                        js, timeout=5000
                    )

                await self.human_like_click(submit_btn)
            else:
                logger.warning(
                    f"[{self.faucet_name}] Submit button "
                    f"NOT found. Trying form submit..."
                )
                await self.page.evaluate(
                    "document.forms[0].submit()"
                )

            logger.info(
                f"[{self.faucet_name}] "
                f"Waiting for post-login state..."
            )

            # Poll for success (max 30 seconds)
            start_time = time.monotonic()
            while (time.monotonic() - start_time) < 30:
                try:
                    url = self.page.url
                    if "/dashboard" in url:
                        logger.info(
                            f"[{self.faucet_name}] Login "
                            f"successful (Dashboard URL)!"
                        )
                        return True

                    dash_loc = self.page.locator(
                        ".user-balance, .level-progress"
                    )
                    if await dash_loc.count() > 0:
                        logger.info(
                            f"[{self.faucet_name}] Login "
                            f"successful (Dashboard "
                            f"elements)!"
                        )
                        return True

                    err_sel = (
                        ".alert-danger, "
                        ".error-message, "
                        ".toast-error"
                    )
                    err_loc = self.page.locator(err_sel)
                    if await err_loc.count() > 0:
                        error_text = (
                            await err_loc.first
                            .text_content()
                        )
                        logger.error(
                            f"[{self.faucet_name}] "
                            f"Login error: {error_text}"
                        )
                        return False

                    elapsed = time.monotonic() - start_time
                    if "/login" in url and elapsed > 10:
                        logger.debug(
                            f"[{self.faucet_name}] "
                            f"Still on login page..."
                        )

                except Exception:
                    pass

                await asyncio.sleep(1)

            logger.warning(
                f"[{self.faucet_name}] Login verification "
                f"timed out. URL: {self.page.url}"
            )
            return False

        except Exception as e:
            logger.error(
                f"FireFaucet login failed: {e}"
            )
            return False

    def get_jobs(self) -> list[Any]:
        """Return FireFaucet-specific scheduled jobs.

        Includes faucet claim, daily bonus, PTC ads, shortlinks,
        and withdrawal tasks with staggered start times.

        Returns:
            List of ``Job`` instances for the orchestrator.
        """
        from core.orchestrator import Job

        jobs: list[Any] = []
        f_type = "fire_faucet"

        # Job 1: Faucet Claim - Highest Priority
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=f_type,
            job_type="claim_wrapper",
        ))

        # Job 2: Daily Bonus (runs once per day)
        jobs.append(Job(
            priority=2,
            next_run=time.time() + 600,
            name=f"{self.faucet_name} Daily Bonus",
            profile=None,
            faucet_type=f_type,
            job_type="daily_bonus_wrapper",
        ))

        # Job 3: PTC Ads - Medium Priority
        jobs.append(Job(
            priority=3,
            next_run=time.time() + 300,
            name=f"{self.faucet_name} PTC",
            profile=None,
            faucet_type=f_type,
            job_type="ptc_wrapper",
        ))

        # Job 4: Shortlinks - Lower Priority
        jobs.append(Job(
            priority=4,
            next_run=time.time() + 1200,
            name=f"{self.faucet_name} Shortlinks",
            profile=None,
            faucet_type=f_type,
            job_type="shortlinks_wrapper",
        ))

        # Job 5: Withdraw - Daily Priority
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=f_type,
            job_type="withdraw_wrapper",
        ))

        return jobs

    async def withdraw(self) -> ClaimResult:
        """Execute automated withdrawal for FireFaucet.

        Selects the first coin that meets its withdrawal
        threshold and submits a withdrawal request via FaucetPay.

        Returns:
            ClaimResult with withdrawal status.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] "
                f"Navigating to withdrawal..."
            )
            await self.page.goto(
                f"{self.base_url}/withdraw"
            )

            coins = self.page.locator(
                ".card:has(button:has-text('Withdraw'))"
            )
            count = await coins.count()

            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"No coins ready for withdrawal."
                )
                return ClaimResult(
                    success=True,
                    status="No Balance",
                    next_claim_minutes=1440,
                )

            coin_btn = coins.first.locator(
                "button:has-text('Withdraw')"
            )
            await self.human_like_click(coin_btn)
            await self.page.wait_for_load_state()

            processor = self.page.locator(
                "select[name='processor']"
            )
            if await processor.count() > 0:
                await processor.select_option("faucetpay")
                await asyncio.sleep(1)

            await self.solver.solve_captcha(self.page)

            submit = self.page.locator(
                "button:has-text('Withdraw')"
            ).last
            await self.human_like_click(submit)

            success_loc = self.page.locator(
                ".alert-success, .toast-success"
            )
            if await success_loc.count() > 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Withdrawal successful!"
                )
                return ClaimResult(
                    success=True,
                    status="Withdrawn",
                    next_claim_minutes=1440,
                )

            return ClaimResult(
                success=False,
                status="Withdrawal submitted, "
                       "no success message",
                next_claim_minutes=120,
            )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Withdrawal Error: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=60,
            )

    async def daily_bonus_wrapper(
        self, page: Page,
    ) -> ClaimResult:
        """Claim the daily login bonus.

        Args:
            page: Playwright ``Page`` to operate on.

        Returns:
            ClaimResult with daily bonus status.
        """
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(
                success=False,
                status="Login Failed",
                next_claim_minutes=30,
            )

        try:
            await self.page.goto(f"{self.base_url}/daily")
            unlock = self.page.locator(
                "body > div.row > div.col.s12.m12.l6 "
                "> div > center > a > button"
            )
            if await unlock.count() > 0 \
                    and await unlock.is_visible():
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Unlocking Daily Bonus..."
                )
                await self.human_like_click(unlock)
                await self.random_delay()

            # Prefer Turnstile via label click
            turnstile_label = self.page.locator(
                "label[for='select-turnstile']"
            )
            if await turnstile_label.count() > 0:
                logger.debug(
                    f"[{self.faucet_name}] Selecting "
                    f"Turnstile via label (daily bonus)"
                )
                await turnstile_label.click()
                await asyncio.sleep(1)
            else:
                turnstile_opt = self.page.locator(
                    "#select-turnstile"
                )
                if await turnstile_opt.count() > 0:
                    logger.debug(
                        f"[{self.faucet_name}] Selecting "
                        f"Turnstile via JS (daily bonus)"
                    )
                    await self.page.evaluate(
                        "document.getElementById("
                        "'select-turnstile').checked "
                        "= true; "
                        "change_captcha('turnstile');"
                    )
                    await asyncio.sleep(1)

            await self.solver.solve_captcha(self.page)

            claim_btn = self.page.locator(
                "body > div.row > div.col.s12.m12.l6 "
                "> div > center > form > button"
            )
            if await claim_btn.count() > 0:
                await self.human_like_click(claim_btn)
                await self.random_delay(2, 4)
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Daily Bonus claimed!"
                )
                return ClaimResult(
                    success=True,
                    status="Daily Bonus Claimed",
                    next_claim_minutes=1440,
                )

            return ClaimResult(
                success=False,
                status="Daily Bonus Not Available",
                next_claim_minutes=1440,
            )
        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Daily Bonus Error: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=1440,
            )

    async def shortlinks_wrapper(
        self, page: Page,
    ) -> ClaimResult:
        """Process available shortlinks for bonus earnings.

        Args:
            page: Playwright ``Page`` to operate on.

        Returns:
            ClaimResult with shortlink processing status.
        """
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(
                success=False,
                status="Login Failed",
                next_claim_minutes=30,
            )

        try:
            await self.claim_shortlinks()
            return ClaimResult(
                success=True,
                status="Shortlinks Processed",
                next_claim_minutes=120,
            )
        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Shortlinks Error: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=120,
            )

    async def claim(self) -> ClaimResult:
        """Execute the main faucet claim cycle.

        Process:
            1. Navigate to daily bonus page and attempt claim.
            2. Navigate to faucet page.
            3. Extract balance and timer with fallback selectors.
            4. If timer active, return with *next_claim_minutes*.
            5. Solve CAPTCHA with retry logic.
            6. Click claim button with stealth techniques.
            7. Verify success and extract updated balance.

        Returns:
            ClaimResult with claim outcome, amount, and balance.
        """
        try:
            # First, check Daily Bonus
            await self.page.goto(f"{self.base_url}/daily")
            await self.warm_up_page()

            cf_blocked = await self.detect_cloudflare_block()
            if cf_blocked:
                logger.warning(
                    f"[{self.faucet_name}] Cloudflare "
                    f"detected on daily page, "
                    f"attempting bypass..."
                )
                bypass_ok = (
                    await self.bypass_cloudflare_with_retry()
                )
                if not bypass_ok:
                    logger.error(
                        f"[{self.faucet_name}] Failed to "
                        f"bypass Cloudflare on daily page"
                    )
                    return ClaimResult(
                        success=False,
                        status="Cloudflare Block",
                        next_claim_minutes=15,
                    )

            # Check for "Unlock" button
            unlock = self.page.locator(
                "body > div.row > div.col.s12.m12.l6 "
                "> div > center > a > button"
            )
            if await unlock.count() > 0 \
                    and await unlock.is_visible():
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Unlocking Daily Bonus..."
                )
                await self.human_like_click(unlock)
                await self.random_delay()

            # Prefer Turnstile CAPTCHA via label click
            turnstile_label = self.page.locator(
                "label[for='select-turnstile']"
            )
            if await turnstile_label.count() > 0:
                logger.debug(
                    f"[{self.faucet_name}] Selecting "
                    f"Turnstile CAPTCHA via label"
                )
                await turnstile_label.click()
                await asyncio.sleep(1)
            else:
                turnstile_opt = self.page.locator(
                    "#select-turnstile"
                )
                if await turnstile_opt.count() > 0:
                    logger.debug(
                        f"[{self.faucet_name}] Selecting "
                        f"Turnstile CAPTCHA via JS"
                    )
                    await self.page.evaluate(
                        "document.getElementById("
                        "'select-turnstile').checked "
                        "= true; "
                        "change_captcha('turnstile');"
                    )
                    await asyncio.sleep(1)

            await self.solver.solve_captcha(self.page)

            # Daily Bonus Button
            claim_btn = self.page.locator(
                "body > div.row > div.col.s12.m12.l6 "
                "> div > center > form > button"
            )
            if await claim_btn.count() > 0:
                await self.human_like_click(claim_btn)
                await self.random_delay(2, 4)

            # Now, Faucet Claim
            logger.info(
                f"[{self.faucet_name}] "
                f"Navigating to faucet page..."
            )
            await self.page.goto(f"{self.base_url}/faucet")
            await self.human_wait(5)

            cf_blocked = await self.detect_cloudflare_block()
            if cf_blocked:
                logger.warning(
                    f"[{self.faucet_name}] Cloudflare "
                    f"detected on faucet page, "
                    f"attempting bypass..."
                )
                bypass_ok = (
                    await self.bypass_cloudflare_with_retry()
                )
                if not bypass_ok:
                    logger.error(
                        f"[{self.faucet_name}] Failed to "
                        f"bypass Cloudflare on faucet page"
                    )
                    return ClaimResult(
                        success=False,
                        status="Cloudflare Block",
                        next_claim_minutes=15,
                    )

            # Wait for faucet content
            try:
                logger.info(
                    f"[{self.faucet_name}] Waiting for "
                    f"faucet interface to load..."
                )
                try:
                    await self.page.wait_for_selector(
                        "#get_reward_button",
                        timeout=15000,
                    )
                    logger.info(
                        f"[{self.faucet_name}] "
                        f"Found #get_reward_button"
                    )
                except Exception:
                    await self.page.wait_for_selector(
                        "button, input[type='submit']",
                        timeout=10000,
                    )
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Faucet interface loaded"
                )
            except Exception as e:
                logger.warning(
                    f"[{self.faucet_name}] Timeout waiting "
                    f"for faucet interface: {e}"
                )

            # Balance selectors (updated 2026-01-30)
            balance_selectors = [
                ".user-balance",
                ".balance",
                "#user-balance",
                ".balance-text",
                "span.user-balance",
                ".navbar .balance",
                "[data-balance]",
                ".account-balance",
                "#balance",
                "[class*='balance']",
                ".wallet-balance",
                "span[class*='balance']:visible",
            ]
            balance = await self.get_balance(
                balance_selectors[0],
                fallback_selectors=balance_selectors[1:],
            )
            logger.info(
                f"[{self.faucet_name}] "
                f"Current balance: {balance}"
            )

            # Timer selectors (updated 2026-01-30)
            timer_selectors = [
                ".fa-clock + span",
                "#claim_timer",
                "#time",
                ".timer",
                ".countdown",
                "[data-timer]",
                "[data-countdown]",
                ".time-remaining",
                "[class*='timer']",
                "[class*='countdown']",
                "[id*='timer']",
                "span.timer:visible",
                ".claim-timer",
            ]
            wait = await self.get_timer(
                timer_selectors[0],
                fallback_selectors=timer_selectors[1:],
            )
            logger.info(
                f"[{self.faucet_name}] "
                f"Timer status: {wait} minutes"
            )

            if wait > 0:
                logger.info(
                    f"[{self.faucet_name}] Claim not "
                    f"ready, waiting {wait} minutes"
                )
                return ClaimResult(
                    success=True,
                    status="Timer Active",
                    next_claim_minutes=wait,
                    balance=balance,
                )

            await self.idle_mouse(
                duration=random.uniform(1.0, 2.0)
            )

            # Select Turnstile CAPTCHA on faucet page
            turnstile_label = self.page.locator(
                "label[for='select-turnstile']"
            )
            if await turnstile_label.count() > 0:
                logger.debug(
                    f"[{self.faucet_name}] Selecting "
                    f"Turnstile via label on faucet page"
                )
                await turnstile_label.click()
                await asyncio.sleep(1)
            else:
                turnstile_opt = self.page.locator(
                    "#select-turnstile"
                )
                if await turnstile_opt.count() > 0:
                    logger.debug(
                        f"[{self.faucet_name}] Selecting "
                        f"Turnstile via JS on faucet page"
                    )
                    await self.page.evaluate(
                        "document.getElementById("
                        "'select-turnstile').checked "
                        "= true; "
                        "change_captcha('turnstile');"
                    )
                    await asyncio.sleep(1)

            logger.info(
                f"[{self.faucet_name}] Solving CAPTCHA..."
            )
            captcha_result = (
                await self.solver.solve_captcha(self.page)
            )
            if not captcha_result:
                logger.warning(
                    f"[{self.faucet_name}] CAPTCHA solving "
                    f"failed, retrying..."
                )
                await self.random_delay(2, 4)
                captcha_result = (
                    await self.solver.solve_captcha(
                        self.page
                    )
                )
                if not captcha_result:
                    logger.error(
                        f"[{self.faucet_name}] CAPTCHA "
                        f"solving failed after retry"
                    )
                    return ClaimResult(
                        success=False,
                        status="CAPTCHA Failed",
                        next_claim_minutes=5,
                        balance=balance,
                    )

            logger.info(
                f"[{self.faucet_name}] "
                f"CAPTCHA solved successfully"
            )
            await self.idle_mouse(
                duration=random.uniform(0.5, 1.5)
            )
            await asyncio.sleep(1)

            # Try to enable the submit button
            try:
                await self.page.evaluate("""
                    const btn = document.querySelector(
                        'button[type="submit"]'
                    );
                    if (btn && btn.disabled) {
                        btn.disabled = false;
                        btn.removeAttribute('disabled');
                    }
                """)
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Manually enabled submit button"
                )
            except Exception as e:
                logger.warning(
                    f"[{self.faucet_name}] Could not "
                    f"manually enable button: {e}"
                )

            # Simulate reading before claim
            await self.simulate_reading(
                duration=random.uniform(2.0, 4.0)
            )
            if random.random() < 0.4:
                await self.natural_scroll(
                    distance=random.randint(80, 200),
                    direction=1,
                )
                await asyncio.sleep(
                    random.uniform(0.3, 0.8)
                )
            await self.thinking_pause()

            # Faucet button selectors (updated 2026-02-08)
            # Priority order: ID > data attributes > classes > text content
            faucet_btn_selectors = [
                "#get_reward_button",  # ID selector (most stable)
                "button#claim-button",
                "button#faucet_btn",
                "button[data-action='claim']",  # Data attribute (semantic, added 2026-02-08)
                "button[data-action='get-reward']",
                "button[data-role='faucet-claim']",
                "button[data-testid='claim-button']",
                "button:has-text('Get reward')",
                "button:has-text('Get Reward')",
                "button:has-text('Claim')",
                "button:has-text('claim')",
                "button:text('Get reward')",
                "button:text('Get Reward')",
                "button.btn.btn-primary:visible",
                "button.claim-btn:visible",  # Added specific claim button class
                ".claim-button",
                "button.btn:visible",
                "button[type='submit']:visible",
                ".btn.btn-primary:visible",
                "form button[type='submit']:visible",
                "button.btn:has-text('reward')",
                "input[type='submit'][value*='Claim']",
                "input[type='submit'][value*='reward']",
                "input[type='submit']:visible",
            ]

            # Debug: log all buttons on the page
            all_btn_count = (
                await self.page.locator('button').count()
            )
            input_sel = (
                'input[type="submit"], '
                'input[type="button"]'
            )
            all_input_count = (
                await self.page.locator(input_sel).count()
            )
            logger.info(
                f"[{self.faucet_name}] Page has "
                f"{all_btn_count} buttons and "
                f"{all_input_count} submit/button inputs"
            )

            if all_btn_count > 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Available buttons:"
                )
                limit = min(all_btn_count, 20)
                for i in range(limit):
                    try:
                        btn = (
                            self.page.locator('button')
                            .nth(i)
                        )
                        text = await btn.text_content()
                        id_attr = await btn.get_attribute(
                            'id'
                        )
                        cls = await btn.get_attribute(
                            'class'
                        )
                        is_vis = await btn.is_visible()
                        is_en = await btn.is_enabled()
                        cls_short = (
                            cls[:50] if cls else ""
                        )
                        logger.debug(
                            f"  [{i}] text='{text}', "
                            f"id='{id_attr}', "
                            f"class='{cls_short}', "
                            f"visible={is_vis}, "
                            f"enabled={is_en}"
                        )
                    except Exception as dbg_err:
                        logger.debug(
                            f"  [{i}] Error logging "
                            f"button: {dbg_err}"
                        )

            faucet_btn = None
            for selector in faucet_btn_selectors:
                try:
                    btn = self.page.locator(selector)
                    cnt = await btn.count()
                    logger.debug(
                        f"[{self.faucet_name}] Testing "
                        f"selector '{selector}': "
                        f"found {cnt} elements"
                    )
                    if cnt > 0:
                        try:
                            is_vis = (
                                await btn.first.is_visible(
                                    timeout=2000
                                )
                            )
                            if is_vis:
                                faucet_btn = btn
                                logger.info(
                                    f"[{self.faucet_name}]"
                                    f" Found claim button "
                                    f"with: {selector}"
                                )
                                break
                            logger.debug(
                                f"[{self.faucet_name}] "
                                f"Button found but not "
                                f"visible: {selector}"
                            )
                        except Exception as vis_err:
                            logger.debug(
                                f"[{self.faucet_name}] "
                                f"Visibility check "
                                f"failed for "
                                f"{selector}: {vis_err}"
                            )
                            continue
                except Exception as sel_err:
                    logger.debug(
                        f"[{self.faucet_name}] "
                        f"Selector '{selector}' "
                        f"failed: {sel_err}"
                    )
                    continue

            if faucet_btn and await faucet_btn.count() > 0:
                return await self._click_and_verify_claim(
                    faucet_btn, balance, balance_selectors,
                )

            # Button not found -- debug logging
            logger.warning(
                f"[{self.faucet_name}] Faucet button "
                f"not found with any selector"
            )
            await self._debug_log_page_elements()
            await self.page.screenshot(
                path=(
                    f"claim_btn_missing_"
                    f"{self.faucet_name}.png"
                ),
                full_page=True,
            )
            logger.error(
                f"[{self.faucet_name}] Screenshot saved "
                f"to claim_btn_missing_"
                f"{self.faucet_name}.png"
            )

            return ClaimResult(
                success=False,
                status="Faucet Ready but Failed",
                next_claim_minutes=5,
                balance=balance,
            )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Claim failed with error: {e}",
                exc_info=True,
            )
            await self.page.screenshot(
                path=f"error_{self.faucet_name}.png",
                full_page=True,
            )

            error_str = str(e).lower()
            net_keywords = [
                "timeout", "network", "connection",
            ]
            if any(kw in error_str for kw in net_keywords):
                logger.warning(
                    f"[{self.faucet_name}] Network error "
                    f"detected, retry in 5 minutes"
                )
                return ClaimResult(
                    success=False,
                    status=f"Network Error: {e}",
                    next_claim_minutes=5,
                )
            if "captcha" in error_str:
                logger.warning(
                    f"[{self.faucet_name}] CAPTCHA error "
                    f"detected, retry in 10 minutes"
                )
                return ClaimResult(
                    success=False,
                    status=f"CAPTCHA Error: {e}",
                    next_claim_minutes=10,
                )
            logger.error(
                f"[{self.faucet_name}] Unknown error, "
                f"retry in 30 minutes"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=30,
            )

    async def _click_and_verify_claim(
        self,
        faucet_btn: Any,
        balance: str,
        balance_selectors: list[str],
    ) -> ClaimResult:
        """Click the faucet button and verify the claim result.

        Handles the button countdown timer, clicking, and
        post-click success detection through multiple strategies
        (success messages, balance changes, URL changes).

        Args:
            faucet_btn: Playwright locator for the claim button.
            balance: Balance string before claiming.
            balance_selectors: CSS selectors for balance
                extraction.

        Returns:
            ClaimResult with claim outcome.
        """
        # Check button state before clicking
        try:
            btn_text = (
                await faucet_btn.first.text_content()
            )
            is_enabled = await faucet_btn.first.is_enabled()
            disabled_attr = (
                await faucet_btn.first.get_attribute(
                    "disabled"
                )
            )
            logger.info(
                f"[{self.faucet_name}] Button text "
                f"before click: '{btn_text}'"
            )
            logger.info(
                f"[{self.faucet_name}] Button enabled: "
                f"{is_enabled}, disabled attr: "
                f"{disabled_attr}"
            )

            if not is_enabled or disabled_attr is not None:
                await self._wait_for_button_countdown(
                    faucet_btn,
                )
        except Exception as btn_err:
            logger.warning(
                f"[{self.faucet_name}] Could not check "
                f"button state: {btn_err}"
            )

        logger.info(
            f"[{self.faucet_name}] "
            f"Clicking faucet reward button..."
        )
        await self.human_like_click(faucet_btn)
        await asyncio.sleep(1)

        # Check if button text changed after click
        try:
            btn_text_after = (
                await faucet_btn.first.text_content()
            )
            logger.info(
                f"[{self.faucet_name}] Button text "
                f"after click: '{btn_text_after}'"
            )

            if "please wait" not in btn_text_after.lower():
                logger.warning(
                    f"[{self.faucet_name}] Button text "
                    f"didn't change, trying JS click..."
                )
                await self.page.evaluate(
                    "document.querySelector("
                    "'button[type=\"submit\"]').click()"
                )
                await asyncio.sleep(2)
                btn_text_js = (
                    await faucet_btn.first.text_content()
                )
                logger.info(
                    f"[{self.faucet_name}] Button text "
                    f"after JS click: '{btn_text_js}'"
                )
        except Exception as btn_err:
            logger.warning(
                f"[{self.faucet_name}] Could not check "
                f"button text after click: {btn_err}"
            )

        await self.random_delay(1, 2)

        # Wait for "Please Wait" countdown to complete
        logger.info(
            f"[{self.faucet_name}] "
            f"Waiting for claim processing..."
        )
        try:
            await self.page.wait_for_function(
                """() => {
                    const btn = document.querySelector(
                        'button[type="submit"]'
                    );
                    return btn && !btn.textContent
                        .includes('Please Wait');
                }""",
                timeout=15000,
            )
            logger.info(
                f"[{self.faucet_name}] "
                f"Claim processing timer completed"
            )

            final_text = await self.page.locator(
                "button[type='submit']"
            ).first.text_content()
            logger.info(
                f"[{self.faucet_name}] Button text "
                f"after processing: '{final_text}'"
            )
        except Exception as wait_err:
            logger.debug(
                f"[{self.faucet_name}] "
                f"Wait for timer error: {wait_err}"
            )

        await self.human_wait(3)

        # Capture page state after claim
        logger.info(
            f"[{self.faucet_name}] "
            f"Checking claim result..."
        )
        current_url = self.page.url
        page_title = await self.page.title()
        logger.info(
            f"[{self.faucet_name}] "
            f"Current URL: {current_url}"
        )
        logger.info(
            f"[{self.faucet_name}] "
            f"Page title: {page_title}"
        )

        # Check page text for success indicators
        result = await self._check_page_text_success(
            balance_selectors,
        )
        if result:
            return result

        # Check DOM for success elements
        success_found, success_msg_text = (
            await self._check_success_selectors()
        )

        # Check balance change
        if not success_found:
            success_found, balance = (
                await self._check_balance_change(
                    balance, balance_selectors,
                )
            )

        # Check URL change
        if not success_found:
            if any(
                ind in current_url.lower()
                for ind in [
                    'success', 'claimed', 'dashboard',
                ]
            ):
                logger.info(
                    f"[{self.faucet_name}] Claim success "
                    f"detected via URL: {current_url}"
                )
                success_found = True

        # Check if button disappeared
        if not success_found:
            try:
                btn_loc = self.page.locator(
                    "button:has-text('Get reward')"
                )
                btn_gone = await btn_loc.count() == 0
                if btn_gone:
                    logger.info(
                        f"[{self.faucet_name}] Claim "
                        f"button disappeared -- "
                        f"assuming success"
                    )
                    success_found = True
            except Exception:
                pass

        if success_found:
            new_balance = await self.get_balance(
                balance_selectors[0],
                fallback_selectors=balance_selectors[1:],
            )
            logger.info(
                f"[{self.faucet_name}] "
                f"Final balance: {new_balance}"
            )

            amount = "unknown"
            if success_msg_text:
                match = re.search(
                    r'(\d+\.?\d*)\s*(satoshi|sat|btc)',
                    success_msg_text.lower(),
                )
                if match:
                    amount = match.group(1)

            # Claim shortlinks in parallel
            enable_sl = getattr(
                self.settings, 'enable_shortlinks', True,
            )
            if enable_sl:
                try:
                    logger.info(
                        f"[{self.faucet_name}] Starting "
                        f"shortlink claiming..."
                    )
                    asyncio.create_task(
                        self.claim_shortlinks(
                            separate_context=True,
                        )
                    )
                except Exception as sl_err:
                    logger.debug(
                        f"[{self.faucet_name}] Shortlink "
                        f"task creation failed: {sl_err}"
                    )

            return ClaimResult(
                success=True,
                status="Claimed",
                next_claim_minutes=30,
                amount=amount,
                balance=new_balance,
            )

        # No success indicator found
        logger.warning(
            f"[{self.faucet_name}] Claim verification "
            f"failed -- no success indicator found"
        )
        try:
            visible = await self.page.evaluate(
                "() => document.body.innerText"
            )
            logger.info(
                f"[{self.faucet_name}] Page visible text "
                f"(first 500 chars): {visible[:500]}"
            )
        except Exception:
            pass

        await self.page.screenshot(
            path=f"claim_failed_{self.faucet_name}.png",
            full_page=True,
        )

        return ClaimResult(
            success=False,
            status="Faucet Ready but Failed",
            next_claim_minutes=5,
            balance=balance,
        )

    async def _wait_for_button_countdown(
        self, faucet_btn: Any,
    ) -> None:
        """Wait for the FireFaucet button countdown to finish.

        FireFaucet has a JavaScript countdown timer (typically
        9 seconds) that keeps the button disabled after page
        load.  This method waits for it to complete, or
        force-enables the button as a last resort.

        Args:
            faucet_btn: Playwright locator for the button.
        """
        logger.info(
            f"[{self.faucet_name}] Button is disabled "
            f"-- waiting for countdown timer..."
        )
        try:
            await self.page.wait_for_function(
                """() => {
                    const btn =
                        document.getElementById(
                            'get_reward_button'
                        ) || document.querySelector(
                            'button[type="submit"]'
                        );
                    if (!btn) return false;
                    return !btn.disabled
                        && !btn.hasAttribute('disabled');
                }""",
                timeout=30000,
            )
            logger.info(
                f"[{self.faucet_name}] Countdown "
                f"completed -- button enabled"
            )
            await asyncio.sleep(1)
        except Exception as wait_err:
            logger.warning(
                f"[{self.faucet_name}] Countdown wait "
                f"timeout: {wait_err}"
            )
            try:
                await self.page.evaluate("""
                    const btn =
                        document.getElementById(
                            'get_reward_button'
                        ) || document.querySelector(
                            'button[type="submit"]'
                        );
                    if (btn) {
                        btn.disabled = false;
                        btn.removeAttribute('disabled');
                    }
                """)
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Force-enabled button after timeout"
                )
            except Exception:
                pass

        # Re-check button state
        is_en = await faucet_btn.first.is_enabled()
        btn_text = await faucet_btn.first.text_content()
        logger.info(
            f"[{self.faucet_name}] Button after wait: "
            f"enabled={is_en}, text='{btn_text}'"
        )

    async def _check_page_text_success(
        self, balance_selectors: list[str],
    ) -> ClaimResult | None:
        """Check page text for success phrases after claiming.

        Scans ``document.body.innerText`` for known success
        phrases and extracts the claimed amount if found.

        Args:
            balance_selectors: CSS selectors for balance
                extraction.

        Returns:
            A ``ClaimResult`` on success, or ``None`` if no
            success phrase was found.
        """
        try:
            page_text = await self.page.evaluate(
                "() => document.body.innerText"
            )
            text_lower = page_text.lower()

            success_phrases = [
                'claimed successfully',
                'reward received',
                'congratulations',
                'success',
                'you got',
                'you earned',
                'you received',
                'claim successful',
                'reward added',
                'balance updated',
            ]

            for phrase in success_phrases:
                if phrase in text_lower:
                    logger.info(
                        f"[{self.faucet_name}] Success "
                        f"phrase found: '{phrase}'"
                    )
                    amount = "unknown"
                    match = re.search(
                        r'(\d+\.?\d*)'
                        r'\s*(satoshi|sat|btc)',
                        text_lower,
                    )
                    if match:
                        amount = match.group(1)
                        logger.info(
                            f"[{self.faucet_name}] "
                            f"Amount: {amount}"
                        )

                    new_bal = await self.get_balance(
                        balance_selectors[0],
                        fallback_selectors=(
                            balance_selectors[1:]
                        ),
                    )
                    return ClaimResult(
                        success=True,
                        status="Claimed",
                        next_claim_minutes=30,
                        amount=amount,
                        balance=new_bal,
                    )
        except Exception as text_err:
            logger.debug(
                f"[{self.faucet_name}] "
                f"Page text check error: {text_err}"
            )
        return None

    async def _check_success_selectors(
        self,
    ) -> tuple[bool, str]:
        """Check DOM for success-indicator elements.

        Scans a prioritised list of CSS selectors for visible
        elements whose text content indicates a successful claim.

        Returns:
            A ``(found, message_text)`` tuple.
        """
        success_selectors = [
            ".success_msg",
            ".alert-success",
            ".toast-success",
            "[class*='success']",
            ".claim-success",
            ".reward-success",
            ".swal2-success",
            ".swal2-popup:has(.swal2-success-ring)",
            ".swal2-popup",
            ".modal:visible",
            "[class*='claimed']",
            "[class*='reward']",
            ".toast:visible",
            ".notification:visible",
            "div:has-text('success')",
            "div:has-text('claimed')",
            "div:has-text('reward')",
        ]
        err_words = [
            'error', 'fail', 'wait',
            'timer', 'please try',
        ]

        for sel in success_selectors:
            try:
                locator = self.page.locator(sel)
                cnt = await locator.count()
                if cnt == 0:
                    continue
                for i in range(cnt):
                    elem = locator.nth(i)
                    if not await elem.is_visible():
                        continue
                    msg = (
                        await elem.text_content() or ""
                    )
                    msg_lower = msg.lower()
                    if msg and not any(
                        w in msg_lower for w in err_words
                    ):
                        logger.info(
                            f"[{self.faucet_name}] "
                            f"Success via {sel}: "
                            f"{msg[:150]}"
                        )
                        return True, msg
            except Exception as e:
                logger.debug(
                    f"[{self.faucet_name}] "
                    f"Success selector {sel} "
                    f"error: {e}"
                )
                continue

        return False, ""

    async def _check_balance_change(
        self,
        old_balance: str,
        balance_selectors: list[str],
    ) -> tuple[bool, str]:
        """Detect a balance change as a claim success signal.

        Args:
            old_balance: Balance string before claiming.
            balance_selectors: CSS selectors for balance
                extraction.

        Returns:
            A ``(changed, current_balance)`` tuple.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] No success msg, "
                f"checking balance change..."
            )
            await asyncio.sleep(2)
            new_bal = await self.get_balance(
                balance_selectors[0],
                fallback_selectors=balance_selectors[1:],
            )
            logger.info(
                f"[{self.faucet_name}] Old balance: "
                f"{old_balance}, New: {new_bal}"
            )

            if (
                new_bal
                and new_bal != "0"
                and new_bal != old_balance
            ):
                logger.info(
                    f"[{self.faucet_name}] Claim success "
                    f"via balance change: "
                    f"{old_balance} -> {new_bal}"
                )
                return True, new_bal
        except Exception as bal_err:
            logger.debug(
                f"[{self.faucet_name}] "
                f"Balance check error: {bal_err}"
            )
        return False, old_balance

    async def _debug_log_page_elements(self) -> None:
        """Log buttons, links, and error elements on the page.

        Used for debugging when the faucet claim button cannot
        be found.
        """
        try:
            page_url = self.page.url
            logger.error(
                f"[{self.faucet_name}] "
                f"Current URL: {page_url}"
            )

            if "/faucet" not in page_url:
                logger.error(
                    f"[{self.faucet_name}] Not on faucet "
                    f"page! Redirected to: {page_url}"
                )

            btn_sel = (
                "button, input[type='submit']"
            )
            all_buttons = (
                await self.page.locator(btn_sel).all()
            )
            logger.error(
                f"[{self.faucet_name}] DEBUG: Found "
                f"{len(all_buttons)} buttons/inputs"
            )
            for idx, btn in enumerate(all_buttons[:10]):
                try:
                    txt = (
                        await btn.text_content() or ""
                    )
                    bid = (
                        await btn.get_attribute("id")
                        or ""
                    )
                    bcls = (
                        await btn.get_attribute("class")
                        or ""
                    )
                    btype = (
                        await btn.get_attribute("type")
                        or ""
                    )
                    bval = (
                        await btn.get_attribute("value")
                        or ""
                    )
                    vis = await btn.is_visible()
                    logger.error(
                        f"[{self.faucet_name}]   "
                        f"[{idx + 1}] "
                        f"text='{txt.strip()[:50]}' "
                        f"id='{bid}' class='{bcls}' "
                        f"type='{btype}' "
                        f"value='{bval}' "
                        f"visible={vis}"
                    )
                except Exception as btn_err:
                    logger.debug(
                        f"[{self.faucet_name}] Could not "
                        f"read button {idx + 1}: "
                        f"{btn_err}"
                    )

            link_sel = "a.btn, a[class*='button']"
            all_links = (
                await self.page.locator(link_sel).all()
            )
            if all_links:
                logger.error(
                    f"[{self.faucet_name}] DEBUG: Found "
                    f"{len(all_links)} link-buttons"
                )
                for idx, link in enumerate(
                    all_links[:5]
                ):
                    try:
                        ltxt = (
                            await link.text_content()
                            or ""
                        )
                        href = (
                            await link.get_attribute(
                                "href"
                            )
                            or ""
                        )
                        lcls = (
                            await link.get_attribute(
                                "class"
                            )
                            or ""
                        )
                        vis = await link.is_visible()
                        logger.error(
                            f"[{self.faucet_name}]   "
                            f"Link[{idx + 1}] "
                            f"text='{ltxt.strip()[:50]}'"
                            f" href='{href}' "
                            f"class='{lcls}' "
                            f"visible={vis}"
                        )
                    except Exception as lnk_err:
                        logger.debug(
                            f"[{self.faucet_name}] "
                            f"Could not read "
                            f"link {idx + 1}: {lnk_err}"
                        )

            err_sel = (
                ".alert, .error, .warning, "
                "[class*='error'], [class*='alert']"
            )
            error_msgs = (
                await self.page.locator(err_sel).all()
            )
            if error_msgs:
                logger.error(
                    f"[{self.faucet_name}] Found "
                    f"{len(error_msgs)} error/alert "
                    f"elements:"
                )
                for idx, msg in enumerate(
                    error_msgs[:3]
                ):
                    try:
                        mtxt = (
                            await msg.text_content()
                            or ""
                        )
                        logger.error(
                            f"[{self.faucet_name}]   "
                            f"Alert[{idx + 1}]: "
                            f"{mtxt.strip()[:100]}"
                        )
                    except Exception:
                        pass

        except Exception as dbg_err:
            logger.error(
                f"[{self.faucet_name}] Could not "
                f"enumerate page elements: {dbg_err}"
            )

    async def claim_shortlinks(
        self, separate_context: bool = True,
    ) -> ClaimResult:
        """Claim available shortlinks on FireFaucet.

        Args:
            separate_context: If True, use a separate browser
                context to avoid interfering with the main
                claim session.

        Returns:
            ClaimResult with shortlink earnings.
        """
        shortlink_earnings = 0.0
        shortlinks_claimed = 0

        try:
            logger.info(
                f"[{self.faucet_name}] "
                f"Checking Shortlinks..."
            )

            # Use separate context if requested
            if separate_context and hasattr(
                self, 'browser_manager'
            ):
                logger.debug(
                    f"[{self.faucet_name}] Using "
                    f"separate context for shortlinks"
                )
                browser = self.page.context.browser
                context = await browser.new_context()
                page = await context.new_page()
                cookies = await self.page.context.cookies()
                await context.add_cookies(cookies)
            else:
                page = self.page

            await page.goto(f"{self.base_url}/shortlinks")

            # FireFaucet Shortlink structure
            links = page.locator(
                "a.btn.btn-primary:has-text('Visit Link')"
            )
            if await links.count() == 0:
                links = page.locator(
                    ".card-body a[href*='/shortlink/']"
                )

            count = await links.count()
            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"No shortlinks available."
                )
                if (
                    separate_context
                    and 'context' in locals()
                ):
                    await context.close()
                return ClaimResult(
                    success=True,
                    status="No shortlinks",
                    next_claim_minutes=120,
                    amount=0.0,
                )

            logger.info(
                f"[{self.faucet_name}] Found {count} "
                f"shortlinks. Processing top 3..."
            )

            blocker = getattr(
                page, "resource_blocker",
                getattr(
                    page.context,
                    "resource_blocker",
                    None,
                ),
            )
            solver = ShortlinkSolver(
                page,
                blocker=blocker,
                captcha_solver=self.solver,
            )

            for i in range(min(3, count)):
                try:
                    # Re-query links
                    links = page.locator(
                        "a.btn.btn-primary"
                        ":has-text('Visit Link')"
                    )
                    if await links.count() == 0:
                        links = page.locator(
                            ".card-body "
                            "a[href*='/shortlink/']"
                        )

                    if await links.count() <= i:
                        break

                    reward_text = (
                        await links.nth(i).get_attribute(
                            "data-reward"
                        )
                        or "0"
                    )

                    await links.nth(i).click()
                    await page.wait_for_load_state()

                    cap_sel = (
                        "iframe[src*='turnstile'], "
                        "iframe[src*='recaptcha']"
                    )
                    if await page.query_selector(cap_sel):
                        await self.solver.solve_captcha(
                            page,
                        )

                    success_pats = [
                        "firefaucet.win/shortlinks",
                        "/shortlinks",
                    ]
                    if await solver.solve(
                        page.url,
                        success_patterns=success_pats,
                    ):
                        logger.info(
                            f"[{self.faucet_name}] "
                            f"Shortlink {i + 1} claimed!"
                        )
                        shortlinks_claimed += 1
                        try:
                            shortlink_earnings += float(
                                reward_text,
                            )
                        except ValueError:
                            shortlink_earnings += 0.0001
                        await page.goto(
                            f"{self.base_url}/shortlinks"
                        )
                    else:
                        logger.warning(
                            f"[{self.faucet_name}] "
                            f"Shortlink {i + 1} failed"
                        )
                        await page.goto(
                            f"{self.base_url}/shortlinks"
                        )

                except Exception as link_err:
                    logger.error(
                        f"[{self.faucet_name}] Error on "
                        f"shortlink {i + 1}: {link_err}"
                    )
                    continue

            # Close separate context if used
            if (
                separate_context
                and 'context' in locals()
            ):
                await context.close()

            # Track earnings in analytics
            if shortlink_earnings > 0:
                try:
                    from core.analytics import get_tracker
                    tracker = get_tracker()
                    tracker.record_claim(
                        faucet=self.faucet_name,
                        success=True,
                        amount=shortlink_earnings,
                    )
                except Exception as analytics_err:
                    logger.debug(
                        f"Analytics tracking "
                        f"failed: {analytics_err}"
                    )

            return ClaimResult(
                success=True,
                status=(
                    f"Claimed {shortlinks_claimed} "
                    f"shortlinks"
                ),
                next_claim_minutes=120,
                amount=shortlink_earnings,
            )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Shortlink error: {e}"
            )
            if (
                separate_context
                and 'context' in locals()
            ):
                try:
                    await context.close()
                except Exception:
                    pass
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=120,
            )
