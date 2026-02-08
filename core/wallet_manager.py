"""Wallet daemon interface for local crypto wallet RPC and public blockchain APIs.

Provides an async context-managed client that keeps two separate HTTP sessions:
one authenticated session for JSON-RPC calls to the local wallet daemon and one
unauthenticated session for read-only public API calls (mempool fee lookups,
on-chain balance queries, etc.).  This prevents RPC credentials from leaking to
third-party services.
"""

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

    async def _rpc_call(self, coin: str, method: str, params: Optional[list] = None) -> Any:
        """
        Execute a JSON-RPC call to a specific coin wallet daemon.
        """
        if params is None:
            params = []
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

    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup."""
        await self.close()
        return False

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

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

    async def get_mempool_fee_rate(self, coin: str) -> Optional[Dict[str, int]]:
        """Fetch current network fee rates from mempool APIs.
        
        APIs used:
        - BTC: mempool.space/api/v1/fees/recommended
        - LTC: blockcypher.com/v1/ltc/main
        - DOGE: sochain.com/api/v2/get_info/DOGE
        
        Returns:
            {
                "economy": int,  # sat/byte for low priority
                "normal": int,   # sat/byte for medium priority  
                "priority": int  # sat/byte for high priority
            }
        """
        coin = coin.upper()
        
        try:
            session = await self._get_session()
            
            if coin == "BTC":
                async with session.get("https://mempool.space/api/v1/fees/recommended", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "economy": data.get("minimumFee", 1),
                            "normal": data.get("halfHourFee", 5),
                            "priority": data.get("fastestFee", 10)
                        }
            
            elif coin == "LTC":
                async with session.get("https://api.blockcypher.com/v1/ltc/main", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # BlockCypher returns fees in satoshis per kb, convert to sat/byte
                        low_fee = data.get("low_fee_per_kb", 1000) // 1000
                        med_fee = data.get("medium_fee_per_kb", 5000) // 1000
                        high_fee = data.get("high_fee_per_kb", 10000) // 1000
                        return {
                            "economy": max(1, low_fee),
                            "normal": max(3, med_fee),
                            "priority": max(5, high_fee)
                        }
            
            elif coin == "DOGE":
                async with session.get("https://sochain.com/api/v2/get_info/DOGE", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # SoChain doesn't provide fee estimates, use conservative defaults
                        # DOGE typically has very low fees (0.01 DOGE recommended)
                        return {
                            "economy": 1,    # 1 sat/byte (very cheap)
                            "normal": 2,     # 2 sat/byte
                            "priority": 5    # 5 sat/byte
                        }
            
            logger.warning(f"No mempool API configured for {coin}, using fallback")
            return None
            
        except Exception as e:
            logger.warning(f"Failed to fetch mempool fees for {coin}: {e}")
            return None

    async def get_network_fee_estimate(self, coin: str, priority: str = "economy") -> Optional[float]:
        """Estimate network fee for a transaction.
        
        First tries real-time mempool APIs, falls back to RPC estimatesmartfee.
        
        Args:
            coin: Cryptocurrency symbol (BTC, LTC, DOGE)
            priority: Fee priority ('economy', 'normal', 'priority')
            
        Returns:
            Estimated fee in satoshis per byte, or None if unavailable
        """
        # Try mempool API first (real-time data)
        mempool_fees = await self.get_mempool_fee_rate(coin)
        if mempool_fees:
            return float(mempool_fees.get(priority, mempool_fees.get("normal", 5)))
        
        # Fallback to RPC estimation
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

    async def get_address_balance_api(self, coin: str, address: str) -> Optional[float]:
        """Fetch on-chain balance for a single address using public APIs.

        Uses lightweight explorer endpoints (read-only) so it works for Cake
        wallet receive-only addresses without requiring RPC credentials.

        Returns the confirmed balance in the main unit (BTC/LTC/DOGE/ETH/TRX/etc.).
        Coins without public balance APIs (e.g., XMR) return None.
        """
        coin = coin.upper()
        session = await self._get_session()

        try:
            if coin == "BTC":
                url = f"https://api.blockcypher.com/v1/btc/main/addrs/{address}/balance"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get("final_balance", 0)) / 100000000

            if coin == "LTC":
                url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/balance"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get("final_balance", 0)) / 100000000

            if coin == "DOGE":
                url = f"https://sochain.com/api/v2/get_address_balance/DOGE/{address}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        balance = data.get("data", {}).get("confirmed_balance")
                        return float(balance) if balance is not None else 0.0

            if coin == "ETH":
                # Cloudflare-hosted Etherscan-lite endpoint via BlockCypher
                url = f"https://api.blockcypher.com/v1/eth/main/addrs/{address}/balance"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # BlockCypher returns wei
                        return float(data.get("final_balance", 0)) / 1e18

            if coin == "TRX":
                url = f"https://apilist.tronscan.org/api/account?address={address}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        balance = data.get("balance")
                        return float(balance) / 1e6 if balance is not None else 0.0

            if coin in {"BCH", "DASH"}:
                # Use BlockCypher where supported; BCH/DASH not universally available
                url = f"https://api.blockcypher.com/v1/{coin.lower()}/main/addrs/{address}/balance"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get("final_balance", 0)) / 100000000

            logger.info(f"No public balance API configured for {coin}; returning None")
            return None
        except Exception as exc:
            logger.warning(f"Failed to fetch address balance for {coin}: {exc}")
            return None

    async def get_balances_for_addresses(self, wallet_addresses: Dict[str, Any]) -> Dict[str, float]:
        """Fetch balances for all configured addresses.

        Supports dict entries like {"BTC": {"address": "..."}} or {"BTC": "addr"}.
        Unsupported coins are skipped gracefully.
        """
        balances: Dict[str, float] = {}

        for coin, entry in wallet_addresses.items():
            address: Optional[str] = None
            if isinstance(entry, dict):
                address = entry.get("address") or entry.get("wallet") or entry.get("addr")
            elif isinstance(entry, str):
                address = entry

            if not address:
                continue

            balance = await self.get_address_balance_api(coin, address)
            if balance is not None:
                balances[coin.upper()] = balance

        return balances

    async def should_withdraw_now(
        self, 
        coin: str, 
        balance_sat: int, 
        min_threshold: int = 30000
    ) -> bool:
        """Determine if withdrawal should proceed based on multiple conditions.
        
        Uses real-time mempool data for optimal fee timing.
        
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
        is_off_peak = self.is_off_peak_hour()
        if not is_off_peak:
            logger.info("Not off-peak hour, checking if fees are exceptionally low...")
        
        # Get real-time mempool fee data
        mempool_fees = await self.get_mempool_fee_rate(coin)
        
        if mempool_fees:
            economy_fee = mempool_fees.get("economy", 999)
            normal_fee = mempool_fees.get("normal", 999)
            
            # Excellent fee environment (< 5 sat/byte) - withdraw regardless of time
            if economy_fee < 5:
                logger.info(f"✅ Excellent fees ({economy_fee} sat/byte) - proceeding with withdrawal")
                return True
            
            # Good fee environment (< 20 sat/byte) during off-peak
            if is_off_peak and economy_fee < 20:
                logger.info(f"✅ Good off-peak fees ({economy_fee} sat/byte) - proceeding")
                return True
            
            # High fees (> 50 sat/byte) - defer even if off-peak
            if economy_fee > 50:
                logger.info(f"❌ High network fees ({economy_fee} sat/byte) - deferring withdrawal")
                return False
            
            # Medium fees during off-peak - proceed if balance is high
            if is_off_peak and balance_sat > min_threshold * 2:
                logger.info(f"⚠️ Medium fees ({economy_fee} sat/byte) but high balance - proceeding")
                return True
        
        # No mempool data - use conservative approach (off-peak only)
        if is_off_peak:
            logger.info("Off-peak hour with no fee data - proceeding conservatively")
            return True
        
        logger.info("Conditions not optimal for withdrawal - deferring")
        return False

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

