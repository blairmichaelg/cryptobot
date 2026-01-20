import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.config import BotSettings
from core.proxy_manager import ProxyManager, Proxy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProxyValidator")

async def test_proxy_generation():
    print("--- Testing Proxy Generation ---")
    settings = BotSettings()
    
    # Create a dummy proxy file for testing
    dummy_proxy_file = Path("dummy_proxies.txt")
    with open(dummy_proxy_file, "w") as f:
        f.write("user:pass@1.2.3.4:8080\n")
        
    settings.residential_proxies_file = str(dummy_proxy_file)
    
    manager = ProxyManager(settings)
    
    # Test generation
    count = await manager.fetch_proxies_from_api(5)
    print(f"Generated {count} proxies.")
    
    # Verify content
    with open(dummy_proxy_file, "r") as f:
        lines = f.readlines()
        print("\nGenerated Proxies:")
        for line in lines:
            print(line.strip())
            
    # Clean up
    if dummy_proxy_file.exists():
        dummy_proxy_file.unlink()

if __name__ == "__main__":
    asyncio.run(test_proxy_generation())
