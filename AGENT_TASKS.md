# Agent Task Delegation Plan

## Current System Status
- **Proxies**: ✅ Working (11 healthy: 3 DO + 8 Azure)
- **Mode**: ✅ NORMAL (exited LOW_PROXY)
- **Bots**: ❌ BROKEN (0 successful claims since Jan 30)
- **Last Success**: Jan 30 17:03 - FreeBitcoin (0.0 BTC extracted)

## Critical Issues Identified
1. All faucets failing with Cloudflare blocks, login timeouts, or browser crashes
2. FreeBitcoin: 100% login failure rate
3. Pick.io family: 11 faucets missing login implementation
4. Browser stability: "Target page, context or browser has been closed" errors
5. Dead proxy fallback: System trying to use known-dead proxies
6. Amount extraction failing (successful claims showing 0.0 balance)

---

## HIGH PRIORITY TASKS (Fix These First)

### Task 1: Fix FreeBitcoin Bot ✅ IMPROVED
**Agent**: Bot Debugger / Selector Specialist
**Priority**: CRITICAL
**Files**: `faucets/freebitcoin.py`
**Status**: ⚠️ **IMPROVED** - Pending User Validation (Feb 1, 2026)

**Problem**: 100% login failure rate
**Root Cause**: Outdated selectors, insufficient error handling, potential signup form conflicts
**Improvements Implemented**:
1. ✅ Enhanced email/username selectors (+5 patterns including HTML5 autocomplete)
2. ✅ Enhanced password selectors (+3 patterns with signup exclusion)
3. ✅ Extended Cloudflare handling (90s → 120s with error recovery)
4. ✅ Added page health checks before credential entry (Task 2 integration)
5. ✅ Implemented credential fill fallback for robustness
6. ✅ Added explicit signup form exclusion to prevent wrong form selection

**Key Changes**:
- Added HTML5 autocomplete attribute selectors (`autocomplete='username'`, `autocomplete='email'`, `autocomplete='current-password'`)
- Explicit exclusion of signup forms: `:not([form*='signup']):not([form*='register'])`
- Extended Cloudflare timeout from 90s to 120s for slow proxies
- Page health validation before filling credentials (prevents "Target closed" errors)
- Fallback to direct `fill()` if `human_type()` fails

**Testing Required**:
```bash
# User must test with actual credentials
python main.py --single freebitcoin --visible --once

# Check results
tail -50 logs/faucet_bot.log | findstr /I "freebitcoin"
```

**Success Criteria**: ⚠️ **PENDING** - Successful login + balance retrieved

**Documentation**: 
- Improvements: `docs/fixes/FREEBITCOIN_FIX_FEBRUARY_2026.md`
- Previous fix: `docs/FREEBITCOIN_FIX_JANUARY_2026.md`

**Next Steps**:
1. User validates with test run
2. If still failing: inspect live site with DevTools
3. Monitor success rate over 24 hours

---

### Task 2: Fix Browser Crash Issue  
**Agent**: Browser Automation Specialist
**Priority**: CRITICAL
**Files**: `browser/instance.py`, `browser/stealth_hub.py`

**Problem**: "Target page, context or browser has been closed" errors during all operations
**Root Cause**: Browser context lifecycle management issues
**Action Items**:
- Debug browser context creation/cleanup in instance.py
- Check for race conditions between context close and operations
- Review Camoufox initialization parameters
- Add error handling for closed context scenarios
- Implement context health checks before operations

**Success Criteria**: Bots run without "Target closed" errors for 30+ minutes

---

### Task 3: Fix FireFaucet Cloudflare Bypass
**Agent**: Anti-Detection Specialist  
**Priority**: CRITICAL
**Files**: `faucets/firefaucet.py`, `browser/stealth_hub.py`

**Problem**: Cloudflare protection blocking access ("maintenance/security pattern found")
**Root Cause**: Insufficient stealth or captcha handling
**Action Items**:
- Verify Camoufox stealth settings for Cloudflare bypass
- Check if manual captcha solve needed (Cloudflare Turnstile)
- Test with different User-Agent / TLS fingerprints
- Add Cloudflare detection + handling logic
- Implement retry with enhanced stealth on detection

**Success Criteria**: FireFaucet loads without Cloudflare block

---

## MEDIUM PRIORITY TASKS

