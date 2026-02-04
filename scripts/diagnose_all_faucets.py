#!/usr/bin/env python3
"""
Comprehensive faucet diagnostic - test login, balance, timer for all faucets.
Run in visible mode to see exact failures.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import BotSettings
from faucets.freebitcoin import FreeBitcoinBot
from faucets.firefaucet import FireFaucetBot
from faucets.cointiply import CointiplyBot


async def diagnose_faucet(bot_class, profile, faucet_name):
    """Diagnose a single faucet with detailed logging."""
    print(f"\n{'='*70}")
    print(f"DIAGNOSING: {faucet_name}")
    print(f"{'='*70}")
    
    bot = bot_class(profile)
    results = {
        'faucet': faucet_name,
        'login': None,
        'balance': None,
        'timer': None,
        'page_url': None,
        'errors': []
    }
    
    try:
        # Step 1: Login
        print(f"\n[1/3] Testing LOGIN...")
        try:
            login_result = await bot.login()
            results['login'] = login_result
            
            if login_result:
                print(f"✅ LOGIN SUCCESS")
                results['page_url'] = bot.page.url if hasattr(bot, 'page') and bot.page else 'unknown'
                print(f"   Current URL: {results['page_url']}")
            else:
                print(f"❌ LOGIN FAILED")
                results['errors'].append("Login returned False")
                return results
        except Exception as e:
            print(f"❌ LOGIN ERROR: {e}")
            results['errors'].append(f"Login exception: {e}")
            return results
        
        # Step 2: Balance
        print(f"\n[2/3] Testing BALANCE extraction...")
        try:
            balance = await bot.get_balance()
            results['balance'] = balance
            
            if balance is not None:
                print(f"✅ BALANCE: {balance}")
            else:
                print(f"❌ BALANCE: Could not extract")
                results['errors'].append("Balance extraction returned None")
        except Exception as e:
            print(f"❌ BALANCE ERROR: {e}")
            results['errors'].append(f"Balance exception: {e}")
        
        # Step 3: Timer
        print(f"\n[3/3] Testing TIMER extraction...")
        try:
            timer = await bot.get_timer()
            results['timer'] = timer
            
            if timer is not None:
                print(f"✅ TIMER: {timer} seconds ({timer//3600}h {(timer%3600)//60}m)")
            else:
                print(f"❌ TIMER: Could not extract")
                results['errors'].append("Timer extraction returned None")
        except Exception as e:
            print(f"❌ TIMER ERROR: {e}")
            results['errors'].append(f"Timer exception: {e}")
        
        # Keep browser open for inspection
        print(f"\n⏸️  Browser kept open for 30 seconds - inspect the page!")
        await asyncio.sleep(30)
        
    finally:
        try:
            await bot.cleanup()
        except:
            pass
    
    return results


async def main():
    """Diagnose all faucets."""
    print("\n" + "="*70)
    print("COMPREHENSIVE FAUCET DIAGNOSTIC")
    print("="*70)
    
    # Configure faucets to test
    faucets = []
    
    # FreeBitcoin
    if BotSettings.FREEBITCOIN_USERNAME and BotSettings.FREEBITCOIN_PASSWORD:
        faucets.append({
            'class': FreeBitcoinBot,
            'name': 'FreeBitcoin',
            'profile': {
                'faucet': 'freebitcoin',
                'username': BotSettings.FREEBITCOIN_USERNAME,
                'password': BotSettings.FREEBITCOIN_PASSWORD,
                'proxy': None,
                'residential_proxy': True,
                'enabled': True
            }
        })
    
    # FireFaucet
    if BotSettings.FIREFAUCET_USERNAME and BotSettings.FIREFAUCET_PASSWORD:
        faucets.append({
            'class': FireFaucetBot,
            'name': 'FireFaucet',
            'profile': {
                'faucet': 'firefaucet',
                'username': BotSettings.FIREFAUCET_USERNAME,
                'password': BotSettings.FIREFAUCET_PASSWORD,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    # Cointiply
    if BotSettings.COINTIPLY_USERNAME and BotSettings.COINTIPLY_PASSWORD:
        faucets.append({
            'class': CointiplyBot,
            'name': 'Cointiply',
            'profile': {
                'faucet': 'cointiply',
                'username': BotSettings.COINTIPLY_USERNAME,
                'password': BotSettings.COINTIPLY_PASSWORD,
                'proxy': None,
                'residential_proxy': False,
                'enabled': True
            }
        })
    
    print(f"\nTesting {len(faucets)} faucets...\n")
    
    all_results = []
    for faucet_info in faucets:
        result = await diagnose_faucet(
            faucet_info['class'],
            faucet_info['profile'],
            faucet_info['name']
        )
        all_results.append(result)
        await asyncio.sleep(5)  # Cooldown between tests
    
    # Final summary
    print("\n" + "="*70)
    print("DIAGNOSTIC SUMMARY")
    print("="*70)
    
    for result in all_results:
        print(f"\n{result['faucet']}:")
        print(f"  Login:   {'✅ SUCCESS' if result['login'] else '❌ FAILED'}")
        print(f"  Balance: {result['balance'] if result['balance'] is not None else '❌ FAILED'}")
        print(f"  Timer:   {result['timer'] if result['timer'] is not None else '❌ FAILED'}")
        if result['errors']:
            print(f"  Errors:")
            for error in result['errors']:
                print(f"    - {error}")
    
    # Recommendations
    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    
    failed_logins = [r for r in all_results if not r['login']]
    failed_balances = [r for r in all_results if r['login'] and r['balance'] is None]
    failed_timers = [r for r in all_results if r['login'] and r['timer'] is None]
    
    if failed_logins:
        print(f"\n❌ {len(failed_logins)} faucets have LOGIN failures:")
        for r in failed_logins:
            print(f"   - {r['faucet']}: Update selectors, check credentials")
    
    if failed_balances:
        print(f"\n⚠️  {len(failed_balances)} faucets cannot extract BALANCE:")
        for r in failed_balances:
            print(f"   - {r['faucet']}: Update balance selectors in get_balance()")
    
    if failed_timers:
        print(f"\n⚠️  {len(failed_timers)} faucets cannot extract TIMER:")
        for r in failed_timers:
            print(f"   - {r['faucet']}: Update timer selectors in get_timer()")
    
    successful = [r for r in all_results if r['login'] and r['balance'] is not None and r['timer'] is not None]
    if successful:
        print(f"\n✅ {len(successful)} faucets are FULLY FUNCTIONAL:")
        for r in successful:
            print(f"   - {r['faucet']}")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    # Force visible mode
    import os
    os.environ['HEADLESS'] = 'false'
    
    asyncio.run(main())
