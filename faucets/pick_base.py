import asyncio
import logging
import time
from typing import Optional, Union
from playwright.async_api import Page, Locator
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
        for attempt in range(max_retries):
            try:
                response = await self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
                if response and response.ok:
                    return True
                # Even if response isn't perfect, page may have loaded
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
                    wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s
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
            
            await self.page.wait_for_load_state("networkidle", timeout=30000)
            
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
        captchas, and verifies the login state with enhanced stealth.

        Returns:
            bool: True if login was successful and resulted in a logged-in state.
        """
        if not self.base_url:
            logger.error("Base URL not set for PickFaucetBase subclass")
            return False

        login_url = f"{self.base_url}/login.php"
        logger.info(f"[{self.faucet_name}] Logging in at {login_url}")
        
        if not await self._navigate_with_retry(login_url):
            logger.error(f"[{self.faucet_name}] Failed to navigate to login page")
            return False
        await self.handle_cloudflare()
        await self.close_popups()

        creds = self.get_credentials(self.faucet_name.lower())
        if not creds:
            logger.error(f"[{self.faucet_name}] No credentials found")
            return False

        try:
            # Fill credentials - Using researched selectors
            email_field = self.page.locator('input[type="email"], input[name="email"], input#email')
            pass_field = self.page.locator('input[type="password"], input[name="password"], input#password')
            
            # Stealth: Human-like typing instead of instant fill
            if await email_field.is_visible():
                logger.debug(f"[{self.faucet_name}] Filling email field")
                await self.human_type(email_field, creds['email'])
            else:
                logger.warning(f"[{self.faucet_name}] Email field not visible")
                return False
                
            await self.random_delay(0.5, 1.5)
            
            if await pass_field.is_visible():
                logger.debug(f"[{self.faucet_name}] Filling password field")
                await self.human_type(pass_field, creds['password'])
            else:
                logger.warning(f"[{self.faucet_name}] Password field not visible")
                return False
            
            # Check for hCaptcha or Turnstile
            captcha_locator = self.page.locator(".h-captcha, .cf-turnstile, .g-recaptcha")
            if await captcha_locator.count() > 0 and await captcha_locator.first.is_visible():
                logger.info(f"[{self.faucet_name}] Solving login captcha...")
                captcha_solved = await self.solver.solve_captcha(self.page)
                if not captcha_solved:
                    logger.warning(f"[{self.faucet_name}] Login CAPTCHA solving failed")
                    return False
                await self.random_delay(2, 4)

            login_btn = self.page.locator('button.btn, button.process_btn, button:has-text("Login"), button:has-text("Log in")')
            
            if not await login_btn.is_visible():
                logger.error(f"[{self.faucet_name}] Login button not found")
                return False
                
            logger.debug(f"[{self.faucet_name}] Clicking login button")
            await self.random_delay(0.5, 1.5)
            await self.human_like_click(login_btn)
            
            await self.page.wait_for_load_state("networkidle", timeout=30000)
            
            # Verify login state
            if await self.is_logged_in():
                logger.info(f"[{self.faucet_name}] Login successful")
                return True
            else:
                logger.warning(f"[{self.faucet_name}] Login did not result in logged-in state")
                
                # Check for error messages
                error_loc = self.page.locator(".alert-danger, .alert-error, .error")
                if await error_loc.count() > 0:
                    error_text = await error_loc.first.text_content()
                    logger.error(f"[{self.faucet_name}] Login error: {error_text}")
                
                return False
                
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Login error: {e}", exc_info=True)
            return False

    async def is_logged_in(self) -> bool:
        """Check if logged in by looking for logout link or balance.

        Returns:
            bool: True if logout link or balance elements are visible.
        """
        return await self.page.locator('a:has-text("Logout"), a[href*="logout"]').is_visible()

    async def get_balance(self) -> str:
        """Extract balance from the header with enhanced fallback logic.

        Returns:
            str: The extracted balance string, or "0" if extraction fails.
        """
        # Multiple selector strategies for robustness
        balance_selectors = [
            ".balance",
            ".navbar-right .balance", 
            "#balance",
            "[class*='balance']",
            ".user-balance",
            "#user-balance"
        ]
        
        balance = await super().get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
        logger.debug(f"[{self.faucet_name}] Balance extracted: {balance}")
        return balance if balance and balance != "0" else "0"

    def get_jobs(self):
        """Standard job definition for the pick family.

        Returns:
            list[Job]: A list of Job objects for the scheduler.
        """
        from core.orchestrator import Job
        import time
        
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
        claim button with enhanced stealth and robustness.

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
        
        # Stealth: Simulate reading page before interacting
        await self.idle_mouse(duration=2.0)

        # Check for existing timer with fallback selectors
        timer_minutes = await self.get_timer("#time", fallback_selectors=["#timer", ".timer", "[id*='countdown']"])
        if timer_minutes > 0:
            logger.info(f"[{self.faucet_name}] Faucet on cooldown: {timer_minutes:.2f}m remaining")
            balance = await self.get_balance()
            return ClaimResult(success=True, status="Cooldown", next_claim_minutes=timer_minutes, balance=balance)

        try:
            # Check for and actively solve CAPTCHA
            captcha_locator = self.page.locator(".h-captcha, .cf-turnstile, .g-recaptcha")
            if await captcha_locator.count() > 0 and await captcha_locator.first.is_visible():
                logger.info(f"[{self.faucet_name}] CAPTCHA detected, solving...")
                captcha_solved = await self.solver.solve_captcha(self.page)
                if not captcha_solved:
                    logger.warning(f"[{self.faucet_name}] CAPTCHA solving failed")
                    return ClaimResult(success=False, status="CAPTCHA Failed", next_claim_minutes=5)
                logger.info(f"[{self.faucet_name}] CAPTCHA solved successfully")
                await self.random_delay(2, 4)

            # The button is often 'Claim' or 'Roll' or has class 'btn-primary'
            claim_btn = self.page.locator('button.btn-primary, button:has-text("Claim"), button:has-text("Roll"), button#claim')
            
            if not await claim_btn.is_visible():
                logger.warning(f"[{self.faucet_name}] Claim button not found, checking if already claimed")
                balance = await self.get_balance()
                return ClaimResult(success=True, status="Already Claimed", next_claim_minutes=60, balance=balance)

            # Stealth: Natural delay before clicking
            await self.random_delay(1, 3)
            await self.human_like_click(claim_btn)
            await self.random_delay(3, 6)

            # Extract result from alert or specific message div
            result_msg_loc = self.page.locator(".alert-success, #success, .message, .alert")
            if await result_msg_loc.count() > 0:
                result_msg = await result_msg_loc.first.text_content()
                logger.info(f"[{self.faucet_name}] Claim successful: {result_msg.strip()}")
                
                # Extract actual claim amount if present
                amount_extracted = DataExtractor.extract_balance(result_msg)
                balance = await self.get_balance()
                
                return ClaimResult(
                    success=True, 
                    status="Claimed", 
                    next_claim_minutes=60,  # Standard hourly claim
                    amount=amount_extracted if amount_extracted != "0" else result_msg.strip(), 
                    balance=balance
                )
            
            # Check for error messages
            error_msg_loc = self.page.locator(".alert-danger, .alert-error, .error")
            if await error_msg_loc.count() > 0:
                error_text = await error_msg_loc.first.text_content()
                logger.warning(f"[{self.faucet_name}] Claim error message: {error_text}")
                return ClaimResult(success=False, status=f"Error: {error_text}", next_claim_minutes=10)
            
            logger.warning(f"[{self.faucet_name}] Claim result not found, assuming success")
            balance = await self.get_balance()
            return ClaimResult(success=True, status="Claimed (unverified)", next_claim_minutes=60, balance=balance)

        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim error: {e}", exc_info=True)
            return ClaimResult(success=False, status=f"Error: {str(e)[:100]}", next_claim_minutes=15)

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
        
        # Check balance against min_withdraw if specified in wallet_addresses
        coin = self.faucet_name.replace("Pick", "").upper()
        if coin == "LITE": coin = "LTC"
        if coin == "TRON": coin = "TRX"
        
        balance_str = await self.get_balance()
        balance = float(balance_str)
        
        # Pull min_withdraw from settings if available
        wallet_info = self.settings.wallet_addresses.get(coin)
        min_withdraw = 0.005 # Default for LTC/TRX family usually
        if isinstance(wallet_info, dict):
             min_withdraw = wallet_info.get('min_withdraw', min_withdraw)
        
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
            saved_address = wallet_info['address'] if isinstance(wallet_info, dict) else None
            if not saved_address:
                logger.error(f"[{self.faucet_name}] No withdrawal address configured for {coin}")
                return ClaimResult(success=False, status="No Address", next_claim_minutes=1440)
            
            await address_field.fill(saved_address)
            
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
