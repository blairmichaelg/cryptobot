"""
BinPick Bot - Binance Coin faucet from the Pick.io family.

Inherits login from PickFaucetBase and implements BNB-specific claim logic.
"""
import asyncio
import logging
from typing import Optional
from playwright.async_api import Page
from faucets.pick_base import PickFaucetBase
from faucets.base import ClaimResult
from core.extractor import DataExtractor

logger = logging.getLogger(__name__)

class BinPickBot(PickFaucetBase):
    """BinPick faucet bot with Pick family login."""
    
    def __init__(self, settings, page: Page, action_lock: Optional[asyncio.Lock] = None):
        """Initialize BinPickBot.
        
        Args:
            settings: BotSettings configuration object
            page: Playwright Page instance
            action_lock: Optional lock for synchronized browser actions
        """
        super().__init__(settings, page, action_lock)
        self.faucet_name = "BinPick"
        self.base_url = "https://binpick.io"
        self.min_claim_amount = 0.001
        self.claim_interval_minutes = 60
        
        logger.info(f"[{self.faucet_name}] Initialized with base URL: {self.base_url}")
    
    async def get_balance(self, selector: str = ".balance", fallback_selectors: list = None) -> str:
        """Extract BNB balance from the page.
        
        Returns:
            str: Balance string (e.g., "0.125") or "0" on failure
        """
        try:
            selectors = [selector] + (fallback_selectors or [
                ".balance",
                ".navbar-right .balance",
                "#balance",
                "span.balance",
                "[data-balance]",
            ])
            
            for sel in selectors:
                try:
                    element = self.page.locator(sel)
                    if await element.count() > 0 and await element.first.is_visible():
                        balance_text = await element.first.text_content()
                        if balance_text:
                            balance = DataExtractor.extract_balance(balance_text)
                            if balance and balance != "0":
                                logger.debug(f"[{self.faucet_name}] Balance extracted: {balance} BNB")
                                return balance
                except Exception as e:
                    logger.debug(f"[{self.faucet_name}] Selector {sel} failed: {e}")
                    continue
            
            logger.warning(f"[{self.faucet_name}] Could not extract balance from any selector")
            return "0"
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Balance extraction error: {e}")
            return "0"
    
    async def get_timer(self, selector: str = "#time", fallback_selectors: list = None) -> float:
        """Extract claim timer and convert to minutes.
        
        Returns:
            float: Remaining time in minutes, or 0.0 if ready to claim
        """
        try:
            selectors = [selector] + (fallback_selectors or [
                "#time",
                ".timer",
                "[data-timer]",
                "#claim_timer",
            ])
            
            for sel in selectors:
                try:
                    element = self.page.locator(sel)
                    if await element.count() > 0:
                        timer_text = await element.first.text_content()
                        if timer_text and any(c.isdigit() for c in timer_text):
                            minutes = DataExtractor.parse_timer_to_minutes(timer_text)
                            if minutes > 0:
                                logger.debug(f"[{self.faucet_name}] Timer: {timer_text} -> {minutes:.2f} min")
                                return minutes
                except Exception as e:
                    logger.debug(f"[{self.faucet_name}] Timer selector {sel} failed: {e}")
                    continue
            
            logger.debug(f"[{self.faucet_name}] No active timer found - ready to claim")
            return 0.0
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Timer extraction error: {e}")
            return 0.0
    
    async def claim(self) -> ClaimResult:
        """Perform BNB claim with stealth and error handling.
        
        Returns:
            ClaimResult: Claim outcome with success status, message, and next_claim_minutes
        """
        logger.info(f"[{self.faucet_name}] Starting claim process")
        
        faucet_url = f"{self.base_url}/faucet.php"
        
        if not await self._navigate_with_retry(faucet_url):
            logger.error(f"[{self.faucet_name}] Failed to navigate to faucet page after retries")
            return ClaimResult(
                success=False, 
                status="Navigation Failed", 
                next_claim_minutes=15,
                balance=await self.get_balance()
            )
        
        await self.idle_mouse(duration=2.0)
        await self.random_delay(1, 3)
        
        try:
            await self.handle_cloudflare()
            await self.close_popups()
            
            current_balance = await self.get_balance()
            logger.info(f"[{self.faucet_name}] Current balance: {current_balance} BNB")
            
            timer_minutes = await self.get_timer()
            if timer_minutes > 0:
                logger.info(f"[{self.faucet_name}] Faucet on cooldown: {timer_minutes:.2f} min remaining")
                return ClaimResult(
                    success=True, 
                    status="Cooldown", 
                    next_claim_minutes=timer_minutes,
                    balance=current_balance
                )
            
            captcha_locator = self.page.locator(".h-captcha, .cf-turnstile, .g-recaptcha")
            captcha_count = await captcha_locator.count()
            captcha_present = captcha_count > 0
            if captcha_present:
                logger.info(f"[{self.faucet_name}] CAPTCHA detected, solving...")
                await self.idle_mouse(duration=1.5)
                
                captcha_solved = False
                for attempt in range(3):
                    try:
                        if await self.solver.solve_captcha(self.page):
                            captcha_solved = True
                            logger.info(f"[{self.faucet_name}] CAPTCHA solved on attempt {attempt + 1}")
                            break
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.warning(f"[{self.faucet_name}] CAPTCHA attempt {attempt + 1} failed: {e}")
                        await asyncio.sleep(3)
                
                if not captcha_solved:
                    logger.error(f"[{self.faucet_name}] CAPTCHA solving failed after 3 attempts")
                    return ClaimResult(
                        success=False,
                        status="CAPTCHA Failed",
                        next_claim_minutes=10,
                        balance=current_balance
                    )
                
                await self.random_delay(2, 4)
            
            claim_btn = self.page.locator(
                'button.btn-primary, button:has-text("Claim"), '
                'button:has-text("Roll"), button#claim, button.process_btn'
            )
            
            if not await claim_btn.is_visible():
                logger.warning(f"[{self.faucet_name}] Claim button not visible")
                return ClaimResult(
                    success=False,
                    status="Button Not Found",
                    next_claim_minutes=self.claim_interval_minutes,
                    balance=current_balance
                )
            
            logger.info(f"[{self.faucet_name}] Clicking claim button")
            await self.human_like_click(claim_btn)
            
            await self.random_delay(3, 6)
            await self.page.wait_for_load_state("networkidle", timeout=15000)
            
            result_selectors = [
                ".alert-success", 
                "#success", 
                ".message", 
                ".success-message",
                "[class*='success']"
            ]
            
            for selector in result_selectors:
                result_loc = self.page.locator(selector)
                if await result_loc.count() > 0:
                    result_msg = await result_loc.first.text_content()
                    if result_msg:
                        result_msg = result_msg.strip()
                        logger.info(f"[{self.faucet_name}] ✅ Claim successful: {result_msg}")
                        
                        new_balance = await self.get_balance()
                        
                        return ClaimResult(
                            success=True,
                            status="Claimed",
                            next_claim_minutes=self.claim_interval_minutes,
                            amount=result_msg,
                            balance=new_balance
                        )
            
            error_selectors = [".alert-danger", ".error", "[class*='error']"]
            for selector in error_selectors:
                error_loc = self.page.locator(selector)
                if await error_loc.count() > 0:
                    error_msg = await error_loc.first.text_content()
                    if error_msg:
                        logger.warning(f"[{self.faucet_name}] Claim error: {error_msg.strip()}")
                        return ClaimResult(
                            success=False,
                            status=f"Error: {error_msg.strip()}",
                            next_claim_minutes=self.claim_interval_minutes,
                            balance=current_balance
                        )
            
            logger.warning(f"[{self.faucet_name}] Claim completed but no result message found")
            return ClaimResult(
                success=False,
                status="Unknown Result",
                next_claim_minutes=10,
                balance=current_balance
            )
            
        except Exception as e:
            logger.error(f"[{self.faucet_name}] Claim error: {e}", exc_info=True)
            return ClaimResult(
                success=False,
                status=f"Exception: {str(e)[:100]}",
                next_claim_minutes=15,
                balance=await self.get_balance()
            )
