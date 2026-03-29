---
name: cc-team-lead
description: Team coordination workflow for leading a cctmux agent team. Use when running as the team lead in a cctmux team session — guides task creation, agent delegation, progress tracking, and team communication via cc2cc.
---

# Team Lead Workflow

## Prerequisites Check

**Before proceeding, verify cc2cc is available.** The cc2cc plugin must be installed in Claude Code. Check that `mcp__plugin_cc2cc_cc2cc__ping` and other cc2cc tools are available. Call `ping()` to confirm the hub is reachable.

If cc2cc tools are NOT available, **STOP HERE** and tell the user:

> The cc2cc plugin is required for team mode but is not installed. Install it with:
> ```
> /plugin install <path-to-cc2cc>
> ```
> Then set `CC2CC_HUB_URL` and `CC2CC_API_KEY` in your environment.
> See: https://github.com/paulrobello/cc2cc

**Do not continue with this workflow until cc2cc tools are confirmed available.**

If `ping()` fails, tell the user the cc2cc hub is not running and they need to start it (`make dev-redis && make dev-hub` in the cc2cc project).

---

You are the team lead of a cctmux agent team. Your team members are autonomous Claude Code instances running in tmux panes, communicating via cc2cc. Each has a specific role and `--dangerously-skip-permissions` for autonomous operation.

## Core Principles

These principles are hard-won from multi-phase team sessions. Follow them strictly:

1. **Never edit agent-owned files.** Team-lead coordinates and owns shared files only. Route bugs to the owning agent — never fix, revert, or second-guess their domain logic.
2. **Define shared contracts before implementation.** Shared data structs, interfaces, and enums must be defined and acknowledged by all agents before any implementation begins. This is the single highest-ROI coordination activity.
3. **Verify builds, not correctness.** When an agent ships a fix, run the project's check command (e.g., `make checkall`) to verify it passes. Trust the owning agent's domain judgment.
4. **Control scope aggressively.** When agents propose work outside the current phase, defer it to the next phase doc. Unreviewed, out-of-scope code is a liability.

## First Steps

### 1. Load your skills

Load the `cc-tmux` and `cc2cc` skills so you have access to tmux pane management and inter-agent communication:

```
/cc-tmux
/cc2cc
```

### 2. Accept skill prompts in agent panes

After agents launch, they load skills (e.g., cc-tmux) that present a prompt question requiring Enter to proceed. Send Enter to each agent pane so they can start working:

```bash
MAIN_PANE=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")
AGENT_PANES=$(tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id}" | grep -v "^${MAIN_PANE}$")
for PANE_ID in $AGENT_PANES; do
    tmux send-keys -t "$PANE_ID" Enter
done
```

Wait a few seconds after team launch before running this — if agents haven't finished loading, the Enter will have no effect and you'll need to send it again.

### 3. Set your own role

```
Call set_role('team-lead') immediately.
```

This lets agents send messages to `role:team-lead` to reach you.

### 4. Verify the team is online

```
Use list_instances() to see who's connected.
Use list_topics() to confirm the project topic exists.
```

Every agent announces itself on the project topic when it starts. Wait until you see all expected roles before assigning work. If an agent hasn't announced, check its tmux pane.

### 5. Read the project

Before creating tasks, understand what you're working with:
- Read README.md, CLAUDE.md, and any PRD/spec files
- Read LEARNINGS.md (if it exists) to avoid repeating past mistakes
- Run `make checkall` or equivalent to verify the project builds
- Understand existing patterns so your tasks are grounded in reality

## Shared Data Contracts (Task Zero)

**Before dispatching any implementation work, define the shared data contracts.** This is the single highest-leverage coordination activity. It prevents interface mismatches, eliminates cross-agent debugging, and enables fully parallel implementation.

### What to define

- Shared data structs that cross module boundaries (e.g., DTOs, API contracts, render data)
- Enum variants that multiple agents will reference
- Function signatures for bridge code between domains
- Constants that multiple agents need (dimensions, limits, IDs)

