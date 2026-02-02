#!/usr/bin/env python3
"""
Log Analysis Script for Cryptobot Farm

Analyzes structured lifecycle logs to provide insights into:
- Claim success/failure patterns
- Common failure points in the claim lifecycle
- Performance metrics (timing for each stage)
- Error type distribution
- Faucet-specific issues

Usage:
    python scripts/analyze_logs.py [--hours 24] [--faucet firefaucet] [--failures-only]
"""

import argparse
import re
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json

# Lifecycle stages we track
LIFECYCLE_STAGES = [
    "login_start",
    "login_success",
    "login_failed",
    "balance_check_start",
    "balance_check",
    "timer_check_start",
    "timer_check",
    "claim_submit_start",
    "claim_submit",
    "claim_submit_failed",
    "claim_verify",
    "result_record",
    "captcha_solve_start",
    "captcha_solve"
]

# Regex pattern to match lifecycle logs
LIFECYCLE_PATTERN = re.compile(
    r'\[LIFECYCLE\]\s+(?P<stage>\w+)\s+\|\s+'
    r'(?P<params>.*?)\s+\|\s+'
    r'timestamp=(?P<timestamp>\d+)'
)

def parse_lifecycle_log(line: str) -> Optional[Dict]:
    """Parse a lifecycle log line into structured data."""
    match = LIFECYCLE_PATTERN.search(line)
    if not match:
        return None
    
    stage = match.group('stage')
    timestamp = int(match.group('timestamp'))
    params_str = match.group('params')
    
    # Parse key=value pairs
    params = {}
    for param in params_str.split(' | '):
        if '=' in param:
            key, value = param.split('=', 1)
            params[key.strip()] = value.strip()
    
    return {
        'stage': stage,
        'timestamp': timestamp,
        'datetime': datetime.fromtimestamp(timestamp),
        **params
    }

def analyze_claim_lifecycle(events: List[Dict]) -> Dict:
    """Analyze a complete claim lifecycle from start to finish."""
    # Group events by faucet + account + timestamp proximity
    claims = defaultdict(list)
    
    for event in events:
        faucet = event.get('faucet', 'unknown')
        account = event.get('account', 'unknown')
        timestamp = event['timestamp']
        
        # Find or create claim group (events within 5 minutes of claim_submit_start)
        key = f"{faucet}:{account}"
        placed = False
        
        for claim_ts, claim_events in claims.items():
            if abs(timestamp - claim_ts) < 300:  # 5 minutes
                claim_events.append(event)
                placed = True
                break
        
        if not placed and event['stage'] == 'claim_submit_start':
            claims[timestamp] = [event]
    
    return claims

def calculate_stage_durations(claim_events: List[Dict]) -> Dict[str, float]:
    """Calculate time spent in each lifecycle stage."""
    durations = {}
    stages_by_time = sorted(claim_events, key=lambda e: e['timestamp'])
    
    for i in range(len(stages_by_time) - 1):
        current = stages_by_time[i]
        next_event = stages_by_time[i + 1]
        duration = next_event['timestamp'] - current['timestamp']
        durations[current['stage']] = duration
    
    return durations

def analyze_log_file(log_file: Path, hours: int = 24, faucet_filter: Optional[str] = None, failures_only: bool = False) -> Dict:
    """Analyze lifecycle logs from the log file."""
    
    cutoff_time = datetime.now() - timedelta(hours=hours)
    events = []
    
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if '[LIFECYCLE]' not in line:
                continue
            
            event = parse_lifecycle_log(line)
            if not event:
                continue
            
            # Filter by time
            if event['datetime'] < cutoff_time:
                continue
            
            # Filter by faucet
            if faucet_filter and event.get('faucet', '').lower() != faucet_filter.lower():
                continue
            
            events.append(event)
    
    if not events:
        return {"error": "No lifecycle events found in the specified timeframe"}
    
    # Analyze claims
    claims = analyze_claim_lifecycle(events)
    
    # Calculate statistics
    stats = {
        "total_claims": len([e for e in events if e['stage'] == 'claim_submit_start']),
        "successful_claims": len([e for e in events if e['stage'] == 'result_record' and e.get('success') == 'true']),
        "failed_claims": len([e for e in events if e['stage'] == 'result_record' and e.get('success') == 'false']),
        "login_attempts": len([e for e in events if e['stage'] == 'login_start']),
        "login_successes": len([e for e in events if e['stage'] == 'login_success']),
        "login_failures": len([e for e in events if e['stage'] == 'login_failed']),
        "captcha_solves": len([e for e in events if e['stage'] == 'captcha_solve' and e.get('success') == 'true']),
        "captcha_failures": len([e for e in events if e['stage'] == 'captcha_solve' and e.get('success') == 'false']),
    }
    
    # Error type distribution
    error_types = Counter([e.get('error_type', 'unknown') for e in events if e.get('error_type') and e.get('error_type') != 'none'])
    
    # Per-faucet breakdown
    faucet_stats = defaultdict(lambda: {"attempts": 0, "successes": 0, "failures": 0, "success_rate": 0.0})
    for event in events:
        if event['stage'] == 'result_record':
            faucet = event.get('faucet', 'unknown')
            faucet_stats[faucet]["attempts"] += 1
            if event.get('success') == 'true':
                faucet_stats[faucet]["successes"] += 1
            else:
                faucet_stats[faucet]["failures"] += 1
    
    # Calculate success rates
    for faucet in faucet_stats:
        total = faucet_stats[faucet]["attempts"]
        if total > 0:
            faucet_stats[faucet]["success_rate"] = float((faucet_stats[faucet]["successes"] / total) * 100)
    
    # Stage-specific failures
    stage_failures = Counter([e['stage'] for e in events if 'failed' in e['stage'] or e.get('success') == 'false'])
    
    # Average claim duration (claim_submit_start to result_record)
    claim_durations = []
    for claim_ts, claim_events in claims.items():
        start_events = [e for e in claim_events if e['stage'] == 'claim_submit_start']
        end_events = [e for e in claim_events if e['stage'] == 'result_record']
        
        if start_events and end_events:
            duration = end_events[-1]['timestamp'] - start_events[0]['timestamp']
            claim_durations.append(duration)
    
    avg_claim_duration = sum(claim_durations) / len(claim_durations) if claim_durations else 0
    
    # Captcha performance
    captcha_events = [e for e in events if e['stage'] == 'captcha_solve']
    captcha_durations = [float(e.get('duration', '0').rstrip('s')) for e in captcha_events if 'duration' in e]
    avg_captcha_duration = sum(captcha_durations) / len(captcha_durations) if captcha_durations else 0
    
    # Proxy usage
    proxies_used = Counter([e.get('proxy', 'none') for e in events if 'proxy' in e])
    
    return {
        "summary": stats,
        "error_distribution": dict(error_types),
        "faucet_breakdown": dict(faucet_stats),
        "stage_failures": dict(stage_failures),
        "avg_claim_duration_seconds": round(avg_claim_duration, 1),
        "avg_captcha_duration_seconds": round(avg_captcha_duration, 1),
        "proxy_usage": dict(proxies_used),
        "time_range": {
            "start": min([e['datetime'] for e in events]).isoformat(),
            "end": max([e['datetime'] for e in events]).isoformat(),
            "hours": hours
        }
    }

