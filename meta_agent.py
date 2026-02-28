"""
Meta-Agent: An agent that creates, runs, and optimizes question-specific subagents.
Now with Skills support - all actions are unified as skills.
"""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Optional
from prompts import SYSTEM_PROMPT
from skills_utils import (
    list_subagent_skills,
    list_all_skills,
    list_tool_skills,
    SUBAGENT_SKILLS_DIR
)

# Built-in skill names that cannot be used for saved subagents
BUILTIN_SKILL_NAMES = {"create_subagent", "run_subagent", "modify_subagent", "finish",
                       "list_saved_subagents", "view_subagent_code",
                       "get_skill_description", "use_skill"}

# Get absolute paths based on script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(SCRIPT_DIR, "skills")
WORKSPACE_DIR = os.path.join(SCRIPT_DIR, "workspace")

from meta_tools import call_llm, write_file, get_skill_description, run_python_file, run_skill

class MetaAgent:
    def __init__(self, verbose: bool = True, save_on_finish: bool = True, human_confirm: bool = False):
        self.verbose = verbose
        self.save_on_finish = save_on_finish
        self.human_confirm = human_confirm
        self.trajectory = []
        self.messages = []
        self.current_workspace = None  # Will be set per question
        self.current_skills = []  # Skills specified for current subagent
        self.viewed_skill_descriptions = set()  # Track which skills have been read
        self.viewed_subagent_codes = set()  # Track which saved subagent codes have been read via view_subagent_code
        self.modified_skills = {}  # Track modified saved skills: {skill_name: {"skill_dir": ..., "workspace_files": {filename: workspace_path}}}
        self._has_created_or_modified = False  # Track if create_subagent or modify_subagent was called successfully

        os.makedirs(SKILLS_DIR, exist_ok=True)
        os.makedirs(SUBAGENT_SKILLS_DIR, exist_ok=True)
        os.makedirs(WORKSPACE_DIR, exist_ok=True)

    def log(self, msg: str):
        if self.verbose:
            print(msg)

    def _prompt_human_confirm_every_n(self) -> str:
        """Prompt human every N iterations. Returns the choice.
        action is one of: 'continue', 'restart', 'next_question'.
        """
        print("\n" + "-"*40)
        print("[Checkpoint] Choose an option:")
        print("  1. Continue - keep working on current question")
        print("  2. Restart - stop and restart current question")
        print("  3. Next - stop and move to next question")
        print("-"*40)
        while True:
            choice = input("Your choice (1/2/3): ").strip()
            if choice == "1":
                return "continue"
            elif choice == "2":
                return "restart"
            elif choice == "3":
                return "next_question"
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

    def _prompt_human_confirm(self) -> tuple:
        """Prompt human for confirmation. Returns (action, user_input).
        action is one of: 'yes', 'no', 'custom'.
        user_input is the custom instruction when action is 'custom', else None.
        """
        # Clear input.txt before each prompt so the user starts fresh
        input_file = os.path.join(SCRIPT_DIR, "input.txt")
        with open(input_file, "w", encoding="utf-8") as f:
            f.write("")

        print("\n" + "-"*40)
        print("[Human Confirm] Choose an option:")
        print("  1. Yes - continue execution")
        print("  2. No - stop execution")
        print(f"  3. Something else - write instruction to {input_file}, then enter 3")
        print("-"*40)
        while True:
            choice = input("Your choice (1/2/3): ").strip()
            if choice == "1":
                return ("yes", None)
            elif choice == "2":
                return ("no", None)
            elif choice == "3":
                with open(input_file, "r", encoding="utf-8") as f:
                    user_input = f.read().strip()
                if not user_input:
                    print("[WARN] input.txt is empty. Please write your instruction to input.txt first, then enter 3 again.")
                    continue
                print(f"[Human Confirm] Instruction from input.txt:\n{user_input}")
                return ("custom", user_input)
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

    def parse_action(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse action from LLM response using XML-style tags.

        Unified format:
            <action>skill_name</action>
            <params>{"param1": "value1"}</params>

        The action is directly the skill name (e.g., list_skills, get_skill_description,
        create_subagent, run_subagent, modify_subagent, finish, etc.)
        """
        # Extract action (which is now directly the skill name)
        action_match = re.search(r'<action>\s*(.*?)\s*</action>', response, re.DOTALL)
        if not action_match:
            return None

        action_type = action_match.group(1).strip()
        result = {"action": action_type, "params": {}}

        # Extract params (JSON format) - use greedy match to capture full content
        params_match = re.search(r'<params>\s*(.*)\s*</params>', response, re.DOTALL)
        if params_match:
            params_str = params_match.group(1).strip()
            if params_str:
                # Try direct JSON parse first
                try:
                    result["params"] = json.loads(params_str)
                except json.JSONDecodeError:
                    # Fallback: find the outermost { ... } and try to parse that
                    brace_start = params_str.find('{')
                    brace_end = params_str.rfind('}')
                    if brace_start != -1 and brace_end > brace_start:
                        json_str = params_str[brace_start:brace_end + 1]
                        try:
                            result["params"] = json.loads(json_str)
                        except json.JSONDecodeError as e:
                            self.log(f"[WARN] Failed to parse params JSON for action '{action_type}': {e}")
                            result["params"] = {}
                            result["json_parse_error"] = str(e)
                    else:
                        self.log(f"[WARN] No JSON object found in params for action '{action_type}'")
                        result["params"] = {}
                        result["json_parse_error"] = "No JSON object found in params"

        return result

    def execute_action(self, action: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        """Execute an action. The action type is directly the skill name.

        Unified format: action is the skill name, params contains the parameters.
        """
        action_type = action.get("action")
        params = action.get("params", {})

        # Only get_skill_description is exempt from description requirement
        if action_type == "get_skill_description":
            skill_name = params.get("skill_name", "")
            if not skill_name:
                return {"success": False, "error": "skill_name is required in params for get_skill_description"}
            result = get_skill_description(skill_name)
            # Track that this skill's description has been viewed
            if result.get("success"):
                self.viewed_skill_descriptions.add(skill_name)
            return result

        # All other actions (including finish, create_subagent, etc.) require reading description first
        else:
            # Check if skill description has been read
            if action_type not in self.viewed_skill_descriptions:
                return {
                    "success": False,
                    "error": f"You must call get_skill_description for '{action_type}' before using it. Read the skill's usage instructions first."
                }
            return self._execute_skill(action_type, params, question)

    def _execute_skill(self, skill_name: str, params: Dict[str, Any], question: str) -> Dict[str, Any]:
        """Execute a skill by name."""
        # Meta skills
        if skill_name == "create_subagent":
            subagent_name = params.get("skill_name", "")
            if not subagent_name:
                return {"success": False, "error": "skill_name is required for create_subagent"}
            # Check for name conflict
            reserved = BUILTIN_SKILL_NAMES | {s["name"] for s in list_tool_skills()}
            if subagent_name in reserved:
                return {"success": False, "error": f"Skill name '{subagent_name}' conflicts with a built-in skill or tool. Please choose a different name."}
            filename = params.get("filename", "subagent.py")
            code = params.get("code", "")
            self.current_skills = params.get("skills", ["local_search", "open_page"])

            # Check that all tool skills used by the subagent have been read
            unread_skills = [s for s in self.current_skills if s not in self.viewed_skill_descriptions]
            if unread_skills:
                return {
                    "success": False,
                    "error": f"Before creating a subagent, you must read the descriptions of ALL tool skills it will use. Unread skills: {', '.join(unread_skills)}. Call get_skill_description for each one first."
                }

            path = os.path.join(self.current_workspace, filename)
            result = write_file(path, code)
            if result["success"]:
                result["message"] = (
                    f"Subagent created with skills: {self.current_skills}.\n\n"
                    "IMPORTANT: Review your subagent code for generality before running it. "
                    "The `query` parameter should be the ONLY input — do NOT hardcode question-specific "
                    "values (URLs, names, numbers, search terms) in the code. Instead, parse them from `query` "
                    "at runtime so this subagent can be reused for similar tasks. "
                    "If the code has hardcoded values, call modify_subagent NOW to make it general before running."
                )
                self._has_created_or_modified = True
            return result

        elif skill_name == "run_subagent":
            # Unified run_subagent: handles both workspace files and saved skills
            # First check if skill_name parameter is provided (for saved skills)
            saved_skill_name = params.get("skill_name", "")
            if saved_skill_name:
                # Check if subagent code has been viewed before running saved subagent
                if saved_skill_name not in self.viewed_subagent_codes:
                    return {
                        "success": False,
                        "error": f"You must call view_subagent_code for '{saved_skill_name}' before running it. Read the subagent's code first using view_subagent_code."
                    }

                # Check if this skill has been modified in workspace - run workspace version
                if saved_skill_name in self.modified_skills:
                    mod_info = self.modified_skills[saved_skill_name]
                    entry_file = mod_info["entry_file"]
                    path = os.path.join(self.current_workspace, entry_file)
                    if not os.path.exists(path):
                        return {"success": False, "error": f"Modified entry file '{entry_file}' not found in workspace"}
                    query = params.get("query", question)
                    return run_python_file(path, query)

                # Check if this is a saved skill (unmodified)
                saved_skills = list_subagent_skills()
                if any(s["name"] == saved_skill_name for s in saved_skills):
                    # Run saved skill from original directory
                    query = params.get("query", question)
                    return run_skill(saved_skill_name, query, workspace=self.current_workspace)
                else:
                    return {"success": False, "error": f"Saved skill not found: {saved_skill_name}"}

            # Otherwise, treat as workspace file
            filename = params.get("filename", "subagent.py")
            path = os.path.join(self.current_workspace, filename)
            if not os.path.exists(path):
                # List available .py files to help the user
                py_files = []
                if self.current_workspace and os.path.exists(self.current_workspace):
                    py_files = [f for f in os.listdir(self.current_workspace) if f.endswith('.py')]
                return {
                    "success": False,
                    "error": f"File not found: {path}. You must specify the correct 'filename' parameter matching the one used in create_subagent. Available .py files in workspace: {py_files}"
                }
            # Allow custom query parameter, default to the original question
            query = params.get("query", question)
            return run_python_file(path, query)

        elif skill_name == "modify_subagent":
            filename = params.get("filename", "subagent.py")
            saved_skill_name = params.get("skill_name", "")

            if saved_skill_name:
                # Modifying a saved skill: copy to workspace first (if not already copied)
                from skills_utils import parse_skill_md
                from meta_tools import _get_skill_directory

                skill_dir = _get_skill_directory(saved_skill_name)
                if skill_dir is None:
                    return {"success": False, "error": f"Saved skill not found: {saved_skill_name}"}

                # Determine the entry file from SKILL.md
                skill_md = os.path.join(skill_dir, "SKILL.md")
                parsed = parse_skill_md(skill_md)
                entry_file = parsed.get("entry_file", "subagent.py") if parsed else "subagent.py"

                # Use the filename param if provided, otherwise default to entry_file
                if params.get("filename"):
                    target_filename = params["filename"]
                else:
                    target_filename = entry_file

                # Copy all .py files from skill dir to workspace if not already done for this skill
                if saved_skill_name not in self.modified_skills:
                    workspace_files = {}
                    for f in os.listdir(skill_dir):
                        if f.endswith('.py'):
                            src = os.path.join(skill_dir, f)
                            dst = os.path.join(self.current_workspace, f)
                            with open(src, 'r', encoding='utf-8') as sf:
                                with open(dst, 'w', encoding='utf-8') as df:
                                    df.write(sf.read())
                            workspace_files[f] = dst
                    self.modified_skills[saved_skill_name] = {
                        "skill_dir": skill_dir,
                        "entry_file": entry_file,
                        "workspace_files": workspace_files
                    }

                # Now modify the file in workspace
                path = os.path.join(self.current_workspace, target_filename)
                if not os.path.exists(path):
                    available = list(self.modified_skills[saved_skill_name]["workspace_files"].keys())
                    return {"success": False, "error": f"File '{target_filename}' not found in workspace copy of skill '{saved_skill_name}'. Available files: {available}"}

                with open(path, "r", encoding="utf-8") as f:
                    current_code = f.read()

                old_content = params.get("old_content", "")
                new_content = params.get("new_content", "")

                if old_content and old_content in current_code:
                    modified_code = current_code.replace(old_content, new_content, 1)
                    result = write_file(path, modified_code)
                    if result["success"]:
                        result["message"] = f"Saved skill '{saved_skill_name}' code modified in workspace. Original skill is preserved. Use run_subagent with skill_name='{saved_skill_name}' to test the modified version."
                        self._has_created_or_modified = True
                    return result
                else:
                    return {
                        "success": False,
                        "error": f"old_content not found in {target_filename}. The old_content must exactly match text in the file."
                    }
            else:
                # Modifying a workspace file (original behavior)
                path = os.path.join(self.current_workspace, filename)

                if not os.path.exists(path):
                    return {"success": False, "error": f"File not found: {filename}"}

                with open(path, "r", encoding="utf-8") as f:
                    current_code = f.read()

                old_content = params.get("old_content", "")
                new_content = params.get("new_content", "")

                if old_content and old_content in current_code:
                    modified_code = current_code.replace(old_content, new_content, 1)
                    result = write_file(path, modified_code)
                    if result["success"]:
                        result["message"] = "Subagent code modified. Now use run_subagent to execute it."
                        self._has_created_or_modified = True
                    return result
                else:
                    return {
                        "success": False,
                        "error": f"old_content not found in {filename}. The old_content must exactly match text in your subagent.py file."
                    }

        elif skill_name == "finish":
            # --- Strict validation ---
            errors = []

            # 1. 'answer' is required
            if "answer" not in params or not params["answer"]:
                errors.append("Missing required key 'answer'.")

            # 2. 'subagents' key must exist (even if empty list)
            if "subagents" not in params:
                wrong_keys = [k for k in params if k not in ("answer",)]
                hint = f" (found unexpected key(s): {wrong_keys} — did you mean 'subagents'?)" if wrong_keys else ""
                errors.append(f"Missing required key 'subagents'. Must be a list (or [] if none to save).{hint}")

            # 3. Validate each subagent entry
            subagents = params.get("subagents", [])
            if isinstance(subagents, list):
                for i, sa in enumerate(subagents):
                    if not isinstance(sa, dict):
                        errors.append(f"subagents[{i}]: must be a dict, got {type(sa).__name__}.")
                        continue
                    if not sa.get("entry_file"):
                        errors.append(f"subagents[{i}]: missing required field 'entry_file'.")
                    if not sa.get("description"):
                        errors.append(f"subagents[{i}]: missing required field 'description'.")
                    # skill_name and supersedes are mutually exclusive
                    has_skill_name = bool(sa.get("skill_name"))
                    has_supersedes = bool(sa.get("supersedes"))
                    if has_skill_name and has_supersedes:
                        errors.append(f"subagents[{i}]: 'skill_name' and 'supersedes' cannot be used together. "
                                      "Use skill_name (without supersedes) for saving a modified saved skill. "
                                      "Use supersedes (without skill_name) for saving a newly created replacement.")

            if errors:
                example = (
                    "There are 4 valid finish patterns:\n"
                    "\n"
                    "Pattern 1 — New subagent (first time creating):\n"
                    '{"answer": "...", "subagents": [{"entry_file": "...", "description": "..."}]}\n'
                    "\n"
                    "Pattern 2 — Modified saved skill (used modify_subagent with skill_name):\n"
                    '{"answer": "...", "subagents": [{"entry_file": "...", "description": "...", "skill_name": "..."}]}\n'
                    "\n"
                    "Pattern 3 — New subagent replacing an old skill (used create_subagent + supersedes):\n"
                    '{"answer": "...", "subagents": [{"entry_file": "...", "description": "...", "supersedes": "..."}]}\n'
                    "\n"
                    "Pattern 4 — Nothing to save:\n"
                    '{"answer": "...", "subagents": []}'
                )
                return {"success": False, "error": "Finish validation failed:\n" + "\n".join(f"- {e}" for e in errors) + "\n\n" + example}

            # 4. If created/modified subagents during this session but saving none, require confirmation
            if self._has_created_or_modified and isinstance(subagents, list) and len(subagents) == 0:
                confirmation = params.get("confirmation", "")
                if not confirmation or not confirmation.strip().lower().startswith("i confirm"):
                    return {
                        "success": False,
                        "error": (
                            "You created or modified subagents during this session but are saving none. "
                            "You are STRONGLY encouraged to save subagents for future reuse.\n\n"
                            "Saving a subagent has two benefits:\n"
                            "1. **Direct reuse**: When an identical or very similar task appears later, "
                            "the saved subagent can be run directly without rebuilding from scratch.\n"
                            "2. **Code reference**: Even for loosely related tasks, the saved code serves as a "
                            "working reference — use view_subagent_code to study its structure, API calls, parsing logic, "
                            "and workarounds, then create_subagent to build a new one based on it, "
                            "saving significant trial-and-error effort.\n\n"
                            "**Even if the subagent is specific to this question**, you should still save it — "
                            "just make sure the skill name and description clearly reflect its specific scope. For example:\n"
                            "- Skill name: use a descriptive name like `weather_api_parser`, `imdb_movie_lookup`, `arxiv_paper_search`\n"
                            "- Description: clearly state what specific domain/topic/API/site it handles, e.g. "
                            "'Searches and parses weather data from OpenWeatherMap API' rather than a vague 'data fetcher'\n\n"
                            "If you truly have nothing worth saving (e.g., the subagent failed completely and has no useful logic), "
                            "add a 'confirmation' key as the FIRST parameter:\n"
                            '{"confirmation": "I confirm that no subagents are worth saving because ...", '
                            '"answer": "...", "subagents": []}'
                        )
                    }

            # Don't save here - saving is deferred to after human confirmation in run()
            answer = params.get("answer", "")
            return {"success": True, "message": "Finished (saving deferred until confirmed)", "answer": answer}

        elif skill_name == "list_saved_subagents":
            try:
                skills = list_subagent_skills()
                skill_names = [{"name": s["name"]} for s in skills]
                return {"success": True, "skills": skill_names, "count": len(skill_names)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif skill_name == "view_subagent_code":
            target_name = params.get("skill_name", "")
            if not target_name:
                return {"success": False, "error": "skill_name is required for view_subagent_code"}
            # Check if this skill has been modified in workspace - show workspace version if so
            if target_name in self.modified_skills:
                mod_info = self.modified_skills[target_name]
                entry_file = mod_info["entry_file"]
                path = os.path.join(self.current_workspace, entry_file)
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as fh:
                        code = fh.read()
                    self.viewed_subagent_codes.add(target_name)
                    return {"success": True, "skill_name": target_name, "entry_file": entry_file, "code": code, "modified": True}
            # Find the skill directory and entry_file via SKILL.md
            from skills_utils import parse_skill_md
            skill_dir = None
            entry_file = None
            if os.path.exists(SUBAGENT_SKILLS_DIR):
                for dirname in os.listdir(SUBAGENT_SKILLS_DIR):
                    candidate = os.path.join(SUBAGENT_SKILLS_DIR, dirname)
                    if not os.path.isdir(candidate):
                        continue
                    skill_md = os.path.join(candidate, "SKILL.md")
                    if not os.path.exists(skill_md):
                        continue
                    parsed = parse_skill_md(skill_md)
                    if parsed and (parsed["name"] == target_name or dirname == target_name):
                        skill_dir = candidate
                        entry_file = parsed.get("entry_file")
                        break
            if skill_dir is None:
                return {"success": False, "error": f"Saved subagent skill not found: {target_name}"}
            if not entry_file:
                return {"success": False, "error": f"No entry_file defined in SKILL.md for '{target_name}'"}
            entry_path = os.path.join(skill_dir, entry_file)
            if not os.path.exists(entry_path):
                return {"success": False, "error": f"Entry file '{entry_file}' not found in skill directory"}
            with open(entry_path, 'r', encoding='utf-8') as fh:
                code = fh.read()
            # Track that this subagent's code has been viewed
            self.viewed_subagent_codes.add(target_name)
            return {"success": True, "skill_name": target_name, "entry_file": entry_file, "code": code}

        else:
            return {"success": False, "error": f"Unknown skill: {skill_name}. Review the available skills list."}

    def _save_on_finish(self, params: Dict[str, Any], answer: str):
        """Save subagent skills after finish is confirmed. Called after human confirmation."""
        if not self.save_on_finish:
            self.log("Finished (not saved)")
            return

        has_python_files = False
        if self.current_workspace and os.path.exists(self.current_workspace):
            for f in os.listdir(self.current_workspace):
                if f.endswith('.py'):
                    has_python_files = True
                    break

        if not has_python_files:
            self.log("Subagent finished (not saved - no python files)")
            return

        subagents = params.get("subagents", [])
        saved = []
        for sa in subagents:
            sa_entry_file = sa.get("entry_file", "")
            sa_desc = sa.get("description", "")
            sa_supersedes = sa.get("supersedes", "")
            if not sa_entry_file:
                continue

            # Check if this entry_file belongs to a modified saved skill
            matched_mod_skill = None
            for mod_skill_name, mod_info in self.modified_skills.items():
                if sa_entry_file in mod_info["workspace_files"]:
                    matched_mod_skill = mod_skill_name
                    break

            if matched_mod_skill:
                # Overwrite the original saved skill directory with workspace version
                mod_info = self.modified_skills[matched_mod_skill]
                skill_dir = mod_info["skill_dir"]
                self.log(f"Overwriting saved skill '{matched_mod_skill}' with modified code...")
                for filename, workspace_path in mod_info["workspace_files"].items():
                    if os.path.exists(workspace_path):
                        dst = os.path.join(skill_dir, filename)
                        with open(workspace_path, 'r', encoding='utf-8') as sf:
                            with open(dst, 'w', encoding='utf-8') as df:
                                df.write(sf.read())
                self.log(f"Saved skill '{matched_mod_skill}' updated.")
                saved.append(matched_mod_skill)
            else:
                # Save as a new skill
                res = self.save_skill(sa_entry_file, sa_desc, answer, supersedes=sa_supersedes)
                if res.get("success"):
                    saved.append(res.get("skill_name", sa_entry_file))

        if saved:
            self.log(f"Skills saved: {', '.join(saved)}")
        else:
            self.log("Finished (no subagents to save)")

    def save_skill(self, entry_file: str, description: str, answer: str, supersedes: str = "") -> Dict[str, Any]:
        """Save a successful subagent as a skill with SKILL.md.

        Args:
            entry_file: The actual .py filename (e.g., "data_collector.py") used as entry point.
                        The skill name is derived from this filename (minus .py).
            description: Description of the skill.
            answer: The answer produced by this run.
            supersedes: Name of an old skill that this new skill replaces. If set, the old skill
                        directory will be removed after the new one is saved.
        """

        # Validate entry_file exists in workspace
        if self.current_workspace:
            entry_path = os.path.join(self.current_workspace, entry_file)
            if not os.path.exists(entry_path):
                return {"success": False, "error": f"Entry file '{entry_file}' not found in workspace. Available files: {[f for f in os.listdir(self.current_workspace) if f.endswith('.py')]}"}

        # Handle supersedes: remove the old skill BEFORE saving new one (avoids name collision)
        superseded_msg = ""
        if supersedes:
            old_skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, supersedes)
            if os.path.exists(old_skill_dir):
                import shutil
                shutil.rmtree(old_skill_dir)
                superseded_msg = f" (superseded and removed old skill '{supersedes}')"
                self.log(f"Removed superseded skill: {supersedes}")
            else:
                superseded_msg = f" (note: old skill '{supersedes}' not found, nothing to remove)"
                self.log(f"Supersedes target '{supersedes}' not found in {SUBAGENT_SKILLS_DIR}")

        # Derive skill name from filename (strip .py)
        base_name = entry_file
        if base_name.endswith('.py'):
            base_name = base_name[:-3]
        safe_name = re.sub(r'[^\w\-]', '_', base_name).lower()

        # If directory already exists, append timestamp (to minute)
        skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, safe_name)
        if os.path.exists(skill_dir):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            safe_name = f"{safe_name}_{timestamp}"
            skill_dir = os.path.join(SUBAGENT_SKILLS_DIR, safe_name)

        os.makedirs(skill_dir, exist_ok=True)

        # Copy subagent code
        copied_files = []
        if os.path.exists(self.current_workspace):
            for f in os.listdir(self.current_workspace):
                if f.endswith('.py'):
                    src = os.path.join(self.current_workspace, f)
                    dst = os.path.join(skill_dir, f)
                    with open(src, 'r') as sf:
                        with open(dst, 'w') as df:
                            df.write(sf.read())
                    copied_files.append(f)

        # Extract a short description for the YAML frontmatter
        short_desc = description.split('\n')[0] if description else f"Subagent skill for {safe_name}"
        if len(short_desc) > 200:
            short_desc = short_desc[:200] + "..."

        # Get skills used
        skills_used = ", ".join(self.current_skills) if self.current_skills else "local_search, open_page"

        # Build supersedes section for SKILL.md if applicable
        supersedes_section = ""
        if supersedes:
            supersedes_section = f"\n## Supersedes\nThis skill replaces `{supersedes}`. See description for what was improved.\n"

        # Create SKILL.md with the actual entry_file
        skill_md_content = f"""---
name: {safe_name}
description: {short_desc}
entry_file: {entry_file}
---

# {safe_name}
{supersedes_section}
## Description
{description}

## Skills Used
{skills_used}

## Usage

**Entry file**: `{entry_file}`

**Query type**: Pass a focused sub-question as the query.

**How to call**:
```xml
<action>run_subagent</action>
<params>{{"skill_name": "{safe_name}", "query": "<your focused sub-question>"}}</params>
```
"""
        write_file(os.path.join(skill_dir, "SKILL.md"), skill_md_content)

        return {"success": True, "skill_name": safe_name, "message": f"Skill saved to {skill_dir}{superseded_msg}", "answer": answer}

    def run(self, question: str, timestamp: int, save_num: int, correct_answer: str = None) -> Dict[str, Any]:
        """Run the meta-agent on a question."""
        self.trajectory = []
        self.messages = []
        self.correct_answer = correct_answer
        self.current_skills = []
        self.viewed_skill_descriptions = set()  # Reset for each new question
        self.viewed_subagent_codes = set()  # Reset for each new question
        self.modified_skills = {}  # Reset modified skills tracking

        self.current_workspace = os.path.join(WORKSPACE_DIR, timestamp, f"q{save_num}")
        os.makedirs(self.current_workspace, exist_ok=True)

        # System prompt - question is sent as a separate user message, not embedded here
        system = SYSTEM_PROMPT

        # Get all available skills
        all_skills = list_all_skills()
        skill_info = "\n".join([f"- {s['name']} ({s['type']})" for s in all_skills])

        # Initial message with available skills
        initial_content = f"""Question: {question}

You are a deep research agent. When you create subagents to help solve this problem, they must be GENERAL - your subagent should NOT contain any content specific to this question only. The subagent you create should be able to help with general deep research tasks, not just this specific one. For example, if you create a subagent to help search for information, it should take any research topic as input and work independently - it should NOT have hardcoded search queries or topic-specific logic.

CRITICAL RULE: Each response must contain AT MOST ONE <action>...</action><params>...</params> block, then STOP IMMEDIATELY.
- NEVER write <response> tags — they are RESERVED for the system. If you write <response> yourself, it is hallucination and will be rejected.
- NEVER predict, simulate, or fabricate what the system will return — wait for the actual result in the next message.
- NEVER chain multiple actions in one response — only the first one will be executed, the rest are wasted.

Available skills:
{skill_info}

Use get_skill_description to view details of any skill before using it."""
        self.messages.append({
            "role": "user",
            "content": initial_content
        })

        self.log(f"\nInitial message to LLM:\n{initial_content}\n")

        final_answer = None
        iteration = 0
        running = True  # Control flag for the loop

        while running:
            iteration += 1
            self.log(f"\n{'='*60}")
            self.log(f"Iteration {iteration}")
            self.log(f"{'='*60}")

            # Checkpoint every 30 iterations (only if human_confirm is enabled)
            if iteration > 0 and iteration % 30 == 0 and self.human_confirm:
                checkpoint_choice = self._prompt_human_confirm_every_n()
                if checkpoint_choice == "restart":
                    self.log("\n[Checkpoint] User chose to restart the question.")
                    return {
                        "success": True,
                        "final_answer": "[Restarted by user]",
                        "trajectory": self.trajectory,
                        "total_iterations": iteration
                    }
                elif checkpoint_choice == "next_question":
                    self.log("\n[Checkpoint] User chose to move to next question.")
                    return {
                        "success": True,
                        "final_answer": "[Skipped by user]",
                        "trajectory": self.trajectory,
                        "total_iterations": iteration
                    }
                # Continue if checkpoint_choice == "continue"

            # Auto-stop after 60 iterations if not using human_confirm
            if not self.human_confirm and iteration >= 60:
                self.log(f"\n[Auto-stop] Reached 60 iterations, moving to next question.")
                return {
                    "success": True,
                    "final_answer": "[Skipped - max iterations]",
                    "trajectory": self.trajectory,
                    "total_iterations": iteration
                }

            if iteration > 1:
                result = call_llm(system, self.messages)
            else:
                result = call_llm(system, self.messages, max_tokens=200)
                
            if not result["success"]:
                self.log(f"LLM Error: {result.get('error')}")
                self.trajectory.append({
                    "iteration": iteration + 1,
                    "type": "error",
                    "error": result.get("error")
                })
                running = False
                break

            response = result["response"]
            self.log(f"\nLLM Response:\n{response[:2000]}...")

            # Detect hallucinated system responses (<response> tags)
            if '<response>' in response or '</response>' in response:
                self.log("[HALLUCINATION DETECTED] LLM fabricated <response> tags.")
                # Only keep content before <response> to avoid reinforcing the pattern
                resp_idx = response.find('<response>')
                if resp_idx == -1:
                    resp_idx = response.find('</response>')
                clean_response = response[:resp_idx].rstrip() if resp_idx > 0 else ""
                self.trajectory.append({
                    "iteration": iteration + 1,
                    "type": "hallucination_detected",
                    "content": response
                })
                if clean_response:
                    self.messages.append({"role": "assistant", "content": clean_response})
                else:
                    self.messages.append({"role": "assistant", "content": "(empty)"})
                self.messages.append({
                    "role": "user",
                    "content": (
                        "HALLUCINATION DETECTED: Your response contained a <response> tag. "
                        "The <response> tag is RESERVED for the SYSTEM — you must NEVER write it yourself. "
                        "You fabricated the system's output instead of waiting for the real result.\n\n"
                        "Please retry: output ONLY your reasoning and ONE <action>...</action><params>...</params> block, "
                        "then STOP. Do NOT predict or simulate what the system will return."
                    )
                })
                continue

            self.trajectory.append({
                "iteration": iteration + 1,
                "type": "llm_response",
                "content": response
            })

            action = self.parse_action(response)

            if action is None:
                self.messages.append({"role": "assistant", "content": response})
                self.messages.append({
                    "role": "user",
                    "content": "Please provide an action using XML tags, e.g.:\n<action>create_subagent</action>\n<params>\n{\"filename\": \"subagent.py\", \"code\": \"your code here\"}\n</params>"
                })
                continue

            # If JSON parsing failed, tell the LLM to fix it and retry
            if action.get("json_parse_error"):
                self.log(f"\n[JSON Parse Error] {action['json_parse_error']}")
                self.messages.append({"role": "assistant", "content": response})
                self.messages.append({
                    "role": "user",
                    "content": f"ERROR: Failed to parse your <params> JSON: {action['json_parse_error']}\n\n"
                               f"This is likely caused by unescaped characters inside JSON string values. "
                               f"Please fix and retry. Remember:\n"
                               f"- Double quotes inside strings MUST be escaped: \\\"\n"
                               f"- Newlines must be escaped: \\n\n"
                               f"- Backslashes must be escaped: \\\\\n"
                               f"- IMPORTANT: You can only call ONE action at a time. Please check if you accidentally included multiple actions in your response."
                })
                continue

            action_type = action.get("action")
            self.log(f"\nAction: {action_type}")

            # Execute the action (all actions go through the same check)
            exec_result = self.execute_action(action, question)

            # Check if this is a finish action and it succeeded
            is_finish = (action_type == "finish")
            if is_finish and exec_result.get("success"):
                final_answer = action.get("params", {}).get("answer", "") or exec_result.get("answer", "")
                self.log(f"\n*** FINAL ANSWER: {final_answer} ***")

                # Human confirmation check - only on finish
                if self.human_confirm:
                    confirm_action, custom_input = self._prompt_human_confirm()
                    if confirm_action == "no":
                        self.log("\n[Human Confirm] User chose to stop.")
                        final_answer = "[Stopped by user]"
                        self.trajectory.append({
                            "iteration": iteration + 1,
                            "type": "finish",
                            "action": action,
                            "result": exec_result
                        })
                        break
                    elif confirm_action == "custom":
                        self.log(f"\n[Human Confirm] User provided custom instruction: {custom_input}")
                        self.messages.append({"role": "assistant", "content": response})
                        self.messages.append({"role": "user", "content": custom_input})
                        continue

                # Save skills and trajectory only after human confirm passes (or no confirm needed)
                self._save_on_finish(action.get("params", {}), final_answer)
                self.trajectory.append({
                    "iteration": iteration + 1,
                    "type": "finish",
                    "action": action,
                    "result": exec_result
                })
                break
            elif is_finish and not exec_result.get("success"):
                # Finish failed (e.g., didn't read description), continue to next iteration
                self.log(f"\nFinish failed: {exec_result.get('error', 'Unknown error')}")
                self.trajectory.append({
                    "iteration": iteration + 1,
                    "type": "action",
                    "action": {"action": action_type},
                    "result": exec_result
                })
                self.messages.append({"role": "assistant", "content": response})
                self.messages.append({
                    "role": "user",
                    "content": f"Error: {exec_result.get('error', 'Unknown error')}"
                })
                continue
            result_str = json.dumps(exec_result, ensure_ascii=False, indent=2)

            # Truncate result if too long
            if len(result_str) > 10000:
                result_str = result_str[:10000] + "\n... [RESULT TRUNCATED] ..."

            self.log(f"\nResult:\n{result_str[:2000]}...")

            self.trajectory.append({
                "iteration": iteration + 1,
                "type": "action",
                "action": {"action": action_type},
                "result": exec_result
            })

            self.messages.append({"role": "assistant", "content": response})

            # Provide guidance based on action type
            if action_type == "get_skill_description":
                if exec_result.get("success"):
                    desc = exec_result.get("description", "")
                    skill_name = exec_result.get("skill_name", "")
                    self.messages.append({
                        "role": "user",
                        "content": f"Skill '{skill_name}' description:\n{desc}"
                    })
                else:
                    self.messages.append({
                        "role": "user",
                        "content": f"Error getting skill description: {exec_result.get('error', '')}"
                    })
            elif action_type == "create_subagent":
                self.messages.append({
                    "role": "user",
                    "content": f"Result: {result_str}\n\nSubagent created. Use run_subagent to execute it."
                })
            elif action_type == "run_subagent":
                if exec_result.get("success"):
                    answer = exec_result.get("answer", "")
                    summary = exec_result.get("summary", "")
                    output = f"ANSWER: {answer}\nSUMMARY: {summary}"
                    self.messages.append({
                        "role": "user",
                        "content": f"Subagent output:\n{output}\n\nCritically evaluate this result:\n1. Does the ANSWER fully satisfy ALL requirements of the original task?\n2. Does the SUMMARY contain red flags (vague language like 'may have', 'appears to', incomplete steps)?\n3. Is there concrete evidence of success, or just a claim?\nIf verified, use finish. If issues found, prefer using modify_subagent to fix the specific problem rather than rewriting from scratch."
                    })
                else:
                    self.messages.append({
                        "role": "user",
                        "content": f"Subagent failed:\n{exec_result.get('error', '')}\n\nDiagnose the specific cause of failure from the error message above. Then prefer using modify_subagent to fix the specific broken part rather than rewriting the entire subagent."
                    })
            elif action_type == "modify_subagent":
                if exec_result.get("success"):
                    self.messages.append({
                        "role": "user",
                        "content": f"Result: {result_str}\n\nSubagent code modified. Use run_subagent to test it."
                    })
                else:
                    self.messages.append({
                        "role": "user",
                        "content": f"Modify failed: {exec_result.get('error', '')}\n\nMake sure old_content exactly matches text in your source code."
                    })
            elif action_type == "list_saved_subagents":
                if exec_result.get("success"):
                    skills = exec_result.get("skills", [])
                    if skills:
                        skill_names = ", ".join([s['name'] for s in skills])
                        self.messages.append({
                            "role": "user",
                            "content": f"Saved subagents: {skill_names}\n\nUse get_skill_description to view details, or run_subagent with skill_name parameter to run one."
                        })
                    else:
                        self.messages.append({
                            "role": "user",
                            "content": "No saved subagents found. Use create_subagent to create a new one."
                        })
                else:
                    self.messages.append({
                        "role": "user",
                        "content": f"Error: {exec_result.get('error', '')}"
                    })
            elif action_type == "view_subagent_code":
                if exec_result.get("success"):
                    code = exec_result.get("code", "")
                    entry_file = exec_result.get("entry_file", "")
                    skill_name = exec_result.get("skill_name", "")
                    self.messages.append({
                        "role": "user",
                        "content": f"Source code of saved subagent '{skill_name}' (entry file: {entry_file}):\n```python\n{code}\n```"
                    })
                else:
                    self.messages.append({
                        "role": "user",
                        "content": f"Error viewing subagent code: {exec_result.get('error', '')}"
                    })
            else:
                # Generic skill result
                self.messages.append({
                    "role": "user",
                    "content": f"Result:\n{result_str}"
                })

        # Save trajectory to current workspace
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        traj_file = os.path.join(self.current_workspace, "trajectory.json")

        final_result = {
            "question": question,
            "final_answer": final_answer,
            "trajectory": self.trajectory,
            "total_iterations": len([t for t in self.trajectory if t["type"] == "llm_response"]),
            "timestamp": timestamp
        }

        with open(traj_file, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False, indent=2)

        self.log(f"\nTrajectory saved to: {traj_file}")

        return final_result
