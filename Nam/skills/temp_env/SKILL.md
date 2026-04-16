---
name: temp_env
description: Create throwaway environments in /tmp using micromamba. Same as local_env but installs to /tmp instead of the task directory — nothing persists after the container exits.
---

# temp_env — throwaway environment in /tmp

The container's system environment is **read-only**. You cannot install into it.
This skill installs everything under `/tmp/mamba_env` — a fast, throwaway
location that does **not** persist after the container exits and does **not**
consume space in the task directory.

Use this when you need packages temporarily and don't need the env to survive
across runs. For persistent local envs, use `local_env` instead.

`micromamba` is pre-installed and available on `$PATH`. Use it to create
isolated environments for any language or toolchain — Python, C/C++ compilers,
R, Julia, or any conda-forge package.

## Creating an environment

```bash
# Python environment
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba create -y -n work -c conda-forge python=3.12

# Python + C++ toolchain
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba create -y -n work -c conda-forge python=3.12 compilers cmake make

# C/C++ only (no Python)
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba create -y -n work -c conda-forge compilers cmake make

# Any conda-forge package
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba create -y -n work -c conda-forge <packages>
```

## Generate env.sh

After creating the environment, write `env.sh` so all bash commands
automatically use it:

```bash
cat > env.sh << 'EOF'
export MAMBA_ROOT_PREFIX=/tmp/mamba_env
export CONDA_PREFIX=/tmp/mamba_env/envs/work
export PATH="/tmp/mamba_env/envs/work/bin:$PATH"
export LD_LIBRARY_PATH="/tmp/mamba_env/envs/work/lib:${LD_LIBRARY_PATH:-}"
EOF
```

Once `env.sh` exists, all bash commands use the env automatically — just
use bare commands:

```bash
python my_script.py
gcc -o prog prog.c
cmake --build .
```

## Installing additional packages

### pip (Python packages from PyPI)

```bash
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba run -n work pip install <package>
```

### uv (fast Python package installer)

```bash
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba run -n work pip install uv
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba run -n work uv pip install <package>
```

### venv — do NOT use

Do not create a `python -m venv` inside the micromamba env. It adds a
redundant layer and can break path resolution. micromamba already provides
isolation — use it directly.

### conda/mamba packages

```bash
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba install -n work -c conda-forge <package> -y
```

### Dev installs from cloned repos

```bash
MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba run -n work pip install ./repo_dir
```

Use `pip install ./repo_dir` (not `-e`). Editable installs can break in
isolated envs.

## Rules

- Create the env with `MAMBA_ROOT_PREFIX=/tmp/mamba_env micromamba create ...`
- Write `env.sh` immediately after creation — all subsequent commands auto-activate
- **All** installs (pip, uv, conda) go into `/tmp/mamba_env` — nothing is written to the task directory
- The `driver` Python (running this agent) is separate — do not use it or install into it
- `git`, `curl`, `wget` are system commands and work without the env
- To check a package version: use `importlib.metadata.version('pkg')` (not `pkg.__version__`)
- The env is **ephemeral** — it will be lost when the container exits
