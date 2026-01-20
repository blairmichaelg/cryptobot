"""
Earnings Analytics Module

Tracks and reports profitability metrics for the cryptobot.
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)

# Analytics data file path
ANALYTICS_FILE = os.path.join(os.path.dirname(__file__), "..", "earnings_analytics.json")


@dataclass
class ClaimRecord:
    """Record of a single claim attempt."""
    timestamp: float
    faucet: str
    success: bool
    amount: float = 0.0
    currency: str = "unknown"
    balance_after: float = 0.0


class EarningsTracker:
    """
    Tracks earnings, claim success rates, and profitability metrics.
    Persists data to disk for historical analysis.
    """
    
    def __init__(self):
        self.claims: list = []
        self.session_start = time.time()
        self._load()
    
    def _load(self):
        """Load existing analytics data from disk."""
        try:
            if os.path.exists(ANALYTICS_FILE):
                with open(ANALYTICS_FILE, "r") as f:
                    data = json.load(f)
                    self.claims = data.get("claims", [])
                    logger.info(f"📊 Loaded {len(self.claims)} historical claims")
        except Exception as e:
            logger.warning(f"Could not load analytics: {e}")
            self.claims = []
    
    def _save(self):
        """Persist analytics data to disk."""
        try:
            data = {
                "claims": self.claims[-1000:],  # Keep last 1000 claims
                "last_updated": time.time()
            }
            with open(ANALYTICS_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Could not save analytics: {e}")
    
    def record_claim(self, faucet: str, success: bool, amount: float = 0.0, 
                     currency: str = "unknown", balance_after: float = 0.0):
        """
        Record a claim attempt.
        
        Args:
            faucet: Name of the faucet
            success: Whether the claim succeeded
            amount: Amount claimed
            currency: Currency code (BTC, LTC, DOGE, etc.)
            balance_after: Balance after the claim
        """
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
        
        # Save periodically (every 10 claims)
        if len(self.claims) % 10 == 0:
            self._save()
    
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
        
        Args:
            periods: Number of 24-hour periods to analyze
            
        Returns:
            Dict with trend data for each faucet
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


# Global tracker instance
_tracker = None

def get_tracker() -> EarningsTracker:
    """Get or create the global earnings tracker."""
    global _tracker
    if _tracker is None:
        _tracker = EarningsTracker()
    return _tracker

