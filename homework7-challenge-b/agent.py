"""Analytics agent with an agent loop, persistent project memory (Challenge A)
and context management: Code Mode + compaction (Challenge B).

Each run of this script is a NEW session: no chat history is carried over.
The only thing that survives between sessions is memory/memory.json.

Agent loop (per user message):
    context = system prompt (tools + injected memory) + session messages
    repeat up to MAX_STEPS:
        [compact first if the context is over budget]          (B1, --context-budget)
        LLM -> {"thought", "tool", "args"}  -> run tool -> append observation
            or {"thought", "final"}         -> return answer
    stop early on: final answer | MAX_STEPS | MAX_CONSECUTIVE_ERRORS
Every LLM call reports its input tokens (provider `usage`) in the trace and the session log.

Usage:
    python agent.py "message"            # one-shot session
    python agent.py                      # interactive session (REPL); /compact forces a compaction
    python agent.py --mode code ...      # B2: log tools only reachable through run_code
    python agent.py --context-budget 20000 ...   # B1: compact when the context passes 60% of this
    python agent.py --show-context ...   # also print the injected memory block
    python agent.py --dump-memory        # print the full store, incl. history

LLM backend (auto-detected, override with AGENT_BACKEND):
    anthropic  : ANTHROPIC_API_KEY  (model: AGENT_MODEL, default claude-haiku-5-5)
    openai     : OPENAI_API_KEY (+ OPENAI_BASE_URL for Gemini/Groq/Ollama compat)
    claude-cli : local `claude -p` as a plain text-completion backend
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import memory_store
from tools import Toolbox


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding real environment variables."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value


load_dotenv(Path(__file__).with_name(".env"))

SESSIONS_DIR = Path(__file__).parent / "sessions"
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", 10))  # hard cap on LLM calls per user message
MAX_CONSECUTIVE_ERRORS = 3   # stop if the agent cannot recover from errors
OBS_PREVIEW = 400            # chars of each observation printed in the trace
COMPACT_AT = 0.6             # compact at a turn boundary past this share of the budget, not when it is full
EMERGENCY_AT = 0.9           # mid-turn compaction (earlier turns only) past this share
MIN_COMPACTABLE = 1500       # tokens of old material needed before a compaction is worth an LLM call
CHARS_PER_TOKEN = 3          # rough estimate for text added since the last measured call

SYSTEM_TEMPLATE = """You are an analytics agent for the SE373 project "Chợ Sen" (Vietnamese e-commerce).
You answer business questions by exploring the SQLite database and running SQL, and you
investigate incidents in the service logs (data/logs, one file per service per day).
Explain results with the actual numbers. Answer in the user's language.

PROJECT MEMORY — conventions agreed in previous sessions. They are binding:
apply them to every query and answer unless the user changes them in this session.
{memory}

TOOLS
{tools}

HOW TO WORK
- Data questions: inspect the schema first (list_tables / describe_table) unless you
  already know it in this session, then run_sql. Never invent numbers: every number
  in the final answer must come from a tool observation.
- Log questions: use the log tools above. Count and compare before concluding; the
  noisiest service is not necessarily the cause.
- If a tool returns an ERROR, read it, fix the call and try again.
- When the user states a NEW durable convention or CHANGES one, call remember.
  If it replaces a convention listed above, REUSE THAT EXACT KEY.
  Do not store one-off questions, query results, investigation notes or chit-chat.
- If the conversation starts with a [CHECKPOINT], it is your own compacted notes of the
  earlier part of this session: trust it, follow its constraints, do not redo its failed attempts.
- In the final answer, show the SQL / code you ran and say which conventions you applied.

RESPONSE FORMAT — reply with exactly one JSON object and nothing else:
  {{"thought": "<short reasoning>", "tool": "<tool name>", "args": {{...}}}}   to call ONE tool, or
  {{"thought": "<short reasoning>", "final": "<answer to the user>"}}          to finish."""

COMPACT_SYSTEM = """You compact the working context of an analytics / incident-investigation agent.
You get the previous checkpoint (may be empty) and the OLDER part of the session transcript
(long tool outputs are already cut down). Write an UPDATED checkpoint so the agent can continue
the work with no other memory of this part of the session.

