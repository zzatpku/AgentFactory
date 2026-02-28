---
name: create_subagent
description: Create a new Python subagent file in the workspace. After creating, use run_subagent to test it (NOT use_saved_subagent).
---

# Create Subagent

Create a new Python subagent file in the **workspace** (temporary directory).

## IMPORTANT: Workflow After Creating

After `create_subagent`, use `run_subagent` to run it:
```
create_subagent → run_subagent (with query) → finish
```

**DO NOT** use `use_saved_subagent` for newly created subagents!
- `run_subagent`: For subagents you just created (in workspace)
- `use_saved_subagent`: ONLY for subagents listed by `list_saved_subagents`

## Usage

```xml
<action>create_subagent</action>
<params>
{
    "skill_name": "my_subagent_name",
    "filename": "subagent.py",
    "code": "your python code here",
    "skills": ["local_search", "open_page"]
}
</params>
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| skill_name | str | required | Name for this subagent (used when saving with `finish`) |
| filename | str | "subagent.py" | Name of the file to create in workspace |
| code | str | required | The Python code for the subagent |
| skills | list | ["local_search", "open_page"] | List of tool skill names this subagent will use. You MUST call `get_skill_description` for each tool skill BEFORE creating the subagent to understand how to use them. |

## Returns

```python
{
    "success": True,
    "path": "/path/to/workspace/subagent.py",
    "message": "Subagent created with skills: [...]"
}
```

## Next Step After Creating

Use `run_subagent` with the same filename to test:
```xml
<action>run_subagent</action>
<params>{"filename": "subagent.py", "query": "your test query"}</params>
```

## Core Component: call_llm

The LLM is the core reasoning engine of your subagent. Use it like this:

```python
from llm import call_llm

response = call_llm(
    system="You are a research assistant.",
    messages=[{"role": "user", "content": "Your prompt here"}],
    max_tokens=2000  # optional, default 8000
)
# Returns: str - The LLM's text response, or "Error:..." on failure
```

**IMPORTANT**: `call_llm` requires TWO positional arguments:
- `system`: A string for the system prompt
- `messages`: A list of message dicts with "role" and "content" keys

## Tool Skills in Subagent

**IMPORTANT**: Before using any tool skill, use `get_skill_description` to read its documentation and understand:
- How to import the tool
- What parameters it accepts
- What format it returns

Each tool skill has a SKILL.md file that shows exactly how to use it. For example:

```python
# For search tool - check its SKILL.md first with get_skill_description
from tools import local_search
results = local_search(query="your query", topk=10)

