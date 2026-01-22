# Quick Reference: GitHub Workflow Commands

## Call from Chat

Just type any of these commands in the VS Code chat:

```
python meta.py workflow
```

## Available Commands

### Dry Run (Safe - Just Preview)
```bash
python meta.py workflow
```
Shows what would happen without making any changes.

### Execute Workflow
```bash
python meta.py workflow --execute
```
Syncs repo, delegates issues, pushes changes. Won't merge PRs.

### Full Automation
```bash
python meta.py workflow --execute --auto-merge
```
Does everything including auto-merging PRs with passing checks.

## What It Does

1. ✓ Pulls latest from master (stashes uncommitted changes first)
2. ✓ Lists all open PRs and issues
3. ✓ Reviews PRs - merges those with passing CI checks
4. ✓ Delegates open issues to Copilot coding agent
5. ✓ Pushes any local commits
6. ✓ Shows summary of activity

## Common Workflows

**Morning routine:**
```bash
python meta.py workflow --execute
```

**After Copilot finishes work:**
```bash
python meta.py workflow --execute --auto-merge
```

**Just check status:**
```bash
python meta.py workflow
```

## Related Commands

```bash
# Just sync without automation
python meta.py sync --merge --push

# Check system health
python meta.py health

# See full help
python meta.py --help
```

## Troubleshooting

**"Not authenticated"**: Run `gh auth login`

**"Uncommitted changes"**: The workflow auto-stashes them. Run `git stash pop` after to restore.

**PR won't merge**: Check if CI is passing with `gh pr checks <number>`

## Protocol Compliance

- ✓ Single branch (master only)
- ✓ No manual branch creation
- ✓ Auto-stash before pull
- ✓ Auto-cleanup after merge
- ✓ Push immediately after changes

See [GITHUB_WORKFLOW.md](GITHUB_WORKFLOW.md) for full documentation.
