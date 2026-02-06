"""Simplest possible test - just run main.py on FireFaucet"""
import subprocess
import sys

print("=" * 80)
print("🔥 RUNNING FIREFAUCET VIA MAIN.PY")
print("=" * 80)
print()
print("This will test the complete flow with User-Agent fix")
print("Press Ctrl+C to stop when login completes")
print()
print("=" * 80)
print()

# Run main.py with FireFaucet
result = subprocess.run(
    [sys.executable, "main.py", "--single", "firefaucet", "--visible", "--once"],
    cwd=r"C:\Users\azureuser\Repositories\cryptobot"
)

sys.exit(result.returncode)
