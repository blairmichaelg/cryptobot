"""DutchyCorp faucet bot for Cryptobot Gen 3.0.

Implements ``dutchycorp.space`` multi-coin faucet with:
    * Roll-based claiming (Dutchy Roll + Coin Roll).
    * Shortlink solving for bonus earnings.
    * Multi-cryptocurrency withdrawal via FaucetPay.

Claim interval: ~30 minutes per roll.
"""

import asyncio
import logging
import random
from typing import Any, List, Optional

from .base import ClaimResult, FaucetBot

logger = logging.getLogger(__name__)


class DutchyBot(FaucetBot):
    """DutchyCorp multi-coin faucet bot.

    Handles automated claiming, shortlink solving, and
    withdrawals for DutchyCorp.  Implements stealth primitives,
    robust error handling, and accurate scheduling.
    """

    def __init__(
        self,
        settings: Any,
        page: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize DutchyBot.

        Args:
            settings: BotSettings configuration object.
            page: Playwright Page instance.
            **kwargs: Additional arguments passed to FaucetBot.
        """
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "DutchyCorp"
        self.base_url = (
            "https://autofaucet.dutchycorp.space"
        )
        # Retry configuration for robustness
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    async def is_logged_in(self) -> bool:
        """Check if user is currently logged in.

        Returns:
            True if logged in, False otherwise.
        """
        try:
            logout_link = (
                await self.page.query_selector(
                    "a[href*='logout']"
                )
            )
            return logout_link is not None
        except Exception as e:
            logger.debug(
                f"[{self.faucet_name}] "
                f"Login check error: {e}"
            )
            return False

    def get_jobs(self) -> List[Any]:
        """Return DutchyCorp jobs for the scheduler.

        Returns:
            List of Job objects for rolls and withdrawals.
        """
        from core.orchestrator import Job
        import time

        jobs: List[Any] = []

        # Job 1: Main Claim (Rolls) - Hourly
        jobs.append(Job(
            priority=1,
            next_run=time.time(),
            name=f"{self.faucet_name} Claim",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="claim_wrapper",
        ))

        # Job 2: Withdraw - Daily
        jobs.append(Job(
            priority=5,
            next_run=time.time() + 3600,
            name=f"{self.faucet_name} Withdraw",
            profile=None,
            faucet_type=self.faucet_name.lower(),
            job_type="withdraw_wrapper",
        ))

        return jobs

    async def claim_shortlinks(
        self, separate_context: bool = True,
    ) -> ClaimResult:
        """Claim available shortlinks on DutchyCorp.

        Args:
            separate_context: Use separate browser context to
                avoid interference with the main session.

        Returns:
            ClaimResult with shortlink earnings.
        """
        shortlink_earnings = 0.0
        shortlinks_claimed = 0

        try:
            logger.info(
                f"[{self.faucet_name}] "
                "Checking shortlinks..."
            )

            # Use separate context if requested
            if (
                separate_context
                and hasattr(self, 'browser_manager')
            ):
                context = (
                    await self.page.context
                    .browser.new_context()
                )
                page = await context.new_page()
                cookies = (
                    await self.page.context.cookies()
                )
                await context.add_cookies(cookies)
            else:
                page = self.page

            nav_timeout = getattr(
                self.settings, "timeout", 180000,
            )
            try:
                await page.goto(
                    f"{self.base_url}/shortlinks.php",
                    timeout=nav_timeout,
                )
            except Exception as e:
                logger.warning(
                    f"[{self.faucet_name}] Shortlinks "
                    f"navigation retry: {e}"
                )
                await page.goto(
                    f"{self.base_url}/shortlinks.php",
                    wait_until="commit",
                    timeout=nav_timeout,
                )

            # DutchyCorp shortlink selectors
            links = page.locator(
                "a[href*='shortlink']"
                ":has-text('Claim'), "
                ".shortlink-btn, "
                "a.btn:has-text('Visit')"
            )
            count = await links.count()

            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    "No shortlinks available"
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
                )

            logger.info(
                f"[{self.faucet_name}] Found {count} "
                "shortlinks, processing top 3..."
            )

            from solvers.shortlink import ShortlinkSolver
            blocker = getattr(
                page, "resource_blocker", None,
            )
            solver = ShortlinkSolver(
                page,
                blocker=blocker,
                captcha_solver=self.solver,
            )

            for i in range(min(3, count)):
                try:
                    links = page.locator(
                        "a[href*='shortlink']"
                        ":has-text('Claim'), "
                        ".shortlink-btn"
                    )
                    if await links.count() <= i:
                        break

                    await self.human_like_click(
                        links.nth(i),
                    )
                    await page.wait_for_load_state()

                    # Solve any captchas
                    captcha_iframe = (
                        await page.query_selector(
                            "iframe[src*='turnstile'], "
                            "iframe[src*='hcaptcha'], "
                            "iframe[src*='recaptcha']"
                        )
                    )
                    if captcha_iframe:
                        await self.solver.solve_captcha(
                            page,
                        )

                    # Solve shortlink
                    success_pats = [
                        "dutchycorp.space",
                        "/shortlinks",
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
                        f"{self.base_url}/shortlinks.php",
                    )

                except Exception as link_err:
                    logger.error(
                        f"[{self.faucet_name}] Shortlink "
                        f"{i + 1} error: {link_err}"
                    )
                    continue

            if (
                separate_context
                and 'context' in locals()
            ):
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
                    f"Claimed {shortlinks_claimed} "
                    "shortlinks"
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

    async def login(self) -> bool:
        """Login to DutchyCorp with stealth and error handling.

        Uses human_type() for credentials, implements retry
        logic for network errors, and validates login state.

        Note: DutchyCorp requires residential proxies --
        datacenter IPs are detected immediately.

        Returns:
            True if login successful, False otherwise.
        """
        # Get credentials with override support
        if (
            hasattr(self, 'settings_account_override')
            and self.settings_account_override
        ):
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("dutchy")

        if not creds:
            logger.error(
                f"[{self.faucet_name}] "
                "No credentials found"
            )
            return False

        # DutchyCorp REQUIRES residential proxies
        if hasattr(self, 'profile') and self.profile:
            if not getattr(
                self.profile, 'residential_proxy', False,
            ):
                logger.error(
                    f"[{self.faucet_name}] DATACENTER "
                    "PROXY DETECTED - DutchyCorp requires "
                    "residential proxies!"
                )
                logger.error(
                    f"[{self.faucet_name}] Set "
                    "'residential_proxy: true' in "
                    "faucet_config.json"
                )
                proxy_info = getattr(
                    self.profile, 'proxy', 'N/A',
                )
                logger.error(
                    f"[{self.faucet_name}] "
                    f"Proxy info: {proxy_info}"
                )
                # Continue but warn

        # Retry loop for network resilience
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"[{self.faucet_name}] Login attempt "
                    f"{attempt}/{self.max_retries}"
                )
                nav_timeout = getattr(
                    self.settings, "timeout", 180000,
                )
                await self.safe_navigate(
                    f"{self.base_url}/login.php",
                    timeout=nav_timeout,
                )

                # Handle Cloudflare challenges
                await self.handle_cloudflare(
                    max_wait_seconds=120,
                )

                # Check common failure states
                failure_state = (
                    await self.check_failure_states()
                )
                if failure_state:
                    if "Proxy Detected" in failure_state:
                        logger.error(
                            f"[{self.faucet_name}] "
                            f"{failure_state} - "
                            "DutchyCorp blocks datacenter "
                            "IPs. Use residential proxies!"
                        )
                    else:
                        logger.error(
                            f"[{self.faucet_name}] "
                            f"{failure_state} detected"
                        )
                    return False

                # Check if already logged in
                if await self.is_logged_in():
                    logger.info(
                        f"[{self.faucet_name}] "
                        "Already logged in"
                    )
                    return True

                # Warm up page
                await self.warm_up_page()

                # Stealth: Idle mouse before interaction
                await self.idle_mouse(1.5)

                # Enter credentials with human behavior
                username_input = self.page.locator(
                    'input[name="username"]'
                )
                await self.human_type(
                    username_input, creds['username'],
                )

                await self.random_delay(0.5, 1.5)

                password_input = self.page.locator(
                    'input[name="password"]'
                )
                await self.human_type(
                    password_input, creds['password'],
                )

                # "Keep me logged in" checkbox
                remember = self.page.locator(
                    'input[name="remember_me"]'
                )
                if await remember.count() > 0:
                    await self.random_delay(0.3, 0.8)
                    await remember.check()
                    logger.debug(
                        f"[{self.faucet_name}] "
                        "Remember me checkbox enabled"
                    )

                # Close any interfering popups
                await self.close_popups()

                # Solve CAPTCHA with retry handling
                captcha_solved = (
                    await self.solver.solve_captcha(
                        self.page,
                    )
                )
                if not captcha_solved:
                    logger.warning(
                        f"[{self.faucet_name}] CAPTCHA "
                        "solving failed or not required"
                    )

                # Submit login
                await self.thinking_pause()
                await self.random_delay(0.5, 1.2)
                submit = self.page.locator(
                    'button[type="submit"]'
                )
                await self.human_like_click(submit)

                # Wait for navigation
                try:
                    await self.page.wait_for_url(
                        "**/dashboard.php",
                        timeout=20000,
                    )
                    logger.info(
                        f"[{self.faucet_name}] "
                        "Login successful"
                    )
                    return True
                except Exception as wait_err:
                    if await self.is_logged_in():
                        logger.info(
                            f"[{self.faucet_name}] Login "
                            "successful (alt check)"
                        )
                        return True
                    raise wait_err

            except asyncio.TimeoutError as e:
                logger.warning(
                    f"[{self.faucet_name}] Login timeout "
                    f"on attempt {attempt}: {e}"
                )
                if attempt < self.max_retries:
                    await self.human_wait(
                        self.retry_delay,
                    )
                    continue
            except Exception as e:
                logger.error(
                    f"[{self.faucet_name}] Login error "
                    f"on attempt {attempt}: {e}"
                )
                if attempt < self.max_retries:
                    await self.human_wait(
                        self.retry_delay,
                    )
                    continue

        logger.error(
            f"[{self.faucet_name}] Login failed after "
            f"{self.max_retries} attempts"
        )
        return False

    async def claim(self) -> ClaimResult:
        """Execute DutchyCorp claim cycle with timing.

        Performs Dutchy Roll, Coin Roll, and Shortlinks in
        sequence.  Uses accurate timer extraction to determine
        the next claim time.

        Returns:
            ClaimResult with success status, balance, and
            next claim time.
        """
        claim_start_time = asyncio.get_event_loop().time()

        try:
            # Extract initial balance
            logger.info(
                f"[{self.faucet_name}] "
                "Starting claim cycle"
            )
            balance = await self.get_balance(
                ".user-balance, .balance-text, "
                "#balance, .balance"
            )
            logger.info(
                f"[{self.faucet_name}] "
                f"Current balance: {balance}"
            )

            # Track minimum next claim time
            min_wait_minutes = 30.0

            # 1. Dutchy Roll - Primary earning source
            roll1_wait = await self._do_roll(
                "roll.php", "Dutchy Roll",
            )
            if roll1_wait is not None and roll1_wait > 0:
                min_wait_minutes = min(
                    min_wait_minutes, roll1_wait,
                )

            # Stealth delay between actions
            await self.random_delay(2, 4)

            # 2. Coin Roll - Secondary earning source
            roll2_wait = await self._do_roll(
                "coin_roll.php", "Coin Roll",
            )
            if roll2_wait is not None and roll2_wait > 0:
                min_wait_minutes = min(
                    min_wait_minutes, roll2_wait,
                )

            await self.random_delay(2, 4)

            # 3. Shortlinks - Bonus earnings (best-effort)
            try:
                await self.claim_shortlinks()
            except Exception as shortlink_err:
                logger.warning(
                    f"[{self.faucet_name}] Shortlinks "
                    f"failed (non-critical): "
                    f"{shortlink_err}"
                )

            # Calculate claim duration for metrics
            claim_duration = (
                asyncio.get_event_loop().time()
                - claim_start_time
            )
            logger.info(
                f"[{self.faucet_name}] Claim cycle "
                f"completed in {claim_duration:.1f}s"
            )

            # Get final balance for earnings calc
            final_balance = await self.get_balance(
                ".user-balance, .balance-text, "
                "#balance, .balance"
            )

            # Calculate earned amount
            earned = "0"
            try:
                initial = (
                    float(balance)
                    if balance and balance != "0"
                    else 0.0
                )
                final = (
                    float(final_balance)
                    if final_balance
                    and final_balance != "0"
                    else 0.0
                )
                if final > initial:
                    earned = str(
                        round(final - initial, 8),
                    )
            except (ValueError, TypeError):
                pass

            return ClaimResult(
                success=True,
                status="Dutchy cycle complete",
                next_claim_minutes=min_wait_minutes,
                balance=final_balance,
                amount=earned,
            )

        except asyncio.TimeoutError as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Claim cycle timeout: {e}"
            )
            return ClaimResult(
                success=False,
                status="Timeout error",
                next_claim_minutes=15,
            )
        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Claim cycle error: {e}",
                exc_info=True,
            )
            return ClaimResult(
                success=False,
                status=f"Error: {str(e)[:100]}",
                next_claim_minutes=15,
            )

    async def _do_roll(
        self, page_slug: str, roll_name: str,
    ) -> Optional[float]:
        """Execute a single roll with comprehensive handling.

        Args:
            page_slug: Page URL slug (e.g. "roll.php").
            roll_name: Human-readable name for logging.

        Returns:
            Cooldown time in minutes if on cooldown, None if
            roll completed or failed.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] "
                f"Checking {roll_name}..."
            )
            nav_timeout = getattr(
                self.settings, "timeout", 180000,
            )
            try:
                await self.page.goto(
                    f"{self.base_url}/{page_slug}",
                    timeout=nav_timeout,
                )
            except Exception as e:
                logger.warning(
                    f"[{self.faucet_name}] {roll_name} "
                    f"navigation retry: {e}"
                )
                await self.page.goto(
                    f"{self.base_url}/{page_slug}",
                    wait_until="commit",
                    timeout=nav_timeout,
                )

            # Close interfering popups
            await self.close_popups()

            # Warm up page and simulate natural browsing
            await self.warm_up_page()
            await self.simulate_reading(
                duration=random.uniform(1.5, 3.0),
            )
            if random.random() < 0.4:
                await self.natural_scroll(
                    distance=random.randint(80, 200),
                    direction=1,
                )
                await asyncio.sleep(
                    random.uniform(0.3, 0.8),
                )

            # Check for timer/cooldown
            timer_selectors = [
                "#timer", ".count_down_timer",
                ".timer", "#countdown", ".cooldown",
            ]
            wait_min = await self.get_timer(
                timer_selectors[0],
                fallback_selectors=timer_selectors[1:],
            )

            if wait_min > 0:
                logger.info(
                    f"[{self.faucet_name}] {roll_name} "
                    f"on cooldown: {wait_min:.1f}m"
                )
                return wait_min

            # Stealth: Simulate reading before roll
            await self.simulate_reading(
                duration=random.uniform(1.0, 2.0),
            )
            await self.thinking_pause()
            await self.idle_mouse(1.0)

            # Handle "Unlock" button if present
            unlock = self.page.locator("#unlockbutton")
            if (
                await unlock.count() > 0
                and await unlock.is_visible()
            ):
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Unlocking {roll_name}..."
                )
                await self.human_like_click(unlock)
                await self.random_delay(1.5, 3.0)

            # Handle "Boost" system
            boost = self.page.locator(
                "#claim_boosted, "
                "button:has-text('Boost')"
            )
            if (
                await boost.count() > 0
                and await boost.is_visible()
            ):
                logger.info(
                    f"[{self.faucet_name}] Applying "
                    f"boost for {roll_name}..."
                )
                await self.human_like_click(boost)
                await self.random_delay(1, 2)

            # Handle Cloudflare/Turnstile challenges
            await self.handle_cloudflare()

            # Solve CAPTCHA
            try:
                captcha_solved = (
                    await self.solver.solve_captcha(
                        self.page,
                    )
                )
                if captcha_solved:
                    logger.info(
                        f"[{self.faucet_name}] CAPTCHA "
                        f"solved for {roll_name}"
                    )
                else:
                    logger.debug(
                        f"[{self.faucet_name}] No CAPTCHA "
                        f"required for {roll_name}"
                    )
            except Exception as captcha_err:
                logger.warning(
                    f"[{self.faucet_name}] CAPTCHA error "
                    f"(continuing): {captcha_err}"
                )

            # Stealth delay before clicking roll
            await self.random_delay(0.5, 1.5)

            # Find and click roll button
            roll_btn_sel = (
                "#claim_boosted, "
                "button:has-text('Roll'), "
                "#roll_button, .roll-button"
            )
            roll_btn = self.page.locator(roll_btn_sel)

            if await roll_btn.count() > 0:
                await self.human_like_click(
                    roll_btn.first,
                )
                await self.random_delay(3, 5)

                # Check for success message
                success = self.page.locator(
                    ".alert-success, "
                    ".toast-success, "
                    "text=/You received/, "
                    ".success-message"
                )
                if await success.count() > 0:
                    success_text = (
                        await success.first.text_content()
                    )
                    logger.info(
                        f"[{self.faucet_name}] "
                        f"{roll_name} claimed: "
                        f"{success_text}"
                    )
                else:
                    logger.info(
                        f"[{self.faucet_name}] "
                        f"{roll_name} button clicked "
                        "(no confirmation message)"
                    )

                return None

            logger.warning(
                f"[{self.faucet_name}] "
                f"{roll_name} button not found"
            )
            return None

        except asyncio.TimeoutError as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"{roll_name} timeout: {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"{roll_name} error: {e}",
                exc_info=True,
            )
            return None

    async def withdraw(self) -> ClaimResult:
        """Execute DutchyCorp withdrawal.

        Attempts to withdraw available balances to FaucetPay
        or direct wallet.  Handles CAPTCHA solving and
        validates withdrawal success.

        Returns:
            ClaimResult with withdrawal status and next run
            time.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] Navigating "
                "to withdrawal page..."
            )
            nav_timeout = getattr(
                self.settings, "timeout", 180000,
            )
            try:
                await self.page.goto(
                    f"{self.base_url}/balance.php",
                    timeout=nav_timeout,
                )
            except Exception as e:
                logger.warning(
                    f"[{self.faucet_name}] Balance "
                    f"navigation retry: {e}"
                )
                await self.page.goto(
                    f"{self.base_url}/balance.php",
                    wait_until="commit",
                    timeout=nav_timeout,
                )

            # Close any interfering popups
            await self.close_popups()

            # Find available withdrawal buttons
            withdraw_btns = self.page.locator(
                "a.btn.btn-success"
                ":has-text('Withdraw'), "
                "button:has-text('Withdraw')"
            )
            count = await withdraw_btns.count()

            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    "No balances ready for withdrawal"
                )
                return ClaimResult(
                    success=True,
                    status="No Balance",
                    next_claim_minutes=1440,
                )

            logger.info(
                f"[{self.faucet_name}] Found {count} "
                "withdrawable balance(s)"
            )

            # Stealth: Idle before interaction
            await self.idle_mouse(1.0)

            # Click first available withdrawal button
            target_btn = withdraw_btns.nth(0)
            await self.human_like_click(target_btn)
            await self.page.wait_for_load_state(
                "domcontentloaded",
            )

            # Select FaucetPay if available
            method_select = self.page.locator(
                "select[name='method'], "
                "#withdrawal_method"
            )
            if await method_select.count() > 0:
                try:
                    await method_select.select_option(
                        label="FaucetPay",
                    )
                    logger.info(
                        f"[{self.faucet_name}] Selected "
                        "FaucetPay withdrawal method"
                    )
                    await asyncio.sleep(1)
                except Exception as select_err:
                    logger.debug(
                        f"[{self.faucet_name}] Could not "
                        "select FaucetPay: "
                        f"{select_err}"
                    )

            # Solve CAPTCHA for withdrawal
            await self.random_delay(0.5, 1.5)
            try:
                captcha_solved = (
                    await self.solver.solve_captcha(
                        self.page,
                    )
                )
                if captcha_solved:
                    logger.info(
                        f"[{self.faucet_name}] CAPTCHA "
                        "solved for withdrawal"
                    )
            except Exception as captcha_err:
                logger.warning(
                    f"[{self.faucet_name}] "
                    f"CAPTCHA error: {captcha_err}"
                )

            # Final confirmation
            await self.random_delay(0.5, 1.2)
            submit = self.page.locator(
                "button:has-text('Withdraw'), "
                "#withdraw_button"
            ).last
            await self.human_like_click(submit)

            await self.random_delay(2, 4)

            # Check for success confirmation
            success = self.page.locator(
                ".alert-success, .toast-success, "
                ":text-contains("
                "'Withdrawal has been sent'), "
                ".success-message"
            )
            if await success.count() > 0:
                success_text = (
                    await success.first.text_content()
                )
                logger.info(
                    f"[{self.faucet_name}] Withdrawal "
                    f"successful: {success_text}"
                )
                return ClaimResult(
                    success=True,
                    status="Withdrawn",
                    next_claim_minutes=1440,
                )

            logger.warning(
                f"[{self.faucet_name}] Withdrawal "
                "submitted but no confirmation message"
            )
            return ClaimResult(
                success=False,
                status="No confirmation message",
                next_claim_minutes=120,
            )

        except asyncio.TimeoutError as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Withdrawal timeout: {e}"
            )
            return ClaimResult(
                success=False,
                status="Timeout error",
                next_claim_minutes=60,
            )
        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Withdrawal error: {e}",
                exc_info=True,
            )
            return ClaimResult(
                success=False,
                status=f"Error: {str(e)[:100]}",
                next_claim_minutes=60,
            )
