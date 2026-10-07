"""Autonomous test execution, regression detection, and verification engine."""

import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from pydantic import BaseModel

class TestResult(BaseModel):
    success: bool
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration: float = 0.0
    output: str = ""
    passed_tests: List[str] = []
    failed_tests: List[str] = []
    regressions: List[str] = []

class TestRunner:
    """Executes tests, captures detailed diagnostics, and detects regressions."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.baseline_passed: Set[str] = set()
        self.baseline_executed = False

    def detect_test_command(self) -> List[str]:
        """Detect the best test runner for this repo (pytest, unittest, npm test)."""
        # Python check
        if (self.repo_path / "pytest.ini").exists() or (self.repo_path / "pyproject.toml").exists() or any(self.repo_path.glob("test*.py")) or any(self.repo_path.glob("**/test_*.py")):
            return [sys.executable, "-m", "pytest", "-v"]

        # Node check
        if (self.repo_path / "package.json").exists():
            return ["npm", "test"]

        # Default fallback
        return [sys.executable, "-m", "unittest", "discover", "-v"]

    def run_tests(self, custom_command: Optional[str] = None, test_target: Optional[str] = None) -> TestResult:
        """Run the test suite and compare against baseline to detect any regressions."""
        cmd = custom_command.split() if custom_command else self.detect_test_command()
        if test_target and not custom_command:
            cmd.append(test_target)

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=90
            )
            raw_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            return TestResult(
                success=False,
                output="Tests timed out after 90 seconds.",
                failed=1
            )
        except Exception as e:
            return TestResult(
                success=False,
                output=f"Failed to execute test command {cmd}: {e}",
                failed=1
            )

        # Parse test results
        passed_list, failed_list = self._parse_test_names(raw_output)
        
        # Summary numbers from output if available
        passed_cnt = len(passed_list)
        failed_cnt = len(failed_list)
        
        # Extract pytest summary lines like: "5 passed, 1 failed in 0.12s"
        summary_match = re.search(r"(=+)\s*([\d\w\s,]+)\s+in\s+([\d\.]+s)", raw_output)
        if summary_match:
            stats = summary_match.group(2)
            p_match = re.search(r"(\d+)\s+passed", stats)
            f_match = re.search(r"(\d+)\s+failed", stats)
            if p_match:
                passed_cnt = max(passed_cnt, int(p_match.group(1)))
            if f_match:
                failed_cnt = max(failed_cnt, int(f_match.group(1)))

        total_cnt = passed_cnt + failed_cnt

        # Check for regressions against baseline
        regressions = []
        if self.baseline_executed:
            for test_name in self.baseline_passed:
                if test_name in failed_list:
                    regressions.append(test_name)

        # If this is the baseline run, record working tests
        if not self.baseline_executed:
            self.baseline_passed = set(passed_list)
            self.baseline_executed = True

        is_success = (exit_code == 0) and (failed_cnt == 0) and (len(regressions) == 0)

        return TestResult(
            success=is_success,
            total=total_cnt,
            passed=passed_cnt,
            failed=failed_cnt,
            output=raw_output.strip(),
            passed_tests=passed_list,
            failed_tests=failed_list,
            regressions=regressions
        )

    def _parse_test_names(self, output: str) -> tuple[List[str], List[str]]:
        """Parse individual test names and their PASSED/FAILED statuses."""
        passed = []
        failed = []

        for line in output.splitlines():
            # Match pytest style: tests/test_auth.py::test_login PASSED
            pytest_match = re.search(r"^([\w\/\.\:\-]+)\s+(PASSED|FAILED|ERROR)", line.strip())
            if pytest_match:
                test_id = pytest_match.group(1)
                status = pytest_match.group(2)
                if status == "PASSED":
                    passed.append(test_id)
                else:
                    failed.append(test_id)
                continue

            # Match unittest style: test_login (tests.test_auth.AuthTest) ... ok / FAIL
            unittest_match = re.search(r"^([\w\.\_]+)\s+\(([\w\.\_]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR)", line.strip())
            if unittest_match:
                test_id = f"{unittest_match.group(2)}.{unittest_match.group(1)}"
                status = unittest_match.group(3)
                if status == "ok":
                    passed.append(test_id)
                else:
                    failed.append(test_id)

        return passed, failed
