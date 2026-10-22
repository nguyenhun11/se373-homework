"""Analytics agent with an agent loop and persistent project memory.

Each run of this script is a NEW session: no chat history is carried over.
The only thing that survives between sessions is memory/memory.json.

Agent loop (per user message):
    context = system prompt (tools + injected memory) + session messages
    repeat up to MAX_STEPS:
        LLM -> {"thought", "tool", "args"}  -> run tool -> append observation
            or {"thought", "final"}         -> return answer
    stop early on: final answer | MAX_STEPS | MAX_CONSECUTIVE_ERRORS

Usage:
    python agent.py "message"            # one-shot session
    python agent.py                      # interactive session (REPL)
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

SESSIONS_DIR = Path(__file__).parent / "sessions"
MAX_STEPS = 10               # hard cap on LLM calls per user message
MAX_CONSECUTIVE_ERRORS = 3   # stop if the agent cannot recover from errors
OBS_PREVIEW = 400            # chars of each observation printed in the trace

SYSTEM_TEMPLATE = """You are an analytics agent for the SE373 project "Chợ Sen" (Vietnamese e-commerce).
You answer business questions by exploring the SQLite database and running SQL,
then explain the result with the actual numbers. Answer in the user's language.

PROJECT MEMORY — conventions agreed in previous sessions. They are binding:
apply them to every query and answer unless the user changes them in this session.
{memory}

TOOLS
{tools}

HOW TO WORK
- Data questions: inspect the schema first (list_tables / describe_table) unless you
  already know it in this session, then run_sql. Never invent numbers: every number
  in the final answer must come from a run_sql observation.
- If a tool returns an ERROR, read it, fix the call and try again.
- When the user states a NEW durable convention or CHANGES one, call remember.
  If it replaces a convention listed above, REUSE THAT EXACT KEY.
  Do not store one-off questions, query results or chit-chat.
- In the final answer, show the SQL you ran and say which conventions you applied.

RESPONSE FORMAT — reply with exactly one JSON object and nothing else:
  {{"thought": "<short reasoning>", "tool": "<tool name>", "args": {{...}}}}   to call ONE tool, or
  {{"thought": "<short reasoning>", "final": "<answer to the user>"}}          to finish."""


# ---------------------------------------------------------------- backends
def _http_json(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def call_llm(system: str, messages: list[dict]) -> str:
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
        return "".join(b.get("text", "") for b in data["content"])
    if backend == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        data = _http_json(
            f"{base}/chat/completions",
            {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "content-type": "application/json"},
            {"model": os.environ.get("AGENT_MODEL", "gpt-4o-mini"),
             "messages": [{"role": "system", "content": system}, *messages]},
        )
        return data["choices"][0]["message"]["content"]
    if backend == "claude-cli":
        # Stateless call: no tools, no settings/CLAUDE.md, no MCP, no saved session,
        # run from /tmp so nothing but OUR context reaches the model.
        transcript = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in messages)
        out = subprocess.run(
            ["claude", "-p", "--system-prompt", system, "--tools", "", "--setting-sources", "",
             "--strict-mcp-config", "--no-session-persistence",
             "--model", os.environ.get("AGENT_MODEL", "haiku"),
             transcript + "\n\n[ASSISTANT] (reply with one JSON object)"],
            capture_output=True, text=True, cwd="/tmp", timeout=180,
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr or out.stdout)
        return out.stdout
    sys.exit("No LLM backend: set ANTHROPIC_API_KEY or OPENAI_API_KEY, or install the claude CLI.")


def parse_action(text: str) -> dict | None:
    """Return the first JSON object in the reply, or None if there is none."""
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj, dict) and ("tool" in obj or "final" in obj):
                return obj
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    return None


# ---------------------------------------------------------------- session
class Session:
    def __init__(self, show_context: bool):
        self.id = datetime.now().strftime("s-%Y%m%d-%H%M%S-%f")
        self.messages: list[dict] = []  # starts EMPTY: no history from older sessions
        self.toolbox = Toolbox(self.id)
        # Memory is retrieved once, at session start, and injected into the system prompt.
        self.memory_block = memory_store.context_block()
        self.system = SYSTEM_TEMPLATE.format(memory=self.memory_block, tools=self.toolbox.describe())
        SESSIONS_DIR.mkdir(exist_ok=True)
        self.log_path = SESSIONS_DIR / f"{self.id}.jsonl"
        print(f"=== new session {self.id} ===")
        if show_context:
            print("--- memory injected into context ---")
            print(self.memory_block)
            print("------------------------------------")

    def log(self, event: dict) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def observe(self, text: str) -> None:
        self.messages.append({"role": "user", "content": f"[OBSERVATION]\n{text}"})

    def ask(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        self.log({"role": "user", "content": user_text})
        seen_calls: set[str] = set()
        errors = 0
        t0 = time.time()

        for step in range(1, MAX_STEPS + 1):
            # 1. THINK: the model sees system prompt + memory + whole session so far
            raw = call_llm(self.system, self.messages)
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
                print(f"  [step {step}] thought: {action['thought']}")

            # 2. FINISH
            if "final" in action and "tool" not in action:
                self.log({"step": step, "event": "final", "content": action["final"],
                          "seconds": round(time.time() - t0, 1)})
                print(f"  [done in {step} step(s), {time.time() - t0:.0f}s]")
                return action["final"]

            # 3. ACT
            name, args = action.get("tool", ""), action.get("args", {})
            signature = json.dumps([name, args], sort_keys=True, ensure_ascii=False)
            if signature in seen_calls:
                obs, is_error = ("ERROR: you already made this exact call in this turn and got its result. "
                                 "Use that result or try something different."), True
            else:
                seen_calls.add(signature)
                obs, is_error = self.toolbox.call(name, args)
            print(f"  [step {step}] action: {name}({json.dumps(args, ensure_ascii=False)})")
            preview = obs if len(obs) <= OBS_PREVIEW else obs[:OBS_PREVIEW] + " ..."
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
        return f"(Agent stopped: {reason}. See {self.log_path} for the trace.)"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("message", nargs="*")
    p.add_argument("--show-context", action="store_true")
    p.add_argument("--dump-memory", action="store_true")
    a = p.parse_args()

    if a.dump_memory:
        print(memory_store.dump_all())
        return
    session = Session(a.show_context)
    if a.message:
        print("USER :", " ".join(a.message))
        print("AGENT:", session.ask(" ".join(a.message)))
        return
    while True:  # interactive: history is kept WITHIN this session only
        try:
            text = input("you> ").strip()
        except EOFError:
            break
        if text in {"exit", "quit"}:
            break
        if text:
            print("agent>", session.ask(text))


if __name__ == "__main__":
    main()
