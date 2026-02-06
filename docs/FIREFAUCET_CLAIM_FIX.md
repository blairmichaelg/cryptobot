# FireFaucet Claim Button Fix (Issue #86)

## Problem Description

FireFaucet login succeeded and navigated to `/faucet` page, but the claim page showed 0 buttons and 0 submit inputs during button detection phase.

## Root Cause

The claim button (`#get_reward_button`) exists on the page but has a **9-second JavaScript countdown timer** that keeps it disabled until the timer completes:

1. Initial button state: `disabled="disabled"` with text "Please Wait (9)"
2. Timer counts down: "Please Wait (8)", "Please Wait (7)", etc.
3. Final state (after 9s): `disabled` attribute removed, text changes to "Get Reward"

### Previous Code Behavior

```python
# Old code waited only 5 seconds after navigation
await asyncio.sleep(5)
await self.page.wait_for_selector("button, input[type='submit']", timeout=15000)

# Then waited up to 3 more seconds if button was disabled
if not is_enabled or is_disabled_attr is not None:
    await asyncio.sleep(3)  # Only 8 seconds total - not enough!
```

The button exists and is detected, but it's still disabled because only 8 seconds have elapsed (5 + 3) while the timer requires 9 seconds.

## Solution

### 1. Wait for Specific Button Element

Changed from generic button selector to specific `#get_reward_button`:

```python
await self.page.wait_for_selector("#get_reward_button", timeout=15000)
```

### 2. Wait for Countdown Timer to Complete

Added JavaScript evaluation to wait for both text change AND disabled removal:

```python
await self.page.wait_for_function(
    """() => {
        const btn = document.getElementById('get_reward_button');
        if (!btn) return false;
        const text = btn.textContent || btn.innerText;
        return text.includes('Get Reward') && !btn.disabled;
    }""",
    timeout=15000
)
```

This waits until:
- Button text contains "Get Reward" (not "Please Wait")
- Button's `disabled` property is `false`

### 3. Prioritize Button Selector

Moved `#get_reward_button` to the top of the selector list to ensure it's found first:

```python
faucet_btn_selectors = [
    "#get_reward_button",         # Primary - specific to FireFaucet
    "button:has-text('Get Reward')",
    "form#faucetform button[type='submit']",
    # ... other fallbacks
]
```

### 4. Remove Redundant Waits

Removed the old 5-second sleep and 3-second retry logic since the countdown timer wait handles it properly.

## Changes Made

### Files Modified

1. **faucets/firefaucet.py**
   - Line ~645: Changed wait logic from generic to specific button
   - Lines ~656-672: Added countdown timer wait with JavaScript evaluation
   - Lines ~739-761: Reordered button selectors with `#get_reward_button` first
   - Lines ~805-814: Simplified button state checking (removed retry wait)

2. **diagnose_firefaucet_claim.py** (new)
   - Comprehensive diagnostic tool for troubleshooting FireFaucet claim page
   - Monitors button state during countdown timer
   - Saves screenshots and HTML for analysis

3. **test_firefaucet_claim_fix.py** (new)
   - Focused test script to validate the fix
   - Tests login and claim flow
   - Captures final state for verification

## Testing Instructions

### Local Testing (if browser available)

```bash
# Run diagnostic script to see countdown timer in action
python3 diagnose_firefaucet_claim.py

# Run focused test
python3 test_firefaucet_claim_fix.py
```

### Azure VM Testing (Required - Linux headless environment)

```bash
# SSH to VM
ssh azureuser@4.155.230.212

# Navigate to repo
cd ~/Repositories/cryptobot

# Pull latest changes
git pull origin copilot/debug-firefaucet-claim-page-again

# Run test with headless mode
HEADLESS=true python3 test_firefaucet_claim_fix.py

# Or test with main bot
HEADLESS=true python3 main.py --single firefaucet
```

## Expected Behavior

### Before Fix
- Button found but disabled
- Click attempted on disabled button
- No claim processed or error about disabled element

### After Fix
- Button found: `#get_reward_button`
- Countdown timer waited: 9 seconds
- Button enabled and text changed to "Get Reward"
- Click succeeds
- Claim processed

## Verification Checklist

- [x] Code syntax validated
- [x] Button selector updated to prioritize `#get_reward_button`
- [x] Countdown timer wait logic added
- [x] Redundant waits removed
- [x] Diagnostic tools created
- [ ] Test on Azure VM (headless Linux)
- [ ] Verify claim succeeds
- [ ] Check logs for proper timer completion messages

## Related Issues

- Issue #86: FireFaucet claim page shows 0 buttons

## Additional Notes

### HTML Evidence

The saved `firefaucet_before.html` file shows the button structure:

```html
<button id="get_reward_button" type="submit" 
        class="btn waves-effect waves-light earn-btns disabled captcha-submit-btn" 
        disabled="disabled">
    Please Wait (9)
</button>
```

And the JavaScript that manages the countdown:

```javascript
var timer_complete = false;
var _0x35be97 = document.getElementById('get_reward_button');
var _0x3ca36b = 9;  // 9 second countdown
var _0xb72e99 = setInterval(function(){
    _0x35be97.innerHTML = 'Please Wait (' + _0x3ca36b + ')';
    _0x3ca36b -= 1;
    if(_0x3ca36b == -1){
        _0x35be97.innerHTML = 'Get Reward';
        _0x35be97.classList.remove('disabled');
        timer_complete = true;
        clearInterval(_0xb72e99);
    }
}, 1000);
```

This confirms the 9-second timer mechanism and the need to wait for completion.
