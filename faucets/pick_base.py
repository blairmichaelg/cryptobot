"""Shared base class for the Pick.io faucet family.

Provides common login, claim, registration, and withdrawal logic
that is shared across all Pick.io faucets (LitePick, TronPick,
USDPick, etc.).  Site-specific subclasses should define
``base_url`` and optionally override methods.

The Pick.io family sites share a common HTML structure:
    * Login / registration forms with hCaptcha / Turnstile.
    * Faucet page with ``#time`` timer and ``button.btn-primary``.
    * Withdrawal page with ``input[name="address"]`` and
      ``input[name="amount"]``.
"""

import asyncio
import logging
import random
import time
from typing import Any, List, Optional

from playwright.async_api import Page

from core.extractor import DataExtractor
from faucets.base import ClaimResult, FaucetBot

logger = logging.getLogger(__name__)


class PickFaucetBase(FaucetBot):
    """Base class for the Pick.io faucet family.

    These sites share a common structure and logic for login,
    claiming, and withdrawals.  Subclasses must define
    ``base_url`` and specific site details.
    """

    def __init__(
        self,
        settings: Any,
        page: Page,
        action_lock: Optional[asyncio.Lock] = None,
    ) -> None:
        """Initialize PickFaucetBase.

        Args:
            settings: Configuration settings object.
            page: Playwright Page instance.
            action_lock: Lock for synchronised browser actions.
        """
        super().__init__(settings, page, action_lock)
        self.faucet_name = "Pick Faucet"
        self.base_url = ""  # Set by subclass
        self.login_url = ""  # Often base_url/login
        self.faucet_url = ""  # Often base_url/faucet

    async def _navigate_with_retry(
        self,
        url: str,
        max_retries: int = 3,
    ) -> bool:
        """Navigate with exponential backoff for errors.

        Pick family faucets are known to use TLS fingerprinting
        and aggressive anti-bot measures that can result in
        ERR_CONNECTION_CLOSED.  This method provides robust
        retry logic with exponential backoff.

        Args:
            url: Target URL to navigate to.
            max_retries: Maximum number of retry attempts.

        Returns:
            True if navigation succeeded, False if all retries
            exhausted.
        """
        # Minimum 90s for Pick.io behind Cloudflare
        nav_timeout = max(
            getattr(self.settings, "timeout", 60000),
            90000,
        )

        for attempt in range(max_retries):
            try:
                # domcontentloaded first, commit fallback
                try:
                    response = await self.page.goto(
                        url, timeout=nav_timeout,
                    )
                except Exception:
                    response = await self.page.goto(
                        url,
                        timeout=nav_timeout,
                        wait_until="commit",
                    )

                if response:
                    logger.debug(
                        f"[{self.faucet_name}] Navigation "
                        "returned status "
                        f"{response.status}"
                    )
                    return True
                return True
            except Exception as e:
                error_str = str(e)
                # Retryable connection / TLS errors
                retryable = [
                    "ERR_CONNECTION_CLOSED",
                    "ERR_CONNECTION_RESET",
                    "net::",
                    "NS_ERROR",
                    "Timeout",
                    "ECONNREFUSED",
                ]
                if any(
                    err in error_str for err in retryable
                ):
                    wait_time = (2 ** attempt) * 3
                    logger.warning(
                        f"[{self.faucet_name}] Connection "
                        f"failed on attempt "
                        f"{attempt + 1}/{max_retries}: "
                        f"{error_str[:100]}. Retrying "
                        f"in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"[{self.faucet_name}] "
                        "Non-retryable navigation "
                        f"error: {e}"
                    )
                    return False

        logger.error(
            f"[{self.faucet_name}] All {max_retries} "
            f"navigation attempts failed for {url}"
        )
        return False

    async def register(
        self,
        email: str,
        password: str,
        wallet_address: Optional[str] = None,
    ) -> bool:
        """Standard registration for Pick.io family.

        Navigates to the registration page, fills the form,
        solves captchas, and verifies success.

        Args:
            email: Email address for registration.
            password: Password for the account.
            wallet_address: Optional wallet address for
                withdrawals.

        Returns:
            True if registration was successful.
        """
        if not self.base_url:
            logger.error(
                "Base URL not set for "
                "PickFaucetBase subclass"
            )
            return False

        register_url = f"{self.base_url}/signup.php"
        logger.info(
            f"[{self.faucet_name}] Registering "
            f"at {register_url}"
        )

        try:
            if not await self._navigate_with_retry(
                register_url,
            ):
                logger.error(
                    f"[{self.faucet_name}] Failed to "
                    "navigate to registration page"
                )
                return False
            await self.handle_cloudflare()
            await self.close_popups()

            # Fill registration form
            email_field = self.page.locator(
                'input[type="email"], '
                'input[name="email"], '
                'input#email'
            )
            pass_field = self.page.locator(
                'input[type="password"], '
                'input[name="password"], '
                'input#password'
            )
            confirm_pass_field = self.page.locator(
                'input[name="password2"], '
                'input[name="confirm_password"], '
                'input#password2'
            )

            await email_field.fill(email)
            await pass_field.fill(password)

            # Fill confirm password if it exists
            if await confirm_pass_field.count() > 0:
                await confirm_pass_field.fill(password)

            # Fill wallet address if provided
            if wallet_address:
                wallet_field = self.page.locator(
                    'input[name="address"], '
                    'input[name="wallet"], '
                    'input#address'
                )
                if await wallet_field.count() > 0:
                    await wallet_field.fill(
                        wallet_address,
                    )

            # Check for and solve captcha
            captcha_locator = self.page.locator(
                ".h-captcha, .cf-turnstile"
            )
            if (
                await captcha_locator.count() > 0
                and await captcha_locator.first
                .is_visible()
            ):
                logger.info(
                    f"[{self.faucet_name}] Solving "
                    "registration captcha..."
                )
                await self.solver.solve_captcha(
                    self.page,
                )
                await self.random_delay(2, 5)

            # Find and click register button
            register_btn = self.page.locator(
                'button.btn, '
                'button.process_btn, '
                'button:has-text("Register"), '
                'button:has-text("Sign Up"), '
                'button:has-text("Create Account")'
            )
            await self.human_like_click(register_btn)

            await self.page.wait_for_load_state(
                "domcontentloaded", timeout=30000,
            )

            # Check for success indicators
            page_content = await self.page.content()
            success_indicators = [
                "successfully registered",
                "registration successful",
                "account created",
                "welcome",
                "check your email",
                "verification email",
            ]

            if any(
                ind in page_content.lower()
                for ind in success_indicators
            ):
                logger.info(
                    f"[{self.faucet_name}] Registration "
                    f"successful for {email}"
                )
                return True

            # Check if auto-logged in
            if await self.is_logged_in():
                logger.info(
                    f"[{self.faucet_name}] Registration "
                    "successful, auto-logged in"
                )
                return True

            logger.warning(
                f"[{self.faucet_name}] Registration "
                "uncertain - no clear success message"
            )
            return False

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Registration error: {e}"
            )
            return False

    async def login(self) -> bool:
        """Standard login for Pick.io family.

        Navigates to the login page, fills credentials,
        solves any captchas, and verifies the login state.

        Returns:
            True if login was successful.
        """
        if not self.base_url:
            logger.error(
                "Base URL not set for "
                "PickFaucetBase subclass"
            )
            return False

        login_urls = [
            f"{self.base_url}/login.php",
            f"{self.base_url}/login",
            f"{self.base_url}/?op=login",
            self.base_url,
        ]
        logger.info(
            f"[{self.faucet_name}] Logging in "
            f"(candidate URLs: {len(login_urls)})"
        )

        creds = self.get_credentials(
            self.faucet_name.lower(),
        )
        if not creds:
            logger.error(
                f"[{self.faucet_name}] "
                "No credentials found"
            )
            return False

        login_id = (
            creds.get("email") or creds.get("username")
        )
        if not login_id:
            logger.error(
                f"[{self.faucet_name}] Credentials "
                "missing email/username"
            )
            return False
        login_id = self.strip_email_alias(login_id)

        try:
            async def _first_visible(
                selectors: List[str],
            ) -> Any:
                """Find the first visible element."""
                for selector in selectors:
                    try:
                        locator = self.page.locator(
                            selector,
                        )
                        if await locator.count() > 0:
                            target = locator.first
                            if await target.is_visible():
                                return target
                    except Exception:
                        continue
                return None

            email_selectors = [
                'input#user_email',
                'input[type="email"]',
                'input[name="email"]',
                'input#email',
                'input[name="username"]',
                'input[name="login"]',
                'input[name="user"]',
                'input[name="user_name"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="username" i]',
                'form input[type="text"]',
            ]
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input#password',
                'input[name="pass"]',
                'input[placeholder*="password" i]',
            ]
            login_trigger_selectors = [
                'a:has-text("Login")',
                'a:has-text("Log in")',
                'button:has-text("Login")',
                'button:has-text("Log in")',
                'a[href*="login"]',
                'button#login',
                'button#process_login',
                '.login-btn',
                '.login-button',
            ]

            email_target = None
            pass_target = None
            for login_url in login_urls:
                logger.info(
                    f"[{self.faucet_name}] "
                    f"Navigating to {login_url}"
                )
                if not await self._navigate_with_retry(
                    login_url,
                ):
                    continue
                # Wait for Cloudflare challenges
                await self.handle_cloudflare(
                    max_wait_seconds=30,
                )
                await self.close_popups()

                # Warm up page for behavioral baseline
                await self.warm_up_page()

                if await self.is_logged_in():
                    logger.info(
                        f"[{self.faucet_name}] "
                        "Already logged in"
                    )
                    return True

                email_target = await _first_visible(
                    email_selectors,
                )
                pass_target = await _first_visible(
                    password_selectors,
                )
                if not email_target or not pass_target:
                    login_trigger = await _first_visible(
                        login_trigger_selectors,
                    )
                    if login_trigger:
                        await self.human_like_click(
                            login_trigger,
                        )
                        await self.random_delay(1.0, 2.0)
                        email_target = (
                            await _first_visible(
                                email_selectors,
                            )
                        )
                        pass_target = (
                            await _first_visible(
                                password_selectors,
                            )
                        )

                if email_target and pass_target:
                    break

            if not email_target or not pass_target:
                logger.error(
                    f"[{self.faucet_name}] Login fields"
                    " not found on page"
                )
                return False

            await self.human_type(
                email_target, login_id,
            )
            await self.random_delay(0.4, 0.9)
            await self.human_type(
                pass_target, creds['password'],
            )

            # Select preferred captcha type if available
            captcha_dropdown = self.page.locator(
                '#select_captcha, '
                'select[name="captcha"]'
            )
            try:
                if (
                    await captcha_dropdown.count() > 0
                    and await captcha_dropdown.first
                    .is_visible()
                ):
                    if self.solver.api_key:
                        try:
                            await (
                                captcha_dropdown.first
                                .select_option(
                                    label="hCaptcha",
                                )
                            )
                        except Exception:
                            try:
                                await (
                                    captcha_dropdown.first
                                    .select_option(
                                        label="Turnstile",
                                    )
                                )
                            except Exception:
                                pass
                        await self.random_delay(0.5, 1.0)
            except Exception:
                pass

            # Check for captcha
            captcha_locator = self.page.locator(
                ".h-captcha, .cf-turnstile, .g-recaptcha"
            )
            try:
                captcha_count = (
                    await captcha_locator.count()
                )
            except Exception:
                captcha_count = 0
            if not isinstance(captcha_count, int):
                captcha_count = 0
            if (
                captcha_count > 0
                and await captcha_locator.first
                .is_visible()
            ):
                logger.info(
                    f"[{self.faucet_name}] "
                    "Solving login captcha..."
                )
                solved = False
                for attempt in range(3):
                    try:
                        if await self.solver.solve_captcha(
                            self.page,
                        ):
                            solved = True

                            # Enable submit button
                            try:
                                await self.page.evaluate("""
                                    const btns =
                                        document
                                        .querySelectorAll(
                                            'button'
                                            + '[type="submit"]'
                                            + ', button.btn'
                                            + ', button'
                                            + '.process_btn'
                                            + ', input'
                                            + '[type="submit"]'
                                        );
                                    btns.forEach(btn => {
                                        if (btn.disabled) {
                                            btn.disabled
                                                = false;
                                            btn
                                            .removeAttribute(
                                                'disabled'
                                            );
                                        }
                                    });
                                """)
                            except Exception:
                                pass

                            break
                        await self.human_wait(2)
                    except Exception as captcha_err:
                        logger.warning(
                            f"[{self.faucet_name}] "
                            "Captcha attempt "
                            f"{attempt + 1} failed: "
                            f"{captcha_err}"
                        )
                        await self.human_wait(3)
                if not solved:
                    logger.error(
                        f"[{self.faucet_name}] Captcha "
                        "solve failed on login"
                    )
                    return False

            # Find login button
            login_btn_selectors = [
                'button#process_login',
                '#login_button',
                'button.login-btn',
                'button.login-button',
                'button.process_btn',
                'button:has-text("Login")',
                'button:has-text("Log in")',
                'button[type="submit"]:visible',
                'input[type="submit"]:visible',
                'button.btn:visible'
                ':has-text("Login")',
            ]

            login_btn = None
            for sel in login_btn_selectors:
                try:
                    locator = self.page.locator(sel).first
                    if await locator.is_visible(
                        timeout=2000,
                    ):
                        login_btn = locator
                        logger.info(
                            f"[{self.faucet_name}] "
                            "Using login button "
                            f"selector: {sel}"
                        )
                        break
                except Exception:
                    continue

            if not login_btn:
                logger.error(
                    f"[{self.faucet_name}] No visible "
                    "login button found"
                )
                return False

            # Submit login
            await self.thinking_pause()
            await self.human_like_click(login_btn)

            try:
                await self.page.wait_for_load_state(
                    "domcontentloaded", timeout=30000,
                )
            except Exception:
                pass

            failure = await self.check_failure_states()
            if failure:
                logger.error(
                    f"[{self.faucet_name}] Failure state "
                    "detected after login: "
                    f"{failure}"
                )
                return False

            if await self.is_logged_in():
                logger.info(
                    f"[{self.faucet_name}] "
                    "Login successful"
                )
                return True

            error_selectors = [
                ".alert-danger",
                ".alert",
                ".error",
                ".text-danger",
                "[class*='error']",
            ]
            for selector in error_selectors:
                try:
                    err_loc = self.page.locator(selector)
                    if (
                        await err_loc.count() > 0
                        and await err_loc.first
                        .is_visible()
                    ):
                        err_text = (
                            await err_loc.first
                            .text_content()
                        )
                        logger.warning(
                            f"[{self.faucet_name}] "
                            f"Login error: {err_text}"
                        )
                        break
                except Exception:
                    continue

            logger.warning(
                f"[{self.faucet_name}] Login did not "
                "result in dashboard"
            )
            return False
        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Login error: {e}"
            )
            return False

    async def is_logged_in(self) -> bool:
        """Check if logged in via logout link or balance.

        Returns:
            True if logout link or balance elements visible.
        """
        try:
            logout = self.page.locator(
                'a:has-text("Logout"), '
                'a[href*="logout"]'
            )
            if (
                await logout.count() > 0
                and await logout.first.is_visible()
            ):
                return True
        except Exception:
            pass

        balance_selectors = [
            ".balance",
            ".navbar-right .balance",
            "#balance",
            "span.balance",
        ]
        for selector in balance_selectors:
            try:
                if await self.page.locator(
                    selector,
                ).is_visible(timeout=2000):
                    return True
            except Exception:
                continue

        # Fallback on URL hint
        try:
            url_lower = self.page.url.lower()
            url_tokens = [
                "dashboard", "account", "profile",
            ]
            if any(t in url_lower for t in url_tokens):
                return True
        except Exception:
            pass

        return False

    async def get_balance(
        self,
        selector: str = ".balance",
        fallback_selectors: Optional[List[str]] = None,
    ) -> str:
        """Extract balance from the header.

        Args:
            selector: Primary CSS selector for balance.
            fallback_selectors: Alternative selectors to try.

        Returns:
            The extracted balance string, or "0" if
            extraction fails.
        """
        selectors = [
            selector,
            ".navbar-right .balance",
            "#balance",
        ]
        fallback = fallback_selectors or [
            ".balance",
            ".navbar-right .balance",
            "#balance",
        ]
        for current_selector in selectors:
            balance = await super().get_balance(
                current_selector,
                fallback_selectors=fallback,
            )
            if balance and balance != "0":
                return balance
        return "0"

    def get_jobs(self) -> List[Any]:
        """Standard job definition for the Pick family.

        Returns:
            List of Job objects for the scheduler.
        """
        from core.orchestrator import Job

        f_type = self.faucet_name.lower()

        return [
            Job(
                priority=2,
                next_run=time.time(),
                name=f"{self.faucet_name} Claim",
                profile=None,
                faucet_type=f_type,
                job_type="claim_wrapper",
            ),
            Job(
                priority=5,
                next_run=time.time() + 3600,
                name=f"{self.faucet_name} Withdraw",
                profile=None,
                faucet_type=f_type,
                job_type="withdraw_wrapper",
            ),
        ]

    async def claim(self) -> ClaimResult:
        """Perform the hourly faucet claim.

        Handles navigation, cooldown checks, captcha solving,
        and clicking the claim button.

        Returns:
            ClaimResult with the claim outcome.
        """
        faucet_url = f"{self.base_url}/faucet.php"
        logger.info(
            f"[{self.faucet_name}] Navigating to "
            f"faucet: {faucet_url}"
        )

        if not await self._navigate_with_retry(faucet_url):
            logger.error(
                f"[{self.faucet_name}] Failed to "
                "navigate to faucet page"
            )
            return ClaimResult(
                success=False,
                status="Connection Failed",
                next_claim_minutes=15,
            )
        await self.handle_cloudflare()
        await self.close_popups()

        # Warm up and simulate natural browsing
        await self.warm_up_page()
        if random.random() < 0.3:
            await self.simulate_tab_activity()

        # Check for existing timer
        timer_text = None
        try:
            timer_loc = self.page.locator("#time")
            if await timer_loc.count() > 0:
                timer_text = (
                    await timer_loc.first.text_content()
                )
        except Exception:
            timer_text = None

        if not timer_text:
            try:
                auto_sel = (
                    await DataExtractor
                    .find_timer_selector_in_dom(self.page)
                )
                if auto_sel:
                    auto_loc = self.page.locator(auto_sel)
                    if await auto_loc.count() > 0:
                        timer_text = (
                            await auto_loc.first
                            .text_content()
                        )
            except Exception:
                timer_text = None

        if timer_text and any(
            c.isdigit() for c in timer_text
        ):
            minutes = (
                DataExtractor.parse_timer_to_minutes(
                    timer_text,
                )
            )
            if minutes > 0:
                logger.info(
                    f"[{self.faucet_name}] Faucet on "
                    f"cooldown: {minutes}m remaining"
                )
                return ClaimResult(
                    success=True,
                    status="Cooldown",
                    next_claim_minutes=minutes,
                    balance=await self.get_balance(),
                )

        try:
            # Select preferred captcha type if available
            captcha_dropdown = self.page.locator(
                '#select_captcha, '
                'select[name="captcha"]'
            )
            try:
                if (
                    await captcha_dropdown.count() > 0
                    and await captcha_dropdown.first
                    .is_visible()
                ):
                    if self.solver.api_key:
                        try:
                            await (
                                captcha_dropdown.first
                                .select_option(
                                    label="hCaptcha",
                                )
                            )
                        except Exception:
                            try:
                                await (
                                    captcha_dropdown.first
                                    .select_option(
                                        label="Turnstile",
                                    )
                                )
                            except Exception:
                                pass
                        await self.random_delay(0.5, 1.0)
            except Exception:
                pass

            # Check for captcha on the faucet page
            captcha_loc = self.page.locator(
                ".h-captcha, .cf-turnstile, .g-recaptcha"
            )
            try:
                captcha_count = (
                    await captcha_loc.count()
                )
            except Exception:
                captcha_count = 0
            if (
                captcha_count > 0
                and await captcha_loc.first.is_visible()
            ):
                logger.info(
                    f"[{self.faucet_name}] "
                    "Solving faucet captcha..."
                )
                solved = False
                for attempt in range(3):
                    try:
                        if await self.solver.solve_captcha(
                            self.page,
                        ):
                            solved = True

                            # Enable submit button
                            try:
                                await self.page.evaluate("""
                                    const btns =
                                        document
                                        .querySelectorAll(
                                            'button'
                                            + '[type="submit"]'
                                            + ', button'
                                            + '.btn-primary'
                                            + ', button#claim'
                                            + ', button.btn'
                                        );
                                    btns.forEach(btn => {
                                        if (btn.disabled) {
                                            btn.disabled
                                                = false;
                                            btn
                                            .removeAttribute(
                                                'disabled'
                                            );
                                        }
                                    });
                                """)
                            except Exception:
                                pass

                            break
                        await self.human_wait(2)
                    except Exception as captcha_err:
                        logger.warning(
                            f"[{self.faucet_name}] "
                            "Captcha attempt "
                            f"{attempt + 1} failed: "
                            f"{captcha_err}"
                        )
                        await self.human_wait(3)
                if not solved:
                    return ClaimResult(
                        success=False,
                        status="CAPTCHA Failed",
                        next_claim_minutes=10,
                    )

                await self.random_delay(2, 5)

            # Simulate reading before claiming
            await self.simulate_reading(
                duration=random.uniform(1.5, 3.0),
            )
            if random.random() < 0.4:
                await self.natural_scroll(
                    distance=random.randint(50, 150),
                    direction=1,
                )
                await asyncio.sleep(
                    random.uniform(0.3, 0.8),
                )
            await self.thinking_pause()

            # Wait after CAPTCHA for page to update
            await self.human_wait(2)

            claim_btn = self.page.locator(
                'button.btn-primary, '
                'button:has-text("Claim"), '
                'button:has-text("Roll"), '
                'button#claim, '
                'button[type="submit"], '
                '.btn-success, '
                'button.get-reward'
            )

            # Try to wait for button visibility
            try:
                await claim_btn.first.wait_for(
                    state="visible", timeout=5000,
                )
            except Exception:
                pass

            if not await claim_btn.first.is_visible():
                logger.warning(
                    f"[{self.faucet_name}] "
                    "Claim button not visible"
                )
                all_buttons = (
                    await self.page
                    .query_selector_all("button")
                )
                logger.debug(
                    f"[{self.faucet_name}] Found "
                    f"{len(all_buttons)} total "
                    "buttons on page"
                )
                return ClaimResult(
                    success=False,
                    status="Button Not Found",
                    next_claim_minutes=15,
                    balance=await self.get_balance(),
                )

            await self.human_like_click(claim_btn)
            await self.random_delay(3, 6)

            # Extract result message
            result_msg_loc = self.page.locator(
                ".alert-success, #success, .message"
            )
            if await result_msg_loc.count() > 0:
                result_msg = (
                    await result_msg_loc.first
                    .text_content()
                )
                logger.info(
                    f"[{self.faucet_name}] Claim "
                    "successful: "
                    f"{result_msg.strip()}"
                )
                return ClaimResult(
                    success=True,
                    status="Claimed",
                    next_claim_minutes=60,
                    amount=result_msg.strip(),
                    balance=await self.get_balance(),
                )

            return ClaimResult(
                success=False,
                status=(
                    "Claim failed or result not found"
                ),
                next_claim_minutes=10,
            )

        except Exception as e:
            logger.error(
                f"[{self.faucet_name}] "
                f"Claim error: {e}"
            )
            return ClaimResult(
                success=False,
                status=f"Error: {e}",
                next_claim_minutes=15,
            )

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for Pick.io family.

        Checks balance against minimum withdrawal thresholds,
        fills the withdrawal form, solves any required captchas,
        and submits the request.

        Returns:
            ClaimResult with the withdrawal outcome.
        """
        withdraw_url = f"{self.base_url}/withdraw.php"
        logger.info(
            f"[{self.faucet_name}] Navigating to "
            f"withdrawal: {withdraw_url}"
        )

        if not await self._navigate_with_retry(
            withdraw_url,
        ):
            logger.error(
                f"[{self.faucet_name}] Failed to "
                "navigate to withdrawal page"
            )
            return ClaimResult(
                success=False,
                status="Connection Failed",
                next_claim_minutes=60,
            )
        await self.handle_cloudflare()

        # Determine coin from faucet name
        coin = (
            self.faucet_name.replace("Pick", "")
            .upper()
        )
        if coin == "LITE":
            coin = "LTC"
        elif coin == "TRON":
            coin = "TRX"
        elif coin == "USD":
            coin = "USDT"

        balance_str = await self.get_balance()
        balance_clean = DataExtractor.extract_balance(
            balance_str,
        )
        try:
            balance = (
                float(balance_clean)
                if balance_clean
                else 0.0
            )
        except Exception:
            logger.error(
                f"[{self.faucet_name}] Could not parse "
                f"balance '{balance_str}'"
            )
            balance = 0.0

        # Pull min_withdraw from settings
        min_withdraw = 0.0
        try:
            from core.analytics import CryptoPriceFeed
            decimals = (
                CryptoPriceFeed.CURRENCY_DECIMALS.get(
                    coin, 8,
                )
            )
            threshold = (
                self.settings.withdrawal_thresholds.get(
                    coin, {},
                )
                if hasattr(
                    self.settings,
                    "withdrawal_thresholds",
                )
                else {}
            )
            if (
                isinstance(threshold, dict)
                and threshold.get("min") is not None
            ):
                min_withdraw = (
                    float(threshold.get("min"))
                    / (10 ** decimals)
                )
        except Exception:
            min_withdraw = 0.0

        # Allow wallet_addresses dict to override
        wallet_info = (
            self.settings.wallet_addresses.get(coin)
            if hasattr(self.settings, "wallet_addresses")
            else None
        )
        if (
            isinstance(wallet_info, dict)
            and wallet_info.get('min_withdraw')
            is not None
        ):
            try:
                min_withdraw = float(
                    wallet_info.get('min_withdraw'),
                )
            except Exception:
                pass

        if balance < min_withdraw:
            logger.info(
                f"[{self.faucet_name}] Balance "
                f"{balance} {coin} below minimum "
                f"{min_withdraw}. Skipping."
            )
            return ClaimResult(
                success=True,
                status="Low Balance",
                next_claim_minutes=1440,
            )

        # Fill withdrawal form
        try:
            address_field = self.page.locator(
                'input[name="address"], #address'
            )
            amount_field = self.page.locator(
                'input[name="amount"], #amount'
            )

            # Use 'withdraw all' button if exists
            all_btn = self.page.locator(
                'button:has-text("Withdraw all"), '
                '#withdraw-all'
            )
            if await all_btn.is_visible():
                await self.human_like_click(all_btn)
            else:
                await amount_field.fill(str(balance))

            # Ensure address is set
            withdraw_address = (
                self.get_withdrawal_address(coin)
            )
            if not withdraw_address:
                logger.error(
                    f"[{self.faucet_name}] No withdrawal "
                    "address configured for "
                    f"{coin}"
                )
                return ClaimResult(
                    success=False,
                    status="No Address",
                    next_claim_minutes=1440,
                )

            if await address_field.count() == 0:
                logger.error(
                    f"[{self.faucet_name}] Withdrawal "
                    "address field not found"
                )
                return ClaimResult(
                    success=False,
                    status="No Address Field",
                    next_claim_minutes=1440,
                )

            await self.human_type(
                address_field, withdraw_address,
            )

            # Solve Captcha
            await self.solver.solve_captcha(self.page)

            withdraw_btn = self.page.locator(
                'button:has-text("Withdraw"), '
                'button.process_btn'
            )
            await self.human_like_click(withdraw_btn)

            await self.random_delay(3, 8)

            # Verify Success
            content = await self.page.content()
            if "success" in content.lower():
                logger.info(
                    f"[{self.faucet_name}] Withdrawal "
                    "processed for "
                    f"{balance} {coin}!"
                )
                return ClaimResult(
                    success=True,
                    status="Withdrawn",
                    next_claim_minutes=1440,
                )

            return ClaimResult(
                success=False,
                status=(
                    "Withdrawal Failed or pending"
                ),
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
                next_claim_minutes=720,
            )


class PickFaucetBot(PickFaucetBase):
    """Generic Pick.io family bot instantiated by name/URL.

    Used for batch registration and testing utilities where a
    specific per-coin subclass is not needed.  For production
    claiming, prefer dedicated subclasses (``LitePickBot``,
    ``TronPickBot``, etc.).
    """

    def __init__(
        self,
        settings: Any,
        page: Page,
        site_name: str,
        site_url: str,
        **kwargs: Any,
    ) -> None:
        """Initialize PickFaucetBot.

        Args:
            settings: Configuration settings object.
            page: Playwright Page instance.
            site_name: Human-readable site name.
            site_url: Base URL for the site.
            **kwargs: Additional arguments passed to base.
        """
        super().__init__(settings, page, **kwargs)
        self.faucet_name = site_name
        self.base_url = site_url
        self.coin = (
            site_name.replace("Pick", "").upper()
        )
