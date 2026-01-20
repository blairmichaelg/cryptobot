#!/usr/bin/env python3
import argparse
import subprocess
import os
import sys
import shutil
import json
from datetime import datetime

class CryptobotMeta:
    """Unified CLI for Cryptobot Management"""
    
    def __init__(self):
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        
    def run_cmd(self, cmd, capture_output=True):
        """Helper to run shell commands"""
        try:
            result = subprocess.run(
                cmd, 
                shell=True, 
                text=True, 
                capture_output=capture_output,
                cwd=self.root_dir
            )
            return result
        except Exception as e:
            print(f"Error running command '{cmd}': {e}")
            return None

    def clean(self, args):
        """Cleanup temporary files and reorganize root if needed"""
        print("[CLEAN] Starting project cleanup...")
        
        # 1. Clear __pycache__
        count = 0
        for root, dirs, files in os.walk(self.root_dir):
            if "__pycache__" in dirs:
                shutil.rmtree(os.path.join(root, "__pycache__"))
                count += 1
        print(f"   Removed {count} __pycache__ directories.")

        # 2. Cleanup root clutter (logs, reports, etc.)
        patterns = {
            "logs/": [".log"],
            "assets/": [".png"],
            "reports/": [".txt", ".coverage"],
            "backups/": [".bak", "bundle.zip"]
        }
        
        # Files that should NEVER be moved from root
        exclusions = [
            "requirements.txt", "proxies.txt", "heartbeat.txt", 
            "IMPLEMENTATION_NOTES.md", "README.md", "pytest.ini",
            "faucet_config.json", "faucet_state.json", "session_state.json",
            "proxy_bindings.json", "main.py", "register_faucets.py",
            "setup.py", ".env", ".env.example", ".gitignore",
            "Dockerfile", "docker-compose.yml", "cryptobot.service", "logrotate.conf"
        ]
        
        for folder, exts in patterns.items():
            folder_path = os.path.join(self.root_dir, folder)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                
            for file in os.listdir(self.root_dir):
                file_path = os.path.join(self.root_dir, file)
                if not os.path.isfile(file_path) or file in exclusions:
                    continue
                    
                match = False
                for ext in exts:
                    if file.endswith(ext):
                        match = True
                        break
                    # Special cases for report files that might not end in .txt but are obviously reports
                    if ext == ".txt" and ("coverage" in file.lower() or "test_" in file.lower() or "_results" in file.lower()):
                        match = True
                        break
                
                if match:
                    try:
                        shutil.move(file_path, os.path.join(folder_path, file))
                        print(f"   Moved {file} -> {folder}/")
                    except Exception as e:
                        print(f"   Failed to move {file}: {e}")

        print("[CLEAN] Cleanup complete.")

    def audit(self, args):
        """Audit project state: GH issues, PRs, local git status"""
        print("[AUDIT] Auditing project state...")
        
        # 1. Git Status
        print("\n--- Local Git Status ---")
        res = self.run_cmd("git status -s")
        if res and res.stdout:
            print(res.stdout.strip())
        else:
            print("   Workspace is clean.")

        # 2. GitHub Issues
        print("\n--- Open GitHub Issues ---")
        res = self.run_cmd("gh issue list")
        if res and res.stdout:
            print(res.stdout.strip())
        else:
            print("   No open issues.")

        # 3. GitHub PRs
        print("\n--- Open Pull Requests ---")
        res = self.run_cmd("gh pr list")
        if res and res.stdout:
            print(res.stdout.strip())
        else:
            print("   No open pull requests.")

        # 4. Azure Resources (Optional, if logged in)
        if args.full:
            print("\n--- Azure Resource Status ---")
            res = self.run_cmd("az resource list --resource-group cryptobot-rg --output table")
            if res and res.stdout:
                print(res.stdout.strip())
            else:
                print("   Azure CLI not logged in or RG not found.")

    def sync(self, args):
        """Sync with remote, merge PRs, and maintain a clean branch"""
        print("[SYNC] Syncing with remote repository...")
        
        # 1. Fetch latest
        self.run_cmd("git fetch origin")
        
        # 2. Check for approved PRs and merge them if requested
        if args.merge:
            print("   Checking for mergeable PRs...")
            # This is complex to automate safely without user feedback in a script
            # but we can list them and prompt or use gh pr merge
            res = self.run_cmd("gh pr list --json number,mergeable,reviewDecision")
            if res and res.stdout:
                prs = json.loads(res.stdout)
                for pr in prs:
                    if pr['reviewDecision'] == 'APPROVED' and pr['mergeable'] == 'MERGEABLE':
                        print(f"   Merging approved PR #{pr['number']}...")
                        self.run_cmd(f"gh pr merge {pr['number']} --merge --delete-branch")
        
        # 3. Commit and push current state
        if args.push:
            print("   Staging and pushing current changes...")
            self.run_cmd("git add .")
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.run_cmd(f'git commit -m "Auto-sync: {date_str}"')
            self.run_cmd("git push origin master")
            
        print("✅ Sync complete.")

    def deploy(self, args):
        """Trigger deployment to Azure"""
        print("[DEPLOY] Deploying to Azure...")
        # Check for deployment script
        ps_script = os.path.join(self.root_dir, "scripts", "deploy_to_azure.ps1")
        if os.path.exists(ps_script):
            print(f"   Running {ps_script}...")
            # On windows, we can use powershell
            subprocess.run(["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", ps_script])
        else:
            print("   Deployment script not found in scripts/deploy_to_azure.ps1")

    def report(self, args):
        """Show unified profitability report"""
        print("[REPORT] Generating unified profitability report...")
        
        try:
            from core.analytics import get_tracker
            from core.withdrawal_analytics import get_analytics
            
            tracker = get_tracker()
            withdrawal_analytics = get_analytics()
            
            print("\n--- Earnings Summary (Last 24h) ---")
            print(tracker.get_daily_summary())
            
            print("\n--- Withdrawal Analytics ---")
            print(withdrawal_analytics.generate_report(period="weekly"))
            
        except Exception as e:
            print(f"   Error generating report: {e}")

    def register_pick(self, args):
        """Automate Pick.io registrations"""
        print("[REGISTER] Starting automated Pick.io registrations...")
        
        email = args.email or os.environ.get("REGISTRATION_EMAIL")
        password = args.password or os.environ.get("REGISTRATION_PASSWORD")
        
        if not email or not password:
            print("   Error: Email and Password required. Use --email/--password or set REGISTRATION_EMAIL/PASSWORD env vars.")
            return

        cmd = f"python register_faucets.py --email {email} --password {password}"
        if args.visible:
            cmd += " --visible"
        if args.faucets:
            cmd += f" --faucets {' '.join(args.faucets)}"
            
        print(f"   Running registration script...")
        self.run_cmd(cmd, capture_output=False)

