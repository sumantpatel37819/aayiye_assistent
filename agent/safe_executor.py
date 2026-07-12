"""
agent/safe_executor.py — Generated Python code ko safely execute karta hai.

Features:
  - stdout/stderr capture
  - Dangerous command blocklist (system destructive ops)
  - User confirmation before running (can be set to auto-approve)
"""

import sys
import io
import re
import os


# ─────────────────────────────────────────────────────────────────
# Dangerous patterns — ye code kabhi execute nahi hoga
# ─────────────────────────────────────────────────────────────────
_BLOCKLIST = [
    r"shutil\.rmtree\s*\(\s*['\"]?/",       # rmtree on root
    r"os\.remove\s*\(\s*['\"]?/",            # remove on root path
    r"subprocess.*\b(format|del\s+/|rm\s+-rf)\b",  # shell destructive
    r"rmdir\s*/s\s*/q",                      # Windows rmdir /s /q
    r"__import__\s*\(\s*['\"]os['\"]",       # dynamic os import attempt
]
_BLOCK_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _BLOCKLIST]


def _is_dangerous(code: str) -> tuple[bool, str]:
    """Returns (True, reason) if code matches blocklist."""
    for pattern in _BLOCK_PATTERNS:
        match = pattern.search(code)
        if match:
            return True, f"Blocked pattern: `{match.group()}`"
    return False, ""


def execute_code(code: str, cwd: str = None, auto_approve: bool = False) -> str:
    """
    Python code ko safely execute karo.

    Args:
        code         : Python code string
        cwd          : Working directory for the code
        auto_approve : Agar True ho toh user confirmation nahi maangega

    Returns:
        str: stdout output ya error message
    """
    if not code.strip():
        return "❌ Koi executable code generate nahi hua."

    # Safety check
    dangerous, reason = _is_dangerous(code)
    if dangerous:
        return f"🚫 Code execute nahi kiya — Dangerous operation detect hua:\n  {reason}"

    # Show the code to the user
    print("\n" + "─" * 50)
    print("📝 Generated Code:")
    print("─" * 50)
    print(code)
    print("─" * 50)

    # User confirmation
    if not auto_approve:
        confirm = input("\n▶ Ye code chalayein? (y/n): ").strip().lower()
        if confirm not in ("y", "yes", "ha", "haan"):
            return "⏭ Code execute nahi kiya — aapne cancel kiya."

    # Execute the code
    print("\n⚙ Code execute ho raha hai...\n")

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    exec_globals = {
        "__builtins__": __builtins__,
        "__name__": "__main__",
    }

    # Change to the working directory if specified
    original_cwd = os.getcwd()
    if cwd:
        try:
            os.chdir(cwd)
        except Exception:
            pass

    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture
        exec(code, exec_globals)  # noqa: S102
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        output = stdout_capture.getvalue().strip()
        errors = stderr_capture.getvalue().strip()

        if errors:
            result = f"✅ Done (with warnings):\n{output}\n\n⚠ Warnings:\n{errors}"
        else:
            result = f"✅ Done:\n{output}" if output else "✅ Task complete! Koi output print nahi hua."

    except Exception as e:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        result = f"❌ Execution error: {type(e).__name__}: {e}"
    finally:
        os.chdir(original_cwd)

    return result
