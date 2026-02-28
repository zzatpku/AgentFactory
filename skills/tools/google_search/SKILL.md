---
name: google_search
description: Search the internet via Google (Serper API). Returns only titles, URLs, and short snippets. Use read_url_jina to get full page content.
---

# Search Tool

search_serper: High-quality search using Google via Serper API. Returns web page title, url and a short snippet.

## Usage

```python
from tools import search_serper

results = search_serper(query, topk=10)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | str | required | The search query string |
| topk | int | 10 | Number of top results to return |

## Returns

Returns a list of dictionaries directly:

```python
[
    {
        "title": "web page title",
        "link": "web page url",
        "snippet": "brief snippet, NOT the full content...",
    },
    ...
]
```

Or on error:
```python
[{"error": "error message"}]
```

**Note**: The `snippet` field is a very short excerpt, NOT the full page content. It may miss critical information. Always use `read_url_jina` to retrieve the full page content for any relevant result.

## Example

```python
from tools import search_serper

# Search for information about a topic
results = search_serper("capital of France", topk=3)

# Process results
for doc in results:
    if "error" in doc:
        print(f"Error: {doc['error']}")
        break
    print(f"Doc title: {doc['title']}")
    print(f"url: {doc['link']}")
    print(f"snippet: {doc['snippet']}...")
    print("---")
```

## Tips

- Use specific, descriptive queries for better results
- Start with topk around 10 and adjust if needed
- Check the score to gauge relevance
- **The `snippet` field is a brief excerpt, NOT the full content** - it may miss critical information
- **Always use `read_url_jina`** to get the full page content for any relevant result - do NOT rely solely on the snippet from search
- Check for errors in the first result
