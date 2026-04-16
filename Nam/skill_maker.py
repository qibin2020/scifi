#!/usr/bin/env python3
"""Skill Maker — interactive builder for SAM driver skills.

Reads a plain description, iteratively builds a standard skill folder
with tool calling (bash, write_file, read_file) to create, test, and
verify the skill. Asks the user for clarification when needed.

Usage:
    python skill_maker.py description.md [skill_name]
    python skill_maker.py  # start from scratch interactively
"""

import sys, os, json, re, time
from openai import OpenAI

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

SKILLS_DIR = os.environ.get("SKILLS_DIR", os.path.join(DRIVER_DIR, "skills"))
# driver.py is bind-mounted to /srv/lib/ inside container
_lib = os.path.join(os.path.dirname(DRIVER_DIR), "lib")
if os.path.isdir(_lib):
    sys.path.insert(0, _lib)
else:
    sys.path.insert(0, DRIVER_DIR)

from pam import Pam

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:4000")
_rank_yaml = os.path.join(_lib or DRIVER_DIR, "gateway.rank.yaml")
pam = Pam(rank_yaml_path=_rank_yaml, gateway_url=GATEWAY)

SYSTEM = """\
You are a skill builder for the always_young system. You help users create
reusable "skills" that agents can use when running tasks.

## What is a skill?

A skill is a reusable capability that gets loaded into an agent at runtime.
Think of it like a plugin. There are two types:

### Tool Skill — adds a callable function
When the agent needs to DO something specific (compute stats, call an API,
validate data), you build a tool skill. It becomes a function the agent can call.

Files created:
```
skill_name/
├── skill.yaml    # name, description, parameter schema
├── run.py        # def execute(args, task_dir) → string result
└── README.md     # usage docs
```

### Context Skill — injects knowledge/instructions
When the agent needs to KNOW something (a workflow, domain rules, templates),
you build a context skill. It gets injected into the agent's context.

Files created:
```
skill_name/
├── SKILL.md      # ---name/description--- frontmatter + full instructions
├── templates/    # reference files (optional)
└── README.md     # usage docs
```

## Your approach — ask first, build second

You MUST understand what the user needs before building anything.
Most users are NOT programmers and do NOT know the skill format.
Your job is to figure out what they need through conversation.

Step 1: Ask clarifying questions using the `ask_user` tool. Consider:
  - What exactly should this skill do? Get a concrete example.
  - What are the inputs? What are the outputs?
  - Is this a function call (tool) or knowledge/workflow (context)?
  - Are there edge cases or error conditions?
  - What environment/dependencies does it need?

Step 2: Summarize your plan back to the user using `ask_user`:
  "Here's what I'll build: [type] skill that [does X]. It takes [inputs]
   and returns [outputs]. Does that sound right?"

Step 3: Build it — create files, test tool skills with bash.

Step 4: Show the user what was created using `ask_user`:
  "I've created [files]. Here's how to use it in a task: add
   `Skills: skill_name` to your task's top.md. The agent will then
   be able to [do X]. Want me to change anything?"

Step 5: When the user approves, call `done` with a clear usage summary.

## Tools Available
- ask_user: Ask the user a question (returns their answer). USE THIS LIBERALLY.
- bash: Run commands (test the skill, check files)
- read_file: Read files
- write_file: Create/edit files
- done: Signal completion (include a usage summary that tells the user
  exactly what to do next)

## Technical rules
- skill.yaml: parameters must have type and description
- run.py: must have `def execute(args, task_dir)` returning a string
- SKILL.md: must have ---name/description--- frontmatter
- Always test tool skills with bash before finishing
- README.md: what it does, which type, how to use in a task
- One clear purpose per skill — don't overload"""

TOOLS = [
    {"type": "function", "function": {"name": "bash",
        "description": "Run a command. Use to test the skill.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file",
        "description": "Read a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file",
        "description": "Write a file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "ask_user",
        "description": "Ask the user a question. Returns their answer.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"}}, "required": ["question"]}}},
    {"type": "function", "function": {"name": "done",
        "description": "Skill is complete. Provide usage summary.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "How to use this skill in a task"}},
            "required": ["summary"]}}},
]


