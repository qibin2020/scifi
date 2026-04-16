#!/usr/bin/env python3
"""Unit tests for portal.py.

Tests cover: command building for all 3 profiles, bind/env computation,
GPU/SLURM resolution, run directory creation, HOME and EFFECTIVE_COMMON_*
env vars, and task metadata gating.

Python 3.6 compatible. Does not require Apptainer — tests command
construction only.
"""

import os
import sys
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Test environment setup (mock filesystem)
# ============================================================

_test_tmpdir = tempfile.mkdtemp(prefix="test_portal_")

_test_env = {
    "BASEDIR": _test_tmpdir,
    "FDIR": os.path.join(_test_tmpdir, "F"),
    "APPTAINER": "/usr/bin/apptainer",
    "SIF": os.path.join(_test_tmpdir, "test.sif"),
    "OVERLAY": os.path.join(_test_tmpdir, "F.overlay.img"),
    "TASKS_SRC": os.path.join(_test_tmpdir, "Sam", "tasks"),
    "SKILLS_SRC": os.path.join(_test_tmpdir, "Nam", "skills"),
    "RANK_SRC": os.path.join(_test_tmpdir, "gateway.rank.yaml"),
    "GATEWAY_PORT": "12345",
    "FALLBACK_HIGHEST": "test-model",
    "FALLBACK_WORKING": "test-worker",
    "MAX_ITERATIONS": "50",
    "CHECKPOINT_EVERY": "5",
    "MAX_CONTEXT": "80",
    "MAX_DEPTH": "5",
    "MAX_REVIEW_ITER": "10",
    "MAX_REFLECT_ITER": "15",
    "MAX_RETRIES": "3",
    "MAX_PARALLEL_AGENTS": "4",
    "MAX_BASH_TIME": "300",
    "WALL_LIMIT_PER_RANK": "60,120,240,300,360,600",
    "ITER_LIMIT_PER_RANK": "10,20,30,30,50,50",
    "TOTAL_WALL_PER_RANK": "1800,1800,1800,1800,1800,1800",
    "MAX_EVOLVE_ITER": "20",
    "CAM_DIR": os.path.join(_test_tmpdir, "Cam"),
    "TMPDIR": _test_tmpdir,
    "NERSC_ACCOUNT": "m2616",
}

for k, v in _test_env.items():
    os.environ[k] = v

# Create mock filesystem
for d in ["F", "F/home", "F/mnt", "F/run", "F/tasks", "Sam/tasks",
           "Nam/skills", "Pam", "Cam"]:
    os.makedirs(os.path.join(_test_tmpdir, d), exist_ok=True)

for f in ["F.overlay.img", "test.sif", "gateway.rank.yaml",
           "F/driver.py", "F/task_parser.py", "F/evolution.py", "F/ask.py",
           "F/F.design.md", "F/F.usage.md", "Pam/pam.py", "ENV.sh"]:
    open(os.path.join(_test_tmpdir, f), "w").close()

# Test tasks with different metadata
def _make_task(name, frontmatter):
    d = os.path.join(_test_tmpdir, "Sam", "tasks", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "top.md"), "w") as f:
        f.write("---\n%s\n---\n\n## Todo\ndo\n\n## Expect\nok\n" % frontmatter)

_make_task("basic_task", "Rank: 0")
_make_task("gpu_task", "Rank: 1\nGPU: local\nSlurm: on\nBashTime: -1\nCommonStorage: ro\nCommonHome: disable")
_make_task("isolated_task", "Rank: 0\nNoMemory: on")
_make_task("skill_task", "Rank: 1\nSkills: common_env\nCommonStorage: rw")

import portal


# ============================================================
# Driver profile
# ============================================================

class TestDriverProfile(unittest.TestCase):

    def test_basic_command_structure(self):
        cmd = portal.build_driver_cmd("basic_task", [])
        cmd_str = " ".join(cmd)
        for flag in ["--overlay", "--cleanenv", "--contain", "--pwd /srv",
                      "--no-home", "--writable-tmpfs"]:
            self.assertIn(flag, cmd_str)

    def test_core_binds(self):
        cmd = portal.build_driver_cmd("basic_task", [])
        cmd_str = " ".join(cmd)
        for path in ["/srv/driver.py", "/srv/pam.py", "/srv/task_parser.py",
                      "/srv/gateway.rank.yaml", "/srv/skills", "/srv/run"]:
            self.assertIn(path, cmd_str)

    def test_env_vars(self):
        cmd = portal.build_driver_cmd("basic_task", [])
        cmd_str = " ".join(cmd)
        self.assertIn("GATEWAY_URL=http://localhost:12345", cmd_str)
        self.assertIn("MAX_ITERATIONS=50", cmd_str)
        self.assertIn("SKILLS_DIR=/srv/skills", cmd_str)

    def test_effective_common_storage_passed(self):
        cmd = portal.build_driver_cmd("basic_task", [])
        cmd_str = " ".join(cmd)
        self.assertIn("EFFECTIVE_COMMON_STORAGE=", cmd_str)
        self.assertIn("EFFECTIVE_COMMON_HOME=", cmd_str)

    def test_home_set_to_task_dir(self):
        cmd = portal.build_driver_cmd("basic_task", [])
        # Find the shell command (last bash -c arg)
        shell_idx = cmd.index("bash") + 2
        shell_cmd = cmd[shell_idx]
        self.assertIn("export HOME=/srv/basic_task", shell_cmd)

    def test_gpu_task_common_storage_ro(self):
        cmd = portal.build_driver_cmd("gpu_task", [])
        cmd_str = " ".join(cmd)
        self.assertIn("EFFECTIVE_COMMON_STORAGE=ro", cmd_str)

    def test_gpu_task_common_home_disable(self):
        cmd = portal.build_driver_cmd("gpu_task", [])
        cmd_str = " ".join(cmd)
        self.assertIn("EFFECTIVE_COMMON_HOME=disable", cmd_str)
        # /home should NOT be bound
        bind_args = [cmd[i+1] for i in range(len(cmd)-1) if cmd[i] == "--bind"]
        home_binds = [b for b in bind_args if ":/home:" in b]
        self.assertEqual(home_binds, [])

    def test_cam_bind(self):
        cmd = portal.build_driver_cmd("basic_task", [])
        cmd_str = " ".join(cmd)
        self.assertIn("/cam", cmd_str)

    def test_extra_args(self):
        cmd = portal.build_driver_cmd("basic_task", ["--debug"])
        self.assertIn("--debug", cmd)

    def test_missing_task_exits(self):
        with self.assertRaises(SystemExit):
            portal.build_driver_cmd("nonexistent", [])


