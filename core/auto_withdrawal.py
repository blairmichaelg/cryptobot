"""Automated Withdrawal Orchestration.

Handles periodic balance checks and executes withdrawals during optimal
network fee windows. Integrates with both direct wallet and FaucetPay.
"""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AutoWithdrawal:
    """Automated withdrawal manager.

    Monitors faucet balances and executes withdrawals during optimal
    network fee conditions.
    """

    def __init__(
        self,
        wallet_daemon: Any,
        settings: Any,
        analytics_tracker: Any,
    ) -> None:
        """Initialize AutoWithdrawal.

        Args:
            wallet_daemon: WalletDaemon instance for blockchain operations.
            settings: BotSettings configuration.
            analytics_tracker: EarningsTracker instance for balance data.
        """
        self.wallet = wallet_daemon
        self.settings = settings
        self.tracker = analytics_tracker
        self.withdrawal_history: List[Dict[str, Any]] = []
        self.last_check_time: float = 0

    def _get_balances_by_currency(self) -> Dict[str, float]:
        """Extract current balances from analytics data.

        Returns:
            Dict mapping currency code to balance in smallest unit.
        """
        balances: Dict[str, float] = defaultdict(float)

        # Get all successful claims and sum by currency
        for claim in self.tracker.claims:
            if claim.get("success") and claim.get("balance_after", 0) > 0:
                currency = claim.get("currency", "unknown").upper()
                # Use the most recent balance_after for each currency
                balances[currency] = max(
                    balances[currency],
                    claim.get("balance_after", 0),
                )

        return dict(balances)

    def _get_withdrawal_address(self, currency: str) -> Optional[str]:
        """Get withdrawal address for currency.

        Checks FaucetPay and direct wallet configurations.

        Args:
            currency: Currency code (BTC, LTC, DOGE, etc.).

        Returns:
            Withdrawal address string, or ``None`` if not configured.
        """
        currency = currency.upper()

        prefer_wallet = getattr(
            self.settings, "prefer_wallet_addresses", False,
        )
        wallet_dict = (
            getattr(self.settings, "wallet_addresses", {})
            if hasattr(self.settings, "wallet_addresses")
            else {}
        )

        # Prefer explicit wallet_addresses entries when opted in
        if prefer_wallet and wallet_dict:
            entry = wallet_dict.get(currency)
            if entry:
                if isinstance(entry, dict):
                    for key in ("address", "wallet", "addr"):
                        if entry.get(key):
                            return str(entry.get(key))
                else:
                    return str(entry)

        # Check if using FaucetPay
        if self.settings.use_faucetpay:
            fp_attr = f"faucetpay_{currency.lower()}_address"

            # Special case for MATIC (Polygon)
            if currency == "MATIC":
                return getattr(
                    self.settings,
                    "faucetpay_polygon_address",
                    None,
                )

            return getattr(self.settings, fp_attr, None)

        # Direct wallet address
        wallet_attr = f"{currency.lower()}_withdrawal_address"
        return getattr(self.settings, wallet_attr, None)

    def _get_withdrawal_threshold(
        self, currency: str,
    ) -> Dict[str, int]:
        """Get withdrawal thresholds for currency.

        Args:
            currency: Currency code.

        Returns:
            Dict with ``min``, ``target``, ``max`` thresholds.
        """
        currency = currency.upper()
        # Conservative defaults
        defaults: Dict[str, int] = {
            "min": 5000,
            "target": 50000,
            "max": 100000,
        }
        return self.settings.withdrawal_thresholds.get(
            currency, defaults,
        )

    async def check_and_execute_withdrawals(
        self,
    ) -> Dict[str, Any]:
        """Check all faucet balances and execute withdrawals.

        This is the main entry point called by the scheduler.
        Evaluates current balances against thresholds and network
        fee conditions before executing.

        Returns:
            Summary of withdrawal actions taken.
        """
        logger.info("Starting automated withdrawal check...")

        summary: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "balances_checked": 0,
            "withdrawals_executed": 0,
            "withdrawals_deferred": 0,
            "currencies_processed": [],
            "transactions": [],
        }

        # Get current balances from analytics
        balances = self._get_balances_by_currency()
        summary["balances_checked"] = len(balances)

        if not balances:
            logger.info("No balances found in analytics data")
            return summary

        logger.info("Current balances: %s", balances)

        # Process each currency
        for currency, balance in balances.items():
            summary["currencies_processed"].append(currency)

            # Get thresholds and address
            thresholds = self._get_withdrawal_threshold(currency)
            min_threshold = thresholds["min"]
            withdrawal_address = self._get_withdrawal_address(
                currency,
            )

            if not withdrawal_address:
                logger.info(
                    "No withdrawal address configured for %s",
                    currency,
                )
                continue

            # Check if balance meets minimum threshold
            if balance < min_threshold:
                logger.info(
                    "%s balance %s below minimum %s",
                    currency, balance, min_threshold,
                )
                continue

            # Check if withdrawal should proceed now
            should_withdraw = await self.wallet.should_withdraw_now(
                currency,
                int(balance),
                min_threshold,
            )

            if not should_withdraw:
                logger.info(
                    "%s withdrawal deferred - not optimal",
                    currency,
                )
                summary["withdrawals_deferred"] += 1
                continue

            # Execute withdrawal
            tx_id = await self._execute_withdrawal(
                currency, balance, withdrawal_address,
            )

            if tx_id:
                logger.info(
                    "%s withdrawal successful: %s",
                    currency, tx_id,
                )
                summary["withdrawals_executed"] += 1
                summary["transactions"].append({
                    "currency": currency,
                    "amount": balance,
                    "tx_id": tx_id,
                    "address": withdrawal_address,
                    "timestamp": (
                        datetime.now(timezone.utc).isoformat()
                    ),
                })

                # Record in withdrawal history
                self.withdrawal_history.append({
                    "timestamp": (
                        datetime.now(timezone.utc).timestamp()
                    ),
                    "currency": currency,
                    "amount": balance,
                    "tx_id": tx_id,
                    "method": (
                        "faucetpay"
                        if self.settings.use_faucetpay
                        else "direct"
                    ),
                })
            else:
                logger.warning("%s withdrawal failed", currency)
                summary["withdrawals_deferred"] += 1

        # Log summary
        logger.info(
            "Withdrawal check complete: %d executed, %d deferred",
            summary["withdrawals_executed"],
            summary["withdrawals_deferred"],
        )

        # Update last check time
        self.last_check_time = (
            datetime.now(timezone.utc).timestamp()
        )

        # Save to analytics if available
        await self._save_withdrawal_summary(summary)

        return summary

    async def _execute_withdrawal(
        self,
        currency: str,
        amount: float,
        address: str,
    ) -> Optional[str]:
        """Execute a single withdrawal transaction.

        Args:
            currency: Cryptocurrency code.
            amount: Amount to withdraw in smallest unit.
            address: Destination address.

        Returns:
            Transaction ID on success, ``None`` on failure.
        """
        logger.info(
            "Executing %s withdrawal: %s to %s",
            currency, amount, address,
        )

        try:
            # Get current fee rate for logging
            mempool_fees = await self.wallet.get_mempool_fee_rate(
                currency,
            )
            if mempool_fees:
                logger.info(
                    "Current mempool fees: %s", mempool_fees,
                )

            # Convert satoshi to BTC for batch_withdraw
            outputs = [
                {"address": address, "amount": amount / 100_000_000},
            ]

            tx_id = await self.wallet.batch_withdraw(
                currency,
                outputs,
                fee_priority="economy",
            )

            return tx_id

        except Exception as e:
            logger.error(
                "Withdrawal execution failed for %s: %s",
                currency, e,
            )
            return None

    async def _save_withdrawal_summary(
        self, summary: Dict[str, Any],
    ) -> None:
        """Save withdrawal summary to analytics file.

        Args:
            summary: Withdrawal summary dictionary.
        """
        try:
            # Lazy import to avoid circular dependency
            from core.analytics import ANALYTICS_FILE  # noqa: E402

            # Load existing data
            data: Dict[str, Any] = {}
            if os.path.exists(ANALYTICS_FILE):
                with open(
                    ANALYTICS_FILE, "r", encoding="utf-8",
                ) as fh:
                    data = json.load(fh)

            # Add withdrawal summary to withdrawals list
            if "withdrawals" not in data:
                data["withdrawals"] = []

            data["withdrawals"].append(summary)

            # Keep last 100 withdrawal summaries
            data["withdrawals"] = data["withdrawals"][-100:]

            # Save back to file
            with open(
                ANALYTICS_FILE, "w", encoding="utf-8",
            ) as fh:
                json.dump(data, fh, indent=2)

            logger.debug(
                "Withdrawal summary saved to %s", ANALYTICS_FILE,
            )

        except Exception as e:
            logger.warning(
                "Failed to save withdrawal summary: %s", e,
            )

    def get_withdrawal_stats(
        self, hours: int = 24,
    ) -> Dict[str, Any]:
        """Get withdrawal statistics for the last *hours* hours.

        Args:
            hours: Number of hours to look back.

        Returns:
            Statistics dictionary with totals by currency.
        """
        cutoff = time.time() - (hours * 3600)

        recent = [
            w for w in self.withdrawal_history
            if w["timestamp"] >= cutoff
        ]

        by_currency: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_amount": 0},
        )
        for w in recent:
            currency = w["currency"]
            by_currency[currency]["count"] += 1
            by_currency[currency]["total_amount"] += w["amount"]

        return {
            "total_withdrawals": len(recent),
            "by_currency": dict(by_currency),
            "period_hours": hours,
        }

    async def get_optimal_withdrawal_windows(
        self,
    ) -> List[Dict[str, Any]]:
        """Predict optimal withdrawal windows for next 24 hours.

        Returns:
            List of optimal time windows with fee predictions.
        """
        windows: List[Dict[str, Any]] = []

        # Check BTC fees as reference (most used)
        mempool_fees = await self.wallet.get_mempool_fee_rate("BTC")

        if not mempool_fees:
            logger.warning(
                "Unable to fetch mempool data for predictions",
            )
            return windows

        current_fee = mempool_fees.get("economy", 999)

        # Off-peak hours are typically best
        off_peak_hours = self.settings.off_peak_hours

        for hour in off_peak_hours:
            windows.append({
                "hour_utc": hour,
                "predicted_fee_range": (
                    "low" if current_fee < 20 else "medium"
                ),
                "recommended": current_fee < 20,
            })

        return windows


def get_auto_withdrawal_instance(
    wallet_daemon: Any,
    settings: Any,
    analytics_tracker: Any,
) -> "AutoWithdrawal":
    """Create an :class:`AutoWithdrawal` instance.

    Factory function used by the orchestrator.

    Args:
        wallet_daemon: WalletDaemon instance.
        settings: BotSettings configuration.
        analytics_tracker: EarningsTracker instance.

    Returns:
        Configured AutoWithdrawal instance.
    """
    return AutoWithdrawal(
        wallet_daemon, settings, analytics_tracker,
    )
