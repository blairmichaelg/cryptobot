#!/usr/bin/env python3
"""Test if config settings are loading correctly from .env"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
os.chdir(Path(__file__).parent.parent)

from core.config import BotSettings

def main():
    print("=" * 60)
    print("Testing Configuration Loading")
    print("=" * 60)
    print()
    
    settings = BotSettings()
    
    print(f"✓ proxy_bypass_faucets: {settings.proxy_bypass_faucets}")
    print(f"✓ image_bypass_faucets: {settings.image_bypass_faucets}")
    print(f"✓ enable_direct_fallback: {settings.enable_direct_fallback}")
    print(f"✓ proxy_fallback_threshold: {settings.proxy_fallback_threshold}")
    print()
    
    # Test if our new settings are applied
    expected_bypass = ["dutchy", "coinpayu", "adbtc", "freebitcoin"]
    
    # Normalize for comparison
    def normalize(lst):
        return sorted([s.lower().replace("_", "").strip('"').strip("'") for s in lst])
    
    actual = normalize(settings.proxy_bypass_faucets)
    expected = normalize(expected_bypass)
    
    print("Expected bypass faucets:", expected)
    print("Actual bypass faucets:", actual)
    print()
    
    if actual == expected:
        print("✅ SUCCESS: Bypass faucets configured correctly!")
        return 0
    elif set(expected).issubset(set(actual)):
        print("✅ PARTIAL: Expected faucets are in the list")
        print(f"   Extra faucets: {set(actual) - set(expected)}")
        return 0
    else:
        print("❌ FAILED: Configuration not loaded correctly")
        print(f"   Missing: {set(expected) - set(actual)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
