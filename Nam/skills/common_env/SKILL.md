# common_env — shared environment discovery and reuse

**This skill is MANDATORY when declared.** Do NOT install packages locally
under `./`. Use `/mnt/sci_envs/` for all environment creation so future
tasks can reuse them. The system prompt's local install example (`./mamba_env`)
does NOT apply when this skill is active.

This skill helps you find or create a reusable environment in the shared
workspace `/mnt/sci_envs/`. Use it for any task that needs packages that are
expensive to install (ROOT, geant4, tensorflow, pytorch, etc.) or that
benefit from cross-task reuse.

## Rule: REUSE or CREATE NEW — never modify an existing env

- If a working env is found → **reuse** it as-is
- If no working env is found → **create a brand new** one
- **Never** pip install into, conda install into, or otherwise modify an existing shared env
- If an env exists but is missing something you need → create a **new** env with a different name

## Step 1: Discover existing envs

List what is already available:
```bash
ls /mnt/sci_envs/ 2>/dev/null || echo "NO SHARED ENVS"
```

Each subdirectory under `/mnt/sci_envs/` is a MAMBA_ROOT_PREFIX. Env names
live inside each prefix. To list envs in a prefix:
```bash
MAMBA_ROOT_PREFIX=/mnt/sci_envs/<prefix> micromamba env list 2>/dev/null
```

## Step 2: Check if an existing env meets your needs

**First, read each prefix's `PURPOSE.md` if present.** This file is written
by this skill at env-creation time and describes the env's intended domain
and key packages. Prefer matches based on purpose over matches based on
directory-name guesses:

```bash
for d in /mnt/sci_envs/*/; do
    [ -f "$d/PURPOSE.md" ] && echo "=== $d ===" && cat "$d/PURPOSE.md"
done
```

**Then consider env names** (useful as a fallback when `PURPOSE.md` is
missing — older envs predate this convention). Each prefix describes a
domain (e.g. `root` for ROOT, `fpga_toolchain` for Verilator/g++, `ml`
for PyTorch).

If a prefix's purpose or name matches your task, verify it actually has
the packages you need:
```bash
MAMBA_ROOT_PREFIX=/mnt/sci_envs/<prefix> micromamba run -n <env> python -c "import <package>; print('OK')"
```

If verification passes → **use this env**. Skip install. Start your actual task.

```bash
MAMBA_ROOT_PREFIX=/mnt/sci_envs/<prefix> micromamba run -n <env> python your_script.py
```

## Step 3: If no suitable env found — create one

Pick a descriptive prefix name for the domain (e.g. `root`, `ml`, `geo`, `astro`).

Check if `/mnt` is writable:
```bash
touch /mnt/.write_test 2>/dev/null && rm /mnt/.write_test && echo "WRITABLE" || echo "READ-ONLY"
```

**If writable** — create the shared env (heavy installs can take 5-10 min, use `"timeout": 600`):
```bash
mkdir -p /mnt/sci_envs/<prefix>
MAMBA_ROOT_PREFIX=/mnt/sci_envs/<prefix> micromamba create -n <env> -c conda-forge <packages> -y
```

Bundle common companions (e.g. numpy, matplotlib with ROOT; pandas, scikit-learn
with ML frameworks) to maximize reuse for future tasks.

Verify after install:
```bash
MAMBA_ROOT_PREFIX=/mnt/sci_envs/<prefix> micromamba run -n <env> python -c "import <package>; print('OK')"
```

Once verification passes, **write a `PURPOSE.md` descriptor** at
`/mnt/sci_envs/<prefix>/PURPOSE.md` so future tasks can discover and reuse
this env instead of creating a near-duplicate. Keep it plain and short:

```bash
cat > /mnt/sci_envs/<prefix>/PURPOSE.md << 'EOF'
# <one-line purpose, e.g. "Verilator + g++ FPGA simulation toolchain">

## Packages
- <key package 1>
- <key package 2>
- ...

## Created by
task: <group/task_name>
date: <YYYY-MM-DD>
EOF
```

Do NOT list every transitive dependency — only the packages a caller would
search for. The point is matchability, not a manifest.

**If read-only** — fall back to a local env in the task directory:
```bash
MAMBA_ROOT_PREFIX=./env micromamba create -n <env> -c conda-forge <packages> -y
```

## Step 4: Generate env.sh

After discovering or creating an env, write `env.sh` so all bash commands
automatically use it. Replace `<prefix>` and `<env>` with actual values:

```bash
cat > env.sh << 'EOF'
export MAMBA_ROOT_PREFIX=/mnt/sci_envs/<prefix>
export CONDA_PREFIX=/mnt/sci_envs/<prefix>/envs/<env>
export PATH="/mnt/sci_envs/<prefix>/envs/<env>/bin:$PATH"
export LD_LIBRARY_PATH="/mnt/sci_envs/<prefix>/envs/<env>/lib:${LD_LIBRARY_PATH:-}"
EOF
```

Verify it works — bare commands should now resolve to the env:
```bash
python3 --version
```

Once `env.sh` exists, all bash commands automatically use the env.
No need for `micromamba run` prefixes — just use bare commands:
```bash
python your_script.py
make
g++  # works if compilers are installed in the env
```

## Common domain examples

| Domain | Prefix | Env name | Key packages |
|--------|--------|----------|--------------|
| CERN ROOT | `root` | `root` | `root numpy matplotlib` |
| ML / Deep Learning | `ml` | `torch` | `pytorch torchvision numpy` |
| Geospatial | `geo` | `geo` | `gdal rasterio fiona shapely` |
| Astronomy | `astro` | `astro` | `astropy healpy matplotlib` |

These are suggestions — use whatever name fits your task.
