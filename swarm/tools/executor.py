
import subprocess
import tempfile
import os
import sys
from agents import function_tool


@function_tool
def python_executor(code: str) -> str:
    """Execute Python code and return its output and exit status."""

    path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            encoding="utf-8",
            delete=False
        ) as f:
            f.write(code)
            path = f.name

        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=10
        )

        return (
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    except subprocess.TimeoutExpired:
        return "Execution failed: timeout after 10 seconds."

    except Exception as e:
        return f"Execution failed: {type(e).__name__}: {e}"

    finally:
        if path and os.path.exists(path):
            os.remove(path)