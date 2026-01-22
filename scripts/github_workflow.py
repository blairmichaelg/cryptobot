#!/usr/bin/env python3
"""
GitHub Workflow Automation for Cryptobot
Handles issue delegation, PR review/merge, and repo sync following single-branch protocol
"""

import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
from datetime import datetime, timedelta


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


class GitHubWorkflow:
    """Automates GitHub workflow for cryptobot project"""

    def __init__(self, dry_run: bool = False, auto_merge: bool = False):
        self.dry_run = dry_run
        self.auto_merge = auto_merge
        self.repo_root = Path(__file__).parent.parent

    def run_command(self, cmd: List[str], check: bool = True, capture: bool = True) -> Tuple[int, str]:
        """Execute shell command and return result"""
        try:
            if capture:
                result = subprocess.run(
                    cmd,
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=check
                )
                return result.returncode, result.stdout.strip()
            else:
                result = subprocess.run(cmd, cwd=self.repo_root, check=check)
                return result.returncode, ""
        except subprocess.CalledProcessError as e:
            return e.returncode, e.stderr if hasattr(e, 'stderr') else str(e)

    def print_header(self, text: str):
        """Print formatted section header"""
        print(f"\n{Colors.BLUE}{'═' * 50}{Colors.NC}")
        print(f"{Colors.BLUE}{Colors.BOLD}  {text}{Colors.NC}")
        print(f"{Colors.BLUE}{'═' * 50}{Colors.NC}\n")

    def print_step(self, step: str, total: int, current: int):
        """Print step progress"""
        print(f"{Colors.YELLOW}[{current}/{total}]{Colors.NC} {step}...")

    def check_prerequisites(self) -> bool:
        """Verify GitHub CLI is installed and authenticated"""
        print(f"{Colors.CYAN}Checking prerequisites...{Colors.NC}")
        
        # Check gh CLI
        ret, _ = self.run_command(['gh', '--version'], check=False)
        if ret != 0:
            print(f"{Colors.RED}✗{Colors.NC} GitHub CLI (gh) not installed")
            print("Install from: https://cli.github.com")
            return False
        
        # Check authentication
        ret, _ = self.run_command(['gh', 'auth', 'status'], check=False)
        if ret != 0:
            print(f"{Colors.RED}✗{Colors.NC} Not authenticated with GitHub CLI")
            print("Run: gh auth login")
            return False
        
        print(f"{Colors.GREEN}✓{Colors.NC} GitHub CLI authenticated\n")
        return True

    def sync_repository(self) -> bool:
        """Pull latest changes from master (single-branch protocol)"""
        self.print_step("Syncing repository", 6, 1)
        
        # Check for uncommitted changes
        ret, status = self.run_command(['git', 'status', '--porcelain'])
        if status:
            print(f"{Colors.YELLOW}⚠{Colors.NC} Uncommitted changes detected")
            if self.dry_run:
                print(f"{Colors.YELLOW}[DRY RUN]{Colors.NC} Would stash changes")
                return True
            
            # Stash changes
            print(f"{Colors.CYAN}Stashing local changes...{Colors.NC}")
            ret, _ = self.run_command(['git', 'stash', 'push', '-m', f'Auto-stash before workflow {datetime.now().isoformat()}'])
            if ret == 0:
                print(f"{Colors.GREEN}✓{Colors.NC} Changes stashed")
        
        # Fetch and pull from origin master
        if self.dry_run:
            print(f"{Colors.YELLOW}[DRY RUN]{Colors.NC} Would pull from origin master")
            return True
        
        print(f"{Colors.CYAN}Pulling latest from origin/master...{Colors.NC}")
        ret, output = self.run_command(['git', 'pull', 'origin', 'master', '--rebase'], check=False)
        
        if ret == 0:
            print(f"{Colors.GREEN}✓{Colors.NC} Repository synchronized")
            if 'Already up to date' not in output:
                print(f"{Colors.CYAN}Changes pulled:{Colors.NC}\n{output}")
            return True
        else:
            print(f"{Colors.RED}✗{Colors.NC} Failed to pull changes")
            return False

    def list_open_items(self) -> Tuple[List[Dict], List[Dict]]:
        """List open issues and PRs"""
        self.print_step("Listing open issues and PRs", 6, 2)
        
        # Get open PRs
        ret, pr_json = self.run_command([
            'gh', 'pr', 'list',
            '--state', 'open',
            '--json', 'number,title,state,author,url,headRefName'
        ])
        prs = json.loads(pr_json) if ret == 0 else []
        
        # Get open issues
        ret, issue_json = self.run_command([
            'gh', 'issue', 'list',
            '--state', 'open',
            '--json', 'number,title,labels,url,author'
        ])
        issues = json.loads(issue_json) if ret == 0 else []
        
        # Display PRs
        if prs:
            print(f"\n{Colors.BLUE}Open Pull Requests:{Colors.NC}")
            for pr in prs:
                print(f"  #{pr['number']}: {pr['title']}")
                print(f"    Author: {pr['author']['login']} | Branch: {pr['headRefName']}")
                print(f"    {pr['url']}")
        else:
            print(f"{Colors.GREEN}✓{Colors.NC} No open PRs")
        
        # Display issues
        if issues:
            print(f"\n{Colors.BLUE}Open Issues:{Colors.NC}")
            for issue in issues:
                labels = ', '.join([l['name'] for l in issue.get('labels', [])])
                print(f"  #{issue['number']}: {issue['title']}")
                if labels:
                    print(f"    Labels: {labels}")
                print(f"    {issue['url']}")
        else:
            print(f"{Colors.GREEN}✓{Colors.NC} No open issues")
        
        return prs, issues

    def review_and_merge_prs(self, prs: List[Dict]) -> int:
        """Review PRs and merge if checks pass"""
        self.print_step("Reviewing PRs for auto-merge", 6, 3)
        
        if not prs:
            print(f"{Colors.GREEN}✓{Colors.NC} No PRs to review")
            return 0
        
        merged_count = 0
        
        for pr in prs:
            pr_num = pr['number']
            print(f"\n{Colors.CYAN}Reviewing PR #{pr_num}: {pr['title']}{Colors.NC}")
            
            # Get PR checks status
            ret, checks_json = self.run_command([
                'gh', 'pr', 'checks', str(pr_num),
                '--json', 'state,name,conclusion'
            ], check=False)
            
            if ret != 0:
                print(f"{Colors.YELLOW}⚠{Colors.NC} Could not fetch checks for PR #{pr_num}")
                continue
            
            checks = json.loads(checks_json) if checks_json else []
            
            # Check if all required checks passed
            failed_checks = [c for c in checks if c.get('conclusion') not in ['SUCCESS', 'NEUTRAL', 'SKIPPED', None]]
            pending_checks = [c for c in checks if c.get('state') in ['PENDING', 'QUEUED', 'IN_PROGRESS']]
            
            if failed_checks:
                print(f"{Colors.RED}✗{Colors.NC} PR #{pr_num} has failing checks:")
                for check in failed_checks[:3]:  # Show first 3
                    print(f"    - {check['name']}: {check.get('conclusion', 'FAILED')}")
                continue
            
            if pending_checks:
                print(f"{Colors.YELLOW}⚠{Colors.NC} PR #{pr_num} has pending checks - will check later")
                continue
            
            # All checks passed
            print(f"{Colors.GREEN}✓{Colors.NC} All checks passed for PR #{pr_num}")
            
            if self.dry_run:
                print(f"{Colors.YELLOW}[DRY RUN]{Colors.NC} Would merge PR #{pr_num} with squash")
                merged_count += 1
            elif self.auto_merge:
                # Request review first if not already approved
                ret, review_json = self.run_command([
                    'gh', 'pr', 'view', str(pr_num),
                    '--json', 'reviews'
                ], check=False)
                
                reviews = json.loads(review_json).get('reviews', []) if ret == 0 else []
                approved = any(r.get('state') == 'APPROVED' for r in reviews)
                
                if not approved:
                    print(f"{Colors.YELLOW}⚠{Colors.NC} PR #{pr_num} not yet approved - requesting review")
                    self.run_command(['gh', 'pr', 'review', str(pr_num), '--approve'], check=False)
                
                # Merge with squash
                print(f"{Colors.CYAN}Merging PR #{pr_num}...{Colors.NC}")
                ret, _ = self.run_command([
                    'gh', 'pr', 'merge', str(pr_num),
                    '--squash',
                    '--delete-branch'
                ], check=False)
                
                if ret == 0:
                    print(f"{Colors.GREEN}✓{Colors.NC} Merged PR #{pr_num}")
                    merged_count += 1
                else:
                    print(f"{Colors.RED}✗{Colors.NC} Failed to merge PR #{pr_num}")
            else:
                print(f"{Colors.BLUE}ℹ{Colors.NC} PR #{pr_num} ready to merge (use --auto-merge flag)")
        
        return merged_count

    def delegate_issues_to_copilot(self, issues: List[Dict]) -> int:
        """Delegate open issues to GitHub Copilot coding agent"""
        self.print_step("Delegating issues to Copilot", 6, 4)
        
        if not issues:
            print(f"{Colors.GREEN}✓{Colors.NC} No issues to delegate")
            return 0
        
        delegated_count = 0
        
        for issue in issues:
            issue_num = issue['number']
            labels = [l['name'] for l in issue.get('labels', [])]
            
            # Skip if already delegated or closed
            if 'delegated' in labels or 'wontfix' in labels:
                print(f"{Colors.CYAN}ℹ{Colors.NC} Issue #{issue_num} already delegated/closed")
                continue
            
            # Skip research/manual tasks
            if any(l in labels for l in ['research', 'manual-task', 'question']):
                print(f"{Colors.CYAN}ℹ{Colors.NC} Issue #{issue_num} requires manual attention ({', '.join(labels)})")
                continue
            
            print(f"\n{Colors.CYAN}Delegating issue #{issue_num}: {issue['title']}{Colors.NC}")
            
            if self.dry_run:
                print(f"{Colors.YELLOW}[DRY RUN]{Colors.NC} Would delegate to @copilot")
                delegated_count += 1
                continue
            
            # Comment to trigger Copilot coding agent
            comment = (
                f"#github-pull-request_copilot-coding-agent: Please implement this issue following the "
                f"patterns in the codebase. Ensure all tests pass and code is properly typed. "
                f"Create a PR with a clear description linking back to this issue."
            )
            
            ret, _ = self.run_command([
                'gh', 'issue', 'comment', str(issue_num),
                '--body', comment
            ], check=False)
            
            if ret == 0:
                # Add delegated label
                self.run_command([
                    'gh', 'issue', 'edit', str(issue_num),
                    '--add-label', 'delegated'
                ], check=False)
                
                print(f"{Colors.GREEN}✓{Colors.NC} Delegated issue #{issue_num}")
                delegated_count += 1
            else:
                print(f"{Colors.RED}✗{Colors.NC} Failed to delegate issue #{issue_num}")
        
        return delegated_count

    def cleanup_and_push(self) -> bool:
        """Clean up merged branches and push changes"""
        self.print_step("Cleanup and push", 6, 5)
        
        # Per protocol: single branch (master), no branch cleanup needed
        # Just ensure we're on master and push any local commits
        
        ret, current_branch = self.run_command(['git', 'branch', '--show-current'])
        if current_branch != 'master':
            print(f"{Colors.YELLOW}⚠{Colors.NC} Not on master branch (currently on {current_branch})")
            if not self.dry_run:
                print(f"{Colors.CYAN}Switching to master...{Colors.NC}")
                self.run_command(['git', 'checkout', 'master'])
        
        # Check for local commits to push
        ret, ahead = self.run_command([
            'git', 'rev-list', '--count', 'origin/master..master'
        ], check=False)
        
        if ahead and int(ahead) > 0:
            print(f"{Colors.CYAN}Found {ahead} local commit(s) to push{Colors.NC}")
            
            if self.dry_run:
                print(f"{Colors.YELLOW}[DRY RUN]{Colors.NC} Would push to origin master")
            else:
                ret, _ = self.run_command(['git', 'push', 'origin', 'master'], check=False)
                if ret == 0:
                    print(f"{Colors.GREEN}✓{Colors.NC} Pushed to origin/master")
                else:
                    print(f"{Colors.RED}✗{Colors.NC} Failed to push")
                    return False
        else:
            print(f"{Colors.GREEN}✓{Colors.NC} No local commits to push")
        
        # Check if we stashed anything earlier
        ret, stash_list = self.run_command(['git', 'stash', 'list'])
        if stash_list and 'Auto-stash before workflow' in stash_list:
            print(f"{Colors.YELLOW}ℹ{Colors.NC} You have stashed changes. Run 'git stash pop' to restore them.")
        
        return True

    def generate_summary(self, merged_count: int, delegated_count: int):
        """Generate workflow summary report"""
        self.print_step("Generating summary", 6, 6)
        
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Get recent closed issues
        ret, closed_json = self.run_command([
            'gh', 'issue', 'list',
            '--state', 'closed',
            '--search', f'closed:>={week_ago}',
            '--limit', '10',
            '--json', 'number,title,closedAt'
        ], check=False)
        
        closed_issues = json.loads(closed_json) if ret == 0 and closed_json else []
        
        # Get recent merged PRs
        ret, merged_json = self.run_command([
            'gh', 'pr', 'list',
            '--state', 'merged',
            '--search', f'merged:>={week_ago}',
            '--limit', '10',
            '--json', 'number,title,mergedAt'
        ], check=False)
        
        merged_prs = json.loads(merged_json) if ret == 0 and merged_json else []
        
        # Display summary
        print(f"\n{Colors.BLUE}{'─' * 50}{Colors.NC}")
        print(f"{Colors.BOLD}Workflow Summary{Colors.NC}")
        print(f"{Colors.BLUE}{'─' * 50}{Colors.NC}")
        print(f"  PRs merged this run: {merged_count}")
        print(f"  Issues delegated: {delegated_count}")
        print(f"  Closed issues (7d): {len(closed_issues)}")
        print(f"  Merged PRs (7d): {len(merged_prs)}")
        
        if closed_issues:
            print(f"\n{Colors.CYAN}Recently Closed Issues:{Colors.NC}")
            for issue in closed_issues[:5]:
                print(f"  ✓ #{issue['number']}: {issue['title']}")
        
        if merged_prs:
            print(f"\n{Colors.CYAN}Recently Merged PRs:{Colors.NC}")
            for pr in merged_prs[:5]:
                print(f"  ✓ #{pr['number']}: {pr['title']}")
        
        print(f"{Colors.BLUE}{'─' * 50}{Colors.NC}\n")

    def run(self):
        """Execute the complete workflow"""
        self.print_header("Cryptobot GitHub Workflow Automation")
        
        if self.dry_run:
            print(f"{Colors.YELLOW}{'!' * 50}{Colors.NC}")
            print(f"{Colors.YELLOW}DRY RUN MODE - No changes will be made{Colors.NC}")
            print(f"{Colors.YELLOW}{'!' * 50}{Colors.NC}\n")
        
        # Check prerequisites
        if not self.check_prerequisites():
            return 1
        
        # 1. Sync repository (pull latest)
        if not self.sync_repository():
            print(f"\n{Colors.RED}✗ Workflow failed at sync step{Colors.NC}")
            return 1
        
        # 2. List open items
        prs, issues = self.list_open_items()
        
        # 3. Review and merge PRs
        merged_count = self.review_and_merge_prs(prs)
        
        # 4. Delegate issues to Copilot
        delegated_count = self.delegate_issues_to_copilot(issues)
        
        # 5. Cleanup and push
        if not self.cleanup_and_push():
            print(f"\n{Colors.RED}✗ Workflow failed at cleanup step{Colors.NC}")
            return 1
        
        # 6. Summary
        self.generate_summary(merged_count, delegated_count)
        
        self.print_header("✓ Workflow Complete!")
        
        return 0


def main():
    parser = argparse.ArgumentParser(
        description='GitHub workflow automation for cryptobot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run workflow (dry-run by default)
  %(prog)s --execute          # Execute workflow with changes
  %(prog)s --auto-merge       # Auto-merge PRs with passing checks
  %(prog)s --execute --auto-merge  # Full automation
        """
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute changes (default is dry-run)'
    )
    
    parser.add_argument(
        '--auto-merge',
        action='store_true',
        help='Automatically merge PRs with passing checks'
    )
    
    args = parser.parse_args()
    
    workflow = GitHubWorkflow(
        dry_run=not args.execute,
        auto_merge=args.auto_merge
    )
    
    try:
        return workflow.run()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Workflow interrupted by user{Colors.NC}")
        return 130
    except Exception as e:
        print(f"\n{Colors.RED}✗ Workflow failed with error:{Colors.NC}")
        print(f"{Colors.RED}{str(e)}{Colors.NC}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
