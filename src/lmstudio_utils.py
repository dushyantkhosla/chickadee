"""
LM Studio server and model loading utilities.

Provides CLI-based helpers for starting the LM Studio server and loading models.
These functions are dependency-free (no `lmstudio` package required) and work
with any project using subprocess to call the `lms` CLI.

Example:
    from lmstudio_utils import ensure_server_running, load_model

    ensure_server_running()
    load_model("qwen3.5-4b-mlx")
"""

import subprocess
import time


def ensure_server_running(timeout: int = 30) -> bool:
    """Check if LM Studio server is running, start it if not.

    Args:
        timeout: Maximum seconds to wait for server to start. Default 30.

    Returns:
        True if server is running, False on timeout.
    """
    result = subprocess.run(
        ["lms", "server", "status"],
        capture_output=True,
        text=True,
    )
    stderr_lower = result.stderr.strip().lower()

    if "running" in stderr_lower or "running on port 1234" in stderr_lower:
        print("LM Studio server is already running.")
        return True

    print("LM Studio server is not running. Starting...")
    subprocess.run(["lms", "server", "start"], capture_output=True)

    elapsed = 0
    interval = 5
    while elapsed < timeout:
        time.sleep(interval)
        elapsed += interval
        status = subprocess.run(
            ["lms", "server", "status"],
            capture_output=True,
            text=True,
        )
        if "running" in status.stderr.strip().lower():
            print("LM Studio server is now running.")
            return True

    print(f"Timeout after {timeout}s waiting for server to start.")
    return False


def load_model(model_name: str, default_model: str = "liquid/lfm2.5-1.2b", ttl: int = 600) -> str:
    """Load a model into LM Studio if not already loaded.

    Args:
        model_name: Exact model identifier (from `lms ls`).
        default_model: Fallback model if model_name is not found.
        ttl: Time-to-live in seconds for the loaded model. Default 600.

    Returns:
        The model identifier that was loaded (or selected).
    """
    ls_result = subprocess.run(
        ["lms", "ls"],
        capture_output=True,
        text=True,
    )
    available_models = ls_result.stdout

    if model_name and model_name in available_models:
        selected_model = model_name
    else:
        print(f"Model '{model_name}' not found. Using default: {default_model}")
        selected_model = default_model

    ps_result = subprocess.run(
        ["lms", "ps"],
        capture_output=True,
        text=True,
    )

    if selected_model not in ps_result.stdout:
        subprocess.run(
            ["lms", "load", selected_model, "--ttl", str(ttl)],
            capture_output=True,
            check=True,
        )
        print(f"Loaded model: {selected_model}")
    else:
        print(f"Model already loaded: {selected_model}")

    return selected_model


def ensure_model_loaded(model_name: str, default_model: str = "liquid/lfm2.5-1.2b") -> str:
    """Convenience function: start server if needed, then load model.

    Args:
        model_name: Model identifier to load.
        default_model: Fallback model if model_name is not available.

    Returns:
        The model identifier that was loaded.
    """
    ensure_server_running()
    return load_model(model_name, default_model=default_model)
