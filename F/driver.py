#!/usr/bin/env python3
"""SAM Driver — Self-Assessed Module agentic loop with concurrent scheduling.

Every .md file is a SAM: a closed loop with Context, Todo, Expect.
Each SAM is sandwiched: PRESCAN → AGENT LOOP → REVIEW.

RALPH loop principle: with sufficient variation and iteration, any
achievable expectation MUST be met. Convergence is structural.

Hard beliefs:
1. Every SAM WILL converge — never quit without a verdict.
2. Every `done` MUST be reviewed — independent agent checks expectations.
3. Review is orthogonal — different model, fresh context.
4. Progress must be re-grounded — re-inject task + memory periodically.
5. Errors are information — catch, report, continue.
6. Prescan plans, review gates — both use highest model.
7. Model assignment is deterministic — parent decides, child receives.
8. Fast iteration wins — prefer the fastest model that can solve the task.
   Thinking models are slow; use them only when fast models fail on reasoning.

File structure:
  cwd/
  ├── driver.py              # this file
  ├── gateway.rank.yaml      # model ranking + budget
  ├── skills/                # skill library
  ├── taskXXX/               # task folder (argv[1])
  │   ├── top.md             # SAM definition
  │   ├── .memory.md         # task memory
  │   ├── .history.md        # task history (append-only)
  │   └── .history_index.md  # auto-generated outline
  └── run/                   # global state
      ├── .global_memory.md  # cross-task knowledge
      └── .global_history.md # system tape (append-only)
"""

import sys, os, json, re, subprocess, time, threading, urllib.request
from openai import OpenAI
from task_parser import parse_task, public_meta, TaskFormatError

# ============================================================
# CONFIG
# ============================================================

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:4000")
FALLBACK_HIGHEST = os.environ["FALLBACK_HIGHEST"]
FALLBACK_WORKING = os.environ["FALLBACK_WORKING"]
MAX_ITER = int(os.environ.get("MAX_ITERATIONS", "50"))  # absolute cap (overridden per-rank)
MAX_REVIEW_ITER = int(os.environ.get("MAX_REVIEW_ITER", "100"))
MAX_REFLECT_ITER = int(os.environ.get("MAX_REFLECT_ITER", "15"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
CHECKPOINT_EVERY = int(os.environ.get("CHECKPOINT_EVERY", "5"))
MAX_CONTEXT = int(os.environ.get("MAX_CONTEXT", "80"))
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "5"))
MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL_AGENTS", "4"))
MAX_BASH_TIME = int(os.environ.get("MAX_BASH_TIME", "300"))  # max seconds per bash call

# Per-rank TOTAL wall limit (including bash/tool time). 0 = disabled.
# Safety net only — bash is already capped separately. Rank is otherwise
# purely a hint to Pam for model selection; iteration count is bounded
# globally by MAX_ITER, and LLM-only wall (if any) comes from per-task
# Timeout/ThinkTime metadata, not from a rank-default table.
TOTAL_WALL_PER_RANK = os.environ.get("TOTAL_WALL_PER_RANK", "300,600,1200,1800,3600,3600")
_total_wall_limits = [int(x) for x in TOTAL_WALL_PER_RANK.split(",")]
# Context caps (chars). Full content always available via tools.
CAP_MEMORY = int(os.environ.get("CAP_MEMORY", "4000"))
CAP_GLOBAL = int(os.environ.get("CAP_GLOBAL", "1000"))
CAP_TASK = int(os.environ.get("CAP_TASK", "4000"))
CAP_TASKGROUP = int(os.environ.get("CAP_TASKGROUP", "3000"))

# Tool-result truncation cap (chars). Head + last 5 lines are kept.
TOOL_RESULT_CAP = int(os.environ.get("TOOL_RESULT_CAP", "10000"))

# Robustness thresholds. ERROR_LIMIT/NUDGE_LIMIT trigger session blacklist for
# the worker model when a model is fundamentally broken (wrong creds, malformed
# id, gateway misroute) vs. having a transient hiccup. Raise to be more tolerant
# of upstream flake; lower for tighter detection. MAX_RECOVERY caps the number
# of delay/retry rounds after LOOP_EXHAUSTED to prevent infinite recursion.
ERROR_LIMIT = int(os.environ.get("ERROR_LIMIT", "5"))
NUDGE_LIMIT = int(os.environ.get("NUDGE_LIMIT", "5"))
MAX_RECOVERY = int(os.environ.get("MAX_RECOVERY", "3"))

# Done-case review iteration floor when the Expect block references verification
# artifacts (verify/test/pass/contain/log/compile/build/output keywords). The
# review burns iterations re-running build/test commands; this floor keeps it
# from prematurely dropping to the no-tool fallback.
MAX_REVIEW_ITER_VERIFY = int(os.environ.get("MAX_REVIEW_ITER_VERIFY", "30"))
DRIVER_PATH = os.path.abspath(__file__)
DRIVER_DIR = os.path.dirname(DRIVER_PATH)
SKILLS_DIR = os.environ.get("SKILLS_DIR", os.path.join(DRIVER_DIR, "skills"))

# ============================================================
# CAM (write-only audit recording — never read back)
# ============================================================

try:
    _cam_dir = os.environ.get("CAM_DIR", "")
    if _cam_dir:
        sys.path.insert(0, _cam_dir)
    from cam import cam_init as _cam_init, cam as _cam
except ImportError:
    def _cam_init(label): pass
    def _cam(event, **data): pass


# ============================================================
# CONTROL MODEL RESOLUTION
# ============================================================

def _resolve_control_model(control_model):
    """Resolve a ControlModel value to a model name.
    Accepts a model name (e.g. 'deepseek-v3') or a rank number (e.g. '2').
    If rank: pick highest available model at-or-below that rank.
    If name: use that exact model.
    If None: returns pam.highest() (default behavior)."""
    if not control_model:
        return pam.highest(usage=_usage)
    # Check if it's a rank number
    try:
        rank = int(control_model)
        return pam.select(rank, usage=_usage)["name"]
    except (ValueError, TypeError):
        pass
    # It's a model name — use force_model to bypass selection
    return pam.select(0, usage=_usage, force_model=control_model)["name"]


# ============================================================
# SKILLS (loaded once at startup)
# ============================================================

_skills = {}       # name -> {"description": str, "tool": dict, "execute": callable}
_skill_catalog = ""  # one-line-per-skill summary for prescan

# Env skills and hardcoded fallback (used when DEFAULT_ENV_SKILL is missing,
# e.g. the user deleted it from Nam/skills/).
_ENV_SKILLS = ("common_env", "local_env", "temp_env")
_ENV_FALLBACK_PROMPT = (
    "---\nEnv fallback: no env skill loaded. The container system env is "
    "read-only — install packages under /tmp/mamba_env using micromamba "
    "(pre-installed on PATH). After creating an env, write env.sh in the "
    "task dir exporting MAMBA_ROOT_PREFIX, CONDA_PREFIX, PATH, and "
    "LD_LIBRARY_PATH so subsequent bash calls auto-activate."
)


def _parse_skill_yaml(text):
    """Parse skill.yaml manifest. Returns {name, description, tool}."""
    result = {"parameters": {}}
    in_params = False
    current_param = None
    for line in text.split('\n'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s.startswith('name:') and not in_params:
            result["name"] = s.split(':', 1)[1].strip()
        elif s.startswith('description:') and not in_params and current_param is None:
            result["description"] = s.split(':', 1)[1].strip()
        elif s == 'parameters:':
            in_params = True
        elif in_params and s.endswith(':') and not s.startswith('type:') and not s.startswith('description:') and not s.startswith('required:'):
            current_param = s[:-1].strip()
            result["parameters"][current_param] = {}
        elif in_params and current_param and s.startswith('type:'):
            result["parameters"][current_param]["type"] = s.split(':')[1].strip()
        elif in_params and current_param and s.startswith('description:'):
            result["parameters"][current_param]["description"] = s.split(':', 1)[1].strip()
        elif in_params and current_param and s.startswith('required:'):
            result["parameters"][current_param]["required"] = s.split(':')[1].strip().lower() == 'true'
        elif s.startswith('tool:'):
            pass  # tool: is a section header
        elif not in_params and s.startswith('description:'):
            # tool-level description
            result["tool_description"] = s.split(':', 1)[1].strip()
    return result


def _build_tool_schema(parsed):
    """Convert parsed skill yaml into OpenAI tool schema."""
    props = {}
    required = []
    for pname, pinfo in parsed.get("parameters", {}).items():
        prop = {"type": pinfo.get("type", "string")}
        if "description" in pinfo:
            prop["description"] = pinfo["description"]
        props[pname] = prop
        if pinfo.get("required"):
            required.append(pname)
    return {"type": "function", "function": {
        "name": parsed.get("name", ""),
        "description": parsed.get("tool_description", parsed.get("description", "")),
        "parameters": {"type": "object", "properties": props,
                       "required": required}}}


def _load_skills():
    """Scan SKILLS_DIR at startup. Two skill types:
    - Tool skill: skill.yaml + run.py → adds a tool + dispatch
    - Context skill: SKILL.md → injects instructions into agent context
    """
    global _skill_catalog
    if not os.path.isdir(SKILLS_DIR):
        return
    catalog = []
    for name in sorted(os.listdir(SKILLS_DIR)):
        skill_dir = os.path.join(SKILLS_DIR, name)
        if not os.path.isdir(skill_dir):
            continue

        manifest_yaml = os.path.join(skill_dir, "skill.yaml")
        manifest_md = os.path.join(skill_dir, "SKILL.md")
        runner = os.path.join(skill_dir, "run.py")

        if os.path.exists(manifest_yaml):
            # Tool skill: has tool schema + execute function
            with open(manifest_yaml) as f:
                parsed = _parse_skill_yaml(f.read())
            skill_name = parsed.get("name", name)
            desc = parsed.get("description", "")
            tool = _build_tool_schema(parsed)
            execute_fn = None
            if os.path.exists(runner):
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"skill_{skill_name}", runner)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                execute_fn = getattr(mod, "execute", None)
            if execute_fn:
                _skills[skill_name] = {
                    "type": "tool",
                    "description": desc,
                    "tool": tool,
                    "execute": execute_fn,
                }
                catalog.append(f"- {skill_name}: {desc} [tool]")

        elif os.path.exists(manifest_md):
            # Context skill: SKILL.md with frontmatter (name/description)
            with open(manifest_md) as f:
                content = f.read()
            # Parse frontmatter
            fm = {}
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    for line in content[3:end].split('\n'):
                        if ':' in line:
                            k, v = line.split(':', 1)
                            fm[k.strip()] = v.strip()
            skill_name = fm.get("name", name)
            desc = fm.get("description", "")
            # Store skill dir path for template access
            _skills[skill_name] = {
                "type": "context",
                "description": desc,
                "content": content,
                "skill_dir": skill_dir,
            }
            catalog.append(f"- {skill_name}: {desc} [context]")

    _skill_catalog = "\n".join(catalog) if catalog else ""


_load_skills()

# ============================================================
# MODEL SELECTION (via Pam)
# ============================================================

from pam import Pam

pam = Pam(
    rank_yaml_path=os.path.join(DRIVER_DIR, "gateway.rank.yaml"),
    gateway_url=GATEWAY,
    fallback_highest=FALLBACK_HIGHEST,
    fallback_working=FALLBACK_WORKING,
)

_usage = {}      # model -> call count (per run)
_usage_lock = threading.Lock()


def _total_wall_for_rank(rank):
    """Get total wall limit including bash/tool time. 0 = no limit."""
    if rank < 0:
        return 0
    if rank < len(_total_wall_limits):
        return _total_wall_limits[rank]
    return _total_wall_limits[-1] if _total_wall_limits else 0


# ============================================================
# AGENT NODE (threading primitive)
# ============================================================

class AgentNode:
    """One agent in the execution tree. Carries fixed model + pause event."""

    def __init__(self, agent_id, task_dir, task_file, model, depth, rank=1,
                 thinking=False, thinking_budget=0, parent=None,
                 force_model=None):
        self.agent_id = agent_id
        self.task_dir = task_dir
        self.task_file = task_file
        self.model = model  # fixed within one run, may change on retry
        self.rank = rank    # task rank, may escalate on retry
        self.thinking = thinking          # whether thinking is enabled
        self.thinking_budget = thinking_budget  # 0 = disabled
        self.force_model = force_model    # task-declared ForceModel, sticky on retry
        self.depth = depth
        self.parent = parent
        self.children = []
        self.state = "pending"
        self.result = None
        self.thread = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # starts unpaused

    def check_pause(self):
        """Block until unpaused. Call before each API call + after each tool."""
        self._pause_event.wait()

    def pause(self):
        """Pause this node + all descendants."""
        self.state = "paused"
        self._pause_event.clear()
        for child in self.children:
            child.pause()

    def resume(self):
        """Resume this node + all descendants."""
        if self.state == "paused":
            self.state = "running"
        self._pause_event.set()
        for child in self.children:
            child.resume()


# ============================================================
# MEMORY LOCK
# ============================================================

_mem_locks = {}
_mem_guard = threading.Lock()


def _get_mem_lock(task_dir):
    with _mem_guard:
        if task_dir not in _mem_locks:
            _mem_locks[task_dir] = threading.Lock()
        return _mem_locks[task_dir]


# ============================================================
# PRESCAN (highest model, single-turn, determines everything)
# ============================================================

