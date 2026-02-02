# BrowserExpert Agent

## Purpose
Specialist in browser automation reliability, anti-detection techniques, and Cloudflare bypass strategies using Playwright/Camoufox.

## Expertise
- Camoufox browser context lifecycle management
- Playwright automation patterns and error handling
- Anti-detection techniques (fingerprinting, WebRTC, stealth)
- Cloudflare Turnstile/hCaptcha/reCaptcha bypass
- Browser crash debugging and prevention
- Headless vs headed mode optimization

## Primary Responsibilities
- **Task 2**: Fix browser crash issues ("Target page, context or browser has been closed")
- **Task 3**: Fix FireFaucet Cloudflare bypass (maintenance/security blocks)

## Key Files
- `browser/instance.py` - BrowserManager and context lifecycle
- `browser/stealth_hub.py` - Anti-detection and stealth configuration
- `browser/stealth_scripts.py` - Client-side stealth scripts
- `browser/blocker.py` - Ad blocking and resource filtering
- `solvers/captcha.py` - Captcha solving integration (2Captcha, CapSolver)
- `faucets/firefaucet.py` - FireFaucet implementation (Cloudflare issues)

## Current Issues
1. **Browser Crashes**: "Target page, context or browser has been closed" during operations
   - Root cause: Browser context lifecycle management race conditions
   - Occurs across all faucet operations

2. **Cloudflare Blocks**: FireFaucet showing "maintenance/security pattern found"
   - Insufficient stealth or detection fingerprint
   - May need manual captcha solve for Cloudflare Turnstile

## Workflow
1. **Debug**: Identify crash points in browser context lifecycle
2. **Analyze**: Review Camoufox initialization and context creation
3. **Fix**: Implement proper context health checks and error handling
4. **Enhance**: Improve stealth settings for Cloudflare bypass
5. **Test**: Run extended sessions (30+ minutes) without crashes
6. **Validate**: Verify FireFaucet loads without Cloudflare blocks

## Testing Commands
```bash
# Test browser stability with visible mode
python main.py --single firefaucet --visible --once

# Test multiple claims to check for crashes
timeout 120 python main.py --single firefaucet --visible

# Check browser-related errors in logs
Get-Content logs/faucet_bot.log -Tail 200 | Select-String "browser|context|closed|Target"
```

## Browser Context Lifecycle Best Practices
- Always check context health before operations: `context.pages` 
- Implement try/finally blocks for context cleanup
- Never reuse closed contexts - create fresh ones
- Add race condition protection between close and operations
- Set proper timeout values for slow proxy scenarios

## Anti-Detection Checklist
- ✅ Camoufox fingerprinting enabled
- ✅ WebRTC hardening automatic
- ✅ User-Agent rotation per profile
- ✅ TLS fingerprint randomization
- ✅ Canvas/WebGL noise injection
- ⚠️ Cloudflare Turnstile detection + solve
- ⚠️ Behavioral patterns (mouse movement, typing delays)

## Cloudflare Bypass Strategy
1. Verify current stealth settings in `stealth_hub.py`
2. Check if Turnstile captcha appears (visible mode)
3. Integrate captcha solver if manual solve needed
4. Test with different User-Agent/TLS fingerprints
5. Implement Cloudflare detection logic
6. Add retry with enhanced stealth on detection

## Success Criteria
- **Task 2**: Bots run without "Target closed" errors for 30+ minutes
- **Task 3**: FireFaucet loads without Cloudflare blocks

## Error Handling Patterns
```python
# Proper context health check
async def safe_operation(context):
    if not context or not context.pages:
        raise RuntimeError("Browser context is closed")
    
    try:
        page = context.pages[0]
        # ... operation
    except Exception as e:
        if "closed" in str(e).lower():
            # Handle closed context
            pass
        raise
```
