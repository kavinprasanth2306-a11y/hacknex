"""Repository exploration, file reading, code searching, and architectural mapping."""

import os
import re
import importlib.util
from pathlib import Path
from typing import List, Dict, Any, Optional
from gemmaswe.codebase.ast_indexer import AstIndexer

IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", 
    "node_modules", ".idea", ".vscode", "dist", "build", ".mypy_cache"
}

class CodebaseNavigator:
    """Provides grounded exploration of large codebases for GemmaSWE."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repo_path}")
        self.known_imports = AstIndexer.get_known_imports(self.repo_path)

    def list_files(self, sub_dir: str = ".", pattern: str = "*") -> List[Dict[str, Any]]:
        """List files in the codebase recursively with metadata."""
        base = (self.repo_path / sub_dir).resolve()
        if not base.exists():
            return []

        results = []
        for p in base.rglob(pattern):
            if any(part in p.parts for part in IGNORE_DIRS):
                continue
            if p.is_file():
                rel_path = p.relative_to(self.repo_path).as_posix()
                results.append({
                    "path": rel_path,
                    "size_bytes": p.stat().st_size,
                    "suffix": p.suffix
                })
        return sorted(results, key=lambda x: x["path"])

    def read_file(self, relative_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Read a file safely with 1-indexed line numbers."""
        file_path = (self.repo_path / relative_path).resolve()
        if not file_path.exists():
            return {"error": f"File not found: {relative_path}"}
        if not file_path.is_file():
            return {"error": f"Path is not a file: {relative_path}"}

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            total_lines = len(lines)

            s = 1 if start_line is None else max(1, start_line)
            e = total_lines if end_line is None else min(total_lines, end_line)

            selected_lines = [
                f"{i:4d} | {lines[i-1]}"
                for i in range(s, e + 1)
            ]
            return {
                "path": relative_path,
                "total_lines": total_lines,
                "range": [s, e],
                "content": "\n".join(selected_lines),
                "raw_content": "\n".join(lines[s-1:e])
            }
        except Exception as ex:
            return {"error": f"Error reading file: {ex}"}

    def search_code(self, query: str, is_regex: bool = False, path_pattern: str = "*") -> List[Dict[str, Any]]:
        """Search for literal string or regex pattern across codebase files."""
        matches = []
        flags = 0 if is_regex else re.IGNORECASE
        pattern = re.compile(query if is_regex else re.escape(query), flags)

        for p in self.repo_path.rglob(path_pattern):
            if any(part in p.parts for part in IGNORE_DIRS):
                continue
            if not p.is_file():
                continue
            # Skip large binaries
            if p.stat().st_size > 1_500_000:
                continue

            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                for idx, line in enumerate(lines, 1):
                    if pattern.search(line):
                        matches.append({
                            "file": p.relative_to(self.repo_path).as_posix(),
                            "line_number": idx,
                            "line_content": line.strip()
                        })
                        if len(matches) >= 50:
                            return matches
            except Exception:
                continue

        return matches

    def get_repo_overview(self) -> Dict[str, Any]:
        """Generate architectural summary, entry points, configs, and test files."""
        files = self.list_files()
        configs = []
        tests = []
        source_files = []

        for f in files:
            path = f["path"]
            filename = Path(path).name
            if filename in ["pyproject.toml", "setup.py", "requirements.txt", "package.json", "Cargo.toml", "go.mod", "Makefile"]:
                configs.append(path)
            elif "test" in path.lower() or filename.startswith("test_") or filename.endswith("_test.py"):
                tests.append(path)
            elif f["suffix"] in [".py", ".js", ".ts", ".go", ".rs", ".java"]:
                source_files.append(path)

        return {
            "root": str(self.repo_path),
            "total_files": len(files),
            "source_files_count": len(source_files),
            "configurations": configs,
            "test_files": tests,
            "sample_sources": source_files[:15],
            "known_dependencies": self.known_imports
        }

    def validate_code_imports(self, code_snippet: str) -> List[str]:
        """
        Verify that imports introduced do not hallucinate APIs.
        Returns list of invalid / hallucinated import warnings.
        """
        invalid_imports = []
        try:
            tree = ast_parse = None
            import ast
            tree = ast.parse(code_snippet)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        names = [node.module.split(".")[0]]
                
                for pkg in names:
                    if pkg and pkg not in self.known_imports:
                        # Check if it's standard library or installed
                        spec = importlib.util.find_spec(pkg)
                        # Also check if it's a local file or folder in repo
                        local_exists = (self.repo_path / pkg).exists() or (self.repo_path / f"{pkg}.py").exists()
                        if spec is None and not local_exists:
                            invalid_imports.append(pkg)
        except Exception:
            pass
        return list(set(invalid_imports))
