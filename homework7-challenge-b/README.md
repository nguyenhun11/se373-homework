# SE373 — Challenge A (persistent memory) + Challenge B (context management)

## Challenge A — Persistent memory (+ agent loop)

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

### Memory design

| Hint | Choice |
|---|---|
| Where to store | `memory/memory.json` (source of truth: key, value, status, timestamps, source session) + generated `memory/MEMORY.md` for humans |
| Who writes | The agent, via the `remember` / `forget` / `history` tools. Only durable conventions are stored, not chat |
| When loaded | At session start: all **active** conventions are injected into the system prompt (`<project_memory>`) |
| When a convention changes | Upsert by key: the old record is marked `superseded` (who, when, why), not deleted; only active records are injected |
| Verification | `--show-context` prints the exact memory block injected; `--dump-memory` prints the full store incl. history |

Proof 1: session 2 (no chat history) computes Q1/2025 revenue = `SUM(total_amount)` of delivered orders, alias `revenue_vnd`.
Proof 2: session 3 switches to net revenue; session 4 returns `SUM(total_amount - discount_amount)`, with lower numbers that match the ground truth printed at the end of `demo.sh`.

### Agent loop

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

---

## Challenge B — Context management (same agent)

Goal: keep the context small while the agent still does the right thing. Challenge B extends the Challenge A agent rather than replacing it: the loop, tool registry, memory and read-only DB are unchanged, and both features are off by default.

| File | Role |
|---|---|
| `logs.py` | 20 fake service logs (`data/logs/`, 4.5 MB, 4 services × 5 days) with a planted incident; `--truth` prints the ground truth |
| `codemode.py` | B2 runtime: runs `run_code` programs in a confined child process, exposes the `tools` SDK |
| `agent.py` | + `usage` token accounting, `--mode native\|code`, `--context-budget N` (compaction) |
| `demo_b2.sh` → `demo_b2_output.txt` | Same 3 questions, native vs Code Mode, token table + ground truth |
| `demo_b1.sh` → `demo_b1_output.txt` | 6-turn investigation, compaction ON vs OFF |

**Planted incident:** on 2025-03-14 at 19:58 a deploy lowers `gateway.vnpay.timeout_ms` from 3000 to 300 → VNPay charges time out (`PAY_GATEWAY_TIMEOUT`) → 504s on nginx → 34 orders fail (`ORDER_PAYMENT_FAILED`, total_amount 346,100,000 VND) until the rollback at 21:04.
**Red herring:** an inventory `STOCK_SYNC_LAG` burst at 20:25–20:34, which makes inventory-service the service with the *most* ERROR lines that day.

**Measuring:** every LLM call reads input tokens from the provider's `usage` (Anthropic: `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`; OpenAI: `prompt_tokens`; `claude -p --output-format json` returns the Anthropic usage). The numbers are printed per step (`(12,345 tok in)`), per turn and per session, and logged in `sessions/<id>.jsonl`.

### B2 — Code Mode

| | Native tools (`--mode native`) | Code Mode (`--mode code`) |
|---|---|---|
| Model gets | `list_logs`, `read_log` (≤200 lines), `grep_log` (≤100 lines) | `list_logs`, `run_code(code)` |
| Who loops over files | the LLM, one tool call per step | the program |
| What enters the context | raw log lines, every step, cumulatively | only what the program `print`s (≤2,000 chars) |

The data tools are the same; only the caller changes. Programs use `tools.list_logs / read_log / grep / parse / run_sql` with no line caps, because the data stays in the runtime.

**Where does the code run?** In a separate `python3 -I` process, not inside the agent:
- inside `bwrap` (bubblewrap) when installed: read-only `/usr` + this project's `data/` and modules, private `/tmp`, `--unshare-all` (no network), `--clearenv` (no API keys), killed with the parent
- `setrlimit`: 20 s CPU, 1 GB memory, 1 MB file writes; 20 s wall-clock timeout
- SQL stays read-only (`SELECT/WITH` guard + SQLite `mode=ro`)
- errors / timeouts / empty output are returned as observations so the model can fix its program

Checked: network access, writing to the project, `DELETE` SQL and `while True` are all rejected. This is a confined runtime, **not a hardened sandbox**: production would need a container/VM, per-tool permission checks and audit logs.

**Result** (`demo_b2.sh`, model haiku via `claude -p`, all 6 answers match the ground truth):

