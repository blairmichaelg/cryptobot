import asyncio
import logging
import time
from playwright.async_api import Page
from faucets.base import FaucetBot, ClaimResult
from core.extractor import DataExtractor

logger = logging.getLogger(__name__)

class PickFaucetBase(FaucetBot):
    """Base class for the '.io pick' faucet family (LitePick, TronPick, etc.).

    These sites share a common structure and logic for login, claiming, and
    withdrawals. Subclasses must define base_url and specific site details.
    """

    def __init__(self, settings, page: Page, action_lock: asyncio.Lock = None):
        """Initialize the PickFaucetBase instance.

        Args:
            settings: Configuration settings object.
            page (Page): Playwright Page instance.
            action_lock (asyncio.Lock, optional): Lock for synchronized browser actions.
        """
        super().__init__(settings, page, action_lock)
        self.faucet_name = "Pick Faucet"
        self.base_url = ""  # To be set by subclass
        self.login_url = ""  # Often same as base_url/login
        self.faucet_url = ""  # Often same as base_url/faucet

    async def _navigate_with_retry(self, url: str, max_retries: int = 3) -> bool:
        """Navigate with exponential backoff retry for connection errors.
        
        Pick family faucets are known to use TLS fingerprinting and aggressive
        anti-bot measures that can result in ERR_CONNECTION_CLOSED. This method
        provides robust retry logic with exponential backoff.
        
        Args:
            url: Target URL to navigate to
            max_retries: Maximum number of retry attempts
            
        Returns:
            True if navigation succeeded, False if all retries exhausted
        """
        # Use longer timeout for Pick.io sites - they're consistently slow
        # Use configured timeout with reasonable minimum for slow Pick.io sites
        nav_timeout = max(getattr(self.settings, "timeout", 60000), 45000)  # At least 45s

        for attempt in range(max_retries):
            try:
                # Try domcontentloaded first (faster), fallback to commit if it fails
                try:
                    response = await self.page.goto(url, timeout=nav_timeout, wait_until="domcontentloaded")
                except Exception:
                    # Fallback to commit for Cloudflare challenges
                    response = await self.page.goto(url, timeout=nav_timeout, wait_until="commit")
                
                if response:
                    # Even 403/503 responses mean we got the page (might be Cloudflare)
                    logger.debug(f"[{self.faucet_name}] Navigation returned status {response.status}")
                    return True
                return True
            except Exception as e:
                error_str = str(e)
                # Check for connection/TLS errors that warrant retry
                if any(err in error_str for err in [
                    "ERR_CONNECTION_CLOSED",
                    "ERR_CONNECTION_RESET", 
                    "net::",
                    "NS_ERROR",
                    "Timeout",
                    "ECONNREFUSED"
                ]):
                    wait_time = (2 ** attempt) * 3  # Faster retry: 3s, 6s, 12s
                    logger.warning(
                        f"[{self.faucet_name}] Connection failed on attempt {attempt+1}/{max_retries}: "
                        f"{error_str[:100]}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    # Non-retryable error
                    logger.error(f"[{self.faucet_name}] Non-retryable navigation error: {e}")
                    return False
        
        logger.error(f"[{self.faucet_name}] All {max_retries} navigation attempts failed for {url}")
        return False

    async def register(self, email: str, password: str, wallet_address: str = None) -> bool:
        """Standard registration for .io pick family.

        Navigates to the registration page, fills the form, solves captchas,
        and verifies successful registration.

        Args:
            email: Email address for registration
            password: Password for the account
            wallet_address: Optional wallet address for withdrawals

        Returns:
            bool: True if registration was successful.
        """
        if not self.base_url:
            logger.error("Base URL not set for PickFaucetBase subclass")
            return False

        register_url = f"{self.base_url}/register.php"
        logger.info(f"[{self.faucet_name}] Registering at {register_url}")
        
        try:
            if not await self._navigate_with_retry(register_url):
                logger.error(f"[{self.faucet_name}] Failed to navigate to registration page")
                return False
            await self.handle_cloudflare()
            await self.close_popups()

            # Fill registration form - using researched selectors
            email_field = self.page.locator('input[type="email"], input[name="email"], input#email')
            pass_field = self.page.locator('input[type="password"], input[name="password"], input#password')
            confirm_pass_field = self.page.locator('input[name="password2"], input[name="confirm_password"], input#password2')
            
            await email_field.fill(email)
            await pass_field.fill(password)
            
            # Fill confirm password if it exists
            if await confirm_pass_field.count() > 0:
                await confirm_pass_field.fill(password)
            
            # Fill wallet address if provided and field exists
            if wallet_address:
                wallet_field = self.page.locator('input[name="address"], input[name="wallet"], input#address')
                if await wallet_field.count() > 0:
                    await wallet_field.fill(wallet_address)
            
            # Check for and solve hCaptcha or Turnstile
            captcha_locator = self.page.locator(".h-captcha, .cf-turnstile")
            if await captcha_locator.count() > 0 and await captcha_locator.first.is_visible():
                logger.info(f"[{self.faucet_name}] Solving registration captcha...")
                await self.solver.solve_captcha(self.page)
                await self.random_delay(2, 5)

            # Find and click register button
            register_btn = self.page.locator('button.btn, button.process_btn, button:has-text("Register"), button:has-text("Sign Up"), button:has-text("Create Account")')
            await self.human_like_click(register_btn)
            
            await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            
            # Check for success indicators
            page_content = await self.page.content()
            success_indicators = [
                "successfully registered",
                "registration successful", 
                "account created",
                "welcome",
                "check your email",
                "verification email"
            ]
            
            if any(indicator in page_content.lower() for indicator in success_indicators):
                logger.info(f"[{self.faucet_name}] Registration successful for {email}")
                return True
            
            # Check if already redirected to dashboard (auto-login after registration)
            if await self.is_logged_in():
                logger.info(f"[{self.faucet_name}] Registration successful, auto-logged in")
                return True
            
            logger.warning(f"[{self.faucet_name}] Registration uncertain - no clear success message")
            return False
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Registration error: {e}")
            return False

    async def login(self) -> bool:
        """Standard login for .io pick family.

        Navigates to the login page, fills credentials, solves any present
        captchas, and verifies the login state.

        Returns:
            bool: True if login was successful and resulted in a logged-in state.
        """
        if not self.base_url:
            logger.error("Base URL not set for PickFaucetBase subclass")
            return False

        login_urls = [
            f"{self.base_url}/login.php",
            f"{self.base_url}/login",
            f"{self.base_url}/?op=login",
            self.base_url,
        ]
        logger.info(f"[{self.faucet_name}] Logging in (candidate URLs: {len(login_urls)})")

        creds = self.get_credentials(self.faucet_name.lower())
        if not creds:
            logger.error(f"[{self.faucet_name}] No credentials found")
            return False

        login_id = creds.get("email") or creds.get("username")
        if not login_id:
            logger.error(f"[{self.faucet_name}] Credentials missing email/username")
            return False
        login_id = self.strip_email_alias(login_id)

        try:
            async def _first_visible(selectors: list[str]):
                for selector in selectors:
                    try:
                        locator = self.page.locator(selector)
                        if await locator.count() > 0:
                            target = locator.first
                            if await target.is_visible():
                                return target
                    except Exception:
                        continue
                return None

            email_selectors = [
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
                '.login-btn',
                '.login-button',
            ]

            email_target = None
            pass_target = None
            for login_url in login_urls:
                logger.info(f"[{self.faucet_name}] Navigating to {login_url}")
                if not await self._navigate_with_retry(login_url):
                    continue
                # Wait up to 30 seconds for Cloudflare challenges (sufficient for most CF)
                await self.handle_cloudflare(max_wait_seconds=30)
                await self.close_popups()

                if await self.is_logged_in():
                    logger.info(f"[{self.faucet_name}] Already logged in")
                    return True

                email_target = await _first_visible(email_selectors)
                pass_target = await _first_visible(password_selectors)
                if not email_target or not pass_target:
                    login_trigger = await _first_visible(login_trigger_selectors)
                    if login_trigger:
                        await self.human_like_click(login_trigger)
                        await self.random_delay(1.0, 2.0)
                        email_target = await _first_visible(email_selectors)
                        pass_target = await _first_visible(password_selectors)

                if email_target and pass_target:
                    break

            if not email_target or not pass_target:
                logger.error(f"[{self.faucet_name}] Login fields not found on page")
                return False

            await self.human_type(email_target, login_id)
            await self.random_delay(0.4, 0.9)
            await self.human_type(pass_target, creds['password'])
            
            # Check for hCaptcha or Turnstile
            captcha_locator = self.page.locator(".h-captcha, .cf-turnstile, .g-recaptcha")
            try:
                captcha_count = await captcha_locator.count()
            except Exception:
                captcha_count = 0
            if not isinstance(captcha_count, int):
                captcha_count = 0
            if captcha_count > 0 and await captcha_locator.first.is_visible():
                logger.info(f"[{self.faucet_name}] Solving login captcha...")
                solved = False
                for attempt in range(3):
                    try:
                        if await self.solver.solve_captcha(self.page):
                            solved = True
                            
                            # Manually enable submit button
                            try:
                                await self.page.evaluate("""
                                    const btns = document.querySelectorAll('button[type="submit"], button.btn, button.process_btn, input[type="submit"]');
                                    btns.forEach(btn => {
                                        if (btn.disabled) {
                                            btn.disabled = false;
                                            btn.removeAttribute('disabled');
                                        }
                                    });
                                """)
                            except Exception:
                                pass
                            
                            break
                        await asyncio.sleep(2)
                    except Exception as captcha_err:
                        logger.warning(f"[{self.faucet_name}] Captcha attempt {attempt + 1} failed: {captcha_err}")
                        await asyncio.sleep(3)
                if not solved:
                    logger.error(f"[{self.faucet_name}] Captcha solve failed on login")
                    return False

            login_btn = self.page.locator(
                'button.btn, button.process_btn, button:has-text("Login"), '
                'button:has-text("Log in"), button[type="submit"], input[type="submit"], '
                '#login_button, .login-btn, .login-button'
            )
            await self.human_like_click(login_btn)

            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass

            failure = await self.check_failure_states()
            if failure:
                logger.error(f"[{self.faucet_name}] Failure state detected after login: {failure}")
                return False

            if await self.is_logged_in():
                logger.info(f"[{self.faucet_name}] Login successful")
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
                    if await err_loc.count() > 0 and await err_loc.first.is_visible():
                        err_text = await err_loc.first.text_content()
                        logger.warning(f"[{self.faucet_name}] Login error: {err_text}")
                        break
                except Exception:
                    continue

            logger.warning(f"[{self.faucet_name}] Login did not result in dashboard")
            return False
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Login error: {e}")
            return False

    async def is_logged_in(self) -> bool:
        """Check if logged in by looking for logout link or balance.

        Returns:
            bool: True if logout link or balance elements are visible.
        """
        try:
            logout = self.page.locator('a:has-text("Logout"), a[href*="logout"]')
            if await logout.count() > 0 and await logout.first.is_visible():
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
                if await self.page.locator(selector).is_visible(timeout=2000):
                    return True
            except Exception:
                continue

        # Fallback on URL hint
        try:
            if any(token in self.page.url.lower() for token in ["dashboard", "account", "profile"]):
                return True
        except Exception:
            pass

        return False

    async def get_balance(self, selector: str = ".balance", fallback_selectors: list | None = None) -> str:
        """Extract balance from the header.

        Returns:
            str: The extracted balance string, or "0" if extraction fails.
        """
        # Researched selectors: .balance, .navbar-right .balance, #balance
        selectors = [selector, ".navbar-right .balance", "#balance"]
        fallback = fallback_selectors or [".balance", ".navbar-right .balance", "#balance"]
        for current_selector in selectors:
            balance = await super().get_balance(current_selector, fallback_selectors=fallback)
            if balance and balance != "0":
                return balance
        return "0"

    def get_jobs(self):
        """Standard job definition for the pick family.

        Returns:
            list[Job]: A list of Job objects for the scheduler.
        """
        from core.orchestrator import Job
        
        f_type = self.faucet_name.lower()
        
        return [
            Job(
                priority=2, # Higher than PTC/Shortlinks, lower than main faucets like Dutchy
                next_run=time.time(),
                name=f"{self.faucet_name} Claim",
                profile=None,
                faucet_type=f_type,
                job_type="claim_wrapper"
            ),
            Job(
                priority=5,
                next_run=time.time() + 3600,
                name=f"{self.faucet_name} Withdraw",
                profile=None,
                faucet_type=f_type,
                job_type="withdraw_wrapper"
            )
        ]

    async def claim(self) -> ClaimResult:
        """Perform the hourly faucet claim.

        Handles navigation, cooldown checks, captcha solving, and clicking the
        claim button.

        Returns:
            ClaimResult: The result of the claim attempt.
        """
        faucet_url = f"{self.base_url}/faucet.php"
        logger.info(f"[{self.faucet_name}] Navigating to faucet: {faucet_url}")
        
        if not await self._navigate_with_retry(faucet_url):
            logger.error(f"[{self.faucet_name}] Failed to navigate to faucet page")
            return ClaimResult(success=False, status="Connection Failed", next_claim_minutes=15)
        await self.handle_cloudflare()
        await self.close_popups()

        # Check for existing timer
        timer_text = None
        try:
            timer_loc = self.page.locator("#time")
            if await timer_loc.count() > 0:
                timer_text = await timer_loc.first.text_content()
        except Exception:
            timer_text = None

        if not timer_text:
            try:
                auto_sel = await DataExtractor.find_timer_selector_in_dom(self.page)
                if auto_sel:
                    auto_loc = self.page.locator(auto_sel)
                    if await auto_loc.count() > 0:
                        timer_text = await auto_loc.first.text_content()
            except Exception:
                timer_text = None

        if timer_text and any(c.isdigit() for c in timer_text):
            minutes = DataExtractor.parse_timer_to_minutes(timer_text)
            if minutes > 0:
                logger.info(f"[{self.faucet_name}] Faucet on cooldown: {minutes}m remaining")
                return ClaimResult(success=True, status="Cooldown", next_claim_minutes=minutes, balance=await self.get_balance())

        try:
            # Check for hCaptcha or Turnstile in the faucet page
            captcha_loc = self.page.locator(".h-captcha, .cf-turnstile, .g-recaptcha")
            try:
                captcha_count = await captcha_loc.count()
            except Exception:
                captcha_count = 0
            if captcha_count > 0 and await captcha_loc.first.is_visible():
                logger.info(f"[{self.faucet_name}] Solving faucet captcha...")
                solved = False
                for attempt in range(3):
                    try:
                        if await self.solver.solve_captcha(self.page):
                            solved = True
                            
                            # Manually enable submit button
                            try:
                                await self.page.evaluate("""
                                    const btns = document.querySelectorAll('button[type="submit"], button.btn-primary, button#claim, button.btn');
                                    btns.forEach(btn => {
                                        if (btn.disabled) {
                                            btn.disabled = false;
                                            btn.removeAttribute('disabled');
                                        }
                                    });
                                """)
                            except Exception:
                                pass
                            
                            break
                        await asyncio.sleep(2)
                    except Exception as captcha_err:
                        logger.warning(f"[{self.faucet_name}] Captcha attempt {attempt + 1} failed: {captcha_err}")
                        await asyncio.sleep(3)
                if not solved:
                    return ClaimResult(success=False, status="CAPTCHA Failed", next_claim_minutes=10)

                await self.random_delay(2, 5)

            # The button is often 'Claim' or 'Roll' or has class 'btn-primary'
            claim_btn = self.page.locator('button.btn-primary, button:has-text("Claim"), button:has-text("Roll"), button#claim')
            
            if not await claim_btn.is_visible():
                logger.warning(f"[{self.faucet_name}] Claim button not found, checking if already claimed")
                return ClaimResult(success=True, status="Already Claimed", next_claim_minutes=60, balance=await self.get_balance())

            await self.human_like_click(claim_btn)
            await self.random_delay(3, 6)

            # Extract result from alert or specific message div
            result_msg_loc = self.page.locator(".alert-success, #success, .message")
            if await result_msg_loc.count() > 0:
                result_msg = await result_msg_loc.first.text_content()
                logger.info(f"[{self.faucet_name}] Claim successful: {result_msg.strip()}")
                return ClaimResult(
                    success=True, 
                    status="Claimed", 
                    next_claim_minutes=60, 
                    amount=result_msg.strip(), 
                    balance=await self.get_balance()
                )
            
            return ClaimResult(success=False, status="Claim failed or result not found", next_claim_minutes=10)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=15)

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for .io pick family.

        Checks balance against minimum withdrawal thresholds, fills the
        withdrawal form, solves any required captchas, and submits the request.

        Returns:
            ClaimResult: The result of the withdrawal attempt.
        """
        withdraw_url = f"{self.base_url}/withdraw.php"
        logger.info(f"[{self.faucet_name}] Navigating to withdrawal: {withdraw_url}")
        
        if not await self._navigate_with_retry(withdraw_url):
            logger.error(f"[{self.faucet_name}] Failed to navigate to withdrawal page")
            return ClaimResult(success=False, status="Connection Failed", next_claim_minutes=60)
        await self.handle_cloudflare()
        
        # Check balance against min_withdraw thresholds
        coin = self.faucet_name.replace("Pick", "").upper()
        if coin == "LITE":
            coin = "LTC"
        if coin == "TRON":
            coin = "TRX"
        if coin == "USD":
            coin = "USDT"
        
        balance_str = await self.get_balance()
        balance_clean = DataExtractor.extract_balance(balance_str)
        try:
            balance = float(balance_clean) if balance_clean else 0.0
        except Exception:
            logger.error(f"[{self.faucet_name}] Could not parse balance '{balance_str}'")
            balance = 0.0

        # Pull min_withdraw from settings (thresholds are stored in smallest units)
        min_withdraw = 0.0
        try:
            from core.analytics import CryptoPriceFeed
            decimals = CryptoPriceFeed.CURRENCY_DECIMALS.get(coin, 8)
            threshold = self.settings.withdrawal_thresholds.get(coin, {}) if hasattr(self.settings, "withdrawal_thresholds") else {}
            if isinstance(threshold, dict) and threshold.get("min") is not None:
                min_withdraw = float(threshold.get("min")) / (10 ** decimals)
        except Exception:
            min_withdraw = 0.0

        # Allow wallet_addresses dict to override min_withdraw if explicitly provided
        wallet_info = self.settings.wallet_addresses.get(coin) if hasattr(self.settings, "wallet_addresses") else None
        if isinstance(wallet_info, dict) and wallet_info.get('min_withdraw') is not None:
            try:
                min_withdraw = float(wallet_info.get('min_withdraw'))
            except Exception:
                pass
        
        if balance < min_withdraw:
            logger.info(f"[{self.faucet_name}] Balance {balance} {coin} below minimum {min_withdraw}. Skipping.")
            return ClaimResult(success=True, status="Low Balance", next_claim_minutes=1440)

        # Fill withdrawal form
        try:
            address_field = self.page.locator('input[name="address"], #address')
            amount_field = self.page.locator('input[name="amount"], #amount')
            
            # Use 'withdraw all' button if exists
            all_btn = self.page.locator('button:has-text("Withdraw all"), #withdraw-all')
            if await all_btn.is_visible():
                await self.human_like_click(all_btn)
            else:
                await amount_field.fill(str(balance))

            # Ensure address is set
            withdraw_address = self.get_withdrawal_address(coin)
            if not withdraw_address:
                logger.error(f"[{self.faucet_name}] No withdrawal address configured for {coin}")
                return ClaimResult(success=False, status="No Address", next_claim_minutes=1440)

            if await address_field.count() == 0:
                logger.error(f"[{self.faucet_name}] Withdrawal address field not found")
                return ClaimResult(success=False, status="No Address Field", next_claim_minutes=1440)
            
            await address_field.fill(withdraw_address)
            
            # Solve Captcha
            await self.solver.solve_captcha(self.page)
            
            withdraw_btn = self.page.locator('button:has-text("Withdraw"), button.process_btn')
            await self.human_like_click(withdraw_btn)
            
            await self.random_delay(3, 8)
            
            # Verify Success
            if "success" in (await self.page.content()).lower():
                logger.info(f"🚀 [{self.faucet_name}] Withdrawal processed for {balance} {coin}!")
                return ClaimResult(success=True, status="Withdrawn", next_claim_minutes=1440)
            
            return ClaimResult(success=False, status="Withdrawal Failed or pending", next_claim_minutes=360)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal error: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=720)
