"""
Withdrawal Analytics Module

Tracks withdrawal performance and optimizes profitability over time.
Provides data-driven insights to continuously improve withdrawal strategies.
"""

import sqlite3
import logging
import time
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)

# Database file path
DB_FILE = os.path.join(os.path.dirname(__file__), "..", "withdrawal_analytics.db")


class WithdrawalMethod(Enum):
    """Withdrawal methods supported."""
    FAUCETPAY = "faucetpay"
    DIRECT = "direct"
    WALLET_DAEMON = "wallet_daemon"


class WithdrawalStatus(Enum):
    """Status of withdrawal transactions."""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class WithdrawalRecord:
    """Record of a single withdrawal transaction."""
    timestamp: float
    faucet: str
    cryptocurrency: str
    amount: float
    network_fee: float
    platform_fee: float
    withdrawal_method: str
    status: str
    balance_before: float = 0.0
    balance_after: float = 0.0
    tx_id: Optional[str] = None
    notes: Optional[str] = None


class WithdrawalAnalytics:
    """
    Tracks withdrawal performance and provides profitability insights.
    
    Core functionality:
    - Records withdrawal transactions to SQLite database
    - Calculates effective earning rates after fees
    - Recommends optimal withdrawal strategies
    - Generates performance reports
    """
    
    def __init__(self, db_path: str = DB_FILE):
        """
        Initialize the WithdrawalAnalytics system.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_database()
        logger.info(f"WithdrawalAnalytics initialized with database: {db_path}")
    
    def _init_database(self):
        """Create database schema if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    faucet TEXT NOT NULL,
                    cryptocurrency TEXT NOT NULL,
                    amount REAL NOT NULL,
                    network_fee REAL DEFAULT 0.0,
                    platform_fee REAL DEFAULT 0.0,
                    withdrawal_method TEXT NOT NULL,
                    status TEXT NOT NULL,
                    balance_before REAL DEFAULT 0.0,
                    balance_after REAL DEFAULT 0.0,
                    tx_id TEXT,
                    notes TEXT
                )
            """)
            
            # Create indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON withdrawals(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_faucet 
                ON withdrawals(faucet)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_crypto 
                ON withdrawals(cryptocurrency)
            """)
            
            conn.commit()
            conn.close()
            logger.info("Withdrawal analytics database schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def record_withdrawal(
        self,
        faucet: str,
        cryptocurrency: str,
        amount: float,
        network_fee: float = 0.0,
        platform_fee: float = 0.0,
        withdrawal_method: str = "faucetpay",
        status: str = "success",
        balance_before: float = 0.0,
        balance_after: float = 0.0,
        tx_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> int:
        """
        Record a withdrawal transaction.
        
        Args:
            faucet: Name of the faucet (e.g., "FreeBitcoin", "Cointiply")
            cryptocurrency: Crypto symbol (e.g., "BTC", "LTC", "DOGE")
            amount: Amount withdrawn (in crypto units)
            network_fee: Network transaction fee paid
            platform_fee: Platform/service fee paid
            withdrawal_method: Method used (faucetpay, direct, wallet_daemon)
            status: Transaction status (success, failed, pending)
            balance_before: Balance before withdrawal
            balance_after: Balance after withdrawal
            tx_id: Transaction ID from blockchain
            notes: Additional notes or error messages
            
        Returns:
            Record ID from database
        """
        record = WithdrawalRecord(
            timestamp=time.time(),
            faucet=faucet,
            cryptocurrency=cryptocurrency.upper(),
            amount=amount,
            network_fee=network_fee,
            platform_fee=platform_fee,
            withdrawal_method=withdrawal_method,
            status=status,
            balance_before=balance_before,
            balance_after=balance_after,
            tx_id=tx_id,
            notes=notes
        )
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO withdrawals (
                    timestamp, faucet, cryptocurrency, amount,
                    network_fee, platform_fee, withdrawal_method, status,
                    balance_before, balance_after, tx_id, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.timestamp, record.faucet, record.cryptocurrency,
                record.amount, record.network_fee, record.platform_fee,
                record.withdrawal_method, record.status,
                record.balance_before, record.balance_after,
                record.tx_id, record.notes
            ))
            
            record_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            total_fee = network_fee + platform_fee
            net_amount = amount - total_fee
            logger.info(
                f"Withdrawal recorded: {faucet} | {amount:.8f} {cryptocurrency} | "
                f"Fees: {total_fee:.8f} | Net: {net_amount:.8f} | {status}"
            )
            
            return record_id
        except Exception as e:
            logger.error(f"Failed to record withdrawal: {e}")
            raise
    
    def calculate_effective_rate(
        self,
        faucet: Optional[str] = None,
        cryptocurrency: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, float]:
        """
        Calculate net earning rate after fees.
        
        Computes the actual profit per hour considering all fees.
        
        Args:
            faucet: Optional filter by specific faucet
            cryptocurrency: Optional filter by specific crypto
            hours: Time period to analyze (default 24 hours)
            
        Returns:
            Dict with metrics: total_earned, total_fees, net_profit, hourly_rate
        """
        cutoff = time.time() - (hours * 3600)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    SUM(amount) as total_earned,
                    SUM(network_fee + platform_fee) as total_fees
                FROM withdrawals
                WHERE timestamp >= ? AND status = ?
            """
            params = [cutoff, "success"]
            
            if faucet:
                query += " AND faucet = ?"
                params.append(faucet)
            
            if cryptocurrency:
                query += " AND cryptocurrency = ?"
                params.append(cryptocurrency.upper())
            
            cursor.execute(query, params)
            row = cursor.fetchone()
            conn.close()
            
            total_earned = row[0] or 0.0
            total_fees = row[1] or 0.0
            net_profit = total_earned - total_fees
            hourly_rate = net_profit / max(hours, 1)
            
            return {
                "total_earned": total_earned,
                "total_fees": total_fees,
                "net_profit": net_profit,
                "hourly_rate": hourly_rate,
                "fee_percentage": (total_fees / total_earned * 100) if total_earned > 0 else 0
            }
        except Exception as e:
            logger.error(f"Failed to calculate effective rate: {e}")
            return {
                "total_earned": 0.0,
                "total_fees": 0.0,
                "net_profit": 0.0,
                "hourly_rate": 0.0,
                "fee_percentage": 0.0
            }
    
    def get_faucet_performance(self, hours: int = 168) -> Dict[str, Dict]:
        """
        Get per-faucet performance statistics.
        
        Args:
            hours: Analysis period in hours (default 168 = 1 week)
            
        Returns:
            Dict mapping faucet names to their performance metrics
        """
        cutoff = time.time() - (hours * 3600)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    faucet,
                    COUNT(*) as total_withdrawals,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                    SUM(amount) as total_amount,
                    SUM(network_fee + platform_fee) as total_fees,
                    AVG(network_fee + platform_fee) as avg_fee
                FROM withdrawals
                WHERE timestamp >= ?
                GROUP BY faucet
            """, (cutoff,))
            
            results = {}
            for row in cursor.fetchall():
                faucet = row[0]
                total = row[1]
                successful = row[2]
                total_amount = row[3] or 0.0
                total_fees = row[4] or 0.0
                avg_fee = row[5] or 0.0
                
                results[faucet] = {
                    "total_withdrawals": total,
                    "successful_withdrawals": successful,
                    "success_rate": (successful / total * 100) if total > 0 else 0,
                    "total_earned": total_amount,
                    "total_fees": total_fees,
                    "net_profit": total_amount - total_fees,
                    "avg_fee": avg_fee,
                    "fee_percentage": (total_fees / total_amount * 100) if total_amount > 0 else 0
                }
            
            conn.close()
            return results
        except Exception as e:
            logger.error(f"Failed to get faucet performance: {e}")
            return {}
    
    def recommend_withdrawal_strategy(
        self,
        current_balance: float,
        cryptocurrency: str,
        faucet: str
    ) -> Dict[str, Any]:
        """
        Recommend optimal withdrawal strategy based on historical data.
        
        Uses ML/rule-based logic to determine:
        - Whether to withdraw now or wait
        - Optimal withdrawal method (FaucetPay vs Direct)
        - Recommended timing (off-peak hours for lower fees)
        
        Args:
            current_balance: Current balance in the faucet
            cryptocurrency: Crypto symbol
            faucet: Faucet name
            
        Returns:
            Dict with recommendation and reasoning
        """
        # Get historical performance for this faucet
        performance = self.get_faucet_performance(hours=168)  # 1 week
        faucet_stats = performance.get(faucet, {})
        
        # Get average fees for this crypto
        avg_fee = faucet_stats.get("avg_fee", 0.0)
        fee_percentage = faucet_stats.get("fee_percentage", 5.0)
        
        # Determine optimal method based on balance size (FaucetPay for small, Direct for large)
        optimal_method = "direct" if current_balance >= 0.001 else "faucetpay"
        
        recommendation = {
            "action": "wait",
            "reason": "Insufficient data",
            "optimal_method": optimal_method,
            "estimated_fee": avg_fee,
            "optimal_timing": "now"
        }
        
        # Rule 1: Balance threshold (avoid tiny withdrawals with high fee %)
        min_threshold = avg_fee * 20 if avg_fee > 0 else 0.0001
        
        if current_balance < min_threshold:
            recommendation["action"] = "wait"
            recommendation["reason"] = f"Balance too low. Wait until {min_threshold:.8f} {cryptocurrency} to minimize fee impact"
            return recommendation
        
        # Rule 2: Fee percentage analysis
        estimated_fee_pct = (avg_fee / current_balance * 100) if current_balance > 0 else 100
        
        if estimated_fee_pct > 10:
            recommendation["action"] = "wait"
            recommendation["reason"] = f"Estimated fee ({estimated_fee_pct:.1f}%) too high. Accumulate more before withdrawing"
            return recommendation
        
        # Rule 3: Check if off-peak hours (lower network fees)
        now = datetime.now(timezone.utc)
        hour = now.hour
        is_off_peak = hour >= 22 or hour < 5
        
        if not is_off_peak:
            recommendation["action"] = "wait"
            recommendation["reason"] = "Wait for off-peak hours (22:00-05:00 UTC) for lower network fees"
            recommendation["optimal_timing"] = "off-peak"
            return recommendation
        
        # All checks passed - recommend withdrawal
        recommendation["action"] = "withdraw"
        recommendation["reason"] = f"Optimal conditions: balance sufficient, low fee impact ({estimated_fee_pct:.1f}%), off-peak hours"
        
        return recommendation
    
    def generate_report(
        self,
        period: str = "daily",
        cryptocurrency: Optional[str] = None
    ) -> str:
        """
        Generate withdrawal performance report.
        
        Args:
            period: Report period ("daily", "weekly", "monthly")
            cryptocurrency: Optional filter by crypto
            
        Returns:
            Formatted report string
        """
        # Determine time window
        period_hours = {
            "daily": 24,
            "weekly": 168,
            "monthly": 720
        }
        hours = period_hours.get(period, 24)
        
        # Get overall metrics
        overall = self.calculate_effective_rate(cryptocurrency=cryptocurrency, hours=hours)
        
        # Get per-faucet breakdown
        faucet_stats = self.get_faucet_performance(hours=hours)
        
        # Filter by cryptocurrency if specified
        if cryptocurrency:
            crypto_filter = cryptocurrency.upper()
            faucet_stats = {
                k: v for k, v in faucet_stats.items()
                if self._faucet_uses_crypto(k, crypto_filter, hours)
            }
        
        # Build report
        lines = [
            "=" * 60,
            f"WITHDRAWAL ANALYTICS REPORT ({period.upper()})",
            "=" * 60,
            "",
            "OVERALL PERFORMANCE",
            "-" * 60,
            f"Total Earned:     {overall['total_earned']:.8f}",
            f"Total Fees:       {overall['total_fees']:.8f}",
            f"Net Profit:       {overall['net_profit']:.8f}",
            f"Fee Percentage:   {overall['fee_percentage']:.2f}%",
            f"Hourly Rate:      {overall['hourly_rate']:.8f}",
            "",
            "PER-FAUCET BREAKDOWN",
            "-" * 60,
        ]
        
        # Sort faucets by net profit (best first)
        sorted_faucets = sorted(
            faucet_stats.items(),
            key=lambda x: x[1].get("net_profit", 0),
            reverse=True
        )
        
        for faucet, stats in sorted_faucets:
            lines.append(f"\n{faucet}:")
            lines.append(f"  Withdrawals:    {stats['successful_withdrawals']}/{stats['total_withdrawals']}")
            lines.append(f"  Success Rate:   {stats['success_rate']:.1f}%")
            lines.append(f"  Total Earned:   {stats['total_earned']:.8f}")
            lines.append(f"  Total Fees:     {stats['total_fees']:.8f}")
            lines.append(f"  Net Profit:     {stats['net_profit']:.8f}")
            lines.append(f"  Fee %:          {stats['fee_percentage']:.2f}%")
        
        # Best and worst performers
        if sorted_faucets:
            lines.extend([
                "",
                "BEST PERFORMER",
                "-" * 60,
                f"{sorted_faucets[0][0]}: {sorted_faucets[0][1]['net_profit']:.8f} net profit",
            ])
            
            if len(sorted_faucets) > 1:
                lines.extend([
                    "",
                    "WORST PERFORMER",
                    "-" * 60,
                    f"{sorted_faucets[-1][0]}: {sorted_faucets[-1][1]['net_profit']:.8f} net profit",
                ])
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _faucet_uses_crypto(self, faucet: str, cryptocurrency: str, hours: int) -> bool:
        """Check if a faucet has withdrawals for a specific cryptocurrency."""
        cutoff = time.time() - (hours * 3600)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) FROM withdrawals
                WHERE faucet = ? AND cryptocurrency = ? AND timestamp >= ?
            """, (faucet, cryptocurrency, cutoff))
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
        except Exception as e:
            logger.error(f"Failed to check crypto usage: {e}")
            return False
    
    def get_withdrawal_history(
        self,
        limit: int = 100,
        faucet: Optional[str] = None,
        cryptocurrency: Optional[str] = None
    ) -> List[Dict]:
        """
        Get withdrawal transaction history.
        
        Args:
            limit: Maximum number of records to return
            faucet: Optional filter by faucet
            cryptocurrency: Optional filter by crypto
            
        Returns:
            List of withdrawal records as dicts
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = "SELECT * FROM withdrawals WHERE 1=1"
            params = []
            
            if faucet:
                query += " AND faucet = ?"
                params.append(faucet)
            
            if cryptocurrency:
                query += " AND cryptocurrency = ?"
                params.append(cryptocurrency.upper())
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description]
            
            # Convert rows to dicts
            records = []
            for row in cursor.fetchall():
                records.append(dict(zip(columns, row)))
            
            conn.close()
            return records
        except Exception as e:
            logger.error(f"Failed to get withdrawal history: {e}")
            return []


# Global instance
_analytics = None


def get_analytics() -> WithdrawalAnalytics:
    """Get or create the global withdrawal analytics instance."""
    global _analytics
    if _analytics is None:
        _analytics = WithdrawalAnalytics()
    return _analytics
