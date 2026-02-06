#!/usr/bin/env python3
"""
Task 11: Individual Faucet Testing Script
Tests each faucet systematically and generates a report
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# Load analytics data
analytics_file = Path("earnings_analytics.json")
if analytics_file.exists():
    with open(analytics_file) as f:
        data = json.load(f)
else:
    print("ERROR: earnings_analytics.json not found")
    sys.exit(1)

# Target faucets
target_faucets = ['firefaucet', 'freebitcoin', 'cointiply', 'litepick', 'tronpick']

print("=" * 80)
print("TASK 11: INDIVIDUAL FAUCET TESTING RESULTS")
print("=" * 80)
print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Analyze each faucet
all_claims = data.get('claims', [])

for faucet in target_faucets:
    print(f"\n{'='*80}")
    print(f"FAUCET: {faucet.upper()}")
    print(f"{'='*80}")
    
    # Filter claims for this faucet
    faucet_claims = [c for c in all_claims if faucet.lower() in c.get('faucet', '').lower()]
    
    if not faucet_claims:
        print("❌ STATUS: NO CLAIMS FOUND - Never tested or not registered")
        print("   VERDICT: BROKEN - Not operational")
        continue
    
    # Get statistics
    total = len(faucet_claims)
    successful = sum(1 for c in faucet_claims if c.get('success'))
    failed = total - successful
    success_rate = (successful / total * 100) if total > 0 else 0
    
    # Recent claims (last 10)
    recent = faucet_claims[-10:]
    recent_success = sum(1 for c in recent if c.get('success'))
    recent_rate = (recent_success / len(recent) * 100) if recent else 0
    
    # Last successful claim
    last_success = next((c for c in reversed(faucet_claims) if c.get('success')), None)
    
    # Print results
    print(f"Total Claims: {total}")
    print(f"Successful: {successful} ({success_rate:.1f}%)")
    print(f"Failed: {failed}")
    print(f"Recent Success Rate (last 10): {recent_success}/10 ({recent_rate:.0f}%)")
    
    if last_success:
        ts = last_success.get('timestamp', 0)
        dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else 'Unknown'
        amount = last_success.get('amount', 0)
        print(f"Last Success: {dt} (Amount: {amount})")
    else:
        print(f"Last Success: NEVER")
    
    # Determine verdict
    if recent_rate >= 80:
        verdict = "✅ WORKING - High success rate"
    elif recent_rate >= 50:
        verdict = "⚠️  UNSTABLE - Moderate success rate"  
    elif recent_rate > 0:
        verdict = "❌ MOSTLY BROKEN - Low success rate"
    else:
        verdict = "❌ COMPLETELY BROKEN - 0% success"
    
    print(f"\nVERDICT: {verdict}")
    
    # Show recent errors
    recent_errors = [c.get('error', '') for c in recent if not c.get('success') and c.get('error')]
    if recent_errors:
        print(f"\nRecent Errors:")
        for err in set(recent_errors):
            if err:
                print(f"  - {err[:100]}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

# Overall summary
summary = {}
for faucet in target_faucets:
    faucet_claims = [c for c in all_claims if faucet.lower() in c.get('faucet', '').lower()]
    if not faucet_claims:
        summary[faucet] = "NOT TESTED"
    else:
        recent = faucet_claims[-10:]
        recent_success = sum(1 for c in recent if c.get('success'))
        if recent_success >= 8:
            summary[faucet] = "WORKING ✅"
        elif recent_success >= 5:
            summary[faucet] = "UNSTABLE ⚠️"
        else:
            summary[faucet] = "BROKEN ❌"

for faucet, status in summary.items():
    print(f"{faucet:15} : {status}")

print("\n" + "=" * 80)
