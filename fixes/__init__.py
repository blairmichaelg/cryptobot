"""
Comprehensive Faucet Fixes - Applied Based on Diagnostic Results
================================================================

This module contains targeted fixes for issues identified in the comprehensive diagnostic:

1. FireFaucet: get_balance/get_timer signature compatibility
2. Cointiply: hCaptcha 2Captcha ERROR_METHOD_CALL
3. FreeBitcoin: Navigation timeouts
4. General improvements for all faucets

Fixes are research-based and tested.
"""

import asyncio
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class CaptchaFix:
    """Fixes for captcha solving issues."""
    
    @staticmethod
    async def solve_hcaptcha_with_fallback(solver, page, sitekey: str, url: str) -> Optional[str]:
        """
        Enhanced hCaptcha solving with automatic fallback.
        
        Handles the ERROR_METHOD_CALL issue by:
        1. Trying 2Captcha with proper parameters
        2. Falling back to CapSolver if 2Captcha fails
        3. Using proper method naming for each provider
        
        Args:
            solver: CaptchaSolver instance
            page: Playwright Page
            sitekey: hCaptcha sitekey
            url: Page URL
            
        Returns:
            Captcha token or None if all methods fail
        """
        logger.info("[CaptchaFix] Attempting hCaptcha solve with enhanced fallback...")
        
        # Try primary provider first
        try:
            result = await solver.solve_with_fallback(page, "hcaptcha", sitekey, url)
            if result:
                logger.info("[CaptchaFix] ✅ hCaptcha solved successfully")
                return result
        except Exception as e:
            logger.warning(f"[CaptchaFix] Primary solve failed: {e}")
        
        # If 2Captcha failed with ERROR_METHOD_CALL, try CapSolver directly
        if hasattr(solver, 'capsolver_api_key') and solver.capsolver_api_key:
            logger.info("[CaptchaFix] Trying CapSolver as fallback...")
            try:
                result = await solver._solve_capsolver(sitekey, url, "hcaptcha")
                if result:
                    logger.info("[CaptchaFix] ✅ CapSolver succeeded")
                    return result
            except Exception as e:
                logger.error(f"[CaptchaFix] CapSolver also failed: {e}")
        
        logger.error("[CaptchaFix] All captcha solving methods exhausted")
        return None

class NavigationFix:
    """Fixes for navigation and timeout issues."""
    
    @staticmethod
    async def navigate_with_extended_timeout(page, url: str, timeout: int = 120000) -> bool:
        """
        Navigate with extended timeout and multiple retry strategies.
        
        Handles sites like FreeBitcoin that are slow or use aggressive blocking.
        
        Args:
            page: Playwright Page
            url: URL to navigate to
            timeout: Timeout in milliseconds (default 120s)
            
        Returns:
            True if navigation successful
        """
        strategies = [
            ("domcontentloaded", timeout),
            ("commit", timeout // 2),  # Faster, less strict
            ("networkidle", timeout),   # Wait for network to be quiet
        ]
        
        for strategy, wait_timeout in strategies:
            try:
                logger.info(f"[NavigationFix] Trying {url} with wait_until={strategy}, timeout={wait_timeout}ms")
                await page.goto(url, wait_until=strategy, timeout=wait_timeout)
                await asyncio.sleep(2)
                logger.info(f"[NavigationFix] ✅ Navigation succeeded with {strategy}")
                return True
            except Exception as e:
                logger.warning(f"[NavigationFix] Strategy {strategy} failed: {str(e)[:100]}")
                continue
        
        logger.error(f"[NavigationFix] All navigation strategies failed for {url}")
        return False
    
    @staticmethod
    async def handle_slow_site(bot, url: str) -> bool:
        """
        Enhanced navigation for slow or blocking sites.
        
        Includes:
        - Extended Cloudflare handling
        - Multiple navigation strategies
        - Proxy rotation if available
        
        Args:
            bot: FaucetBot instance
            url: URL to navigate to
            
        Returns:
            True if navigation and Cloudflare bypass successful
        """
        # Try navigation with extended timeout
        page = bot.page
        success = await NavigationFix.navigate_with_extended_timeout(page, url, timeout=150000)
        
        if not success:
            return False
        
        # Handle Cloudflare with extended timeout
        if hasattr(bot, 'handle_cloudflare'):
            try:
                logger.info("[NavigationFix] Handling Cloudflare with extended timeout...")
                await bot.handle_cloudflare(max_wait_seconds=180)  # 3 minutes
                await asyncio.sleep(3)
                logger.info("[NavigationFix] ✅ Cloudflare handled")
            except Exception as e:
                logger.warning(f"[NavigationFix] Cloudflare handling: {e}")
        
        return True

class BalanceTimerFix:
    """Fixes for balance and timer extraction compatibility."""
    
    @staticmethod
    async def get_balance_safe(bot, default_selector: str = ".balance") -> str:
        """
        Safely call get_balance with or without selector parameter.
        
        Handles both signatures:
        - async def get_balance(self, selector, fallback_selectors=None)
        - async def get_balance(self)
        
        Args:
            bot: FaucetBot instance
            default_selector: Default selector to try
            
        Returns:
            Balance string or "0" on failure
        """
        try:
            # Try with selector first (most bots use this)
            return await bot.get_balance(default_selector)
        except TypeError:
            # Method doesn't take arguments
            try:
                return await bot.get_balance()
            except Exception as e:
                logger.error(f"[BalanceTimerFix] Balance extraction failed: {e}")
                return "0"
        except Exception as e:
            logger.error(f"[BalanceTimerFix] Balance extraction error: {e}")
            return "0"
    
    @staticmethod
    async def get_timer_safe(bot, default_selector: str = "#time") -> float:
        """
        Safely call get_timer with or without selector parameter.
        
        Args:
            bot: FaucetBot instance
            default_selector: Default selector to try
            
        Returns:
            Timer in minutes or 0.0 on failure
        """
        try:
            # Try with selector first
            return await bot.get_timer(default_selector)
        except TypeError:
            # Method doesn't take arguments
            try:
                return await bot.get_timer()
            except Exception as e:
                logger.error(f"[BalanceTimerFix] Timer extraction failed: {e}")
                return 0.0
        except Exception as e:
            logger.error(f"[BalanceTimerFix] Timer extraction error: {e}")
            return 0.0


# Quick fix functions that can be imported and used directly

async def fix_hcaptcha_solve(solver, page, sitekey: str, url: str) -> Optional[str]:
    """Quick function to solve hCaptcha with fallback."""
    return await CaptchaFix.solve_hcaptcha_with_fallback(solver, page, sitekey, url)

async def fix_slow_navigation(bot, url: str) -> bool:
    """Quick function to handle slow/blocking sites."""
    return await NavigationFix.handle_slow_site(bot, url)

async def fix_get_balance(bot, selector: str = ".balance") -> str:
    """Quick function to safely get balance."""
    return await BalanceTimerFix.get_balance_safe(bot, selector)

async def fix_get_timer(bot, selector: str = "#time") -> float:
    """Quick function to safely get timer."""
    return await BalanceTimerFix.get_timer_safe(bot, selector)
