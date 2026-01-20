"""
Profitability Monitor Script

Monitors bot profitability by tracking earnings vs costs.
Alerts when ROI drops below threshold.

Usage:
    python scripts/profitability_monitor.py
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.analytics import EarningsTracker, ANALYTICS_FILE
from core.config import BotSettings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ProfitabilityMonitor")

# ROI threshold for alerts (percentage)
ROI_THRESHOLD = 50.0


async def get_2captcha_balance(api_key: str) -> Optional[float]:
    """
    Fetch current balance from 2Captcha API.
    
    Args:
        api_key: 2Captcha API key
        
    Returns:
        Current balance in USD, or None if error
    """
    import aiohttp
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"http://2captcha.com/res.php?key={api_key}&action=getbalance&json=1"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("status") == 1:
                    balance = float(data["request"])
                    logger.info(f"2Captcha balance: ${balance:.2f}")
                    return balance
                else:
                    logger.warning(f"Failed to get 2Captcha balance: {data.get('request')}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching 2Captcha balance: {e}")
        return None


def calculate_earnings(tracker: EarningsTracker, hours: int = 24) -> Dict[str, float]:
    """
    Calculate total earnings by currency over the specified time period.
    
    Args:
        tracker: EarningsTracker instance
        hours: Number of hours to look back
        
    Returns:
        Dict mapping currency to total earnings
    """
    stats = tracker.get_session_stats()
    earnings_by_currency = stats.get("earnings_by_currency", {})
    
    # Convert to USD (simplified - in production would use real exchange rates)
    # For now, we'll just sum the amounts as a basic metric
    total_earnings = sum(earnings_by_currency.values())
    
    logger.info(f"Total earnings (last {hours}h): {total_earnings:.8f} across {len(earnings_by_currency)} currencies")
    return earnings_by_currency


def estimate_costs(tracker: EarningsTracker, initial_balance: Optional[float], current_balance: Optional[float], hours: int = 24) -> Dict[str, float]:
    """
    Estimate costs including captcha and proxy expenses.
    
    Args:
        tracker: EarningsTracker instance
        initial_balance: Starting 2Captcha balance
        current_balance: Current 2Captcha balance
        hours: Number of hours to estimate for
        
    Returns:
        Dict with cost breakdown
    """
    costs = {
        "captcha_cost": 0.0,
        "proxy_cost": 0.0,
        "total_cost": 0.0
    }
    
    # Calculate captcha costs from balance difference
    if initial_balance is not None and current_balance is not None:
        captcha_spent = max(0, initial_balance - current_balance)
        costs["captcha_cost"] = captcha_spent
        logger.info(f"Captcha costs: ${captcha_spent:.2f}")
    else:
        # Estimate based on claims (rough estimate: $0.003 per captcha)
        stats = tracker.get_session_stats()
        total_claims = stats.get("total_claims", 0)
        estimated_captcha = total_claims * 0.003
        costs["captcha_cost"] = estimated_captcha
        logger.info(f"Estimated captcha costs: ${estimated_captcha:.2f} (based on {total_claims} claims)")
    
    # Proxy costs (simplified - could be enhanced to track actual proxy usage)
    # Estimate: $0.001 per claim for proxy bandwidth
    stats = tracker.get_session_stats()
    estimated_proxy = stats.get("total_claims", 0) * 0.001
    costs["proxy_cost"] = estimated_proxy
    logger.info(f"Estimated proxy costs: ${estimated_proxy:.2f}")
    
    costs["total_cost"] = costs["captcha_cost"] + costs["proxy_cost"]
    return costs


def calculate_roi(earnings: float, costs: float) -> float:
    """
    Calculate Return on Investment percentage.
    
    Args:
        earnings: Total earnings in USD
        costs: Total costs in USD
        
    Returns:
        ROI as a percentage
    """
    if costs == 0:
        return 100.0 if earnings > 0 else 0.0
    
    roi = ((earnings - costs) / costs) * 100
    return roi


async def check_profitability(hours: int = 24) -> Dict[str, Any]:
    """
    Main profitability check function.
    
    Args:
        hours: Number of hours to analyze
        
    Returns:
        Dict with profitability metrics
    """
    # Load settings
    settings = BotSettings()
    
    # Initialize tracker
    tracker = EarningsTracker()
    
    # Get 2Captcha balance
    current_balance = None
    if settings.twocaptcha_api_key:
        current_balance = await get_2captcha_balance(settings.twocaptcha_api_key)
    else:
        logger.warning("No 2Captcha API key configured")
    
    # Load initial balance from tracking file (if exists)
    balance_file = os.path.join(os.path.dirname(ANALYTICS_FILE), "captcha_balance_tracking.json")
    initial_balance = None
    try:
        if os.path.exists(balance_file):
            with open(balance_file, "r") as f:
                data = json.load(f)
                initial_balance = data.get("initial_balance")
    except Exception as e:
        logger.warning(f"Could not load balance tracking: {e}")
    
    # Save current balance as initial if not set
    if initial_balance is None and current_balance is not None:
        initial_balance = current_balance
        try:
            with open(balance_file, "w") as f:
                json.dump({"initial_balance": initial_balance, "timestamp": datetime.now().isoformat()}, f)
        except Exception as e:
            logger.warning(f"Could not save balance tracking: {e}")
    
    # Calculate earnings (convert to USD equivalent - simplified)
    earnings_by_currency = calculate_earnings(tracker, hours)
    # For simplicity, assume 1 unit = $0.01 (would need real exchange rates in production)
    total_earnings_usd = sum(earnings_by_currency.values()) * 0.01
    
    # Calculate costs
    costs = estimate_costs(tracker, initial_balance, current_balance, hours)
    
    # Calculate net profit and ROI
    net_profit = total_earnings_usd - costs["total_cost"]
    roi = calculate_roi(total_earnings_usd, costs["total_cost"])
    
    result = {
        "timestamp": datetime.now().isoformat(),
        "period_hours": hours,
        "earnings_usd": total_earnings_usd,
        "earnings_by_currency": earnings_by_currency,
        "costs": costs,
        "net_profit": net_profit,
        "roi_percentage": roi,
        "captcha_balance": current_balance
    }
    
    return result


def generate_alert(result: Dict[str, Any]) -> bool:
    """
    Check if an alert should be generated based on profitability metrics.
    
    Args:
        result: Profitability check result
        
    Returns:
        True if alert was generated, False otherwise
    """
    roi = result["roi_percentage"]
    net_profit = result["net_profit"]
    
    alert_triggered = False
    
    if roi < ROI_THRESHOLD:
        alert_triggered = True
        logger.warning(f"⚠️  PROFITABILITY ALERT: ROI is {roi:.1f}%, below threshold of {ROI_THRESHOLD}%")
        logger.warning(f"   Net profit: ${net_profit:.2f}")
        logger.warning(f"   Earnings: ${result['earnings_usd']:.2f}")
        logger.warning(f"   Costs: ${result['costs']['total_cost']:.2f}")
        
        # Log breakdown
        logger.warning(f"   - Captcha costs: ${result['costs']['captcha_cost']:.2f}")
        logger.warning(f"   - Proxy costs: ${result['costs']['proxy_cost']:.2f}")
    else:
        logger.info(f"✅ ROI is healthy: {roi:.1f}% (threshold: {ROI_THRESHOLD}%)")
        logger.info(f"   Net profit: ${net_profit:.2f}")
    
    return alert_triggered


async def main():
    """Main entry point for the profitability monitor."""
    logger.info("=" * 60)
    logger.info("CRYPTOBOT PROFITABILITY MONITOR")
    logger.info("=" * 60)
    
    try:
        # Run profitability check
        result = await check_profitability(hours=24)
        
        # Generate alert if needed
        alert_triggered = generate_alert(result)
        
        # Save report
        report_file = os.path.join(os.path.dirname(ANALYTICS_FILE), "profitability_report.json")
        try:
            with open(report_file, "w") as f:
                json.dump(result, f, indent=2)
            logger.info(f"📄 Profitability report saved to {report_file}")
        except Exception as e:
            logger.warning(f"Could not save report: {e}")
        
        logger.info("=" * 60)
        logger.info("Profitability check complete")
        logger.info("=" * 60)
        
        # Exit with status code
        sys.exit(1 if alert_triggered else 0)
        
    except Exception as e:
        logger.error(f"Error during profitability check: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
