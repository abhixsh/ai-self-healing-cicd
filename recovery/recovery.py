#!/usr/bin/env python3
"""Runs ONE allow-listed recovery action. No arbitrary commands are accepted."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "ai-self-healing-cicd:test"
CONTAINER = "selfheal-test"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def restore_known_good_config() -> None:
    src = ROOT / "recovery" / "known-good" / "pytest.ini"
    dst = ROOT / "pytest.ini"
    shutil.copyfile(src, dst)
    print(f"Restored {dst.relative_to(ROOT)} from {src.relative_to(ROOT)}")


def restart_test_container() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], cwd=ROOT, check=False)
    run(["docker", "build", "-t", IMAGE, "."])
    run(["docker", "run", "-d", "--name", CONTAINER, "-p", "5000:5000", IMAGE])
    run(["bash", "scripts/health-check.sh"])


ACTIONS = {
    "restore_known_good_config": restore_known_good_config,
    "restart_test_container": restart_test_container,
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--action", required=True)
    action = p.parse_args().action
    fn = ACTIONS.get(action)
    if fn is None:
        print(f"Refusing action '{action}'. Allowed: {sorted(ACTIONS)}", file=sys.stderr)
        return 2
    fn()
    return 0


if __name__ == "__main__":
    sys.exit(main())
