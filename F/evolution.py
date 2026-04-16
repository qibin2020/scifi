#!/usr/bin/env python3
"""Global Evolution — three modes for system self-improvement.

Modes:
  suggest  — read-only analysis, writes .global_suggestion.md (default)
  code     — can modify driver.py (careful tuning)
  model    — can modify gateway.rank.yaml (rank ±1, budget, blacklist)

All modes read+write .global_memory.md and append .global_history.md.

Usage:
    python evolution.py suggest                # analyze, suggest only
    python evolution.py model                  # adjust ranks + budgets
    python evolution.py code                   # tune driver.py
    python evolution.py suggest task10 task11  # analyze specific tasks
"""

import sys, os, json, re, subprocess, time
from openai import OpenAI

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:4000")
EVOLVE_MODEL = os.environ["FALLBACK_HIGHEST"]
MAX_EVOLVE_ITER = int(os.environ.get("MAX_EVOLVE_ITER", "20"))
DRIVER_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.path.join(DRIVER_DIR, "run")
DRIVER_PATH = os.path.join(DRIVER_DIR, "driver.py")
RANK_PATH = os.path.join(DRIVER_DIR, "gateway.rank.yaml")

# --- Cam (write-only audit recording) ---

try:
    _cam_dir = os.environ.get("CAM_DIR", "")
    if _cam_dir:
        sys.path.insert(0, _cam_dir)
    from cam import cam_init as _cam_init, cam as _cam
except ImportError:
    def _cam_init(label): pass
    def _cam(event, **data): pass


# --- Prompts per mode ---

BASE_PROMPT = """\
You are the global evolution agent for a SAM driver system.
All modes: read+update .global_memory.md (cross-task knowledge, you are
the ONLY writer, workers read this at start). Append .global_history.md.

Use `history_stats` to get a summary of task history without loading
full text. Use `read_file` with offset/limit for details when needed.

Each task may have a `.suggestion.md` (written by the driver's final review).
It contains per-task suggestions for both the task design and the system.
Read these first — they are pre-analyzed feedback from the highest-rank model.
"""

SUGGEST_PROMPT = BASE_PROMPT + """
MODE: suggest (read-only analysis)
- Write .global_suggestion.md with issues requiring human intervention
- Update .global_memory.md with patterns and knowledge
- Do NOT modify driver.py or gateway.rank.yaml
- One line per suggestion, with evidence reference
Call `evolution` when done."""

CODE_PROMPT = BASE_PROMPT + """
MODE: code (driver tuning)
- You may modify driver.py via write_file — TUNE, don't rewrite
- Focus on system prompt wording, constants, small logic fixes
- Changes must be minimal and conservative (±5 lines per change)
- Test your understanding by reading driver.py first
- Document every change in .global_memory.md with reason
Call `evolution` when done."""

MODEL_PROMPT = BASE_PROMPT + """
MODE: model (rank + budget management)
- You may modify gateway.rank.yaml via write_file
- Adjust rank by ±1 only, based on evidence from history
- Set budget=0 to blacklist a broken model
- Restore budget when model is fixed
- Evidence: RANK_ESCALATION events, NUDGE_LIMIT, ERROR_LIMIT,
  consecutive failures, iteration counts, success rates
- Document every change in .global_memory.md with reason
Call `evolution` when done."""

# --- Tool definitions per mode ---

TOOLS_BASE = [
    {"type": "function", "function": {"name": "bash",
        "description": "Run a command to inspect state.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file",
        "description": "Read a file. Use offset/limit for large files.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "description": "Start char position"},
            "limit": {"type": "integer", "description": "Max chars"}},
            "required": ["path"]}}},
    {"type": "function", "function": {"name": "history_stats",
        "description": "Get summary stats from history without loading full text. "
            "Returns: task count, success/fail, model usage, rank changes, errors.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Path to .history.md or .global_history.md"}},
            "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_global_memory",
        "description": "Overwrite .global_memory.md.",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string"}}, "required": ["content"]}}},
    {"type": "function", "function": {"name": "evolution",
        "description": "Signal evolution is complete.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string"}}, "required": ["summary"]}}},
]

TOOL_WRITE_SUGGESTION = {"type": "function", "function": {"name": "write_suggestions",
    "description": "Write .global_suggestion.md for human review.",
    "parameters": {"type": "object", "properties": {
        "content": {"type": "string"}}, "required": ["content"]}}}

TOOL_WRITE_FILE = {"type": "function", "function": {"name": "write_file",
    "description": "Write a file (for driver.py or gateway.rank.yaml only).",
    "parameters": {"type": "object", "properties": {
        "path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"]}}}

MODE_CONFIG = {
    "suggest": {
        "prompt": SUGGEST_PROMPT,
        "extra_tools": [TOOL_WRITE_SUGGESTION],
        "writable": [],  # no file writes
    },
    "code": {
        "prompt": CODE_PROMPT,
        "extra_tools": [TOOL_WRITE_FILE],
        "writable": [DRIVER_PATH],
    },
    "model": {
        "prompt": MODEL_PROMPT,
        "extra_tools": [TOOL_WRITE_FILE],
        "writable": [RANK_PATH],
    },
}