def execute_tool(name, args, skill_dir):
    """Execute tools for skill building."""
    try:
        if name == "bash":
            import subprocess
            r = subprocess.run(args["command"], shell=True, capture_output=True,
                text=True, timeout=60, cwd=skill_dir)
            out = (r.stdout + r.stderr).strip()
            return out[:5000] if out else "(no output)"
        elif name == "read_file":
            path = args["path"]
            if not os.path.isabs(path):
                path = os.path.join(skill_dir, path)
            with open(path) as f:
                return f.read()[:5000]
        elif name == "write_file":
            path = args["path"]
            if not os.path.isabs(path):
                path = os.path.join(skill_dir, path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(args["content"])
            return "OK"
        elif name == "ask_user":
            print(f"\n  [agent asks] {args['question']}\n")
            answer = input("  [you] > ").strip()
            return answer or "(no answer)"
        else:
            return f"ERROR: unknown tool '{name}'"
    except Exception as e:
        return f"ERROR: {e}"


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


def make_skill(description, skill_dir):
    model = pam.highest()
    skill_name = os.path.basename(skill_dir)

    # Read template for reference
    tpl_readme = os.path.join(SKILLS_DIR, "skill_template", "README.md")
    template = ""
    if os.path.exists(tpl_readme):
        with open(tpl_readme) as f:
            template = f.read()

    client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content":
            f"Build a skill named `{skill_name}` in directory `{skill_dir}/`.\n\n"
            f"## Description\n{description}\n\n"
            f"## Skill Template Reference\n{template[:2000]}\n\n"
            f"Start by asking clarifying questions to understand exactly "
            f"what the user needs. Do NOT build anything until you have "
            f"confirmed your plan with the user."},
    ]

    print(f"[skill_maker] using {model}")
    print(f"[skill_maker] building in {skill_dir}/")
    print("=" * 60)

    os.makedirs(skill_dir, exist_ok=True)

    for iteration in range(20):
        try:
            resp = client.chat.completions.create(
                model=model, max_tokens=4096, messages=messages, tools=TOOLS)
        except Exception as e:
            print(f"[error] API: {e}")
            break

        msg = resp.choices[0].message
        _cam("api_request", model=model, messages=messages,
             response_content=getattr(msg, 'content', None),
             response_tool_calls=[
                 {"name": tc.function.name, "args": tc.function.arguments}
                 for tc in (msg.tool_calls or [])] if msg.tool_calls else [],
             **_response_meta(resp))
        messages.append(msg)

        # Text-only response
        if not msg.tool_calls:
            print(f"\n[agent] {msg.content}\n")
            answer = input("[you] > ").strip()
            _cam("user_input", answer=answer)
            messages.append({"role": "user", "content": answer or "Continue."})
            continue

        # Process tool calls
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                messages.append({"role": "tool", "tool_call_id": tc.id,
                    "content": "ERROR: bad JSON"})
                continue

            if tc.function.name == "done":
                summary = args.get("summary", "")
                print(f"\n{'=' * 60}")
                print(f"  SKILL COMPLETE: {skill_name}")
                print(f"{'=' * 60}")
                # List created files
                for root, dirs, files in os.walk(skill_dir):
                    for f in sorted(files):
                        rel = os.path.relpath(os.path.join(root, f), skill_dir)
                        print(f"  - {rel}")
                print(f"\n{summary}")
                print(f"\n  --- What to do next ---")
                print(f"  1. Add 'Skills: {skill_name}' to your task's top.md")
                print(f"  2. Run: SciF RUN <task_name>")
                print(f"     The agent will automatically have access to this skill.")
                print(f"{'=' * 60}")
                return

            print(f"  [{tc.function.name}] {json.dumps(args)[:200]}", flush=True)
            result = execute_tool(tc.function.name, args, skill_dir)
            _cam("tool_call", tool=tc.function.name, args=args, result=str(result))
            messages.append({"role": "tool", "tool_call_id": tc.id,
                "content": str(result)})

    print("[skill_maker] max iterations reached")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        desc_path = os.path.abspath(sys.argv[1])
        with open(desc_path) as f:
            description = f.read()
        if len(sys.argv) >= 3:
            skill_name = sys.argv[2]
        else:
            skill_name = os.path.splitext(os.path.basename(desc_path))[0]
    else:
        print("Describe your skill (end with empty line):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        description = "\n".join(lines)
        skill_name = input("Skill name: ").strip() or "new_skill"

    skill_dir = os.path.join(SKILLS_DIR, skill_name)
    if not description.strip():
        print("No description provided.")
        sys.exit(1)

    _cam_init(f"skill_maker_{skill_name}")
    make_skill(description, skill_dir)
