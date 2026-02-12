#!/usr/bin/env python3
"""Analyze claim history to determine if bot is actually earning."""
import json
from pathlib import Path

analytics_file = Path.home() / "Repositories/cryptobot/earnings_analytics.json"

with open(analytics_file) as f:
    data = json.load(f)

claims = data.get("claims", [])
costs = data.get("costs", [])

print("=" * 60)
print("CLAIM ANALYSIS")
print("=" * 60)

# Overall stats
total_claims = len(claims)
successful = [c for c in claims if c.get("success")]
failed = [c for c in claims if not c.get("success")]

print(f"\nTotal Claims: {total_claims}")
print(f"  ✓ Successful: {len(successful)}")
print(f"  ✗ Failed: {len(failed)}")

# By faucet
faucets = {}
for claim in claims:
    faucet = claim.get("faucet", "Unknown")
    if faucet not in faucets:
        faucets[faucet] = {"success": 0, "failed": 0, "amounts": []}
    
    if claim.get("success"):
        faucets[faucet]["success"] += 1
        amt = claim.get("amount", 0)
        if amt and isinstance(amt, (int, float)) and amt > 0:
            faucets[faucet]["amounts"].append(amt)
    else:
        faucets[faucet]["failed"] += 1

print("\n" + "=" * 60)
print("BY FAUCET")
print("=" * 60)

for faucet, stats in sorted(faucets.items()):
    print(f"\n{faucet}:")
    print(f"  Success: {stats['success']}")
    print(f"  Failed: {stats['failed']}")
    if stats['amounts']:
        total = sum(stats['amounts'])
        avg = total / len(stats['amounts'])
        print(f"  Amounts: {len(stats['amounts'])} non-zero")
        print(f"  Total: {total}")
        print(f"  Average: {avg:.2f}")
    else:
        print(f"  ⚠️  NO NON-ZERO AMOUNTS RECORDED")

# Check for suspicious patterns
print("\n" + "=" * 60)
print("SUSPICIOUS PATTERNS")
print("=" * 60)

# Check if all amounts are the same (placeholder values)
all_amounts = []
for claim in successful:
    amt = claim.get("amount", 0)
    if amt and isinstance(amt, (int, float)):
        all_amounts.append(amt)

if all_amounts:
    unique_amounts = set(all_amounts)
    if len(unique_amounts) == 1:
        print(f"⚠️  ALL {len(all_amounts)} amounts are identical: {list(unique_amounts)[0]}")
        print("   This suggests placeholder values, not real earnings!")
    elif len(unique_amounts) < 5 and len(all_amounts) > 20:
        print(f"⚠️  Only {len(unique_amounts)} unique amounts across {len(all_amounts)} claims")
        print(f"   Values: {sorted(unique_amounts)}")
else:
    print("❌ NO AMOUNTS RECORDED AT ALL")

# Balance tracking
balances = [c.get("balance_after", 0) for c in successful if c.get("balance_after")]
if not balances or all(b == 0 for b in balances):
    print("❌ Balance tracking appears broken - all zeros or missing")

# Cost analysis
total_cost = sum(c.get("amount_usd", 0) for c in costs)
print("\n" + "=" * 60)
print("COST ANALYSIS")
print("=" * 60)
print(f"Total Captcha Costs: ${total_cost:.2f}")
print(f"Number of Captchas: {len(costs)}")

# Last 5 claims
print("\n" + "=" * 60)
print("LAST 5 CLAIMS")
print("=" * 60)
for claim in claims[-5:]:
    from datetime import datetime
    ts = claim.get("timestamp", 0)
    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "Unknown"
    faucet = claim.get("faucet", "Unknown")
    success = "✓" if claim.get("success") else "✗"
    amount = claim.get("amount", 0)
    balance = claim.get("balance_after", "Unknown")
    print(f"{dt} | {faucet:15} | {success} | Amt: {amount} | Bal: {balance}")

print("\n" + "=" * 60)
