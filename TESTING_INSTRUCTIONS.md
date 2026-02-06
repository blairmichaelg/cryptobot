# Testing Instructions for FreeBitcoin Claim Fix

## Overview
This fix addresses the FreeBitcoin claim flow issue where balance extraction was failing due to incorrect selector usage.

## Quick Validation (Local)
Run the validation script to ensure all changes are correctly applied:
```bash
python3 validate_freebitcoin_fix.py
```

Expected output: ✅ All validations passed!

## End-to-End Testing (Azure VM)

### Prerequisites
- Access to Azure VM with FreeBitcoin credentials configured
- Git access to pull the branch

### Steps

1. **SSH to Azure VM**
   ```bash
   ssh <username>@<vm-ip-address>
   ```

2. **Navigate to repository**
   ```bash
   cd ~/Repositories/cryptobot
   ```

3. **Pull the fix branch**
   ```bash
   git fetch origin
   git checkout copilot/debug-freebitcoin-claim-flow
   git pull
   ```

4. **Run the detailed test**
   ```bash
   HEADLESS=true python3 test_freebitcoin_claim_detailed.py
   ```

### Expected Results

The test should complete successfully with output showing:

1. ✅ **STEP 1: LOGIN** - Login successful
2. ✅ **STEP 2: BALANCE EXTRACTION** - Shows actual balance (not "0")
3. ✅ **STEP 3: TIMER EXTRACTION** - Shows timer value or 0 if ready
4. ✅ **STEP 4: FULL CLAIM** - Claim succeeds or shows timer active

### Success Criteria

- Balance extraction returns a value (not "0" or empty)
- Timer extraction works correctly
- If claim is available:
  - Claim succeeds
  - Balance or timer updates confirm the claim
- If timer is active:
  - Status shows "Timer Active"
  - Next claim time is reasonable (> 0 minutes)

### Troubleshooting

If balance still shows "0":
1. Check that #balance_small selector exists on the page
2. Verify credentials are correct
3. Check browser console for errors

If claim fails:
1. Check the debug logs for detailed error messages
2. Verify CAPTCHA solving is working
3. Ensure proxy/network connectivity

## Production Deployment

After successful testing:

1. Merge the PR
2. Deploy to production VM
3. Monitor first few claims for success
4. Check analytics for claim success rate improvement

## Documentation

See `docs/FREEBITCOIN_CLAIM_FIX.md` for complete technical details.
