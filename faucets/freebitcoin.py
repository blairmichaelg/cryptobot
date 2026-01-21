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
        return await self.page.locator("#balance").is_visible()

    async def login(self) -> bool:
        # Check for override (Multi-Account Loop)
        if hasattr(self, 'settings_account_override') and self.settings_account_override:
            creds = self.settings_account_override
        else:
            creds = self.settings.get_account("freebitcoin")
            
        if not creds: 
            logger.error("FreeBitcoin credentials missing")
            return False

        try:
            await self.page.goto(f"{self.base_url}/login")
            await self.random_delay()
            
            # Close cookie banner if present
            await self.close_popups()

            # Fill Login with human-like typing
            email_field = self.page.locator("input[name='login_email_input']")
            if await email_field.is_visible():
                logger.debug("[FreeBitcoin] Filling login credentials with human-like typing")
                await self.human_type("input[name='login_email_input']", creds['username'])
                await self.random_delay(0.5, 1.5)
                await self.human_type("input[name='login_password_input']", creds['password'])
                await self.idle_mouse(1.0)  # Simulate thinking time before submission
                
                # Check for 2FA or CAPTCHA on login
                if await self.page.locator("#login_2fa_input").is_visible():
                     logger.warning("2FA DETECTED! Use manual mode to enter code.")
                     await self.solver.solve_captcha(self.page) # Waits for manual input

                # Sometimes there is a captcha on login
                logger.debug("[FreeBitcoin] Checking for login CAPTCHA")
                try:
                    await self.solver.solve_captcha(self.page)
                except Exception as captcha_err:
                    logger.warning(f"[FreeBitcoin] Login CAPTCHA solve failed: {captcha_err}")
                    # Continue anyway, might not need CAPTCHA

                submit = self.page.locator("#login_button")
                await self.human_like_click(submit)
                
                logger.debug("[FreeBitcoin] Waiting for login redirect...")
                try:
                    await self.page.wait_for_url(f"{self.base_url}/", timeout=60000)
                except asyncio.TimeoutError:
                    logger.warning("[FreeBitcoin] Login redirect timeout, checking if already logged in...")
                    # Continue to check login status anyway
            
            # Check if logged in (url is base url, and specific element exists)
            if await self.page.locator("#balance").is_visible():
                logger.info("FreeBitcoin logged in.")
                return True
                
        except Exception as e:
            logger.error(f"FreeBitcoin login failed: {e}")
            
        return False

    async def claim(self) -> ClaimResult:
        """
        Execute the claim process for FreeBitcoin.
        
        Implements:
        - Retry logic for network failures
        - Fallback selectors for robustness
        - Human-like behavior patterns
        - Comprehensive error logging
        
        Returns:
            ClaimResult with success status and next claim time
        """
        logger.info(f"[DEBUG] FreeBitcoin claim() method started")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"[DEBUG] Attempt {attempt + 1}/{max_retries}: Navigating to {self.base_url}/")
                await self.page.goto(f"{self.base_url}/")
                await self.close_popups()
                await self.random_delay(2, 4)

                # Extract Balance with fallback selectors
                logger.info(f"[DEBUG] Getting balance...")
                balance = await self.get_balance(
                    "#balance", 
                    fallback_selectors=["span.balance", ".user-balance", "[data-balance]"]
                )
                logger.info(f"[DEBUG] Balance: {balance}")

                # Check if timer is running (already claimed) with fallback selectors
                logger.info(f"[DEBUG] Checking timer...")
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
                    "#free_play_form_button, button[id*='play'], .claim-btn, button:has-text('Roll')"
                ).first
                
                if await roll_btn.is_visible():
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
                        logger.warning(f"[DEBUG] Roll button disappeared after captcha solve. "
                                     f"Page URL: {self.page.url}, Roll button count: {await self.page.locator('#free_play_form_button').count()}")
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