def print_analysis(results: Dict):
    """Pretty-print analysis results."""
    if "error" in results:
        print(f"❌ {results['error']}")
        return
    
    print("\n" + "="*60)
    print("📊 CRYPTOBOT LIFECYCLE ANALYSIS")
    print("="*60)
    
    # Summary
    summary = results['summary']
    print(f"\n📈 SUMMARY ({results['time_range']['hours']}h)")
    print(f"   Total Claims: {summary['total_claims']}")
    print(f"   ✅ Successful: {summary['successful_claims']}")
    print(f"   ❌ Failed: {summary['failed_claims']}")
    if summary['total_claims'] > 0:
        success_rate = (summary['successful_claims'] / summary['total_claims']) * 100
        print(f"   Success Rate: {success_rate:.1f}%")
    
    print(f"\n🔐 LOGIN PERFORMANCE")
    print(f"   Attempts: {summary['login_attempts']}")
    print(f"   ✅ Successful: {summary['login_successes']}")
    print(f"   ❌ Failed: {summary['login_failures']}")
    if summary['login_attempts'] > 0:
        login_rate = (summary['login_successes'] / summary['login_attempts']) * 100
        print(f"   Success Rate: {login_rate:.1f}%")
    
    print(f"\n🔑 CAPTCHA PERFORMANCE")
    print(f"   ✅ Solved: {summary['captcha_solves']}")
    print(f"   ❌ Failed: {summary['captcha_failures']}")
    print(f"   Avg Duration: {results['avg_captcha_duration_seconds']:.1f}s")
    
    # Faucet breakdown
    print(f"\n🎯 PER-FAUCET BREAKDOWN")
    faucet_breakdown = results['faucet_breakdown']
    for faucet, stats in sorted(faucet_breakdown.items(), key=lambda x: x[1]['success_rate'], reverse=True):
        print(f"   {faucet}:")
        print(f"      Attempts: {stats['attempts']} | Success: {stats['successes']} | Failed: {stats['failures']} | Rate: {stats['success_rate']:.1f}%")
    
    # Error distribution
    if results['error_distribution']:
        print(f"\n⚠️  ERROR DISTRIBUTION")
        for error_type, count in sorted(results['error_distribution'].items(), key=lambda x: x[1], reverse=True):
            print(f"   {error_type}: {count}")
    
    # Stage failures
    if results['stage_failures']:
        print(f"\n🚧 STAGE-SPECIFIC FAILURES")
        for stage, count in sorted(results['stage_failures'].items(), key=lambda x: x[1], reverse=True):
            print(f"   {stage}: {count}")
    
    # Performance metrics
    print(f"\n⏱️  PERFORMANCE METRICS")
    print(f"   Avg Claim Duration: {results['avg_claim_duration_seconds']:.1f}s")
    print(f"   Avg Captcha Duration: {results['avg_captcha_duration_seconds']:.1f}s")
    
    # Proxy usage
    if results['proxy_usage']:
        print(f"\n🌐 PROXY USAGE")
        for proxy, count in sorted(results['proxy_usage'].items(), key=lambda x: x[1], reverse=True)[:10]:
            proxy_display = proxy if proxy != 'none' else 'No Proxy'
            print(f"   {proxy_display}: {count} events")
    
    print("\n" + "="*60)

def main():
    parser = argparse.ArgumentParser(description="Analyze cryptobot lifecycle logs")
    parser.add_argument("--hours", type=int, default=24, help="Hours of logs to analyze (default: 24)")
    parser.add_argument("--faucet", type=str, help="Filter by specific faucet name")
    parser.add_argument("--failures-only", action="store_true", help="Show only failed claims")
    parser.add_argument("--log-file", type=str, default="logs/faucet_bot.log", help="Path to log file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    log_file = Path(args.log_file)
    if not log_file.exists():
        print(f"❌ Log file not found: {log_file}")
        return
    
    results = analyze_log_file(log_file, args.hours, args.faucet, args.failures_only)
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_analysis(results)

if __name__ == "__main__":
    main()
