#!/usr/bin/env python3
"""
Check actual balances on all configured faucet sites.
This will login to each site and retrieve current balance.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import BotSettings
from faucets.freebitcoin import FreeBitcoinBot
from faucets.firefaucet import FireFaucetBot
from faucets.cointiply import CointiplyBot
from faucets.dutchy import DutchyBot
from faucets.coinpayu import CoinPayUBot
from faucets.adbtc import AdBTCBot
from faucets.faucetcrypto import FaucetCryptoBot


async def check_balance(faucet_class, profile):
    """Check balance for a single faucet."""
    print(f"\n{'='*60}")
    print(f"Checking {faucet_class.__name__}...")
    print(f"{'='*60}")
    
    bot = faucet_class(profile)
    
    try:
        # Login
        print("🔐 Logging in...")
        login_success = await bot.login()
        
        if not login_success:
            print(f"❌ Login failed for {faucet_class.__name__}")
            return None
        
        print("✅ Login successful")
        
        # Get balance
        print("💰 Fetching balance...")
        balance = await bot.get_balance()
        
        if balance is not None and balance > 0:
            print(f"💎 BALANCE: {balance}")
            return {
                'faucet': faucet_class.__name__.replace('Bot', ''),
                'balance': balance,
                'username': profile['username']
            }
        else:
            print(f"⚠️ Balance: {balance if balance is not None else 'Unknown'}")
            return {
                'faucet': faucet_class.__name__.replace('Bot', ''),
                'balance': balance if balance is not None else 0,
                'username': profile['username']
            }
            
    except Exception as e:
        print(f"❌ Error checking {faucet_class.__name__}: {e}")
        return None
    finally:
        try:
            await bot.cleanup()
        except:
            pass


async def main():
    """Check all faucet balances."""
    
    print("\n" + "="*60)
    print("LIVE BALANCE CHECK")
    print("="*60)
    
    # Build profile configs
    faucets_to_check = []
    
    # FreeBitcoin
    if BotSettings.freebitcoin_username and BotSettings.freebitcoin_password:
        faucets_to_check.append({
            'class': FreeBitcoinBot,
            'profile': {
                'faucet': 'freebitcoin',
                'username': BotSettings.freebitcoin_username,
                'password': BotSettings.freebitcoin_password,
                'proxy': None,
                'residential_proxy': True,
                'enabled': True
            }
        })
    
    # FireFaucet
    if BotSettings.firefaucet_username and BotSettings.firefaucet_password:
        faucets_to_check.append({
            'class': FireFaucetBot,
            'profile': {
                'faucet': 'firefaucet',
                'username': BotSettings.firefaucet_username,
                'password': BotSettings.firefaucet_password,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    # Cointiply
    if BotSettings.cointiply_username and BotSettings.cointiply_password:
        faucets_to_check.append({
            'class': CointiplyBot,
            'profile': {
                'faucet': 'cointiply',
                'username': BotSettings.cointiply_username,
                'password': BotSettings.cointiply_password,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    # DutchyCorp
    if BotSettings.dutchy_username and BotSettings.dutchy_password:
        faucets_to_check.append({
            'class': DutchyBot,
            'profile': {
                'faucet': 'dutchy',
                'username': BotSettings.dutchy_username,
                'password': BotSettings.dutchy_password,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    # CoinPayU
    if BotSettings.coinpayu_username and BotSettings.coinpayu_password:
        faucets_to_check.append({
            'class': CoinPayUBot,
            'profile': {
                'faucet': 'coinpayu',
                'username': BotSettings.coinpayu_username,
                'password': BotSettings.coinpayu_password,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    # AdBTC
    if BotSettings.adbtc_username and BotSettings.adbtc_password:
        faucets_to_check.append({
            'class': AdBTCBot,
            'profile': {
                'faucet': 'adbtc',
                'username': BotSettings.adbtc_username,
                'password': BotSettings.adbtc_password,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    # FaucetCrypto
    if BotSettings.faucetcrypto_username and BotSettings.faucetcrypto_password:
        faucets_to_check.append({
            'class': FaucetCryptoBot,
            'profile': {
                'faucet': 'faucetcrypto',
                'username': BotSettings.faucetcrypto_username,
                'password': BotSettings.faucetcrypto_password,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    print(f"\nFound {len(faucets_to_check)} faucets with credentials")
    
    # Check balances
    results = []
    for faucet_info in faucets_to_check:
        result = await check_balance(faucet_info['class'], faucet_info['profile'])
        if result:
            results.append(result)
        await asyncio.sleep(2)  # Rate limiting
    
    # Summary
    print("\n" + "="*60)
    print("BALANCE SUMMARY")
    print("="*60)
    
    total_found = 0
    for result in results:
        balance = result['balance']
        if balance and balance > 0:
            print(f"💎 {result['faucet']:20s} | Balance: {balance:>15}")
            total_found += 1
        else:
            print(f"⚪ {result['faucet']:20s} | Balance: {balance if balance is not None else 'Unknown':>15}")
    
    print("\n" + "="*60)
    if total_found > 0:
        print(f"✅ Found balances on {total_found} faucet(s)")
    else:
        print("❌ No balances found on any faucets")
        print("   This could mean:")
        print("   - No successful claims yet")
        print("   - Balance retrieval failed")
        print("   - Sites require login verification")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
