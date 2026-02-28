---
name: modify_subagent
description: Edit an existing subagent file by replacing specific code snippets. Supports both workspace files and saved skills.
---

# Modify Subagent

Edit an existing subagent file by replacing specific code snippets. Supports two modes:

1. **Workspace file** (default): Modify a file in the current workspace.
2. **Saved skill**: Provide `skill_name` to modify a previously saved skill. The skill's code is copied to workspace and modified there.

After modifying, use `run_subagent` to test — it will automatically run the modified version.

## Usage

### Modify a workspace file

```xml
<action>modify_subagent</action>
<params>
{
    "filename": "subagent.py",
    "old_content": "exact code to replace",
    "new_content": "new code"
}
</params>
```

### Modify a saved skill

```xml
<action>modify_subagent</action>
<params>
{
    "skill_name": "web_searcher",
    "old_content": "exact code to replace",
    "new_content": "new code"
}
</params>
```

You can also specify `filename` to target a specific file within the saved skill (defaults to the skill's entry_file):

```xml
<action>modify_subagent</action>
<params>
{
    "skill_name": "web_searcher",
    "filename": "helper.py",
    "old_content": "exact code to replace",
    "new_content": "new code"
}
</params>
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| filename | str | entry_file or "subagent.py" | Name of the file to modify. When used with `skill_name`, defaults to the skill's entry_file. |
| skill_name | str | "" | (Optional) Name of a saved skill to modify. |
| old_content | str | required | Exact code snippet to find and replace |
| new_content | str | required | New code to replace with |

## Returns

On success:
```python
{
    "success": True,
    "path": "/path/to/file.py",
    "message": "Subagent code modified."
}
```

On failure:
```python
{
    "success": False,
    "error": "old_content not found in file..."
}
```

## Important Notes

- The `old_content` must be an **exact match** of text in the source file
- This modifies your SOURCE CODE, not the subagent's output
- After modifying, use `run_subagent` to test the changes — it will run the modified version
- When modifying a saved skill, use `run_subagent` with the same `skill_name` to test
- **When to modify vs. create new**: Only use `modify_subagent` on a saved skill when the skill itself has problems — e.g. it contains hardcoded values, lacks generality, has bugs, or otherwise cannot be reused as-is. If the saved skill is fine but you simply want to borrow ideas or patterns from it for a similar but different task, you should `view_subagent_code` to study its code, then use `create_subagent` to build a new one. Do NOT modify a working, general-purpose skill just to adapt it to a different task.
- **`modify_subagent` vs. `supersedes` in `finish`**: These serve different purposes:
  - **`modify_subagent` with `skill_name`**: For small, surgical fixes (bug fixes, selector updates, minor logic changes). The skill name and file name stay the same. Changes are saved back to the original skill directory at `finish` time.
  - **`create_subagent` (new file) + `supersedes` in `finish`**: For major rewrites where the architecture, approach, or file name changes significantly. This creates a new skill and removes the old one. Use this when `modify_subagent` would require replacing most of the code.
