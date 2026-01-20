# Multi-Agent Coordination Protocol

To ensure seamless collaboration between Antigravity, Copilot, Gemini, and other agents, we follow these coordination guidelines.

## 1. Task Handoffs

Any agent finishing a session or major task MUST update the shared state. This is done by:

- Updating `task.md` with detailed progress.
- Leaving a summary in the most recent `walkthrough.md` or a dedicated `COORDINATION.md`.

### Handoff Template
>
> **Last Active Agent**: [Agent Name]
> **Task Completed**: [Brief Summary]
> **Current Blockers**: [Any issues encountered]
> **Next Steps Planned**: [Clear list of immediate actions for the next agent]

## 2. GitHub Management

- **Issues**: Use labels (`enhancement`, `bug`, `priority:high`) to categorize tasks.
- **Pull Requests**:
  - Always create PRs for significant changes.
  - Reference the issue number in the PR description.
  - Tag other agents for review if their context is relevant (e.g., `@copilot please review this browser stealth update`).

## 3. Effective Delegation (`/delegate`)

- **Scope Control**: Keep delegated tasks small and well-defined.
- **Context Injection**: Use `--include` or mention specific files to ensure the delegated agent has all necessary information.
- **Verification**: The delegating agent is responsible for verifying the work of the sub-agent before merging.

## 4. Conflict Resolution

- If two agents are working on the same file, the last one to start should wait for the other to finish or coordinate via GitHub comments on the relevant issue.
- Avoid force-pushing to shared branches. Use `git fetch` and `rebase` to stay in sync.