def prescan(task_content, task_dir, memory, global_memory, task_file="top.md"):
    """Analyze task: rank, subtask deps, context assembly.
    Uses highest model — this call determines the entire execution.
    Returns {"rank": N, "subtasks": [...], "context": {file: str}}
    """
    # Deterministic metadata extraction via task_parser
    try:
        parsed = parse_task(task_content)
        meta = parsed["meta"]
    except TaskFormatError:
        # Fallback for malformed files (e.g. nu2flows): empty meta, still run
        meta = {}
    rank_match = meta.get("Rank")
    timeout_match = meta.get("Timeout")
    bash_time_match = meta.get("BashTime")
    think_time_match = meta.get("ThinkTime")
    skills_match = meta.get("Skills")
    force_model_match = meta.get("ForceModel")
    control_match = meta.get("ControlModel")
    thinking_match = meta.get("Thinking")
    nomemory_val = meta.get("NoMemory", "")
    no_memory = nomemory_val.lower() in ("on", "true", "yes", "1")
    task_group = meta.get("TaskGroup")
    suggested_skills = []
    if skills_match:
        suggested_skills = [s.strip() for s in skills_match.split(',') if s.strip()]

    # Find .md files in task_dir (potential subtasks, excluding self)
    md_files = []
    if os.path.isdir(task_dir):
        md_files = sorted(f for f in os.listdir(task_dir)
                         if f.endswith('.md') and not f.startswith('.')
                         and f != task_file)

    # Category: group by prefix (A.B.md → category A)
    categories = {}
    for f in md_files:
        parts = f.rsplit('.md', 1)[0].split('.')
        if len(parts) >= 2:
            cat = parts[0]
            categories.setdefault(cat, []).append(f)

    mr = pam.max_rank()
    cm = control_match  # already a string or None
    model = _resolve_control_model(cm)

    if rank_match and not md_files:
        # Self-declared rank, no subtasks — skip LLM call
        result = {
            "rank": int(rank_match),
            "subtasks": [],
            "context": {},
            "skills": [s for s in suggested_skills if s in _skills],
            "source": "self-declared",
        }
        if timeout_match:
            result["wall_limit"] = int(timeout_match)
        if bash_time_match:
            result["bash_time"] = int(bash_time_match)
        if think_time_match:
            result["think_time"] = int(think_time_match)
        if force_model_match:
            result["force_model"] = force_model_match
        if control_match:
            result["control_model"] = control_match
        if thinking_match:
            result["thinking"] = True
            result["thinking_budget"] = int(thinking_match)
        result["no_memory"] = no_memory
        result["task_group"] = task_group
        return result

    # Single-turn LLM call for analysis
    skills_info = ""
    if _skill_catalog:
        skills_info = (f"Available skills:\n{_skill_catalog}\n\n"
            f"Task suggests skills: {suggested_skills or '(none)'}\n\n")
    prompt = (
        f"Analyze this SAM task. Reply with ONLY valid JSON.\n\n"
        f"Task content:\n{task_content[:3000]}\n\n"
        f"Available .md files in directory: {md_files}\n\n"
        f"Categories (files sharing prefix): {dict(categories)}\n\n"
        f"{skills_info}"
        f"Reply format:\n"
        f'{{"rank": <0-{mr} difficulty>, '
        f'"subtasks": [{{"file": "name.md", "rank": <0-{mr}>, "depends_on": ["other.md"]}}], '
        f'"skills": ["skill_name", ...]}}\n\n'
        f"Rules:\n"
        f"- rank 0 = trivial, {mr} = complex\n"
        f"- depends_on lists files that must complete first\n"
        f"- dependencies must form a tree (no cycles)\n"
        f"- if no subtasks found, return empty list\n"
        f"- skills: include only skills the task actually needs\n"
        f"- if task self-declares Rank: N, use that rank\n"
        f"- if task self-declares Skills:, respect those suggestions"
    )

    try:
        client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
        resp = client.chat.completions.create(
            model=model, max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        with _usage_lock:
            _usage[model] = _usage.get(model, 0) + 1
        raw = resp.choices[0].message.content.strip()
        _cam("api_request", caller="prescan", model=model,
             prompt=prompt, response=raw, **_response_meta(resp))
        # Extract JSON from response (may be wrapped in ```json...```)
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group())
        else:
            plan = {"rank": 1, "subtasks": []}
    except Exception:
        plan = {"rank": int(rank_match) if rank_match else 1,
                "subtasks": []}

    rank = int(plan.get("rank", 1))
    subtasks = plan.get("subtasks", [])

    # Assemble context for each subtask (capped)
    context = {}
    for st in subtasks:
        fname = st.get("file", "")
        parts = []
        if global_memory:
            parts.append(f"---\nGlobal Experience:\n{global_memory[:CAP_GLOBAL]}")
        cat_prefix = fname.rsplit('.md', 1)[0].split('.')[0] if '.' in fname.rsplit('.md', 1)[0] else ""
        if cat_prefix and cat_prefix in categories:
            for sibling in categories[cat_prefix]:
                if sibling != fname:
                    parts.append(f"---\nCategory sibling ({sibling}): see shared memory")
        if memory:
            parts.append(f"---\nParent Memory:\n{memory[:CAP_MEMORY]}")
        context[fname] = "\n".join(parts)

    # Skills: from prescan LLM output, validated against loaded skills
    skills = [s for s in plan.get("skills", suggested_skills) if s in _skills]

    # Auto-inject default env skill if none declared.
    # DEFAULT_ENV_SKILL (from ENV.sh) picks which one; if it's missing from
    # _skills (user deleted it), skill_context rendering adds a hardcoded
    # fallback prompt pointing at /tmp.
    if not (set(skills) & set(_ENV_SKILLS)):
        default_env = os.environ.get("DEFAULT_ENV_SKILL", "temp_env")
        if default_env in _skills:
            skills.append(default_env)

    result = {
        "rank": max(0, min(rank, mr)),
        "subtasks": subtasks,
        "context": context,
        "skills": skills,
        "source": "scanned",
    }
    if timeout_match:
        result["wall_limit"] = int(timeout_match)
    if bash_time_match:
        result["bash_time"] = int(bash_time_match)
    if think_time_match:
        result["think_time"] = int(think_time_match)
    if force_model_match:
        result["force_model"] = force_model_match
    if control_match:
        result["control_model"] = control_match
    if thinking_match:
        result["thinking"] = True
        result["thinking_budget"] = int(thinking_match)
    result["no_memory"] = no_memory
    result["task_group"] = task_group
    return result


# ============================================================
# SCHEDULER (wave-based, ~10 lines of core logic)
# ============================================================

_agent_sem = threading.Semaphore(MAX_PARALLEL)


class Scheduler:
    """Manages sub-task execution for a parent agent node."""

    def __init__(self, parent_node, prescan_result=None):
        self.parent = parent_node
        self.plan = prescan_result or {}

    def launch(self, task_dir, task_file, model, rank=1, context=None, wall_limit=None):
        """Launch a sub-agent in a thread. Returns AgentNode."""
        agent_id = f"{self.parent.agent_id}.{task_file.rsplit('.md',1)[0]}"
        node = AgentNode(agent_id, task_dir, task_file, model,
                        self.parent.depth + 1, rank=rank, parent=self.parent)
        self.parent.children.append(node)

        def _run():
            _agent_sem.acquire()
            try:
                node.state = "running"
                node.result = _run_sam(node, context=context, wall_limit=wall_limit)
                node.state = "done"
            except Exception as e:
                node.result = f"ERROR: {e}"
                node.state = "failed"
            finally:
                _agent_sem.release()

        node.thread = threading.Thread(target=_run, daemon=True)
        node.thread.start()
        return node

    def launch_blocking(self, task_dir, task_file, model, rank=1, context=None, wall_limit=None):
        """Launch and wait. Returns result string."""
        node = self.launch(task_dir, task_file, model, rank, context, wall_limit)
        node.thread.join()
        return node.result or ""

    def pause_siblings(self, exclude=None):
        """Pause all sibling agents (and subtrees). Returns paused list."""
        paused = []
        for child in self.parent.children:
            if child is not exclude and child.state == "running":
                child.pause()
                paused.append(child)
        return paused

    def resume_siblings(self, paused):
        for node in paused:
            node.resume()


# ============================================================
# SYSTEM PROMPTS
# ============================================================

SYSTEM_CORE = """\
You are an autonomous agent executing a SAM (Self-Assessed Module).

A SAM is a closed loop defined by a .md file with three sections:
- Context: what you know
- Todo: what to do
- Expect: what must be true when done

Capabilities (via tool calls):
- bash: run any shell command
- read_file: read a file (relative to task dir)
- write_file: create/overwrite a file
- edit_file: replace a string in a file (faster than write_file for small fixes)
- web_fetch: HTTP GET a URL
- memory_read: read persistent memory (survives across runs)
- memory_write: overwrite persistent memory
- done: signal SAM completion with a summary

Environment:
- Your task directory (./) is writable and persistent — put all output here.
- micromamba is in PATH but the active env (/F/mamba) is the DRIVER's env,
  NOT yours. It is read-only. Do NOT pip install or micromamba install into it.
  Writes may appear to succeed (RAM layer) but WILL be silently lost on exit.
  To install packages, create a NEW env under ./ :
    MAMBA_ROOT_PREFIX=./mamba_env micromamba create -n work python=3.12 -y
    micromamba run -r ./mamba_env -n work pip install <pkg>
- env.sh is the standard way to persist environment setup across bash calls.
  If env.sh exists in ./, it is auto-sourced before every bash command.
  After finding or creating an environment, IMMEDIATELY write env.sh.
  Use absolute paths anchored to env.sh itself — relative ./ paths break
  as soon as a command does `cd subdir && ...` or a script internally
  calls subprocess.run:
    cat > env.sh << 'EOF'
    _ENV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    export PATH="$_ENV_ROOT/mamba_env/envs/work/bin:$PATH"
    export LD_LIBRARY_PATH="$_ENV_ROOT/mamba_env/envs/work/lib:${LD_LIBRARY_PATH:-}"
    EOF
  Then all subsequent bash commands will have the env's tools available as
  bare commands — no prefixes needed.
- /tmp is writable but not persistent across runs.
- Writes to paths outside ./ may silently vanish. Always use ./

Follow the SAM structure: understand Context, execute Todo, satisfy Expect.
Memory and global experience in your context may be truncated — use
memory_read or read_file tools to access full versions when needed.
An independent reviewer will check your Expect claims after you call done.
Call done only when you believe all expectations are truly met.

When you call done, include two things in the summary:

1) RAW evidence — the actual command(s) you ran plus the tail of their
   output (~10-30 lines, uninterpreted). Paste the command line prefixed
   with `$ ` then the tool's literal stdout/stderr tail. Do NOT fabricate
   or paraphrase — the reviewer grep-checks the cited output AND re-runs
   independently. Honest partial-success beats polished prose; if a step
   failed, quote the real failure line.

2) A `## Verification Reference` block at the END of your summary — a
   warmup map for the reviewer so they don't have to rediscover your env.
   Format:
     ## Verification Reference
     - Env: <skill used (common_env/local_env/temp_env) + where env.sh lives>
     - Verify: <exact bash command(s) that passed, copy-pasteable>
     - Evidence: <file path or stdout signature that shows pass>
     - Randomness: <seed(s) / fixture / sampling if any — reviewer may vary>

   This is a SOFT HINT. The reviewer treats it as a warmup, not as
   authority — they will re-run verification independently and may vary
   random inputs/seeds to detect fabrication. An accurate reference
   speeds review; a misleading one just invites stricter scrutiny.

Bash output may be truncated for long commands. To get specific results from
long output, use grep, tail, or redirect to a file and read the parts you need.

If a fix does not work, diagnose before retrying — read error output, check
assumptions, and understand why it failed. Do not rewrite code blindly."""

# Conditional system prompt sections, assembled from task metadata
SYSTEM_HOME = """\
- /home may contain shared credentials (.ssh keys, git config). It may be
  read-only — writes to /home may go to RAM and be discarded on exit."""

SYSTEM_MNT_RW = """\
- /mnt is shared persistent storage across tasks, writable.
  Use it for large reusable assets (shared envs, datasets)."""

SYSTEM_MNT_ENVS = """\
- /mnt/sci_envs/ may contain shared pre-built environments. Check there
  FIRST before installing anything:
    ls /mnt/sci_envs/
  Each subdirectory is a MAMBA_ROOT_PREFIX with envs inside. If a matching
  env exists, reuse it by writing env.sh with its paths."""

SYSTEM_MNT_RO = """\
- /mnt is shared storage across tasks, read-only in this run.
  Existing shared environments and data can be used but not modified."""

SYSTEM_SUBAGENT = """\
- subagent: delegate to a sub-SAM by pointing it at a .md task file"""


def _build_system_prompt(meta, has_subtasks=False):
    """Assemble SYSTEM prompt from core + conditional sections based on metadata.
    Uses EFFECTIVE_COMMON_* env vars (set by portal.py after isolation override)
    so the prompt matches actual container mounts, not just task metadata."""
    core = SYSTEM_CORE

    parts = [core]

    # Use effective values from portal.py (reflects isolation overrides)
    # Fall back to task metadata if env vars not set (e.g. direct invocation)
    common_home = os.environ.get("EFFECTIVE_COMMON_HOME",
                                  meta.get("CommonHome", "ro")).lower()
    common_storage = os.environ.get("EFFECTIVE_COMMON_STORAGE",
                                     meta.get("CommonStorage", "rw")).lower()

    if common_home != "disable":
        parts.append(SYSTEM_HOME)

    if common_storage == "rw":
        parts.append(SYSTEM_MNT_RW)
        # Only mention sci_envs when task has env-related skill
        skills = meta.get("Skills", "")
        if "env" in skills.lower():
            parts.append(SYSTEM_MNT_ENVS)
    elif common_storage == "ro":
        parts.append(SYSTEM_MNT_RO)

    if has_subtasks:
        parts.append(SYSTEM_SUBAGENT)

    return "\n\n".join(parts)