Selective compaction rules:
- KEEP exactly: the goal, every constraint / decision the user stated, unresolved errors and
  questions, findings with their concrete numbers, times, ids and file names, and the evidence
  (tool + file/pattern/query) behind each finding.
- KEEP failed attempts and ruled-out hypotheses WITH the reason, so they are not retried.
- TRUNCATE tool output to the one or two lines that matter.
- DROP raw log lines, duplicates, health checks, chit-chat, and data that is cheap to re-fetch
  (mention the tool call instead).
- Never add facts that are not in the transcript or the previous checkpoint. Merge with the
  previous checkpoint: keep its content unless the transcript supersedes it.

Reply with ONLY this JSON object:
{"goal": "", "constraints": [""], "current_state": "", "findings": [{"fact": "", "evidence": ""}],
 "failed_attempts": [{"attempt": "", "why_failed": ""}], "open_questions": [""],
 "files_examined": [""], "next_action": ""}"""


# ---------------------------------------------------------------- backends
def _http_json(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def call_llm(system: str, messages: list[dict]) -> tuple[str, int]:
    """Returns (reply text, input tokens of this call as reported by the provider's usage)."""
    backend = os.environ.get("AGENT_BACKEND") or (
        "anthropic" if os.environ.get("ANTHROPIC_API_KEY")
        else "openai" if os.environ.get("OPENAI_API_KEY")
        else "claude-cli" if shutil.which("claude")
        else None
    )
    if backend == "anthropic":
        data = _http_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
             "content-type": "application/json"},
            {"model": os.environ.get("AGENT_MODEL", "claude-haiku-5-5"), "max_tokens": 2000,
             "system": system, "messages": messages},
        )
        return "".join(b.get("text", "") for b in data["content"]), _input_tokens(data["usage"])
    if backend == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        data = _http_json(
            f"{base}/chat/completions",
            {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "content-type": "application/json"},
            {"model": os.environ.get("AGENT_MODEL", "gpt-4o-mini"),
             "messages": [{"role": "system", "content": system}, *messages]},
        )
        return data["choices"][0]["message"]["content"], data.get("usage", {}).get("prompt_tokens", 0)
    if backend == "claude-cli":
        # Stateless call: no tools, no settings/CLAUDE.md, no MCP, no saved session,
        # run from /tmp so nothing but OUR context reaches the model.
        transcript = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages)
        out = subprocess.run(
            ["claude", "-p", "--system-prompt", system, "--tools", "", "--setting-sources", "",
             "--strict-mcp-config", "--no-session-persistence", "--output-format", "json",
             "--model", os.environ.get("AGENT_MODEL", "haiku"),
             transcript + "\n\n[ASSISTANT] (reply with one JSON object)"],
            capture_output=True, text=True, cwd="/tmp", timeout=300,
        )
        try:
            data = json.loads(out.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(out.stderr or out.stdout) from None
        if out.returncode != 0 or data.get("is_error"):
            raise RuntimeError(data.get("result") or out.stderr)
        return data["result"], _input_tokens(data["usage"])
    sys.exit("No LLM backend: set ANTHROPIC_API_KEY or OPENAI_API_KEY, or install the claude CLI.")


def _input_tokens(usage: dict) -> int:
    # Anthropic splits the prompt into uncached + cache-write + cache-read; all of it is context.
    return (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0))


def first_json(text: str, keys: tuple[str, ...] = ()) -> dict | None:
    """Return the first JSON object in the reply (having one of `keys`, if given), or None."""
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj, dict) and (not keys or any(k in obj for k in keys)):
                return obj
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    return None


def parse_action(text: str) -> dict | None:
    return first_json(text, ("tool", "final"))


