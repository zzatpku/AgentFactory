---
name: read_url_jina
description: Retrieve the full content of a web page by its URL. The snippets from search are incomplete - always use read_url_jina to get the full page content for relevant results.
---

# Open Page Tool

read_url_jina: Retrieve the full, untruncated content of a web page using its URL and convert to Markdown format. Since search tools only return brief snippets that may miss critical information, use `read_url_jina` on any relevant result to ensure you have the complete content.

## Usage

```python
from tools import read_url_jina

content = read_url_jina(url)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| url | str | required | The web page url obtained from search results |

## Returns

```python
document_content (type: str)
```

Or on error:
```python
{"error": "error message"}
```

## Example

```python
from tools import read_url_jina

# Open the full document
full_content = read_url_jina(url)

if "error" not in full_content:
    print(f"Title: {full_content.get('title', 'N/A')}")
    print(f"Content: {full_content.get('text', '')[:1000]}...")
```

## Tips

- Always use doc urls from search results, don't guess document urls
- Check for errors in the response before processing
- Full documents can be long; extract relevant sections for analysis
- **Always call `read_url_jina` for relevant search results** - the snippets from search are incomplete and may miss critical information
