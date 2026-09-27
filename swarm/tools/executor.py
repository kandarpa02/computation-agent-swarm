import subprocess
import tempfile
from agents import function_tool

@function_tool
def python_executor(code)-> str:
    with tempfile.TemporaryFile(
        'w', 
        suffix='.py', 
        delete=False) as f:

        f.write(code)
        path = f.name

        result = subprocess.run(
        ["python", path],
        capture_output=True,
        text=True,
        timeout=10
    )

    return (result.stdout + result.stderr)

