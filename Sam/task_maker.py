#!/usr/bin/env python3
"""Task Maker — interactive conversion of descriptions into SAM task folders.

Reads a plain .md file, uses highest-end model to analyze and ask clarifying
questions until the task structure is clear, then writes the task folder.

Usage:
    python task_maker.py description.md [output_dir]
    python task_maker.py                # start from scratch interactively
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
# driver.py is bind-mounted to /srv/lib/ inside container
_lib = os.path.join(os.path.dirname(DRIVER_DIR), "lib")
if os.path.isdir(_lib):
    sys.path.insert(0, _lib)
else:
    sys.path.insert(0, DRIVER_DIR)

from pam import Pam
from driver import GATEWAY, _skill_catalog, _skills

_rank_yaml = os.path.join(_lib or DRIVER_DIR, "gateway.rank.yaml")
pam = Pam(rank_yaml_path=_rank_yaml, gateway_url=GATEWAY)

SYSTEM = """\
You are a task architect for a SAM (Self-Assessed Module) driver system.
Your job: have a thorough conversation with the user to understand what they
want, then convert it into a structured task folder.

## SAM Format
Each .md file uses frontmatter + three sections:

```
---
Rank: 2
BashTime: -1
Skills: common_env
---

# Task Title

## Context
background, constraints, domain knowledge

## Todo
1. numbered steps the agent will execute

## Expect
- verifiable success criteria (review agent checks these)
```

## Metadata (inside --- fences, all optional)
- Rank: N (0=trivial to {max_rank}=complex)
- Timeout: N (wall time seconds, excludes subtask/bash time)
- BashTime: N (per-bash-call limit, -1=no limit for long jobs)
- Skills: a, b (from available skills list)
- GPU: no | local | slurm | on (default: no)
    no    = task does not need a GPU
    local = task needs a GPU; only run when host has nvidia-smi
    slurm = task needs a GPU; ALWAYS submit to a SLURM GPU node (overrides Slurm: off default)
    on    = task wants a GPU; auto — local GPU if present, else SLURM
- Slurm: off | on (default: off)
    off = run locally only (default)
    on  = SLURM submission allowed; dense workloads (BashTime: -1) auto-route to SLURM
    Note: GPU: slurm together with explicit Slurm: off is an ERROR (contradiction).
- SlurmHours: N (wall hours when submitted via SLURM, default 4)
- SlurmCpus: N (CPUs per task in SLURM, default 32)

## Subtasks
- Reference as `name.md` in Todo
- Category naming: `data.load.md`, `data.clean.md` → shared category
- Each subtask is its own SAM with Context/Todo/Expect

## Rules
- Expect must be concrete (files exist, content matches, specific values)
- Only decompose when subtasks have clear boundaries
- Rank = difficulty of hardest step
- BashTime: -1 for SLURM/training/long processes
- If the task trains a model, runs CUDA, or otherwise needs a GPU, set GPU
  appropriately. If user did not specify, ASK whether to use a local GPU,
  always submit to SLURM, or auto.
- Keep minimal — don't over-decompose

## Interaction Protocol

You MUST ask questions before generating. Do NOT generate on the first round
unless the description is completely unambiguous with zero missing details.

Think about what the driver agent will actually need to execute this task:
- What environment/dependencies are needed?
- What are the concrete success criteria? (vague = bad)
- Are there implicit assumptions that should be explicit?
- Does the task need decomposition into subtasks?
- What could go wrong that the Expect section should guard against?

Ask questions in batches. Be specific — don't ask "anything else?" but rather
"should the output be CSV or JSON?" or "GPU local, GPU on SLURM, or no GPU?".

When you have enough clarity, summarize your understanding back to the user
BEFORE generating, so they can correct any misunderstanding.

Reply with a JSON object:
- Questions: {{"action": "ask", "questions": ["q1", "q2", ...], "thinking": "what I understand so far and what I still need"}}
- Summary before generating: {{"action": "confirm", "summary": "Here is my understanding: ..."}}
- Generate (only after user confirms summary): {{"action": "generate", "files": {{"top.md": "...", ...}}, "reasoning": "..."}}

