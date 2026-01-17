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
