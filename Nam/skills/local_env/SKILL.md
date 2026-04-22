---
name: local_env
description: Create local writable environments (Python, C++, any language) in the task directory using micromamba. Covers pip/uv/venv best practices.
---

# local_env — local environment setup in the task directory

The container's system environment is **read-only**. You cannot install into it.
All package installations must go into your **local task directory** (`./`).

`micromamba` is pre-installed and available on `$PATH`. Use it to create
isolated environments for any language or toolchain — Python, C/C++ compilers,
R, Julia, or any conda-forge package.

## Creating an environment

All environments live under `./mamba_env` in your task directory:

```bash
# Python environment
MAMBA_ROOT_PREFIX=./mamba_env micromamba create -y -n work -c conda-forge python=3.12

# Python + C++ toolchain
MAMBA_ROOT_PREFIX=./mamba_env micromamba create -y -n work -c conda-forge python=3.12 compilers cmake make

# C/C++ only (no Python)
MAMBA_ROOT_PREFIX=./mamba_env micromamba create -y -n work -c conda-forge compilers cmake make

# Any conda-forge package
MAMBA_ROOT_PREFIX=./mamba_env micromamba create -y -n work -c conda-forge <packages>
```

## Generate env.sh

After creating the environment, write `env.sh` so all bash commands
automatically use it:

Use absolute paths anchored to `env.sh` itself — relative paths break as
soon as the agent does `cd subdir && python script.py` and the script
internally calls `subprocess.run(['make'])` (PATH would resolve against
the new cwd and miss the env).

```bash
cat > env.sh << 'EOF'
_ENV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAMBA_ROOT_PREFIX="$_ENV_ROOT/mamba_env"
export CONDA_PREFIX="$_ENV_ROOT/mamba_env/envs/work"
export PATH="$_ENV_ROOT/mamba_env/envs/work/bin:$PATH"
export LD_LIBRARY_PATH="$_ENV_ROOT/mamba_env/envs/work/lib:${LD_LIBRARY_PATH:-}"
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
MAMBA_ROOT_PREFIX=./mamba_env micromamba run -n work pip install <package>
```

pip installs into the micromamba env's site-packages — already local.

### uv (fast Python package installer)

If you prefer `uv`, install it into the env first, then use it:

```bash
MAMBA_ROOT_PREFIX=./mamba_env micromamba run -n work pip install uv
MAMBA_ROOT_PREFIX=./mamba_env micromamba run -n work uv pip install <package>
```

### venv — do NOT use

Do not create a `python -m venv` inside the micromamba env. It adds a
redundant layer and can break path resolution. micromamba already provides
isolation — use it directly.

### conda/mamba packages

```bash
MAMBA_ROOT_PREFIX=./mamba_env micromamba install -n work -c conda-forge <package> -y
```

### Dev installs from cloned repos

```bash
MAMBA_ROOT_PREFIX=./mamba_env micromamba run -n work pip install ./repo_dir
```

Use `pip install ./repo_dir` (not `-e`). Editable installs can break in
isolated envs.

## Rules

- Create the env with `MAMBA_ROOT_PREFIX=./mamba_env micromamba create ...`
- Write `env.sh` immediately after creation — all subsequent commands auto-activate
- **All** installs (pip, uv, conda) go into `./mamba_env` — nothing is written outside the task directory
- The `driver` Python (running this agent) is separate — do not use it or install into it
- `git`, `curl`, `wget` are system commands and work without the env
- To check a package version: use `importlib.metadata.version('pkg')` (not `pkg.__version__`)
