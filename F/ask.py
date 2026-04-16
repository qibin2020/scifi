#!/usr/bin/env python3
"""F Ask — interactive troubleshooter for the SAM driver system.

Read-only helper: diagnoses problems, suggests fixes, answers questions.
Never modifies files directly — tells you what to do.

Requires: Pam (gateway running) + Kam (container built).

Usage:
    python ask.py                   # default model
    python ask.py <model-name>      # override model
"""

import sys, os, json, time
from openai import OpenAI

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:4000")
DRIVER_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Cam (write-only audit recording) ---

try:
    _cam_dir = os.environ.get("CAM_DIR", "")
    if _cam_dir:
        sys.path.insert(0, _cam_dir)
    from cam import cam_init as _cam_init, cam as _cam
except ImportError:
    def _cam_init(label): pass
    def _cam(event, **data): pass


# --- Load context from F/*.md files ---

def _load_context():
    """Load all F/*.md files as system context."""
    parts = []
    for name in sorted(os.listdir(DRIVER_DIR)):
        if name.endswith('.md') and not name.startswith('.'):
            path = os.path.join(DRIVER_DIR, name)
            try:
                with open(path) as f:
                    content = f.read()
                parts.append(f"=== {name} ===\n{content}")
            except Exception:
                pass
    return "\n\n".join(parts)


def _load_rank_config():
    """Load gateway.rank.yaml if available."""
    for name in ["gateway.rank.yaml"]:
        path = os.path.join(DRIVER_DIR, name)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return f.read()
            except Exception:
                pass
    return ""


def _load_env_config():
    """Try to read ENV.sh for reference."""
    for candidate in [
        os.path.join(DRIVER_DIR, "ENV.sh"),             # container: /srv/ENV.sh
    ]:
        if os.path.exists(candidate):
            try:
                with open(candidate) as f:
                    return f.read()
            except Exception:
                pass
    return ""


# --- System prompt ---

SYSTEM = """\
You are the F-system troubleshooter — an interactive helper for the SAM driver \
and evolution system. You help users bootstrap, debug, and solve problems.

## Your role
- READ-ONLY: you never modify files. You tell the user exactly what to do.
- You are practical, clear, and minimal. No fluff.
- When you suggest a fix, give the exact command or exact text to write.
- If you need more information, ask the user to run a specific command and \
paste the output. Keep the command simple and short.
- If something is ambiguous, ask before guessing.

## Your beliefs
- Most problems are system/environment issues, not code bugs.
- You are inside a container and cannot see the full host system. \
Ask the user to check things outside the container when needed.
- Different systems (NERSC, local, cloud) behave very differently. \
Never assume — investigate first.
- Bootstrap problems (gateway not running, container not built, missing \
API keys, wrong paths) are the most common issues.

## What you can help with
- Bootstrap: setting up Kam (container), Pam (gateway), ENV.sh
- Gateway issues: API keys, model availability, connection errors
- Task problems: why a task failed, how to fix it, how to structure tasks
- Review/evolution: understanding review decisions, model ranking
- History: reading .history.md, .global_history.md, understanding events
- Skills: creating, testing, debugging skills
- Configuration: ENV.sh parameters, gateway.rank.yaml tuning
- Cam audit logs: reading JSONL recordings of past runs

## What you have access to (read-only, inside container)
- /srv/F.design.md, /srv/F.usage.md — system documentation
- /srv/driver.py, /srv/evolution.py — source code
- /srv/gateway.rank.yaml — model ranking config
- /srv/ENV.sh — environment configuration
- /srv/run/ — global memory and history (.global_memory.md, .global_history.md)
- /srv/tasks/ — past task run directories (with .history.md, .memory.md)
- /srv/skills/ — skill library
- /srv/task_defs/ — task definitions (Sam/tasks/)
- /cam/ — Cam audit JSONL logs (if CAM_DIR is configured; may not exist)

You CAN read any of these files yourself. For files outside the container \
(host system, network, SLURM), ask the user to run a command and paste output.

## What you cannot help with
- Problems outside the F-system (general Python, SLURM admin, network config)
- Modifying driver.py internals (suggest contacting the authors instead)
- Security or API key management (suggest the user handle this directly)

For problems you cannot solve or feel uncertain about, be conservative and say: \
"This looks like it needs the system authors — I'd suggest reaching out to them \
with [specific details to share]."

## How to diagnose
1. Ask what the user is trying to do and what went wrong
2. Check files you have access to first (history, Cam logs, config)
3. If you need host-side info, ask the user to run a simple command and paste output
4. Suggest the minimal fix — one step at a time
5. Confirm it worked before moving on

## Context loaded
You have the full F-system documentation, rank configuration, and ENV.sh \
preloaded below. Use them to answer accurately. You can also read task \
histories, Cam audit logs, and source code at the paths listed above.
"""


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


def check_gateway(client, model):
    """Quick health check — can we reach the LLM?"""
    try:
        resp = client.chat.completions.create(
            model=model, max_tokens=10,
            messages=[{"role": "user", "content": "Say OK."}])
        return True
    except Exception as e:
        return str(e)


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else os.environ["FALLBACK_HIGHEST"]

    _cam_init("ask")

    # Load context
    docs = _load_context()
    rank_config = _load_rank_config()
    env_config = _load_env_config()

    context_parts = []
    if docs:
        context_parts.append(f"## Documentation\n{docs}")
    if rank_config:
        context_parts.append(f"## gateway.rank.yaml\n```yaml\n{rank_config}\n```")
    if env_config:
        context_parts.append(f"## ENV.sh\n```bash\n{env_config}\n```")

    system_msg = SYSTEM + "\n\n" + "\n\n".join(context_parts)

    # Check gateway connectivity
    print(f"[ask] connecting to gateway at {GATEWAY}...")
    print(f"[ask] model: {model}")
    client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
    result = check_gateway(client, model)
    _cam("gateway_check", model=model, success=(result is True),
         error=result if result is not True else None)
    if result is not True:
        print(f"\n[ask] ERROR: cannot reach the LLM gateway.")
        print(f"  Detail: {result}")
        print()
        print("  Checklist:")
        print("  1. Is the gateway running?  →  bash Pam/gateway.sh  (in another terminal)")
        print("  2. Is ENV.sh sourced?       →  source ENV.sh")
        print(f"  3. Is the URL correct?      →  curl {GATEWAY}/health")
        print(f"  4. Is '{model}' configured? →  check Pam/gateway.model.yaml")
        print()
        print("  Start the gateway first, then run ask again.")
        sys.exit(1)

    print("[ask] connected. Type your question. Ctrl+D or 'exit' to quit.\n")

    messages = [{"role": "system", "content": system_msg}]

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[ask] bye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print("[ask] bye.")
            break

        messages.append({"role": "user", "content": user_input})
        _cam("user_input", content=user_input)

        try:
            resp = client.chat.completions.create(
                model=model, max_tokens=4096, messages=messages)
            reply = resp.choices[0].message.content.strip()
            _cam("api_request", model=model, messages=messages, response=reply,
                 **_response_meta(resp))
        except Exception as e:
            print(f"\n[ask] API error: {e}\n")
            _cam("api_error", error=str(e))
            messages.pop()  # remove failed user message so conversation stays clean
            continue

        messages.append({"role": "assistant", "content": reply})
        print(f"\n{reply}\n")

        # Trim conversation if too long (keep system + last 40 exchanges)
        if len(messages) > 82:
            messages = [messages[0]] + messages[-80:]


if __name__ == "__main__":
    main()
