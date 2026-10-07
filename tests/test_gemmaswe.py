"""Unit test suite for GemmaSWE core modules."""

import sys
import tempfile
import unittest
from pathlib import Path

from gemmaswe.codebase.ast_indexer import AstIndexer
from gemmaswe.codebase.navigator import CodebaseNavigator
from gemmaswe.codebase.patcher import CodePatcher
from gemmaswe.test_runner.runner import TestRunner
from gemmaswe.llm.gemma_provider import MockGemmaClient
from gemmaswe.agent.swe_agent import GemmaSweAgent
from gemmaswe.agent.auditor import CodeAuditor
from gemmaswe.benchmark.scenarios.auth_scenario import setup_auth_repo

class TestGemmaSweCore(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="gemmaswe_test_"))
        setup_auth_repo(self.temp_dir)

    def test_navigator_and_ast_indexing(self):
        navigator = CodebaseNavigator(str(self.temp_dir))
        files = navigator.list_files()
        file_names = [f["path"] for f in files]
        self.assertIn("auth_service.py", file_names)
        self.assertIn("test_auth_baseline.py", file_names)

        # Test code search
        results = navigator.search_code("class TokenManager")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["file"], "auth_service.py")

        # Test AST inspection
        ast_info = AstIndexer.inspect_python_file(self.temp_dir / "auth_service.py")
        class_names = [c["name"] for c in ast_info["classes"]]
        self.assertIn("TokenManager", class_names)

    def test_anti_hallucination_import_checker(self):
        navigator = CodebaseNavigator(str(self.temp_dir))
        
        # Valid code with real standard library
        clean_code = "import time\nimport math\nfrom typing import Dict"
        invalids = navigator.validate_code_imports(clean_code)
        self.assertEqual(len(invalids), 0)

        # Code with fake hallucinated package
        hallucinated_code = "import totally_fake_nonexistent_lib\nfrom super_magic_tool import do_magic"
        invalids = navigator.validate_code_imports(hallucinated_code)
        self.assertIn("totally_fake_nonexistent_lib", invalids)

    def test_atomic_patcher_and_rollback(self):
        patcher = CodePatcher(str(self.temp_dir))
        target_file = "auth_service.py"
        
        # Apply modification
        res = patcher.apply_replacement(target_file, "default_ttl_seconds: int = 300", "default_ttl_seconds: int = 999")
        self.assertTrue(res["success"])
        
        # Verify change
        content = (self.temp_dir / target_file).read_text()
        self.assertIn("default_ttl_seconds: int = 999", content)

        # Rollback
        reverted = patcher.rollback(target_file)
        self.assertIn(target_file, reverted)
        
        # Verify restored pristine state
        restored_content = (self.temp_dir / target_file).read_text()
        self.assertIn("default_ttl_seconds: int = 300", restored_content)

    def test_baseline_and_regression_detection(self):
        runner = TestRunner(str(self.temp_dir))
        
        # Baseline execution
        res1 = runner.run_tests(test_target="test_auth_baseline.py")
        self.assertTrue(res1.success)
        self.assertTrue(runner.baseline_executed)
        self.assertTrue(len(runner.baseline_passed) > 0)

        # Now simulate introducing a regression
        (self.temp_dir / "auth_service.py").write_text("broken syntax !!!", encoding="utf-8")
        res2 = runner.run_tests(test_target="test_auth_baseline.py")
        self.assertFalse(res2.success)

    def test_autonomous_agent_end_to_end(self):
        client = MockGemmaClient()
        agent = GemmaSweAgent(repo_path=str(self.temp_dir), client=client)
        
        task = "Fix the session refresh bug in auth_service.py."
        result = agent.run(task_description=task, test_command=f"{sys.executable} -m unittest discover -v")
        
        self.assertTrue(result["success"])
        self.assertEqual(result["audit"]["verdict"], "PASSED")
        self.assertEqual(result["audit"]["score_breakdown"]["regression_immunity"], 30)
        self.assertEqual(result["audit"]["score_breakdown"]["real_apis_only"], 20)

if __name__ == "__main__":
    unittest.main()