REVIEW_SYSTEM = """\
You are an independent review agent. Your job is to PROTECT against false positives.

CORE PRINCIPLE
  The worker's claims are HEARSAY. Your OWN tool observations are the only
  ground truth. Never approve based on what the worker says — only on what
  YOU observe with your own tools. Workers have been caught writing fake log
  files, claiming tests pass when they don't, and producing code that doesn't
  even compile. Assume fabrication is possible until you rule it out.

CASE 1 — Worker called `done`  (your primary duty: independent verification)

  You MUST independently verify every item in the Expect section before
  approving. For each criterion:

  1. Read the Expect criterion and identify what real-world state or output
     it requires.
  2. Use your tools to OBSERVE that state DIRECTLY. Do not trust worker-
     produced artifacts at face value.
  3. If the criterion references a verification script, test suite, build
     command, or ANY command that PRODUCES the expected evidence, YOU MUST
     RE-RUN that command yourself and compare its ACTUAL output against the
     criterion. Examples:
       - "<log-file> contains <success-string>" → re-run the command that
         should produce the log; check its LIVE output, not the file.
       - "tests pass" → run the test runner yourself.
       - "binary X exists and prints Y" → run the binary yourself.
     The file on disk is NOT evidence. The live command output IS evidence.
  4. Cross-check for fabrication signals:
       - Does the log's format / header / structure actually match what the
         tool produces? A suspiciously terse success line (e.g. a lone
         "PASSED" or "OK" with no test counts, timings, summary, or framing
         the real tool would emit) is a fabrication red flag.
       - Compare file mtime to the history of bash calls. If the log was
         written by `write_file` rather than by running the verifier, it is
         fabricated.
       - If you re-run the verification and the output differs from the file,
         the file is stale or fake — REJECT.
  5. WARMUP — read worker's "## Verification Reference" block.
     The worker's done summary may include a `## Verification Reference`
     block naming the env, verification commands, evidence locations, and
     random seeds used. Treat this as a WARMUP MAP, not as authority:
       - Use it to jump straight to the verify step (skip env rediscovery).
       - Then independently run at least one cited command yourself AND
         cross-check the artifacts; trust only what YOU observe.
       - If no Verification Reference is present, scan the worker's recent
         bash tool_results (exit code 0) for the same cues.

  6. ENV-REUSE POLICY — do NOT rebuild the environment.
     When the worker claims done, the env is in a good state by definition.
     Your bash is auto-wrapped with `. env.sh && ...` so tools are on PATH.
       - common_env (shared /mnt/sci_envs/<prefix>): READ-ONLY. Never
         rebuild, never pip/mamba install anything there. Just source
         env.sh (automatic) and run bare commands.
       - local_env (./mamba_env) or temp_env (/tmp/mamba_env): REUSE what
         the worker built. Do not recreate. env.sh is auto-sourced.
       - If env.sh is missing or malformed, surface that as a failure —
         don't invent a new env.
     "Module not found" in system python when the worker used a local env
     is NOT fabrication — it means you bypassed env.sh. Try again with
     the env. `bash` in this agent auto-sources env.sh; just don't write
     commands that `cd` elsewhere and shadow the wrapper.

  7. RANDOMIZATION — vary inputs to catch over-fitting/fabrication.
     If the verification uses a random seed, a fixed sample, or a specific
     test fixture, VARY it when you re-run:
       - Re-run with a different seed.
       - Feed a different sample / edge case / alternate fixture.
       - Perturb inputs in a way the worker couldn't have anticipated.
     A correct solution generalizes across varied inputs; a solution that
     was pattern-matched to the reference case will diverge. If the task
     is deterministic with no randomness, cross-check artifacts against
     domain invariants instead (expected value ranges, file structure,
     counts, known-good relationships between fields).

  Call `verdict`:
    - passed=true  ONLY if YOUR OWN observations independently confirm EVERY
      Expect criterion. If you could not independently verify a criterion,
      passed=false.
    - passed=false otherwise. In `observations`, include the ACTUAL output
      you saw from your own tool calls — quote the real output alongside the
      worker's claim. In `reason`, state specifically what the worker should
      fix, including the concrete evidence of the failure.

  When rejecting, BE SPECIFIC AND DIAGNOSTIC. Restating the failure ("most
  tests fail", "mismatch") is useless — the next worker will just rewrite and
  hit the same class of bug. Look AT the failure output and try to name the
  pattern. Common categories (task-agnostic):

    - SYSTEMATIC DEVIATION: observed values differ from expected by a
      near-constant amount, ratio, or scale across all items.
      (suggests a wrong factor / normalization / direction / precision in
       one computation, not per-item bugs)
    - POSITIONAL error: some items wrong, others correct, with structure.
      (e.g. every other item wrong → stride/step off-by-one;
       first N wrong then correct → warmup / pipeline not flushed;
       last N missing → early termination / wrong loop bound)
    - INDEX/TIME SHIFT: observed sequence i matches expected i+k.
      (output lags or leads by k — wrong trigger condition, off-by-k
       in an index, wrong causality)
    - BUILD / RUNTIME error: compile fails, exit nonzero, import error,
      missing file. Quote the exact line the tool emitted.
    - GARBAGE output: no discernible relationship to expected.
      (suggests fundamental wrong-algorithm / wrong-wiring, not a subtle
       tweak; next attempt should re-read the spec before rewriting)

  In `reason` / `memory_update`, NAME the pattern you see and suggest the
  CLASS of fix, not just what's wrong. Example shape (adapt to your task):
  "observed values are uniformly ~30% below expected — looks like a
  constant-factor bug in the producing step; check the scaling/direction in
  <component>." Quote 2-3 concrete values (first two + a later one) so the
  next worker can sanity-check their own fix.

  If you cannot diagnose from the output alone, say so explicitly — e.g.
  "outputs look unrelated to inputs; could not identify a pattern;
  recommend re-reading the interface spec / reference data before
  rewriting."

CASE 2 — Worker hit MAX_ITERATIONS  (forward-looking guidance)

  The worker ran out of iterations without calling done. Your job is to route
  the task toward success on the next attempt.

  Decide:
    - DELAY:   task depends on unfinished sibling work. Suggest wait time.
    - RETRY:   task can succeed with specific guidance. Provide concrete
               `memory_update` hints (see below). This is usually the right
               call when the worker was making progress but ran out of time
               or took a wrong sub-approach.
    - REFLECT: task is fundamentally stuck (wrong definition, too large,
               missing tools). Trigger deeper diagnosis.

  If RETRY, your `memory_update` is the most important thing you will write.
  It will be injected into the NEXT worker's context. Write concrete,
  actionable hints — not vague encouragement. Good hints name files, lines,
  commands, and pitfalls. Bad hints say "be more careful".

  CRITICAL: Before writing the memory_update, READ the current state of any
  files the worker modified. The next worker starts fresh with no memory.
  Use this format:
    KEEP: <what is correct in the current files — be specific, name values>
    FIX:  <what is still wrong and how — name the PATTERN when possible>
    RUN:  <exact command to verify>
  Without KEEP, the next worker will rewrite from scratch and lose progress.

  Pattern-naming applies here too (see CASE 1 "BE SPECIFIC AND DIAGNOSTIC"):
  if the last verify showed a systematic offset, time-shift, or every-Nth
  error, NAME that pattern in FIX so the next worker doesn't repeat the
  same guess. Quote 2-3 concrete sample values if available.

  Model control (pick ONE):
    - Same model, just retry with better guidance: omit model fields.
    - Try another at same rank: set exclude_model=true (model did poorly).
    - Escalate rank: set suggested_rank=N (model too weak).

  If you detected fabrication in a prior done-case rejection that cascaded
  here, bias toward exclude_model=true or suggested_rank escalation — the
  worker cannot be trusted on this task.

  Thinking mode (thinkable=true models only): enable ONLY for reasoning
  failures. Start with thinking_budget=5000.

GLOBAL PRINCIPLES
- Ranking principle: fast iteration wins. Prefer same rank + better hints
  over escalation, unless the worker clearly lacks capability.
- Be strict. Never approve because "probably it's fine" — require observed
  evidence.
- You have read-only tools: bash, read_file, memory_read, compact.
- The same task_dir and environment from the worker persist during review —
  you do NOT need to re-install or re-bind anything."""

REVIEW_SYSTEM_SIMPLE = """\
You are a quick verification agent. Check if the task's Expect criteria are met.
Read the task file for the Expect section. Use bash/read_file to INDEPENDENTLY
verify each criterion — observe real state with your own tools. Do not trust
worker-produced log files or claims; if a criterion references a test/verify
script, re-run it yourself and use the live output.

Env reuse: bash auto-sources env.sh, so the worker's env is active. Do NOT
rebuild it. If worker included a `## Verification Reference` block in the
done summary, use it as a warmup (env path, verify command), then verify
independently. When inputs are random, vary the seed to catch over-fitting.

Then call `verdict` with passed=true/false, observations (quoting the real
output you saw), and reason. When rejecting, look for a PATTERN in the
failure — is the deviation SYSTEMATIC (constant factor/offset across items),
POSITIONAL (every-Nth item, first-N, or last-N), SHIFTED (observed i matches
expected i+k), a BUILD/RUNTIME error, or GARBAGE (no pattern) — and name it
in `reason`. Quote 2-3 sample values. If case is 'failed', call `decision`
with action=retry + concrete memory_update hints (name files, commands,
pitfalls, patterns)."""

REFLECT_SYSTEM = """\
You are a reflection agent. A SAM failed to converge. Diagnose WHY.

Access: task .md files, .history_index.md (outline), .history.md (full,
use offset/limit), .memory.md, driver.py, bash, read_file.
You can update .memory.md with findings via memory_write.

Start with .history_index.md for overview, then read specific parts of
.history.md with offset/limit for details.

Failure causes (check in order):
1. Task definition wrong  2. Task too large  3. Stuck in a loop
4. Review too strict  5. Tool limitation  6. Driver bug

Diagnose, update memory, call `diagnosis`."""

# ============================================================
# TOOL DEFINITIONS
# ============================================================

TOOLS = [
    {"type": "function", "function": {"name": "bash",
        "description": "Execute a bash command. Returns stdout+stderr. "
            "Set timeout for long-running commands (default 30s, max from config).",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer", "description": "Seconds to wait (default 30)"}},
            "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file",
        "description": "Read a file. Returns first 10k chars by default. Use offset/limit for large files.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "description": "Start position in chars (default 0)"},
            "limit": {"type": "integer", "description": "Max chars to return (default 10000)"}},
            "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file",
        "description": "Write content to a file (full overwrite). Prefer edit_file for modifying existing files — it preserves what you already fixed.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file",
        "description": "Replace a string in a file. Faster than write_file for small changes. "
                       "old_string must match exactly once in the file.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string", "description": "Exact string to find (must be unique in file)"},
            "new_string": {"type": "string", "description": "Replacement string"}},
            "required": ["path", "old_string", "new_string"]}}},
    {"type": "function", "function": {"name": "web_fetch",
        "description": "HTTP GET a URL. Returns body (truncated 10k).",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "memory_read",
        "description": "Read persistent memory.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "memory_write",
        "description": "Overwrite persistent memory.",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string"}}, "required": ["content"]}}},
    {"type": "function", "function": {"name": "subagent",
        "description": "Spawn a sub-SAM on a .md task file. Blocks until done.",
        "parameters": {"type": "object", "properties": {
            "task_file": {"type": "string"}}, "required": ["task_file"]}}},
    {"type": "function", "function": {"name": "done",
        "description": "REQUIRED to complete the task. Call this when ALL Expect criteria "
                       "are satisfied. Do not stop generating without calling a tool — "
                       "either keep working or call done. An independent reviewer will verify.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "What was accomplished."}},
            "required": ["summary"]}}},
]

REVIEW_TOOLS = [
    {"type": "function", "function": {"name": "bash",
        "description": "Inspect state (read-only).",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file",
        "description": "Read a file. Use offset/limit for large files.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "description": "Start position in chars"},
            "limit": {"type": "integer", "description": "Max chars to return"}},
            "required": ["path"]}}},
    {"type": "function", "function": {"name": "memory_read",
        "description": "Read memory.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "compact",
        "description": "Send text to a cheap model to summarize/compact it. "
            "Use when tool outputs or memory are too long. Returns compacted text.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "Text to compact"},
            "instruction": {"type": "string", "description": "What to keep/focus on"}},
            "required": ["text"]}}},
    {"type": "function", "function": {"name": "verdict",
        "description": "Verification verdict (done case).",
        "parameters": {"type": "object", "properties": {
            "passed": {"type": "boolean"},
            "observations": {"type": "string"},
            "reason": {"type": "string"}},
            "required": ["passed", "observations", "reason"]}}},
    {"type": "function", "function": {"name": "decision",
        "description": "Recovery decision (failed case).",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["delay", "retry", "reflect"]},
            "wait_seconds": {"type": "integer"},
            "memory_update": {"type": "string"},
            "suggested_rank": {"type": "integer", "description": "New rank if model was insufficient."},
            "exclude_model": {"type": "boolean", "description": "True = current model did poorly, try another at same rank."},
            "enable_thinking": {"type": "boolean", "description": "Enable thinking mode if model supports it."},
            "thinking_budget": {"type": "integer", "description": "Thinking token budget (e.g. 5000, 10000). Only if enable_thinking=true."},
            "reason": {"type": "string"}},
            "required": ["action", "reason"]}}},
]

REFLECT_TOOLS = [
    {"type": "function", "function": {"name": "bash",
        "description": "Inspect state.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "read_file",
        "description": "Read a file. Use offset/limit for large files.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "description": "Start position in chars"},
            "limit": {"type": "integer", "description": "Max chars to return"}},
            "required": ["path"]}}},
    {"type": "function", "function": {"name": "memory_read",
        "description": "Read memory.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "memory_write",
        "description": "Update memory with findings.",
        "parameters": {"type": "object", "properties": {
            "content": {"type": "string"}}, "required": ["content"]}}},
    {"type": "function", "function": {"name": "diagnosis",
        "description": "Deliver diagnosis.",
        "parameters": {"type": "object", "properties": {
            "cause": {"type": "string", "enum": [
                "task_definition", "task_too_large", "stuck_loop",
                "review_too_strict", "tool_limitation", "driver_bug", "other"]},
            "evidence": {"type": "string"},
            "suggestion": {"type": "string"}},
            "required": ["cause", "evidence", "suggestion"]}}},
]

# ============================================================
# HISTORY (thread-safe: build string first, single write call)
# ============================================================

_history_lock = threading.Lock()


