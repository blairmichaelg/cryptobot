import re
import logging
from typing import Optional, List, Dict, Any
from playwright.async_api import Page

logger = logging.getLogger(__name__)

class DataExtractor:
    """
    Utility class for extracting data from faucet pages using regex and common patterns.
    
    This class provides standardized methods for parsing timers and balances across
    all faucet implementations, ensuring consistent data extraction.
    
    Examples:
        >>> DataExtractor.parse_timer_to_minutes("59:59")
        59.983333333333334
        >>> DataExtractor.parse_timer_to_minutes("1h 30m")
        90.0
        >>> DataExtractor.extract_balance("Balance: 1,234.56 BTC")
        '1234.56'
    """

    @staticmethod
    def parse_timer_to_minutes(text: str) -> float:
        """
        Parses timer text into total minutes.
        
        Supported formats:
        - "59:59" (MM:SS)
        - "01:02:03" (HH:MM:SS)
        - "1h 30m" or "1h30m"
        - "45 min" or "45 minutes"
        - "120 seconds" or "120s"
        - "2 hours" or "2h"
        - "3 days" or "3d"
        
        Args:
            text: The timer text to parse
            
        Returns:
            Total time in minutes as a float. Returns 0.0 if parsing fails.
        """
        if not text:
            logger.debug("Empty timer text provided")
            return 0.0

        text = text.lower().strip()
        logger.debug(f"Parsing timer text: '{text}'")
        
        # 1. Format: HH:MM:SS or MM:SS
        match = re.search(r'(\d+):(\d+):?(\d+)?', text)
        if match:
            h = int(match.group(1)) if match.group(3) else 0
            m = int(match.group(2)) if match.group(3) else int(match.group(1))
            s = int(match.group(3)) if match.group(3) else int(match.group(2))
            result = h * 60 + m + s / 60.0
            logger.debug(f"Parsed HH:MM:SS format: {result:.2f} minutes")
            return result

        # 2. Format: Xd Yh Zm (days, hours, minutes, seconds)
        days = 0
        hours = 0
        minutes = 0
        seconds = 0
        
        # Check for days
        d_match = re.search(r'(\d+)\s*d(?:ay)?s?', text)
        if d_match:
            days = int(d_match.group(1))
            
        # Check for hours
        h_match = re.search(r'(\d+)\s*h(?:our)?s?', text)
        if h_match:
            hours = int(h_match.group(1))
            
        # Check for minutes
        m_match = re.search(r'(\d+)\s*m(?:in(?:ute)?)?s?', text)
        if m_match:
            minutes = int(m_match.group(1))
            
        # Check for seconds
        s_match = re.search(r'(\d+)\s*s(?:ec(?:ond)?)?s?', text)
        if s_match:
            seconds = int(s_match.group(1))
        
        if days or hours or minutes or seconds:
            result = days * 24 * 60 + hours * 60 + minutes + seconds / 60.0
            logger.debug(f"Parsed compound format (d:{days} h:{hours} m:{minutes} s:{seconds}): {result:.2f} minutes")
            return result

        # 3. Fallback: Just a number (assume minutes)
        num_match = re.search(r'(\d+)', text)
        if num_match:
            result = float(num_match.group(1))
            logger.debug(f"Parsed as plain number: {result} minutes")
            return result

        logger.warning(f"Failed to parse timer text: '{text}'")
        return 0.0

    @staticmethod
    def extract_balance(text: str) -> str:
        """
        Extracts numeric balance from text like "Balance: 1,234.56 BTC" -> "1234.56"
        
        Handles:
        - Standard decimal: "1234.56" -> "1234.56"
        - Comma separators: "1,234.56" -> "1234.56"
        - Scientific notation: "3.8e-07" -> "0.00000038"
        - Leading zeros: "0.00012345" -> "0.00012345"
        - Embedded in text: "Balance: 100 BTC" -> "100"
        
        Args:
            text: The balance text to extract from
            
        Returns:
            Extracted balance as a string. Returns "0" if extraction fails.
            
        Examples:
            >>> DataExtractor.extract_balance("Balance: 1,234.56 BTC")
            '1234.56'
            >>> DataExtractor.extract_balance("3.8e-07")
            '0.00000038'
            >>> DataExtractor.extract_balance("0.00012345")
            '0.00012345'
        """
        if not text:
            logger.debug("Empty balance text provided")
            return "0"
        
        original_text = text
        text = text.strip()
        
        # Remove common non-numeric characters but keep decimal point, minus sign, and 'e' for scientific notation
        text = text.replace(",", "").replace("$", "").replace("₿", "").replace("฿", "")
        
        # Try to find scientific notation first (e.g., 3.8e-07, 1.2E+05)
        sci_match = re.search(r'([+-]?\d+\.?\d*[eE][+-]?\d+)', text)
        if sci_match:
            try:
                sci_value = float(sci_match.group(1))
                # Convert to string without scientific notation
                if sci_value == 0:
                    result = "0"
                elif abs(sci_value) < 1e-8:
                    result = f"{sci_value:.10f}".rstrip('0').rstrip('.')
                elif abs(sci_value) < 1:
                    result = f"{sci_value:.8f}".rstrip('0').rstrip('.')
                else:
                    result = str(sci_value)
                logger.debug(f"Extracted scientific notation: {result} from '{original_text}'")
                return result
            except (ValueError, OverflowError) as e:
                logger.warning(f"Failed to parse scientific notation '{sci_match.group(1)}': {e}")
        
        # Find standard decimal number (including decimals)
        match = re.search(r'(\d+\.?\d*)', text)
        if match:
            result = match.group(1)
            # Remove trailing zeros and decimal point if unnecessary
            if '.' in result:
                result = result.rstrip('0').rstrip('.')
            if result == "":
                result = "0"
            logger.debug(f"Extracted balance: {result} from '{original_text}'")
            return result
        
        logger.warning(f"Failed to extract balance from: '{original_text}'")
        return "0"

    @staticmethod
    async def find_balance_selector_in_dom(page: Page) -> Optional[str]:
        """Auto-detect balance selector by looking for common patterns in DOM."""
        common_balance_patterns = [
            "[class*='balance']",
            "[class*='user-balance']",
            "[id*='balance']",
            ".balance",
            ".user-balance",
            "#balance",
            "[data-balance]"
        ]
        
        for pattern in common_balance_patterns:
            try:
                el = page.locator(pattern)
                if await el.count() > 0 and await el.is_visible():
                    logger.info(f"Auto-detected balance selector: {pattern}")
                    return pattern
            except Exception:
                continue
        
        return None

    @staticmethod
    async def find_timer_selector_in_dom(page: Page) -> Optional[str]:
        """Auto-detect timer selector by looking for common patterns in DOM."""
        common_timer_patterns = [
            "[class*='timer']",
            "[class*='countdown']",
            "[id*='timer']",
            "[id*='countdown']",
            ".timer",
            "#timer",
            "[data-timer]"
        ]
        
        for pattern in common_timer_patterns:
            try:
                el = page.locator(pattern)
                if await el.count() > 0 and await el.is_visible():
                    logger.info(f"Auto-detected timer selector: {pattern}")
                    return pattern
            except Exception:
                continue
        
        return None