# ============================================================
# Evolution profile
# ============================================================

class TestEvolutionProfile(unittest.TestCase):

    def test_basic(self):
        cmd = portal.build_evolution_cmd(["suggest"])
        cmd_str = " ".join(cmd)
        self.assertIn("/srv/evolution.py", cmd_str)
        self.assertIn("/srv/task_parser.py", cmd_str)
        self.assertIn("MAX_EVOLVE_ITER=20", cmd_str)

    def test_no_gpu(self):
        cmd = portal.build_evolution_cmd(["suggest"])
        self.assertNotIn("--nv", cmd)

    def test_dir_arg_conversion(self):
        d = os.path.join(_test_tmpdir, "some_dir")
        os.makedirs(d, exist_ok=True)
        cmd = portal.build_evolution_cmd(["suggest", d])
        cmd_str = " ".join(cmd)
        self.assertIn("/srv/tasks/some_dir", cmd_str)


# ============================================================
# Ask profile
# ============================================================

class TestAskProfile(unittest.TestCase):

    def test_interactive(self):
        cmd = portal.build_ask_cmd([])
        self.assertIn("-it", cmd)

    def test_default_model(self):
        cmd = portal.build_ask_cmd([])
        cmd_str = " ".join(cmd)
        self.assertIn("MODEL=test-model", cmd_str)

    def test_custom_model(self):
        cmd = portal.build_ask_cmd(["claude-opus"])
        cmd_str = " ".join(cmd)
        self.assertIn("MODEL=claude-opus", cmd_str)

    def test_readonly_binds(self):
        cmd = portal.build_ask_cmd([])
        cmd_str = " ".join(cmd)
        self.assertIn("/srv/run:ro", cmd_str)
        self.assertIn("/srv/tasks:ro", cmd_str)


# ============================================================
# GPU resolution
# ============================================================

class TestResolveGpu(unittest.TestCase):

    def test_gpu_no(self):
        use_nv, devices = portal.resolve_gpu({"GPU": "no"})
        self.assertFalse(use_nv)
        self.assertIsNone(devices)

    def test_gpu_default(self):
        use_nv, devices = portal.resolve_gpu({})
        self.assertFalse(use_nv)

    def test_gpu_numeric(self):
        """GPU: 2 should be treated as local with count."""
        # Can't test fully without nvidia-smi, but verify it doesn't crash
        # on machines without GPU
        try:
            portal.resolve_gpu({"GPU": "2"})
        except SystemExit:
            pass  # expected on machines without nvidia-smi


# ============================================================
# SLURM resolution
# ============================================================

class TestResolveSlurm(unittest.TestCase):

    def test_off(self):
        self.assertEqual(portal.resolve_slurm({"Slurm": "off"}), [])

    def test_default_off(self):
        self.assertEqual(portal.resolve_slurm({}), [])

    def test_on(self):
        binds = portal.resolve_slurm({"Slurm": "on"})
        paths = [b[0] for b in binds]
        self.assertIn("/usr/bin/sbatch", paths)
        self.assertIn("/usr/bin/squeue", paths)
        self.assertIn("/usr/bin/scancel", paths)

    def test_gpu_slurm_implies_on(self):
        binds = portal.resolve_slurm({"GPU": "slurm"})
        self.assertTrue(len(binds) > 0)


# ============================================================
# Run directory creation
# ============================================================

class TestCreateRunDir(unittest.TestCase):

    def test_creates_dir_with_task_files(self):
        run_dir, bind_run = portal.create_run_dir("basic_task", "driver")
        self.assertTrue(os.path.isdir(run_dir))
        self.assertTrue(os.path.isfile(os.path.join(run_dir, "top.md")))

    def test_global_state_files(self):
        run_dir, bind_run = portal.create_run_dir("basic_task", "driver")
        self.assertTrue(os.path.isfile(os.path.join(bind_run, ".global_memory.md")))
        self.assertTrue(os.path.isfile(os.path.join(bind_run, ".global_history.md")))

    def test_unique_dirs(self):
        """Multiple calls produce unique directories."""
        dirs = set()
        for _ in range(5):
            run_dir, _ = portal.create_run_dir("basic_task", "driver")
            self.assertNotIn(run_dir, dirs)
            dirs.add(run_dir)

    def test_missing_task_exits(self):
        with self.assertRaises(SystemExit):
            portal.create_run_dir("nonexistent", "driver")


# ============================================================
# Cleanup
# ============================================================

def tearDownModule():
    shutil.rmtree(_test_tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
