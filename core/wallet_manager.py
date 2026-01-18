import aiohttp
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

class WalletDaemon:
    """
    Interface for local crypto wallet daemons (Electrum, Core).
    Uses JSON-RPC to manage keys and sign transactions headless.
    """
    
    def __init__(self, rpc_urls: Dict[str, str], rpc_user: str, rpc_pass: str):
        """
        Initialize the WalletDaemon.

        Args:
            rpc_urls: Mapping of coin symbols to their RPC URLs (e.g. {'BTC': 'http://...', 'LTC': '...'}).
            rpc_user: The username for RPC authentication.
            rpc_pass: The password for RPC authentication.
        """
        self.urls = rpc_urls
        self.auth = aiohttp.BasicAuth(rpc_user, rpc_pass) if rpc_user else None
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(auth=self.auth)
        return self._session

    async def _rpc_call(self, coin: str, method: str, params: list = []) -> Any:
        """
        Execute a JSON-RPC call to a specific coin wallet daemon.
        """
        url = self.urls.get(coin.upper())
        if not url:
            logger.error(f"No RPC URL configured for coin: {coin}")
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": f"crypto-bot-{coin}",
            "method": method,
            "params": params
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'error' in data and data['error']:
                        logger.error(f"RPC Error {coin}:{method}: {data['error']}")
                        return None
                    return data.get('result')
                else:
                    logger.error(f"RPC HTTP Error {response.status} on {coin}")
                    return None
        except Exception as e:
            logger.error(f"Wallet Daemon Connection Failed ({coin}): {e}")
            return None

    async def get_balance(self, coin: str = "BTC") -> Optional[Dict]:
        """Get confirmed and unconfirmed balance for a specific coin."""
        return await self._rpc_call(coin, "getbalance")

    async def close(self):
        if self._session:
            await self._session.close()

    async def get_unused_address(self, coin: str = "BTC") -> Optional[str]:
        """Generate a new receiving address."""
        return await self._rpc_call(coin, "getunusedaddress")

    async def validate_address(self, address: str, coin: str = "BTC") -> bool:
        """Check if address is valid."""
        res = await self._rpc_call(coin, "validateaddress", [address])
        return res if isinstance(res, bool) else res.get('isvalid', False)

    async def check_connection(self, coin: str = "BTC") -> bool:
        """Health check."""
        res = await self._rpc_call(coin, "getnetworkinfo")  # 'version' is often deprecated/not standard, getnetworkinfo is safer for bitcoind-likes
        return res is not None

    async def get_network_fee_estimate(self, coin: str, priority: str = "economy") -> Optional[float]:
        """Estimate network fee for a transaction.
        
        Uses Bitcoin Core's estimatesmartfee RPC to get fee rate recommendations.
        
        Args:
            coin: Cryptocurrency symbol (BTC, LTC, DOGE)
            priority: Fee priority ('economy', 'normal', 'priority')
            
        Returns:
            Estimated fee in satoshis per byte, or None if unavailable
        """
        # Target confirmation blocks by priority
        blocks = {"economy": 12, "normal": 6, "priority": 2}
        target_blocks = blocks.get(priority, 6)
        
        result = await self._rpc_call(coin, "estimatesmartfee", [target_blocks])
        if result and "feerate" in result:
            # Convert BTC/kB to sat/byte
            return int(result["feerate"] * 100000000 / 1000)
        return None

    def is_off_peak_hour(self) -> bool:
        """Check if current time is optimal for withdrawals (lower network fees).
        
        Off-peak hours are typically:
        - Late night / early morning UTC (22:00 - 05:00)
        - Weekends (especially Sunday)
        
        These times generally have lower network congestion and fees.
        
        Returns:
            True if current time is off-peak for withdrawals
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        weekday = now.weekday()
        
        is_night = hour >= 22 or hour < 5
        is_weekend = weekday >= 5
        
        return is_night or is_weekend

    async def should_withdraw_now(
        self, 
        coin: str, 
        balance_sat: int, 
        min_threshold: int = 30000
    ) -> bool:
        """Determine if withdrawal should proceed based on multiple conditions.
        
        Considers: balance threshold, network fees, time of day.
        
        Args:
            coin: Cryptocurrency symbol
            balance_sat: Current balance in satoshis
            min_threshold: Minimum balance required (default 30,000 satoshi)
            
        Returns:
            True if withdrawal is recommended now
        """
        if balance_sat < min_threshold:
            logger.info(f"Balance {balance_sat} sat below threshold {min_threshold}")
            return False
        
        # Check if off-peak hours
        if not self.is_off_peak_hour():
            logger.info("Not off-peak hour, deferring withdrawal for better timing")
            return False
        
        # Check fee estimate if available
        fee_rate = await self.get_network_fee_estimate(coin, "economy")
        if fee_rate and fee_rate > 50:  # High fee environment (>50 sat/byte)
            logger.info(f"High network fees ({fee_rate} sat/byte), deferring withdrawal")
            return False
        
        return True

    async def batch_withdraw(
        self,
        coin: str,
        outputs: List[Dict[str, Any]],
        fee_priority: str = "economy"
    ) -> Optional[str]:
        """Execute batched withdrawal with multiple outputs.
        
        Batching multiple withdrawals into a single transaction can reduce 
        fees by 50-70% compared to individual transactions.
        
        Args:
            coin: Cryptocurrency symbol
            outputs: List of {"address": str, "amount": float}
            fee_priority: Fee tier ('economy', 'normal', 'priority')
            
        Returns:
            Transaction ID on success, None on failure
        """
        from core.withdrawal_analytics import get_analytics
        
        if not outputs:
            logger.warning("No outputs provided for batch withdrawal")
            return None
        
        # Validate all addresses first
        for out in outputs:
            is_valid = await self.validate_address(out["address"], coin)
            if not is_valid:
                logger.error(f"Invalid address in batch: {out['address']}")
                return None
        
        # Get network fee estimate
        fee_rate = await self.get_network_fee_estimate(coin, fee_priority)
        estimated_network_fee = (fee_rate * 250 / 100000000) if fee_rate else 0.0  # Estimate for typical tx size
        
        # Format for sendmany RPC call
        amounts = {out["address"]: out["amount"] for out in outputs}
        total_amount = sum(out["amount"] for out in outputs)
        
        result = await self._rpc_call(coin, "sendmany", ["", amounts])
        
        if result:
            logger.info(f"Batch withdrawal submitted: txid={result}")
            
            # Record in analytics
            try:
                analytics = get_analytics()
                analytics.record_withdrawal(
                    faucet="WalletDaemon",
                    cryptocurrency=coin,
                    amount=total_amount,
                    network_fee=estimated_network_fee,
                    platform_fee=0.0,
                    withdrawal_method="wallet_daemon",
                    status="success",
                    tx_id=result,
                    notes=f"Batch withdrawal with {len(outputs)} outputs"
                )
            except Exception as e:
                logger.warning(f"Failed to record batch withdrawal analytics: {e}")
            
            return result
        
        logger.error("Batch withdrawal failed")
        return None