# --- Helpers ---

def _global_history(entry_type, **kwargs):
    _cam(entry_type, **kwargs)
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    hf = os.path.join(RUN_DIR, ".global_history.md")
    lines = [f"**[{ts}] {entry_type}**"]
    for k, v in kwargs.items():
        val = str(v)[:500]
        lines.append(f"  - {k}: {val}")
    lines.append("")
    with open(hf, "a") as f:
        f.write("\n".join(lines) + "\n")


def _history_stats(path):
    """Summarize a history file without loading full text."""
    if not os.path.exists(path):
        return "(file not found)"
    with open(path) as f:
        text = f.read()

    lines = text.split('\n')
    total_lines = len(lines)
    file_size = len(text)

    # Count event types
    events = {}
    for line in lines:
        m = re.match(r'\s*\*\*\[.*?\]\s+(\w+)\*\*', line)
        if m:
            evt = m.group(1)
            events[evt] = events.get(evt, 0) + 1

    # Extract key data points
    models_used = set()
    ranks_seen = set()
    for line in lines:
        if '- model:' in line:
            models_used.add(line.split('- model:')[1].strip()[:30])
        if '- final_model:' in line:
            models_used.add(line.split('- final_model:')[1].strip()[:30])
        if '- rank:' in line or '- final_rank:' in line:
            rm = re.search(r'(?:final_)?rank:\s*(\d+)', line)
            if rm:
                ranks_seen.add(rm.group(1))

    stats = [
        f"File: {path}",
        f"Size: {file_size} chars, {total_lines} lines",
        f"Events: {json.dumps(events, indent=2)}",
        f"Models seen: {sorted(models_used)}",
        f"Ranks seen: {sorted(ranks_seen)}",
    ]

    # Success/fail for global history — count only inside TASK_END blocks
    # (INSIGHT events also have a `success:` field; don't double-count)
    if events.get("TASK_END"):
        successes = failures = 0
        in_task_end = False
        for line in lines:
            if re.match(r'\s*\*\*\[.*?\]\s+TASK_END\*\*', line):
                in_task_end = True
            elif re.match(r'\s*\*\*\[.*?\]\s+\w+\*\*', line):
                in_task_end = False
            elif in_task_end:
                if "success: True" in line:
                    successes += 1
                elif "success: False" in line:
                    failures += 1
        stats.append(f"Tasks: {successes} success, {failures} failed")

    return "\n".join(stats)