### Task 4: Implement Pick.io Family Login (11 Faucets) ✅ COMPLETE
**Agent**: Code Generator / Template Specialist
**Priority**: HIGH
**Status**: ✅ **COMPLETE** - Login already implemented via inheritance
**Files**: `faucets/litepick.py`, `dogepick.py`, `solpick.py`, `binpick.py`, `bchpick.py`, `tonpick.py`, `polygonpick.py`, `dashpick.py`, `ethpick.py`, `usdpick.py`

**Problem**: 11 faucets missing login implementation ✅ SOLVED
**Reference**: `faucets/tronpick.py` (working implementation)
**Action Items**:
- ✅ Review tronpick.py as reference implementation
- ✅ Verify all Pick.io faucets inherit from pick_base.py (ALL 11 CONFIRMED)
- ✅ Ensure each implements: get_balance(), get_timer(), claim() (ALL 11 CONFIRMED)
- ⚠️ Test login flow for each faucet (TEST SCRIPT CREATED - pending user credentials)
- ✅ Document which faucets work vs need fixes (see docs/PICKIO_IMPLEMENTATION_STATUS.md)

**Key Findings**:
- ✅ All 11 faucets already inherit from `PickFaucetBase` which provides complete login implementation
- ✅ All faucets registered in `core/registry.py`
- ✅ All configuration properties exist in `core/config.py`
- ✅ All required methods implemented (get_balance, get_timer, claim)
- ✅ `.env.example` updated with credential placeholders
- ✅ Test script created: `scripts/test_pickio_login.py`
- ⚠️ Live testing requires user to add credentials to `.env`

**Success Criteria**: All 11 Pick.io faucets can login successfully ✅ READY (pending credentials)

**Documentation**: See `docs/PICKIO_IMPLEMENTATION_STATUS.md` for complete details

**Next Steps for User**:
1. Add credentials to `.env` for each Pick.io faucet
2. Run test: `python scripts/test_pickio_login.py`
3. Test individual faucets: `python main.py --single litepick --visible`

---

### Task 5: Fix Dead Proxy Fallback Logic ✅ COMPLETED
**Agent**: Proxy Management Specialist
**Priority**: MEDIUM  
**Files**: `core/proxy_manager.py`
**Completed**: January 31, 2026

**Problem**: System trying to use known-dead proxies (142.93.66.75, 167.99.207.160)
**Root Cause**: get_proxy_for_profile() not properly filtering dead/cooldown proxies
**Solution**: 
- Updated assign_proxies() to filter dead/cooldown proxies during initial assignment
- Improved rotate_proxy() with better fallback logic and comprehensive logging
- Added detailed error messages when all proxies exhausted
- Created test suite (test_proxy_fallback.py) - all 5 tests passing

**Documentation**: docs/fixes/PROXY_FALLBACK_FIX_JAN31_2026.md
**Success Criteria**: ✅ Only healthy proxies used; ✅ warning logged if none available

---

### Task 6: Fix Claim Result Tracking
**Agent**: Data Extraction Specialist
**Priority**: MEDIUM
**Files**: `core/extractor.py`, `core/analytics.py`

**Problem**: Successful claims showing 0.0 BTC (amount extraction failing)
**Root Cause**: DataExtractor not parsing balance correctly
**Action Items**:
- Review balance extraction selectors for each faucet
- Test with actual faucet pages (screenshots if needed)  
- Update regex patterns for currency amounts
- Verify ClaimResult has correct values before saving
- Add validation before writing to earnings_analytics.json

**Success Criteria**: Successful claim shows actual amount > 0

---

### Task 7: Update Cointiply Bot Selectors
**Agent**: Selector Maintenance Specialist
**Priority**: MEDIUM
**Files**: `faucets/cointiply.py`

**Problem**: Login navigation timeouts, "Target page closed" errors
**Root Cause**: Site structure may have changed
**Action Items**:
- Inspect current Cointiply login page
- Update login selectors
- Fix navigation timeout issues  
- Test claim flow end-to-end
- Document working flow

**Success Criteria**: Cointiply login + claim succeeds

---

## LOW PRIORITY / INFRASTRUCTURE TASKS

### Task 8: Validate Proxy Health Detection
**Agent**: DevOps / Testing Specialist
**Priority**: LOW (proxies working, but validation needed)
**Files**: `config/proxy_health.json`, `core/proxy_manager.py`

**Action Items**:
- Test all 11 proxies: `curl -x http://{IP}:8888 http://ipinfo.io/ip`
- Verify proxy_health.json accuracy
- Remove stale dead entries
- Document proxy latency/performance
- Set up automated health checks

**Success Criteria**: proxy_health.json matches actual proxy status

---

