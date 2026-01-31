"""Test what parameters Camoufox can accept without errors."""
import asyncio
from camoufox import AsyncCamoufox
import traceback

async def test_camoufox_params():
    """Test different parameter combinations."""
    
    # Test 1: Minimal (what currently works locally)
    print("Test 1: Minimal params")
    try:
        async with AsyncCamoufox(headless=True) as _browser:
            print("  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    
    # Test 2: With fonts only
    print("\nTest 2: With fonts")
    try:
        async with AsyncCamoufox(
            headless=True,
            fonts=["Arial", "Courier New", "Georgia"]
        ) as _browser:
            print("  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    
    # Test 3: With geoip and humanize
    print("\nTest 3: With geoip and humanize")
    try:
        async with AsyncCamoufox(
            headless=True,
            geoip=True,
            humanize=True
        ) as _browser:
            print("  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    
    # Test 4: Full combo (current browser/instance.py)
    print("\nTest 4: Full combo with fonts, geoip, humanize")
    try:
        async with AsyncCamoufox(
            headless=True,
            geoip=True,
            humanize=True,
            block_images=True,
            fonts=["Arial", "Courier New", "Georgia", "Times New Roman", "Verdana"]
        ) as _browser:
            print("  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
    
    # Test 5: Try with explicit OS
    print("\nTest 5: With explicit OS")
    try:
        async with AsyncCamoufox(
            headless=True,
            os="windows"
        ) as _browser:
            print("  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
    
    # Test 6: With screen dict
    print("\nTest 6: With screen dict")
    try:
        async with AsyncCamoufox(
            headless=True,
            screen={"width": 1920, "height": 1080}
        ) as _browser:
            print("  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_camoufox_params())
