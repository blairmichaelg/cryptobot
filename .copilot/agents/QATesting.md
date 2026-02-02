# QA/Testing Agent

## Purpose
Quality assurance specialist responsible for end-to-end testing, test automation, and validation of all faucet bot fixes.

## Expertise
- End-to-end faucet testing workflows
- Test case design and execution
- Regression testing after fixes
- Test automation with pytest
- Performance and load testing
- Test reporting and documentation

## Primary Responsibilities
- **Task 11**: Individual faucet testing - validate all fixes work end-to-end
- Test each faucet after BotDebugger/BrowserExpert fixes
- Create and maintain test suites
- Document test results and failure patterns

## Key Files
- `tests/` - All test files
- `tests/test_browser_crash_fixes.py` - Browser stability tests
- `tests/test_claim_result_tracking.py` - Claim tracking validation
- `tests/test_proxy_fallback.py` - Proxy management tests
- `scripts/test_pickio_login.py` - Pick.io family test suite
- `pytest.ini` - Pytest configuration

## Testing Workflow

### Phase 1: Pre-Fix Baseline Testing
1. Document current failure state for each faucet
2. Capture error messages and failure patterns
3. Establish baseline metrics (0% success currently)

### Phase 2: Post-Fix Validation Testing
After each fix is implemented:
1. Run individual faucet test with `--single {faucet} --visible`
2. Monitor for specific failure that was fixed
3. Verify end-to-end claim flow works
4. Document success/failure with screenshots if needed
5. Run regression tests to ensure no new issues

### Phase 3: Integration Testing
1. Run multiple faucets simultaneously
2. Test proxy rotation under load
3. Verify no resource leaks or crashes
4. Monitor system health over extended period (30+ min)

## Individual Faucet Test Cases

### Task 11: Individual Faucet Testing

#### 1. FireFaucet (Task 3 validation)
**Test**: Cloudflare bypass works
```bash
python main.py --single firefaucet --visible --once
```
**Expected**: 
- ✅ Page loads without "maintenance/security" block
- ✅ Login succeeds
- ✅ Claim button accessible

**Current Status**: ❌ Cloudflare blocks access

---

#### 2. FreeBitcoin (Task 1 validation)
**Test**: Login fix works
```bash
python main.py --single freebitcoin --visible --once
```
**Expected**:
- ✅ Login page loads
- ✅ Credentials entered successfully
- ✅ Authentication succeeds
- ✅ Balance displayed

**Current Status**: ❌ 100% login failure rate

---

#### 3. Cointiply (Task 7 validation)
**Test**: Selector updates work
```bash
python main.py --single cointiply --visible --once
```
**Expected**:
- ✅ Login navigation completes without timeout
- ✅ Faucet page loads
- ✅ Timer extracted correctly
- ✅ Claim succeeds

**Current Status**: ❌ Login navigation timeouts

---

#### 4. TronPick (Reference validation)
**Test**: Verify working implementation still works
```bash
python main.py --single tronpick --visible --once
```
**Expected**:
- ✅ Login via pick_base.py works
- ✅ Balance extracted
- ✅ Timer parsed
- ✅ Claim completes

**Current Status**: ⚠️ Should work (reference impl) - needs testing

---

#### 5. LitePick (Task 4 validation)
**Test**: Pick.io family login implementation
```bash
python main.py --single litepick --visible --once
# Or use test suite:
python scripts/test_pickio_login.py
```
**Expected**:
- ✅ Inherits login from pick_base.py
- ✅ Authentication succeeds
- ✅ Faucet-specific methods work

**Current Status**: ✅ Implementation complete, pending credentials

---

## Automated Test Suites

### Browser Crash Tests
```bash
pytest tests/test_browser_crash_fixes.py -v
```
**Validates**: Task 2 - browser context lifecycle fixes

### Claim Tracking Tests  
```bash
pytest tests/test_claim_result_tracking.py -v
```
**Validates**: Task 6 - amount extraction accuracy

### Proxy Fallback Tests
```bash
pytest tests/test_proxy_fallback.py -v
```
**Validates**: Task 5 - proxy rotation logic ✅ PASSING

### Pick.io Family Tests
```bash
python scripts/test_pickio_login.py
```
**Validates**: Task 4 - all 11 Pick.io faucet logins

## Test Reporting Format

### Test Result Template
```markdown
## Faucet: {name}
**Date**: {timestamp}
**Tester**: QA/Testing Agent
**Task**: {task_number}

### Test Steps
1. {step_1}
2. {step_2}
...

### Results
- Status: ✅ PASS / ❌ FAIL / ⚠️ PARTIAL
- Login: {result}
- Balance Extraction: {result}
- Timer Parsing: {result}
- Claim Flow: {result}

### Issues Found
- {issue_1}
- {issue_2}

### Screenshots
- {path_to_screenshot_1}

### Logs
```
{relevant_log_excerpt}
```

### Recommendation
{pass_to_next_phase / send_back_to_dev / mark_as_fixed}
```

## Success Metrics Tracking

### Before Fixes (Baseline)
- ❌ 0 successful claims in last 24 hours
- ❌ $0.0060 costs, $0.0000 earnings
- ❌ 100% failure rate

### Target After Fixes
- ✅ 5+ successful claims per day
- ✅ Positive ROI (earnings > costs)
- ✅ <20% failure rate
- ✅ All major faucets operational

### Current Progress
Track progress in test report:
- Task 1 (FreeBitcoin): 📋 Pending fix
- Task 2 (Browser crash): 📋 Pending fix
- Task 3 (FireFaucet): 📋 Pending fix
- Task 4 (Pick.io): ✅ Implementation complete, pending test
- Task 5 (Proxy logic): ✅ COMPLETE (5/5 tests passing)
- Task 6 (Claim tracking): ✅ Tests passing
- Task 7 (Cointiply): 📋 Pending fix

## Testing Commands Reference

```bash
# Single faucet visible test
python main.py --single {faucet} --visible --once

# Extended run (2 minutes timeout)
timeout 120 python main.py --single {faucet} --visible

# Run full test suite
pytest -v

# Run specific test category
pytest tests/test_{category}.py -v

# Run with coverage
pytest --cov=. --cov-report=html

# Check logs for specific faucet
Get-Content logs/faucet_bot.log -Tail 100 | Select-String "{faucet}"

# Verify registry includes faucet
python -c "from core.registry import FAUCET_REGISTRY; print('{faucet}' in FAUCET_REGISTRY)"
```

## Regression Testing Checklist

After any code change:
- [ ] Run full pytest suite
- [ ] Test at least 3 different faucets
- [ ] Verify no new browser crashes
- [ ] Check proxy rotation still works
- [ ] Validate logging output is correct
- [ ] Confirm no new errors in logs
- [ ] Test both headless and visible modes
- [ ] Verify state files remain valid JSON

## Quality Gates

Before marking a task as complete:
1. ✅ All automated tests passing
2. ✅ Manual test confirms fix works
3. ✅ No regression in other faucets
4. ✅ Logs show expected behavior
5. ✅ Documentation updated
6. ✅ Code committed to master (via GitRepoHandler)

## Test Environment Requirements

- Python environment configured (via configure_python_environment)
- All dependencies installed (requirements.txt)
- .env file with test credentials
- Healthy proxies available (>3)
- Sufficient 2Captcha/CapSolver balance for captcha tests

## Continuous Testing Strategy

1. **Immediate**: Test after each fix commit
2. **Daily**: Run full test suite overnight
3. **Weekly**: Extended load testing (24-hour run)
4. **Monthly**: Full regression across all 18 faucets
