# Driving & monitoring another Claude in a pane

When you orchestrate a second Claude Code instance running in another pane (drive it
via `send-keys`, read its state via `capture-pane`), two problems recur: knowing **when
it finishes a turn or stops to ask a question**, and **submitting commands reliably**.
This is the hardened recipe.

## Idle-or-heartbeat poller

A background poller that watches a Claude pane and exits when the remote Claude **goes
idle / starts waiting for input** OR after a **5-minute heartbeat** — whichever fires
first. Launch it detached (`run_in_background: true`) so the harness re-invokes you on
exit; then read its output, handle the pane, and re-arm a fresh poller.

```bash
PANE=%1            # target pane ID — get it from:
                   # tmux list-panes -t "$CCTMUX_SESSION" -F "#{pane_id} #{pane_current_command}"
miss=0
for i in $(seq 1 30); do                      # 30 * 10s = 5-min hard cap (heartbeat backstop)
  out=$(tmux capture-pane -p -t "$PANE" -S -25)
  # Active-spinner signatures — if ANY present, Claude is still working:
  #   "(NNs"            elapsed-time timer in the spinner parens
  #   "esc to interrupt"
  #   "NNk tokens"      token counter
  #   "thinking with"   extended-thinking spinner
  #   ✽ ✶ ✻ ✢          spinner glyphs
  if printf '%s' "$out" | grep -qE '\([0-9]+s |esc to interrupt|[0-9]+(\.[0-9]+)?k? tokens|thinking with|✽|✶|✻|✢'; then
    miss=0
  else
    miss=$((miss+1))
    if [ "$miss" -ge 6 ]; then                # 6 * 10s = 60s of silence => really idle/waiting
      echo "=== REASON: IDLE/WAITING confirmed (60s) after ~$((i*10))s ==="
      printf '%s\n' "$out" | tail -40
      exit 0
    fi
  fi
  sleep 10
done
echo "=== REASON: 5-MIN HEARTBEAT (still working) ==="
tmux capture-pane -p -t "$PANE" -S -25 | tail -40
```

### Why it's built this way

- **Two exit conditions, not one.** Idle-detection alone is unreliable — the spinner
  text isn't always on screen between tool calls — so the 5-min heartbeat is the hard
  backstop. You always re-check at least every 5 minutes.
- **Detect "working," infer "idle" from its absence.** Don't try to positively match the
  idle prompt; match the *active-spinner* signatures and treat their absence as idle. The
  multi-pattern `grep -qE` matters because no single token (e.g. "esc to interrupt")
  appears in every spinner frame — extended-thinking frames render
  `(48s · ↓ 2.7k tokens · thinking with high effort)` instead.
- **Require ~60s of silence (6 consecutive misses), not 30s.** Brief inter-tool gaps
  tripped a 30s threshold; 60s eliminates false positives while real idle/question states
  persist indefinitely.
- **`-S -25`** captures enough scrollback that a question menu which pushed the spinner
  off the last few lines is still in the grab.
- **Version-robustness:** the glyph set (`✽ ✶ ✻ ✢`) and `thinking with` string are from
  the current Claude Code build. Across releases, the `(NNs` timer and `esc to interrupt`
  patterns are the most stable — keep those first.

## Companion gotcha — submitting commands to the pane

Send the command text **and** `Enter` in a *single* `send-keys` call:

```bash
tmux send-keys -t %1 "/clear" Enter
tmux send-keys -t %1 "/sdlc-plugin:implement-work-item #57" Enter
```

Sending `Enter` as a *separate* call lands on autosuggestion **ghost text** (an empty
input box rendering a greyed last-command suggestion) and submits nothing. `Ctrl+U`
won't "clear" it because the box is already empty — typing the real command replaces the
ghost, then the trailing `Enter` submits.

## Answering a question menu in the remote pane

Selection menus (plan-mode design questions, plan approval, worktree disposition) show
`❯` on the default option with the footer `Enter to select · ↑/↓ to navigate`. To pick a
non-default option, send `Down`/`Up` to move the `❯`, verify with a capture, then `Enter`
in a separate call (menus accept bare arrow/Enter keys, not the one-call pattern):

```bash
tmux send-keys -t %1 Down            # move selection
tmux capture-pane -p -t %1 -S -16 | grep -nE "❯"   # verify which option is highlighted
tmux send-keys -t %1 Enter           # confirm
```
