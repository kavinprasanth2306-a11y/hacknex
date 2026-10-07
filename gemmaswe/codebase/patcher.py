"""Safe, atomic code patcher with rollback and regression protection."""

import difflib
from pathlib import Path
from typing import Dict, List, Any, Optional

class CodePatcher:
    """Manages file modifications, atomic backups, diff tracking, and rollbacks."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        # Backups map: relative_path -> original content string (or None if newly created)
        self.backups: Dict[str, Optional[str]] = {}
        self.modified_files: List[str] = []

    def _ensure_backup(self, rel_path: str, full_path: Path):
        if rel_path not in self.backups:
            if full_path.exists():
                self.backups[rel_path] = full_path.read_text(encoding="utf-8", errors="replace")
            else:
                self.backups[rel_path] = None  # File was created fresh

    def apply_replacement(self, rel_path: str, old_text: str, new_text: str) -> Dict[str, Any]:
        """Replace an exact substring within a file."""
        file_path = (self.repo_path / rel_path).resolve()
        if not file_path.exists():
            return {"success": False, "error": f"File does not exist: {rel_path}"}

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            if old_text not in content:
                # Try normalized whitespace match
                normalized_old = "\n".join(line.strip() for line in old_text.strip().splitlines())
                normalized_content = "\n".join(line.strip() for line in content.splitlines())
                if normalized_old not in normalized_content:
                    return {
                        "success": False,
                        "error": "The specified 'old_text' was not found in the target file. Ensure exact match including indentations."
                    }

            self._ensure_backup(rel_path, file_path)
            updated_content = content.replace(old_text, new_text, 1)
            file_path.write_text(updated_content, encoding="utf-8")
            if rel_path not in self.modified_files:
                self.modified_files.append(rel_path)

            return {
                "success": True,
                "file": rel_path,
                "message": f"Successfully updated {rel_path}"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to patch file: {e}"}

    def write_file(self, rel_path: str, content: str) -> Dict[str, Any]:
        """Write whole file content (or create new file)."""
        file_path = (self.repo_path / rel_path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_backup(rel_path, file_path)

        try:
            file_path.write_text(content, encoding="utf-8")
            if rel_path not in self.modified_files:
                self.modified_files.append(rel_path)
            return {"success": True, "file": rel_path, "message": f"Wrote content to {rel_path}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to write file: {e}"}

    def rollback(self, rel_path: Optional[str] = None) -> List[str]:
        """Rollback one file or all files to their pristine initial state."""
        reverted = []
        targets = [rel_path] if rel_path else list(self.backups.keys())

        for target in targets:
            if target in self.backups:
                path = (self.repo_path / target).resolve()
                orig = self.backups[target]
                if orig is None:
                    # File was newly created -> remove it
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(orig, encoding="utf-8")
                reverted.append(target)
                if target in self.modified_files:
                    self.modified_files.remove(target)

        if not rel_path:
            self.backups.clear()
            self.modified_files.clear()

        return reverted

    def get_summary_diff(self) -> Dict[str, Any]:
        """Return unified diff and metrics (lines added/removed)."""
        full_diff = []
        lines_added = 0
        lines_removed = 0

        for rel_path, orig in self.backups.items():
            curr_path = (self.repo_path / rel_path).resolve()
            curr = curr_path.read_text(encoding="utf-8", errors="replace") if curr_path.exists() else ""
            orig_text = orig or ""

            diff = list(difflib.unified_diff(
                orig_text.splitlines(keepends=True),
                curr.splitlines(keepends=True),
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}"
            ))

            for line in diff:
                if line.startswith("+") and not line.startswith("+++"):
                    lines_added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    lines_removed += 1

            full_diff.extend(diff)

        diff_str = "".join(full_diff)
        return {
            "diff": diff_str,
            "modified_files": list(self.modified_files),
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "is_minimal": (lines_added + lines_removed) < 150
        }
