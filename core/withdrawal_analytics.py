"""Withdrawal Analytics Module.

Tracks withdrawal performance and optimizes profitability over time.
Provides data-driven insights to continuously improve withdrawal
strategies.
"""

import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Database file path
DB_FILE = os.path.join(
    os.path.dirname(__file__), "..", "withdrawal_analytics.db"
)


class WithdrawalMethod(Enum):
    """Withdrawal methods supported by the platform."""

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
    """Tracks withdrawal performance and profitability.

    Core functionality:
    - Records withdrawal transactions to SQLite database
    - Calculates effective earning rates after fees
    - Recommends optimal withdrawal strategies
    - Generates performance reports
    """

    def __init__(self, db_path: str = DB_FILE) -> None:
        """Initialize the WithdrawalAnalytics system.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._init_database()
        logger.info(
            "WithdrawalAnalytics initialized with "
            "database: %s", db_path,
        )

    def _init_database(self) -> None:
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
            logger.info(
                "Withdrawal analytics database schema "
                "initialized"
            )
        except Exception as e:
            logger.error(
                "Failed to initialize database: %s", e
            )
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
        notes: Optional[str] = None,
    ) -> int:
        """Record a withdrawal transaction.

        Args:
            faucet: Name of the faucet
                (e.g. "FreeBitcoin", "Cointiply").
            cryptocurrency: Crypto symbol
                (e.g. "BTC", "LTC", "DOGE").
            amount: Amount withdrawn (in crypto units).
            network_fee: Network transaction fee paid.
            platform_fee: Platform/service fee paid.
            withdrawal_method: Method used
                (faucetpay, direct, wallet_daemon).
            status: Transaction status
                (success, failed, pending).
            balance_before: Balance before withdrawal.
            balance_after: Balance after withdrawal.
            tx_id: Transaction ID from blockchain.
            notes: Additional notes or error messages.

        Returns:
            Record ID from database.
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
            notes=notes,
        )

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO withdrawals (
                    timestamp, faucet, cryptocurrency,
                    amount, network_fee, platform_fee,
                    withdrawal_method, status,
                    balance_before, balance_after,
                    tx_id, notes
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                record.timestamp, record.faucet,
                record.cryptocurrency, record.amount,
                record.network_fee, record.platform_fee,
                record.withdrawal_method, record.status,
                record.balance_before,
                record.balance_after,
                record.tx_id, record.notes,
            ))

            record_id = cursor.lastrowid
            conn.commit()
            conn.close()

            total_fee = network_fee + platform_fee
            net_amount = amount - total_fee
            logger.info(
                "Withdrawal recorded: %s | %.8f %s | "
                "Fees: %.8f | Net: %.8f | %s",
                faucet, amount, cryptocurrency,
                total_fee, net_amount, status,
            )

            return record_id
        except Exception as e:
            logger.error(
                "Failed to record withdrawal: %s", e
            )
            raise

    def calculate_effective_rate(
        self,
        faucet: Optional[str] = None,
        cryptocurrency: Optional[str] = None,
        hours: int = 24,
    ) -> Dict[str, float]:
        """Calculate net earning rate after fees.

        Computes the actual profit per hour considering all
        fees.

        Args:
            faucet: Optional filter by specific faucet.
            cryptocurrency: Optional filter by specific crypto.
            hours: Time period to analyze (default 24 hours).

        Returns:
            Dict with metrics: total_earned, total_fees,
            net_profit, hourly_rate, fee_percentage.
        """
        cutoff = time.time() - (hours * 3600)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = """
                SELECT
                    SUM(amount) as total_earned,
                    SUM(network_fee + platform_fee)
                        as total_fees
                FROM withdrawals
                WHERE timestamp >= ? AND status = ?
            """
            params: List[Any] = [cutoff, "success"]

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
            fee_pct = (
                (total_fees / total_earned * 100)
                if total_earned > 0 else 0.0
            )

            return {
                "total_earned": total_earned,
                "total_fees": total_fees,
                "net_profit": net_profit,
                "hourly_rate": hourly_rate,
                "fee_percentage": fee_pct,
            }
        except Exception as e:
            logger.error(
                "Failed to calculate effective rate: %s", e
            )
            return {
                "total_earned": 0.0,
                "total_fees": 0.0,
                "net_profit": 0.0,
                "hourly_rate": 0.0,
                "fee_percentage": 0.0,
            }

    def get_faucet_performance(
        self, hours: int = 168
    ) -> Dict[str, Dict[str, Any]]:
        """Get per-faucet performance statistics.

        Args:
            hours: Analysis period in hours
                (default 168 = 1 week).

        Returns:
            Dict mapping faucet names to their performance
            metrics.
        """
        cutoff = time.time() - (hours * 3600)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    faucet,
                    COUNT(*) as total_withdrawals,
                    SUM(
                        CASE WHEN status = 'success'
                        THEN 1 ELSE 0 END
                    ) as successful,
                    SUM(amount) as total_amount,
                    SUM(network_fee + platform_fee)
                        as total_fees,
                    AVG(network_fee + platform_fee)
                        as avg_fee
                FROM withdrawals
                WHERE timestamp >= ?
                GROUP BY faucet
            """, (cutoff,))

            results: Dict[str, Dict[str, Any]] = {}
            for row in cursor.fetchall():
                faucet_name = row[0]
                total = row[1]
                successful = row[2]
                total_amount = row[3] or 0.0
                total_fees = row[4] or 0.0
                avg_fee = row[5] or 0.0

                success_rate = (
                    (successful / total * 100)
                    if total > 0 else 0.0
                )
                fee_pct = (
                    (total_fees / total_amount * 100)
                    if total_amount > 0 else 0.0
                )

                results[faucet_name] = {
                    "total_withdrawals": total,
                    "successful_withdrawals": successful,
                    "success_rate": success_rate,
                    "total_earned": total_amount,
                    "total_fees": total_fees,
                    "net_profit": total_amount - total_fees,
                    "avg_fee": avg_fee,
                    "fee_percentage": fee_pct,
                }

            conn.close()
            return results
        except Exception as e:
            logger.error(
                "Failed to get faucet performance: %s", e
            )
            return {}

    def recommend_withdrawal_strategy(
        self,
        current_balance: float,
        cryptocurrency: str,
        faucet: str,
    ) -> Dict[str, Any]:
        """Recommend optimal withdrawal strategy.

        Uses rule-based logic to determine:
        - Whether to withdraw now or wait
        - Optimal withdrawal method (FaucetPay vs Direct)
        - Recommended timing (off-peak for lower fees)

        Args:
            current_balance: Current balance in the faucet.
            cryptocurrency: Crypto symbol.
            faucet: Faucet name.

        Returns:
            Dict with recommendation and reasoning.
        """
        # Get historical performance for this faucet
        performance = self.get_faucet_performance(hours=168)
        faucet_stats = performance.get(faucet, {})

        # Get average fees for this crypto
        avg_fee = faucet_stats.get("avg_fee", 0.0)

        # Determine optimal method based on balance size
        optimal_method = (
            "direct"
            if current_balance >= 0.001
            else "faucetpay"
        )

        recommendation: Dict[str, Any] = {
            "action": "wait",
            "reason": "Insufficient data",
            "optimal_method": optimal_method,
            "estimated_fee": avg_fee,
            "optimal_timing": "now",
        }

        # Rule 1: Balance threshold
        min_threshold = (
            avg_fee * 20 if avg_fee > 0 else 0.0001
        )

        if current_balance < min_threshold:
            recommendation["action"] = "wait"
            recommendation["reason"] = (
                f"Balance too low. Wait until "
                f"{min_threshold:.8f} {cryptocurrency} "
                "to minimize fee impact"
            )
            return recommendation

        # Rule 2: Fee percentage analysis
        estimated_fee_pct = (
            (avg_fee / current_balance * 100)
            if current_balance > 0 else 100
        )

        if estimated_fee_pct > 10:
            recommendation["action"] = "wait"
            recommendation["reason"] = (
                f"Estimated fee ({estimated_fee_pct:.1f}%)"
                " too high. Accumulate more before "
                "withdrawing"
            )
            return recommendation

        # Rule 3: Check if off-peak hours
        now = datetime.now(timezone.utc)
        is_off_peak = now.hour >= 22 or now.hour < 5

        if not is_off_peak:
            recommendation["action"] = "wait"
            recommendation["reason"] = (
                "Wait for off-peak hours "
                "(22:00-05:00 UTC) for lower network fees"
            )
            recommendation["optimal_timing"] = "off-peak"
            return recommendation

        # All checks passed - recommend withdrawal
        recommendation["action"] = "withdraw"
        recommendation["reason"] = (
            "Optimal conditions: balance sufficient, "
            f"low fee impact ({estimated_fee_pct:.1f}%), "
            "off-peak hours"
        )

        return recommendation

    def generate_report(
        self,
        period: str = "daily",
        cryptocurrency: Optional[str] = None,
    ) -> str:
        """Generate withdrawal performance report.

        Args:
            period: Report period
                ("daily", "weekly", "monthly").
            cryptocurrency: Optional filter by crypto.

        Returns:
            Formatted report string.
        """
        # Determine time window
        period_hours = {
            "daily": 24,
            "weekly": 168,
            "monthly": 720,
        }
        hours = period_hours.get(period, 24)

        # Get overall metrics
        overall = self.calculate_effective_rate(
            cryptocurrency=cryptocurrency, hours=hours
        )

        # Get per-faucet breakdown
        faucet_stats = self.get_faucet_performance(
            hours=hours
        )

        # Filter by cryptocurrency if specified
        if cryptocurrency:
            crypto_filter = cryptocurrency.upper()
            faucet_stats = {
                k: v for k, v in faucet_stats.items()
                if self._faucet_uses_crypto(
                    k, crypto_filter, hours
                )
            }

        # Build report
        lines = [
            "=" * 60,
            f"WITHDRAWAL ANALYTICS REPORT "
            f"({period.upper()})",
            "=" * 60,
            "",
            "OVERALL PERFORMANCE",
            "-" * 60,
            f"Total Earned:     "
            f"{overall['total_earned']:.8f}",
            f"Total Fees:       "
            f"{overall['total_fees']:.8f}",
            f"Net Profit:       "
            f"{overall['net_profit']:.8f}",
            f"Fee Percentage:   "
            f"{overall['fee_percentage']:.2f}%",
            f"Hourly Rate:      "
            f"{overall['hourly_rate']:.8f}",
            "",
            "PER-FAUCET BREAKDOWN",
            "-" * 60,
        ]

        # Sort faucets by net profit (best first)
        sorted_faucets = sorted(
            faucet_stats.items(),
            key=lambda x: x[1].get("net_profit", 0),
            reverse=True,
        )

        for faucet_name, stats in sorted_faucets:
            success = stats["successful_withdrawals"]
            total = stats["total_withdrawals"]
            lines.append(f"\n{faucet_name}:")
            lines.append(
                f"  Withdrawals:    {success}/{total}"
            )
            lines.append(
                f"  Success Rate:   "
                f"{stats['success_rate']:.1f}%"
            )
            lines.append(
                f"  Total Earned:   "
                f"{stats['total_earned']:.8f}"
            )
            lines.append(
                f"  Total Fees:     "
                f"{stats['total_fees']:.8f}"
            )
            lines.append(
                f"  Net Profit:     "
                f"{stats['net_profit']:.8f}"
            )
            lines.append(
                f"  Fee %:          "
                f"{stats['fee_percentage']:.2f}%"
            )

        # Best and worst performers
        if sorted_faucets:
            best = sorted_faucets[0]
            lines.extend([
                "",
                "BEST PERFORMER",
                "-" * 60,
                f"{best[0]}: "
                f"{best[1]['net_profit']:.8f} net profit",
            ])

            if len(sorted_faucets) > 1:
                worst = sorted_faucets[-1]
                lines.extend([
                    "",
                    "WORST PERFORMER",
                    "-" * 60,
                    f"{worst[0]}: "
                    f"{worst[1]['net_profit']:.8f} "
                    "net profit",
                ])

        lines.append("=" * 60)

        return "\n".join(lines)

    def _faucet_uses_crypto(
        self,
        faucet: str,
        cryptocurrency: str,
        hours: int,
    ) -> bool:
        """Check if a faucet has withdrawals for a crypto.

        Args:
            faucet: Faucet name to check.
            cryptocurrency: Cryptocurrency symbol.
            hours: Lookback window in hours.

        Returns:
            True if the faucet has matching withdrawals.
        """
        cutoff = time.time() - (hours * 3600)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COUNT(*) FROM withdrawals
                WHERE faucet = ?
                    AND cryptocurrency = ?
                    AND timestamp >= ?
            """, (faucet, cryptocurrency, cutoff))

            count = cursor.fetchone()[0]
            conn.close()

            return count > 0
        except Exception as e:
            logger.error(
                "Failed to check crypto usage: %s", e
            )
            return False

    def get_withdrawal_history(
        self,
        limit: int = 100,
        faucet: Optional[str] = None,
        cryptocurrency: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get withdrawal transaction history.

        Args:
            limit: Maximum number of records to return.
            faucet: Optional filter by faucet.
            cryptocurrency: Optional filter by crypto.

        Returns:
            List of withdrawal records as dicts.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = "SELECT * FROM withdrawals WHERE 1=1"
            params: List[Any] = []

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
            columns = [
                desc[0] for desc in cursor.description
            ]

            # Convert rows to dicts
            records = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

            conn.close()
            return records
        except Exception as e:
            logger.error(
                "Failed to get withdrawal history: %s", e
            )
            return []


# Global instance
_analytics: Optional[WithdrawalAnalytics] = None


def get_analytics() -> WithdrawalAnalytics:
    """Get or create the global withdrawal analytics instance.

    Returns:
        The singleton WithdrawalAnalytics instance.
    """
    global _analytics
    if _analytics is None:
        _analytics = WithdrawalAnalytics()
    return _analytics
