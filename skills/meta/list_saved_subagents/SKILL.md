---
name: list_saved_subagents
description: List all previously saved subagent skills. Use this to check if a suitable subagent already exists before creating a new one.
---

# List Saved Subagents

List all previously saved subagent skills.

## Usage

```xml
<action>list_saved_subagents</action>
<params>{}</params>
```

## Parameters

None required.

## Returns

```python
{
    "success": True,
    "skills": [
        {"name": "skill_name_1"},
        {"name": "skill_name_2"},
        ...
    ],
    "count": 2
}
```

## Important Notes

- Returns only skill names, not full descriptions
- Use `get_skill_description` with a specific skill name to view its details
- Check if any existing subagent matches your problem category before creating a new one