### Task 9: Add Comprehensive Logging
**Agent**: Logging/Observability Specialist  
**Priority**: LOW (helps debugging but not blocker)
**Files**: `faucets/base.py`, `core/orchestrator.py`

**Action Items**:
- Add structured logging at claim lifecycle stages:
  - login_start, login_success, balance_check, timer_check
  - captcha_solve, claim_submit, claim_verify, result_record
- Include timestamps, faucet name, account, proxy used
- Log failure reasons with context
- Create log analysis script

**Success Criteria**: Can trace full claim lifecycle in logs

---

### Task 10: Fix Permanent Failure Classification  
**Agent**: Error Handling Specialist
**Priority**: LOW
**Files**: `core/orchestrator.py` (classify_error method)

**Problem**: FireFaucet permanently disabled after single Cloudflare block
**Root Cause**: classify_error treats security challenges as permanent
**Action Items**:
- Review error classification logic
- Cloudflare/security should be "retryable" not "permanent"
- Implement retry limits before permanent disable
- Add manual re-enable mechanism  
- Document error categories

**Success Criteria**: Accounts not disabled on first security challenge

---

### Task 11: Individual Faucet Testing
**Agent**: QA/Testing Specialist
**Priority**: MEDIUM (after fixes applied)
**Command**: `python main.py --single {faucet} --visible`

**Test Each**:
1. firefaucet - Test Cloudflare bypass
2. freebitcoin - Test login fix
3. cointiply - Test selector updates  
4. litepick - Test Pick.io login
5. tronpick - Verify reference implementation still works

**Success Criteria**: Document which faucets work vs remain broken

---

### Task 12: Create Monitoring Dashboard
**Agent**: Dashboard/Analytics Developer
**Priority**: LOW (nice-to-have)
**Files**: `core/dashboard_builder.py` or new `core/monitoring.py`

**Action Items**:
- Track per-faucet metrics:
  - Success rate (last 24h, 7d, 30d)
  - Average claim time
  - Failure reasons breakdown  
  - Last successful claim timestamp
- Add alerting for prolonged failures (>24h)
- Create simple web dashboard or CLI tool
- Integrate with existing analytics

**Success Criteria**: Real-time view of faucet health

---

## Recommended Agent Assignments

### GitRepoHandler Agent
- Manages all git operations (commits, PRs, branch cleanup)
- Ensures work stays on master branch
- Handles merge conflicts

### BotDebugger Agent
- Tasks 1, 6, 7 (FreeBitcoin, Cointiply, claim tracking)
- Focus on selector updates and login fixes

### BrowserExpert Agent  
- Tasks 2, 3 (browser crashes, Cloudflare bypass)
- Deep knowledge of Playwright/Camoufox

### CodeGenerator Agent
- Task 4 (Pick.io family implementation)
- Template-based code generation

### InfrastructureAgent
- Tasks 5, 8, 10 (proxy logic, health checks, error handling)
- System reliability improvements

### QA/TestingAgent
- Task 11 (individual faucet testing)
- Validates all fixes work end-to-end

---

## Execution Priority

**Week 1 (Critical Fixes)**:
1. Task 2: Fix browser crashes (blocks everything)
2. Task 1: Fix FreeBitcoin (highest value faucet)
3. Task 3: Fix FireFaucet Cloudflare bypass

**Week 2 (Feature Complete)**:
4. Task 4: Implement Pick.io family (11 faucets)
5. Task 5: Fix dead proxy fallback
6. Task 7: Update Cointiply

**Week 3 (Quality & Monitoring)**:
7. Task 6: Fix claim tracking
8. Task 11: Individual testing
9. Task 8: Validate proxy health
10. Task 9: Add logging
11. Task 10: Fix error classification
12. Task 12: Monitoring dashboard

---

## Success Metrics

**Before Fixes**:
- ❌ 0 successful claims in last 24 hours
- ❌ $0.0060 costs, $0.0000 earnings  
- ❌ 100% failure rate

**After Fixes (Target)**:
- ✅ 5+ successful claims per day
- ✅ Positive ROI (earnings > costs)
- ✅ <20% failure rate
- ✅ All major faucets operational

---

## How to Delegate

Use the runSubagent tool with specific agent names:

```
runSubagent(
  agentName="GitRepoHandler",
  description="Fix FreeBitcoin login",
  prompt="Fix the FreeBitcoin bot login failure. The bot has 100% failure rate. Investigate faucets/freebitcoin.py, update login selectors, test with --single freebitcoin until successful. Commit working code to master."
)
```

Or use specialized agents from the agent catalog for specific domains.