# For open_page tool - check its SKILL.md first with get_skill_description
from tools import open_page
content = open_page(docid="doc_id_from_search")
```

**Workflow**:
1. Meta agent calls `get_skill_description("local_search")` to read the tool's documentation
2. Meta agent creates subagent code that imports and uses the tool directly as shown in the documentation
3. Subagent runs and uses the tool by importing it directly

## Important Notes

- **CRITICAL: Data Passing Between Subagents**: When a subagent needs to collect large amounts of data, or when data needs to be passed between multiple subagents, use JSON files as the intermediate format. The producing subagent writes data to a `.json` file in the workspace, and the consuming subagent reads from that JSON file. This avoids passing large data through return values and keeps subagent interfaces clean.
- **CRITICAL: Output Files Must Use Relative Paths**: When the subagent needs to **write/save** output files (markdown, images, JSON, etc.), ALWAYS use **relative paths** (e.g., `output.md`, `result.png`, `data.json`). The subagent runs in a workspace directory, so relative paths will automatically save files to the correct location. Do NOT use absolute paths like `/Users/.../file.md` for output.
  - Examples of output files: `plt.savefig('chart.png')`, `pathlib.Path('result.md').write_text(...)`, `json.dump(data, open('data.json', 'w'))`
- **Reading Input Files**: For **reading** files (e.g., reading source code to analyze, reading data files), you CAN use absolute paths if needed — this is allowed since you're referencing existing files, not creating new output.
- **CRITICAL: Matplotlib Text Encoding**: When the subagent uses `matplotlib` for plotting, Do NOT use emoji characters (e.g., `\U0001f4c8`, `📈`, `😊`) in any labels, titles, legends, annotations, or text elements. Emojis are NOT supported by matplotlib's default fonts and will cause rendering failures or missing characters. Use plain text only.
- **CRITICAL**: Before creating a subagent, you MUST call `get_skill_description` for EVERY tool skill the subagent will use. This is mandatory to understand:
  - How to import the tool correctly
  - What parameters it accepts and their types
  - What format the tool returns (essential for writing correct code!)
- The subagent should be a **complete problem-solving pipeline**, not a simple function
- It should have its own reasoning loop: think → act → observe → iterate
- The subagent's `main(query)` function receives the question as a parameter and returns a dict
- Use `def main(query):` as the entry point
- The subagent should work for ANY question of the same category

## ⚠️ CRITICAL: Subagent MUST Be Generic ⚠️

A subagent will be saved and reused for MANY different questions of the same category. **NEVER hardcode the current question's specific details** (entity names, dates, search terms, expected answers, if-checks for specific strings) into the code.

**Instead, ALL question-specific logic must be driven by `call_llm` at runtime:**
- **Search queries**: Generated by `call_llm` based on the `query` parameter, not written as string literals
- **Entity extraction / checks**: Done by `call_llm` analyzing search results, not by `if "SomeName" in text`
- **Final answer**: Produced by `call_llm` reasoning over evidence, not hardcoded

**Self-test**: Mentally replace the `query` parameter with a completely different question of the same category. If the code would break or return nonsense, it is too specific — rewrite it to be input-driven.

### Examples: Generic vs. Hardcoded Subagents

**Example 1: Web Data Extraction**

Task: "Scrape the price of iPhone 15 from amazon.com"

❌ BAD — hardcoded product and URL:
```python
def main(query):
    page = open_page("https://www.amazon.com/dp/B0CHP7Y5VN")
    price = call_llm(
        system="Extract the price of iPhone 15 from this page.",
        messages=[{"role": "user", "content": page}]
    )
    return {"answer": price, "summary": "Found iPhone 15 price."}
```

✅ GOOD — LLM-driven extraction, works for any product:
```python
def main(query):
    # Step 1: LLM decides what to search for based on the query
    search_plan = call_llm(
        system="You are a web research planner. Given a user query about finding product info, generate a search query.",
        messages=[{"role": "user", "content": f"Query: {query}\nGenerate a search query to find this product's information online."}]
    )
    results = local_search(query=search_plan, topk=5)
    # Step 2: LLM picks the best result and extracts the answer
    # ... (iterative search and extraction loop)
```

**Example 2: File Processing**

Task: "Convert report.csv to a bar chart"

❌ BAD — hardcoded file path and column names:
```python
def main(query):
    import pandas as pd
    df = pd.read_csv("/Users/alice/data/report.csv")
    df.plot.bar(x="month", y="revenue")
    plt.savefig("/Users/alice/data/chart.png")
    return {"answer": "/Users/alice/data/chart.png", "summary": "Created bar chart."}
```

✅ GOOD — LLM extracts file path and column info from query:
```python
def main(query):
    # Step 1: LLM parses the query to extract file path and intent
    plan = call_llm(
        system="You are a data visualization planner.",
        messages=[{"role": "user", "content": f"Query: {query}\nExtract: 1) the file path, 2) what type of chart to create, 3) which columns to use (if specified). Return as JSON."}]
    )
    parsed = json.loads(plan)
    # Step 2: Read the file, inspect columns, let LLM decide visualization
    # ... (dynamic processing based on parsed intent)
```

**Example 3: API Interaction**

Task: "Send a Slack message to #general saying 'Hello team'"

❌ BAD — hardcoded channel and message:
```python
def main(query):
    execute_shell_command('curl -X POST -H "Authorization: Bearer xoxb-TOKEN" '
        '-d \'{"channel": "#general", "text": "Hello team"}\' '
        'https://slack.com/api/chat.postMessage')
    return {"answer": "Sent 'Hello team' to #general", "summary": "Done."}
```

✅ GOOD — LLM extracts parameters from query:
```python
def main(query):
    # Step 1: LLM parses the query to extract channel, message, and action
    parsed = call_llm(
        system="You parse user requests about sending messages. Extract the target channel/recipient and message content. Return as JSON.",
        messages=[{"role": "user", "content": f"Query: {query}"}]
    )
    params = json.loads(parsed)
    # Step 2: Use extracted params to perform the action dynamically
    # ... (send message using params["channel"] and params["message"])
