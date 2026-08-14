"""Run critical backend tests and frontend production builds."""

from __future__ import annotations

import argparse
import compileall
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parent
BACKEND = ROOT / "backend"


def configure_isolated_environment() -> None:
    """Ensure test imports cannot connect to production resources."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(BACKEND))
    os.environ["DATABASE_URL"] = "sqlite://"
    os.environ["MISTRAL_API_KEY"] = "test-only-no-network-calls"
    os.environ["MCP_SSE_URL"] = "http://127.0.0.1:1/sse"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["UPLOAD_DIR"] = str(Path(tempfile.gettempdir()) / "credit-dossier-tests")


def run_python_checks() -> bool:
    print("\n[1/3] Compiling backend and MCP Python source...")
    compiled = compileall.compile_dir(
        BACKEND / "app", quiet=1, force=False
    ) and compileall.compile_dir(ROOT / "mcp", quiet=1, force=False)
    if not compiled:
        print("Python compilation failed.")
        return False

    print("\n[2/3] Running critical backend tests...")
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(TEST_DIR),
        pattern="test_*.py",
        top_level_dir=str(ROOT),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def run_frontend_builds() -> bool:
    print("\n[3/3] Building both frontends...")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        print("FAIL: npm was not found on PATH.")
        return False

    success = True
    for frontend in (ROOT / "frontend", ROOT / "frontend_2"):
        if not (frontend / "node_modules").is_dir():
            print(f"FAIL: {frontend.name}/node_modules is missing; run npm install there.")
            success = False
            continue
        print(f"\n--- {frontend.name}: npm run build ---")
        completed = subprocess.run([npm, "run", "build"], cwd=frontend, check=False)
        success = completed.returncode == 0 and success
    return success


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Credit Dossier critical-path tests.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run Python checks only and skip the two frontend builds.",
    )
    args = parser.parse_args()

    configure_isolated_environment()
    python_ok = run_python_checks()
    frontend_ok = True if args.quick else run_frontend_builds()

    print("\n" + "=" * 68)
    if python_ok and frontend_ok:
        print("PASS: All requested Credit Dossier checks completed successfully.")
        return 0
    print("FAIL: One or more Credit Dossier checks failed. Review the output above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

