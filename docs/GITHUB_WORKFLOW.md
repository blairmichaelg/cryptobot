# GitHub Workflow Automation

Complete automation for managing GitHub issues, pull requests, and repository synchronization following the single-branch master protocol.

## Quick Start

### From Chat or Terminal

```bash
# Dry run (preview what would happen - safe to run anytime)
python meta.py workflow

# Execute the workflow with changes
python meta.py workflow --execute

# Full automation (auto-merge PRs with passing checks)
python meta.py workflow --execute --auto-merge
```

### Alternative Ways to Run

```powershell
# Direct Python script
python scripts/github_workflow.py --execute

# PowerShell wrapper
.\scripts\github_workflow.ps1 -Execute -AutoMerge
```

## What It Does

The workflow performs these steps in order:

### 1. **Repository Sync** 
- Stashes any uncommitted changes
- Pulls latest from `origin/master` (with rebase)
- Ensures clean working directory

### 2. **List Open Items**
- Displays all open pull requests with status
- Lists open issues with labels and assignees

### 3. **Review & Merge PRs**
- Checks CI/CD status for each PR
- Reports passing/failing/pending checks
- Auto-merges PRs with passing checks (if `--auto-merge` flag used)
- Auto-approves before merging
- Deletes merged branches automatically

### 4. **Delegate Issues to Copilot**
- Skips issues already labeled as `delegated`, `research`, or `manual-task`
- Comments on eligible issues with `#github-pull-request_copilot-coding-agent` tag
- Adds `delegated` label for tracking
- Copilot coding agent works in background on cloud

### 5. **Cleanup & Push**
- Ensures on `master` branch (per single-branch protocol)
- Pushes any local commits to origin
- Reports if stashed changes need to be restored

### 6. **Summary Report**
- Shows PRs merged this run
- Shows issues delegated
- Lists recently closed issues (last 7 days)
- Lists recently merged PRs (last 7 days)

## Usage Examples

### Preview Changes (Dry Run)

```bash
# See what would happen without making changes
python meta.py workflow
```

Output shows:
- What PRs would be merged
- What issues would be delegated
- What commits would be pushed
- All with `[DRY RUN]` markers

### Execute Changes Only

```bash
# Execute workflow but don't auto-merge PRs
python meta.py workflow --execute
```

This will:
- ✓ Pull latest changes
- ✓ Delegate issues to Copilot
- ✓ Push commits
- ✗ Won't merge PRs (you review manually)

### Full Automation

```bash
# Complete automation with PR merging
python meta.py workflow --execute --auto-merge
```

This will:
- ✓ Pull latest changes
- ✓ Delegate issues to Copilot
- ✓ Auto-merge PRs with passing checks
- ✓ Push commits
- ✓ Clean up merged branches

## Single-Branch Protocol Compliance

The workflow strictly follows the [single-branch master protocol](../docs/delegate_workflow.md):

1. **No Branch Creation**: Works only with `master`
2. **Stash Before Pull**: Saves uncommitted work safely
3. **Rebase Pull**: Keeps linear history
4. **Push After Changes**: Updates remote immediately
5. **Auto-Cleanup**: Removes merged PR branches

## Integration with Copilot Coding Agent

When issues are delegated:

1. Workflow comments on issue with `#github-pull-request_copilot-coding-agent` tag
2. GitHub Copilot coding agent activates in cloud
3. Agent implements the feature/fix following project patterns
4. Agent creates PR and links back to issue
5. Next workflow run reviews and merges the PR

This enables **parallel execution** without local branching.

## Safety Features

- **Dry run by default**: Won't make changes unless `--execute` specified
- **Stash protection**: Saves uncommitted work before pulling
- **CI check validation**: Only merges PRs with passing checks
- **Approval workflow**: Approves PRs before merging
- **Branch detection**: Ensures on `master` before operations
- **Error handling**: Graceful failures with clear error messages

## Typical Workflows

### Daily Maintenance

```bash
# Morning: Check status and delegate new issues
python meta.py workflow --execute

# Evening: Auto-merge completed work
python meta.py workflow --execute --auto-merge
```

### Before Starting Work

```bash
# Sync everything and review status
python meta.py workflow
```

### After Copilot Completes PRs

```bash
# Review and merge completed PRs
python meta.py workflow --execute --auto-merge
```

## Troubleshooting

### "Not authenticated with GitHub CLI"

```bash
gh auth login
# Follow prompts to authenticate
```

### "Repository has uncommitted changes"

The workflow automatically stashes changes. After completion:

```bash
# Restore your changes
git stash pop
```

### "Failed to merge PR"

Check:
- Are all CI checks passing?
- Does PR have conflicts?
- Is PR approved?

Manual merge:
```bash
gh pr view <number>
gh pr merge <number> --squash
```

### PR Not Auto-Merging

Ensure you use the `--auto-merge` flag:

```bash
python meta.py workflow --execute --auto-merge
```

## Advanced Usage

### Filter by Issue Labels

The workflow automatically skips:
- `delegated` - Already assigned to Copilot
- `research` - Requires manual investigation
- `manual-task` - Requires human intervention
- `question` - Discussion/clarification needed
- `wontfix` - Intentionally not implementing

### Custom Integration

Import the workflow class in your own scripts:

```python
from scripts.github_workflow import GitHubWorkflow

workflow = GitHubWorkflow(dry_run=False, auto_merge=True)
workflow.run()
```

## See Also

- [Delegate Workflow](../docs/delegate_workflow.md) - Parallel delegation patterns
- [Developer Guide](../docs/DEVELOPER_GUIDE.md) - Development workflow
- [Optimal Workflow](../docs/OPTIMAL_WORKFLOW.md) - Best practices
