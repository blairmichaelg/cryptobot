"""CoinPayU faucet bot for Cryptobot Gen 3.0.

Implements ``coinpayu.com`` -- a PTC (paid-to-click) and faucet site.
Features:
    * PTC ad viewing (primary earning method).
    * Faucet claims with timer scheduling.
    * Shortlink traversal for bonus earnings.
    * Multi-currency withdrawal support.

Claim interval: varies per activity.
"""

import asyncio
import logging
import random
import re
from typing import Any, List, Optional

from .base import ClaimResult, FaucetBot

logger = logging.getLogger(__name__)


class CoinPayUBot(FaucetBot):
    """CoinPayU PTC and faucet bot.

    Handles PTC ad viewing, faucet claiming, shortlink solving, and
    multi-currency withdrawals.  Strips email aliases (plus-addressing)
    since CoinPayU blocks ``+`` in email addresses.
    """

    def __init__(
        self,
        settings: Any,
        page: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize CoinPayU bot.

        Args:
            settings: BotSettings configuration object.
            page: Playwright Page instance.
            **kwargs: Additional arguments passed to FaucetBot.
        """
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "CoinPayU"
        self.base_url = "https://www.coinpayu.com"

    async def is_logged_in(self) -> bool:
        """Check whether the user is currently logged in.

        Returns:
            True if a dashboard URL or logout link is detected.
        """
        if "dashboard" in self.page.url:
            return True
        logout = await self.page.query_selector(
            "a[href*='logout']"
        )
        return logout is not None

    async def claim_shortlinks(
        self, separate_context: bool = True,
    ) -> ClaimResult:
        """Claim available shortlinks on CoinPayU.

        Args:
            separate_context: Use separate browser context to
                avoid interference.

        Returns:
            ClaimResult with shortlink earnings.
        """
        shortlink_earnings = 0.0
        shortlinks_claimed = 0

        try:
            logger.info(
                f"[{self.faucet_name}] Checking shortlinks..."
            )

            # Use separate context if requested
            if (
                separate_context
                and hasattr(self, 'browser_manager')
            ):
                context = (
                    await self.page.context.browser.new_context()
                )
                page = await context.new_page()
                cookies = await self.page.context.cookies()
                await context.add_cookies(cookies)
            else:
                page = self.page

            await page.goto(
                f"{self.base_url}/dashboard/shortlinks"
            )
            await self.handle_cloudflare(max_wait_seconds=20)

            # CoinPayU shortlink selectors
            links = page.locator(
                "a.shortlink-card, "
                "a[href*='visit']:has-text('Visit'), "
                "button:has-text('Visit Link')"
            )
            count = await links.count()

            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    "No shortlinks available"
                )
                if separate_context and 'context' in locals():
                    await context.close()
                return ClaimResult(
                    success=True,
                    status="No shortlinks",
                    next_claim_minutes=120,
                )

            logger.info(
                f"[{self.faucet_name}] Found {count} "
                "shortlinks, processing top 3..."
            )

            from solvers.shortlink import ShortlinkSolver
            blocker = getattr(page, "resource_blocker", None)
            solver = ShortlinkSolver(
                page,
                blocker=blocker,
                captcha_solver=self.solver,
            )

            for i in range(min(3, count)):
                try:
                    links = page.locator(
                        "a.shortlink-card, "
                        "a[href*='visit']:has-text('Visit')"
                    )
                    if await links.count() <= i:
                        break

                    await self.human_like_click(links.nth(i))
                    await page.wait_for_load_state()

                    # Handle Cloudflare and captchas
                    await self.handle_cloudflare(
                        max_wait_seconds=15,
                    )
                    captcha_frame = await page.query_selector(
                        "iframe[src*='turnstile'], "
                        "iframe[src*='hcaptcha']"
                    )
                    if captcha_frame:
                        if not await self.solver.solve_captcha(page):
                            logger.warning(f"[{self.faucet_name}] Shortlink CAPTCHA solve failed")

                    # Solve shortlink
                    success_pats = [
                        "coinpayu.com", "/shortlinks",
                    ]
                    if await solver.solve(
                        page.url,
                        success_patterns=success_pats,
                    ):
                        logger.info(
                            f"[{self.faucet_name}] "
                            f"Shortlink {i + 1} claimed"
                        )
                        shortlinks_claimed += 1
                        shortlink_earnings += 0.0001

                    await page.goto(
                        f"{self.base_url}/dashboard/shortlinks"
                    )

                except Exception as link_err:
                    logger.error(
                        f"[{self.faucet_name}] "
                        f"Shortlink {i + 1} error: {link_err}"
                    )
                    continue

            if separate_context and 'context' in locals():
                await context.close()

            # Track in analytics
            if shortlink_earnings > 0:
                try:
                    from core.analytics import get_tracker
                    tracker = get_tracker()
                    tracker.record_claim(
                        faucet=self.faucet_name,
                        success=True,
                        amount=shortlink_earnings,
                    )
                except Exception:
                    pass

            return ClaimResult(
                success=True,
                status=(
                    f"Claimed {shortlinks_claimed} shortlinks"
                ),
                next_claim_minutes=120,
                amount=shortlink_earnings,
            )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] Shortlink error: {e}"
            )
            if separate_context and 'context' in locals():
                try:
                    await context.close()
                except Exception:
                    pass
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=120,
            )

    async def login(self) -> bool:
        """Perform login to CoinPayU with stealth.

        Uses human-like typing and robust error handling with
        retry logic.

        Returns:
            True if login successful, False otherwise.
        """
        if (
            hasattr(self, 'settings_account_override')
            and self.settings_account_override
        ):
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("coinpayu")

        if not creds:
            logger.error(
                f"[{self.faucet_name}] No credentials found."
            )
            return False

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"[{self.faucet_name}] Navigating to "
                    f"login... (Attempt "
                    f"{attempt + 1}/{max_retries})"
                )
                timeout_ms = getattr(
                    self.settings, "timeout", 60000,
                )
                await self.safe_navigate(
                    f"{self.base_url}/login",
                    timeout=timeout_ms,
                )

                # Handle Cloudflare challenge if present
                await self.handle_cloudflare(
                    max_wait_seconds=30,
                )

                if "dashboard" in self.page.url:
                    logger.info(
                        f"[{self.faucet_name}] "
                        "Already logged in."
                    )
                    return True

                # Accept cookies if present
                await self.close_popups()

                # Warm up page with natural browsing behavior
                await self.warm_up_page()

                # Add human-like delay before interaction
                await self.idle_mouse(duration=1.0)

                logger.info(
                    f"[{self.faucet_name}] "
                    "Filling credentials..."
                )
                # CoinPayU blocks email aliases with '+'
                base_email = self.strip_email_alias(
                    creds['username'],
                )

                email_selectors = [
                    'input[placeholder="Email"]',
                    'input[type="email"]',
                    'input[name="email"]',
                    'input#email',
                    'input[name="login"]',
                ]
                password_selectors = [
                    'input[placeholder="Password"]',
                    'input[type="password"]',
                    'input[name="password"]',
                    'input#password',
                ]

                email_field = None
                for selector in email_selectors:
                    try:
                        loc = self.page.locator(selector)
                        if (
                            await loc.count() > 0
                            and await loc.first.is_visible()
                        ):
                            email_field = loc.first
                            break
                    except Exception:
                        continue

                password_field = None
                for selector in password_selectors:
                    try:
                        loc = self.page.locator(selector)
                        if (
                            await loc.count() > 0
                            and await loc.first.is_visible()
                        ):
                            password_field = loc.first
                            break
                    except Exception:
                        continue

                if not email_field or not password_field:
                    logger.warning(
                        f"[{self.faucet_name}] "
                        "Login fields not found"
                    )
                    continue

                # Use human_type for stealth
                await self.human_type(
                    email_field, base_email,
                    delay_min=80, delay_max=150,
                )
                await self.random_delay(0.5, 1.0)
                await self.human_type(
                    password_field, creds['password'],
                    delay_min=80, delay_max=150,
                )

                # Small human-like pause
                await self.random_delay(1.0, 2.0)

                # Check for Cloudflare Turnstile
                turnstile_sel = (
                    "#turnstile-container, .cf-turnstile"
                )
                if await self.page.locator(
                    turnstile_sel
                ).count() > 0:
                    logger.info(
                        f"[{self.faucet_name}] "
                        "Cloudflare Turnstile detected."
                    )

                # Solve any CAPTCHA present
                logger.info(
                    f"[{self.faucet_name}] "
                    "Checking for CAPTCHA..."
                )
                captcha_solved = (
                    await self.solver.solve_captcha(self.page)
                )
                if captcha_solved:
                    logger.info(
                        f"[{self.faucet_name}] "
                        "CAPTCHA solved successfully."
                    )
                    await self.random_delay(0.5, 1.0)

                # After CAPTCHA solve, DOM may have been
                # rebuilt.  Re-query the login button with
                # extended selectors and a fresh DOM check.
                await self.thinking_pause()
                await asyncio.sleep(1)

                # Click Login with multiple fallback selectors
                login_selectors = [
                    'button.btn-primary:has-text("Login")',
                    'button.btn-primary:has-text("Log in")',
                    'button:has-text("Login")',
                    'button:has-text("Log in")',
                    'button[type="submit"]',
                    'input[type="submit"]',
                    '#login-button',
                    '.login-btn',
                    'form button.btn-primary',
                    'form button.btn',
                    'button.btn-primary',
                ]

                login_btn = None
                for selector in login_selectors:
                    try:
                        loc = self.page.locator(selector)
                        if (
                            await loc.count() > 0
                            and await loc.first.is_visible(
                                timeout=2000,
                            )
                        ):
                            login_btn = loc.first
                            logger.info(
                                f"[{self.faucet_name}] "
                                "Found login button "
                                f"with: {selector}"
                            )
                            break
                    except Exception:
                        continue

                if login_btn:
                    logger.info(
                        f"[{self.faucet_name}] "
                        "Clicking login button..."
                    )
                    await self.human_like_click(login_btn)
                else:
                    logger.warning(
                        f"[{self.faucet_name}] Login button "
                        "not found, trying form submit..."
                    )
                    # Last resort: submit via JavaScript
                    try:
                        await self.page.evaluate("""
                            const forms =
                                document.querySelectorAll(
                                    'form'
                                );
                            for (const form of forms) {
                                const emailInput =
                                    form.querySelector(
                                        'input[type="email"],'
                                        + ' input[name="email"]'
                                    );
                                if (emailInput) {
                                    form.submit();
                                    break;
                                }
                            }
                        """)
                    except Exception:
                        logger.error(
                            f"[{self.faucet_name}] "
                            "Form submit fallback also failed"
                        )
                        continue

                # Check for "Proxy detected" error
                await self.random_delay(1.0, 2.0)
                error_msg = self.page.locator(
                    ".alert-div.alert-red"
                )
                if (
                    await error_msg.count() > 0
                    and await error_msg.is_visible()
                ):
                    text = await error_msg.inner_text()
                    if "Proxy" in text or "VPN" in text:
                        logger.error(
                            f"[{self.faucet_name}] "
                            f"Login Blocked: {text}"
                        )
                        return False

                # Wait for redirect to dashboard
                try:
                    await self.page.wait_for_url(
                        "**/dashboard**", timeout=15000,
                    )
                    logger.info(
                        f"[{self.faucet_name}] "
                        "Login successful (URL redirect)."
                    )
                    return True
                except Exception:
                    # URL check failed, try other indicators
                    await asyncio.sleep(2)
                    if await self.is_logged_in():
                        logger.info(
                            f"[{self.faucet_name}] Login "
                            "successful (session detected)."
                        )
                        return True
                    # Check for error messages
                    try:
                        error_el = self.page.locator(
                            ".alert-danger, "
                            ".alert-div.alert-red, "
                            ".error-message"
                        )
                        if (
                            await error_el.count() > 0
                            and await error_el.first
                            .is_visible()
                        ):
                            error_text = (
                                await error_el.first
                                .text_content()
                            )
                            logger.error(
                                f"[{self.faucet_name}] "
                                f"Login error: {error_text}"
                            )
                            low = error_text.lower()
                            if (
                                "proxy" in low
                                or "vpn" in low
                            ):
                                return False
                    except Exception:
                        pass
                    logger.warning(
                        f"[{self.faucet_name}] Login state "
                        f"unclear on attempt {attempt + 1}"
                    )

            except asyncio.TimeoutError:
                logger.warning(
                    f"[{self.faucet_name}] Login timeout "
                    f"on attempt {attempt + 1}"
                )
                if attempt < max_retries - 1:
                    await self.random_delay(2.0, 4.0)
                    continue
            except Exception as e:
                logger.error(
                    f"[{self.faucet_name}] Login failed "
                    f"on attempt {attempt + 1}: {e}"
                )
                if attempt < max_retries - 1:
                    await self.random_delay(2.0, 4.0)
                    continue

        logger.error(
            f"[{self.faucet_name}] Login failed "
            f"after {max_retries} attempts"
        )
        return False

    async def claim(self) -> ClaimResult:
        """Faucet claim for multiple coins (up to 4 per hour).

        Returns:
            ClaimResult with success status, message, next
            claim time, and balance.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            logger.info(
                f"[{self.faucet_name}] "
                "Starting claim process..."
            )

            # Navigate to dashboard to get balance
            await self.safe_navigate(
                f"{self.base_url}/dashboard", timeout=30000,
            )
            await self.handle_cloudflare(max_wait_seconds=20)

            # Extract main dashboard balance
            balance = await self.get_balance(
                ".v2-dashboard-card-value, "
                ".user-balance, .balance-text"
            )
            logger.info(
                f"[{self.faucet_name}] "
                f"Current balance: {balance}"
            )

            # Navigate to faucet page
            logger.info(
                f"[{self.faucet_name}] "
                "Navigating to faucet page..."
            )
            await self.safe_navigate(
                f"{self.base_url}/dashboard/faucet",
                timeout=30000,
            )
            await self.random_delay(1.0, 2.0)

            # Simulate natural page engagement
            await self.simulate_reading(
                duration=random.uniform(2.0, 3.5),
            )
            if random.random() < 0.4:
                await self.natural_scroll(
                    distance=random.randint(100, 250),
                    direction=1,
                )
                await asyncio.sleep(
                    random.uniform(0.3, 0.8),
                )

            # Check for timer first
            timer_minutes = await self.get_timer(
                ".timer, .countdown, "
                "[id*='timer'], [class*='timer']",
                fallback_selectors=[
                    "[data-time]", ".time-left",
                ],
            )

            if timer_minutes > 0:
                logger.info(
                    f"[{self.faucet_name}] Claim not ready."
                    f" Timer: {timer_minutes:.1f} minutes"
                )
                return ClaimResult(
                    success=False,
                    status=(
                        f"Timer active: {timer_minutes:.1f}"
                        " minutes remaining"
                    ),
                    next_claim_minutes=timer_minutes,
                    balance=balance,
                )

            # Find all claim buttons (target top 4 coins)
            claim_btns = self.page.locator(
                ".btn-primary:has-text('Claim'), "
                "button:has-text('Claim')"
            )
            count = await claim_btns.count()
            logger.info(
                f"[{self.faucet_name}] "
                f"Found {count} claimable coins"
            )

            if count == 0:
                logger.warning(
                    f"[{self.faucet_name}] "
                    "No claim buttons available"
                )
                return ClaimResult(
                    success=False,
                    status="No claims available",
                    next_claim_minutes=60,
                    balance=balance,
                )

            claimed = 0
            failed = 0
            max_claims = min(4, count)

            for i in range(max_claims):
                try:
                    logger.info(
                        f"[{self.faucet_name}] Claiming "
                        f"coin {i + 1}/{max_claims}..."
                    )

                    # Re-query list to handle DOM updates
                    claim_btns = self.page.locator(
                        ".btn-primary:has-text('Claim'), "
                        "button:has-text('Claim')"
                    )
                    if await claim_btns.count() == 0:
                        logger.warning(
                            f"[{self.faucet_name}] "
                            "No more claim buttons available"
                        )
                        break

                    # Add human-like delay
                    await self.idle_mouse(
                        duration=random.uniform(0.5, 1.5),
                    )

                    await self.human_like_click(
                        claim_btns.nth(i),
                    )
                    await self.page.wait_for_load_state(
                        "domcontentloaded", timeout=15000,
                    )
                    await self.random_delay(1.0, 2.0)

                    # Secondary claim page
                    final_btn = self.page.locator(
                        "#claim-now, "
                        ".btn-primary:has-text('Claim Now')"
                    )
                    if await final_btn.count() > 0:
                        # Simulate reading before claiming
                        await self.simulate_reading(
                            duration=random.uniform(1.0, 2.0),
                        )
                        await self.thinking_pause()

                        await self.human_like_click(final_btn)
                        await self.random_delay(2.0, 4.0)

                        # Watch for CAPTCHA
                        logger.info(
                            f"[{self.faucet_name}] "
                            "Checking for CAPTCHA..."
                        )
                        captcha_result = (
                            await self.solver.solve_captcha(
                                self.page,
                            )
                        )
                        if captcha_result:
                            logger.info(
                                f"[{self.faucet_name}] "
                                "CAPTCHA solved for "
                                f"claim {i + 1}"
                            )
                            await self.random_delay(1.0, 2.0)

                        # Final "Claim Now" button after timer
                        confirm_btn = self.page.locator(
                            ".btn-primary:has-text("
                            "'Claim Now')"
                        )
                        if await confirm_btn.count() > 0:
                            await self.human_like_click(
                                confirm_btn,
                            )
                            await self.random_delay(2.0, 4.0)
                            claimed += 1
                            logger.info(
                                f"[{self.faucet_name}] "
                                "Successfully claimed "
                                f"coin {i + 1}"
                            )
                        else:
                            # Assume success if button gone
                            claimed += 1
                            logger.info(
                                f"[{self.faucet_name}] "
                                f"Claim {i + 1} appears "
                                "successful"
                            )
                    else:
                        logger.warning(
                            f"[{self.faucet_name}] Claim "
                            "button not found for "
                            f"coin {i + 1}"
                        )
                        failed += 1

                    # Go back to faucet list
                    await self.page.goto(
                        f"{self.base_url}/dashboard/faucet",
                        timeout=15000,
                    )
                    await self.random_delay(1.0, 2.0)

                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{self.faucet_name}] Timeout "
                        f"claiming coin {i + 1}"
                    )
                    failed += 1
                except Exception as e:
                    logger.error(
                        f"[{self.faucet_name}] Error "
                        f"claiming coin {i + 1}: {e}"
                    )
                    failed += 1

            # Calculate elapsed time for metrics
            elapsed_time = (
                asyncio.get_event_loop().time() - start_time
            )
            logger.info(
                f"[{self.faucet_name}] Claim session "
                f"completed in {elapsed_time:.1f}s: "
                f"{claimed} claimed, {failed} failed"
            )

            # Get updated balance
            final_balance = await self.get_balance(
                ".v2-dashboard-card-value, "
                ".user-balance, .balance-text"
            )

            # Next claim time (hourly for faucets)
            next_claim = 60.0

            if claimed > 0:
                return ClaimResult(
                    success=True,
                    status=(
                        f"Claimed {claimed} coins "
                        f"({failed} failed)"
                    ),
                    next_claim_minutes=next_claim,
                    balance=final_balance,
                )
            return ClaimResult(
                success=False,
                status=(
                    f"Failed to claim any coins "
                    f"({failed} attempts)"
                ),
                next_claim_minutes=30,
                balance=final_balance,
            )

        except Exception as e:
            elapsed_time = (
                asyncio.get_event_loop().time() - start_time
            )
            logger.error(
                f"[{self.faucet_name}] Claim error "
                f"after {elapsed_time:.1f}s: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {str(e)[:100]}",
                next_claim_minutes=60,
            )

    def get_jobs(self) -> List[Any]:
        """Return CoinPayU-specific jobs for the scheduler.

        Returns:
            List of Job objects for faucet claim, PTC ads,
            consolidation, and withdrawal.
        """
        from core.orchestrator import Job
        import time

        jobs: List[Any] = []
        f_type = self.faucet_name.lower()

        # 1. Faucet Claim (Hourly)
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=f_type,
            job_type="claim_wrapper",
        ))

        # 2. PTC/Surf Ads (Periodically)
        jobs.append(Job(
            priority=3,
            next_run=time.time() + 300,
            name=f"{self.faucet_name} PTC",
            profile=None,
            faucet_type=f_type,
            job_type="ptc_wrapper",
        ))

        # 3. Consolidation Job (Faucet -> Main)
        jobs.append(Job(
            priority=4,
            next_run=time.time() + 7200,
            name=f"{self.faucet_name} Consolidate",
            profile=None,
            faucet_type=f_type,
            job_type="consolidate_wrapper",
        ))

        # 4. Withdraw Job (Daily)
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=f_type,
            job_type="withdraw_wrapper",
        ))

        return jobs

    async def consolidate_wrapper(
        self, page: Any,
    ) -> ClaimResult:
        """Consolidate faucet balances to main balance.

        Args:
            page: Playwright Page instance for the session.

        Returns:
            ClaimResult with transfer status.
        """
        self.page = page
        if not await self.login_wrapper():
            return ClaimResult(
                success=False,
                status="Login/Access Failed",
                next_claim_minutes=30,
            )
        return await self.transfer_faucet_to_main()

    async def transfer_faucet_to_main(self) -> ClaimResult:
        """Move funds from faucet balances to main balance.

        Returns:
            ClaimResult with transfer status and next run time.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            logger.info(
                f"[{self.faucet_name}] Starting "
                "Faucet -> Main transfer..."
            )
            await self.safe_navigate(
                f"{self.base_url}/dashboard/faucet",
                timeout=30000,
            )
            await self.handle_cloudflare(max_wait_seconds=20)

            # Add human-like delay
            await self.idle_mouse(duration=1.0)

            # Find all Transfer buttons
            transfer_btns = self.page.locator(
                "button:has-text('Transfer')"
            )
            count = await transfer_btns.count()
            logger.info(
                f"[{self.faucet_name}] Found {count} "
                "coins available for transfer"
            )

            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] No transfers "
                    "available (likely insufficient balances)"
                )
                return ClaimResult(
                    success=True,
                    status="No transfers needed",
                    next_claim_minutes=120,
                )

            transferred = 0
            failed = 0

            for i in range(count):
                try:
                    logger.info(
                        f"[{self.faucet_name}] "
                        f"Transferring coin "
                        f"{i + 1}/{count}..."
                    )

                    # Re-query buttons
                    transfer_btns = self.page.locator(
                        "button:has-text('Transfer')"
                    )
                    if await transfer_btns.count() == 0:
                        break

                    btn = transfer_btns.nth(i)

                    # Human-like interaction
                    await self.idle_mouse(
                        duration=random.uniform(0.5, 1.0),
                    )
                    await self.human_like_click(btn)
                    await self.page.wait_for_load_state(
                        "domcontentloaded", timeout=10000,
                    )
                    await self.random_delay(1.0, 2.0)

                    # Transfer Modal or Page
                    confirm = self.page.locator(
                        "button.btn-primary"
                        ":has-text('Transfer'), "
                        "#transfer-btn"
                    )
                    amount_input = self.page.locator(
                        "input[name='amount'], "
                        "#transfer-amount"
                    )

                    if await confirm.count() > 0:
                        val = None
                        if await amount_input.count() > 0:
                            val = (
                                await amount_input
                                .get_attribute("placeholder")
                            )
                        if val and "min" in val.lower():
                            logger.debug(
                                f"[{self.faucet_name}] "
                                "Minimum transfer amount"
                                f" required: {val}"
                            )

                        await self.idle_mouse(duration=0.5)
                        await self.human_like_click(confirm)
                        await asyncio.sleep(2)
                        transferred += 1
                        logger.info(
                            f"[{self.faucet_name}] "
                            f"Transfer {i + 1} completed"
                        )
                    else:
                        logger.warning(
                            f"[{self.faucet_name}] Transfer"
                            " confirmation button not found"
                        )
                        failed += 1

                    # Return to faucet page
                    await self.page.goto(
                        f"{self.base_url}/dashboard/faucet",
                        timeout=10000,
                    )
                    await self.random_delay(0.5, 1.0)

                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{self.faucet_name}] Timeout "
                        f"transferring coin {i + 1}"
                    )
                    failed += 1
                except Exception as e:
                    logger.error(
                        f"[{self.faucet_name}] Error "
                        f"transferring coin {i + 1}: {e}"
                    )
                    failed += 1

            elapsed_time = (
                asyncio.get_event_loop().time() - start_time
            )
            logger.info(
                f"[{self.faucet_name}] Transfer session "
                f"completed in {elapsed_time:.1f}s: "
                f"{transferred} transferred, {failed} failed"
            )

            return ClaimResult(
                success=transferred > 0,
                status=(
                    f"Transferred {transferred} coins "
                    f"({failed} failed)"
                ),
                next_claim_minutes=120,
            )

        except Exception as e:
            elapsed_time = (
                asyncio.get_event_loop().time() - start_time
            )
            logger.error(
                f"[{self.faucet_name}] Transfer error "
                f"after {elapsed_time:.1f}s: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {str(e)[:100]}",
                next_claim_minutes=60,
            )

    async def withdraw(self) -> ClaimResult:
        """Execute main balance withdrawal.

        Selects withdrawal method, confirms amount, handles
        2FA if required, and submits the request.

        Returns:
            ClaimResult with withdrawal status.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] Executing "
                "Main Balance withdrawal..."
            )
            await self.page.goto(
                f"{self.base_url}/dashboard/withdraw",
            )

            # 1. Select Method
            method_dropdown = self.page.locator(
                ".select-method, "
                "input[placeholder='Select Method']"
            )
            await self.human_like_click(method_dropdown)
            await asyncio.sleep(1)

            # Try to find specific option
            option = self.page.locator(
                "li:has-text('Litecoin'), "
                "li:has-text('FaucetPay'), "
                ".el-select-dropdown__item"
                ":has-text('Litecoin')"
            )
            if await option.count() > 0:
                logger.info(
                    f"[{self.faucet_name}] Selecting "
                    "specific withdrawal method..."
                )
                await self.human_like_click(option.first)
            else:
                await self.page.keyboard.press("Enter")

            # 2. Confirm Amount
            confirm_btn = self.page.locator(
                "button.btn-primary:has-text('Confirm')"
            )
            if await confirm_btn.count() > 0:
                await self.human_like_click(confirm_btn)
                await self.random_delay(2, 4)

                # Check for 2FA or Captcha
                await self.solver.solve_captcha(self.page)

                # Check for 2FA field
                otp_field = self.page.locator(
                    "input[name='google_code'], "
                    "input[placeholder*='2FA']"
                )
                if await otp_field.count() > 0:
                    logger.warning(
                        f"[{self.faucet_name}] "
                        "2FA required for withdrawal. "
                        "Bot paused."
                    )
                    return ClaimResult(
                        success=False,
                        status="2FA Required",
                        next_claim_minutes=1440,
                    )

                # Final Confirm
                final_btn = self.page.locator(
                    "button.btn-primary:has-text('Confirm')"
                ).last
                await self.human_like_click(final_btn)

                logger.info(
                    f"[{self.faucet_name}] "
                    "Withdrawal request submitted!"
                )
                return ClaimResult(
                    success=True,
                    status="Withdrawn",
                    next_claim_minutes=1440,
                )

            return ClaimResult(
                success=False,
                status="Withdrawal Button Not Found",
                next_claim_minutes=60,
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

    async def view_ptc_ads(self) -> Optional[ClaimResult]:
        """View CoinPayU Surf Ads with stealth and error handling.

        Returns:
            ClaimResult with ad viewing status, or None on
            failure.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            logger.info(
                f"[{self.faucet_name}] "
                "Checking Surf Ads..."
            )
            await self.page.goto(
                f"{self.base_url}/dashboard/ads_surf",
                timeout=30000,
            )
            await self.handle_cloudflare(max_wait_seconds=20)

            # Wait for list or no-ads message
            try:
                await self.page.wait_for_selector(
                    ".ags-list-box, .no-ads", timeout=10000,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[{self.faucet_name}] "
                    "Timeout waiting for ads list"
                )

            # Add human-like delay
            await self.idle_mouse(duration=1.0)

            # Ads that are NOT grayed out (unclicked)
            ad_items = self.page.locator(
                ".clearfix.ags-list-box:not(.gray-all)"
            )
            count = await ad_items.count()
            logger.info(
                f"[{self.faucet_name}] "
                f"Found {count} unclicked Surf Ads"
            )

            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    "No surf ads available"
                )
                return ClaimResult(
                    success=True,
                    status="No ads available",
                    next_claim_minutes=60,
                )

            processed = 0
            failed = 0
            limit = 10

            while processed < limit:
                try:
                    # Always target the first unclicked ad
                    ad_items = self.page.locator(
                        ".clearfix.ags-list-box"
                        ":not(.gray-all)"
                    )
                    if await ad_items.count() == 0:
                        logger.info(
                            f"[{self.faucet_name}] "
                            "No more unclicked ads"
                        )
                        break

                    item = ad_items.first

                    # Extract duration
                    duration_locator = item.locator(
                        ".ags-detail-time span"
                    )
                    if await duration_locator.count() > 0:
                        duration_text = (
                            await duration_locator.first
                            .inner_text()
                        )
                        match = re.search(
                            r'(\d+)', duration_text,
                        )
                        duration = (
                            int(match.group(1))
                            if match
                            else 15
                        )
                    else:
                        duration = 15
                        logger.debug(
                            f"[{self.faucet_name}] Using "
                            f"default duration: {duration}s"
                        )

                    logger.info(
                        f"[{self.faucet_name}] Clicking "
                        f"Surf Ad {processed + 1} "
                        f"({duration}s duration)..."
                    )

                    # Human-like interaction before clicking
                    await self.idle_mouse(
                        duration=random.uniform(0.5, 1.5),
                    )

                    # Open ad in new page
                    new_page_ctx = (
                        self.page.context.expect_page()
                    )
                    async with new_page_ctx as new_page_info:
                        # Click the title span
                        title_link = item.locator(
                            ".text-overflow"
                            ".ags-description > span, "
                            "a.title"
                        )
                        if await title_link.count() > 0:
                            await self.human_like_click(
                                title_link.first,
                            )
                        else:
                            logger.warning(
                                f"[{self.faucet_name}] "
                                "Ad title link not found"
                            )
                            failed += 1
                            continue

                    ad_page = await new_page_info.value
                    logger.debug(
                        f"[{self.faucet_name}] Ad page "
                        f"opened, waiting {duration}s..."
                    )

                    # Timer is on the MAIN tab. Ad tab just
                    # needs to exist. Add extra buffer time.
                    await self.human_wait(
                        duration + random.uniform(3, 5),
                        with_interactions=True,
                    )

                    await ad_page.close()
                    logger.debug(
                        f"[{self.faucet_name}] "
                        "Ad page closed"
                    )

                    # Random delay between ads
                    await self.random_delay(2.0, 4.0)

                    # Check for interruption CAPTCHA
                    captcha_sel = (
                        "#turnstile-container, "
                        ".cf-turnstile, "
                        ".captcha-container"
                    )
                    if await self.page.locator(
                        captcha_sel
                    ).count() > 0:
                        logger.info(
                            f"[{self.faucet_name}] CAPTCHA "
                            "detected during Surf Ads"
                        )
                        captcha_result = (
                            await self.solver.solve_captcha(
                                self.page,
                            )
                        )
                        if captcha_result:
                            logger.info(
                                f"[{self.faucet_name}] "
                                "CAPTCHA solved"
                            )
                            await self.random_delay(1.0, 2.0)
                        else:
                            logger.warning(
                                f"[{self.faucet_name}] "
                                "CAPTCHA solving failed"
                            )

                    processed += 1

                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{self.faucet_name}] Timeout "
                        f"on ad {processed + 1}"
                    )
                    failed += 1
                except Exception as e:
                    logger.error(
                        f"[{self.faucet_name}] Error "
                        f"on ad {processed + 1}: {e}"
                    )
                    failed += 1

            elapsed_time = (
                asyncio.get_event_loop().time() - start_time
            )
            logger.info(
                f"[{self.faucet_name}] Surf Ads session "
                f"completed in {elapsed_time:.1f}s: "
                f"{processed} watched, {failed} failed"
            )

            return ClaimResult(
                success=processed > 0,
                status=(
                    f"Watched {processed} ads "
                    f"({failed} failed)"
                ),
                next_claim_minutes=60,
            )

        except Exception as e:
            elapsed_time = (
                asyncio.get_event_loop().time() - start_time
            )
            logger.error(
                f"[{self.faucet_name}] PTC error "
                f"after {elapsed_time:.1f}s: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {str(e)[:100]}",
                next_claim_minutes=60,
            )