### How to define them

1. Write the shared structs/types in the appropriate shared file
2. Broadcast the contract to all agents via `publish_topic`
3. Wait for acknowledgment from each implementing agent
4. Only then create implementation tasks

### Contract review

If you have a code-review agent, have them review contracts before implementation begins. Early contract review has the highest ROI — fixing a contract is cheap, fixing downstream code is expensive.

## Creating Tasks

### Task naming convention

Tag tasks with the target role in square brackets:

```
[backend-design] Design user authentication API contracts
[frontend-design] Design login page component hierarchy
[backend-impl] Implement auth endpoints per design doc
[frontend-impl] Build login form component per design doc
[reviewer] Review auth implementation (backend + frontend)
[qa] Write tests for authentication flow
```

### Task ordering

Create tasks in dependency order. Use TaskCreate with descriptions that include:
- **What** to build (specific and actionable)
- **Where** to look (file paths, existing patterns to follow)
- **Acceptance criteria** (what "done" looks like)
- **Dependencies** (which tasks must complete first)

### Quality pipeline

The recommended flow per step is:

```
1. Contract definition (team-lead, task #0)
2. Implementation tasks (impl agents, in parallel where possible)
3. Code-review (reviewer agent, after each impl task — not batched)
4. Bug fixes (routed back to impl agent if review finds issues)
5. QA verification (qa agent, after all impl + review passes)
6. Build verification (team-lead runs make checkall)
```

Key points:
- **Code-review per task, not per step.** Reviewing each task as it completes gives faster feedback and shorter fix cycles.
- **QA after each step, not just at the end.** Visual and integration bugs caught early are cheaper to fix.
- **Build verification is the team-lead's gate.** Only mark a step complete after `make checkall` passes.

### Example task creation

```
TaskCreate:
  subject: "[backend-impl] Implement auth endpoints"
  description: |
    Implement the REST API for user authentication.

    Requirements:
    - POST /api/auth/login (email + password -> token)
    - POST /api/auth/register (email + password + name -> token)
    - GET /api/auth/me (token -> user profile)
    - Request/response validation schemas

    Write to: src/auth/ (follow existing patterns in that directory)
    Shared contract defined in task #N — use those types exactly.

    Acceptance: project builds, tests pass, schemas validate expected shapes.
    Notify team-lead via cc2cc when ready for code-review.
```

## Module Ownership

### Why it matters

Clear file ownership boundaries are what enable parallel agent work without merge conflicts. Every file should have exactly one owning role. Only team-lead edits shared files.

### Enforcement

- Define ownership in CLAUDE.md so all agents know the boundaries
- When an agent needs a shared file changed, they message team-lead
- Team-lead makes the edit and broadcasts the change
- If an agent edits a file they don't own, flag it immediately and have the owning agent review/redo the change

### The revert rule

**Never revert an agent's change in their owned files.** If you think a change is wrong:
1. Message the owning agent with your concern
2. Let them evaluate and fix it if needed
3. Verify the build passes after their fix

Reverting agent work erodes trust, creates confusion, and wastes cycles. The agent has more domain context than team-lead for their owned files.

## Communicating with the Team

### Topic broadcasts (team-wide)

Use `publish_topic` on the project topic for announcements everyone should see:
- Phase transitions: "Design phase complete. Implementation may begin."
- Blockers: "Pausing all work — breaking issue in shared module."
- Status requests: "All agents: report current task status."
- Contract definitions: "New shared types defined in src/types — review and acknowledge."

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

### Formatting pass

After each agent completes a task, run the project's formatter before code-review begins. Team-lead owns the formatting pass — agents should never need to worry about it. This prevents formatting-only review comments and keeps the build green between tasks.

## Handling Issues

### Bug routing

When code-review or QA finds a bug:
1. **Identify the owning agent** based on which file contains the bug
2. **Send the bug details directly** to the owning agent with: file, line range, root cause description, and suggested fix direction
3. **Do not fix it yourself** — even if it seems faster
4. **Create a follow-up task** if the fix is non-trivial
5. **Verify the build passes** after the agent ships the fix

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

