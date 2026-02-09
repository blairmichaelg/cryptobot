---
description: How to delegate tasks to GitHub Copilot agent using CLI
---

# GitHub Copilot CLI Delegation Workflow

This workflow describes how to use GitHub Copilot CLI to delegate coding tasks to the Copilot agent for autonomous background work.

## Prerequisites

// turbo
1. Ensure Node.js 22+ is installed: `node --version`
// turbo  
2. Install Copilot CLI: `npm install -g @github/copilot`
// turbo
3. Verify installation: `copilot --help`
4. Authenticate: Run `copilot` and follow prompts
5. Require GitHub Copilot Pro, Pro+, Business, or Enterprise subscription

## Built-in Agents (Automatic Delegation)

The new Copilot CLI has specialized built-in agents:
- **Explore**: Fast codebase analysis and Q&A
- **Task**: Running commands like tests and builds  
- **Plan**: Creating implementation plans
- **Code-review**: Reviewing changes with high signal-to-noise

### Method 2: Assign Issue to @copilot
1. Create a GitHub Issue describing the task
2. Assign the issue to `@copilot` user
3. Copilot will create a draft PR with changes

### Method 3: Comment on PR
1. On an existing PR, comment `@copilot` with your request
2. Example: `@copilot please add error handling to this function`

## What Happens When You Delegate

1. **Agent Works**: Copilot makes changes in background
2. **Draft PR Opened**: Changes submitted as draft pull request on a temporary branch
3. **Review Requested**: You receive notification to review
4. **Merge to master**: Squash-merge the PR to master, then delete the temporary branch
5. **Sync everywhere**: Pull master locally and on the VM to stay in sync

> **IMPORTANT**: This project uses a single-branch (`master`) workflow. If Copilot creates a branch for a PR, merge it to master promptly and delete the branch. Never leave stale branches.

## Best Use Cases

- ✅ Codebase maintenance (security fixes, dependency updates)
- ✅ Documentation updates
- ✅ Adding test coverage
- ✅ Refactoring existing code
- ✅ Prototyping new features
- ✅ Setting up development environments

## Example Delegation Tasks for Cryptobot

```bash
# Add tests
gh copilot suggest "create unit tests for browser/secure_storage.py"

# Documentation
gh copilot suggest "update README with new cookie encryption feature"

# Refactoring
gh copilot suggest "refactor duplicate code in faucets directory"
```

## Tips for Effective Delegation

1. **Be Specific**: Provide clear, detailed task descriptions
2. **Small Scope**: Break large tasks into smaller chunks
3. **Context**: Reference specific files or functions
4. **Acceptance Criteria**: Describe expected outcomes

## Monitoring Delegated Work

- Check draft PRs: `gh pr list --state open --draft`
- View Copilot sessions: Visit GitHub repository → Pull Requests
