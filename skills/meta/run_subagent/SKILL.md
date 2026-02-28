---
name: run_subagent
description: Run a subagent - either a newly created one from workspace or a saved subagent from previous sessions.
---

# Run Subagent

Run a subagent file from either the **workspace** (newly created) or from **saved skills** (previous sessions).

## Unified Command

`run_subagent` now handles BOTH types of subagents:
- **Newly created subagents**: Use `filename` parameter
- **Saved subagents**: Use `skill_name` parameter

## Usage

**For newly created subagents (workspace files):**
```xml
<action>run_subagent</action>
<params>{"filename": "subagent.py", "query": "your focused sub-question"}</params>
```

**For saved subagents (from previous sessions):**
```xml
<action>run_subagent</action>
<params>{"skill_name": "multi_hop_biographical_researcher", "query": "your focused sub-question"}</params>
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| filename | str | "subagent.py" | Name of the file you created with create_subagent (for workspace files) |
| skill_name | str | - | Name of a saved subagent from list_saved_subagents (for saved skills) |
| query | str | original question | The focused query to pass to the subagent |

**Note**: Provide either `filename` OR `skill_name`, not both. If `skill_name` is provided, it takes priority.

## Returns

On success:
```python
{
    "success": True,
    "answer": "the subagent's answer",
    "summary": "reasoning trace with key evidence"
}
```

On failure:
```python
{
    "success": False,
    "error": "error message..."
}
```

## Important Notes

- **CRITICAL: For workspace files, you MUST provide the `filename` parameter matching the exact filename you used in `create_subagent`.** If you created with `"filename": "visualizer.py"`, you must run with `"filename": "visualizer.py"` — omitting it will default to `"subagent.py"` and fail.
- For saved skills: First check `list_saved_subagents` to see available names
- Use the `query` parameter to pass focused sub-questions
- The query is passed to the subagent's `main(query)` function as a parameter
- If the subagent fails, check the error message and use `modify_subagent` to fix (workspace files only)

## Examples

```xml
<!-- After create_subagent with filename="subagent.py" -->
<action>run_subagent</action>
<params>{"filename": "subagent.py", "query": "What year was the Sapphire Jubilee?"}</params>

<!-- Using a saved subagent -->
<action>run_subagent</action>
<params>{"skill_name": "entity_researcher", "query": "Who is Kwesi Arthur?"}</params>

<!-- Call again with different query -->
<action>run_subagent</action>
<params>{"filename": "subagent.py", "query": "Who created Linux?"}</params>
```
