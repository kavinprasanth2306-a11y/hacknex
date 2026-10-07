"""AST-based symbol extraction and validation for Python codebases."""

import ast
from pathlib import Path
from typing import Dict, List, Any, Optional

class AstIndexer:
    """Extracts symbols, function signatures, classes, and imports to prevent hallucination."""

    @staticmethod
    def inspect_python_file(file_path: Path) -> Dict[str, Any]:
        """Extract functions, classes, and imports from a Python file."""
        if not file_path.is_file() or file_path.suffix != ".py":
            return {"error": "Not a Python file"}

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except Exception as e:
            return {"error": f"Failed to parse AST: {e}"}

        functions = []
        classes = []
        imports = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "args": args,
                    "docstring": ast.get_docstring(node)
                })
            elif isinstance(node, ast.ClassDef):
                methods = []
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append({
                            "name": child.name,
                            "line": child.lineno,
                            "args": [arg.arg for arg in child.args.args]
                        })
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "methods": methods,
                    "docstring": ast.get_docstring(node)
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)

        return {
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "lines_of_code": len(content.splitlines())
        }

    @staticmethod
    def get_known_imports(repo_root: Path) -> List[str]:
        """Collect all packages and local modules genuinely imported in the repository."""
        all_imports = set()
        for p in repo_root.rglob("*.py"):
            if any(part in p.parts for part in [".git", "__pycache__", ".venv", "venv", ".pytest_cache"]):
                continue
            info = AstIndexer.inspect_python_file(p)
            for imp in info.get("imports", []):
                top_pkg = imp.split(".")[0]
                if top_pkg:
                    all_imports.add(top_pkg)
        return sorted(list(all_imports))
