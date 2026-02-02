"""
Quick test to check Cointiply selectors using simple --single run.
"""
import asyncio
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

async def main():
    """Run a single Cointiply test."""
    from main import main as run_main
    
    # Override sys.argv to simulate --single cointiply --visible
    sys.argv = ["main.py", "--single", "cointiply", "--visible", "--once"]
    
    try:
        await run_main()
    except KeyboardInterrupt:
        print("\n⏸️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("TESTING COINTIPLY BOT")
    print("="*60)
    print("\nThis will run the cointiply bot with visible browser.")
    print("Watch for any errors in selectors or navigation.\n")
    
    asyncio.run(main())
