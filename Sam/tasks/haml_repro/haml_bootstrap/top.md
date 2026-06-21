---
Rank: 1
ThinkTime: -1
BashTime: -1
GPU: local
NoMemory: on
Skills: common_env
ForceModel: gemma4
ControlModel: gemma4
CommonStorage: rw
---

# HAML Bootstrap — build the shared HGQ → da4ml → RTL toolchain env

## Context
Stand up the shared environment that every `haml_repro/*` task reuses, at
**prefix** `/mnt/sci_envs/fpga_toolchain` with **env name** `hgq`
(full path `/mnt/sci_envs/fpga_toolchain/envs/hgq`). This task does NO ML or
Verilog work — it only creates + verifies the toolchain so subsequent tasks
discover it instantly (warm reuse) instead of rebuilding.

**Discover first, build only if missing** (the `common_env` contract): call
`list_shared_envs`; if a suitable env already exists at that path (covers jax,
keras, hgq, da4ml, verilator), just `activate_env` it, verify, and you are done.
Only build a NEW one if none is found.

### What the env must contain (the verified stack — pin these)
- **conda-forge** (`micromamba`): `python=3.12`, `verilator=5.044`, `gxx_linux-64`,
  `make`, `numpy`, `h5py`.
- **pip (PyPI)**: `jax[cuda13]==0.9.1` (CUDA-13 wheels; brings jaxlib + nvidia-*-cu13),
  `keras==3.13.2`.
- **pip (from the source checkouts staged on shared `/mnt` — use these, NOT PyPI, so the RTL
  stays bit-exact to the reference)**: install the two local packages
  `/mnt/sci_shared/src/hgq2` (imports as `hgq`) and `/mnt/sci_shared/src/da4ml`. They are git
  checkouts at the exact commits the reference packages were verified with. (`/mnt` is the
  shared storage the driver auto-maps via `CommonStorage` — no host paths to hardcode.)

## Todo
1. **Discover — call `list_shared_envs` EXACTLY ONCE.** Read its result:
   - If it lists `/mnt/sci_envs/fpga_toolchain/envs/hgq` (the normal warm case), **immediately call
     `activate_env(env_path="/mnt/sci_envs/fpga_toolchain/envs/hgq")` and jump to step 4 (verify).**
     Do NOT call `list_shared_envs` again — calling it repeatedly is a bug; one call is enough.
   - Only if that path is NOT listed, proceed to step 2 (build a new env).
2. **Create** (only if missing). `/mnt` is writable (`CommonStorage: rw`):
   ```bash
   mkdir -p /mnt/sci_envs/fpga_toolchain
   MAMBA_ROOT_PREFIX=/mnt/sci_envs/fpga_toolchain micromamba create -y -n hgq \
       -c conda-forge python=3.12 verilator=5.044 gxx_linux-64 make numpy h5py
   ```
   Then `activate_env(env_path="/mnt/sci_envs/fpga_toolchain/envs/hgq")` and pip-install jax+keras
   (prebuilt wheels — straightforward):
   ```bash
   python -m pip install "jax[cuda13]==0.9.1" keras==3.13.2
   ```
   **Then the two custom packages from the bound source — TWO gotchas, both must be handled:**
   ```bash
   # (a) the builds write egg-info/build dirs into the source tree; don't pollute the SHARED
   #     /mnt copy — COPY each source to a writable /tmp place first:
   cp -r /mnt/sci_shared/src/hgq2  /tmp/hgq2_src
   cp -r /mnt/sci_shared/src/da4ml /tmp/da4ml_src
   # (b) da4ml is a meson + C++ build — meson needs a compiler. The conda gxx wrapper is $CXX/$CC
   #     (injected by the manifest aliases once activated). Export them so meson finds the compiler:
   export CC="$CC"  CXX="$CXX"      # = bin/x86_64-conda-linux-gnu-{gcc,g++}
   python -m pip install /tmp/hgq2_src       # hgq2: pure-python, builds a wheel
   python -m pip install /tmp/da4ml_src      # da4ml: meson/C++; .git in the copy gives the exact version
   ```
   (Heavy installs: use a long bash timeout, e.g. 600s. The jax CUDA wheels are ~2 GB.)
   *Simpler fallback if a source build still fights you:* `pip install hgq2==0.1.8 da4ml==0.6.0` from
   PyPI gives working prebuilt wheels — but da4ml 0.6.0 (final) differs from the verified 0.6.0rc1.dev4,
   so prefer the source build; only fall back if blocked, and note it.
3. **Write the manifest** at `/mnt/sci_envs/fpga_toolchain/envs/hgq/.manifest.json` so
   future tasks discover + activate correctly (note the JAX backend — keras must NOT
   pull tensorflow):
   ```json
   {
     "purpose": "HGQ -> da4ml -> bit-exact streaming RTL: jax(CUDA13), keras(jax backend), hgq, da4ml, h5py, numpy + verilator, make, g++.",
     "binaries": {"python": "bin/python3", "verilator": "bin/verilator", "make": "bin/make"},
     "aliases": {"CXX": "bin/x86_64-conda-linux-gnu-g++", "CC": "bin/x86_64-conda-linux-gnu-gcc"},
     "env": {"KERAS_BACKEND": "jax", "XLA_PYTHON_CLIENT_PREALLOCATE": "false", "MPLCONFIGDIR": "/tmp/mpl-cache"},
     "notes": ["After activate_env run bare commands. KERAS_BACKEND=jax keeps keras off tensorflow.",
               "Data (read-only) is separate: /mnt/sci_shared/data/{train,val}_v3.h5."]
   }
   ```
4. **Verify** the activated env (KERAS_BACKEND=jax is injected by the manifest):
   ```bash
   verilator --version
   python3 -c "import os; os.environ.setdefault('KERAS_BACKEND','jax'); \
import jax, keras, hgq, da4ml, h5py, numpy; \
print('jax', jax.__version__, 'devices', [d.platform for d in jax.devices()]); \
print('keras', keras.__version__, keras.backend.backend()); print('hgq/da4ml/h5py OK')"
   ```
   Write the versions to `toolchain_versions.txt`.

## Expect
- `/mnt/sci_envs/fpga_toolchain/envs/hgq/` exists with a valid `.manifest.json`.
- `verilator --version` → 5.044; `import jax` sees a `gpu` device; `keras.backend.backend()` == `jax`;
  `import hgq` and `import da4ml` succeed.
- `toolchain_versions.txt` lists verilator + jax + keras + hgq + da4ml versions.
- The env is under `/mnt/sci_envs/` (shared), NOT a local `./` dir.
