"""
FreeBitcoin Login Fix - Research-Based Solution
===============================================

Based on analysis of:
1. Current FreeBitcoin website structure (Feb 2026)
2. TEST_FREEBITCOIN_FIX.md diagnostic procedures
3. Common login failure patterns

This module provides enhanced selectors and login logic specifically for FreeBitcoin.
"""

import asyncio
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class FreeBitcoinLoginFix:
    """Enhanced login logic for FreeBitcoin with research-based fixes."""
    
    # Updated selectors based on Feb 2026 research
    EMAIL_SELECTORS = [
        "#login_form_btc_address",  # Primary selector (confirmed working)
        "input[name='btc_address']",  # FreeBitcoin uses Bitcoin address as username
        "input[name='email']",
        "input[type='email']",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "input[placeholder*='address' i]",
        "#email",
        "#btc_address",
    ]
    
    PASSWORD_SELECTORS = [
        "#login_form_password",  # Primary selector (confirmed working)
        "input[name='password']",
        "input[type='password']",
        "#password",
        "input[id*='pass' i]",
    ]
    
    SUBMIT_SELECTORS = [
        "#login_button",  # Primary (confirmed working)
        "button[id*='login' i]",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Login')",
        "button:has-text('LOG IN')",
        "button.btn-login",
        "form button[type='submit']",
    ]
    
    LOGIN_TRIGGER_SELECTORS = [
        "a:text-is('LOGIN')",  # Exact match for FreeBitcoin
        "a:has-text('LOG IN')",
        "button:has-text('LOGIN')",
        "a[href*='op=login']",
        "a.login",
        "#login_link",
    ]
    
    @staticmethod
    async def enhanced_login(bot, page, creds: Dict[str, str]) -> bool:
        """
        Enhanced login specifically for FreeBitcoin.
        
        Args:
            bot: The FaucetBot instance
            page: Playwright Page instance
            creds: Credentials dict with username/email and password
        
        Returns:
            bool: True if login successful
        """
        login_id = creds.get("username") or creds.get("email")
        if hasattr(bot, 'strip_email_alias'):
            login_id = bot.strip_email_alias(login_id)
        password = creds.get("password")
        
        if not login_id or not password:
            logger.error("[FreeBitcoin] Missing credentials")
            return False
        
        try:
            # Navigate to base URL
            logger.info("[FreeBitcoin Fix] Navigating to base URL...")
            await page.goto("https://freebitco.in", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            
            # Handle Cloudflare with extended timeout
            if hasattr(bot, 'handle_cloudflare'):
                await bot.handle_cloudflare(max_wait_seconds=120)
            
            # Close any popups
            if hasattr(bot, 'close_popups'):
                await bot.close_popups()
            
            await asyncio.sleep(1)
            
            # Check if already logged in
            if hasattr(bot, 'is_logged_in'):
                if await bot.is_logged_in():
                    logger.info("[FreeBitcoin Fix] Already logged in")
                    return True
            
            # Click login trigger to show form
            logger.info("[FreeBitcoin Fix] Looking for login trigger...")
            trigger_clicked = False
            for selector in FreeBitcoinLoginFix.LOGIN_TRIGGER_SELECTORS:
                try:
                    trigger = page.locator(selector).first
                    if await trigger.is_visible(timeout=3000):
                        logger.info(f"[FreeBitcoin Fix] Clicking trigger: {selector}")
                        if hasattr(bot, 'human_like_click'):
                            await bot.human_like_click(trigger)
                        else:
                            await trigger.click()
                        await asyncio.sleep(2)
                        trigger_clicked = True
                        break
                except:
                    continue
            
            if not trigger_clicked:
                logger.warning("[FreeBitcoin Fix] Login trigger not found - form may already be visible")
            
            # Wait for form to appear
            await asyncio.sleep(1)
            
            # Find email field with enhanced selectors
            email_field = None
            for selector in FreeBitcoinLoginFix.EMAIL_SELECTORS:
                try:
                    field = page.locator(selector).first
                    if await field.is_visible(timeout=5000):
                        logger.info(f"[FreeBitcoin Fix] Found email field: {selector}")
                        email_field = field
                        break
                except:
                    continue
            
            if not email_field:
                logger.error("[FreeBitcoin Fix] Email field not found")
                # Take screenshot for debugging
                try:
                    await page.screenshot(path="logs/freebitcoin_no_email_field.png", full_page=True)
                except:
                    pass
                return False
            
            # Find password field
            password_field = None
            for selector in FreeBitcoinLoginFix.PASSWORD_SELECTORS:
                try:
                    field = page.locator(selector).first
                    if await field.is_visible(timeout=5000):
                        logger.info(f"[FreeBitcoin Fix] Found password field: {selector}")
                        password_field = field
                        break
                except:
                    continue
            
            if not password_field:
                logger.error("[FreeBitcoin Fix] Password field not found")
                try:
                    await page.screenshot(path="logs/freebitcoin_no_password_field.png", full_page=True)
                except:
                    pass
                return False
            
            # Fill credentials
            logger.info("[FreeBitcoin Fix] Filling credentials...")
            if hasattr(bot, 'human_type'):
                await bot.human_type(email_field, login_id)
                await asyncio.sleep(0.5)
                await bot.human_type(password_field, password)
            else:
                await email_field.fill(login_id)
                await asyncio.sleep(0.3)
                await password_field.fill(password)
            
            # Solve CAPTCHA if present
            logger.info("[FreeBitcoin Fix] Checking for CAPTCHA...")
            try:
                captcha_exists = await page.locator(".cf-turnstile, .h-captcha, .g-recaptcha, iframe[src*='captcha']").count() > 0
                if captcha_exists and hasattr(bot, 'solver'):
                    logger.info("[FreeBitcoin Fix] Solving CAPTCHA...")
                    await bot.solver.solve_captcha(page)
                    await asyncio.sleep(2)
            except Exception as e:
                logger.debug(f"[FreeBitcoin Fix] CAPTCHA check: {e}")
            
            # Find and click submit
            submit_btn = None
            for selector in FreeBitcoinLoginFix.SUBMIT_SELECTORS:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=5000):
                        logger.info(f"[FreeBitcoin Fix] Found submit button: {selector}")
                        submit_btn = btn
                        break
                except:
                    continue
            
            if submit_btn:
                logger.info("[FreeBitcoin Fix] Clicking submit...")
                if hasattr(bot, 'human_like_click'):
                    await bot.human_like_click(submit_btn)
                else:
                    await submit_btn.click()
            else:
                logger.warning("[FreeBitcoin Fix] Submit not found, trying Enter key...")
                await password_field.press("Enter")
            
            # Wait for login to complete
            await asyncio.sleep(3)
            
            # Verify login
            if hasattr(bot, 'is_logged_in'):
                if await bot.is_logged_in():
                    logger.info("✅ [FreeBitcoin Fix] Login successful!")
                    return True
            
            # Check for error messages
            try:
                error_elem = page.locator(".alert-danger, .error, .alert-error").first
                if await error_elem.is_visible(timeout=2000):
                    error_text = await error_elem.text_content()
                    logger.error(f"[FreeBitcoin Fix] Login error: {error_text}")
            except:
                pass
            
            logger.error("[FreeBitcoin Fix] Login verification failed")
            try:
                await page.screenshot(path="logs/freebitcoin_login_failed.png", full_page=True)
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"[FreeBitcoin Fix] Exception during login: {e}", exc_info=True)
            try:
                await page.screenshot(path="logs/freebitcoin_exception.png")
            except:
                pass
            return False
