from .base import FaucetBot, ClaimResult
import logging
import asyncio
import time
from typing import List

logger = logging.getLogger(__name__)

class PickFaucetBot(FaucetBot):
    """
    Standard implementation for the 'Pick' family of faucets
    (LitePick, TronPick, DogePick, etc.)
    """
    def __init__(self, settings, page, site_name, site_url, **kwargs):
        super().__init__(settings, page, **kwargs)
        self.faucet_name = site_name
        self.base_url = site_url
        self.coin = site_name.replace("Pick", "").upper()

    async def is_logged_in(self) -> bool:
        # Use locator for consistency with tests and modern Playwright
        return await self.page.locator("a[href*='logout'], a[href*='dashboard']").count() > 0

    async def login(self) -> bool:
        creds = self.get_credentials(self.faucet_name.lower())
        if not creds:
            return False

        try:
            logger.info(f"[{self.faucet_name}] Navigating to login...")
            await self.page.goto(f"{self.base_url}/login")
            
            # Check if already logged in via cookies
            if await self.is_logged_in():
                logger.info(f"[{self.faucet_name}] Successfully logged in via cookies.")
                return True

            await self.page.fill('input[name="email"], input[name="username"]', creds['username'])
            await self.page.fill('input[name="password"]', creds['password'])
            
            await self.solver.solve_captcha(self.page)
            
            submit = self.page.locator('button[type="submit"], #login_btn')
            await self.human_like_click(submit)
            
            await self.page.wait_for_load_state()
            if await self.is_logged_in():
                 logger.info(f"[{self.faucet_name}] Login Successful.")
                 return True
            return False
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Login failed: {e}")
            return False

    async def claim(self) -> ClaimResult:
        try:
            await self.page.goto(f"{self.base_url}/faucet")
            await self.close_popups()
            
            # Check for timer
            wait_min = await self.get_timer("#timer, .count_down_timer")
            if wait_min > 0:
                return ClaimResult(success=True, status="Timer Active", next_claim_minutes=wait_min)

            # Solve Captcha
            await self.solver.solve_captcha(self.page)
            
            # Claim Button
            claim_btn = self.page.locator("button:has-text('Claim'), #claim_btn, .claim-button")
            if await claim_btn.count() > 0:
                await self.human_like_click(claim_btn.first)
                await asyncio.sleep(3)
                
                # Check for success message
                success_msg_loc = self.page.locator(".alert-success, .success-message")
                amount = "0"
                if await success_msg_loc.count() > 0:
                    text = await success_msg_loc.first.text_content()
                    amount = text.strip()
                
                # Extract balance
                balance = await self.get_balance(".user-balance, #balance")
                return ClaimResult(success=True, status="Claimed", next_claim_minutes=60, balance=balance, amount=amount)
            
            return ClaimResult(success=False, status="Claim Button not found", next_claim_minutes=5)
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim failed: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=15)

    async def withdraw(self) -> ClaimResult:
        """Automated withdrawal for Pick family."""
        try:
            logger.info(f"[{self.faucet_name}] Navigating to withdrawal...")
            await self.page.goto(f"{self.base_url}/withdraw")
            
            # Fill address if not already there
            address_input = self.page.locator("input[name='address'], #withdraw_address")
            wallet = self.settings.wallet_addresses.get(self.coin, {})
            if await address_input.count() > 0 and wallet.get('address'):
                val = await address_input.get_attribute("value")
                if not val or len(val) < 5:
                    await self.page.fill(address_input, wallet['address'])
            
            # Amount - withdrawal all
            amount_input = self.page.locator("input[name='amount'], #withdraw_amount")
            if await amount_input.count() > 0:
                 # Often there is a 'Max' button or similar
                 max_btn = self.page.locator("button:has-text('Max'), .max-button")
                 if await max_btn.count() > 0:
                     await max_btn.click()
                 else:
                     # Fallback to extracting balance and filling
                     balance = await self.get_balance(".user-balance, #balance")
                     await self.page.fill(amount_input, balance)
            
            await self.solver.solve_captcha(self.page)
            
            submit = self.page.locator("button:has-text('Withdraw')").last
            await self.human_like_click(submit)
            
            return ClaimResult(success=True, status="Withdrawal Submitted", next_claim_minutes=1440)
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Withdrawal failed: {e}")
            return ClaimResult(success=False, status=f"Error: {e}", next_claim_minutes=1440)

def get_pick_faucets(settings, page) -> List[PickFaucetBot]:
    """Factory to create all Pick faucets."""
    sites = [
        ("LitePick", "https://litepick.io"),
        ("TronPick", "https://tronpick.io"),
        ("DogePick", "https://dogepick.io"),
        ("SolPick", "https://solpick.io"),
        ("BinPick", "https://binpick.io"),
        ("BchPick", "https://bchpick.io"),
        ("TonPick", "https://tonpick.io"),
        ("PolygonPick", "https://polygonpick.io"),
        ("DashPick", "https://dashpick.io"),
        ("EthPick", "https://ethpick.io"),
        ("UsdPick", "https://usdpick.io"),
    ]
    return [PickFaucetBot(settings, page, name, url) for name, url in sites]
