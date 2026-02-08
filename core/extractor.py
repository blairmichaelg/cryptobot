"""Data extraction utilities for faucet pages.

Provides standardised methods for parsing timers, balances, and
auto-detecting DOM selectors across all faucet implementations.
"""

import re
import logging
from typing import Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class DataExtractor:
    """Utility class for extracting data from faucet pages.

    Uses regex and common patterns to parse timers and balances,
    ensuring consistent data extraction across all faucet bots.

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
        """Parse timer text into total minutes.

        Supported formats:
            - ``"59:59"`` (MM:SS)
            - ``"01:02:03"`` (HH:MM:SS)
            - ``"1h 30m"`` or ``"1h30m"``
            - ``"45 min"`` or ``"45 minutes"``
            - ``"120 seconds"`` or ``"120s"``
            - ``"2 hours"`` or ``"2h"``
            - ``"3 days"`` or ``"3d"``

        Args:
            text: The timer text to parse.

        Returns:
            Total time in minutes as a float.  Returns ``0.0`` if
            parsing fails.
        """
        if not text:
            logger.debug("Empty timer text provided")
            return 0.0

        text = text.lower().strip()
        logger.debug("Parsing timer text: '%s'", text)

        # 1. Format: HH:MM:SS or MM:SS
        match = re.search(r'(\d+):(\d+):?(\d+)?', text)
        if match:
            h = int(match.group(1)) if match.group(3) else 0
            m = (
                int(match.group(2))
                if match.group(3)
                else int(match.group(1))
            )
            s = (
                int(match.group(3))
                if match.group(3)
                else int(match.group(2))
            )
            result = h * 60 + m + s / 60.0
            logger.debug(
                "Parsed HH:MM:SS format: %.2f minutes", result,
            )
            return result

        # 2. Format: Xd Yh Zm (days, hours, minutes, seconds)
        days = 0
        hours = 0
        minutes = 0
        seconds = 0

        d_match = re.search(r'(\d+)\s*d(?:ay)?s?', text)
        if d_match:
            days = int(d_match.group(1))

        h_match = re.search(r'(\d+)\s*h(?:our)?s?', text)
        if h_match:
            hours = int(h_match.group(1))

        m_match = re.search(
            r'(\d+)\s*m(?:in(?:ute)?)?s?', text,
        )
        if m_match:
            minutes = int(m_match.group(1))

        s_match = re.search(
            r'(\d+)\s*s(?:ec(?:ond)?)?s?', text,
        )
        if s_match:
            seconds = int(s_match.group(1))

        if days or hours or minutes or seconds:
            result = (
                days * 24 * 60
                + hours * 60
                + minutes
                + seconds / 60.0
            )
            logger.debug(
                "Parsed compound format "
                "(d:%d h:%d m:%d s:%d): %.2f minutes",
                days, hours, minutes, seconds, result,
            )
            return result

        # 3. Fallback: Just a number (assume minutes)
        num_match = re.search(r'(\d+)', text)
        if num_match:
            result = float(num_match.group(1))
            logger.debug(
                "Parsed as plain number: %s minutes", result,
            )
            return result

        logger.warning(
            "Failed to parse timer text: '%s'", text,
        )
        return 0.0

    @staticmethod
    def extract_balance(text: str) -> str:
        """Extract numeric balance from text.

        Handles:
            - Standard decimal: ``"1234.56"``
            - Comma separators: ``"1,234.56"`` -> ``"1234.56"``
            - Scientific notation: ``"3.8e-07"``
            - Leading zeros: ``"0.00012345"``
            - Embedded in text: ``"Balance: 100 BTC"`` -> ``"100"``

        Args:
            text: The balance text to extract from.

        Returns:
            Extracted balance as a string.  Returns ``"0"`` if
            extraction fails.

        Examples:
            >>> DataExtractor.extract_balance("1,234.56 BTC")
            '1234.56'
            >>> DataExtractor.extract_balance("3.8e-07")
            '0.00000038'
        """
        if not text:
            logger.debug("Empty balance text provided")
            return "0"

        original_text = text
        text = text.strip()

        # Remove common non-numeric characters but keep
        # decimal point, minus sign, and 'e' for sci notation
        text = (
            text.replace(",", "")
            .replace("$", "")
            .replace("\u20bf", "")
            .replace("\u0e3f", "")
        )

        # Try scientific notation first (e.g. 3.8e-07)
        sci_match = re.search(
            r'([+-]?\d+\.?\d*[eE][+-]?\d+)', text,
        )
        if sci_match:
            try:
                sci_value = float(sci_match.group(1))
                if sci_value == 0:
                    result = "0"
                elif abs(sci_value) < 1e-8:
                    result = (
                        f"{sci_value:.10f}"
                        .rstrip('0')
                        .rstrip('.')
                    )
                elif abs(sci_value) < 1:
                    result = (
                        f"{sci_value:.8f}"
                        .rstrip('0')
                        .rstrip('.')
                    )
                else:
                    result = str(sci_value)
                logger.debug(
                    "Extracted scientific notation: %s "
                    "from '%s'",
                    result, original_text,
                )
                return result
            except (ValueError, OverflowError) as e:
                logger.warning(
                    "Failed to parse scientific notation "
                    "'%s': %s",
                    sci_match.group(1), e,
                )

        # Find standard decimal number
        match = re.search(r'(\d+\.?\d*)', text)
        if match:
            result = match.group(1)
            if '.' in result:
                result = result.rstrip('0').rstrip('.')
            if result == "":
                result = "0"
            logger.debug(
                "Extracted balance: %s from '%s'",
                result, original_text,
            )
            return result

        logger.warning(
            "Failed to extract balance from: '%s'",
            original_text,
        )
        return "0"

    @staticmethod
    async def find_balance_selector_in_dom(
        page: Page,
    ) -> Optional[str]:
        """Auto-detect balance selector in the DOM.

        Searches for common CSS patterns used by faucet sites to
        display user balances.

        Args:
            page: Playwright page instance.

        Returns:
            CSS selector string, or ``None`` if not found.
        """
        common_balance_patterns = [
            "[class*='balance']",
            "[class*='user-balance']",
            "[id*='balance']",
            ".balance",
            ".user-balance",
            "#balance",
            "[data-balance]",
        ]

        for pattern in common_balance_patterns:
            try:
                el = page.locator(pattern)
                if await el.count() > 0 and await el.is_visible():
                    logger.info(
                        "Auto-detected balance selector: %s",
                        pattern,
                    )
                    return pattern
            except Exception:
                continue

        return None

    @staticmethod
    async def find_timer_selector_in_dom(
        page: Page,
    ) -> Optional[str]:
        """Auto-detect timer/countdown selector in the DOM.

        Searches for common CSS patterns used by faucet sites to
        display countdown timers.

        Args:
            page: Playwright page instance.

        Returns:
            CSS selector string, or ``None`` if not found.
        """
        common_timer_patterns = [
            "[class*='timer']",
            "[class*='countdown']",
            "[id*='timer']",
            "[id*='countdown']",
            ".timer",
            "#timer",
            "[data-timer]",
        ]

        for pattern in common_timer_patterns:
            try:
                el = page.locator(pattern)
                if await el.count() > 0 and await el.is_visible():
                    logger.info(
                        "Auto-detected timer selector: %s",
                        pattern,
                    )
                    return pattern
            except Exception:
                continue

        return None
