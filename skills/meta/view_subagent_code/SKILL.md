---
name: view_subagent_code
description: View the source code of a saved subagent skill. Use this to understand how an existing subagent works before reusing or adapting it.
---

# View Subagent Code

View the actual Python source code of a saved subagent skill.

## Usage

```xml
<action>view_subagent_code</action>
<params>{"skill_name": "name_of_saved_subagent"}</params>
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| skill_name | str | required | Name of the saved subagent skill whose code you want to view |

## Returns

```python
{
    "success": True,
    "skill_name": "the_skill_name",
    "entry_file": "data_collector.py",
    "code": "...source code of the entry file..."
}
```

## Important Notes

- Only works for saved subagent skills (listed by `list_saved_subagents`), not for meta or tool skills
- Returns the source code of the skill's entry file (as declared in SKILL.md)
- Use this when you want to understand an existing subagent's implementation before deciding whether to reuse it or create a new one
