#!/usr/bin/env python3
"""
Quick validation script to verify FreeBitcoin balance selector fix.
Run this on the Azure VM to confirm the fix works.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_balance_selectors():
    """Verify that balance selectors are correctly configured."""
    print("=" * 70)
    print("FreeBitcoin Balance Selector Validation")
    print("=" * 70)
    
    # Read freebitcoin.py
    freebitcoin_path = project_root / "faucets" / "freebitcoin.py"
    with open(freebitcoin_path, "r") as f:
        content = f.read()
    
    issues = []
    
    # Check claim method balance extraction
    if 'balance = await self.get_balance(\n                    "#balance_small"' in content:
        print("✅ Claim method uses #balance_small as primary selector")
    elif 'balance = await self.get_balance(\n                    "#balance"' in content:
        issues.append("❌ Claim method still uses #balance as primary (should be #balance_small)")
    else:
        issues.append("⚠️  Could not verify claim method balance selector")
    
    # Check claim confirmation balance extraction
    if 'new_balance = await self.get_balance(\n                                "#balance_small"' in content:
        print("✅ Claim confirmation uses #balance_small as primary selector")
    elif 'new_balance = await self.get_balance(\n                                "#balance"' in content:
        issues.append("❌ Claim confirmation still uses #balance as primary (should be #balance_small)")
    else:
        issues.append("⚠️  Could not verify claim confirmation balance selector")
    
    # Check withdraw method balance extraction
    if 'balance = await self.get_balance("#balance_small"' in content:
        print("✅ Withdraw method uses #balance_small as primary selector")
    elif 'balance = await self.get_balance("#balance")' in content:
        issues.append("❌ Withdraw method still uses #balance as primary (should be #balance_small)")
    else:
        issues.append("⚠️  Could not verify withdraw method balance selector")
    
    # Check for #balance in fallbacks
    if '"#balance"' in content and 'fallback_selectors=' in content:
        print("✅ #balance is present as fallback selector")
    else:
        issues.append("⚠️  #balance might not be in fallback selectors")
    
    print()
    
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("✅ All balance selectors are correctly configured!")
        return True

def check_test_file():
    """Verify test file uses correct BrowserManager API."""
    print("\n" + "=" * 70)
    print("Test File Validation")
    print("=" * 70)
    
    test_path = project_root / "test_freebitcoin_claim_detailed.py"
    if not test_path.exists():
        print("⚠️  Test file not found")
        return None
    
    with open(test_path, "r") as f:
        content = f.read()
    
    issues = []
    
    # Check BrowserManager initialization
    if "BrowserManager(settings)" in content:
        issues.append("❌ Test uses BrowserManager(settings) - should use individual parameters")
    elif "BrowserManager(" in content and "headless=" in content:
        print("✅ Test uses correct BrowserManager initialization")
    
    # Check for launch() call
    if "await browser_manager.launch()" in content:
        print("✅ Test calls browser_manager.launch()")
    else:
        issues.append("⚠️  Test might not call browser_manager.launch()")
    
    # Check for create_context
    if "create_context" in content:
        print("✅ Test uses create_context() method")
    elif "get_or_create_context" in content:
        issues.append("❌ Test uses get_or_create_context() - should use create_context()")
    
    print()
    
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("✅ Test file is correctly configured!")
        return True

def main():
    """Run all validation checks."""
    print("\n🔍 Validating FreeBitcoin fixes...\n")
    
    selectors_ok = check_balance_selectors()
    test_ok = check_test_file()
    
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    
    if selectors_ok:
        print("✅ Balance selectors: PASSED")
    else:
        print("❌ Balance selectors: FAILED")
    
    if test_ok is None:
        print("⚠️  Test file: NOT FOUND")
    elif test_ok:
        print("✅ Test file: PASSED")
    else:
        print("❌ Test file: FAILED")
    
    print()
    
    if selectors_ok and (test_ok is None or test_ok):
        print("✅ All validations passed! Ready to test on Azure VM.")
        print("\nTo test on VM:")
        print("  ssh azureuser@4.155.230.212")
        print("  cd ~/Repositories/cryptobot")
        print("  git pull")
        print("  HEADLESS=true python3 test_freebitcoin_claim_detailed.py")
        return 0
    else:
        print("❌ Some validations failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
