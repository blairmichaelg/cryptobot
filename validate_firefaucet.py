#!/usr/bin/env python3
"""
Simple validation that FireFaucetBot can be imported and initialized.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from faucets.firefaucet import FireFaucetBot
    print("✅ FireFaucetBot imported successfully")
    
    # Check that the class has the required methods
    required_methods = ['login', 'claim', 'get_balance', 'get_timer']
    for method in required_methods:
        if hasattr(FireFaucetBot, method):
            print(f"✅ Method '{method}' exists")
        else:
            print(f"❌ Method '{method}' missing")
            sys.exit(1)
    
    print("\n✅ All validation checks passed")
    
except Exception as e:
    print(f"❌ Validation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
