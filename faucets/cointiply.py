"""Cointiply faucet bot for Cryptobot Gen 3.0.

Implements ``cointiply.com`` with faucet claiming, PTC (paid-to-click) ad
viewing, and multi-currency withdrawals.  Uses hCaptcha solving (via
CapSolver fallback if 2Captcha primary is configured).

Claim interval: ~60 minutes.
"""

import asyncio
import logging
import random
import re
from typing import Any, List

from .base import ClaimResult, FaucetBot

logger = logging.getLogger(__name__)


class CointiplyBot(FaucetBot):
    """Cointiply faucet bot implementation.

    Supports:
        * Faucet claims with timer-based scheduling.
        * PTC (paid-to-click) ad viewing for bonus earnings.
        * Automated withdrawals to multiple cryptocurrencies.
        * hCaptcha solving with provider fallback.
    """

    def __init__(
        self,
        settings: Any,
        page: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize Cointiply bot.

        Args:
            settings: BotSettings configuration object.
            page: Playwright Page instance.
            **kwargs: Additional arguments passed to FaucetBot.
        """
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "Cointiply"
        self.base_url = "https://cointiply.com"

    async def is_logged_in(self) -> bool:
        """Check whether the user is currently logged in.

        Returns:
            True if dashboard URL or balance element is found.
        """
        if "dashboard" in self.page.url:
            return True
        balance_loc = self.page.locator(
            ".user-balance-coins, .user-balance"
        )
        return await balance_loc.is_visible()

    async def get_current_balance(self) -> str:
        """Get current balance from Cointiply dashboard.

        Returns:
            Balance as string. Returns "0" if extraction fails.
        """
        balance = await self.get_balance(
            ".user-balance-coins",
            fallback_selectors=[".user-balance"],
        )
        logger.debug(
            f"[{self.faucet_name}] "
            f"Current balance: {balance}"
        )
        return balance

    async def view_ptc_ads(self) -> None:
        """View PTC ads with focused-tab management.

        Opens each ad in a new tab, waits for the timer to
        count down, then verifies image if required.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] "
                "Checking PTC Ads..."
            )
            await self.page.goto(f"{self.base_url}/ptc")

            # Update selector for PTC View Button
            ads = self.page.locator(
                "button.view-ad-button, "
                ".btn-success:has-text('View')"
            )
            count = await ads.count()
            if count == 0:
                logger.info(
                    f"[{self.faucet_name}] "
                    "No PTC ads available."
                )
                return

            limit = 5
            logger.info(
                f"[{self.faucet_name}] Found {count} "
                f"PTC Ads. Watching top {limit}..."
            )

            for i in range(limit):
                ads = self.page.locator(
                    "button.view-ad-button, "
                    ".btn-success:has-text('View')"
                )
                if await ads.count() == 0:
                    break

                new_page_ctx = (
                    self.page.context.expect_page()
                )
                async with new_page_ctx as new_page_info:
                    await self.human_like_click(ads.first)

                ad_page = await new_page_info.value
                await ad_page.wait_for_load_state(
                    "domcontentloaded",
                )

                # Cointiply PTC requires active focus
                await ad_page.bring_to_front()

                # Wait 35s with human activity
                await self.human_wait(
                    35, with_interactions=True,
                )

                # Switch back to verify if needed
                await self.page.bring_to_front()
                await ad_page.close()
                await self.random_delay(2, 4)

                # Check for "Unique Image" Verification
                verify_container = self.page.locator(
                    "#captcha-images, "
                    ".ptc-verify-container"
                )
                if await verify_container.is_visible():
                    logger.info(
                        f"[{self.faucet_name}] Multi-image "
                        "verification detected."
                    )
                    await self.solver.solve_captcha(
                        self.page,
                    )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] PTC Error: {e}"
            )

    async def login(self) -> bool:
        """Authenticate with Cointiply using credentials.

        Returns:
            True if login successful, False otherwise.
        """
        if (
            hasattr(self, 'settings_account_override')
            and self.settings_account_override
        ):
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("cointiply")

        if not creds:
            logger.warning(
                f"[{self.faucet_name}] "
                "No credentials configured"
            )
            return False

        try:
            logger.info(
                f"[{self.faucet_name}] "
                "Starting login process"
            )
            nav_timeout = getattr(
                self.settings, "timeout", 180000,
            )
            await self.safe_navigate(
                f"{self.base_url}/login",
                timeout=nav_timeout,
            )
            await self.handle_cloudflare()

            # Verify page is still alive
            if not await self.check_page_health():
                logger.error(
                    f"[{self.faucet_name}] Page became "
                    "unresponsive after Cloudflare check"
                )
                return False

            # Warm up page with natural browsing behavior
            await self.warm_up_page()

            # Enhanced email selectors
            email_selectors = [
                'input[autocomplete="email"]'
                ':not([form*="signup"])'
                ':not([form*="register"])',
                'input[autocomplete="username"]'
                ':not([form*="signup"])'
                ':not([form*="register"])',
                'input[name="email"]'
                ':not([form*="signup"])',
                'input[type="email"]'
                ':not([form*="signup"])',
                'input[id*="email" i]'
                ':not([form*="signup"])',
                'input[name="username"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="username" i]',
            ]
            email_input = None
            for selector in email_selectors:
                locator = self.page.locator(selector)
                if await locator.count() > 0:
                    email_input = locator.first
                    break

            if not email_input:
                logger.error(
                    f"[{self.faucet_name}] Email input "
                    "not found on login page"
                )
                return False

            # Type with human behavior, fallback to fill
            await self.human_type(
                email_input, creds['username'],
            )
            if not await email_input.input_value():
                await email_input.fill(creds['username'])
            await self.random_delay(0.5, 1.5)

            password_selectors = [
                'input[autocomplete="current-password"]'
                ':not([form*="signup"])'
                ':not([form*="register"])',
                'input[type="password"]'
                ':not([form*="signup"])'
                ':not([form*="register"])',
                'input[name="password"]'
                ':not([form*="signup"])',
                'input[id*="password" i]'
                ':not([form*="signup"])',
                'input[placeholder*="password" i]',
            ]
            password_input = None
            for selector in password_selectors:
                locator = self.page.locator(selector)
                if await locator.count() > 0:
                    password_input = locator.first
                    break

            if not password_input:
                logger.error(
                    f"[{self.faucet_name}] Password input "
                    "not found on login page"
                )
                return False

            # Type with human behavior, fallback to fill
            await self.human_type(
                password_input, creds['password'],
            )
            if not await password_input.input_value():
                await password_input.fill(creds['password'])
            await self.random_delay(0.5, 1.5)

            # Solve CAPTCHA if present
            logger.debug(
                f"[{self.faucet_name}] "
                "Attempting CAPTCHA solve"
            )

            # Check if ALTCHA is present
            altcha_present = (
                await self.page.query_selector(
                    "altcha-widget, "
                    "[data-altcha], .altcha"
                )
            )
            if altcha_present:
                logger.info(
                    f"[{self.faucet_name}] ALTCHA "
                    "proof-of-work captcha detected "
                    "(free to solve)"
                )

            # Legacy: Check for hCaptcha
            hcaptcha_present = (
                await self.page.query_selector(
                    "iframe[src*='hcaptcha']"
                )
            )
            if hcaptcha_present:
                logger.info(
                    f"[{self.faucet_name}] hCaptcha "
                    "detected - requires CapSolver fallback"
                )
                if not self.solver.fallback_provider:
                    logger.warning(
                        f"[{self.faucet_name}] No fallback"
                        " provider configured! Set "
                        "CAPTCHA_FALLBACK_PROVIDER=capsolver"
                        " and CAPSOLVER_API_KEY in .env"
                    )

            captcha_solved = (
                await self.solver.solve_captcha(self.page)
            )
            if not captcha_solved:
                logger.warning(
                    f"[{self.faucet_name}] CAPTCHA solving"
                    " failed or not present"
                )

            # Simulate human behavior before submitting
            await self.thinking_pause()
            await self.idle_mouse(1.0)

            submit_selectors = [
                'form button[type="submit"]',
                'form input[type="submit"]',
                'button:has-text("Login")',
                'button:has-text("Log in")',
                'button:has-text("Sign In")',
                'button:has-text("Sign in")',
                'button.btn-primary',
                'button[type="submit"]',
            ]
            submit = None
            for selector in submit_selectors:
                locator = self.page.locator(selector)
                if await locator.count() > 0:
                    submit = locator.first
                    break

            if not submit:
                logger.error(
                    f"[{self.faucet_name}] "
                    "Login submit button not found"
                )
                return False

            # Use safe click to prevent crash errors
            click_success = await self.safe_click(submit)
            if not click_success:
                logger.warning(
                    f"[{self.faucet_name}] Safe click "
                    "failed, trying direct click"
                )
                await self.human_like_click(submit)

            # Wait for navigation with timeout
            try:
                await self.page.wait_for_url(
                    re.compile(
                        r".*/(home|dashboard|account).*"
                    ),
                    timeout=30000,
                )
                logger.info(
                    f"[{self.faucet_name}] "
                    "Login successful"
                )
                return True
            except Exception:
                if await self.is_logged_in():
                    logger.info(
                        f"[{self.faucet_name}] Login "
                        "successful (session detected)"
                    )
                    return True
                logger.warning(
                    f"[{self.faucet_name}] Login did not "
                    "navigate to dashboard"
                )
                return False

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Login failed: {e}"
            )
            return False

    async def claim(self) -> ClaimResult:
        """Execute faucet claim with robust error handling.

        Includes timer extraction and retry logic.

        Returns:
            ClaimResult with success status, next claim time,
            and balance.
        """
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                logger.info(
                    f"[{self.faucet_name}] Starting claim "
                    f"process (attempt "
                    f"{retry_count + 1}/{max_retries})"
                )

                nav_timeout = getattr(
                    self.settings, "timeout", 180000,
                )
                # Try multiple faucet URLs
                faucet_urls = [
                    f"{self.base_url}/faucet",
                    f"{self.base_url}/dashboard",
                    f"{self.base_url}/home",
                ]
                navigated = False
                for faucet_url in faucet_urls:
                    try:
                        nav_result = await self.safe_navigate(
                            faucet_url, timeout=nav_timeout,
                        )
                        if nav_result:
                            page_title = (
                                await self.page.title()
                            )
                            if (
                                "404" not in page_title
                                and "not found"
                                not in page_title.lower()
                            ):
                                logger.info(
                                    f"[{self.faucet_name}]"
                                    " Navigated to: "
                                    f"{faucet_url}"
                                )
                                navigated = True
                                break
                            logger.warning(
                                f"[{self.faucet_name}] "
                                f"{faucet_url} returned "
                                "404, trying next URL"
                            )
                    except Exception:
                        continue

                if not navigated:
                    logger.error(
                        f"[{self.faucet_name}] Could not "
                        "navigate to any faucet page"
                    )
                    retry_count += 1
                    continue

                await self.handle_cloudflare()

                # Verify page health before proceeding
                if not await self.check_page_health():
                    logger.warning(
                        f"[{self.faucet_name}] Page "
                        "unresponsive after navigation"
                    )
                    retry_count += 1
                    continue

                # Simulate natural page engagement
                await self.simulate_reading(
                    duration=random.uniform(2.0, 4.0),
                )
                if random.random() < 0.5:
                    await self.natural_scroll(
                        distance=random.randint(100, 300),
                        direction=1,
                    )
                    await asyncio.sleep(
                        random.uniform(0.3, 0.8),
                    )
                if random.random() < 0.3:
                    await self.simulate_tab_activity()

                # Extract current balance
                balance = await self.get_current_balance()
                logger.debug(
                    f"[{self.faucet_name}] "
                    f"Balance before claim: {balance}"
                )

                # Check for Roll Button
                roll = self.page.locator(
                    "#claim_button, "
                    "button.faucet-claim-btn, "
                    "button:has-text('Roll & Win'), "
                    "button:has-text('Roll'), "
                    "button.roll-button, .faucet-button, "
                    "button[onclick*='roll'], "
                    "input[type='submit'][value*='Roll']"
                )
                roll_count = await roll.count()

                logger.debug(
                    f"[{self.faucet_name}] Found "
                    f"{roll_count} potential roll buttons"
                )

                if (
                    roll_count > 0
                    and await roll.first.is_visible()
                ):
                    logger.debug(
                        f"[{self.faucet_name}] Roll "
                        "button found and visible"
                    )

                    # Extract timer
                    timer_selectors = [
                        ".timer_display",
                        "#timer_display",
                        ".timer-text",
                    ]
                    timer_mins = await self.get_timer(
                        timer_selectors[0],
                        fallback_selectors=(
                            timer_selectors[1:]
                        ),
                    )

                    logger.debug(
                        f"[{self.faucet_name}] Timer "
                        f"extracted: {timer_mins} minutes"
                    )

                    # Check if timer is ready
                    if timer_mins < 1.0:
                        logger.info(
                            f"[{self.faucet_name}] Timer "
                            "ready, proceeding with claim"
                        )

                        # Simulate human reading
                        await self.simulate_reading(
                            duration=random.uniform(
                                1.5, 3.0,
                            ),
                        )
                        await self.thinking_pause()
                        await self.idle_mouse(1.5)

                        # Solve CAPTCHA
                        logger.debug(
                            f"[{self.faucet_name}] "
                            "Attempting CAPTCHA solve"
                        )
                        captcha_solved = (
                            await self.solver.solve_captcha(
                                self.page,
                            )
                        )

                        if not captcha_solved:
                            logger.warning(
                                f"[{self.faucet_name}] "
                                "CAPTCHA solving failed"
                            )
                            retry_count += 1
                            if retry_count >= max_retries:
                                return ClaimResult(
                                    success=False,
                                    status=(
                                        "CAPTCHA failed "
                                        "after retries"
                                    ),
                                    next_claim_minutes=30,
                                    balance=balance,
                                )
                            await self.human_wait(5)
                            continue

                        # Enable submit button
                        logger.debug(
                            f"[{self.faucet_name}] CAPTCHA "
                            "solved, enabling buttons"
                        )
                        try:
                            await self.page.evaluate("""
                                const btns =
                                    document.querySelectorAll(
                                        'button[type="submit"],'
                                        + ' button.claim-button,'
                                        + ' button[id*="claim"],'
                                        + ' button[id*="roll"]'
                                    );
                                btns.forEach(btn => {
                                    if (btn.disabled) {
                                        btn.disabled = false;
                                        btn.removeAttribute(
                                            'disabled'
                                        );
                                    }
                                });
                            """)
                        except Exception:
                            pass

                        # Click roll button
                        await self.random_delay(0.5, 1.5)
                        click_success = (
                            await self.safe_click(roll)
                        )
                        if not click_success:
                            logger.warning(
                                f"[{self.faucet_name}] "
                                "Safe click on roll button "
                                "failed, trying direct"
                            )
                            await self.human_like_click(roll)

                        # Wait for result
                        await self.human_wait(3)

                        # Check for success indicators
                        success_selectors = [
                            ".md-snackbar-content",
                            ".toast-success",
                            ".alert-success",
                        ]
                        success_found = False

                        for sel in success_selectors:
                            if await self.page.locator(
                                sel
                            ).count() > 0:
                                success_found = True
                                logger.info(
                                    f"[{self.faucet_name}]"
                                    " Claim successful"
                                )
                                break

                        # Get updated balance
                        new_balance = (
                            await self.get_current_balance()
                        )

                        if success_found:
                            return ClaimResult(
                                success=True,
                                status="Claimed",
                                next_claim_minutes=60,
                                balance=new_balance,
                            )
                        logger.info(
                            f"[{self.faucet_name}] Roll "
                            "completed (success uncertain)"
                        )
                        return ClaimResult(
                            success=True,
                            status="Rolled",
                            next_claim_minutes=60,
                            balance=new_balance,
                        )

                    logger.info(
                        f"[{self.faucet_name}] Timer "
                        f"active: {timer_mins:.1f} "
                        "minutes remaining"
                    )
                    return ClaimResult(
                        success=True,
                        status="Timer Active",
                        next_claim_minutes=timer_mins,
                        balance=balance,
                    )

                logger.warning(
                    f"[{self.faucet_name}] Roll button "
                    "not found or not visible"
                )
                return ClaimResult(
                    success=False,
                    status="Roll Not Available",
                    next_claim_minutes=15,
                    balance=balance,
                )

            except asyncio.TimeoutError as e:
                logger.warning(
                    f"[{self.faucet_name}] Timeout error "
                    f"(attempt {retry_count + 1}): {e}"
                )
                retry_count += 1
                if retry_count >= max_retries:
                    return ClaimResult(
                        success=False,
                        status="Timeout after retries",
                        next_claim_minutes=30,
                    )
                await self.human_wait(5)

            except Exception as e:
                logger.error(
                    f"[{self.faucet_name}] "
                    f"Claim failed: {e}"
                )
                retry_count += 1
                if retry_count >= max_retries:
                    return ClaimResult(
                        success=False,
                        status=f"Error: {str(e)[:50]}",
                        next_claim_minutes=30,
                    )
                await self.human_wait(5)

    def get_jobs(self) -> List[Any]:
        """Return Cointiply-specific jobs for the scheduler.

        Returns:
            List of Job objects for claiming, withdrawal,
            and PTC ads.
        """
        from core.orchestrator import Job
        import time

        return [
            Job(
                priority=1,
                next_run=time.time(),
                name=f"{self.faucet_name} Claim",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="claim_wrapper",
            ),
            Job(
                priority=5,
                next_run=time.time() + 7200,
                name=f"{self.faucet_name} Withdraw",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="withdraw_wrapper",
            ),
            Job(
                priority=3,
                next_run=time.time() + 600,
                name=f"{self.faucet_name} PTC",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="ptc_wrapper",
            ),
        ]

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for Cointiply.

        Supports BTC, LTC, DOGE, DASH with varying thresholds:
        - BTC: 50,000 coins minimum
        - LTC/DOGE/DASH: 30,000 coins minimum

        Returns:
            ClaimResult with withdrawal status.
        """
        try:
            logger.info(
                f"[{self.faucet_name}] Navigating "
                "to withdrawal page..."
            )
            await self.page.goto(
                f"{self.base_url}/withdraw",
            )
            await self.handle_cloudflare()

            # Get current balance in coins
            balance = await self.get_current_balance()
            balance_coins = (
                float(balance) if balance else 0
            )

            # Check minimum thresholds
            min_btc = 50000
            min_other = 30000

            if balance_coins < min_other:
                logger.info(
                    f"[{self.faucet_name}] Balance "
                    f"{balance_coins} below minimum "
                    "threshold"
                )
                return ClaimResult(
                    success=True,
                    status="Low Balance",
                    next_claim_minutes=1440,
                )

            # Select cryptocurrency based on balance
            coin = None
            if balance_coins >= min_btc:
                coin = "BTC"
            else:
                for c in ["LTC", "DOGE", "DASH"]:
                    addr = self.get_withdrawal_address(c)
                    if addr:
                        coin = c
                        break

            if not coin:
                logger.warning(
                    f"[{self.faucet_name}] "
                    "No suitable withdrawal option"
                )
                return ClaimResult(
                    success=False,
                    status="No Suitable Option",
                    next_claim_minutes=1440,
                )

            # Click on the coin tab/button
            coin_selector = self.page.locator(
                f"button:has-text('{coin}'), "
                f".crypto-tab:has-text('{coin}')"
            )
            if await coin_selector.is_visible():
                await self.human_like_click(coin_selector)
                await self.random_delay(1, 2)

            # Fill wallet address
            address_field = self.page.locator(
                "input[name='address'], "
                "input.wallet-address, #address"
            )
            address = self.get_withdrawal_address(coin)
            await self.human_type(address_field, address)

            # Solve captcha if present
            await self.solver.solve_captcha(self.page)

            # Click withdraw
            withdraw_btn = self.page.locator(
                "button:has-text('Withdraw'), "
                "button.withdraw-btn"
            )
            await self.human_like_click(withdraw_btn)

            await self.random_delay(3, 5)

            # Check result
            content = await self.page.content()
            if (
                "success" in content.lower()
                or "email" in content.lower()
            ):
                logger.info(
                    f"[{self.faucet_name}] Withdrawal "
                    "request submitted! Check email "
                    "for confirmation."
                )
                return ClaimResult(
                    success=True,
                    status="Withdrawn (Pending Email)",
                    next_claim_minutes=1440,
                )

            return ClaimResult(
                success=False,
                status="Unknown Result",
                next_claim_minutes=360,
            )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Withdrawal error: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=60,
            )