The goal is a task definition so clear that ANY agent can execute it without
needing to ask the user anything. Ambiguity in the task = failure downstream."""


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


def _build_skill_docs():
    """Build full skill documentation from loaded skills."""
    parts = []
    for name, info in _skills.items():
        desc = info.get("description", "")
        stype = info.get("type", "unknown")
        parts.append(f"### {name} [{stype}]\n{desc}")
        if stype == "context" and info.get("content"):
            # Include full SKILL.md content (skip frontmatter)
            content = info["content"]
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    content = content[end + 3:].strip()
            parts.append(content[:2000])
        parts.append("")
    return "\n".join(parts) if parts else "(none loaded)"


def _load_env_context():
    """Load execution environment summary from F.usage.md."""
    # Walk up from Sam/ to find F/F.usage.md
    basedir = os.path.dirname(DRIVER_DIR)
    usage_path = os.path.join(basedir, "F", "F.usage.md")
    if not os.path.exists(usage_path):
        return ""
    with open(usage_path) as f:
        content = f.read()
    # Extract key sections: How it works + Bootstrap prereqs
    return (
        "## Execution Environment\n"
        "Tasks run inside Apptainer containers with a read-only overlay.\n"
        "The agent has: bash, git, curl, wget, micromamba (system), "
        "and a pre-installed Python 3.12 driver env (read-only).\n"
        "To install new Python packages, the agent must create a new "
        "micromamba environment in its writable task directory.\n"
        "Skills like `local_env` provide recipes for common patterns.\n"
        "SLURM job submission is available via sbatch/squeue/scancel.\n"
        "\n"
        "GPU + SLURM are controlled by task metadata, NOT by the agent:\n"
        "- GPU: no|local|slurm|on (default no). 'slurm' or 'on' lets the\n"
        "  driver auto-submit the task to a NERSC GPU node before the\n"
        "  agent ever runs — agent code does NOT need to call sbatch.\n"
        "- Slurm: off|on (default off). 'on' allows the driver to route\n"
        "  dense workloads (BashTime: -1) to a CPU SLURM allocation.\n"
        "Only set GPU/Slurm metadata when the task genuinely needs them.\n"
    )


def make_task_interactive(description, output_dir):
    model = pam.highest()
    mr = pam.max_rank()
    skill_docs = _build_skill_docs()
    env_context = _load_env_context()

    # Read template
    tpl_path = os.path.join(DRIVER_DIR, "task_template", "top.md")
    template = ""
    if os.path.exists(tpl_path):
        with open(tpl_path) as f:
            template = f.read()

    client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
    messages = [
        {"role": "system", "content": SYSTEM.format(max_rank=mr)},
        {"role": "user", "content":
            f"## Description\n{description}\n\n"
            f"{env_context}\n"
            f"## Available Skills (with full docs)\n{skill_docs}\n\n"
            f"## Rank Range\n0 to {mr}\n\n"
            f"## Template Reference\n{template[:1500]}\n\n"
            f"Analyze this description carefully. Ask clarifying questions "
            f"before generating anything. Reply with JSON."},
    ]

    print(f"[task_maker] using {model}", flush=True)
    print("=" * 60)

    for iteration in range(20):  # max 20 rounds (ask + confirm + generate + revise)
        resp = client.chat.completions.create(
            model=model, max_tokens=4096, messages=messages)
        raw = resp.choices[0].message.content.strip()
        _cam("api_request", model=model, messages=messages, response=raw,
             **_response_meta(resp))

        # Parse JSON from response
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            print(f"\n[agent]\n{raw}\n")
            answer = input("[you] > ").strip()
            if not answer:
                answer = "Please proceed with your best judgment."
            _cam("user_input", answer=answer)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": answer})
            continue

        try:
            result = json.loads(json_match.group())
        except json.JSONDecodeError:
            print(f"\n[agent] (malformed response, retrying)\n")
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content":
                "Your JSON was malformed. Try again."})
            continue

        action = result.get("action", "")

        if action == "ask":
            questions = result.get("questions", [])
            thinking = result.get("thinking", "")
            if thinking:
                print(f"\n  [thinking] {thinking}\n")
            print()
            for i, q in enumerate(questions, 1):
                print(f"  Q{i}: {q}")
            print()
            print("  (Answer all, or type 'skip' to let the agent decide)")
            answer = input("[you] > ").strip()
            if not answer or answer.lower() == "skip":
                answer = "Use your best judgment for all questions."
            _cam("user_input", questions=questions, answer=answer)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": answer})

        elif action == "confirm":
            summary = result.get("summary", "")
            print(f"\n{'=' * 60}")
            print(f"  SUMMARY — agent's understanding:")
            print(f"{'=' * 60}")
            print(f"\n{summary}\n")
            print(f"{'=' * 60}")
            confirm = input("[you] Correct? (y/n/feedback) > ").strip()
            _cam("user_confirm_summary", summary=summary, confirm=confirm)
            messages.append({"role": "assistant", "content": raw})
            if confirm.lower() in ('y', 'yes', ''):
                messages.append({"role": "user", "content":
                    "Correct. Now generate the task files."})
            else:
                messages.append({"role": "user", "content":
                    f"Not quite. Corrections: {confirm}"})

        elif action == "generate":
            files = result.get("files", {})
            reasoning = result.get("reasoning", "")

            if not files:
                print("[task_maker] ERROR: no files in response")
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                    "No files were generated. Please try again."})
                continue

            # Show preview
            print(f"\n{'=' * 60}")
            print(f"  Generated {len(files)} file(s):")
            for fname in files:
                print(f"    - {fname}")
            if reasoning:
                print(f"\n  Reasoning: {reasoning}")
            print(f"{'=' * 60}\n")

            # Show file contents (full, so user can review properly)
            for fname, content in files.items():
                print(f"--- {fname} ---")
                print(content)
                print()

            # Confirm or refine
            confirm = input("[you] Accept? (y/n/feedback) > ").strip()
            _cam("user_confirm", confirm=confirm, files=list(files.keys()))
            if confirm.lower() in ('y', 'yes', ''):
                # Write files
                os.makedirs(output_dir, exist_ok=True)
                for fname, content in files.items():
                    with open(os.path.join(output_dir, fname), "w") as f:
                        f.write(content)
                    print(f"  wrote {fname}")

                # Summary
                task_name = os.path.basename(output_dir)
                top = files.get("top.md", "")
                rank_m = re.search(r'Rank:\s*(\d+)', top)
                skills_m = re.search(r'Skills:\s*(.+)', top)
                subtasks = [f for f in files if f != "top.md"]
                print(f"\n{'=' * 60}")
                print(f"  TASK READY: {task_name}")
                print(f"{'=' * 60}")
                print(f"  Rank: {rank_m.group(1) if rank_m else 'auto'}")
                if skills_m:
                    print(f"  Skills: {skills_m.group(1)}")
                if subtasks:
                    print(f"  Subtasks: {', '.join(subtasks)}")
                print(f"  Files: {len(files)}")
                print(f"\n  Run:  SciF RUN {task_name}")
                print(f"{'=' * 60}")
                return
            else:
                # Refine
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                    f"User feedback: {confirm}\nPlease revise."})
        else:
            # Unknown action — treat as text, ask user
            print(f"\n[agent]\n{raw}\n")
            answer = input("[you] > ").strip()
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": answer or "Continue."})

    print("[task_maker] max iterations reached")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        desc_path = os.path.abspath(sys.argv[1])
        with open(desc_path) as f:
            description = f.read()
        if len(sys.argv) >= 3:
            out_dir = sys.argv[2]
        else:
            base = os.path.splitext(os.path.basename(desc_path))[0]
            out_dir = os.path.join(DRIVER_DIR, f"task_{base}")
    else:
        # Start from scratch
        print("Describe your task (end with empty line):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        description = "\n".join(lines)
        if len(sys.argv) >= 2:
            out_dir = sys.argv[1]
        else:
            out_dir = os.path.join(DRIVER_DIR, "task_new")

    if not description.strip():
        print("No description provided.")
        sys.exit(1)

    _cam_init(f"task_maker_{os.path.basename(out_dir)}")
    make_task_interactive(description, out_dir)
