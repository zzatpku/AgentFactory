---
name: local_search
description: Search for relevant documents in the local knowledge base. Returns incomplete/truncated text snippets with relevance scores. Use open_page to get full document content.
---

# Search Tool

Search for documents matching a query in the local knowledge base.

## Usage

```python
from tools import local_search

results = local_search(query, topk=10)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | str | required | The search query string |
| topk | int | 10 | Number of top results to return |

## Returns

```python
{
    "results": [
        {
            "docid": "document_id_string",
            "url": "https://example.com/page",
            "text": "incomplete/truncated document snippet...",
            "score": 0.95
        },
        ...
    ],
    "took_ms": 12.5
}
```

Or on error:
```python
{"error": "error message"}
```

**Note**: The `text` field returned by `local_search` contains **incomplete/truncated content**, NOT the full document. It may cut off at arbitrary points, causing you to miss critical information. Always use `open_page` to retrieve the full document content for any result that is relevant to your query.

## Example

```python
from tools import local_search

# local_search for information about a topic
results = local_search("capital of France", topk=3)

# Process results
for doc in results.get("results", []):
    print(f"DocID: {doc['docid']}")
    print(f"Score: {doc['score']}")
    print(f"Text: {doc['text'][:200]}...")
    print("---")
```

## Tips

- Use specific, descriptive queries for better results
- Start with topk around 10 and adjust if needed
- Check the score to gauge relevance
- **The `text` field from `local_search` is incomplete/truncated** - it may cut off mid-sentence at arbitrary points
- **Always use `open_page`** to get the full document content for any relevant result - do NOT rely solely on the truncated text from `local_search`
- When using `open_page`, remember the text is in `results[0]["text"]`, not at the top level
