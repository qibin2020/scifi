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

## Two names — keep them straight

Every shared env has TWO identifiers, and they are NOT the same:

- **`<prefix>`** = a `MAMBA_ROOT_PREFIX` directory under `/mnt/sci_envs/`. Each
  prefix is one *domain* (a category of related work, e.g. `fpga_toolchain`
  for FPGA/Verilog work, `root` for CERN ROOT, `ml` for ML frameworks). It
  holds an `envs/` folder, a `pkgs/` cache, and a `PURPOSE.md` manifest.
- **`<env>`** = the actual env name *inside* a prefix. Lives at
  `<prefix>/envs/<env>/bin/...`. One prefix can hold multiple envs.

Full path of an env: `/mnt/sci_envs/<prefix>/envs/<env>/`.

Pick `<prefix>` for the domain (rarely changes — pin it in the task spec).
Pick `<env>` for the specific configuration within that domain.

If the task spec gives you both names, use them verbatim — that's how
sibling tasks reuse the env you're about to build.

## Step 1: Discover existing envs

Call the `list_shared_envs` tool. It enumerates `/mnt/sci_envs/` and prints
each env's path plus a one-line `purpose` from the env's manifest. No bash
probing needed.

## Step 2: Inspect a candidate before activating

For any env that looks plausible, call `read_env_manifest(env_path=...)`
to see its full manifest: `purpose`, key `binaries`, `aliases` (e.g. `CXX`,
`CC`), and free-form `notes` (quirks like which g++ wrapper to use).

Pick the env whose purpose matches your task. If multiple plausibly match,
prefer the one whose `aliases`/`binaries` cover what your task needs.

## Step 3: If no suitable env found — create one

If the task spec named a `<prefix>` and `<env>` — use those exactly. If not,
pick a descriptive prefix name for the **domain** (e.g. `root`, `ml`, `geo`,
`astro`) and an env name for the **specific configuration**.

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

Once verification passes, **write a `.manifest.json`** at the env root
`/mnt/sci_envs/<prefix>/envs/<env>/.manifest.json` so future tasks (and
list_shared_envs) can discover and reuse this env. Use write_file with:

```json
{
  "purpose": "<one-line summary, e.g. Verilator + g++ FPGA simulation toolchain>",
  "binaries": {
    "python": "bin/python3",
    "<other key tool>": "bin/<exec>"
  },
  "aliases": {
    "CXX": "bin/<conda-wrapper-c++>",
    "CC":  "bin/<conda-wrapper-cc>"
  },
  "notes": [
    "<concrete tip, e.g. use $CXX in build scripts; conda's wrapper differs from /usr/bin/g++>",
    "<another quirk worth flagging>"
  ]
}
```

`aliases` are the most important field: they get exported as env vars on
every bash call, so build scripts that reference `$CXX` / `$CC` Just Work
without the agent having to discover the right wrapper name.

**If read-only** — fall back to a local env in the task directory:
```bash
MAMBA_ROOT_PREFIX=./env micromamba create -n <env> -c conda-forge <packages> -y
```

## Step 4: Activate the env

Call `activate_env(env_path="/mnt/sci_envs/<prefix>/envs/<env>")` exactly
once. From that point on:

- Every bash result is prefixed with `[active env: <path>]` so the
  active state is always visible — no probing needed.
- `PATH`, `LD_LIBRARY_PATH`, `MAMBA_ROOT_PREFIX`, `CONDA_PREFIX`, and any
  manifest `aliases` (e.g. `$CXX`) are injected automatically.
- Run bare commands: `python3 your_script.py`, `make`, `verilator`, etc.
  Do NOT write env.sh, do NOT prefix with `micromamba run`, do NOT
  `source` anything.

For local-fallback envs (when `/mnt` is read-only), pass the local path
instead, e.g. `activate_env(env_path="./env/envs/<env>")`.

## Common domain examples

| Domain | Prefix | Env name | Key packages |
|--------|--------|----------|--------------|
| CERN ROOT | `root` | `root` | `root numpy matplotlib` |
| ML / Deep Learning | `ml` | `torch` | `pytorch torchvision numpy` |
| Geospatial | `geo` | `geo` | `gdal rasterio fiona shapely` |
| Astronomy | `astro` | `astro` | `astropy healpy matplotlib` |

These are suggestions — use whatever name fits your task.
