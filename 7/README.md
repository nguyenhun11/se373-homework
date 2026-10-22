# Challenge A — Persistent memory (+ agent loop)

Analytics agent ("Chợ Sen", fake SQLite data) that remembers project conventions across sessions,
updates them when they change, and answers data questions with a tool-using agent loop.

| File | Role |
|---|---|
| `agent.py` | Session + agent loop + LLM backends |
| `tools.py` | Tool registry (the system prompt is generated from it) |
| `db.py` | Sample DB (`python3 db.py` rebuilds it) + read-only query tools |
| `memory_store.py` | Persistent memory (supersede, not append) |
| `demo.sh` → `demo_output.txt` | Proof 1 + Proof 2 |
| `demo_loop.sh` → `demo_loop_output.txt` | Multi-step, self-correction, read-only guard |

Each `python3 agent.py ...` call is a new session with empty chat history.

## Memory design

| Hint | Choice |
|---|---|
| Where to store | `memory/memory.json` (source of truth: key, value, status, timestamps, source session) + generated `memory/MEMORY.md` for humans |
| Who writes | The agent, via the `remember` / `forget` / `history` tools. Only durable conventions are stored, not chat |
| When loaded | At session start: all **active** conventions are injected into the system prompt (`<project_memory>`) |
| When a convention changes | Upsert by key: the old record is marked `superseded` (who, when, why), not deleted; only active records are injected |
| Verification | `--show-context` prints the exact memory block injected; `--dump-memory` prints the full store incl. history |

Proof 1: session 2 (no chat history) computes Q1/2025 revenue = `SUM(total_amount)` of delivered orders, alias `revenue_vnd`.
Proof 2: session 3 switches to net revenue; session 4 returns `SUM(total_amount - discount_amount)`, with lower numbers that match the ground truth printed at the end of `demo.sh`.

## Agent loop

```
user message → [THINK] LLM sees: system prompt (tools + memory) + session messages
             → reply {"thought", "tool", "args"} → [ACT] run tool → [OBSERVE] append result → repeat
             → reply {"thought", "final"}        → answer
```

| Mechanism | Purpose |
|---|---|
| `MAX_STEPS = 10` | Hard cap on LLM calls per user message |
| Errors returned as observations | SQL errors / bad tool args go back to the model so it can fix them (self-correction) |
| `MAX_CONSECUTIVE_ERRORS = 3` | Stop when the agent cannot recover |
| Invalid JSON → retry message | A malformed reply is not silently treated as the answer |
| Repeated identical call blocked | Prevents loops calling the same tool with the same args |
| Observation capped at 20 rows | Keeps raw data out of the context |
| Read-only: SQL guard + `mode=ro` connection | Writes are blocked in code, not just in the prompt |
| `sessions/<id>.jsonl` | Full trace per session (thought, action, observation) |

Limitation: if the model invents a new key instead of reusing the existing one, both rules stay active. This is reduced by showing the existing keys in context and telling the model to reuse them. A stronger fix would be to have the harness check for conflicts before writing.
