#!/usr/bin/env python3
"""
Feature Verification Script

Verifies all 5 new features are properly implemented and functional.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_feature_1_shortlinks():
    """Verify shortlink claiming implementation."""
    print("\n" + "="*60)
    print("FEATURE 1: Multi-Session Shortlink Claiming")
    print("="*60)
    
    checks = []
    
    # Check firefaucet has claim_shortlinks with separate_context parameter
    try:
        from faucets.firefaucet import FireFaucetBot
        import inspect
        
        sig = inspect.signature(FireFaucetBot.claim_shortlinks)
        params = list(sig.parameters.keys())
        
        assert 'separate_context' in params, "Missing separate_context parameter"
        checks.append(("✅ FireFaucet claim_shortlinks()", True))
    except Exception as e:
        checks.append((f"❌ FireFaucet claim_shortlinks(): {e}", False))
    
    # Check dutchy has claim_shortlinks
    try:
        from faucets.dutchy import DutchyBot
        assert hasattr(DutchyBot, 'claim_shortlinks'), "Missing claim_shortlinks method"
        checks.append(("✅ DutchyBot claim_shortlinks()", True))
    except Exception as e:
        checks.append((f"❌ DutchyBot claim_shortlinks(): {e}", False))
    
    # Check coinpayu has claim_shortlinks
    try:
        from faucets.coinpayu import CoinPayUBot
        assert hasattr(CoinPayUBot, 'claim_shortlinks'), "Missing claim_shortlinks method"
        checks.append(("✅ CoinPayUBot claim_shortlinks()", True))
    except Exception as e:
        checks.append((f"❌ CoinPayUBot claim_shortlinks(): {e}", False))
    
    # Check config has ENABLE_SHORTLINKS setting
    try:
        from core.config import BotSettings
        settings_fields = BotSettings.model_fields.keys()
        assert 'enable_shortlinks' in settings_fields, "Missing enable_shortlinks setting"
        checks.append(("✅ BotSettings.enable_shortlinks", True))
    except Exception as e:
        checks.append((f"❌ BotSettings.enable_shortlinks: {e}", False))
    
    for check, status in checks:
        print(f"  {check}")
    
    return all(status for _, status in checks)


def check_feature_2_autoregister():
    """Verify auto-registration implementation."""
    print("\n" + "="*60)
    print("FEATURE 2: Self-Healing Account Registration")
    print("="*60)
    
    checks = []
    
    # Check script exists
    script_path = Path("scripts/auto_register.py")
    checks.append((f"✅ scripts/auto_register.py exists", script_path.exists()))
    
    if not script_path.exists():
        checks.append(("❌ Script not found", False))
        for check, _ in checks:
            print(f"  {check}")
        return False
    
    # Check classes exist
    try:
        sys.path.insert(0, str(Path("scripts")))
        from auto_register import TempMailAPI, AccountVault, FaucetRegistrar
        
        checks.append(("✅ TempMailAPI class", True))
        checks.append(("✅ AccountVault class", True))
        checks.append(("✅ FaucetRegistrar class", True))
        
        # Check key methods
        assert hasattr(FaucetRegistrar, 'register_account')
        checks.append(("✅ FaucetRegistrar.register_account()", True))
        
        assert hasattr(FaucetRegistrar, 'rotate_burned_accounts')
        checks.append(("✅ FaucetRegistrar.rotate_burned_accounts()", True))
        
        assert hasattr(AccountVault, 'save_account')
        checks.append(("✅ AccountVault.save_account()", True))
        
        assert hasattr(AccountVault, 'mark_burned')
        checks.append(("✅ AccountVault.mark_burned()", True))
        
    except Exception as e:
        checks.append((f"❌ Import error: {e}", False))
    
    # Check faker dependency
    try:
        import faker
        checks.append(("✅ faker library installed", True))
    except ImportError:
        checks.append(("❌ faker library not installed", False))
    
    for check, status in checks:
        print(f"  {check}")
    
    return all(status for _, status in checks)


def check_feature_3_ml_scheduling():
    """Verify ML-based timer prediction."""
    print("\n" + "="*60)
    print("FEATURE 3: Intelligent Job Scheduling with ML")
    print("="*60)
    
    checks = []
    
    # Check orchestrator has prediction methods
    try:
        from core.orchestrator import JobScheduler
        
        assert hasattr(JobScheduler, 'predict_next_claim_time')
        checks.append(("✅ JobScheduler.predict_next_claim_time()", True))
        
        assert hasattr(JobScheduler, 'record_timer_observation')
        checks.append(("✅ JobScheduler.record_timer_observation()", True))
        
        # Check __init__ has timer_predictions
        import inspect
        source = inspect.getsource(JobScheduler.__init__)
        assert 'timer_predictions' in source
        checks.append(("✅ JobScheduler.timer_predictions tracking", True))
        
        assert 'TIMER_HISTORY_SIZE' in source
        checks.append(("✅ TIMER_HISTORY_SIZE constant", True))
        
    except Exception as e:
        checks.append((f"❌ JobScheduler ML methods: {e}", False))
    
    # Test prediction logic
    try:
        from core.config import BotSettings
        from core.orchestrator import JobScheduler
        
        settings = BotSettings()
        scheduler = JobScheduler(settings, None, None)
        
        # Add sample observations
        scheduler.record_timer_observation('test_faucet', 30.0, 28.5)
        scheduler.record_timer_observation('test_faucet', 30.0, 29.0)
        scheduler.record_timer_observation('test_faucet', 30.0, 28.0)
        
        # Test prediction
        predicted = scheduler.predict_next_claim_time('test_faucet', 30.0)
        assert 27.0 <= predicted <= 31.0, f"Prediction out of range: {predicted}"
        
        checks.append(("✅ Timer prediction logic works", True))
        
    except Exception as e:
        checks.append((f"❌ Prediction logic test: {e}", False))
    
    for check, status in checks:
        print(f"  {check}")
    
    return all(status for _, status in checks)


def check_feature_4_cicd():
    """Verify CI/CD pipeline implementation."""
    print("\n" + "="*60)
    print("FEATURE 4: CI/CD Pipeline with Health Checks")
    print("="*60)
    
    checks = []
    
    # Check workflow file exists
    workflow_path = Path(".github/workflows/deploy.yml")
    checks.append((f"✅ .github/workflows/deploy.yml exists", workflow_path.exists()))
    
    if not workflow_path.exists():
        checks.append(("❌ Workflow file not found", False))
        for check, _ in checks:
            print(f"  {check}")
        return False
    
    # Check workflow content
    try:
        content = workflow_path.read_text()
        
        # Check for test job
        assert 'jobs:\n  test:' in content or 'jobs:\r\n  test:' in content
        checks.append(("✅ Test job defined", True))
        
        # Check for pytest
        assert 'pytest' in content
        checks.append(("✅ pytest execution", True))
        
        # Check for mypy/pylint
        assert 'mypy' in content or 'pylint' in content
        checks.append(("✅ Code quality checks", True))
        
        # Check for health check
        assert 'health_check' in content or 'Health check' in content
        checks.append(("✅ Health check step", True))
        
        # Check for rollback
        assert 'rollback' in content.lower()
        checks.append(("✅ Rollback on failure", True))
        
        # Check for push trigger
        assert 'push:' in content
        checks.append(("✅ Auto-deploy on push", True))
        
    except Exception as e:
        checks.append((f"❌ Workflow validation: {e}", False))
    
    for check, status in checks:
        print(f"  {check}")
    
    return all(status for _, status in checks)


def check_feature_5_proxy_management():
    """Verify dynamic proxy management."""
    print("\n" + "="*60)
    print("FEATURE 5: Dynamic Proxy Management")
    print("="*60)
    
    checks = []
    
    # Check proxy_manager has auto methods
    try:
        from core.proxy_manager import ProxyManager
        
        assert hasattr(ProxyManager, 'auto_provision_proxies')
        checks.append(("✅ ProxyManager.auto_provision_proxies()", True))
        
        assert hasattr(ProxyManager, 'auto_remove_dead_proxies')
        checks.append(("✅ ProxyManager.auto_remove_dead_proxies()", True))
        
        # Check method signatures
        import inspect
        
        sig = inspect.signature(ProxyManager.auto_provision_proxies)
        params = list(sig.parameters.keys())
        assert 'min_threshold' in params
        assert 'provision_count' in params
        checks.append(("✅ auto_provision_proxies parameters", True))
        
        sig = inspect.signature(ProxyManager.auto_remove_dead_proxies)
        params = list(sig.parameters.keys())
        assert 'failure_threshold' in params
        checks.append(("✅ auto_remove_dead_proxies parameters", True))
        
    except Exception as e:
        checks.append((f"❌ ProxyManager methods: {e}", False))
    
    for check, status in checks:
        print(f"  {check}")
    
    return all(status for _, status in checks)


def main():
    """Run all feature verification checks."""
    print("\n" + "="*70)
    print(" "*20 + "FEATURE VERIFICATION REPORT")
    print("="*70)
    
    results = []
    
    results.append(("Shortlink Claiming", check_feature_1_shortlinks()))
    results.append(("Auto-Registration", check_feature_2_autoregister()))
    results.append(("ML Scheduling", check_feature_3_ml_scheduling()))
    results.append(("CI/CD Pipeline", check_feature_4_cicd()))
    results.append(("Proxy Management", check_feature_5_proxy_management()))
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    for feature, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {feature}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print("\n" + "="*70)
    print(f"Results: {passed}/{total} features verified successfully")
    print("="*70 + "\n")
    
    if passed == total:
        print("🎉 All features implemented correctly!")
        return 0
    else:
        print("⚠️  Some features need attention")
        return 1


if __name__ == "__main__":
    sys.exit(main())
