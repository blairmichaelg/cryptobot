"""
Earnings Analytics Module

Tracks and reports profitability metrics for the cryptobot.
"""

import json
import os
import time
import logging
import aiohttp
from datetime import datetime
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
    
    # Decimal places for each currency (for converting from smallest unit)
    CURRENCY_DECIMALS = {
        "BTC": 8,     # 100,000,000 satoshi = 1 BTC
        "LTC": 8,     # 100,000,000 litoshi = 1 LTC
        "DOGE": 8,    # 100,000,000 units = 1 DOGE
        "BCH": 8,     # 100,000,000 satoshi = 1 BCH
        "TRX": 6,     # 1,000,000 sun = 1 TRX
        "ETH": 18,    # 1,000,000,000,000,000,000 wei = 1 ETH
        "BNB": 18,    # 1e18 units = 1 BNB
        "SOL": 9,     # 1,000,000,000 lamports = 1 SOL
        "TON": 9,     # 1,000,000,000 nanoton = 1 TON
        "DASH": 8,    # 100,000,000 duffs = 1 DASH
        "POLYGON": 18, # 1e18 units = 1 MATIC
        "USDT": 6     # 1,000,000 units = 1 USDT (varies by chain, using common)
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
            amount: Amount in smallest unit (satoshi for BTC, wei for ETH, etc.)
            currency: Currency code
            
        Returns:
            USD value
        """
        currency = currency.upper()
        price = await self.get_price(currency)
        
        if not price:
            return 0.0
        
        # Get decimal places for this currency
        decimals = self.CURRENCY_DECIMALS.get(currency, 8)  # Default to 8 if unknown
        divisor = 10 ** decimals
        
        coin_amount = amount / divisor
        return coin_amount * price


def get_price_feed() -> CryptoPriceFeed:
    """Get or create the global price feed."""
    if not hasattr(get_price_feed, "instance"):
        get_price_feed.instance = CryptoPriceFeed()
    return get_price_feed.instance


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
    Persists data to disk for historical analysis with auto-flush capability.
    """
    
    # Auto-flush interval (5 minutes)
    AUTO_FLUSH_INTERVAL = 300
    
    def __init__(self, storage_file: Optional[str] = None):
        self.storage_file = storage_file or ANALYTICS_FILE
        self.claims: list = []
        self.costs: list = []  # Fix #27: Track costs
        self.session_start = time.time()
        self.last_flush_time = time.time()  # Track last auto-flush
        
        # Ensure file exists and is writable
        if not os.path.exists(ANALYTICS_FILE):
            self._save()
             
        self._load()

    def _safe_json_write(self, filepath: str, data: dict, max_backups: int = 3):
        """Atomic JSON write with corruption protection and backups."""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            if os.path.exists(filepath):
                backup_base = filepath + ".backup"
                for i in range(max_backups - 1, 0, -1):
                    old = f"{backup_base}.{i}"
                    new = f"{backup_base}.{i+1}"
                    if os.path.exists(old):
                        os.replace(old, new)
                os.replace(filepath, f"{backup_base}.1")

            temp_file = filepath + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with open(temp_file, "r", encoding="utf-8") as f:
                json.load(f)
            os.replace(temp_file, filepath)
        except Exception as e:
            logger.warning(f"Could not safely write analytics: {e}")

    def _safe_json_read(self, filepath: str, max_backups: int = 3) -> Optional[dict]:
        """Read JSON with fallback to backups if corrupted."""
        paths = [filepath] + [f"{filepath}.backup.{i}" for i in range(1, max_backups + 1)]
        for path in paths:
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        return None
    
    def _load(self):
        """Load existing analytics data from disk."""
        try:
            data = self._safe_json_read(self.storage_file)
            if data:
                self.claims = data.get("claims", [])
                self.costs = data.get("costs", [])
                logger.info(f"📊 Loaded {len(self.claims)} claims and {len(self.costs)} costs.")
        except Exception as e:
            logger.warning(f"Could not load analytics: {e}")
            self.claims = []
            self.costs = []
    
    def _save(self):
        """Persist analytics data to disk."""
        try:
            data = {
                "claims": self.claims[-2000:],  # Increased limit
                "costs": self.costs[-1000:],
                "last_updated": time.time()
            }
            self._safe_json_write(self.storage_file, data)
            self.last_flush_time = time.time()
            logger.debug(f"📊 Analytics flushed: {len(self.claims)} claims, {len(self.costs)} costs")
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
        
        # Auto-flush if interval exceeded (5 minutes)
        if time.time() - self.last_flush_time > self.AUTO_FLUSH_INTERVAL:
            logger.info("💾 Auto-flushing analytics (interval exceeded)")
            self._save()
        else:
            # Regular save (on every claim for data protection)
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

    def record_runtime_cost(self, faucet: str, duration_seconds: float, time_cost_per_hour: float, proxy_cost_per_hour: float, proxy_used: bool = False):
        """Record time/proxy costs associated with a faucet runtime."""
        hours = max(duration_seconds, 0.0) / 3600.0
        if time_cost_per_hour > 0:
            self.record_cost("time", hours * time_cost_per_hour, faucet=faucet)
        if proxy_used and proxy_cost_per_hour > 0:
            self.record_cost("proxy", hours * proxy_cost_per_hour, faucet=faucet)

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
        
        # Convert to USD using concurrent price fetching
        total_earnings_usd = 0.0
        try:
            # Use existing event loop if available
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No event loop - create one
            loop = None
        
        async def _convert_all():
            """Convert all currencies to USD concurrently."""
            tasks = []
            for currency, amount in earnings_by_currency.items():
                tasks.append(price_feed.convert_to_usd(amount, currency))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total = 0.0
            for result in results:
                if isinstance(result, Exception):
                    logger.debug(f"Currency conversion failed: {result}")
                elif result is not None:
                    total += result
            return total
        
        if loop and loop.is_running():
            # Already in async context - create task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _convert_all())
                total_earnings_usd = future.result()
        else:
            # Run in new event loop
            total_earnings_usd = asyncio.run(_convert_all())
        
        total_costs = sum(cost['amount_usd'] for cost in self.costs if cost['timestamp'] >= cutoff)
        
        return {
            "earnings_usd": total_earnings_usd,
            "costs_usd": total_costs,
            "net_profit_usd": total_earnings_usd - total_costs,
            "roi": (total_earnings_usd / total_costs) if total_costs > 0 else 0
        }

    def get_faucet_profitability(self, faucet: str, days: int = 7) -> dict:
        """
        Calculate ROI metrics for a faucet over last N days.
        
        Returns:
            {
                "total_earned_usd": float,
                "total_cost_usd": float,
                "net_profit_usd": float,
                "roi_percentage": float,
                "avg_earnings_per_claim": float,
                "claim_count": int,
                "profitability_score": float  # 0-100+
            }
        """
        import asyncio
        
        hours = days * 24
        cutoff = time.time() - (hours * 3600)
        now = time.time()
        
        # Get all claims for this faucet within time window
        faucet_claims = [
            c for c in self.claims
            if c.get("faucet") == faucet and c.get("timestamp", 0) >= cutoff
        ]
        
        # Get costs for this faucet
        faucet_costs = [
            cost for cost in self.costs
            if cost.get("faucet") == faucet and cost.get("timestamp", 0) >= cutoff
        ]
        
        # Calculate metrics
        claim_count = len(faucet_claims)
        success_count = sum(1 for c in faucet_claims if c.get("success"))
        
        # Count captcha failures (failed claims with costs)
        captcha_failures = len([c for c in faucet_claims if not c.get("success")])
        
        # Calculate earnings with time-decay weighting
        earnings_by_currency = defaultdict(lambda: {"amount": 0.0, "weighted_amount": 0.0})
        for c in faucet_claims:
            if c.get("success"):
                currency = c.get("currency")
                amount = c.get("amount", 0.0)
                timestamp = c.get("timestamp", 0)
                
                # Time decay: recent claims weighted higher (exponential decay)
                # Formula: weight = e^(-0.1 * days_ago)
                days_ago = (now - timestamp) / 86400
                time_weight = 2.71828 ** (-0.1 * days_ago)  # e^(-0.1 * days_ago)
                
                earnings_by_currency[currency]["amount"] += amount
                earnings_by_currency[currency]["weighted_amount"] += amount * time_weight
        
        # Convert to USD
        price_feed = get_price_feed()
        
        async def _convert_to_usd():
            total_usd = 0.0
            weighted_usd = 0.0
            for currency, data in earnings_by_currency.items():
                price = await price_feed.get_price(currency)
                if price:
                    decimals = price_feed.CURRENCY_DECIMALS.get(currency.upper(), 8)
                    coin_amount = data["amount"] / (10 ** decimals)
                    weighted_coin_amount = data["weighted_amount"] / (10 ** decimals)
                    total_usd += coin_amount * price
                    weighted_usd += weighted_coin_amount * price
            return total_usd, weighted_usd
        
        # Run async conversion
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                total_earned_usd, weighted_earned_usd = executor.submit(asyncio.run, _convert_to_usd()).result()
        else:
            total_earned_usd, weighted_earned_usd = asyncio.run(_convert_to_usd())
        
        # Calculate total costs
        total_cost_usd = sum(cost.get("amount_usd", 0.0) for cost in faucet_costs)
        cost_breakdown = defaultdict(float)
        for cost in faucet_costs:
            cost_breakdown[cost.get("type", "unknown")] += cost.get("amount_usd", 0.0)
        
        # Calculate metrics
        net_profit_usd = total_earned_usd - total_cost_usd
        roi_percentage = (net_profit_usd / total_cost_usd * 100) if total_cost_usd > 0 else 0.0
        avg_earnings_per_claim = total_earned_usd / success_count if success_count > 0 else 0.0
        
        # Calculate profitability score (0-100+)
        # Base score: ROI percentage capped at 100
        base_score = min(roi_percentage, 100) if roi_percentage > 0 else roi_percentage
        
        # Success rate bonus: +20 points for >80% success rate
        success_rate = (success_count / claim_count * 100) if claim_count > 0 else 0
        success_bonus = 0
        if success_rate > 80:
            success_bonus = 20
        elif success_rate > 60:
            success_bonus = 10
        elif success_rate > 40:
            success_bonus = 5
        
        # Captcha failure penalty: -5 points per 10% failure rate
        captcha_failure_rate = (captcha_failures / claim_count * 100) if claim_count > 0 else 0
        captcha_penalty = -(captcha_failure_rate / 10) * 5
        
        # Time-decay factor: use weighted earnings for more recent performance
        # If weighted earnings are significantly higher than total, boost score
        time_decay_bonus = 0
        if total_earned_usd > 0:
            weighted_ratio = weighted_earned_usd / total_earned_usd
            if weighted_ratio > 1.2:  # Recent performance is 20% better
                time_decay_bonus = 10
            elif weighted_ratio > 1.1:
                time_decay_bonus = 5
        
        profitability_score = base_score + success_bonus + captcha_penalty + time_decay_bonus
        
        return {
            "total_earned_usd": total_earned_usd,
            "total_cost_usd": total_cost_usd,
            "cost_breakdown_usd": dict(cost_breakdown),
            "net_profit_usd": net_profit_usd,
            "roi_percentage": roi_percentage,
            "avg_earnings_per_claim": avg_earnings_per_claim,
            "claim_count": claim_count,
            "success_count": success_count,
            "success_rate": success_rate,
            "captcha_failure_rate": captcha_failure_rate,
            "profitability_score": profitability_score,
            "time_weighted_earnings_usd": weighted_earned_usd
        }

    def get_hourly_roi(self, faucet: Optional[str] = None, days: int = 7) -> Dict[str, Dict[int, float]]:
        """
        Calculate ROI percentage by hour-of-day for each faucet.

        Returns:
            Dict mapping faucet -> {hour: roi_percentage}
        """
        import asyncio
        cutoff = time.time() - (days * 24 * 3600)
        claims = [c for c in self.claims if c.get("timestamp", 0) >= cutoff]
        costs = [c for c in self.costs if c.get("timestamp", 0) >= cutoff]

        if faucet:
            claims = [c for c in claims if c.get("faucet") == faucet]
            costs = [c for c in costs if c.get("faucet") == faucet]

        earnings_by_faucet_hour: Dict[str, Dict[int, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        costs_by_faucet_hour: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))

        # Aggregate earnings by faucet and hour
        for c in claims:
            if not c.get("success"):
                continue
            ts = c.get("timestamp", 0)
            hour = datetime.utcfromtimestamp(ts).hour
            f = c.get("faucet")
            currency = c.get("currency")
            if currency:
                earnings_by_faucet_hour[f][hour][currency] += c.get("amount", 0.0)

        # Aggregate costs by faucet and hour
        for cost in costs:
            ts = cost.get("timestamp", 0)
            hour = datetime.utcfromtimestamp(ts).hour
            f = cost.get("faucet") or "global"
            costs_by_faucet_hour[f][hour] += cost.get("amount_usd", 0.0)

        # Convert earnings to USD by faucet/hour
        price_feed = get_price_feed()

        async def _convert_earnings_to_usd():
            converted = defaultdict(lambda: defaultdict(float))
            for f, hours in earnings_by_faucet_hour.items():
                for hour, amount in hours.items():
                    for currency, raw_amount in amount.items():
                        price = await price_feed.get_price(currency)
                        if not price:
                            continue
                        decimals = price_feed.CURRENCY_DECIMALS.get(currency.upper(), 8)
                        converted[f][hour] += (raw_amount / (10 ** decimals)) * price
            return converted

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                earnings_usd = executor.submit(asyncio.run, _convert_earnings_to_usd()).result()
        else:
            earnings_usd = asyncio.run(_convert_earnings_to_usd())

        hourly_roi: Dict[str, Dict[int, float]] = defaultdict(dict)
        for f, hours in earnings_usd.items():
            for hour, earned in hours.items():
                cost = costs_by_faucet_hour.get(f, {}).get(hour, 0.0)
                if cost <= 0:
                    continue
                net = earned - cost
                hourly_roi[f][hour] = (net / cost) * 100

        return dict(hourly_roi)
    
    def get_profitability_report(self, days: int = 7, min_claims: int = 3) -> List[Dict[str, Any]]:
        """
        Generate a ranked list of faucets by profitability.
        
        Args:
            days: Number of days to analyze
            min_claims: Minimum number of claims required to include faucet
            
        Returns:
            List of faucet profitability dicts, sorted by profitability_score (highest first)
        """
        # Get all unique faucets that have claims
        cutoff = time.time() - (days * 24 * 3600)
        faucets = set(
            c.get("faucet") for c in self.claims
            if c.get("timestamp", 0) >= cutoff and c.get("faucet")
        )
        
        # Calculate profitability for each faucet
        report = []
        for faucet in faucets:
            try:
                metrics = self.get_faucet_profitability(faucet, days)
                
                # Skip if not enough data
                if metrics["claim_count"] < min_claims:
                    continue
                
                report.append({
                    "faucet": faucet,
                    **metrics
                })
            except Exception as e:
                logger.warning(f"Failed to calculate profitability for {faucet}: {e}")
        
        # Sort by profitability score (highest first)
        report.sort(key=lambda x: x["profitability_score"], reverse=True)
        
        return report
    
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
            "EARNINGS SUMMARY (Last 24 Hours)",
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
    
    def get_captcha_costs_since(self, since: datetime) -> float:
        """
        Get total captcha costs since a specific datetime.
        
        Args:
            since: DateTime to start counting from
            
        Returns:
            Total cost in USD
        """
        cutoff = since.timestamp()
        total = sum(
            cost['amount_usd'] for cost in self.costs
            if cost.get('timestamp', 0) >= cutoff and cost.get('type', '').startswith('captcha')
        )
        return total
    
    def get_stats_since(self, since: datetime) -> Dict[str, Any]:
        """
        Get claim statistics since a specific datetime.
        
        Args:
            since: DateTime to start counting from
            
        Returns:
            Dict with total_claims, successes, failures
        """
        cutoff = since.timestamp()
        recent_claims = [c for c in self.claims if c.get('timestamp', 0) >= cutoff]
        
        total = len(recent_claims)
        successes = sum(1 for c in recent_claims if c.get('success'))
        failures = total - successes
        
        return {
            "total_claims": total,
            "successes": successes,
            "failures": failures,
            "success_rate": (successes / total * 100) if total > 0 else 0
        }

    def generate_automated_report(self, save_to_file: bool = True) -> str:
        """
        Generate a comprehensive automated daily report.
        
        Args:
            save_to_file: If True, also saves report to disk
            
        Returns:
            Report content as string
        """
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
                reports_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
                os.makedirs(reports_dir, exist_ok=True)
                
                filename = os.path.join(reports_dir, f"daily_report_{now.strftime('%Y%m%d')}.txt")
                with open(filename, "w") as f:
                    f.write(report)
                logger.info(f"📄 Daily report saved to {filename}")
            except Exception as e:
                logger.warning(f"Failed to save report: {e}")
        
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


def get_tracker() -> EarningsTracker:
    """Get or create the global earnings tracker."""
    if not hasattr(get_tracker, "instance"):
        get_tracker.instance = EarningsTracker()
    return get_tracker.instance

