"""Core autonomous SWE agent orchestration loop."""

import json
import logging
from typing import Dict, Any, List, Optional, Callable
from pydantic import BaseModel

from gemmaswe.config import config
from gemmaswe.llm.base import BaseGemmaClient, ToolDefinition
from gemmaswe.llm.gemma_provider import get_gemma_client
from gemmaswe.codebase.navigator import CodebaseNavigator
from gemmaswe.codebase.patcher import CodePatcher
from gemmaswe.test_runner.runner import TestRunner, TestResult
from gemmaswe.agent.prompts import SWE_SYSTEM_PROMPT, AVAILABLE_TOOLS
from gemmaswe.agent.auditor import CodeAuditor

logger = logging.getLogger(__name__)

class AgentStepEvent(BaseModel):
    step_number: int
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    status: str = "running"

class GemmaSweAgent:
    """Autonomous Software Engineering Agent powered by Gemma."""

    def __init__(
        self,
        repo_path: str,
        client: Optional[BaseGemmaClient] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.repo_path = repo_path
        self.client = client or get_gemma_client()
        self.navigator = CodebaseNavigator(repo_path)
        self.patcher = CodePatcher(repo_path)
        self.test_runner = TestRunner(repo_path)
        self.event_callback = event_callback or (lambda event: None)

        self.history: List[Dict[str, str]] = []
        self.steps: List[AgentStepEvent] = []
        self.explanation: str = ""
        self.final_test_result: Optional[TestResult] = None
        self.audit_report: Optional[Dict[str, Any]] = None

    def _emit(self, event_type: str, data: Dict[str, Any]):
        payload = {"type": event_type, "timestamp": None, **data}
        self.event_callback(payload)

    def run(self, task_description: str, test_command: Optional[str] = None) -> Dict[str, Any]:
        """Execute the autonomous engineering loop to solve the task."""
        self._emit("start", {
            "task": task_description,
            "model": self.client.get_model_identifier(),
            "repo": str(self.navigator.repo_path)
        })

        # Step 0: Run initial baseline tests
        self._emit("status", {"message": "Establishing initial test baseline..."})
        baseline = self.test_runner.run_tests(custom_command=test_command)
        self._emit("baseline", {
            "passed": baseline.passed,
            "failed": baseline.failed,
            "total": baseline.total,
            "success": baseline.success
        })

        # Initialize conversation
        overview = self.navigator.get_repo_overview()
        initial_user_prompt = f"""TASK:
{task_description}

REPOSITORY OVERVIEW:
Root: {overview['root']}
Total Files: {overview['total_files']}
Configurations: {overview['configurations']}
Existing Tests: {overview['test_files']}
Sample Source Files: {overview['sample_sources']}

INITIAL TEST BASELINE:
Status: {"All baseline tests passing" if baseline.success else f"{baseline.failed} tests failing initially"}
Passed Baseline Tests: {list(baseline.passed_tests)[:10]}
Failed Baseline Tests: {list(baseline.failed_tests)[:10]}

Please inspect the code, formulate a plan, make minimal changes, and verify all tests pass with zero regressions.
"""

        self.history = [
            {"role": "system", "content": SWE_SYSTEM_PROMPT},
            {"role": "user", "content": initial_user_prompt}
        ]

        iteration = 0
        solved = False

        while iteration < config.max_iterations and not solved:
            iteration += 1
            self._emit("step_start", {"step": iteration})

            # Call Gemma
            try:
                gemma_resp = self.client.generate(self.history, tools=AVAILABLE_TOOLS)
            except Exception as e:
                err_msg = f"LLM Generation Error: {e}"
                logger.error(err_msg)
                self._emit("error", {"error": err_msg})
                break

            thought = gemma_resp.thought
            tool_call = gemma_resp.tool_call

            step_event = AgentStepEvent(
                step_number=iteration,
                thought=thought,
                action=tool_call["name"] if tool_call else None,
                action_input=tool_call["arguments"] if tool_call else None
            )
            self._emit("thought", {"step": iteration, "thought": thought})

            if not tool_call:
                # Gemma responded with text only
                self.history.append({"role": "assistant", "content": gemma_resp.raw_content})
                self.history.append({
                    "role": "user",
                    "content": "Please specify an action tool call in JSON format or call `finish` if you are done."
                })
                continue

            action_name = tool_call["name"]
            args = tool_call.get("arguments", {})

            self._emit("tool_call", {"step": iteration, "action": action_name, "args": args})

            # Execute tool
            obs = self._dispatch_tool(action_name, args, test_command=test_command)
            step_event.observation = str(obs)
            self.steps.append(step_event)

            self._emit("tool_result", {"step": iteration, "action": action_name, "result": obs})

            # Format tool turn for history
            assistant_content = f"Thought: {thought}\n```json\n" + json.dumps({"action": action_name, "action_input": args}) + "\n```"
            self.history.append({"role": "assistant", "content": assistant_content})
            self.history.append({"role": "user", "content": f"Observation:\n{obs}"})

            if action_name == "finish":
                # Check if tests pass
                verify_test = self.test_runner.run_tests(custom_command=test_command)
                self.final_test_result = verify_test

                if not verify_test.success and config.max_test_retries > 0:
                    # Reject finish if tests are failing
                    rejection_msg = f"WARNING: You called finish, but tests are failing!\nFailures:\n{verify_test.output[-800:]}\nPlease fix the failing tests before finishing."
                    self.history.append({"role": "user", "content": rejection_msg})
                    self._emit("warning", {"message": "Finish rejected: tests still failing. Retrying..."})
                else:
                    self.explanation = args.get("explanation", thought)
                    solved = True
                    break

        # If loop ended without finish, run final verification test
        if not self.final_test_result:
            self.final_test_result = self.test_runner.run_tests(custom_command=test_command)

        # Run auditor
        self.audit_report = CodeAuditor.audit_patch(
            patcher=self.patcher,
            navigator=self.navigator,
            final_test_result=self.final_test_result,
            explanation=self.explanation or "Changes applied."
        )

        diff_summary = self.patcher.get_summary_diff()
        result = {
            "success": self.final_test_result.success and (len(self.final_test_result.regressions) == 0),
            "iterations": iteration,
            "explanation": self.explanation,
            "diff": diff_summary["diff"],
            "modified_files": diff_summary["modified_files"],
            "test_summary": {
                "total": self.final_test_result.total,
                "passed": self.final_test_result.passed,
                "failed": self.final_test_result.failed,
                "regressions": self.final_test_result.regressions
            },
            "audit": self.audit_report
        }

        self._emit("complete", result)
        return result

    def _dispatch_tool(self, name: str, args: Dict[str, Any], test_command: Optional[str] = None) -> Any:
        try:
            if name == "get_repo_overview":
                return self.navigator.get_repo_overview()

            elif name == "list_files":
                d = args.get("directory", ".")
                p = args.get("pattern", "*")
                return self.navigator.list_files(sub_dir=d, pattern=p)

            elif name == "search_code":
                q = args.get("query", "")
                is_reg = args.get("is_regex", False)
                return self.navigator.search_code(query=q, is_regex=is_reg)

            elif name == "read_file":
                path = args.get("path", "")
                s = args.get("start_line")
                e = args.get("end_line")
                res = self.navigator.read_file(path, start_line=s, end_line=e)
                return res.get("content", res.get("error"))

            elif name == "apply_patch":
                path = args.get("path", "")
                old_text = args.get("old_text", "")
                new_text = args.get("new_text", "")
                
                # Check for fake imports before applying
                invalids = self.navigator.validate_code_imports(new_text)
                warning_notice = ""
                if invalids:
                    warning_notice = f"\nWARNING: Found potentially unimported / nonexistent modules: {invalids}. Ensure they exist!"

                patch_res = self.patcher.apply_replacement(path, old_text, new_text)
                if not patch_res["success"]:
                    return patch_res["error"]
                return f"{patch_res['message']}{warning_notice}"

            elif name == "write_file":
                path = args.get("path", "")
                content = args.get("content", "")
                invalids = self.navigator.validate_code_imports(content)
                warning_notice = ""
                if invalids:
                    warning_notice = f"\nWARNING: Found unverified modules: {invalids}."
                write_res = self.patcher.write_file(path, content)
                return f"{write_res['message']}{warning_notice}"

            elif name == "run_tests":
                target = args.get("test_target")
                res = self.test_runner.run_tests(custom_command=test_command, test_target=target)
                status_str = "PASSED" if res.success else "FAILED"
                reg_str = f"REGRESSIONS DETECTED: {res.regressions}" if res.regressions else "NO REGRESSIONS"
                return f"Tests {status_str} ({res.passed} passed, {res.failed} failed). {reg_str}\nOutput:\n{res.output[-1000:]}"

            elif name == "rollback":
                p = args.get("path")
                reverted = self.patcher.rollback(p)
                return f"Reverted files: {reverted}"

            elif name == "finish":
                return f"Finished with explanation: {args.get('explanation', '')}"

            else:
                return f"Unknown tool: '{name}'. Available tools: {[t.name for t in AVAILABLE_TOOLS]}"

        except Exception as e:
            return f"Error executing tool '{name}': {e}"