def _history(task_dir, entry_type, depth, **kwargs):
    """Append to task .history.md. Append-only tape."""
    _cam(entry_type, depth=depth, task_dir=task_dir, **kwargs)
    ts = time.strftime('%H:%M:%S')
    indent = "  " * depth
    hf = os.path.join(task_dir, ".history.md")
    lines = [f"{indent}**[{ts}] {entry_type}**"]
    for k, v in kwargs.items():
        val = str(v)[:500]
        lines.append(f"{indent}  - {k}: {val}")
    lines.append("")
    entry = "\n".join(lines) + "\n"
    with _history_lock:
        with open(hf, "a") as f:
            f.write(entry)


def _global_history(entry_type, **kwargs):
    """Append to .global_history.md. System-level tape."""
    _cam(entry_type, **kwargs)
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    hf = os.path.join(DRIVER_DIR, "run", ".global_history.md")
    lines = [f"**[{ts}] {entry_type}**"]
    for k, v in kwargs.items():
        val = str(v)[:500]
        lines.append(f"  - {k}: {val}")
    lines.append("")
    entry = "\n".join(lines) + "\n"
    with _history_lock:
        with open(hf, "a") as f:
            f.write(entry)


# ============================================================
# HELPERS
# ============================================================

def _read_memory(task_dir):
    mf = os.path.join(task_dir, ".memory.md")
    if os.path.exists(mf):
        with _get_mem_lock(task_dir):
            with open(mf) as f:
                return f.read()
    return ""


def _read_global_memory():
    gm = os.path.join(DRIVER_DIR, "run", ".global_memory.md")
    if os.path.exists(gm):
        with open(gm) as f:
            return f.read()
    return ""

def _read_taskgroup_memory(task_group):
    if not task_group:
        return ""
    fm = os.path.join(DRIVER_DIR, "run", ".taskgroup_memory", f"{task_group}.md")
    if os.path.exists(fm):
        with open(fm) as f:
            return f.read()
    return ""

def _write_taskgroup_memory(task_group, entry):
    if not task_group:
        return
    fm_dir = os.path.join(DRIVER_DIR, "run", ".taskgroup_memory")
    os.makedirs(fm_dir, exist_ok=True)
    fm = os.path.join(fm_dir, f"{task_group}.md")
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(fm, "a") as f:
        f.write(f"\n---\n**[{ts}]**\n{entry}\n")


# ------------------------------------------------------------------
# Review feedback — per-subtask, run-scoped, survives retries.
# Written on review rejection/retry, injected into worker context at
# _run_sam start, cleared on SAM_VERIFIED. Independent of NoMemory since
# it is scoped to the current task run, not cross-task memory.
# ------------------------------------------------------------------

def _feedback_path(task_dir, task_file):
    stem = os.path.basename(task_file).rsplit(".md", 1)[0].lstrip("./")
    return os.path.join(task_dir, f".review_feedback.{stem}.md")


def _read_feedback(task_dir, task_file):
    fp = _feedback_path(task_dir, task_file)
    if os.path.exists(fp):
        with open(fp) as f:
            return f.read()
    return ""


def _append_feedback(task_dir, task_file, block):
    fp = _feedback_path(task_dir, task_file)
    ts = time.strftime('%H:%M:%S')
    with open(fp, "a") as f:
        f.write(f"\n---\n[{ts}] {block}\n")


def _clear_feedback(task_dir, task_file):
    fp = _feedback_path(task_dir, task_file)
    if os.path.exists(fp):
        try:
            os.remove(fp)
        except OSError:
            pass


def _format_prior_investigation(messages, max_pairs=12, result_cap=500):
    """Extract (tool_call, tool_result) pairs from a failed review loop and
    format them as a reference block for a lateral reviewer. Assistant text
    and partial conclusions are stripped — only raw system-captured outputs
    are passed through. Returns '' if nothing useful to share."""
    pairs = []
    for i, msg in enumerate(messages):
        tool_calls = getattr(msg, "tool_calls", None) if not isinstance(msg, dict) else None
        if not tool_calls:
            continue
        for tc in tool_calls:
            if len(pairs) >= max_pairs:
                break
            try:
                call_args = tc.function.arguments[:200]
                call_desc = f"{tc.function.name}({call_args})"
            except Exception:
                continue
            result_text = ""
            for j in range(i + 1, min(i + len(tool_calls) + 4, len(messages))):
                m = messages[j]
                if isinstance(m, dict) and m.get("role") == "tool" \
                        and m.get("tool_call_id") == tc.id:
                    content = str(m.get("content", ""))
                    if len(content) > result_cap:
                        half = result_cap // 2
                        content = (content[:half]
                                   + "\n...[truncated]...\n"
                                   + content[-half:])
                    result_text = content
                    break
            pairs.append((call_desc, result_text))
        if len(pairs) >= max_pairs:
            break
    if not pairs:
        return ""
    lines = [
        "PRIOR INVESTIGATION LOG (previous reviewer did NOT commit a verdict)",
        "",
        "A prior reviewer at the same rank began investigating this done-claim",
        "but could not commit a verdict in its iteration budget. Below are the",
        "RAW tool calls it made and the SYSTEM-CAPTURED outputs. The prior",
        "reviewer's interpretation and partial reasoning are NOT included.",
        "",
        "Rules for using this log:",
        "1. Form your OWN verdict. This log is reference only, NOT authoritative.",
        "2. For any verification command named in the Expect section (test",
        "   suites, verify scripts, builds), you MUST re-run it yourself. Do",
        "   not cite the prior log as evidence for your final verdict.",
        "3. If the prior log contradicts the worker's claim, that is a strong",
        "   rejection signal — document the contradiction explicitly.",
        "",
    ]
    for idx, (call, result) in enumerate(pairs, 1):
        lines.append(f"[{idx}] {call}")
        if result:
            for rline in result.split("\n")[:15]:
                lines.append(f"    > {rline}")
            if result.count("\n") > 15:
                lines.append("    > ...")
        lines.append("")
    return "\n".join(lines)


