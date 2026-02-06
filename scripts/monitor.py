#!/usr/bin/env python3
"""
Cryptobot Monitoring Dashboard CLI

Standalone script for viewing real-time faucet health metrics.

Usage:
    python monitor.py                    # Show 24h metrics
    python monitor.py --period 168       # Show 7d metrics (168 hours)
    python monitor.py --live             # Live updating dashboard
    python monitor.py --alerts-only      # Show only active alerts
    python monitor.py --show-all         # Show all faucets including inactive
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.monitoring import main as monitoring_main

if __name__ == "__main__":
    asyncio.run(monitoring_main())