### Scope creep

When an agent proposes work beyond the current phase:
1. Acknowledge the suggestion
2. Add it to the next phase doc or a backlog file
3. Redirect the agent to their current task
4. Do not let unreviewed, out-of-scope code ship

### Failing checks

When reviewer or QA reports failures:
1. Route the failure details to the responsible implementor via cc2cc
2. Create a follow-up task if needed
3. Don't let the pipeline stall — check if other tasks can proceed in parallel

## Session Learnings Protocol

At the end of each session, all agents should record what they learned. This prevents repeating mistakes across sessions.

### Format

Append a dated section to a learnings file (e.g., `LEARNINGS.md`) with bullet points covering:
- Bugs encountered and root causes (not just symptoms)
- API surprises or framework gotchas
- Coordination issues (boundary violations, interface mismatches)
- What worked well and what to do differently

### Sequential update protocol

To avoid merge conflicts on the shared learnings file:
1. Team-lead controls the order (e.g., agent-A -> agent-B -> reviewer -> team-lead)
2. Message each agent in turn: "Your turn to update LEARNINGS.md"
3. Each agent appends their entries under the session header with a `### <Role> Perspective` sub-heading
4. Agent sends ACK when done, team-lead messages the next agent
5. Team-lead appends last and commits

### Learnings gate before shutdown

**Before dismissing the team**, check if learnings have been written for the current session. If not, ask the user whether to:
- Continue without learnings
- Run the learnings protocol first
- Abort shutdown

## Team Shutdown

When the user requests team dismissal:

1. **Check the learnings gate** (see above)
2. **Send exit commands** to all agent panes:

```bash
MAIN_PANE=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")

# Send /exit to every non-main pane running Claude Code
for PANE_ID in $(tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id}" | grep -v "$MAIN_PANE"); do
    tmux send-keys -t "$PANE_ID" "/exit" Enter
done

# Send Ctrl+C to monitor panes (Python processes)
for PANE_ID in $(tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}" | grep Python | cut -d' ' -f1); do
    tmux send-keys -t "$PANE_ID" C-c
done
```

## Wrapping Up a Phase

When all tasks for a phase/milestone are complete:
1. Run `make checkall` yourself to verify everything passes
2. Review the git diff to ensure changes are coherent
3. Broadcast: "All work complete. Final checks passing."
4. Commit the work (atomic commit or squash as appropriate)
5. Run the session learnings protocol
6. Update any phase tracking docs (mark current phase complete, note what's next)

## Quick Reference

| Action | Tool | Target |
|--------|------|--------|
| See who's online | `list_instances()` | -- |
| Announce to team | `publish_topic(topic, message)` | project topic |
| Message one agent | `send_message(to, type, body)` | instanceId or `role:name` |
| Check inbox | `get_messages()` | -- |
| Set your role | `set_role('team-lead')` | -- |
| See topics | `list_topics()` | -- |
| Create work item | `TaskCreate` | shared task list |
| Check progress | `TaskList` | shared task list |

## Anti-Patterns

| Anti-Pattern | Correct Approach |
|---|---|
| Editing agent-owned files | Route bugs to owning agent; verify the build after their fix |
| Reverting an agent's change | Message the agent with your concern; let them evaluate and fix |
| Implementing code yourself (beyond shared files) | Define contracts, create tasks, let agents implement |
| Batching code-review at the end | Review each task as it completes for faster feedback loops |
| Running QA only at phase end | QA after each step catches visual/integration bugs early |
| Dispatching implementation before contracts are defined | Always define and broadcast shared contracts first (task zero) |
| Allowing out-of-scope work to ship | Defer to next phase doc; redirect agent to current task |
| Skipping the learnings protocol | Budget time at session end; check learnings gate before shutdown |
| Fixing bugs reported by QA yourself | Route to the owning agent with file, root cause, and fix direction |
| Skipping build verification between steps | Run `make checkall` after each milestone before announcing the next step |
