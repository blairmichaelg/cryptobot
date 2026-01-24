# Azure VM Comprehensive Fix - Execution Plan
**Date:** January 24, 2026  
**Objective:** Properly fix and standardize the Azure VM deployment

---

## Comprehensive Fix Strategy

### Phase 1: Update Repositories/cryptobot to Latest
- Pull latest master branch (with all recent fixes)
- Verify all code is current
- Check for any import errors

### Phase 2: Fix Any Remaining Import Issues
- Ensure all typing imports (Dict, List, Any, Optional) are present
- Validate all files can import without errors

### Phase 3: Reconfigure systemd Service
- Update service to use ~/Repositories/cryptobot as canonical location
- Configure proper environment variables
- Set up correct logging paths

### Phase 4: Clean Up backend_service
- Archive the broken installation
- Free up disk space (16 MB crash log)
- Document what was archived

### Phase 5: Deploy and Verify
- Restart service with new configuration
- Monitor for stability (10+ minutes)
- Verify heartbeat updates
- Run health checks

### Phase 6: Set Up Monitoring
- Configure systemd watchdog
- Set up log rotation
- Document monitoring procedures

---

## Executing Now...