def _extract_expect(task_content):
    patterns = [
        r'#{1,3}\s*Expect(?:ation|ed)?\s*\n(.*?)(?=\n#{1,3}\s|\Z)',
        r'\*\s*Expect(?:ation|ed)?\s*[:：]\s*(.*?)(?=\n\*\s|\Z)',
    ]
    for pat in patterns:
        m = re.search(pat, task_content, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _trim_messages(messages):
    if len(messages) <= MAX_CONTEXT:
        return messages
    head = messages[:2]
    tail = messages[-(MAX_CONTEXT - 3):]
    head.append({"role": "user", "content":
        "[Earlier messages trimmed. Use memory_read for persistent state.]"})
    return head + tail


def _response_meta(result):
    """Extract audit-relevant metadata from an OpenAI SDK response."""
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


def _api_call(client, model, messages, tools, retries=3,
              thinking=False, thinking_budget=0):
    mc = pam.config(model)
    model_max_tokens = mc.get("max_tokens", 4096)
    kwargs = {"model": model, "messages": messages, "tools": tools}
    if thinking and thinking_budget > 0:
        max_tb = mc.get("max_thinking_budget", thinking_budget)
        tb = min(thinking_budget, max_tb, model_max_tokens - 1024)
        tb = max(tb, 0)
        if tb > 0:
            kwargs["max_tokens"] = tb + 1024
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": tb}
        else:
            kwargs["max_tokens"] = min(4096, model_max_tokens)
    else:
        kwargs["max_tokens"] = min(4096, model_max_tokens)
    # Hard cap on per-request wall time. Without this, a stale TCP connection
    # to a Bedrock/Ollama backend can hang the OpenAI client for the SDK's
    # default ~10 min, stalling the whole driver. 120s is generous for any
    # legitimate response and short enough to fail fast and trigger retry.
    kwargs["timeout"] = 120
    for attempt in range(retries):
        try:
            result = client.chat.completions.create(**kwargs)
            with _usage_lock:
                _usage[model] = _usage.get(model, 0) + 1
            pam.report_connection_ok()
            msg = result.choices[0].message
            _cam("api_request", model=model, messages=messages,
                 tools=[t.get("function", {}).get("name") for t in (tools or [])],
                 thinking=thinking, thinking_budget=thinking_budget,
                 response_content=getattr(msg, 'content', None),
                 response_tool_calls=[
                     {"name": tc.function.name, "args": tc.function.arguments}
                     for tc in (msg.tool_calls or [])] if msg.tool_calls else [],
                 **_response_meta(result))
            return result
        except Exception as e:
            err = str(e)
            if any(s in err for s in ["Connection", "Timeout", "timeout"]):
                pam.report_connection_error()
            if attempt < retries - 1 and any(s in err for s in
                    ["429", "500", "502", "503", "Connection", "Timeout", "timeout"]):
                time.sleep(2 ** attempt)
            else:
                raise


def _checkpoint_msg(task_content, memory, iteration, max_iter, wall_used=None, wall_limit=None):
    budget = f"iteration {iteration}/{max_iter}"
    if wall_limit:
        budget += f", LLM time {wall_used:.0f}s/{wall_limit}s"
    parts = [f"[Checkpoint: {budget}]",
        "Re-read your SAM and verify progress.",
        "---", "SAM (re-stated):", task_content[:CAP_TASK]]
    if memory:
        parts += ["---", "MEMORY (use memory_read for full):", memory[:CAP_MEMORY]]
    remaining = max_iter - iteration
    parts += ["---", f"You have {remaining} iterations left.",
        "What has been achieved? What remains?",
        "If all expectations are met, call done. Otherwise keep working efficiently.",
        "---",
        "Tool reminder: write_file requires BOTH arguments: "
        "{\"path\": \"filename\", \"content\": \"...\"}. "
        "bash requires: {\"command\": \"...\"}. "
        "done requires: {\"summary\": \"...\"}."
    ]
    return "\n".join(parts)


# ============================================================
# TOOL DISPATCH
# ============================================================

def _truncate(content, limit=None):
    """Truncate keeping head + last few lines so agents see errors and final result."""
    if limit is None:
        limit = TOOL_RESULT_CAP
    if len(content) <= limit:
        return content
    # Keep as much head as possible, append last 5 lines for final status.
    lines = content.rstrip('\n').split('\n')
    tail_lines = '\n'.join(lines[-5:])
    head = limit - len(tail_lines) - 80  # 80 for the separator
    if head < limit // 2:
        head = limit // 2
    return (content[:head]
            + f"\n\n...[{len(content) - head - len(tail_lines)} chars truncated, last 5 lines shown]...\n\n"
            + tail_lines)


def _read_file_impl(args, task_dir):
    """Shared read_file with offset/limit support."""
    p = args["path"]
    path = p if os.path.isabs(p) else os.path.join(task_dir, p)
    offset = int(args.get("offset", 0) or 0)
    limit = int(args.get("limit", 10000) or 10000)
    with open(path) as f:
        content = f.read()
    total = len(content)
    chunk = content[offset:offset + limit]
    if total > offset + limit:
        chunk += f"\n\n[Showing {offset}-{offset+len(chunk)} of {total} chars]"
    return chunk


def _compact_text(text, instruction=""):
    """Use rank -1 model to compact/summarize text. Pure text, no tools."""
    pick = pam.select(-1, usage=_usage)
    if not pick:
        return text  # no rank -1 available, return as-is
    model = pick["name"]
    try:
        client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
        prompt = f"Compact this text concisely. Keep key facts, remove fluff.\n"
        if instruction:
            prompt += f"Focus on: {instruction}\n"
        prompt += f"\n---\n{text[:8000]}"
        resp = client.chat.completions.create(
            model=model, max_tokens=2000,
            messages=[{"role": "user", "content": prompt}])
        with _usage_lock:
            _usage[model] = _usage.get(model, 0) + 1
        result = resp.choices[0].message.content.strip()
        _cam("api_request", caller="compact", model=model,
             response=result[:300], **_response_meta(resp))
        return result
    except Exception:
        return text  # fallback: return original


def _prepare_bash(command, task_dir):
    """Wrap command with env.sh sourcing if the file exists in task_dir.

    Source by absolute path so the env activates even when the command does
    `cd subdir && ...` before any env lookup — relative `. ./env.sh` would
    miss if the script internally changes cwd and then looks up binaries.
    """
    env_sh = os.path.join(task_dir, "env.sh")
    if os.path.isfile(env_sh):
        return f'. "{os.path.abspath(env_sh)}" && {command}'
    return command


def _execute_tool_readonly(name, args, task_dir):
    try:
        if name == "bash":
            r = subprocess.run(_prepare_bash(args["command"], task_dir),
                shell=True, capture_output=True,
                text=True, timeout=min(60, MAX_BASH_TIME), cwd=task_dir)
            out = (r.stdout + r.stderr).strip()
            return _truncate(out) if out else "(no output)"
        elif name == "read_file":
            return _read_file_impl(args, task_dir)
        elif name == "memory_read":
            mem = _read_memory(task_dir)
            return _truncate(mem) if mem else "(empty)"
        elif name == "compact":
            return _compact_text(args.get("text", ""), args.get("instruction", ""))
        else:
            return f"ERROR: unknown tool '{name}'"
    except Exception as e:
        return f"ERROR: {e}"


def _execute_tool_reflect(name, args, task_dir):
    if name == "memory_write":
        try:
            with _get_mem_lock(task_dir):
                with open(os.path.join(task_dir, ".memory.md"), "w") as f:
                    f.write(args["content"])
            return "OK"
        except Exception as e:
            return f"ERROR: {e}"
    return _execute_tool_readonly(name, args, task_dir)


def _execute_tool(name, args, task_dir, node, scheduler):
    """Worker tool dispatch. Handles subagent via scheduler."""
    try:
        if name == "bash":
            # Agent suggests timeout, capped by task's bash_time (-1 = no cap)
            bt = getattr(node, 'bash_time', MAX_BASH_TIME)
            # When BashTime: -1, default to 600s (not 30s) so package installs
            # and training runs don't get killed when agent forgets timeout.
            default_t = 600 if bt == -1 else 30
            agent_t = int(args.get("timeout", default_t) or default_t)
            timeout = agent_t if bt == -1 else min(agent_t, bt)
            r = subprocess.run(_prepare_bash(args["command"], task_dir),
                shell=True, capture_output=True,
                text=True, timeout=timeout, cwd=task_dir)
            out = (r.stdout + r.stderr).strip()
            return _truncate(out) if out else "(no output)"
        elif name == "read_file":
            return _read_file_impl(args, task_dir)
        elif name == "write_file":
            if "path" not in args:
                return ("ERROR: write_file requires both 'path' and 'content' arguments. "
                        "You provided 'content' but forgot 'path'. "
                        "Call write_file again with {\"path\": \"filename.py\", \"content\": \"...\"}.")
            p = args["path"]
            path = p if os.path.isabs(p) else os.path.join(task_dir, p)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(args["content"])
            return "OK"
        elif name == "edit_file":
            p = args["path"]
            path = p if os.path.isabs(p) else os.path.join(task_dir, p)
            with open(path) as f:
                content = f.read()
            old = args["old_string"]
            count = content.count(old)
            if count == 0:
                return f"ERROR: old_string not found in {p}"
            if count > 1:
                return f"ERROR: old_string matches {count} times in {p} (must be unique)"
            new_content = content.replace(old, args["new_string"], 1)
            with open(path, "w") as f:
                f.write(new_content)
            # Show lines around the edit so agent can spot side effects
            pos = new_content.find(args["new_string"])
            line_start = new_content[:pos].count('\n')
            all_lines = new_content.split('\n')
            a = max(0, line_start - 2)
            b = min(len(all_lines), line_start + args["new_string"].count('\n') + 3)
            ctx = '\n'.join(f"{a+i+1:4d}| {all_lines[a+i]}" for i in range(b - a))
            return f"OK\n{ctx}"
        elif name == "web_fetch":
            req = urllib.request.Request(args["url"], headers={"User-Agent": "driver/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode(errors="replace")[:10000]
        elif name == "memory_read":
            mem = _read_memory(task_dir)
            return _truncate(mem) if mem else "(empty)"
        elif name == "memory_write":
            with _get_mem_lock(task_dir):
                with open(os.path.join(task_dir, ".memory.md"), "w") as f:
                    f.write(args["content"])
            return "OK"
        elif name == "subagent":
            if node.depth >= MAX_DEPTH:
                return f"ERROR: max depth ({MAX_DEPTH}) reached"
            tf = args["task_file"]
            # Look up prescan plan for this subtask
            plan_entry = next((s for s in scheduler.plan.get("subtasks", [])
                              if s.get("file") == tf), None)
            if plan_entry:
                r = int(plan_entry.get("rank", 1))
                # yaml-order selection (no shuffle) — deterministic first pick.
                # Retry rotation happens via exclude_model in the recovery path.
                # The subtask's own prescan will override via force_model if set.
                model = pam.select(r, usage=_usage)["name"]
                ctx = scheduler.plan.get("context", {}).get(tf, "")
            else:
                r = node.rank
                model = node.model
                ctx = ""
            return scheduler.launch_blocking(task_dir, tf, model, r, ctx)
        elif name in _skills:
            return _skills[name]["execute"](args, task_dir)
        else:
            return f"ERROR: unknown tool '{name}'"
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# GENERIC AGENT LOOP (review, reflection)
# ============================================================

def _run_agent_loop(system, tools, execute_fn, task_dir, user_msg,
                    max_iter, terminal_tool, model, label, depth=0,
                    capture_messages=None):
    """Run until terminal_tool or max_iter. Returns args dict or None.

    capture_messages: optional list; if provided and the loop ends without a
        verdict, the full message history is copied into it (used by review
        lateral retry to extract raw tool observations for handoff).
    """
    client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]
    for i in range(max_iter):
        try:
            response = _api_call(client, model, messages, tools)
        except Exception as e:
            _history(task_dir, f"{label}_API_ERROR", depth, error=str(e))
            if capture_messages is not None:
                capture_messages.extend(messages)
            return None
        msg = response.choices[0].message
        # Sanitize malformed tool calls (same as worker loop)
        if msg.tool_calls:
            valid_names = {t["function"]["name"] for t in tools}
            bad = [tc for tc in msg.tool_calls if tc.function.name not in valid_names]
            if bad:
                messages.append({"role": "user",
                    "content": f"Malformed tool call. Use only: {', '.join(valid_names)}"})
                continue
        messages.append(msg)
        if not msg.tool_calls:
            messages.append({"role": "user", "content":
                f"You must call {terminal_tool} or use a tool."})
            continue
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                messages.append({"role": "tool", "tool_call_id": tc.id,
                    "content": "ERROR: malformed JSON."})
                continue
            if tc.function.name == terminal_tool:
                return args
            result = execute_fn(tc.function.name, args, task_dir)
            messages.append({"role": "tool", "tool_call_id": tc.id,
                "content": str(result)})

    # Fix C: iter cap reached without a verdict. Rather than throwing away
    # everything the agent observed, make ONE final forced call: terminal
    # tool only, explicit instruction to commit now based on current
    # observations. Extracts partial work instead of discarding it.
    try:
        terminal_only = [t for t in tools
                         if t.get("function", {}).get("name") == terminal_tool]
        if terminal_only:
            messages_fc = list(messages) + [{"role": "user", "content":
                f"You have reached the iteration budget. Based on everything "
                f"you have observed so far, commit your verdict NOW by calling "
                f"`{terminal_tool}`. No other tools are permitted. If you are "
                f"not fully certain, call {terminal_tool} with your best "
                f"current judgment and state your uncertainty in the reason."}]
            _history(task_dir, f"{label}_FORCE_COMMIT", depth)
            response = _api_call(client, model, messages_fc, terminal_only)
            fc_msg = response.choices[0].message
            if fc_msg.tool_calls:
                for tc in fc_msg.tool_calls:
                    if tc.function.name == terminal_tool:
                        try:
                            args = json.loads(tc.function.arguments)
                            _history(task_dir, f"{label}_FORCE_COMMIT_OK",
                                     depth, result=str(args)[:200])
                            return args
                        except json.JSONDecodeError:
                            continue
    except Exception as e:
        _history(task_dir, f"{label}_FORCE_COMMIT_ERROR", depth,
                 error=str(e)[:200])

    # All attempts (loop + force-commit) failed to produce a verdict.
    if capture_messages is not None:
        capture_messages.extend(messages)
    return None


# ============================================================
# REVIEW (replaces verify_sam — handles done + failure triage)
# ============================================================

def _review_fallback(task_dir, case, user_msg, terminal, depth, force_model=None):
    """Rank -2 fallback for review when highest model fails.
    No tools — pure text reasoning on the provided context."""
    if force_model:
        model = force_model
    else:
        pick = pam.select(-2, usage=_usage)
        if not pick:
            return None
        model = pick["name"]
    _history(task_dir, "REVIEW_FALLBACK", depth, model=model, case=case)
    print(f"{'  ' * depth}[review fallback] trying {model} (no tools)...",
          flush=True)
    try:
        client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
        if terminal == "verdict":
            # Fix A': strict anti-fabrication text-only gate. This is the
            # last-resort reviewer with no tools — it can only read text.
            # Apply rules that block common fabrication patterns.
            prompt = (
                "You are the LAST-LINE review agent. All tool-capable reviewers "
                "failed to commit a verdict. You have NO tools — only the "
                "worker's summary text and the task's Expect criteria.\n\n"
                "Because you cannot independently verify ground truth, apply "
                "STRICT textual rules. False positives are catastrophic "
                "(shipping broken work with a fake PASS). False negatives only "
                "cost one retry. WHEN IN DOUBT, REJECT.\n\n"
                "RULES:\n"
                "1. For EACH Expect item, the summary must contain UNAMBIGUOUS, "
                "CONCRETE evidence that it is satisfied. Concrete means: "
                "explicit file names, quoted actual command output, verbatim "
                "test result strings. Vague claims like 'implementation "
                "complete' or 'all requirements met' are NOT evidence.\n\n"
                "2. REJECT immediately if the summary contains ANY of these "
                "red flags:\n"
                "   - Admission of partial failure: 'some issues', 'mostly "
                "works', 'appears to be a flaw', 'output counting issues', "
                "'not quite right', 'only N outputs instead of M'\n"
                "   - Hedging language: 'should work', 'supposed to', 'in "
                "theory', 'I believe', 'probably', 'would'\n"
                "   - Description of code logic without evidence of actual "
                "execution ('I implemented X' instead of 'I ran X and got Y')\n"
                "   - Claims about logs/tests without the actual output quoted\n"
                "   - Any mention of verification not completing or failing\n"
                "   - Contradiction between overall PASS claim and any "
                "mentioned problem\n"
                "   - Reinterpretation of failure as 'escape state', 'known "
                "issue', 'documented failure mode', or 'acceptable flaw'\n\n"
                "3. APPROVE ONLY when the summary is specific, concrete, and "
                "every Expect criterion is directly addressed with quoted "
                "evidence of success.\n\n"
                "4. Tie-breaker: less than certain = REJECT.\n\n"
                f"---\n{user_msg}\n---\n\n"
                'Reply with strict JSON: {"passed": true/false, '
                '"observations": "For each Expect item, quote the specific '
                'evidence or note its absence.", '
                '"reason": "Which rule applied and why."}')
        else:
            # Failed-case (routing decision) is a judgment call, not ground
            # truth — fallback text reasoning is appropriate here.
            prompt = (
                f"You are a review agent deciding recovery for a failed SAM "
                f"loop. Based ONLY on the information below, reply with valid "
                f"JSON.\n\n{user_msg}\n\n"
                'Reply: {"action": "delay"|"retry"|"reflect", '
                '"reason": "..."}')
        resp = client.chat.completions.create(
            model=model, max_tokens=1000,
            messages=[{"role": "user", "content": prompt}])
        with _usage_lock:
            _usage[model] = _usage.get(model, 0) + 1
        raw = resp.choices[0].message.content.strip()
        _cam("api_request", caller="review_fallback", model=model,
             prompt=prompt, response=raw, **_response_meta(resp))
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            args = json.loads(json_match.group())
            _history(task_dir, "REVIEW_FALLBACK_OK", depth, result=str(args)[:300])
            return args
    except Exception as e:
        _history(task_dir, "REVIEW_FALLBACK_ERROR", depth, error=str(e)[:200])
    return None

def _ensure_env_sh(task_dir):
    """If worker created a local env but didn't write env.sh, auto-generate it.
    This ensures the reviewer's bash calls find the worker's packages."""
    env_sh = os.path.join(task_dir, "env.sh")
    if os.path.exists(env_sh):
        return  # worker already wrote one
    # Search for local micromamba envs
    for prefix_dir in ("env", "mamba_env", ".env"):
        envs_dir = os.path.join(task_dir, prefix_dir, "envs")
        if os.path.isdir(envs_dir):
            env_names = [d for d in os.listdir(envs_dir)
                        if os.path.isdir(os.path.join(envs_dir, d))]
            if env_names:
                env_name = env_names[0]
                bin_dir = os.path.join(envs_dir, env_name, "bin")
                if os.path.isdir(bin_dir):
                    abs_bin = os.path.abspath(bin_dir)
                    abs_lib = os.path.abspath(os.path.join(envs_dir, env_name, "lib"))
                    with open(env_sh, "w") as f:
                        f.write(f'export PATH="{abs_bin}:$PATH"\n')
                        f.write(f'export LD_LIBRARY_PATH="{abs_lib}:${{LD_LIBRARY_PATH:-}}"\n')
                    return


def review_sam(task_dir, node, scheduler, case, expect_section="",
              summary="", depth=0, control_model=None):
    """case='done': verify expectations. case='failed': decide recovery.
    Pauses siblings before reviewing. Uses control_model if set, else highest."""
    prefix = "  " * depth
    model = _resolve_control_model(control_model)

    # Auto-generate env.sh if worker created local env but forgot to write it.
    # This ensures the reviewer's bash calls find the worker's packages.
    if case == "done":
        _ensure_env_sh(task_dir)

    # Pause siblings for consistent review
    paused = scheduler.pause_siblings(exclude=node)
    _history(task_dir, "REVIEW_START", depth,
        case=case, model=model, paused=len(paused))
    print(f"{prefix}[review] {case} with {model} "
          f"(paused {len(paused)} siblings)...", flush=True)

    try:
        if case == "done":
            user_msg = (
                f"Worker claims done.\nSummary: {summary}\n\n---\n"
                f"EXPECTATIONS TO VERIFY:\n{expect_section}\n\n---\n"
                f"Check each by inspecting actual state. Call `verdict`.")
            terminal = "verdict"
        else:
            mem = _read_memory(task_dir)
            # Read tail of history for context
            hf_path = os.path.join(task_dir, ".history.md")
            history_tail = ""
            if os.path.exists(hf_path):
                with open(hf_path) as f:
                    lines = f.readlines()
                    history_tail = "".join(lines[-80:])
            thinkable = pam.is_thinkable(node.model)
            thinking_status = (f"thinking={'ON' if node.thinking else 'OFF'}"
                f" (budget={node.thinking_budget})" if thinkable
                else "thinking=not supported by this model")
            bash_note = ""
            if getattr(node, 'bash_time', 0) == -1:
                bash_note = ("\n[BASH-TIME UNLIMITED] This task has BashTime: -1. "
                    "The bash tool defaults to timeout=30s which kills long operations. "
                    "Workers should use timeout=86400 for any workload command. "
                    "Check whether the worker hit 30s timeouts and suggest using "
                    "large timeouts in your feedback.\n")
            user_msg = (
                f"Worker hit MAX_ITERATIONS.\n\n"
                f"Task: {node.task_file}\n"
                f"Current rank: {node.rank}, model: {node.model}\n"
                f"{thinking_status}{bash_note}\n"
                f"Memory:\n{mem[:2000]}\n\n"
                f"Recent history:\n{history_tail[:3000]}\n\n"
                f"Decide: delay, retry, or reflect.\n"
                f"If retrying: set exclude_model=true if model did poorly "
                f"but task rank is correct. Set suggested_rank if task needs "
                f"stronger model. Set enable_thinking + thinking_budget for "
                f"complex reasoning. Call `decision`.")
            terminal = "decision"

        # If control model is a no-tool model (rank < 0), skip tool-based review
        # and go straight to text-only fallback
        model_cfg = pam.config(model)
        if model_cfg.get("rank", 0) < 0:
            args = _review_fallback(task_dir, case, user_msg, terminal, depth,
                                    force_model=model)
        else:
            review_prompt = REVIEW_SYSTEM_SIMPLE if node.rank <= 0 else REVIEW_SYSTEM
            # Adaptive iter budget: done-case reviews whose Expect references
            # verification-like artifacts burn iters re-running build/test
            # commands — give them more room so they don't drop to fallback.
            iter_cap = MAX_REVIEW_ITER
            if case == "done" and expect_section:
                low = expect_section.lower()
                if any(k in low for k in ("verify", "test", "pass",
                        "contain", "log", "compile", "build", "output")):
                    iter_cap = max(MAX_REVIEW_ITER, MAX_REVIEW_ITER_VERIFY)
            # Capture primary's message history so a lateral reviewer (Fix D)
            # can inherit raw observations if the primary fails to commit.
            primary_messages = []
            args = _run_agent_loop(
                review_prompt, REVIEW_TOOLS, _execute_tool_readonly,
                task_dir, user_msg, iter_cap, terminal, model,
                "REVIEW", depth, capture_messages=primary_messages)

            # Fix D: lateral control-model rotation. If the primary reviewer
            # (including its force-commit final call, Fix C) could not commit
            # a verdict, try ONE other tool-capable reviewer at the same rank
            # before dropping to the no-tool fallback. Preserves ground-truth
            # verification capability when a specific model has a bad run.
            # Prior tool outputs are shared as reference-only observations —
            # interpretation is stripped to avoid anchoring bias.
            if args is None:
                primary_rank = model_cfg.get("rank", 0)
                lateral_pick = pam.select(primary_rank, exclude=model,
                                          usage=_usage)
                if lateral_pick and lateral_pick["name"] != model:
                    lateral_model = lateral_pick["name"]
                    _history(task_dir, "REVIEW_LATERAL", depth,
                             primary=model, lateral=lateral_model)
                    print(f"{prefix}[review lateral] {model}→{lateral_model} "
                          f"(same rank, with prior observations)", flush=True)
                    prior_log = _format_prior_investigation(primary_messages)
                    lateral_user_msg = user_msg
                    if prior_log:
                        lateral_user_msg = user_msg + "\n\n---\n" + prior_log
                    args = _run_agent_loop(
                        review_prompt, REVIEW_TOOLS, _execute_tool_readonly,
                        task_dir, lateral_user_msg, iter_cap, terminal,
                        lateral_model, "REVIEW_LATERAL", depth)

        if args is None:
            # Final fallback: rank -2 text-only reasoning model.
            # For done-case this path now applies strict anti-fabrication
            # rules (Fix A') — it can approve unambiguous wins but rejects
            # any claim with admission language, hedging, or missing evidence.
            args = _review_fallback(task_dir, case, user_msg, terminal, depth)

        if args is None:
            _history(task_dir, "REVIEW_TIMEOUT", depth, case=case)
            if case == "done":
                return {"verdict": False, "feedback": "Review timed out"}
            return {"action": "reflect", "reason": "Review timed out"}

        if case == "done":
            passed = args.get("passed", False)
            observations = args.get("observations", "")
            reason = args.get("reason", "")
            status = "PASS" if passed else "FAIL"
            feedback = f"Observations: {observations}\nReason: {reason}"
            _history(task_dir, f"REVIEW_VERDICT_{status}", depth,
                observations=observations, reason=reason)
            print(f"{prefix}[review] {status}: {reason}", flush=True)
            return {"verdict": passed, "feedback": feedback}
        else:
            action = args.get("action", "reflect")
            _history(task_dir, "REVIEW_DECISION", depth,
                action=action, reason=args.get("reason", ""),
                wait=args.get("wait_seconds", ""),
                suggested_rank=args.get("suggested_rank", ""),
                current_rank=node.rank, current_model=node.model,
                memory_update=str(args.get("memory_update", ""))[:200])
            print(f"{prefix}[review] decision: {action}", flush=True)
            return args
    finally:
        scheduler.resume_siblings(paused)


# ============================================================
# REFLECTION
# ============================================================

def reflect_sam(task_dir, task_file, exit_reason, depth=0, control_model=None):
    prefix = "  " * depth
    model = _resolve_control_model(control_model)
    _history(task_dir, "REFLECT_START", depth, model=model, reason=exit_reason)
    print(f"{prefix}[reflect] diagnosing with {model}...", flush=True)

    args = _run_agent_loop(
        REFLECT_SYSTEM, REFLECT_TOOLS, _execute_tool_reflect, task_dir,
        f"SAM `{task_file}` failed.\nReason: {exit_reason}\n\n"
        f"Files: .history.md, .memory.md, {task_file}, {DRIVER_PATH}\n\n"
        f"Diagnose, update memory, call `diagnosis`.",
        MAX_REFLECT_ITER, "diagnosis", model, "REFLECT", depth)

    if args is None:
        _history(task_dir, "REFLECT_TIMEOUT", depth)
        return {"cause": "other", "evidence": "Reflection timed out",
                "suggestion": "Manually inspect .history.md"}

    cause, evidence, suggestion = (args.get("cause", "other"),
        args.get("evidence", ""), args.get("suggestion", ""))
    _history(task_dir, "REFLECT_DIAGNOSIS", depth,
        cause=cause, evidence=evidence, suggestion=suggestion)
    print(f"{prefix}[reflect] cause={cause}: {suggestion}", flush=True)
    return {"cause": cause, "evidence": evidence, "suggestion": suggestion}


# ============================================================
# CORE SAM LOOP
# ============================================================

def _run_sam(node, context=None, wall_limit=None, plan=None, control_model=None):
    """Run a SAM on an AgentNode. Model is fixed. Supports pause/resume."""
    task_dir = node.task_dir
    task_file = node.task_file
    model = node.model
    depth = node.depth
    prefix = "  " * depth

    task_path = os.path.join(task_dir, task_file)
    with open(task_path) as f:
        task_content = f.read()
    try:
        parsed = parse_task(task_content)
        expect_section = parsed["expect"]
    except TaskFormatError:
        parsed = None
        expect_section = _extract_expect(task_content)  # fallback for malformed

    # Prescan for subtask planning (skip if already provided)
    memory = _read_memory(task_dir)
    global_memory = _read_global_memory()
    task_group = None
    taskgroup_memory = ""
    if plan is None:
        plan = prescan(task_content, task_dir, memory, global_memory)
    task_group = plan.get("task_group")
    if task_group:
        taskgroup_memory = _read_taskgroup_memory(task_group)

    # NoMemory: don't inject prior global experience into this task's context.
    # TaskGroup memory is independent — explicitly opt-in via TaskGroup: field.
    if plan.get("no_memory"):
        global_memory = ""

    # Per-task LLM wall limit: ThinkTime > Timeout > parent ThinkTime > rank default.
    # ThinkTime: -1 = no LLM time limit.
    think_time = plan.get("think_time")
    if think_time is None:
        think_time = getattr(node.parent, 'think_time', None) if node.parent else None
    node.think_time = think_time
    if wall_limit is None:
        if think_time is not None:
            wall_limit = None if think_time == -1 else think_time
        else:
            wall_limit = plan.get("wall_limit") or None

    # Per-task bash time: -1 = no limit, else cap
    node.bash_time = plan.get("bash_time", MAX_BASH_TIME)

    # Sticky force_model: declared in task metadata, must survive retry
    # (so retry stays on the user-pinned model instead of falling back via PAM).
    # Also override node.model if it was pre-selected by the subagent dispatcher
    # before this subtask's own prescan was known — subtask metadata wins.
    if plan.get("force_model"):
        fm = plan["force_model"]
        if not getattr(node, 'force_model', None):
            node.force_model = fm
        if node.model != fm:
            node.model = fm
            model = fm
    # If the subtask's declared rank differs from what was dispatched (e.g. the
    # parent's prescan LLM over-estimated the subtask difficulty), re-select the
    # model based on the subtask's self-declared rank. Only on the INITIAL
    # invocation — on retries (recovery_count > 0) the review-driven rank
    # escalation must stick, so we leave node.rank alone.
    elif (getattr(node, '_recovery_count', 0) == 0
          and plan.get("rank") is not None
          and int(plan["rank"]) != node.rank):
        node.rank = int(plan["rank"])
        new_model = pam.select(node.rank, usage=_usage)["name"]
        if new_model != node.model:
            node.model = new_model
            model = new_model

    # Similarly, if the subtask declares its own ControlModel, use it.
    # Priority: plan (subtask file) > caller-provided control_model > default.
    if plan.get("control_model"):
        control_model = plan["control_model"]

    # Build tool list + context from prescan-selected skills
    selected_skills = plan.get("skills", [])
    task_tools = list(TOOLS)
    skill_context = []
    env_skill_loaded = False
    for sk in selected_skills:
        if sk not in _skills:
            continue
        s = _skills[sk]
        if s["type"] == "tool":
            task_tools.append(s["tool"])
        elif s["type"] == "context":
            skill_context.append(f"---\nSkill: {sk}\n{s['content'][:CAP_TASK]}")
        if sk in _ENV_SKILLS:
            env_skill_loaded = True
    if not env_skill_loaded:
        skill_context.append(_ENV_FALLBACK_PROMPT)

    _history(task_dir, "PRESCAN", depth,
        rank=plan["rank"], subtasks=len(plan.get("subtasks", [])),
        skills=selected_skills or "none",
        source=plan.get("source", ""),
        wall_limit=wall_limit or "none")

    scheduler = Scheduler(node, plan)

    # Build initial context: structured sections → skills → global → memory
    if parsed:
        agent_meta = public_meta(parsed["meta"])
        meta_block = "\n".join(f"{k}: {v}" for k, v in agent_meta.items())
        sections = []
        if parsed["title"]:
            sections.append(f"# {parsed['title']}")
        if meta_block:
            sections.append(meta_block)
        if parsed["context"]:
            sections.append(f"## Context\n{parsed['context']}")
        sections.append(f"## Todo\n{parsed['todo']}")
        sections.append(f"## Expect\n{parsed['expect']}")
        user_msg = "\n\n".join(sections)[:CAP_TASK]
    else:
        user_msg = task_content[:CAP_TASK]
    if skill_context:
        user_msg += "\n\n" + "\n".join(skill_context)
    if context:
        user_msg += f"\n\n{context[:CAP_GLOBAL]}"
    if global_memory:
        user_msg += f"\n\n---\nGlobal Experience (truncated, use read_file for full):\n{global_memory[:CAP_GLOBAL]}"
    if memory:
        user_msg += f"\n\n---\nPersistent Memory (truncated, use memory_read for full):\n{memory[:CAP_MEMORY]}"
    if taskgroup_memory:
        user_msg += (f"\n\n---\nTaskGroup Experience ({task_group}) — "
                     f"cross-task domain memory:\n{taskgroup_memory[:CAP_TASKGROUP]}")

    # Review feedback from prior attempts on this same subtask (if any).
    # Always injected, independent of NoMemory (this is run-scoped, not
    # cross-task). The review agent writes specific, actionable hints here
    # when rejecting a done claim or routing a failed-loop retry.
    feedback = _read_feedback(task_dir, task_file)
    if feedback:
        user_msg += (
            f"\n\n---\n[REVIEW FEEDBACK FROM PRIOR ATTEMPTS ON THIS SUBTASK]\n"
            f"The independent reviewer rejected or routed previous attempts with "
            f"the following concrete observations and hints. Read them carefully "
            f"and act on them — do not repeat the same mistakes.\n\n"
            f"{feedback[:CAP_MEMORY]}")

    # Iteration cap is global (rank no longer scales it); per-rank total wall stays.
    max_iter = MAX_ITER
    total_wall = _total_wall_for_rank(plan["rank"])

    # BashTime: -1 means the user explicitly opts in to long bash calls.
    # Disable total wall (no hard cut).
    if node.bash_time == -1:
        total_wall = 0  # disabled

    # --- Soft environment hints ---
    # Metadata controls the outer system (hard). These hints tell the agent
    # what the outer system configured, so it can make informed decisions.
    # Read from parsed metadata (not regex on raw text).
    _meta = parsed["meta"] if parsed else {}
    _hints = []
    if node.bash_time == -1:
        _hints.append(
            "BashTime: unlimited — for any workload command (training, installs, "
            "downloads, generation, builds), set timeout to a very large value: "
            "{\"command\": \"...\", \"timeout\": 86400}. The default is only 30s "
            "and WILL kill your process. Only use short/no timeout for trivial "
            "commands (ls, cat, grep, echo).")
    _gpu_v = _meta.get("GPU", "")
    if _gpu_v:
        gv = _gpu_v
        gvl = gv.lower()
        if gvl in ("local", "all") or gvl.isdigit():
            _hints.append(
                "GPU: %s — GPU(s) are pinned and available on this node "
                "via CUDA_VISIBLE_DEVICES." % gv)
        elif gv == "ALL":
            _hints.append(
                "GPU: ALL — all physical GPUs exposed (debug mode).")
        elif gvl == "slurm":
            _hints.append(
                "GPU: slurm — for real workload, prefer submitting GPU jobs "
                "via SLURM (sbatch). A local GPU may be available for testing.")
        elif gvl == "on":
            _hints.append(
                "GPU: on — check nvidia-smi to see if a GPU is available "
                "locally; if not, submit via SLURM.")
    _slurm_v = _meta.get("Slurm", "").lower()
    if _slurm_v == "on":
        # Only hint Slurm separately when it's not already implied by GPU: slurm
        if _gpu_v.lower() != "slurm":
            _hints.append(
                "Slurm: on — SLURM job submission (sbatch, squeue, scancel) "
                "is enabled for this task.")
    _cs_v = _meta.get("CommonStorage", "").lower()
    _skills_v = _meta.get("Skills", "")
    _has_env_skill = "env" in _skills_v.lower() if _skills_v else False
    if _cs_v == "rw":
        if _has_env_skill:
            _hints.append(
                "CommonStorage: rw — /mnt is writable. Check /mnt/sci_envs/ "
                "for existing shared environments before creating new ones.")
        else:
            _hints.append(
                "CommonStorage: rw — /mnt is writable and shared across tasks.")
    elif _cs_v == "ro":
        _hints.append(
            "CommonStorage: ro — /mnt is read-only.")
    if _hints:
        user_msg += "\n\n---\n[ENVIRONMENT HINTS]\n" + "\n".join(
            f"- {h}" for h in _hints)

    node.state = "running"
    _history(task_dir, "SAM_START", depth,
        task_file=task_file, model=model, rank=plan["rank"],
        thinking=node.thinking, thinking_budget=node.thinking_budget,
        wall_limit=wall_limit or "none", total_wall=total_wall or "none",
        max_iter=max_iter, has_expect=bool(expect_section))
    print(f"{prefix}[start] {task_file} rank={plan['rank']} model={model} "
          f"max_iter={max_iter} total_wall={total_wall}s",
          flush=True)

    client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
    has_subtasks = bool(plan.get("subtasks"))
    system_prompt = _build_system_prompt(_meta, has_subtasks)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    review_failures = 0
    consecutive_nudges = 0   # detect models that can't use tools
    consecutive_errors = 0   # detect models with persistent API errors
    wall_start = time.time()
    excluded_time = 0.0  # subagent + tool time (excluded from wall limit)
    READONLY_TOOLS = {"read_file", "memory_read", "compact"}

    effective_iter = 0  # only counts iterations with mutating tool calls
    total_iter = 0      # counts all iterations (for logging)
    while effective_iter < max_iter:
        # --- PAUSE CHECK ---
        node.check_pause()

        # --- LLM-ONLY WALL LIMIT ---
        if wall_limit and (time.time() - wall_start - excluded_time) > wall_limit:
            _history(task_dir, "WALL_LIMIT", depth, own_time=time.time()-wall_start-excluded_time)
            print(f"{prefix}[wall limit] exceeded", flush=True)
            break

        # --- TOTAL WALL LIMIT (including bash/tool time) ---
        if total_wall and (time.time() - wall_start) > total_wall:
            _history(task_dir, "TOTAL_WALL_LIMIT", depth,
                total_time=time.time()-wall_start, limit=total_wall)
            print(f"{prefix}[total wall limit] {time.time()-wall_start:.0f}s > {total_wall}s",
                  flush=True)
            break

        iter_start = time.time()
        total_iter += 1
        print(f"{prefix}[iter {effective_iter+1}/{max_iter} (total {total_iter})]", flush=True)
        _history(task_dir, "ITERATION", depth,
            n=f"{effective_iter+1}/{max_iter}", model=model,
            review_failures=review_failures, messages_len=len(messages),
            total_iter=total_iter,
            avg_iter_s=f"{(time.time()-wall_start)/total_iter:.1f}" if total_iter > 1 else "n/a")

        # Checkpoint (based on effective iterations)
        if effective_iter > 0 and effective_iter % CHECKPOINT_EVERY == 0:
            memory = _read_memory(task_dir)
            messages.append({"role": "user",
                "content": _checkpoint_msg(task_content, memory, effective_iter+1, max_iter,
                    wall_used=time.time()-wall_start-excluded_time,
                    wall_limit=wall_limit)})
            _history(task_dir, "CHECKPOINT", depth)
            print(f"{prefix}  [checkpoint]", flush=True)

        messages = _trim_messages(messages)

        # API call
        try:
            response = _api_call(client, model, messages, task_tools,
                thinking=node.thinking, thinking_budget=node.thinking_budget)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            _history(task_dir, "API_ERROR", depth,
                error=str(e)[:200], consecutive=consecutive_errors)
            print(f"{prefix}  [error] API: {str(e)[:100]}", flush=True)
            if consecutive_errors >= ERROR_LIMIT:
                _history(task_dir, "ERROR_LIMIT", depth,
                    reason=f"{ERROR_LIMIT} consecutive API errors")
                print(f"{prefix}[error limit] model has persistent API failures",
                      flush=True)
                pam.blacklist_model(model)
                break  # go to review for rank escalation
            messages.append({"role": "user",
                "content": f"API failed: {e}. Continue."})
            continue

        msg = response.choices[0].message

        # Sanitize malformed tool calls before appending to history.
        # Some models (e.g. kimi-k2 via Bedrock) occasionally emit tool calls
        # with corrupted names. If appended as-is, they poison the conversation
        # and cause unrecoverable 400 errors on every subsequent API call.
        if msg.tool_calls:
            valid_names = {t["function"]["name"] for t in task_tools}
            bad = [tc for tc in msg.tool_calls if tc.function.name not in valid_names]
            if bad:
                bad_names = [tc.function.name[:60] for tc in bad]
                _history(task_dir, "MALFORMED_TOOL_CALL", depth, bad_names=bad_names)
                print(f"{prefix}  [malformed tool call] {bad_names}", flush=True)
                # Drop the entire response — don't append corrupted message
                messages.append({"role": "user",
                    "content": "Your last response had a malformed tool call "
                    f"(invalid name: {bad_names[0][:40]}). Use only the provided "
                    "tools. Try again."})
                consecutive_nudges += 1
                if consecutive_nudges >= NUDGE_LIMIT:
                    _history(task_dir, "NUDGE_LIMIT", depth,
                        reason="model emits malformed tool calls")
                    print(f"{prefix}[nudge limit] model emits malformed tool calls",
                          flush=True)
                    pam.blacklist_model(model)
                    break
                continue

        messages.append(msg)

        # Text-only — nudge (detect models that can't use tools)
        if not msg.tool_calls:
            consecutive_nudges += 1
            _history(task_dir, "NUDGE", depth, consecutive=consecutive_nudges)
            print(f"{prefix}[agent] {(msg.content or '')[:200]}", flush=True)
            if consecutive_nudges >= NUDGE_LIMIT:
                _history(task_dir, "NUDGE_LIMIT", depth,
                    reason=f"model cannot use tools after {NUDGE_LIMIT} consecutive nudges")
                print(f"{prefix}[nudge limit] model appears unable to use tools",
                      flush=True)
                pam.blacklist_model(model)
                break  # go to review for rank escalation
            messages.append({"role": "user",
                "content": "You must use a tool or call done. Keep working."})
            continue

        consecutive_nudges = 0  # reset on successful tool use
        # Process tool calls
        tool_calls = list(msg.tool_calls)
        iter_has_mutation = False  # track if this iteration has a mutating tool
        for idx, tc in enumerate(tool_calls):
            node.check_pause()  # pause check between tools

            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError as e:
                _history(task_dir, "JSON_ERROR", depth)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                    "content": f"ERROR: bad JSON: {e}. Try again."})
                continue

            print(f"{prefix}  [{tc.function.name}] {json.dumps(args)[:200]}",
                  flush=True)

            # --- DONE ---
            if tc.function.name == "done":
                iter_has_mutation = True
                summary = args.get("summary", "")
                _history(task_dir, "DONE_CLAIMED", depth, summary=summary)
                print(f"{prefix}[done] {summary}", flush=True)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                    "content": "done acknowledged"})

                # Add stub results for remaining sibling tool calls
                # (API requires every tool_use to have a tool_result)
                for sibling in tool_calls[idx + 1:]:
                    messages.append({"role": "tool",
                        "tool_call_id": sibling.id,
                        "content": "skipped (done was called)"})

                if expect_section:
                    t0 = time.time()
                    rv = review_sam(task_dir, node, scheduler, "done",
                                   expect_section, summary, depth,
                                   control_model=control_model)
                    excluded_time += time.time() - t0
                    if rv["verdict"]:
                        _history(task_dir, "SAM_VERIFIED", depth)
                        # Success: clear any stale review feedback for this
                        # subtask so a later re-run sees a clean slate.
                        _clear_feedback(task_dir, task_file)
                        return summary
                    else:
                        review_failures += 1
                        _history(task_dir, "REVIEW_REJECTED", depth,
                            attempt=f"{review_failures}/{MAX_RETRIES}",
                            feedback=rv["feedback"])
                        print(f"{prefix}[rejected] {rv['feedback']}", flush=True)
                        # Persist the reviewer's concrete observations so any
                        # future retry of this subtask (including after loop
                        # exhaustion and full _run_sam restart) sees them.
                        _append_feedback(task_dir, task_file,
                            f"DONE-CLAIM REJECTED (attempt {review_failures}/{MAX_RETRIES})\n"
                            f"Worker summary: {summary[:500]}\n"
                            f"Reviewer findings:\n{rv['feedback']}")
                        if review_failures >= MAX_RETRIES:
                            _history(task_dir, "MAX_REVIEW_FAILURES", depth)
                            diag = reflect_sam(task_dir, task_file,
                                f"Review failed {MAX_RETRIES}x. Last: {rv['feedback']}",
                                depth, control_model=control_model)
                            return (f"UNVERIFIED: {summary}\n"
                                f"REFLECTION: [{diag['cause']}] {diag['suggestion']}")
                        messages.append({"role": "user",
                            "content": f"Review FAILED — your previous done claim was rejected "
                                f"by the INDEPENDENT reviewer, who ran its own tools to check:\n\n"
                                f"{rv['feedback']}\n\n"
                                f"Treat the reviewer's observations as ground truth. Do NOT "
                                f"fabricate logs or claim success without actually running the "
                                f"verification command yourself. Fix the real issue, re-run "
                                f"verification, and only then call done again with the real output."})
                        break
                else:
                    _history(task_dir, "SAM_DONE_NO_EXPECT", depth)
                    return summary

            # --- SUBAGENT (track time separately) ---
            elif tc.function.name == "subagent":
                iter_has_mutation = True
                _history(task_dir, "TOOL_CALL", depth, tool="subagent",
                    args=json.dumps(args)[:300])
                t0 = time.time()
                result = _execute_tool("subagent", args, task_dir, node, scheduler)
                excluded_time += time.time() - t0
                _history(task_dir, "TOOL_RESULT", depth, tool="subagent",
                    result=str(result)[:300])
                messages.append({"role": "tool", "tool_call_id": tc.id,
                    "content": str(result)})

            # --- OTHER TOOLS ---
            else:
                if tc.function.name not in READONLY_TOOLS:
                    iter_has_mutation = True
                _history(task_dir, "TOOL_CALL", depth,
                    tool=tc.function.name, args=json.dumps(args)[:300])
                t0 = time.time()
                result = _execute_tool(tc.function.name, args, task_dir,
                                      node, scheduler)
                excluded_time += time.time() - t0
                _history(task_dir, "TOOL_RESULT", depth,
                    tool=tc.function.name, result=str(result)[:300])
                messages.append({"role": "tool", "tool_call_id": tc.id,
                    "content": str(result)})

        # Only count this iteration against the budget if it had a mutating tool
        if iter_has_mutation:
            effective_iter += 1

    # --- MAX_ITERATIONS or WALL_LIMIT: review decides recovery ---
    _history(task_dir, "LOOP_EXHAUSTED", depth)
    rv = review_sam(task_dir, node, scheduler, "failed", depth=depth,
                    control_model=control_model)

    # MAX_RECOVERY (env-tunable, default 3): cap on delay/retry rounds after
    # LOOP_EXHAUSTED to prevent infinite recursion. See module-level definition.
    recovery_count = getattr(node, '_recovery_count', 0)

    if rv.get("action") == "delay" and recovery_count < MAX_RECOVERY:
        node._recovery_count = recovery_count + 1
        wait = rv.get("wait_seconds", 60)
        _history(task_dir, "DELAY_PAUSE", depth, wait=wait, reason=rv["reason"])
        print(f"{prefix}[delay] pausing {wait}s: {rv['reason']}", flush=True)
        node.pause()
        threading.Timer(wait, node.resume).start()
        node.check_pause()  # blocks until timer fires
        _history(task_dir, "DELAY_RESUME", depth)
        return _run_sam(node, context, wall_limit, control_model=control_model)

    elif rv.get("action") == "retry" and recovery_count < MAX_RECOVERY:
        node._recovery_count = recovery_count + 1
        if rv.get("memory_update"):
            with _get_mem_lock(task_dir):
                with open(os.path.join(task_dir, ".memory.md"), "a") as f:
                    f.write(f"\n\n---\nReview feedback:\n{rv['memory_update']}")
        # Also persist the hint as subtask-scoped review feedback so the
        # next _run_sam attempt injects it directly into the worker context.
        hint_text = rv.get("memory_update") or rv.get("reason", "")
        if hint_text:
            _append_feedback(task_dir, task_file,
                f"LOOP-EXHAUSTED RETRY (recovery {node._recovery_count}/{MAX_RECOVERY})\n"
                f"Reviewer reason: {rv.get('reason', '')}\n"
                f"Reviewer hints for next attempt:\n{hint_text}")
        # Model selection: escalate rank OR exclude current, not both.
        # Sticky force_model from task metadata overrides everything — if the
        # user pinned a model, retries stay on it (only thinking/iter changes).
        old_rank = node.rank
        old_model = node.model
        suggested_rank = rv.get("suggested_rank")
        fm = getattr(node, 'force_model', None)
        if fm:
            new_model = pam.select(node.rank, usage=_usage, force_model=fm)["name"]
        elif suggested_rank is not None:
            node.rank = int(suggested_rank)
            new_model = pam.select(node.rank, usage=_usage)["name"]
        elif rv.get("exclude_model"):
            new_model = pam.select(node.rank, exclude=old_model, usage=_usage)["name"]
        else:
            new_model = pam.select(node.rank, usage=_usage)["name"]
        if new_model != old_model:
            _history(task_dir, "MODEL_CHANGE", depth,
                old_rank=old_rank, new_rank=node.rank,
                old_model=old_model, new_model=new_model)
            print(f"{prefix}[model] {old_model}→{new_model} "
                  f"(rank {old_rank}→{node.rank})", flush=True)
        node.model = new_model
        # Thinking: apply review's suggestion if model supports it
        if rv.get("enable_thinking") and pam.is_thinkable(new_model):
            mc = pam.config(new_model)
            max_tb = mc.get("max_thinking_budget", 10000)
            node.thinking = True
            node.thinking_budget = min(int(rv.get("thinking_budget", 5000)), max_tb)
            _history(task_dir, "THINKING_ENABLED", depth,
                model=new_model, budget=node.thinking_budget, max=max_tb)
            print(f"{prefix}[thinking] enabled, budget={node.thinking_budget} "
                  f"(max={max_tb})", flush=True)
        elif not rv.get("enable_thinking"):
            node.thinking = False
            node.thinking_budget = 0
        _history(task_dir, "RETRY", depth, reason=rv["reason"],
            rank=node.rank, model=new_model)
        print(f"{prefix}[retry] {rv['reason']}", flush=True)
        return _run_sam(node, context, wall_limit, control_model=control_model)

    else:  # reflect (or recovery limit reached)
        # If review timed out, the control model may be too weak for review/reflect.
        # Escalate reflect to highest model to avoid double failure.
        reflect_cm = None if rv.get("reason") == "Review timed out" else control_model
        diag = reflect_sam(task_dir, task_file,
            f"Loop exhausted + review chose reflect: {rv['reason']}", depth,
            control_model=reflect_cm)
        memory = _read_memory(task_dir)
        return (f"MAX_ITERATIONS ({max_iter}) reached.\n"
            f"Memory: {memory[:300]}\n"
            f"REFLECTION: [{diag['cause']}] {diag['suggestion']}")


