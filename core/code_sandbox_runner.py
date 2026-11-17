import subprocess
import sys
import tempfile
import os


def run_python_code(code: str, timeout: int = 5) -> dict:
    """Executes Python code in a temporary file with a timeout and captures output/errors."""
    if not code.strip():
        return {"success": False, "stdout": "", "stderr": "No code provided to run."}

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(code)
            temp_path = tmp.name

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            [sys.executable, "-u", temp_path],
            input="",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"⏱️ Execution timed out after {timeout} seconds (check for infinite loops)."
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"⚠️ Runner Error: {str(e)}"
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)