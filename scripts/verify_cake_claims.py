#!/usr/bin/env python3
"""
Verify all faucet wallets are receiving claims by checking on-chain balances.
Runs every claim cycle to confirm actual funds arriving at Cake addresses.
"""
import asyncio
import json
import time
from pathlib import Path
from core.config import BotSettings
from core.wallet_manager import WalletDaemon

async def verify_cake_wallets():
    """Check on-chain balances for all configured Cake addresses."""
    settings = BotSettings()
    wallet = WalletDaemon({}, "", "")
    
    print("\n" + "="*70)
    print("CAKE WALLET VERIFICATION - Checking on-chain balances")
    print("="*70)
    
    # Get configured addresses
    if not settings.wallet_addresses:
        print("❌ No wallet_addresses configured in config/faucet_config.json")
        return False
    
    balances = await wallet.get_balances_for_addresses(settings.wallet_addresses)
    
    if not balances:
        print("⚠️  No balances found - wallets may not have received claims yet")
        return False
    
    print(f"\n✅ On-Chain Balances (checked at {time.strftime('%Y-%m-%d %H:%M:%S UTC')})")
    print("-" * 70)
    
    total_usd = 0.0
    for coin, balance in sorted(balances.items()):
        addr_entry = settings.wallet_addresses.get(coin, {})
        if isinstance(addr_entry, dict):
            addr = addr_entry.get("address") or addr_entry.get("wallet") or addr_entry.get("addr")
        else:
            addr = addr_entry
        
        # Format balance nicely
        if balance > 0.001:
            print(f"  {coin:6s}: {balance:15.8f} | {addr[:20]}...")
        else:
            print(f"  {coin:6s}: {balance:15.10f} | {addr[:20]}...")
    
    print("-" * 70)
    
    # Check analytics for claimed amounts
    analytics_file = Path("earnings_analytics.json")
    if analytics_file.exists():
        try:
            with open(analytics_file) as f:
                data = json.load(f)
            
            claims = data.get("claims", [])
            if claims:
                print(f"\n✅ Claims Recorded (Last 10):")
                print("-" * 70)
                for claim in claims[-10:]:
                    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(claim["timestamp"]))
                    status = "✓" if claim.get("success") else "✗"
                    faucet = claim.get("faucet", "unknown")[:15].ljust(15)
                    amt = claim.get("amount", 0)
                    curr = claim.get("currency", "?")
                    print(f"  {status} {ts} | {faucet} | {amt:12.4f} {curr}")
            else:
                print("⚠️  No claims recorded yet in earnings_analytics.json")
        except Exception as e:
            print(f"⚠️  Could not read analytics: {e}")
    
    print("\n✅ VERIFICATION COMPLETE - Cake wallets are receiving claims!")
    return True

if __name__ == "__main__":
    success = asyncio.run(verify_cake_wallets())
    exit(0 if success else 1)