def run_sam(task_dir, task_file="top.md", depth=0):
    """Top-level entry. Creates root node, prescans once, runs SAM.
    Returns (result_string, final_rank, final_model)."""
    with open(os.path.join(task_dir, task_file)) as f:
        content = f.read()
    memory = _read_memory(task_dir)
    global_memory = _read_global_memory()
    plan = prescan(content, task_dir, memory, global_memory, task_file)
    fm = plan.get("force_model")
    cm = plan.get("control_model")
    model = pam.select(plan["rank"], usage=_usage, force_model=fm)["name"]

    root = AgentNode(
        agent_id=os.path.basename(task_dir),
        task_dir=task_dir, task_file=task_file,
        model=model, depth=depth, rank=plan["rank"],
        thinking=plan.get("thinking", False),
        thinking_budget=plan.get("thinking_budget", 0),
        force_model=fm)

    result = _run_sam(root, plan=plan, control_model=cm)
    return result, root.rank, root.model, cm, plan.get("no_memory", False), plan.get("task_group")


# ============================================================
# HISTORY INDEX (rank -1 model, cheap summarization)
# ============================================================

def index_history(task_dir):
    """Use rank -1 model to summarize .history.md into .history_index.md.
    Overwrites the index each time. Cheap, no tools, pure text."""
    hf = os.path.join(task_dir, ".history.md")
    if not os.path.exists(hf):
        return
    with open(hf) as f:
        history = f.read()
    if len(history) < 500:
        return  # too short to need an index

    # Use rank -1 (cheapest text model)
    pick = pam.select(-1, usage=_usage)
    if not pick:
        return
    model = pick["name"]

    # Read tail (most recent) + head (start context)
    head = history[:2000]
    tail = history[-3000:] if len(history) > 3000 else ""

    try:
        client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
        resp = client.chat.completions.create(
            model=model, max_tokens=1000,
            messages=[{"role": "user", "content":
                f"Summarize this task execution history into a concise outline.\n"
                f"Include: what was attempted, key events (successes, failures, "
                f"rank changes, review decisions), and final outcome.\n"
                f"Format as a bullet list. Be brief.\n\n"
                f"HISTORY START:\n{head}\n"
                f"{'...[middle omitted]...' if tail else ''}\n"
                f"{'HISTORY END:' + chr(10) + tail if tail else ''}"}],
        )
        with _usage_lock:
            _usage[model] = _usage.get(model, 0) + 1
        summary = resp.choices[0].message.content.strip()
        _cam("api_request", caller="index_history", model=model,
             response=summary, **_response_meta(resp))
        idx_path = os.path.join(task_dir, ".history_index.md")
        with open(idx_path, "w") as f:
            f.write(f"# History Index (auto-generated)\n\n{summary}\n")
        print(f"[index] history indexed ({len(history)} chars → {len(summary)} chars)",
              flush=True)
    except Exception as e:
        print(f"[index] failed: {e}", flush=True)