# ---------------------------------------------------------------- compaction helpers (B1)
def prune_observation(text: str, keep: int = 40) -> str:
    """TRUNCATE: a long tool output becomes its header + the lines that carry signal."""
    lines = text.splitlines()
    if len(text) <= 600:
        return text
    signal = [l for l in lines[1:] if any(s in l for s in ("ERROR", "WARN", "code=", "config", " 5", "row(s)"))
              and "health check" not in l]
    kept = signal[:keep] or lines[1:keep // 2]
    return "\n".join([lines[0], *kept, f"... [{len(lines) - 1 - len(kept)} more lines dropped at compaction]"])


def render_for_summary(messages: list[dict]) -> str:
    out = []
    for m in messages:
        c = m["content"]
        if c.startswith("[OBSERVATION]"):
            c = "[OBSERVATION]\n" + prune_observation(c.removeprefix("[OBSERVATION]\n"))
        elif m["role"] == "assistant" and len(c) > 1500:
            c = c[:1500] + " ..."
        out.append(f"[{m['role'].upper()}] {c}")
    return "\n\n".join(out)


# ---------------------------------------------------------------- session
class Session:
    def __init__(self, show_context: bool, mode: str = "native", context_budget: int | None = None):
        self.id = datetime.now().strftime("s-%Y%m%d-%H%M%S-%f")
        self.messages: list[dict] = []  # starts EMPTY: no history from older sessions
        self.toolbox = Toolbox(self.id, mode)
        # Memory is retrieved once, at session start, and injected into the system prompt.
        self.memory_block = memory_store.context_block()
        self.system = SYSTEM_TEMPLATE.format(memory=self.memory_block, tools=self.toolbox.describe())
        SESSIONS_DIR.mkdir(exist_ok=True)
        self.log_path = SESSIONS_DIR / f"{self.id}.jsonl"
        # context accounting
        self.budget = context_budget
        self.last_input = 0             # input tokens of the latest call (= current context size)
        self.msgs_at_last_call = 0
        self.calls = self.input_total = self.compactions = 0
        self.checkpoint: dict = {}
        self.user_turns: list[str] = []  # verbatim user messages: constraints must never be summarised away
        self.turn_start = 0
        self.seen_calls: set[str] = set()
        print(f"=== new session {self.id} (mode={mode}, context budget="
              f"{f'{context_budget:,} tok, compact at {COMPACT_AT:.0%} between turns / {EMERGENCY_AT:.0%} mid-turn' if context_budget else 'off'}) ===")
        if show_context:
            print("--- memory injected into context ---")
            print(self.memory_block)
            print("------------------------------------")

    def log(self, event: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def observe(self, text: str) -> None:
        self.messages.append({"role": "user", "content": f"[OBSERVATION]\n{text}"})

    # -------------------------------------------------------- context size
    def estimated_context(self) -> int:
        """Last measured input tokens + a rough estimate for what was appended since."""
        added = sum(len(m["content"]) for m in self.messages[self.msgs_at_last_call:])
        if self.msgs_at_last_call == 0:  # nothing measured yet for this context: count the system prompt too
            added += len(self.system)
        return self.last_input + added // CHARS_PER_TOKEN

    def llm(self, system: str, messages: list[dict], purpose: str) -> str:
        raw, tokens = call_llm(system, messages)
        self.calls += 1
        self.input_total += tokens
        if purpose == "agent":
            self.last_input, self.msgs_at_last_call = tokens, len(messages) + 1
        self.log({"event": "usage", "purpose": purpose, "input_tokens": tokens})
        return raw

    # -------------------------------------------------------- compaction (B1)
    def maybe_compact(self, at_turn_start: bool) -> None:
        """WHEN: at a turn boundary (a milestone) once the context passes COMPACT_AT of the budget.
        Mid-turn only as an emergency (> EMERGENCY_AT), and then only the earlier turns: the
        evidence the current turn is still working with is never compacted."""
        if not self.budget:
            return
        est = self.estimated_context()
        if at_turn_start and est > COMPACT_AT * self.budget:
            keep_from = max((i for i, m in enumerate(self.messages) if m["role"] == "assistant"), default=0)
            self.compact(f"turn boundary, context ~{est:,} tok > {COMPACT_AT:.0%} of {self.budget:,}", keep_from)
        elif not at_turn_start and est > EMERGENCY_AT * self.budget:
            self.compact(f"emergency, context ~{est:,} tok > {EMERGENCY_AT:.0%} of {self.budget:,}", self.turn_start)

    def compact(self, reason: str, keep_from: int) -> None:
        """Controlled reboot of the working context:
        messages[:keep_from] -> (prune tool outputs) -> LLM structured checkpoint;
        new context = [checkpoint] + messages[keep_from:] kept verbatim."""
        old, tail = self.messages[:keep_from], self.messages[keep_from:]
        old_tokens = sum(len(m["content"]) for m in old) // CHARS_PER_TOKEN
        if old_tokens < MIN_COMPACTABLE:  # not worth an extra LLM call; avoids compacting on every step
            print(f"  [compact] skipped ({reason}): only ~{old_tokens:,} tok of older material")
            return
        before = self.estimated_context()
        print(f"  [compact] {reason} -> compacting {len(old)} old message(s) (~{old_tokens:,} tok), "
              f"keeping {len(tail)} recent verbatim")
        prompt = (f"PREVIOUS CHECKPOINT:\n{json.dumps(self.checkpoint, ensure_ascii=False, indent=1)}\n\n"
                  f"OLDER TRANSCRIPT TO COMPACT:\n{render_for_summary(old)}")
        new = None
        for _ in range(2):
            new = first_json(self.llm(COMPACT_SYSTEM, [{"role": "user", "content": prompt}], "compact"),
                             ("goal", "next_action"))
            if new:
                break
        if not new:  # never throw state away on a failed summary
            print("  [compact] checkpoint was not valid JSON -> keeping the full context")
            self.log({"event": "compact_failed", "reason": reason})
            return
        self.checkpoint = new
        self.compactions += 1
        users = "\n".join(f"  {i}. {t}" for i, t in enumerate(self.user_turns, 1))
        ckpt = ("[CHECKPOINT] The earlier part of this session was compacted. Raw tool outputs were removed.\n"
                "If you need exact values (ids, lines) that are not written below, re-run the tool;\n"
                "never reconstruct them from memory.\n"
                f"User messages so far (verbatim, the constraints in them still apply):\n{users}\n"
                f"Working state:\n{json.dumps(new, ensure_ascii=False, indent=1)}")
        if tail and tail[0]["role"] == "user":  # keep user/assistant alternation
            tail = [{"role": "user", "content": ckpt + "\n\n" + tail[0]["content"]}] + tail[1:]
        else:
            tail = [{"role": "user", "content": ckpt}] + tail
        self.messages = tail
        self.turn_start = max(0, self.turn_start - keep_from)
        self.msgs_at_last_call, self.last_input = 0, 0  # next estimate = whole new context
        after = self.estimated_context()
        ckpt_path = SESSIONS_DIR / f"{self.id}.checkpoint.json"
        ckpt_path.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log({"event": "compact", "reason": reason, "est_tokens_before": before,
                  "est_tokens_after": after, "checkpoint": new})
        print(f"  [compact] ~{before:,} -> ~{after:,} tok (estimated). Checkpoint saved to {ckpt_path.name}:")
        print("    " + json.dumps(new, ensure_ascii=False, indent=1).replace("\n", "\n    "))

    # -------------------------------------------------------- agent loop
    def ask(self, user_text: str) -> str:
        self.maybe_compact(at_turn_start=True)
        self.turn_start = len(self.messages)
        self.messages.append({"role": "user", "content": user_text})
        self.user_turns.append(user_text)
        self.log({"role": "user", "content": user_text})
        self.seen_calls = set()
        errors = 0
        t0, calls0, tokens0 = time.time(), self.calls, self.input_total

        def turn_stats() -> str:
            return (f"{self.calls - calls0} LLM call(s), {self.input_total - tokens0:,} input tok this turn, "
                    f"context now {self.last_input:,} tok")

        for step in range(1, MAX_STEPS + 1):
            if step > 1:
                self.maybe_compact(at_turn_start=False)
            # 1. THINK: the model sees system prompt + memory + whole session so far
            raw = self.llm(self.system, self.messages, "agent")
            self.messages.append({"role": "assistant", "content": raw})
            action = parse_action(raw)

            # Malformed reply: tell the model, do not silently accept it
            if action is None:
                errors += 1
                print(f"  [step {step}] invalid format -> asking model to retry")
                self.log({"step": step, "event": "format_error", "raw": raw})
                if errors >= MAX_CONSECUTIVE_ERRORS:
                    break
                self.observe("ERROR: reply was not a valid JSON action. Reply with exactly one JSON object.")
                continue

            if action.get("thought"):
                print(f"  [step {step}] ({self.last_input:,} tok in) thought: {action['thought']}")

            # 2. FINISH
            if "final" in action and "tool" not in action:
                self.log({"step": step, "event": "final", "content": action["final"],
                          "seconds": round(time.time() - t0, 1)})
                print(f"  [done in {step} step(s), {time.time() - t0:.0f}s; {turn_stats()}]")
                return action["final"]

            # 3. ACT
            name, args = action.get("tool", ""), action.get("args", {})
            signature = json.dumps([name, args], sort_keys=True, ensure_ascii=False)
            if signature in self.seen_calls:
                obs, is_error = ("ERROR: you already made this exact call in this turn and got its result. "
                                 "Use that result or try something different."), True
            else:
                self.seen_calls.add(signature)
                obs, is_error = self.toolbox.call(name, args)
            shown_args = json.dumps(args, ensure_ascii=False)
            print(f"  [step {step}] action: {name}({shown_args if len(shown_args) < 300 else shown_args[:300] + ' ...'})")
            preview = obs if len(obs) <= OBS_PREVIEW else obs[:OBS_PREVIEW] + f" ... [{len(obs):,} chars]"
            print("           observation: " + preview.replace("\n", "\n                        "))
            self.log({"step": step, "event": "tool", "name": name, "args": args,
                      "observation": obs, "error": is_error})

            # 4. OBSERVE: feed the result back and loop
            errors = errors + 1 if is_error else 0
            if errors >= MAX_CONSECUTIVE_ERRORS:
                break
            self.observe(obs)

        reason = "too many consecutive errors" if errors >= MAX_CONSECUTIVE_ERRORS else f"reached {MAX_STEPS} steps"
        self.log({"event": "stopped", "reason": reason})
        print(f"  [{turn_stats()}]")
        return f"(Agent stopped: {reason}. See {self.log_path} for the trace.)"

    def summary(self) -> str:
        return (f"=== session {self.id}: {self.calls} LLM call(s), {self.input_total:,} input tokens in total, "
                f"{self.compactions} compaction(s), final context {self.last_input:,} tok ===")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("message", nargs="*")
    p.add_argument("--show-context", action="store_true")
    p.add_argument("--dump-memory", action="store_true")
    p.add_argument("--mode", choices=["native", "code"], default="native",
                   help="native: model reads logs itself; code: model sends programs to run_code (B2)")
    p.add_argument("--context-budget", type=int, default=None,
                   help=f"enable compaction (turn boundary at {COMPACT_AT:.0%}, emergency at {EMERGENCY_AT:.0%} of this many input tokens) (B1)")
    a = p.parse_args()

    if a.dump_memory:
        print(memory_store.dump_all())
        return
    session = Session(a.show_context, a.mode, a.context_budget)
    if a.message:
        print("USER :", " ".join(a.message))
        print("AGENT:", session.ask(" ".join(a.message)))
        print(session.summary())
        return
    while True:  # interactive: history is kept WITHIN this session only
        try:
            text = input("you> ").strip()
        except EOFError:
            break
        if text in {"exit", "quit"}:
            break
        if text == "/compact":
            last_answer = max((i for i, m in enumerate(session.messages) if m["role"] == "assistant"), default=0)
            session.compact("requested by the user", last_answer)
        elif text:
            if not sys.stdin.isatty():
                print(f"\nUSER : {text}")
            print("agent>", session.ask(text))
    print(session.summary())


if __name__ == "__main__":
    main()
