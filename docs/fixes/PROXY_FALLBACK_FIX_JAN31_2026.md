# Dead Proxy Fallback Logic Fix - January 31, 2026

## Problem Statement
The proxy manager was attempting to use known-dead proxies (142.93.66.75, 167.99.207.160) during bot operations. The `get_proxy_for_profile()` method (via `assign_proxies()` and `rotate_proxy()`) was not properly filtering out dead proxies and those in cooldown.

## Root Cause
1. **assign_proxies()**: Initial proxy assignment did not filter out dead or cooldown proxies
2. **rotate_proxy()**: While it filtered dead proxies, the filtering logic had gaps with host-level cooldowns
3. **Insufficient Logging**: No clear warnings when all proxies were exhausted

## Changes Made

### 1. Fixed `assign_proxies()` (lines 1167-1229)
**Before**: Assigned proxies without checking if they were dead or in cooldown
**After**: Now filters proxies through multiple health checks:
- Skips proxies in `dead_proxies` list
- Skips proxies with active cooldowns
- Skips host-level cooldowns
- Logs detailed error if ALL proxies are unavailable
- Tracks filtered proxy count

**Key Code Addition**:
```python
# Filter out dead proxies and those in cooldown
now = time.time()
healthy_proxies = []
for p in self.proxies:
    proxy_key = self._proxy_key(p)
    host_port = self._proxy_host_port(p)
    
    # Skip if dead
    if proxy_key in self.dead_proxies or (host_port and host_port in self.dead_proxies):
        logger.debug(f"Skipping dead proxy during assignment: {self._mask_proxy_key(proxy_key)}")
        continue
    
    # Skip if in cooldown
    if proxy_key in self.proxy_cooldowns and self.proxy_cooldowns[proxy_key] > now:
        logger.debug(f"Skipping proxy in cooldown during assignment: {self._mask_proxy_key(proxy_key)}")
        continue
    if host_port and host_port in self.proxy_cooldowns and self.proxy_cooldowns[host_port] > now:
        logger.debug(f"Skipping proxy with host in cooldown during assignment: {self._mask_proxy_key(proxy_key)}")
        continue
    
    healthy_proxies.append(p)

if not healthy_proxies:
    logger.error("⚠️ ALL PROXIES ARE DEAD OR IN COOLDOWN! Cannot assign proxies to profiles.")
    logger.error(f"   Dead: {len(self.dead_proxies)}, In cooldown: {len(self.proxy_cooldowns)}")
    return
```

### 2. Improved `rotate_proxy()` (lines 1237-1332)
**Before**: Basic filtering but incomplete host-level checks and poor error messages
**After**: 
- More thorough filtering of dead/cooldown proxies
- Better host-port cooldown handling
- Comprehensive logging when no healthy proxies available
- Shows diagnostic info (total proxies, dead count, cooldown count)
- Attempts to find best available proxy with shortest cooldown

**Key Improvements**:
```python
if not healthy:
    logger.error(f"⚠️ NO HEALTHY PROXIES AVAILABLE for {profile.username}")
    logger.error(f"   Total proxies: {len(self.proxies)}")
    logger.error(f"   Dead proxies: {len(self.dead_proxies)}")
    logger.error(f"   In cooldown: {len([k for k, v in self.proxy_cooldowns.items() if v > now])}")
    
    # Try to salvage: find the proxy with the shortest cooldown remaining
    cooldown_proxies = [(p, self.proxy_cooldowns.get(self._proxy_key(p), 0)) for p in self.proxies if self._proxy_key(p) in self.proxy_cooldowns]
    if cooldown_proxies:
        best = min(cooldown_proxies, key=lambda x: x[1])
        if best[1] > now:  # Still in cooldown
            wait_time = int(best[1] - now)
            logger.warning(f"   Best available proxy has {wait_time}s cooldown remaining")
```

### 3. Enhanced Logging
Added informative error messages that clearly indicate:
- When all proxies are dead/in cooldown
- Breakdown of why proxies are unavailable (dead count vs cooldown count)
- Time remaining for best available proxy
- Number of proxies filtered during assignment

## Testing
Created comprehensive test suite (`test_proxy_fallback.py`) with 5 test cases:

1. ✅ **Test 1**: Dead proxies are not assigned during `assign_proxies()`
2. ✅ **Test 2**: Cooldown proxies are not assigned during `assign_proxies()`
3. ✅ **Test 3**: Graceful handling when ALL proxies are dead
4. ✅ **Test 4**: Successful rotation away from dead proxy to healthy proxy
5. ✅ **Test 5**: `get_proxy_stats()` correctly reports `is_dead` status

**All tests passed** (5/5)

## Success Criteria (from Task 5)
- [x] Only healthy proxies used
- [x] Warning logged if none available
- [x] Dead proxies properly filtered
- [x] Cooldown proxies properly filtered
- [x] Graceful fallback behavior

## Files Modified
1. `core/proxy_manager.py` - Updated `assign_proxies()` and `rotate_proxy()` methods
2. `test_proxy_fallback.py` - New comprehensive test suite

## Impact
- **Before**: System would attempt to use proxies marked as dead or in cooldown, causing connection failures
- **After**: System only uses healthy proxies; provides clear warnings when proxy pool is exhausted

## Next Steps
1. Monitor logs for "⚠️ ALL PROXIES ARE DEAD" warnings in production
2. If this occurs frequently, consider:
   - Reducing cooldown durations (currently 1h for detection, 5m for failures)
   - Implementing auto-provisioning when proxy count drops too low
   - Adding proxy health checks before assignment

## Related Issues
- Addresses AGENT_TASKS.md Task 5: Fix Dead Proxy Fallback Logic
- Reduces errors like "connection refused" when using known-bad proxies
- Improves overall system reliability and reduces wasted claim attempts