def _response_meta(result):
    """Extract audit metadata from an OpenAI SDK response."""
    meta = {}
    meta["response_id"] = getattr(result, "id", None)
    meta["response_model"] = getattr(result, "model", None)
    meta["system_fingerprint"] = getattr(result, "system_fingerprint", None)
    meta["created"] = getattr(result, "created", None)
    usage = getattr(result, "usage", None)
    if usage:
        meta["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
        meta["completion_tokens"] = getattr(usage, "completion_tokens", None)
        meta["total_tokens"] = getattr(usage, "total_tokens", None)
    choice = result.choices[0] if result.choices else None
    if choice:
        meta["finish_reason"] = getattr(choice, "finish_reason", None)
    return meta


def _api_call(client, messages, tools, retries=3):
    # Evolution always uses non-thinking mode (fast iteration)
    max_tok = 4096
    for attempt in range(retries):
        try:
            result = client.chat.completions.create(
                model=EVOLVE_MODEL, messages=messages,
                tools=tools, max_tokens=max_tok)
            msg = result.choices[0].message
            _cam("api_request", model=EVOLVE_MODEL, messages=messages,
                 tools=[t.get("function", {}).get("name") for t in (tools or [])],
                 response_content=getattr(msg, 'content', None),
                 response_tool_calls=[
                     {"name": tc.function.name, "args": tc.function.arguments}
                     for tc in (msg.tool_calls or [])] if msg.tool_calls else [],
                 **_response_meta(result))
            return result
        except Exception as e:
            err = str(e)
            if attempt < retries - 1 and any(s in err for s in
                    ["429", "500", "502", "503", "Connection", "Timeout", "timeout"]):
                time.sleep(2 ** attempt)
            else:
                raise


def _execute_tool(name, args, writable):
    """Tool dispatch. writable = list of paths allowed for write_file."""
    try:
        if name == "bash":
            r = subprocess.run(args["command"], shell=True, capture_output=True,
                text=True, timeout=60, cwd=DRIVER_DIR)
            out = (r.stdout + r.stderr).strip()
            if len(out) > 10000:
                return out[:10000] + f"\n[TRUNCATED: {len(out)} chars total]"
            return out or "(no output)"

        elif name == "read_file":
            path = args["path"]
            offset = int(args.get("offset", 0) or 0)
            limit = int(args.get("limit", 10000) or 10000)
            with open(path) as f:
                content = f.read()
            total = len(content)
            chunk = content[offset:offset + limit]
            if total > offset + limit:
                chunk += f"\n[Showing {offset}-{offset+len(chunk)} of {total} chars]"
            return chunk

        elif name == "history_stats":
            return _history_stats(args["path"])

        elif name == "write_global_memory":
            with open(os.path.join(RUN_DIR, ".global_memory.md"), "w") as f:
                f.write(args["content"])
            return "OK"

        elif name == "write_suggestions":
            with open(os.path.join(RUN_DIR, ".global_suggestion.md"), "w") as f:
                f.write(args["content"])
            return "OK"

        elif name == "write_file":
            path = os.path.realpath(args["path"])
            if path not in [os.path.realpath(w) for w in writable]:
                return f"ERROR: this mode cannot write to {path}. Allowed: {writable}"
            with open(path, "w") as f:
                f.write(args["content"])
            return "OK"

        else:
            return f"ERROR: unknown tool '{name}'"
    except Exception as e:
        return f"ERROR: {e}"


# --- Main ---

def evolve(mode, task_dirs):
    config = MODE_CONFIG[mode]
    tools = TOOLS_BASE + config["extra_tools"]
    writable = config["writable"]

    _global_history("EVOLVE_START",
        mode=mode,
        tasks=", ".join(os.path.basename(d) for d in task_dirs),
        model=EVOLVE_MODEL)
    print(f"[evolve:{mode}] analyzing {len(task_dirs)} task(s) "
          f"with {EVOLVE_MODEL}...", flush=True)

    # Build task listing
    task_info = []
    for td in task_dirs:
        files = [f for f in [".history.md", ".memory.md", ".suggestion.md", "top.md"]
                 if os.path.exists(os.path.join(td, f))]
        task_info.append(f"- `{td}/` — {', '.join(files)}")

    gm_path = os.path.join(RUN_DIR, ".global_memory.md")
    global_memory = ""
    if os.path.exists(gm_path):
        with open(gm_path) as f:
            global_memory = f.read()

    user_msg = (
        f"## Tasks\n" + "\n".join(task_info) + "\n\n"
        f"## Current Global Memory\n{global_memory[:2000] or '(empty)'}\n\n"
        f"## Key Files\n"
        f"- `{DRIVER_PATH}` — driver source\n"
        f"- `{RANK_PATH}` — model ranking config\n"
        f"- `{os.path.join(RUN_DIR, '.global_history.md')}` — system history\n\n"
        f"Start with `history_stats` on .global_history.md and task histories "
        f"to understand what happened. Then act per your mode. "
        f"Call `evolution` when done.")

    client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
    messages = [
        {"role": "system", "content": config["prompt"]},
        {"role": "user", "content": user_msg},
    ]

    for i in range(MAX_EVOLVE_ITER):
        try:
            response = _api_call(client, messages, tools)
        except Exception as e:
            _global_history("EVOLVE_API_ERROR", mode=mode, error=str(e))
            print(f"[evolve:{mode}] API error: {e}", flush=True)
            return

        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            messages.append({"role": "user", "content":
                "You must call evolution or use a tool."})
            continue

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                messages.append({"role": "tool", "tool_call_id": tc.id,
                    "content": "ERROR: malformed JSON."})
                continue

            if tc.function.name == "evolution":
                summary = args.get("summary", "")
                _global_history("EVOLVE_COMPLETE", mode=mode, summary=summary)
                print(f"[evolve:{mode}] {summary}", flush=True)
                return

            print(f"  [{tc.function.name}] {json.dumps(args)[:200]}", flush=True)
            result = _execute_tool(tc.function.name, args, writable)
            _cam("tool_call", tool=tc.function.name, args=args, result=str(result))
            messages.append({"role": "tool", "tool_call_id": tc.id,
                "content": str(result)})

    _global_history("EVOLVE_TIMEOUT", mode=mode)
    print(f"[evolve:{mode}] timed out", flush=True)


if __name__ == "__main__":
    # Parse mode and task dirs
    args = sys.argv[1:]
    mode = "suggest"
    task_args = []

    if args and args[0] in MODE_CONFIG:
        mode = args[0]
        task_args = args[1:]
    else:
        task_args = args

    _cam_init(f"evolution_{mode}")

    TASKS_DIR = os.path.join(DRIVER_DIR, "tasks")
    if task_args:
        task_dirs = [os.path.abspath(d) for d in task_args]
    else:
        task_dirs = sorted([
            os.path.join(TASKS_DIR, d) for d in os.listdir(TASKS_DIR)
            if os.path.isdir(os.path.join(TASKS_DIR, d))
            and os.path.exists(os.path.join(TASKS_DIR, d, "top.md"))
        ]) if os.path.isdir(TASKS_DIR) else []

    if not task_dirs:
        print("No task directories found.")
        sys.exit(1)

    print(f"Mode: {mode}")
    print(f"Tasks: {[os.path.basename(d) for d in task_dirs]}")
    evolve(mode, task_dirs)
