---
name: open_page
description: Retrieve the full content of a document by its ID. The text from local_search is incomplete/truncated - always use open_page to get the full document content for relevant results.
---

# Open Page Tool

Retrieve the full, untruncated content of a document using its document ID. Since `local_search` only returns incomplete snippets that may cut off at arbitrary points, use `open_page` on any relevant result to ensure you have the complete information.

## Usage

```python
from tools import open_page

content = open_page(docid)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| docid | str | required | The document ID obtained from local_search results |

## Returns

```python
{
    "results": [
        {
            "docid": "document_id_string",
            "url": "https://example.com/page",
            "text": "full document content..."
        }
    ],
    "took_ms": 12.5
}
```

Or on error:
```python
{"error": "error message"}
```

**Note**: The text is inside `results[0]["text"]`, not at the top level.

## Example

```python
from tools import local_search, open_page

# First search for documents
results = local_search("machine learning basics", topk=3)

# Get the docid of the most relevant result
if results.get("results"):
    top_doc = results["results"][0]
    docid = top_doc["docid"]

    # Open the full document
    full_content = open_page(docid)

    if "error" not in full_content and full_content.get("results"):
        doc = full_content["results"][0]
        print(f"DocID: {doc.get('docid', 'N/A')}")
        print(f"Content: {doc.get('text', '')[:1000]}...")
```

## Tips

- Always use docids from local_search results, don't guess document IDs
- Check for errors in the response before processing
- Full documents can be long; extract relevant sections for analysis
- **Always call `open_page` for relevant search results** - the text from `local_search` is truncated and may miss critical information