def main():
    parser = argparse.ArgumentParser(description="Cryptobot Management Meta-Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Clean
    subparsers.add_parser("clean", help="Cleanup project clutter and temp files")

    # Audit
    audit_parser = subparsers.add_parser("audit", help="Check local and remote project state")
    audit_parser.add_argument("--full", action="store_true", help="Include Azure resource check")

    # Sync
    sync_parser = subparsers.add_parser("sync", help="Synchronize with remote and merge approved PRs")
    sync_parser.add_argument("--merge", action="store_true", help="Automatically merge approved PRs")
    sync_parser.add_argument("--push", action="store_true", help="Commit and push local changes to master")

    # Deploy
    subparsers.add_parser("deploy", help="Deploy the latest version to Azure")

    # Report
    subparsers.add_parser("report", help="Show unified profitability and withdrawal report")

    # Register
    register_parser = subparsers.add_parser("register", help="Automate Pick.io registrations")
    register_parser.add_argument("--email", help="Email for registration")
    register_parser.add_argument("--password", help="Password for registration")
    register_parser.add_argument("--faucets", nargs="+", help="Specific faucets to register")
    register_parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")

    args = parser.parse_args()
    meta = CryptobotMeta()

    if args.command == "clean":
        meta.clean(args)
    elif args.command == "audit":
        meta.audit(args)
    elif args.command == "sync":
        meta.sync(args)
    elif args.command == "deploy":
        meta.deploy(args)
    elif args.command == "report":
        meta.report(args)
    elif args.command == "register":
        meta.register_pick(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
