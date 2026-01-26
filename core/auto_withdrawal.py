"""
Automated Withdrawal Orchestration

Handles periodic balance checks and executes withdrawals during optimal
network fee windows. Integrates with both direct wallet and FaucetPay.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class AutoWithdrawal:
    """
    Automated withdrawal manager that monitors balances and executes
    withdrawals during optimal network fee conditions.
    """
    
    def __init__(self, wallet_daemon, settings, analytics_tracker):
        """
        Initialize AutoWithdrawal.
        
        Args:
            wallet_daemon: WalletDaemon instance for blockchain operations
            settings: BotSettings configuration
            analytics_tracker: EarningsTracker instance for balance data
        """
        self.wallet = wallet_daemon
        self.settings = settings
        self.tracker = analytics_tracker
        self.withdrawal_history: List[Dict] = []
        self.last_check_time: float = 0
        
    def _get_balances_by_currency(self) -> Dict[str, float]:
        """
        Extract current balances from analytics data.
        
        Returns:
            Dict mapping currency code to balance in smallest unit
        """
        balances = defaultdict(float)
        
        # Get all successful claims and sum by currency
        for claim in self.tracker.claims:
            if claim.get("success") and claim.get("balance_after", 0) > 0:
                currency = claim.get("currency", "unknown").upper()
                # Use the most recent balance_after for each currency
                balances[currency] = max(balances[currency], claim.get("balance_after", 0))
        
        return dict(balances)
    
    def _get_withdrawal_address(self, currency: str) -> Optional[str]:
        """
        Get withdrawal address for currency (FaucetPay or direct wallet).
        
        Args:
            currency: Currency code (BTC, LTC, DOGE, etc.)
            
        Returns:
            Withdrawal address or None
        """
        currency = currency.upper()

        prefer_wallet = getattr(self.settings, "prefer_wallet_addresses", False)
        wallet_dict = getattr(self.settings, "wallet_addresses", {}) if hasattr(self.settings, "wallet_addresses") else {}

        # Prefer explicit wallet_addresses entries (e.g., Cake) when opted in
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
                return getattr(self.settings, "faucetpay_polygon_address", None)
            
            return getattr(self.settings, fp_attr, None)
        
        # Direct wallet address
        wallet_attr = f"{currency.lower()}_withdrawal_address"
        return getattr(self.settings, wallet_attr, None)
    
    def _get_withdrawal_threshold(self, currency: str) -> Dict[str, int]:
        """
        Get withdrawal thresholds for currency.
        
        Args:
            currency: Currency code
            
        Returns:
            Dict with min, target, max thresholds
        """
        currency = currency.upper()
        return self.settings.withdrawal_thresholds.get(
            currency,
            {"min": 5000, "target": 50000, "max": 100000}  # Conservative defaults
        )
    
    async def check_and_execute_withdrawals(self) -> Dict[str, Any]:
        """
        Check all faucet balances and execute withdrawals when optimal.
        
        This is the main entry point called by the scheduler.
        
        Returns:
            Summary of withdrawal actions taken
        """
        logger.info("🔍 Starting automated withdrawal check...")
        
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "balances_checked": 0,
            "withdrawals_executed": 0,
            "withdrawals_deferred": 0,
            "currencies_processed": [],
            "transactions": []
        }
        
        # Get current balances from analytics
        balances = self._get_balances_by_currency()
        summary["balances_checked"] = len(balances)
        
        if not balances:
            logger.info("No balances found in analytics data")
            return summary
        
        logger.info(f"📊 Current balances: {balances}")
        
        # Process each currency
        for currency, balance in balances.items():
            summary["currencies_processed"].append(currency)
            
            # Get thresholds and address
            thresholds = self._get_withdrawal_threshold(currency)
            min_threshold = thresholds["min"]
            withdrawal_address = self._get_withdrawal_address(currency)
            
            if not withdrawal_address:
                logger.info(f"⏭️  No withdrawal address configured for {currency}")
                continue
            
            # Check if balance meets minimum threshold
            if balance < min_threshold:
                logger.info(f"⏭️  {currency} balance {balance} below minimum {min_threshold}")
                continue
            
            # Check if withdrawal should proceed now (fees, timing, etc.)
            should_withdraw = await self.wallet.should_withdraw_now(
                currency,
                int(balance),
                min_threshold
            )
            
            if not should_withdraw:
                logger.info(f"⏸️  {currency} withdrawal deferred - conditions not optimal")
                summary["withdrawals_deferred"] += 1
                continue
            
            # Execute withdrawal
            tx_id = await self._execute_withdrawal(
                currency,
                balance,
                withdrawal_address
            )
            
            if tx_id:
                logger.info(f"✅ {currency} withdrawal successful: {tx_id}")
                summary["withdrawals_executed"] += 1
                summary["transactions"].append({
                    "currency": currency,
                    "amount": balance,
                    "tx_id": tx_id,
                    "address": withdrawal_address,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                # Record in withdrawal history
                self.withdrawal_history.append({
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "currency": currency,
                    "amount": balance,
                    "tx_id": tx_id,
                    "method": "faucetpay" if self.settings.use_faucetpay else "direct"
                })
            else:
                logger.warning(f"❌ {currency} withdrawal failed")
                summary["withdrawals_deferred"] += 1
        
        # Log summary
        logger.info(f"📋 Withdrawal check complete: {summary['withdrawals_executed']} executed, "
                   f"{summary['withdrawals_deferred']} deferred")
        
        # Update last check time
        self.last_check_time = datetime.now(timezone.utc).timestamp()
        
        # Save to analytics if available
        await self._save_withdrawal_summary(summary)
        
        return summary
    
    async def _execute_withdrawal(
        self,
        currency: str,
        amount: float,
        address: str
    ) -> Optional[str]:
        """
        Execute a single withdrawal transaction.
        
        Args:
            currency: Cryptocurrency code
            amount: Amount to withdraw in smallest unit
            address: Destination address
            
        Returns:
            Transaction ID on success, None on failure
        """
        logger.info(f"💸 Executing {currency} withdrawal: {amount} to {address}")
        
        try:
            # Get current fee rate for logging
            mempool_fees = await self.wallet.get_mempool_fee_rate(currency)
            if mempool_fees:
                logger.info(f"📊 Current mempool fees: {mempool_fees}")
            
            # Use batch_withdraw for flexibility (single output in this case)
            outputs = [{"address": address, "amount": amount / 100000000}]  # Convert satoshi to BTC
            
            tx_id = await self.wallet.batch_withdraw(
                currency,
                outputs,
                fee_priority="economy"
            )
            
            return tx_id
            
        except Exception as e:
            logger.error(f"Withdrawal execution failed for {currency}: {e}")
            return None
    
    async def _save_withdrawal_summary(self, summary: Dict) -> None:
        """
        Save withdrawal summary to analytics file.
        
        Args:
            summary: Withdrawal summary dictionary
        """
        try:
            from core.analytics import ANALYTICS_FILE
            import json
            import os
            
            # Load existing data
            data = {}
            if os.path.exists(ANALYTICS_FILE):
                with open(ANALYTICS_FILE, "r") as f:
                    data = json.load(f)
            
            # Add withdrawal summary to withdrawals list
            if "withdrawals" not in data:
                data["withdrawals"] = []
            
            data["withdrawals"].append(summary)
            
            # Keep last 100 withdrawal summaries
            data["withdrawals"] = data["withdrawals"][-100:]
            
            # Save back to file
            with open(ANALYTICS_FILE, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"💾 Withdrawal summary saved to {ANALYTICS_FILE}")
            
        except Exception as e:
            logger.warning(f"Failed to save withdrawal summary: {e}")
    
    def get_withdrawal_stats(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get withdrawal statistics for the last N hours.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            Statistics dictionary
        """
        import time
        cutoff = time.time() - (hours * 3600)
        
        recent = [w for w in self.withdrawal_history if w["timestamp"] >= cutoff]
        
        by_currency = defaultdict(lambda: {"count": 0, "total_amount": 0})
        for w in recent:
            currency = w["currency"]
            by_currency[currency]["count"] += 1
            by_currency[currency]["total_amount"] += w["amount"]
        
        return {
            "total_withdrawals": len(recent),
            "by_currency": dict(by_currency),
            "period_hours": hours
        }
    
    async def get_optimal_withdrawal_windows(self) -> List[Dict[str, Any]]:
        """
        Predict optimal withdrawal windows for next 24 hours.
        
        Returns:
            List of optimal time windows with fee predictions
        """
        windows = []
        
        # Check BTC fees as reference (most used)
        mempool_fees = await self.wallet.get_mempool_fee_rate("BTC")
        
        if not mempool_fees:
            logger.warning("Unable to fetch mempool data for predictions")
            return windows
        
        current_fee = mempool_fees.get("economy", 999)
        
        # Off-peak hours are typically best
        off_peak_hours = self.settings.off_peak_hours
        
        for hour in off_peak_hours:
            windows.append({
                "hour_utc": hour,
                "predicted_fee_range": "low" if current_fee < 20 else "medium",
                "recommended": current_fee < 20
            })
        
        return windows


def get_auto_withdrawal_instance(wallet_daemon, settings, analytics_tracker) -> AutoWithdrawal:
    """
    Factory function to create AutoWithdrawal instance.
    
    Args:
        wallet_daemon: WalletDaemon instance
        settings: BotSettings configuration
        analytics_tracker: EarningsTracker instance
        
    Returns:
        AutoWithdrawal instance
    """
    return AutoWithdrawal(wallet_daemon, settings, analytics_tracker)