def final_review(task_dir, task_file, result, elapsed, iterations, final_rank, final_model,
                 control_model=None, task_group=None):
    """Post-task reflection: review task design + system feedback.
    Writes .suggestion.md, prints conclusion + task suggestions to user.
    Does NOT retry or re-run anything. Pure reflection."""
    # Gather context
    top_path = os.path.join(task_dir, task_file)
    idx_path = os.path.join(task_dir, ".history_index.md")
    mem_path = os.path.join(task_dir, ".memory.md")

    top_content = ""
    if os.path.exists(top_path):
        with open(top_path) as f:
            top_content = f.read()[:CAP_TASK]

    history_index = ""
    if os.path.exists(idx_path):
        with open(idx_path) as f:
            history_index = f.read()[:3000]

    memory = ""
    if os.path.exists(mem_path):
        with open(mem_path) as f:
            memory = f.read()[:CAP_MEMORY]

    success = not result.startswith(("MAX_ITERATIONS", "UNVERIFIED"))

    # Use control model if set, else highest (same as review — quality judgment)
    model = _resolve_control_model(control_model)

    # Per-task system stats: what limits applied + what actually happened.
    # Gives final_review factual context to write sharp System suggestions.
    max_iter_limit = MAX_ITER
    total_wall_limit = _total_wall_for_rank(final_rank)
    history_raw = ""
    hf = os.path.join(task_dir, ".history.md")
    if os.path.exists(hf):
        with open(hf) as f:
            history_raw = f.read()
    n_retry = history_raw.count("] RETRY**")
    n_model_change = history_raw.count("] MODEL_CHANGE**")
    n_review_rejected = history_raw.count("] REVIEW_REJECTED**")
    thinking_used = "] THINKING_ENABLED**" in history_raw
    wall_hit = "] WALL_LIMIT**" in history_raw      # leading `] ` avoids matching TOTAL_WALL_LIMIT
    total_wall_hit = "] TOTAL_WALL_LIMIT**" in history_raw
    nudge_limit_hit = "] NUDGE_LIMIT**" in history_raw

    prompt = (
        "You are the final reviewer for a completed task. The task has FINISHED "
        "(passed or failed). You do NOT retry or fix anything.\n\n"
        "Your job: reflect on (1) the task itself and (2) the system, then write "
        "a structured suggestion document.\n\n"
        f"## Task result\n"
        f"- Success: {success}\n"
        f"- Result: {result[:500]}\n"
        f"- Elapsed: {elapsed:.1f}s, {iterations} iterations\n"
        f"- Model: {final_model} (rank {final_rank})\n\n"
        f"## System context (this task's actual run)\n"
        f"- Limits applied: max_iter={max_iter_limit}, "
        f"total_wall={total_wall_limit or 'none'}s\n"
        f"- Used: {iterations} iters, total elapsed {elapsed:.0f}s\n"
        f"- Recovery events: retries={n_retry}, model_changes={n_model_change}, "
        f"review_rejections={n_review_rejected}\n"
        f"- Flags: thinking={'ON' if thinking_used else 'off'}, "
        f"hit_LLM_wall={wall_hit}, hit_total_wall={total_wall_hit}, "
        f"hit_nudge_limit={nudge_limit_hit}\n\n"
        f"## Task definition\n{top_content}\n\n"
        f"## Execution history (index)\n{history_index or '(none)'}\n\n"
        f"## Task memory\n{memory or '(none)'}\n\n"
        "## Output format\n"
        "Write EXACTLY this structure (markdown):\n\n"
        "```\n"
        "## Conclusion\n"
        "<DONE or NOT DONE>: <one sentence reason>\n\n"
        "## Task suggestions\n"
        "- <how to improve the task definition for faster/better convergence>\n"
        "- <were Context/Todo/Expect clear enough?>\n"
        "- <rank, timeout, skills appropriate?>\n\n"
        "## System suggestions\n"
        "- <observations about model performance, review behavior, driver issues>\n"
        "- <only from this task's perspective — evolution will aggregate across tasks>\n\n"
        "## Key insight\n"
        "<ONE line, <120 chars, that captures the most reusable lesson from this run. "
        "This will be appended to global history for evolution to grep. "
        "Examples: 'shell one-liner faster than python loop for word count', "
        "'llama4-scout sufficient for rank-2 multifile refactor', "
        "'BashTime: -1 needed when task installs heavy ML deps'>\n"
        + (f"\n## TaskGroup learning\n"
           f"<2-4 bullets of domain-specific lessons for FUTURE sibling tasks "
           f"in the '{task_group}' group. Focus on: what worked, what failed, "
           f"gotchas, useful patterns. Be concrete and actionable.>\n"
           if task_group else "") +
        "```\n\n"
        "Be concise. Focus on actionable improvements."
    )

    try:
        client = OpenAI(base_url=f"{GATEWAY}/v1", api_key="na")
        resp = client.chat.completions.create(
            model=model, max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        with _usage_lock:
            _usage[model] = _usage.get(model, 0) + 1
        review_text = resp.choices[0].message.content.strip()
        _cam("api_request", caller="final_review", model=model,
             response=review_text, **_response_meta(resp))

        # Write .suggestion.md
        sug_path = os.path.join(task_dir, ".suggestion.md")
        with open(sug_path, "w") as f:
            f.write(f"# Final Review (auto-generated)\n\n{review_text}\n")

        # Extract Key insight and append a structured INSIGHT to global history.
        # Evolution will grep history for INSIGHT entries — faster than walking
        # every task's .suggestion.md.
        insight_match = re.search(
            r'##\s*Key insight\s*\n+(.+?)(?:\n\n|\n##|\Z)',
            review_text, re.DOTALL | re.IGNORECASE)
        if insight_match:
            insight = " ".join(insight_match.group(1).split())[:200]
            _global_history("INSIGHT",
                task=os.path.basename(task_dir),
                success=success,
                model=final_model,
                rank=final_rank,
                insight=insight)

        # TaskGroup ledger: always append structured status (success or failure).
        # Downstream/sibling tasks see this automatically and can act on it.
        if task_group:
            task_label = os.path.basename(task_dir)
            status = "PASSED" if success else "FAILED"
            wall_min = int(elapsed / 60)
            ledger_line = (f"Task: {task_label} | {status} | "
                           f"{final_model} | {wall_min}m {iterations}iter")

            # On failure, also extract domain learnings from final review
            # (success learnings omitted to avoid leaking solutions to siblings)
            tg_learning = ""
            if not success:
                tg_match = re.search(
                    r'##\s*TaskGroup learning\s*\n+(.+?)(?:\n\n##|\Z)',
                    review_text, re.DOTALL | re.IGNORECASE)
                if tg_match:
                    tg_learning = "\n" + tg_match.group(1).strip()[:500]

            _write_taskgroup_memory(task_group, ledger_line + tg_learning)

        # Extract and print conclusion + task suggestions (not system suggestions)
        lines = review_text.split("\n")
        print_section = True
        printed = []
        for line in lines:
            if line.strip().startswith("## System"):
                print_section = False
            if print_section:
                printed.append(line)

        user_output = "\n".join(printed).strip()
        if user_output:
            print(f"\n[final review]", flush=True)
            print(user_output, flush=True)

    except Exception as e:
        print(f"[final review] failed: {e}", flush=True)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: driver.py <task_dir> [task_file]")
        sys.exit(1)

    task_dir = os.path.abspath(sys.argv[1])
    task_file = sys.argv[2] if len(sys.argv) > 2 else "top.md"
    _cam_init(f"driver_{os.path.basename(task_dir)}")

    # Pre-parse NoMemory flag so we can skip global_history writes
    _no_mem_pre = False
    try:
        with open(os.path.join(task_dir, task_file)) as _f:
            _parsed_pre = parse_task(_f.read())
            _no_mem_pre = _parsed_pre["meta"].get("NoMemory", "").lower() in ("on", "true", "yes", "1")
    except (OSError, TaskFormatError):
        pass

    t0 = time.time()
    if not _no_mem_pre:
        _global_history("TASK_START", task=f"{task_dir}/{task_file}",
            rank_config="loaded" if pam._config else "none")

    result, final_rank, final_model, cm, no_memory, task_group = run_sam(task_dir, task_file)

    elapsed = time.time() - t0
    success = not result.startswith(("MAX_ITERATIONS", "UNVERIFIED"))
    hf = os.path.join(task_dir, ".history.md")
    iterations = 0
    if os.path.exists(hf):
        with open(hf) as f:
            iterations = f.read().count("ITERATION**")

    if no_memory:
        print("[no-memory] global history not written for this task", flush=True)
    else:
        _global_history("TASK_END",
            task=f"{task_dir}/{task_file}", success=success,
            iterations=iterations, elapsed=f"{elapsed:.1f}s",
            usage=json.dumps(_usage),
            final_rank=final_rank, final_model=final_model,
            result=result[:300])

    print(f"\n=== Result ({elapsed:.1f}s, {iterations} iters, "
          f"rank={final_rank}, model={final_model}) ===")
    print(f"Model usage: {_usage}")
    print(result)

    # Skip post-task LLM work for trivial successful tasks (saves ~30s + tokens).
    # Trivial = succeeded in <5 iterations and total elapsed <60s.
    skip_post = success and iterations < 5 and elapsed < 60
    if skip_post:
        print(f"[post] skipped (trivial: {iterations} iters, {elapsed:.0f}s)", flush=True)
    else:
        # Index history for future agents to navigate
        index_history(task_dir)
        # Final review: reflect on task design + system feedback
        final_review(task_dir, task_file, result, elapsed, iterations, final_rank, final_model,
                     control_model=cm, task_group=task_group)

    total_wall = time.time() - t0
    print(f"\n=== Total wall time: {total_wall:.1f}s "
          f"(solve: {elapsed:.1f}s + post: {total_wall - elapsed:.1f}s) ===",
          flush=True)
