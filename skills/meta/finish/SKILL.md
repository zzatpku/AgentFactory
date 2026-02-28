---
name: finish
description: Complete the task with a final answer and save reusable subagents as skills. Use this when you have successfully solved the question.
---

# Finish

Complete the task with a final answer and save reusable subagents as skills.

## Required Parameters

Both `answer` and `subagents` are **required** keys. Omitting either will cause a validation error.

| Parameter | Type | Description |
|-----------|------|-------------|
| answer | str | A **brief** final answer (1-3 sentences). Do NOT put full reports or large content here. |
| subagents | list | List of subagents to save, or `[]` if none worth saving. |

## The 4 Valid Patterns

**Do NOT mix `skill_name` and `supersedes` in the same entry — they are mutually exclusive.**

### Pattern 1 — New subagents (first time creating)

You created multiple new subagents with `create_subagent` and want to save them all.

```xml
<action>finish</action>
<params>
{"answer": "...", "subagents": [
  {"entry_file": "researcher.py", "description": "..."},
  {"entry_file": "analyzer.py", "description": "..."},
  {"entry_file": "visualizer.py", "description": "..."}
]}
</params>
```

### Pattern 2 — Modified saved skills (small fix via `modify_subagent`)

You used `modify_subagent` with `skill_name` to fix saved skills. Include `skill_name` so changes are saved back to the original skill directories.

```xml
<action>finish</action>
<params>
{"answer": "...", "subagents": [
  {"entry_file": "researcher.py", "description": "...", "skill_name": "researcher"},
  {"entry_file": "analyzer.py", "description": "...", "skill_name": "analyzer"}
]}
</params>
```

### Pattern 3 — New subagents replacing old skills (`create_subagent` + `supersedes`)

You created new subagents to replace old broken skills. The old skills will be deleted.

```xml
<action>finish</action>
<params>
{"answer": "...", "subagents": [
  {"entry_file": "researcher.py", "description": "...\n**Improved From**: ...", "supersedes": "old_researcher"},
  {"entry_file": "analyzer.py", "description": "..."}
]}
</params>
```

### Pattern 4 — Nothing to save

Use this when: (a) existing saved subagents already solved the problem without any new code or modifications, or (b) the subagents completely failed and contain no useful logic. **In all other cases, you MUST save ALL reusable subagents** — review every subagent you created in this session and save each one that has value. See Important Notes.

```xml
<action>finish</action>
<params>
{"answer": "...", "subagents": []}
</params>
```

## Subagent Entry Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| entry_file | str | **Yes** | The exact `.py` filename from `create_subagent`. Must match a file in the workspace. |
| description | str | **Yes** | What problems this subagent solves. If `supersedes` is set, MUST include `**Improved From**`. |
| skill_name | str | No | Only for Pattern 2. The saved skill name you modified via `modify_subagent`. **Cannot be used with `supersedes`.** |
| supersedes | str | No | Only for Pattern 3. The old skill name to delete and replace. **Cannot be used with `skill_name`.** |

## Description Format

```
**Problem Category**: ...
**Applicable Questions**: ...
**Key Features**: ...
**Skills Used**: ...
**Reasoning Pattern**: ...
**Input Format**: ...
**Output Format**: ...
**Improved From**: [Only if supersedes is set. Explain what the old skill got wrong and what this version fixes.]
```

## Important Notes

- **`answer` must be brief** (1-3 sentences). Large content causes JSON parsing failures.
- **`entry_file` must be the exact `.py` filename** you used in `create_subagent`.
- **Modified saved skills must be listed** (Pattern 2), otherwise modifications are discarded.
- **`skill_name` and `supersedes` are mutually exclusive**: use one or the other, never both.
- **You MUST save ALL reusable subagents**: Before calling `finish`, review EVERY subagent you created in this session (check all `.py` files in the workspace). Save each one that has value — do not save only the main one. Even helper subagents or narrowly-focused subagents may be useful for future tasks.
- **Specific subagents are also worth saving**: even if a subagent targets a narrow domain, save it with a descriptive skill name and description that clearly states its specific scope (e.g., what site/API/topic it handles). Benefits: (1) identical or very similar tasks can directly reuse it; (2) for related tasks, its code serves as a working reference — use `view_subagent_code` to study its structure, API calls, and workarounds, then `create_subagent` to build a new one based on it.
- All workspace `.py` files are copied into each saved skill directory.
