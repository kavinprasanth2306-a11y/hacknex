"""System prompts, instruction templates, and tool schemas for GemmaSWE."""

from typing import List
from gemmaswe.llm.base import ToolDefinition

SWE_SYSTEM_PROMPT = """You are GemmaSWE, an elite Autonomous AI Software Engineering Agent powered by Google's Gemma model.
Your objective is to inspect an unfamiliar real-world codebase, locate relevant files, implement a requested change or bugfix, and verify that nothing breaks.

CRITICAL RULES YOU MUST STRICTLY FOLLOW:
1. REGRESSION IMMUNITY: Existing tests MUST still pass. If you break anything that was working, you fail the challenge.
2. NO HALLUCINATED IMPORTS OR APIS: You must only use APIs, imports, and methods that genuinely exist in the codebase or standard library. Never invent fake modules.
3. MINIMAL & CLEAN CHANGES: Change only the lines necessary. Do not rewrite unrelated functions or reformats.
4. TEST-DRIVEN VERIFICATION: Always run the test suite to confirm your change fixes the issue and all existing tests pass. If tests fail, analyze the traceback and self-correct.

WORKFLOW:
Step 1: Explore the codebase layout and locate relevant files and tests using `get_repo_overview` or `list_files`.
Step 2: Run tests to understand the current working baseline and observe any failing acceptance tests.
Step 3: Read the target files around the relevant logic using `read_file` or `search_code`.
Step 4: Formulate a precise fix or feature addition using real codebase APIs.
Step 5: Apply the fix using `apply_patch`.
Step 6: Run tests using `run_tests`. If tests fail, inspect the error, self-correct, or rollback if needed.
Step 7: Once all tests pass and no regressions exist, call `finish` with a detailed explanation of the bug, the root cause, and the solution.

FORMATTING INSTRUCTIONS:
To invoke a tool, respond with:
Thought: <Your reasoning about what to explore, check, or fix>
```json
{
  "action": "<tool_name>",
  "action_input": {
     <parameters>
  }
}
```
"""

AVAILABLE_TOOLS: List[ToolDefinition] = [
    ToolDefinition(
        name="get_repo_overview",
        description="Get high-level map of the codebase, including config files, test directories, and known dependencies.",
        parameters={}
    ),
    ToolDefinition(
        name="list_files",
        description="List files in the repository or a specific subfolder matching an optional glob pattern.",
        parameters={
            "directory": {"type": "string", "description": "Subdirectory to scan, default '.'"},
            "pattern": {"type": "string", "description": "Glob pattern such as '*.py', default '*'"}
        }
    ),
    ToolDefinition(
        name="search_code",
        description="Search for a text string or regex pattern across files in the codebase.",
        parameters={
            "query": {"type": "string", "description": "Substring or regex pattern to search"},
            "is_regex": {"type": "boolean", "description": "Whether query is a regular expression, default false"}
        }
    ),
    ToolDefinition(
        name="read_file",
        description="Read lines from a file with 1-indexed line numbers.",
        parameters={
            "path": {"type": "string", "description": "Relative path to file"},
            "start_line": {"type": "integer", "description": "Starting line number (1-based), optional"},
            "end_line": {"type": "integer", "description": "Ending line number, optional"}
        }
    ),
    ToolDefinition(
        name="apply_patch",
        description="Replace exact existing text in a file with new text.",
        parameters={
            "path": {"type": "string", "description": "Relative path to target file"},
            "old_text": {"type": "string", "description": "Exact text substring to be replaced"},
            "new_text": {"type": "string", "description": "Replacement text"}
        }
    ),
    ToolDefinition(
        name="write_file",
        description="Write or overwrite an entire file, or create a new test file.",
        parameters={
            "path": {"type": "string", "description": "Relative path to file"},
            "content": {"type": "string", "description": "Complete file content"}
        }
    ),
    ToolDefinition(
        name="run_tests",
        description="Run test suite to verify tests pass and detect any regressions.",
        parameters={
            "test_target": {"type": "string", "description": "Optional specific test path or test name to run"}
        }
    ),
    ToolDefinition(
        name="rollback",
        description="Roll back modified files to pristine initial state if changes broke existing tests.",
        parameters={
            "path": {"type": "string", "description": "Optional specific file to revert, or empty to revert all"}
        }
    ),
    ToolDefinition(
        name="finish",
        description="Finish the task after verifying all tests pass and documenting the fix.",
        parameters={
            "explanation": {"type": "string", "description": "Clear explanation of the bug, root cause, and solution"}
        }
    )
]