| Question | Mode | LLM calls | Input tokens (sum) | Context at last call |
|---|---|---|---|---|
| Q1 service with most ERRORs + top code | native | 6 | 66,971 | 20,709 |
| | code | 2 | **5,058** | 2,826 |
| Q2 hour of the timeouts + event just before | native | 3 | 32,747 | 19,812 |
| | code | 2 | **5,882** | 3,636 |
| Q3 failed orders → SUM(total_amount) from DB | native | 4 | 20,068 | 6,419 |
| | code | 4 | **12,824** | 3,911 |

Code Mode uses 1.6–13× fewer input tokens. The gap is largest when the answer needs many raw lines (Q1, Q2) and smallest when a narrow grep already returns little (Q3). Each run is a single sample and LLM runs vary, so the exact ratios change from run to run.

### B1 — Compaction

**When** (slide "Thời điểm compact": don't wait until the context is full):
- at a **turn boundary** (a milestone) once the measured context passes **60 %** of `--context-budget`
- **mid-turn only as an emergency** (> 90 %), and then only the *earlier* turns: evidence the current turn is still working with is never compacted
- skipped when there is less than ~1,500 tokens of old material (not worth an extra LLM call)
- manually with `/compact` in the REPL

**How** (a controlled reboot of the working context):
1. **Tool-output pruning:** old observations are cut to their header + up to 40 signal lines (ERROR/WARN/code=/config); health checks and raw lines are dropped.
2. **Structured checkpoint:** one LLM call merges the previous checkpoint with the pruned transcript into a fixed schema: `goal, constraints, current_state, findings[{fact, evidence}], failed_attempts[{attempt, why_failed}], open_questions, files_examined, next_action`. It is saved to `sessions/<id>.checkpoint.json`.
3. **Rebuild:** `system prompt (memory) + [CHECKPOINT] + latest messages verbatim`.

**Keep / truncate / drop** (selective compaction):

| Keep | Truncate | Drop |
|---|---|---|
| goal, user constraints, findings with numbers + evidence, failed attempts + why, open questions, next action. **All user messages are copied verbatim by code**, not by the LLM, so constraints cannot be summarised away. Project memory stays in the system prompt. | long tool outputs → a few signal lines | raw log lines, duplicates, health checks, data that is cheap to re-fetch (the checkpoint says to re-run the tool instead of reconstructing values) |

**Test** (`demo_b1.sh`): 6 turns in one session with native tools. The user sets 2 constraints (no "restart service", times as HH:MM) and the session tries 2 wrong hypotheses (inventory, momo) before finding the config change. Turn 5 asks "what are we investigating, what did we try, what's next?" after compaction; turn 6 asks for the root cause and numbers.

**Result** (`demo_b1_output.txt`, budget 30,000 tokens):

| | Compaction ON | Compaction OFF |
|---|---|---|
| Compactions | 3 (2 emergency mid-turn, earlier turns only; 1 at a turn boundary) | 0 |
| Largest context sent | 28,030 tokens (mid-turn; emergency compaction keeps it near the budget) | 63k tokens, still growing |
| Context at the end | 21,559 tokens | 63,067 tokens |
| Input tokens, whole session (incl. the 3 checkpoint calls) | **312,475** | 740,948 |
| Turn 5 summary after compaction | goal, both constraints, inventory ruled out (lag starts 20:25, 504s start 20:02), momo ruled out (no timeouts), 19:58 config change, next steps without restart | same content |
| Turn 6 answer | config change 3000→300 ms at 19:58; 34 orders, 346,100,000 VND (= ground truth); no restart; HH:MM times | same |

The compacted session reaches the same correct conclusion with 2.4× fewer input tokens, and its context stays under the budget instead of growing every turn.

**Lesson from the first version:** compacting as soon as the context passed 60 % (mid-turn, keeping only the last 4 messages) made the agent compact on almost every step (a single 200-line read is ~8k tokens), and pruning cut a grep result the current turn still needed (34 order ids → 12). The agent then **invented 22 order ids** and stopped at the step limit. This is the "loses state" risk from the slides, and it is why compaction now runs at turn boundaries, never touches the current turn's evidence, and tells the model to re-run tools instead of reconstructing values.

### Combining both

Known data limitation: the order ids in the fake logs are drawn at random from the DB, so their `order_date` / `status` in `orders` do not match the incident (the OFF run noticed this). The log→SQL join and the totals are still checked against the ground truth.

`python3 agent.py --mode code --context-budget 30000` uses both techniques together. Code Mode slows down how fast the context grows; compaction is the checkpoint for long sessions.
