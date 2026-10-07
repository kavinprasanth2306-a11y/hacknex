"""Strict quality, regression, and anti-hallucination auditor for GemmaSWE."""

from typing import Dict, Any, List
from gemmaswe.codebase.patcher import CodePatcher
from gemmaswe.codebase.navigator import CodebaseNavigator
from gemmaswe.test_runner.runner import TestResult

class CodeAuditor:
    """Evaluates adherence to hackathon judging rules."""

    @staticmethod
    def audit_patch(
        patcher: CodePatcher,
        navigator: CodebaseNavigator,
        final_test_result: TestResult,
        explanation: str
    ) -> Dict[str, Any]:
        diff_info = patcher.get_summary_diff()
        modified_files = diff_info["modified_files"]
        lines_added = diff_info["lines_added"]
        lines_removed = diff_info["lines_removed"]

        # 1. Anti-hallucination check: any fake imports in new code?
        hallucinated_imports = []
        for file in modified_files:
            file_path = navigator.repo_path / file
            if file_path.exists() and file.endswith(".py"):
                content = file_path.read_text(encoding="utf-8", errors="replace")
                invalids = navigator.validate_code_imports(content)
                hallucinated_imports.extend(invalids)

        # 2. Regression check
        regressions_count = len(final_test_result.regressions)
        passed_existing = final_test_result.success and (regressions_count == 0)

        # 3. Clean and minimal check
        is_minimal = (lines_added + lines_removed) <= 80 and len(modified_files) <= 5

        # 4. Explanation quality
        has_good_explanation = len(explanation.strip()) >= 50 and any(
            kw in explanation.lower() for kw in ["root cause", "bug", "fixed", "cause", "issue", "logic"]
        )

        # Scoring
        score_breakdown = {
            "regression_immunity": 30 if passed_existing else 0,
            "real_apis_only": 20 if len(hallucinated_imports) == 0 else 0,
            "clean_and_minimal": 15 if is_minimal else 8,
            "tests_pass": 25 if final_test_result.success else 0,
            "explanation_quality": 10 if has_good_explanation else 5,
        }
        total_score = sum(score_breakdown.values())

        return {
            "total_score": total_score,
            "max_score": 100,
            "score_breakdown": score_breakdown,
            "regressions": final_test_result.regressions,
            "hallucinated_imports": list(set(hallucinated_imports)),
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "files_modified": modified_files,
            "is_minimal": is_minimal,
            "has_good_explanation": has_good_explanation,
            "verdict": "PASSED" if total_score >= 80 else "NEEDS_IMPROVEMENT"
        }
