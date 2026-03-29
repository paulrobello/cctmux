# Team Mode Reference

When running inside a team session (`cctmux team`), the same pane management commands work — each agent has its own pane in the shared tmux session. Additional team-specific environment variables are available:

| Variable | Description |
|----------|-------------|
| `CC2CC_SESSION_ID` | Unique per-pane session ID for cc2cc communication |
| `CLAUDE_CODE_TASK_LIST_ID` | Shared task list ID (when `shared_task_list` is enabled) |

## Team Agent Configuration

Each agent in the team config supports these fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `role` | string | (required) | Agent role name (e.g., `architect`, `implementer`) |
| `prompt` | string | `""` | Role-specific system prompt injected via `--append-system-prompt-file` |
| `model` | string | `null` | Claude model to use via `--model` (e.g., `sonnet`, `opus`) |
| `claude_args` | string | `null` | Per-agent Claude CLI arg overrides |

```yaml
team:
  agents:
    - role: architect
      model: opus
      prompt: |
        You lead the team.
    - role: tester
      model: sonnet
      prompt: |
        Write and run tests.
```

## Accepting Skill Prompts in Agent Panes

After team agents launch and load their skills (e.g., the cc-tmux skill), they may present a prompt question that requires pressing Enter to accept. The team lead must send Enter to each agent pane via tmux so agents can proceed:

```bash
# List agent panes (exclude the lead's own pane)
MAIN_PANE=$(tmux display-message -t "$CCTMUX_SESSION" -p "#{pane_id}")
AGENT_PANES=$(tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id}" | grep -v "^${MAIN_PANE}$")

# Send Enter to each agent pane to accept the prompt
for PANE_ID in $AGENT_PANES; do
    tmux send-keys -t "$PANE_ID" Enter
done
```

**Important**: Wait a few seconds after team launch for agents to finish loading before sending Enter. If sent too early (before the prompt appears), it will have no effect and you may need to send it again.

## Team Coordination

For team coordination workflows (task delegation, inter-agent messaging, progress tracking), load the **cc-team-lead** skill:

```
/cc-team-lead
```
