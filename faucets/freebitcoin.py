from .base import FaucetBot, ClaimResult
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

            # Fill Login
            email_field = self.page.locator("input[name='login_email_input']")
            if await email_field.is_visible():
                await self.page.fill("input[name='login_email_input']", creds['username'])
                await self.page.fill("input[name='login_password_input']", creds['password'])
                
                # Check for 2FA or CAPTCHA on login
                if await self.page.locator("#login_2fa_input").is_visible():
                     logger.warning("2FA DETECTED! Use manual mode to enter code.")
                     await self.solver.solve_captcha(self.page) # Waits for manual input

                # Sometimes there is a captcha on login
                await self.solver.solve_captcha(self.page)

                submit = self.page.locator("#login_button")
                await self.human_like_click(submit)
                await self.page.wait_for_url(f"{self.base_url}/", timeout=15000)
            
            # Check if logged in (url is base url, and specific element exists)
            if await self.page.locator("#balance").is_visible():
                logger.info("FreeBitcoin logged in.")
                return True
                
        except Exception as e:
            logger.error(f"FreeBitcoin login failed: {e}")
            
        return False

    async def claim(self) -> ClaimResult:
        try:
            await self.page.goto(f"{self.base_url}/")
            await self.close_popups()
            await self.random_delay(2, 4)

            # Extract Balance
            balance = await self.get_balance("#balance")

            # Check if timer is running (already claimed)
            wait_min = await self.get_timer("#time_remaining")
            if wait_min > 0:
                 return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait_min, balance=balance)

            # Check for CAPTCHA (Turnstile/hCaptcha)
            # wait for Turnstile to finish if it exists (visibility check)
            await self.handle_cloudflare()
            await self.solver.solve_captcha(self.page)
            
            # Click ROLL
            roll_btn = self.page.locator("#free_play_form_button")
            if await roll_btn.is_visible():
                await self.human_like_click(roll_btn)
                await asyncio.sleep(5)
                await self.close_popups()
                
                # Check result
                result = self.page.locator("#winnings")
                if await result.is_visible():
                    won = await result.text_content()
                    logger.info(f"FreeBitcoin Claimed! Won: {won}")
                    return ClaimResult(success=True, status="Claimed", next_claim_minutes=60, amount=str(won), balance=balance)
            else:
                 logger.warning("Roll button not found (or hidden)")
                 return ClaimResult(success=False, status="Roll Button Not Found", next_claim_minutes=15, balance=balance)

        except Exception as e:
            logger.error(f"FreeBitcoin claim failed: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=30)
            
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
            
            # Fill withdrawal form
            address_field = self.page.locator("input#withdraw_address, input[name='address']")
            amount_field = self.page.locator("input#withdraw_amount, input[name='amount']")
            
            # Use "Slow Withdraw" for lower fees
            slow_radio = self.page.locator("input[value='slow'], #slow_withdraw")
            if await slow_radio.is_visible():
                await slow_radio.click()
            
            # Click Max/All button if available
            max_btn = self.page.locator("button:has-text('Max'), #max_withdraw")
            if await max_btn.is_visible():
                await self.human_like_click(max_btn)
            elif await amount_field.is_visible():
                await amount_field.fill(str(float(balance)))
            
            await self.human_type(address_field, address)
            
            # Handle 2FA if present
            twofa_field = self.page.locator("input#twofa_code, input[name='2fa']")
            if await twofa_field.is_visible():
                logger.warning(f"[{self.faucet_name}] 2FA required - manual intervention needed")
                return ClaimResult(success=False, status="2FA Required", next_claim_minutes=60)
            
            # Solve captcha
            await self.solver.solve_captcha(self.page)
            
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
