"""
Earnings Analytics Module

Tracks and reports profitability metrics for the cryptobot.
"""

import json
import os
import time
import logging
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)

# Analytics data file path
ANALYTICS_FILE = os.path.join(os.path.dirname(__file__), "..", "earnings_analytics.json")


class CryptoPriceFeed:
    """
    Fetches and caches cryptocurrency prices in USD.
    Uses CoinGecko API (free tier) with TTL-based caching.
    """
    
    CACHE_TTL = 300  # 5 minutes
    API_URL = "https://api.coingecko.com/api/v3/simple/price"
    
    # CoinGecko ID mapping for common currencies
    CURRENCY_IDS = {
        "BTC": "bitcoin",
        "LTC": "litecoin",
        "DOGE": "dogecoin",
        "BCH": "bitcoin-cash",
        "TRX": "tron",
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "SOL": "solana",
        "TON": "the-open-network",
        "DASH": "dash",
        "POLYGON": "matic-network",
        "USDT": "tether"
    }
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_file = os.path.join(os.path.dirname(__file__), "..", "config", "price_cache.json")
        self._load_cache()
    
    def _load_cache(self):
        """Load cached prices from disk."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    # Only load non-expired entries
                    now = time.time()
                    self.cache = {
                        k: v for k, v in data.items()
                        if v.get("timestamp", 0) + self.CACHE_TTL > now
                    }
                logger.debug(f"Loaded {len(self.cache)} cached prices")
        except Exception as e:
            logger.debug(f"Could not load price cache: {e}")
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f)
        except Exception as e:
            logger.debug(f"Could not save price cache: {e}")
    
    async def get_price(self, currency: str) -> Optional[float]:
        """
        Get current USD price for a currency.
        
        Args:
            currency: Currency code (BTC, LTC, DOGE, etc.)
            
        Returns:
            Price in USD, or None if unavailable
        """
        currency = currency.upper()
        
        # Check cache first
        if currency in self.cache:
            cached = self.cache[currency]
            if time.time() - cached["timestamp"] < self.CACHE_TTL:
                return cached["price"]
        
        # Fetch from API
        coin_id = self.CURRENCY_IDS.get(currency)
        if not coin_id:
            logger.warning(f"Unknown currency: {currency}")
            return None
        
        try:
            params = {
                "ids": coin_id,
                "vs_currencies": "usd"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.API_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = data.get(coin_id, {}).get("usd")
                        
                        if price:
                            # Cache result
                            self.cache[currency] = {
                                "price": price,
                                "timestamp": time.time()
                            }
                            self._save_cache()
                            logger.debug(f"Fetched {currency} price: ${price}")
                            return price
        except Exception as e:
            logger.warning(f"Failed to fetch {currency} price: {e}")
        
        return None
    
    async def convert_to_usd(self, amount: float, currency: str) -> float:
        """
        Convert an amount of cryptocurrency to USD.
        
        Args:
            amount: Amount in smallest unit (satoshi for BTC, etc.)
            currency: Currency code
            
        Returns:
            USD value
        """
        currency = currency.upper()
        price = await self.get_price(currency)
        
        if not price:
            return 0.0
        
        # Convert from smallest unit to whole coin
        # Bitcoin and most alts use 8 decimal places (100M satoshi = 1 coin)
        # Ethereum uses 18 decimal places
        if currency == "ETH":
            divisor = 1e18
        else:
            divisor = 1e8
        
        coin_amount = amount / divisor
        return coin_amount * price


# Global price feed instance
_price_feed = None

def get_price_feed() -> CryptoPriceFeed:
    """Get or create the global price feed."""
    global _price_feed
    if _price_feed is None:
        _price_feed = CryptoPriceFeed()
    return _price_feed


@dataclass
class ClaimRecord:
    """Record of a single claim attempt."""
    timestamp: float
    faucet: str
    success: bool
    amount: float = 0.0
    currency: str = "unknown"
    balance_after: float = 0.0

@dataclass
class CostRecord:
    """Record of a cost incurred (captcha, proxy)."""
    timestamp: float
    type: str  # 'captcha', 'proxy'
    amount_usd: float
    faucet: Optional[str] = None


class EarningsTracker:
    """
    Tracks earnings, claim success rates, and profitability metrics.
    Persists data to disk for historical analysis.
    """
    
    def __init__(self, storage_file: Optional[str] = None):
        self.storage_file = storage_file or ANALYTICS_FILE
        self.claims: list = []
        self.costs: list = []  # Fix #27: Track costs
        self.session_start = time.time()
        
        # Ensure file exists and is writable
        if not os.path.exists(ANALYTICS_FILE):
             self._save()
             
        self._load()
    
    def _load(self):
        """Load existing analytics data from disk."""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
                    self.claims = data.get("claims", [])
                    self.costs = data.get("costs", [])
                    logger.info(f"📊 Loaded {len(self.claims)} claims and {len(self.costs)} costs.")
        except Exception as e:
            logger.warning(f"Could not load analytics: {e}")
            self.claims = []
    
    def _save(self):
        """Persist analytics data to disk."""
        try:
            data = {
                "claims": self.claims[-2000:],  # Increased limit
                "costs": self.costs[-1000:],
                "last_updated": time.time()
            }
            with open(self.storage_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Could not save analytics: {e}")
    
    def record_claim(self, faucet: str, success: bool, amount: float = 0.0, 
                     currency: str = "unknown", balance_after: float = 0.0,
                     allow_test: bool = False):
        """
        Record a claim attempt.
        
        Args:
            faucet: Name of the faucet
            success: Whether the claim succeeded
            amount: Amount claimed
            currency: Currency code (BTC, LTC, DOGE, etc.)
            balance_after: Balance after the claim
            allow_test: Whether to allow test faucets (defaults to False)
        """
        # Filter out test faucets from production analytics unless explicitly allowed
        if not allow_test and (faucet == "test_faucet" or faucet.startswith("test_")):
            logger.debug(f"Skipping analytics for test faucet: {faucet}")
            return
        
        record = ClaimRecord(
            timestamp=time.time(),
            faucet=faucet,
            success=success,
            amount=amount,
            currency=currency,
            balance_after=balance_after
        )
        self.claims.append(asdict(record))
        logger.info(f"📈 Recorded: {faucet} {'✓' if success else '✗'} {amount} {currency}")
        
        
        # Save immediately to ensure data persistence
        self._save()

    def record_cost(self, cost_type: str, amount_usd: float, faucet: str = None):
        """Record a cost incurred (e.g. captcha solve)."""
        record = CostRecord(
            timestamp=time.time(),
            type=cost_type,
            amount_usd=amount_usd,
            faucet=faucet
        )
        self.costs.append(asdict(record))
        logger.debug(f"💸 Cost: {cost_type} ${amount_usd:.4f} for {faucet or 'global'}")
        self._save()

    def get_profitability(self, hours: int = 24) -> Dict[str, Any]:
        """Calculate net profit in USD using real-time price feed."""
        import asyncio
        
        cutoff = time.time() - (hours * 3600)
        
        # Get price feed
        price_feed = get_price_feed()
        
        # Calculate earnings in USD per currency
        earnings_by_currency = defaultdict(float)
        for c in self.claims:
            if c['timestamp'] >= cutoff and c['success']:
                earnings_by_currency[c['currency']] += c['amount']
        
        # Convert to USD
        total_earnings_usd = 0.0
        try:
            # Run async price conversion
            loop = asyncio.get_event_loop()
            for currency, amount in earnings_by_currency.items():
                try:
                    usd_value = loop.run_until_complete(price_feed.convert_to_usd(amount, currency))
                    total_earnings_usd += usd_value
                except Exception as e:
                    logger.debug(f"Could not convert {currency} to USD: {e}")
        except RuntimeError:
            # No event loop - create one
            async def _convert():
                total = 0.0
                for currency, amount in earnings_by_currency.items():
                    try:
                        usd_value = await price_feed.convert_to_usd(amount, currency)
                        total += usd_value
                    except Exception as e:
                        logger.debug(f"Could not convert {currency} to USD: {e}")
                return total
            
            total_earnings_usd = asyncio.run(_convert())
        
        total_costs = sum(cost['amount_usd'] for cost in self.costs if cost['timestamp'] >= cutoff)
        
        return {
            "earnings_usd": total_earnings_usd,
            "costs_usd": total_costs,
            "net_profit_usd": total_earnings_usd - total_costs,
            "roi": (total_earnings_usd / total_costs) if total_costs > 0 else 0
        }
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for the current session."""
        session_claims = [
            c for c in self.claims 
            if c["timestamp"] >= self.session_start
        ]
        
        total = len(session_claims)
        successful = sum(1 for c in session_claims if c["success"])
        
        # Group by currency
        by_currency = defaultdict(float)
        for c in session_claims:
            if c["success"]:
                by_currency[c["currency"]] += c["amount"]
        
        return {
            "session_duration_hours": (time.time() - self.session_start) / 3600,
            "total_claims": total,
            "successful_claims": successful,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "earnings_by_currency": dict(by_currency)
        }
    
    def get_faucet_stats(self, hours: int = 24) -> Dict[str, Dict]:
        """
        Get per-faucet statistics for the last N hours.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            Dict with stats per faucet
        """
        cutoff = time.time() - (hours * 3600)
        recent_claims = [c for c in self.claims if c["timestamp"] >= cutoff]
        
        by_faucet = defaultdict(lambda: {"total": 0, "success": 0, "earnings": 0.0})
        
        for c in recent_claims:
            f = c["faucet"]
            by_faucet[f]["total"] += 1
            if c["success"]:
                by_faucet[f]["success"] += 1
                by_faucet[f]["earnings"] += c["amount"]
        
        # Calculate success rates
        for f in by_faucet:
            total = by_faucet[f]["total"]
            by_faucet[f]["success_rate"] = (by_faucet[f]["success"] / total * 100) if total > 0 else 0
        
        return dict(by_faucet)
    
    def get_hourly_rate(self, faucet: str = None, hours: int = 24) -> Dict[str, float]:
        """
        Calculate earnings per hour by faucet or overall.
        
        This is useful for profitability analysis and dynamic job priority
        adjustments based on which faucets generate the best returns.
        
        Args:
            faucet: Optional specific faucet to check. If None, returns all.
            hours: Number of hours to analyze (default 24)
            
        Returns:
            Dict mapping faucet names to their hourly earning rate
        """
        cutoff = time.time() - (hours * 3600)
        recent = [c for c in self.claims if c["timestamp"] >= cutoff and c["success"]]
        
        by_faucet = defaultdict(float)
        for c in recent:
            if faucet is None or c["faucet"] == faucet:
                by_faucet[c["faucet"]] += c.get("amount", 0)
        
        # Convert to hourly rate
        for f in by_faucet:
            by_faucet[f] = by_faucet[f] / max(hours, 1)
        
        return dict(by_faucet)
    
    def get_daily_summary(self) -> str:
        """Generate a human-readable daily summary."""
        stats = self.get_faucet_stats(24)
        session = self.get_session_stats()
        
        lines = [
            "=" * 50,
            f"EARNINGS SUMMARY (Last 24 Hours)",
            "=" * 50,
            f"Session Duration: {session['session_duration_hours']:.1f} hours",
            f"Total Claims: {session['total_claims']}",
            f"Success Rate: {session['success_rate']:.1f}%",
            "",
            "Earnings by Currency:",
        ]
        
        for currency, amount in session["earnings_by_currency"].items():
            lines.append(f"  {currency}: {amount:.8f}")
        
        lines.extend(["", "Per-Faucet Performance:"])
        for faucet, fstats in stats.items():
            lines.append(f"  {faucet}: {fstats['success']}/{fstats['total']} ({fstats['success_rate']:.0f}%)")
        
        lines.append("=" * 50)
        return "\n".join(lines)

    def get_trending_analysis(self, periods: int = 7) -> Dict[str, Any]:
        """
        Analyze earnings trends over multiple periods.
        """
        trends = {}
        now = time.time()
        
        for i in range(periods):
            period_start = now - ((i + 1) * 24 * 3600)
            period_end = now - (i * 24 * 3600)
            
            period_claims = [
                c for c in self.claims 
                if period_start <= c["timestamp"] < period_end
            ]
            
            for c in period_claims:
                if c["faucet"] not in trends:
                    trends[c["faucet"]] = {
                        "daily_earnings": [0] * periods,
                        "daily_claims": [0] * periods,
                        "daily_success": [0] * periods
                    }
                
                trends[c["faucet"]]["daily_claims"][i] += 1
                if c["success"]:
                    trends[c["faucet"]]["daily_success"][i] += 1
                    trends[c["faucet"]]["daily_earnings"][i] += c.get("amount", 0)
        
        # Calculate growth rates
        for faucet in trends:
            today = trends[faucet]["daily_earnings"][0]
            yesterday = trends[faucet]["daily_earnings"][1] if periods > 1 else 0
            
            if yesterday > 0:
                trends[faucet]["growth_rate"] = ((today - yesterday) / yesterday) * 100
            else:
                trends[faucet]["growth_rate"] = 0 if today == 0 else 100
            
            # Average over all periods
            trends[faucet]["avg_daily_earnings"] = sum(trends[faucet]["daily_earnings"]) / periods
        
        return trends

    def check_performance_alerts(self, hours: int = 2) -> List[str]:
        """
        Check for significant drops in performance compared to historical averages.
        Returns a list of alert messages.
        """
        alerts = []
        recent_stats = self.get_faucet_stats(hours)
        historical_stats = self.get_trending_analysis(7)
        
        for faucet, stats in recent_stats.items():
            if stats['total'] < 2: continue # Not enough data for alert
            
            # 1. Success Rate Drop
            recent_sr = stats['success_rate']
            
            if recent_sr < 40:
                alerts.append(f"⚠️ LOW SUCCESS RATE: {faucet} is at {recent_sr:.0f}% over last {hours}h.")
            
            # 2. Earnings Drop
            recent_hourly = self.get_hourly_rate(faucet, hours).get(faucet, 0)
            hist_avg_hourly = historical_stats.get(faucet, {}).get('avg_daily_earnings', 0) / 24
            
            if hist_avg_hourly > 0 and recent_hourly < (hist_avg_hourly * 0.3):
                alerts.append(f"📉 EARNINGS DROP: {faucet} earnings are 70% below average.")
                
        return alerts

    def generate_automated_report(self, save_to_file: bool = True) -> str:
        """
        Generate a comprehensive automated daily report.
        
        Args:
            save_to_file: If True, also saves report to disk
            
        Returns:
            Report content as string
        """
        from datetime import datetime
        
        now = datetime.now()
        session = self.get_session_stats()
        faucet_stats = self.get_faucet_stats(24)
        hourly_rates = self.get_hourly_rate(hours=24)
        trends = self.get_trending_analysis(7)
        
        lines = [
            "╔══════════════════════════════════════════════════════╗",
            f"║       CRYPTOBOT DAILY REPORT - {now.strftime('%Y-%m-%d')}       ║",
            "╚══════════════════════════════════════════════════════╝",
            "",
            "📈 SESSION OVERVIEW",
            "─" * 50,
            f"  Runtime: {session['session_duration_hours']:.1f} hours",
            f"  Claims Attempted: {session['total_claims']}",
            f"  Success Rate: {session['success_rate']:.1f}%",
            "",
            "💰 EARNINGS BY CURRENCY",
            "─" * 50,
        ]
        
        total_value = 0
        for currency, amount in session["earnings_by_currency"].items():
            lines.append(f"  {currency}: {amount:.8f}")
        
        lines.extend([
            "",
            "🏆 TOP PERFORMING FAUCETS (by hourly rate)",
            "─" * 50,
        ])
        
        sorted_faucets = sorted(hourly_rates.items(), key=lambda x: x[1], reverse=True)
        for faucet, rate in sorted_faucets[:5]:
            stats = faucet_stats.get(faucet, {})
            success_rate = stats.get('success_rate', 0)
            trend = trends.get(faucet, {})
            growth = trend.get('growth_rate', 0)
            growth_emoji = "📈" if growth > 0 else "📉" if growth < 0 else "➡️"
            
            lines.append(f"  {faucet}: {rate:.4f}/hr | {success_rate:.0f}% success | {growth_emoji} {growth:+.1f}%")
        
        lines.extend([
            "",
            "⚠️  NEEDS ATTENTION (low success rate)",
            "─" * 50,
        ])
        
        low_performers = [
            (f, s) for f, s in faucet_stats.items() 
            if s.get('success_rate', 100) < 50 and s.get('total', 0) >= 3
        ]
        
        if low_performers:
            for faucet, stats in low_performers[:3]:
                lines.append(f"  {faucet}: {stats['success_rate']:.0f}% ({stats['success']}/{stats['total']})")
        else:
            lines.append("  None - all faucets performing well! ✅")
        
        lines.extend([
            "",
            "═" * 50,
            f"Report generated: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        ])
        
        report = "\n".join(lines)
        
        # Save to file
        if save_to_file:
            try:
                import os
                reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
                os.makedirs(reports_dir, exist_ok=True)
                
                filename = os.path.join(reports_dir, f"daily_report_{now.strftime('%Y%m%d')}.txt")
                with open(filename, "w") as f:
                    f.write(report)
                logger.info(f"📄 Daily report saved to {filename}")
            except Exception as e:
                logger.warning(f"Failed to save report: {e}")
        
        return report


        return report


class ProfitabilityOptimizer:
    """
    Analyzes earnings data to provide optimization recommendations for the bot.
    Suggests job priorities and identifies low-performing faucets/proxies.
    """
    
    def __init__(self, tracker: EarningsTracker):
        self.tracker = tracker

    def suggest_job_priorities(self) -> Dict[str, float]:
        """
        Calculates a priority multiplier for each faucet based on recent stability and earnings.
        Returns a mapping of faucet_name -> multiplier (0.5 to 2.0).
        """
        stats = self.tracker.get_faucet_stats(24)
        hourly_rates = self.tracker.get_hourly_rate(hours=24)
        
        priorities = {}
        for faucet, fstats in stats.items():
            # Success rate component (0.5 to 1.0)
            sr = fstats.get('success_rate', 50)
            sr_factor = max(0.5, sr / 100)
            
            # Earnings component (base 1.0, increases for top performers)
            rate = hourly_rates.get(faucet, 0)
            # Find max rate to normalize
            max_rate = max(hourly_rates.values()) if hourly_rates else 1
            rate_factor = 1.0 + (rate / max_rate) if max_rate > 0 else 1.0
            
            # Combine sr_factor and rate_factor
            priority = sr_factor * rate_factor
            priorities[faucet] = max(0.5, min(priority, 2.0))
            
        return priorities

    def get_underperforming_profiles(self, threshold_sr: float = 30.0) -> List[str]:
        """Identifies profiles/faucets that are consistently failing."""
        stats = self.tracker.get_faucet_stats(48)
        return [f for f, s in stats.items() if s['success_rate'] < threshold_sr and s['total'] >= 5]


# Global tracker instance
_tracker = None

def get_tracker() -> EarningsTracker:
    """Get or create the global earnings tracker."""
    global _tracker
    if _tracker is None:
        _tracker = EarningsTracker()
    return _tracker

