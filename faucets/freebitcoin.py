from .base import FaucetBot, ClaimResult
from core.extractor import DataExtractor
import logging
import asyncio

logger = logging.getLogger(__name__)

class FreeBitcoinBot(FaucetBot):
    def __init__(self, settings, page, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = "FreeBitcoin"
        self.base_url = "https://freebitco.in"

    async def is_logged_in(self) -> bool:
        balance_selectors = [
            "#balance",
            ".balance",
            "[data-balance]",
            ".user-balance",
            "span.balance",
            "#balance_small",
            "#balance_small span",
            ".balance-amount",
            "a[href*='logout']",
            "a:has-text('Logout')",
            "a:has-text('Sign out')",
            "a[href*='logout.php']",
            "#logout",
            ".logout",
            ".account-balance",
            "[data-testid='logout']",
        ]
        for selector in balance_selectors:
            try:
                if await self.page.locator(selector).is_visible(timeout=3000):
                    return True
            except Exception:
                continue
        return False

    async def _find_selector(self, selectors: list, element_name: str = "element", timeout: int = 5000, include_frames: bool = True):
        """
        Try multiple selectors and return the first one that exists and is visible.
        
        Args:
            selectors: List of CSS selectors to try
            element_name: Name of element for logging
            timeout: Total timeout in milliseconds
            
        Returns:
            Locator if found, None otherwise
        """
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                # is_visible() already checks existence internally
                if await locator.is_visible(timeout=timeout):
                    logger.debug(f"[FreeBitcoin] Found {element_name} with selector: {selector}")
                    return locator
            except Exception:
                continue

        if include_frames:
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                for selector in selectors:
                    try:
                        locator = frame.locator(selector).first
                        if await locator.is_visible(timeout=timeout):
                            logger.debug(f"[FreeBitcoin] Found {element_name} in frame with selector: {selector}")
                            return locator
                    except Exception:
                        continue
        
        logger.warning(f"[FreeBitcoin] Could not find {element_name}. Tried selectors: {selectors}")
        return None

    async def _find_selector_any_frame(self, selectors: list, element_name: str = "element", timeout: int = 5000):
        """
        Try multiple selectors across the main page and iframes.

        Returns:
            Locator if found, None otherwise
        """
        locator = await self._find_selector(selectors, element_name=element_name, timeout=timeout)
        if locator:
            return locator

        for frame in self.page.frames:
            if frame == self.page.main_frame:
                continue
            for selector in selectors:
                try:
                    candidate = frame.locator(selector).first
                    if await candidate.is_visible(timeout=timeout):
                        logger.debug(f"[FreeBitcoin] Found {element_name} in iframe with selector: {selector}")
                        return candidate
                except Exception:
                    continue

        logger.warning(f"[FreeBitcoin] Could not find {element_name} in any frame. Tried selectors: {selectors}")
        return None

    async def login(self) -> bool:
        # Check for override (Multi-Account Loop)
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("freebitcoin")
            
        if not creds: 
            logger.error("[FreeBitcoin] Credentials missing - set FREEBITCOIN_USERNAME and FREEBITCOIN_PASSWORD")
            return False

        try:
            login_urls = [
                f"{self.base_url}/?op=login",
                f"{self.base_url}/login",
                f"{self.base_url}/login.php",
                self.base_url,
            ]
            email_field = None
            password_field = None

            # Try multiple selectors for email/username field
            email_selectors = [
                "input[name='btc_address']",  # FreeBitcoin uses BTC address as login
                "input[name='login_form[btc_address]']",
                "input[name='login_form[username]']",
                "input[name='login_form[login]']",
                "input[name='login_form[email]']",
                "input[name='login_form[username_or_email]']",
                "input[name='login']",
                "input[name='username']",
                "input[name='login_email_input']",
                "input[type='email']",
                "input[name='email']",
                "#email",
                "#login_form_email",
                "#login_form_login",
                "#login_form_username",
                "#login_form_btc_address",
                "input#login_form_btc_address",
                "#login_form_bt_address",  # legacy misspelling seen in older versions
                "form input[type='text']:first-of-type",
            ]

            # Try multiple selectors for password field
            password_selectors = [
                "input[name='password']",
                "input[name='login_form[password]']",
                "input[name='login_form[pass]']",
                "input[name='login_form[password_confirmation]']",
                "input[name='login_password_input']",
                "input[type='password']",
                "#password",
                "#login_form_password",
            ]

            login_trigger_selectors = [
                "a[href*='login']",
                "a[href*='op=login']",
                "button:has-text('Login')",
                "button:has-text('Log In')",
                "button:has-text('Sign in')",
                "a:has-text('Login')",
                "a:has-text('Log In')",
                "#login_link",
                ".login-link",
            ]

            login_form_selectors = [
                "form#login_form",
                "#login_form",
                "form[action*='login']",
                "form[action*='op=login']",
            ]

            nav_timeout = max(getattr(self.settings, "timeout", 60000), 60000)

            for login_url in login_urls:
                logger.info(f"[FreeBitcoin] Navigating to login page: {login_url}")
                # Use shorter timeout and more lenient wait strategy for slow proxies
                try:
                    response = await self.page.goto(login_url, wait_until="domcontentloaded", timeout=nav_timeout)
                except Exception as e:
                    logger.warning(f"[FreeBitcoin] Initial navigation slow, retrying with commit: {e}")
                    response = await self.page.goto(login_url, wait_until="commit", timeout=nav_timeout)
                if response is not None:
                    try:
                        status = response.status
                        if status >= 400:
                            logger.error(f"[FreeBitcoin] Login page returned HTTP {status}. URL: {response.url}")
                            try:
                                self.last_error_type = self.classify_error(None, None, status)
                            except Exception:
                                pass
                            if status in (401, 403, 429):
                                await self.random_delay(1.0, 2.0)
                                return False
                    except Exception:
                        pass
                await self.random_delay(2, 4)

                # Handle Cloudflare if present
                await self.handle_cloudflare(max_wait_seconds=60)

                # Close cookie banner if present
                await self.close_popups()

                # Log current page state for debugging
                logger.debug(f"[FreeBitcoin] Current URL: {self.page.url}")

                if await self.is_logged_in():
                    logger.info("✅ [FreeBitcoin] Session already active after navigation")
                    return True

                try:
                    await self.page.wait_for_selector(",".join(login_form_selectors), timeout=6000)
                except Exception:
                    pass

                email_field = await self._find_selector_any_frame(email_selectors, "email/username field", timeout=8000)
                if not email_field:
                    login_trigger = await self._find_selector_any_frame(login_trigger_selectors, "login trigger", timeout=4000)
                    if login_trigger:
                        logger.debug("[FreeBitcoin] Opening login form/modal...")
                        await self.human_like_click(login_trigger)
                        await self.random_delay(1.0, 2.0)
                        email_field = await self._find_selector_any_frame(email_selectors, "email/username field", timeout=8000)
                    if not email_field and await self.is_logged_in():
                        logger.info("✅ [FreeBitcoin] Session active after login trigger")
                        return True
                if email_field:
                    password_field = await self._find_selector_any_frame(password_selectors, "password field", timeout=5000)
                    if password_field:
                        break

            if not email_field:
                logger.error("[FreeBitcoin] Could not find email/username field on login page")
                # Take screenshot for debugging
                try:
                    await self.page.screenshot(path="logs/freebitcoin_login_failed_no_email_field.png")
                    logger.info("[FreeBitcoin] Screenshot saved to logs/freebitcoin_login_failed_no_email_field.png")
                except Exception:
                    pass
                return False

            if not password_field:
                logger.error("[FreeBitcoin] Could not find password field on login page")
                try:
                    await self.page.screenshot(path="logs/freebitcoin_login_failed_no_password_field.png")
                    logger.info("[FreeBitcoin] Screenshot saved to logs/freebitcoin_login_failed_no_password_field.png")
                except Exception:
                    pass
                return False

            # Fill Login with human-like typing
            login_id = creds.get("username") or creds.get("email")
            if not login_id:
                logger.error("[FreeBitcoin] Credentials missing username/email")
                return False
            login_id = self.strip_email_alias(login_id)
            username_display = login_id[:10] + "***" if len(login_id) > 10 else login_id[:3] + "***"
            logger.info(f"[FreeBitcoin] Filling login credentials for user: {username_display}")
            await self.human_type(email_field, login_id)
            await self.random_delay(0.5, 1.5)
            await self.human_type(password_field, creds['password'])
            await self.idle_mouse(1.0)  # Simulate thinking time before submission
            
            # Check for 2FA field
            twofa_selectors = [
                "#login_2fa_input",
                "input[name='2fa']",
                "input[name='twofa']",
                "input[placeholder*='2FA' i]",
            ]
            twofa_field = await self._find_selector_any_frame(twofa_selectors, "2FA field", timeout=2000)
            if twofa_field:
                logger.warning("[FreeBitcoin] 2FA DETECTED! Manual intervention required.")
                # Don't proceed automatically with 2FA
                max_login_attempts = 2
                for login_attempt in range(1, max_login_attempts + 1):
                    error_text = None
                return False

            # Check for CAPTCHA on login page
            logger.debug("[FreeBitcoin] Checking for login CAPTCHA...")
            try:
                try:
                    await self.page.wait_for_selector(
                        "iframe[src*='turnstile'], iframe[src*='challenges.cloudflare.com'], .cf-turnstile, [id*='cf-turnstile']",
                        timeout=8000
                    )
                except Exception:
                    pass
                await self.solver.solve_captcha(self.page)
                logger.debug("[FreeBitcoin] Login CAPTCHA solved")
            except Exception as captcha_err:
                logger.debug(f"[FreeBitcoin] No CAPTCHA required or solve failed: {captcha_err}")
                # Continue anyway, CAPTCHA might not be required

            # Try multiple selectors for submit button
            submit_selectors = [
                "#login_button",
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Login')",
                "button:has-text('Log In')",
                "button:has-text('Sign In')",
                ".login-button",
                "#login_form_button",
            ]
            
            submit_btn = await self._find_selector_any_frame(submit_selectors, "submit button", timeout=5000)
            if submit_btn:
                logger.debug("[FreeBitcoin] Clicking submit button...")
                await self.human_like_click(submit_btn)
            else:
                logger.warning("[FreeBitcoin] Submit button not found. Falling back to Enter key submission.")
                try:
                    await password_field.press("Enter")
                except Exception:
                    try:
                        await self.page.keyboard.press("Enter")
                    except Exception:
                        logger.error("[FreeBitcoin] Enter key fallback failed")
                        try:
                            await self.page.screenshot(path="logs/freebitcoin_login_failed_no_submit.png")
                            logger.info("[FreeBitcoin] Screenshot saved to logs/freebitcoin_login_failed_no_submit.png")
                        except Exception:
                            pass
                        return False
            
            # Wait for navigation or login success
            logger.debug("[FreeBitcoin] Waiting for login to complete...")
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                await self.page.wait_for_url(f"{self.base_url}/**", timeout=45000)
                logger.debug(f"[FreeBitcoin] Navigation completed to: {self.page.url}")
            except asyncio.TimeoutError:
                logger.warning("[FreeBitcoin] Login redirect timeout, checking if logged in anyway...")
            
            # Small delay to let page settle
            await self.random_delay(2, 3)

            # Re-check CAPTCHA after submit (some pages render challenge only after submit)
            try:
                try:
                    await self.page.wait_for_selector(
                        "iframe[src*='turnstile'], iframe[src*='challenges.cloudflare.com'], .cf-turnstile, [id*='cf-turnstile']",
                        timeout=8000
                    )
                except Exception:
                    pass
                await self.solver.solve_captcha(self.page)
            except Exception as captcha_err:
                logger.debug(f"[FreeBitcoin] Post-submit CAPTCHA solve skipped/failed: {captcha_err}")
            
            # Check if logged in
            if await self.is_logged_in():
                logger.info("✅ [FreeBitcoin] Login successful (session detected)")
                return True
            
            # Login failed - check for error messages
            logger.error("[FreeBitcoin] Login failed - balance element not found")
            
            # Try to capture error message
            error_selectors = [
                ".alert-danger",
                ".error",
                ".login-error",
                "#login_error",
                "#login_error_msg",
                ".alert",
                "[class*='error']",
            ]
            error_text_norm = ""
            for selector in error_selectors:
                try:
                    error_elem = await self._find_selector_any_frame([selector], "error message", timeout=2000)
                    if error_elem:
                        error_text = await error_elem.text_content()
                        logger.error(f"[FreeBitcoin] Login error message: {error_text}")
                        if error_text:
                            error_text_norm = error_text.casefold()
                        break
                except Exception:
                    continue

            if error_text_norm and any(token in error_text_norm for token in ["captcha", "expired", "try again"]):
                try:
                    logger.info("[FreeBitcoin] Captcha error detected. Attempting re-solve and re-submit...")
                    await self.solver.solve_captcha(self.page)
                    await self.random_delay(1.0, 2.0)
                    submit_btn_retry = await self._find_selector_any_frame(submit_selectors, "submit button", timeout=5000)
                    if submit_btn_retry:
                        await self.human_like_click(submit_btn_retry)
                        await self.random_delay(2.0, 3.0)
                        if await self.is_logged_in():
                            logger.info("✅ [FreeBitcoin] Login successful after captcha retry")
                            return True
                except Exception as retry_err:
                    logger.warning(f"[FreeBitcoin] Captcha retry failed: {retry_err}")
            
            # Take screenshot for debugging
            try:
                await self.page.screenshot(path="logs/freebitcoin_login_failed.png")
                logger.info("[FreeBitcoin] Screenshot saved to logs/freebitcoin_login_failed.png")
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"[FreeBitcoin] Login exception: {e}", exc_info=True)
            try:
                await self.page.screenshot(path="logs/freebitcoin_login_exception.png")
                logger.info("[FreeBitcoin] Exception screenshot saved")
            except Exception:
                pass
            
        return False

    async def claim(self) -> ClaimResult:
        """
        Execute the claim process for FreeBitcoin.
        
        Implements:
        - Retry logic for network failures
                    email_field = await self._find_selector(email_selectors, "email/username field", timeout=8000)
        - Human-like behavior patterns
        - Comprehensive error logging
        
        Returns:
            ClaimResult with success status and next claim time
        """
        logger.info("[DEBUG] FreeBitcoin claim() method started")
        
        max_retries = 3
        nav_timeout = max(getattr(self.settings, "timeout", 60000), 60000)
        for attempt in range(max_retries):
            try:
                logger.info(f"[DEBUG] Attempt {attempt + 1}/{max_retries}: Navigating to {self.base_url}/")
                response = await self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=nav_timeout)
                if response is not None:
                    try:
                        status = response.status
                        if status in (401, 403, 429):
                            from core.orchestrator import ErrorType
                            logger.error(f"[FreeBitcoin] Claim page returned HTTP {status}. URL: {response.url}")
                            return ClaimResult(
                                success=False,
                                status=f"HTTP {status}",
                                next_claim_minutes=30,
                                error_type=ErrorType.PROXY_ISSUE if status == 403 else ErrorType.RATE_LIMIT
                            )
                    except Exception:
                        pass
                await self.handle_cloudflare(max_wait_seconds=60)
                await self.close_popups()
                await self.random_delay(2, 4)

                # Extract Balance with fallback selectors
                logger.info("[DEBUG] Getting balance...")
                balance = await self.get_balance(
                    "#balance",
                    fallback_selectors=["span.balance", ".user-balance", "[data-balance]"]
                )
                logger.info(f"[DEBUG] Balance: {balance}")

                # Check if timer is running (already claimed) with fallback selectors
                logger.info("[DEBUG] Checking timer...")
                wait_min = await self.get_timer(
                    "#time_remaining",
                    fallback_selectors=["span#timer", ".countdown", "[data-next-claim]", ".time-remaining"]
                )
                logger.info(f"[DEBUG] Timer: {wait_min} minutes")
                if wait_min > 0:
                    # Simulate reading page content while timer is active
                    await self.simulate_reading(2.0)
                    return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait_min, balance=balance)

                # Check for Roll Button Presence BEFORE Solving (Save $$)
                # Use multiple selector options for robustness
                roll_btn = self.page.locator(
                    "#free_play_form_button, input#free_play_form_button, input[name='free_play_form_button'], "
                    "button#free_play_form_button, button[id*='play'], .claim-btn, button:has-text('Roll'), "
                    "button:has-text('Play')"
                ).first

                try:
                    await roll_btn.wait_for(state="visible", timeout=8000)
                    roll_visible = True
                except Exception:
                    roll_visible = False

                if roll_visible:
                    if hasattr(roll_btn, "is_enabled") and not await roll_btn.is_enabled():
                        logger.warning("[DEBUG] Roll button is visible but disabled")
                        return ClaimResult(
                            success=False,
                            status="Roll Disabled",
                            next_claim_minutes=15,
                            balance=balance
                        )
                    logger.info("[DEBUG] Roll button found. Initiating Captcha Solve...")

                    # Handle Cloudflare & Captcha
                    logger.debug("[DEBUG] Checking for CloudFlare protection...")
                    cf_result = await self.handle_cloudflare()
                    logger.debug(f"[DEBUG] CloudFlare check result: {cf_result}")

                    # Solve CAPTCHA with error handling
                    logger.debug("[DEBUG] Solving CAPTCHA for claim...")
                    try:
                        await self.solver.solve_captcha(self.page)
                        logger.debug("[DEBUG] CAPTCHA solved successfully")
                    except Exception as captcha_err:
                        logger.error(f"[DEBUG] CAPTCHA solve failed: {captcha_err}")
                        return ClaimResult(
                            success=False,
                            status="CAPTCHA Failed",
                            next_claim_minutes=15,
                            balance=balance
                        )

                    # Double check visibility after potential captcha delay
                    if await roll_btn.is_visible():
                        await self.human_like_click(roll_btn)
                        await self.idle_mouse(1.0)  # Read result naturally
                        await asyncio.sleep(5)
                        await self.close_popups()

                        # Check result with fallback selectors
                        result = self.page.locator(
                            "#winnings, .winning-amount, .result-amount, .btc-won, span:has-text('BTC')"
                        ).first

                        if await result.is_visible():
                            won = await result.text_content()
                            # Use DataExtractor for consistent parsing
                            clean_amount = DataExtractor.extract_balance(won)
                            logger.info(f"FreeBitcoin Claimed! Won: {won} ({clean_amount})")
                            return ClaimResult(
                                success=True,
                                status="Claimed",
                                next_claim_minutes=60,
                                amount=clean_amount,
                                balance=balance
                            )
                    else:
                        logger.warning(
                            f"[DEBUG] Roll button disappeared after captcha solve. "
                            f"Page URL: {self.page.url}, Roll button count: {await self.page.locator('#free_play_form_button').count()}"
                        )
                        return ClaimResult(
                            success=False,
                            status="Roll Button Vanished",
                            next_claim_minutes=15,
                            balance=balance
                        )
                else:
                    logger.warning("Roll button not found (possibly hidden or blocked)")
                    return ClaimResult(
                        success=False,
                        status="Roll Button Not Found",
                        next_claim_minutes=15,
                        balance=balance
                    )

            except asyncio.TimeoutError as e:
                logger.warning(f"FreeBitcoin claim timeout attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5  # Exponential backoff: 5s, 10s, 20s
                    logger.info(f"Retrying in {backoff_time}s...")
                    await asyncio.sleep(backoff_time)
                    continue
                return ClaimResult(
                    success=False,
                    status=f"Timeout after {max_retries} attempts",
                    next_claim_minutes=30
                )

            except Exception as e:
                logger.error(f"FreeBitcoin claim failed attempt {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    backoff_time = (2 ** attempt) * 5
                    logger.info(f"Retrying in {backoff_time}s...")
                    await asyncio.sleep(backoff_time)
                    continue
                return ClaimResult(
                    success=False,
                    status=f"Error: {e}",
                    next_claim_minutes=30
                )
            
        logger.warning(f"FreeBitcoin claim reached unknown failure path. URL: {self.page.url}")
        return ClaimResult(success=False, status="Unknown Failure", next_claim_minutes=15)

    def get_jobs(self):
        """Returns FreeBitcoin-specific jobs for the scheduler."""
        from core.orchestrator import Job
        import time
        
        return [
            Job(
                priority=1,
                next_run=time.time(),
                name=f"{self.faucet_name} Claim",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="claim_wrapper"
            ),
            Job(
                priority=5,
                next_run=time.time() + 86400,  # Check withdrawal daily
                name=f"{self.faucet_name} Withdraw",
                profile=None,
                faucet_type=self.faucet_name.lower(),
                job_type="withdraw_wrapper"
            )
        ]

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for FreeBitcoin.
        
        Supports three modes:
        - Auto Withdraw: Enabled via settings, happens automatically
        - Slow Withdraw: Lower fee (~400 sat), 6-24 hour processing
        - Instant Withdraw: Higher fee, 15 min processing
        
        Minimum: 30,000 satoshis (0.0003 BTC)
        """
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal page...")
            await self.page.goto(f"{self.base_url}/?op=withdraw")
            await self.handle_cloudflare()
            await self.close_popups()
            
            # Get current balance
            balance = await self.get_balance("#balance")
            balance_sat = int(float(balance) * 100000000) if balance else 0
            
            # Check minimum (30,000 satoshis)
            min_withdraw = 30000
            if balance_sat < min_withdraw:
                logger.info(f"[{self.faucet_name}] Balance {balance_sat} sat below minimum {min_withdraw}")
                return ClaimResult(success=True, status="Low Balance", next_claim_minutes=1440)
            
            # Get withdrawal address
            address = self.get_withdrawal_address("BTC")
            if not address:
                logger.error(f"[{self.faucet_name}] No BTC withdrawal address configured")
                return ClaimResult(success=False, status="No Address", next_claim_minutes=1440)
            
            # Fill withdrawal form with human-like typing
            address_field = self.page.locator("input#withdraw_address, input[name='address']")
            amount_field = self.page.locator("input#withdraw_amount, input[name='amount']")
            
            # Use "Slow Withdraw" for lower fees
            slow_radio = self.page.locator("input[value='slow'], #slow_withdraw")
            if await slow_radio.is_visible():
                await self.human_like_click(slow_radio)
                logger.debug(f"[{self.faucet_name}] Selected slow withdrawal for lower fees")
            
            # Click Max/All button if available
            max_btn = self.page.locator("button:has-text('Max'), #max_withdraw")
            if await max_btn.is_visible():
                await self.human_like_click(max_btn)
                logger.debug(f"[{self.faucet_name}] Clicked max withdrawal button")
            elif await amount_field.is_visible():
                await amount_field.fill(str(float(balance)))
                logger.debug(f"[{self.faucet_name}] Filled withdrawal amount: {balance}")
            
            logger.debug(f"[{self.faucet_name}] Filling withdrawal address with human-like typing")
            await self.human_type(address_field, address)
            await self.idle_mouse(1.0)  # Think time before submission
            
            # Handle 2FA if present
            twofa_field = self.page.locator("input#twofa_code, input[name='2fa']")
            if await twofa_field.is_visible():
                logger.warning(f"[{self.faucet_name}] 2FA field detected - manual intervention required")
                return ClaimResult(success=False, status="2FA Required", next_claim_minutes=60)
            
            # Solve captcha
            logger.debug(f"[{self.faucet_name}] Solving CAPTCHA for withdrawal...")
            try:
                await self.solver.solve_captcha(self.page)
                logger.debug(f"[{self.faucet_name}] CAPTCHA solved successfully")
            except Exception as captcha_err:
                logger.error(f"[{self.faucet_name}] Withdrawal CAPTCHA solve failed: {captcha_err}")
                return ClaimResult(success=False, status="CAPTCHA Failed", next_claim_minutes=60)
            
            # Submit
            submit_btn = self.page.locator("button#withdraw_button, button:has-text('Withdraw')")
            await self.human_like_click(submit_btn)
            
            await self.random_delay(3, 5)
            
            # Check result
            success_msg = self.page.locator(".alert-success, #withdraw_success, :has-text('successful')")
            if await success_msg.count() > 0:
                logger.info(f"🚀 [{self.faucet_name}] Withdrawal submitted: {balance} BTC")
                return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)
            
            # Check for error messages
            error_msg = self.page.locator(".alert-danger, .error, #withdraw_error")
            if await error_msg.count() > 0:
                error_text = await error_msg.first.text_content()
                logger.warning(f"[{self.faucet_name}] Withdrawal error: {error_text}")
                return ClaimResult(success=False, status=f"Error: {error_text}", next_claim_minutes=360)
            
            return ClaimResult(success=False, status="Unknown Result", next_claim_minutes=360)
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=60)
