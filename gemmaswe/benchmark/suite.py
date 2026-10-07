"""SWE-Agent Benchmark Evaluator with Visible and Hidden Test Scoring."""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List

from gemmaswe.agent.swe_agent import GemmaSweAgent
from gemmaswe.benchmark.scenarios.auth_scenario import setup_auth_repo
from gemmaswe.benchmark.scenarios.ratelimit_scenario import setup_ratelimit_repo

class BenchmarkEvaluator:
    """Runs automated benchmark evaluation for GemmaSWE across multiple scenarios."""

    @staticmethod
    def run_auth_scenario(provider: str = "mock", api_key: str = "") -> Dict[str, Any]:
        """Run Scenario 1: Auth & Session Token Bugfix."""
        temp_dir = Path(tempfile.mkdtemp(prefix="gemmaswe_auth_"))
        try:
            setup_auth_repo(temp_dir)
            
            from gemmaswe.llm.gemma_provider import get_gemma_client
            client = get_gemma_client(provider=provider, api_key=api_key)
            agent = GemmaSweAgent(repo_path=str(temp_dir), client=client)

            task = (
                "Investigate and fix the session refresh bug in auth_service.py. "
                "Ensure that when refresh_session is called, it returns a valid new token with the user's metadata, "
                "properly revokes the old token, and all existing tests in test_auth_baseline.py and "
                "test_token_refresh.py pass without breaking any existing behavior."
            )

            run_result = agent.run(task_description=task, test_command=f"{sys.executable} -m unittest discover -v")

            # Execute HIDDEN TESTS for 30 points
            hidden_proc = subprocess.run(
                [sys.executable, "-m", "unittest", "hidden_tests.py"],
                cwd=str(temp_dir),
                capture_output=True,
                text=True
            )
            hidden_passed = hidden_proc.returncode == 0

            return {
                "scenario": "auth_session_bugfix",
                "repo_path": str(temp_dir),
                "agent_success": run_result["success"],
                "hidden_tests_passed": hidden_passed,
                "hidden_score": 30 if hidden_passed else 0,
                "iterations": run_result["iterations"],
                "explanation": run_result["explanation"],
                "diff": run_result["diff"],
                "audit": run_result["audit"]
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def clone_and_run_public_repo(repo_url: str, task: str, test_command: str = "", provider: str = "google") -> Dict[str, Any]:
        """Clone any public repository (GitHub, GitLab) and dispatch GemmaSWE to solve an issue."""
        temp_dir = Path(tempfile.mkdtemp(prefix="gemmaswe_git_"))
        try:
            clone_proc = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(temp_dir)],
                capture_output=True,
                text=True
            )
            if clone_proc.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to clone repository {repo_url}: {clone_proc.stderr}"
                }

            from gemmaswe.llm.gemma_provider import get_gemma_client
            client = get_gemma_client(provider=provider)
            agent = GemmaSweAgent(repo_path=str(temp_dir), client=client)

            result = agent.run(task_description=task, test_command=test_command or None)
            return {
                "scenario": "public_git_repo",
                "repo_url": repo_url,
                **result
            }
        finally:
            # Note: in real run, caller can inspect or keep temp_dir
            pass
