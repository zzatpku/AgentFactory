---
name: tencent_docs_final
description: **Problem Category**: Browser automation for creating and editing Tencent Docs (腾讯文档) online spreadsheets.
entry_file: tencent_docs_final.py
---

# tencent_docs_final

## Description
**Problem Category**: Browser automation for creating and editing Tencent Docs (腾讯文档) online spreadsheets.
**Applicable Questions**: Creating new spreadsheets on Tencent Docs, filling in cell data (headers and data rows), getting document share links.
**Key Features**:
- Uses Playwright with persistent browser context for session management
- Phased approach: navigate → click 新建 → click 表格 → click 空白表格 in iframe template picker → fill data → verify → get share link
- Handles the template picker iframe (tmall-panel-iframe) which appears after clicking 表格
- Uses name box (input.bar-label) for reliable cell navigation
- Uses formula bar (div.formula-input, contenteditable) for reliable data input into canvas-based cells
- Verifies cell content by reading formula bar after navigation
- Handles popup windows/new tabs for newly created documents
**Skills Used**: playwright, google_search, execute_shell_command
**Reasoning Pattern**: LLM parses headers/data from query → navigates to docs.qq.com → clicks New → selects Spreadsheet → clicks Blank Spreadsheet in iframe → navigates to each cell via name box → types via formula bar → verifies each cell → returns share link
**Input Format**: Natural language query describing what spreadsheet to create and what data to fill in.
**Output Format**: Dict with 'answer' containing share link and completion message, 'summary' with detailed trace.
**Critical Implementation Details**:
1. Tencent Docs spreadsheet is canvas-based - cannot type directly into cells via keyboard
2. Must click formula bar (div.formula-input) to focus it before typing
3. After clicking 表格 in creation menu, a template picker appears in iframe (tmall-panel-iframe) - must click 空白表格 inside the iframe
4. Cell navigation: click name box (input.bar-label) → triple-click to select → type cell ref (e.g. A1) → Enter
5. Data input: navigate to cell → click formula bar → type text → Enter to commit

## Skills Used
playwright

## Usage

**Entry file**: `tencent_docs_final.py`

**Query type**: Pass a focused sub-question as the query.

**How to call**:
```xml
<action>run_subagent</action>
<params>{"skill_name": "tencent_docs_final", "query": "<your focused sub-question>"}</params>
```