```

**Key Principle**: The subagent code should be a *reusable template* for a category of tasks. All question-specific details (file paths, entity names, URLs, search terms, expected values) must be extracted from `query` at runtime via `call_llm`, never written as literals in the code.

## ⚠️ CRITICAL: Subagent Output Format ⚠️

Your subagent's `main(query)` function must **return** a dict with `answer` and `summary` keys. Do NOT use `print()` for output.

**Function signature**: `def main(query: str) -> dict`

**Return format**:
```python
return {"answer": "<the answer to the focused sub-task>", "summary": "<reasoning trace with key evidence>"}
```

**ANSWER**: The direct answer to the task. Should be focused and specific.

**SUMMARY**: A detailed reasoning trace that includes:
- **Key actions (like search queries)** that were tried and what each returned
- **Critical evidence** found (e.g., "Wikipedia article on X states: '...'")
- **Verification steps** taken (e.g., "Confirmed via secondary source...")
- **Reasoning chain** connecting evidence to the answer
- **Number of iterations** used

Keep SUMMARY between 100-2000 words. Focus on the reasoning path and evidence, not verbose explanations.

**⚠️ CRITICAL: SUMMARY must be generated by `call_llm` as a SEPARATE step ⚠️**

Do NOT generate SUMMARY by string concatenation or truncation like `analysis[:200]`. Instead, after finding the answer, make a DEDICATED `call_llm` call to produce the SUMMARY, passing it ALL the evidence collected during the search. This ensures the SUMMARY is coherent, complete, and contains the key reasoning chain.

**Example code pattern:**
```python
# WRONG - printing output
print(f"ANSWER: {final_answer}")
print(f"SUMMARY: {summary}")

# WRONG - truncated string concatenation for summary
return {"answer": final_answer, "summary": analysis[:200]}

# RIGHT - LLM-generated summary with full context, returned as dict
summary = call_llm(
    system="You are a research summarizer. Write a detailed SUMMARY of the research process and findings.",
    messages=[{"role": "user", "content": f"Query: {query}\nEvidence collected:\n{evidence}\nFinal answer: {answer}\n\nWrite a SUMMARY (100-2000 words) that traces the reasoning path: what was searched, what was found, what evidence supports the answer, and how the answer was verified."}],
    max_tokens=3000
)
return {"answer": final_answer, "summary": summary}
```

**Good SUMMARY example**:
```
Searched "Mount Everest first ascent" → Found Wikipedia article stating Edmund Hillary and Tenzing Norgay reached the summit on May 29, 1953, as part of the British Expedition led by John Hunt. Verified expedition name "British Expedition 1953" from nationalgeographic.com article titled "First to Everest". Cross-checked dates match across both sources. The answer is confirmed: Edmund Hillary and Tenzing Norgay. (2 iterations)
```

**Bad SUMMARY examples**:
```
Research completed  # Too vague, no evidence, no reasoning trace
```
```
Searched 5 queries including 'some query'. Based on the search results...  # Truncated, missing actual evidence
```

**Why this matters**: The meta-agent reads your SUMMARY to decide what to do next. If your SUMMARY is vague, the meta-agent cannot refine its strategy. Even when you FAIL to find the answer, your SUMMARY must report exactly what you searched and what you found, so the meta-agent can try a different approach.

## Subagent Quality Guidelines

**CRITICAL: Create COMPLETE PIPELINES, not weak single-shot tools**

A good subagent is a full reasoning agent that can solve problems autonomously:

- **Has a reasoning loop**: Can think, search, analyze results, and iterate
- **Can try multiple strategies**: If the first search doesn't work, try different queries
- **Can reason about results**: Use LLM to analyze what was found and decide next steps
- **Can self-correct**: Adjust approach based on intermediate results
- **Keeps trying**: Iterate until finding the answer or exhausting reasonable attempts

**AVOID weak subagents** that only do:
- One search → one LLM call → return answer (too fragile, gives up too easily)

**Remember**: The meta agent will give subagents SIMPLER sub-problems to reduce reasoning difficulty. But each subagent should still be a COMPLETE PIPELINE capable of solving its sub-problem through autonomous reasoning.
