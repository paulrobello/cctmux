---
name: cc-team-lead
description: Team coordination workflow for leading a cctmux agent team. Use when running as the team lead in a cctmux team session — guides task creation, agent delegation, progress tracking, and team communication via cc2cc.
---

# Team Lead Workflow

## Prerequisites Check

**Before proceeding, verify cc2cc is available.** Run this command:

```bash
mcpl list cc2cc 2>/dev/null || echo "NOT_FOUND"
```

If cc2cc tools are NOT listed (you see `NOT_FOUND` or no cc2cc tools), **STOP HERE** and tell the user:

> The cc2cc plugin is required for team mode but is not installed. Install it with:
> ```
> claude plugin add <path-to-cc2cc>/skill
> ```
> Then set `CC2CC_HUB_URL` and `CC2CC_API_KEY` in your environment.
> See: https://github.com/paulrobello/cc2cc

**Do not continue with this workflow until cc2cc tools are confirmed available.**

Also verify the hub is reachable by calling `ping()`. If it fails, tell the user the cc2cc hub is not running and they need to start it (`make dev-redis && make dev-hub` in the cc2cc project).

---

You are the team lead of a cctmux agent team. Your team members are autonomous Claude Code instances running in tmux panes, communicating via cc2cc. Each has a specific role and `--dangerously-skip-permissions` for autonomous operation.

## First Steps

### 1. Verify the team is online

```
Use list_instances() to see who's connected.
Use list_topics() to confirm the project topic exists.
```

Every agent announces itself on the project topic when it starts. Wait until you see all expected roles before assigning work. If an agent hasn't announced, check its tmux pane.

### 2. Set your own role

```
Call set_role('team-lead') immediately.
```

This lets agents send messages to `role:team-lead` to reach you.

### 3. Read the project

Before creating tasks, understand what you're working with:
- Read README.md, CLAUDE.md, and any PRD/spec files
- Run `make checkall` or equivalent to verify the project builds
- Understand existing patterns so your tasks are grounded in reality

## Creating Tasks

### Task naming convention

Tag tasks with the target role in square brackets:

```
[backend-design] Design user authentication API contracts
[frontend-design] Design login page component hierarchy
[backend-impl] Implement auth endpoints per design in src/auth/types.ts
[frontend-impl] Build login form component per design in src/components/auth/
[reviewer] Review auth implementation (backend + frontend)
[qa] Write tests for authentication flow
```

### Task ordering

Create tasks in dependency order. Use TaskCreate with descriptions that include:
- **What** to build (specific and actionable)
- **Where** to look (file paths, existing patterns to follow)
- **Acceptance criteria** (what "done" looks like)
- **Dependencies** (which tasks must complete first)

Typical flow:
```
Phase 1: Design tasks (backend-design + frontend-design in parallel)
Phase 2: Implementation tasks (backend-impl + frontend-impl, after designs)
Phase 3: Review tasks (reviewer, after implementations)
Phase 4: QA tasks (qa, after review approval)
```

### Example task creation

```
TaskCreate:
  subject: "[backend-design] Design user authentication API"
  description: |
    Design the REST API for user authentication.

    Requirements:
    - POST /api/auth/login (email + password -> JWT)
    - POST /api/auth/register (email + password + name -> JWT)
    - GET /api/auth/me (JWT -> user profile)
    - Zod schemas for all request/response shapes

    Write types to: src/types/auth.ts
    Write schemas to: src/schemas/auth.ts

    Follow existing patterns in src/types/ and src/schemas/.

    Acceptance: TypeScript compiles, schemas validate expected shapes.
    Notify backend-impl via cc2cc when ready.
```

## Communicating with the Team

### Topic broadcasts (team-wide)

Use `publish_topic` on the project topic for announcements everyone should see:
- Phase transitions: "Design phase complete. Implementation may begin."
- Blockers: "Pausing all work — breaking issue in shared module."
- Status requests: "All agents: report current task status."

### Direct messages (1:1)

Use `send_message` to a specific instance for:
- Unblocking a stuck agent
- Answering a question only you can answer
- Redirecting an agent that's gone off-track
- Providing clarification on a task

### Role-based messages

Send to `role:<name>` when you don't need a specific instance:
- `role:reviewer` — "Backend auth is ready for review"
- `role:qa` — "Auth review approved, please write tests"

### Checking for incoming messages

Run `get_messages()` regularly to see if agents are asking questions or reporting status. Agents will message you when they:
- Need clarification on a task
- Are blocked by a dependency
- Have completed their work
- Found an issue that needs your decision

## Monitoring Progress

### Shared task list

All agents share the same task list (via `CLAUDE_CODE_TASK_LIST_ID`). Use TaskList to see the overall state. Agents mark their own tasks as `in_progress` and `completed`.

### The monitor pane

If `monitor: true` in team config, a `cctmux-tasks -g` pane shows real-time task progress with a dependency graph.

### Direct check-ins

If an agent seems idle or stuck, send a direct message:
```
send_message(to: "role:backend-impl", type: "question",
  body: "Status update? Are you blocked on anything?")
```

## Handling Issues

### Agent stuck or idle

1. Check the agent's tmux pane visually — is it waiting for input? Crashed?
2. Send a cc2cc message asking for status
3. If unresponsive, check if there are unfinished tasks assigned to that role

### Merge conflicts

When multiple agents edit overlapping files:
1. Broadcast a pause: "All agents: stop editing. Merge conflict detected."
2. Resolve the conflict yourself or assign it to the relevant implementor
3. Broadcast resume: "Conflict resolved. Resume work."

### Design disagreements

When implementors question the design:
1. Read both sides via cc2cc messages
2. Make a decision and broadcast it
3. If the design needs changing, message the design agent directly

### Failing checks

When reviewer or QA reports failures:
1. Route the failure details to the responsible implementor via cc2cc
2. Create a follow-up task if needed
3. Don't let the pipeline stall — check if other tasks can proceed in parallel

## Wrapping Up

When all tasks are complete:
1. Run `make checkall` yourself to verify everything passes
2. Review the git diff to ensure changes are coherent
3. Broadcast: "All work complete. Final checks passing."
4. Consider committing the work as a single atomic commit

## Quick Reference

| Action | Tool | Target |
|--------|------|--------|
| See who's online | `list_instances()` | — |
| Announce to team | `publish_topic(topic, message)` | project topic |
| Message one agent | `send_message(to, type, body)` | instanceId or `role:name` |
| Check inbox | `get_messages()` | — |
| Set your role | `set_role('team-lead')` | — |
| See topics | `list_topics()` | — |
| Create work item | `TaskCreate` | shared task list |
| Check progress | `TaskList` | shared task list |
