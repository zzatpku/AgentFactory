"""
Meta-Agent: An agent that creates, runs, and optimizes question-specific subagents.
Now with Skills support - all actions are unified as skills.
"""

import os
import sys
from typing import Any, Dict, Optional
from llm import call_llm as _call_llm_raw
from skills_utils import (
    get_skill_instructions,
    get_subagent_skill_instructions,
    parse_skill_md,
    SUBAGENT_SKILLS_DIR
)

# Get absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(SCRIPT_DIR, "skills")
WORKSPACE_DIR = os.path.join(SCRIPT_DIR, "workspace")


def call_llm(system: str, messages: list, max_tokens: int = 8000) -> Dict[str, Any]:
    """Wrapper for call_llm that returns Dict format for meta_agent use."""
    response = _call_llm_raw(system, messages, max_tokens)
    if response.startswith("Error:"):
        return {"success": False, "error": response}
    return {"success": True, "response": response}


def write_file(path: str, content: str) -> Dict[str, Any]:
    """Write a file."""
    try:
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "path": path}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_skill_description(skill_name: str) -> Dict[str, Any]:
    """Get the description of any skill (meta, tool, or saved subagent)."""
    try:
        instructions = get_skill_instructions(skill_name)
        if instructions:
            # If this is a saved subagent skill, append hint about viewing code
            if get_subagent_skill_instructions(skill_name) is not None:
                instructions += "\n\n**Tip**: If you think this skill could be helpful for your current task, you can use `view_subagent_code` to inspect its source code. If not, skip this step."
            return {"success": True, "skill_name": skill_name, "description": instructions}
        else:
            return {"success": False, "error": f"Skill not found: {skill_name}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_python_file(path: str, question: str = "", timeout: int = 600, work_dir: str = None) -> Dict[str, Any]:
    """Run a Python file by dynamically importing it and calling its main(query) function.

    The subagent's main(query) should return a dict with 'answer' and 'summary' keys.

    Args:
        path: Absolute path to the Python file to run
        question: Question to pass to main(query)
        timeout: Execution timeout in seconds (default: 600)
        work_dir: Working directory for file output. If provided, os.chdir to this
                  directory instead of the subagent's own directory. This ensures
                  generated files (png, md, etc.) are written to the workspace.

    Returns:
        Dict with success, answer, summary (or error on failure)
    """
    import importlib.util
    import signal
    from dotenv import load_dotenv

    if not os.path.exists(path):
        return {"success": False, "error": f"File not found: {path}"}

    # Switch to subagent environment variables
    load_dotenv()
    original_env = {
        "LLM_URL": os.environ.get("LLM_URL"),
        "LLM_API_KEY": os.environ.get("LLM_API_KEY"),
        "LLM_MODEL": os.environ.get("LLM_MODEL"),
        "LLM_PROTOCOL": os.environ.get("LLM_PROTOCOL")
    }
    os.environ["LLM_URL"] = os.getenv("SUBAGENT_URL", "")
    os.environ["LLM_API_KEY"] = os.getenv("SUBAGENT_API_KEY", "")
    os.environ["LLM_MODEL"] = os.getenv("SUBAGENT_MODEL", "")
    os.environ["LLM_PROTOCOL"] = os.getenv("SUBAGENT_PROTOCOL", "OPENAI_STYLE")

    # Ensure SCRIPT_DIR is on sys.path so subagent can import tools, llm, etc.
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)

    # Also add the subagent's own directory so it can do relative imports
    subagent_dir = os.path.dirname(path)
    if subagent_dir not in sys.path:
        sys.path.insert(0, subagent_dir)

    # Save and switch cwd:
    # - If work_dir is provided (e.g. workspace), chdir there so generated files
    #   (png, md, etc.) are written to the workspace instead of the skill directory.
    # - Otherwise, chdir to the subagent's own directory (for workspace-based runs).
    original_cwd = os.getcwd()
    run_dir = work_dir if work_dir else subagent_dir

    try:
        os.chdir(run_dir)

        # Dynamically load the module from file path
        module_name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, 'main'):
            return {"success": False, "error": f"No main() function found in {path}"}

        # Call main(query) with timeout via signal alarm (Unix only)
        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Execution timed out ({timeout}s limit)")

        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
        try:
            result = module.main(question)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Validate return value
        if not isinstance(result, dict):
            return {"success": False, "error": f"main() must return a dict, got {type(result).__name__}"}

        return {
            "success": True,
            "answer": result.get("answer", ""),
            "summary": result.get("summary", ""),
        }

    except TimeoutError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        import traceback
        return {"success": False, "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"}
    finally:
        os.chdir(original_cwd)
        # Restore meta agent environment variables
        for key, value in original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]


def _get_skill_entry_file(skill_name: str) -> Optional[str]:
    """Get the entry_file from a saved subagent skill's SKILL.md frontmatter."""
    if not os.path.exists(SUBAGENT_SKILLS_DIR):
        return None

    for dirname in os.listdir(SUBAGENT_SKILLS_DIR):
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md):
            continue

        parsed = parse_skill_md(skill_md)
        if parsed and (parsed["name"] == skill_name or dirname == skill_name):
            return parsed.get("entry_file")

    return None


def _get_skill_directory(skill_name: str) -> Optional[str]:
    """Get the directory path for a skill by name."""
    if not os.path.exists(SUBAGENT_SKILLS_DIR):
        return None

    for dirname in os.listdir(SUBAGENT_SKILLS_DIR):
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, dirname)
        if not os.path.isdir(skill_dir):
            continue

        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md):
            continue

        parsed = parse_skill_md(skill_md)
        if parsed and (parsed["name"] == skill_name or dirname == skill_name):
            return skill_dir

    return None


def run_skill(skill_name: str, question: str, timeout: int = 600, workspace: str = None) -> Dict[str, Any]:
    """Run a saved subagent skill with a given question.

    Reads entry_file from SKILL.md frontmatter to determine which .py to execute.

    Args:
        skill_name: Name of the saved skill to run
        question: Question to pass to the skill's main(query)
        timeout: Execution timeout in seconds
        workspace: Workspace directory for file output. If provided, generated files
                   will be written here instead of the skill's own directory.
    """
    # Find the skill directory
    skill_dir = _get_skill_directory(skill_name)
    if skill_dir is None:
        return {"success": False, "error": f"Skill not found: {skill_name}"}

    # Get entry_file from SKILL.md frontmatter
    entry_file = _get_skill_entry_file(skill_name)

    if entry_file:
        target_file = os.path.join(skill_dir, entry_file)
        if not os.path.exists(target_file):
            # entry_file specified but doesn't exist, try fallback
            target_file = None
    else:
        target_file = None

    # Fallback: try subagent.py, then first .py file found
    if target_file is None:
        fallback = os.path.join(skill_dir, "subagent.py")
        if os.path.exists(fallback):
            target_file = fallback
        else:
            # Find any .py file
            py_files = [f for f in os.listdir(skill_dir) if f.endswith('.py')]
            if py_files:
                target_file = os.path.join(skill_dir, py_files[0])
            else:
                return {"success": False, "error": f"No .py files found in {skill_dir}"}

    return run_python_file(target_file, question, timeout, work_dir=workspace)
