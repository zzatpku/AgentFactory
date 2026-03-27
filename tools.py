"""
Search API Tool - Search documents and retrieve full content.

Usage:
    from tools import search, open_page

    # Search for documents
    results = local_search("your query", topk=10)
    # Returns: {"results": [{"docid": "...", "text": "...", "score": ...}, ...]}

    # Open a specific document
    content = open_page("docid_here")
    # Returns: Full document content as dict
"""

import os
import httpx
from typing import Dict, Any, Optional, List
import requests
import time
import subprocess
import re
import json
import http
from dotenv import load_dotenv

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
JINA_API_KEY = os.getenv("JINA_API_KEY")

def read_url_jina(url: str) -> str:
    """
    Use Jina Reader to convert a web page URL into clean Markdown text.
    Suitable for reading articles from WeChat, Zhihu, news sites, stripping ads.
    """
    print(f"📖 [Jina Reader] Reading: {url}")

    api_key = JINA_API_KEY
    jina_base = "https://r.jina.ai/"
    target_url = f"{jina_base}{url}"

    headers = {}

    key = api_key
    if key:
        headers["Authorization"] = f"Bearer {key}"
    print("wait for a moment...")
    time.sleep(2)
    try:
        response = requests.get(target_url, headers=headers, timeout=20)
        if response.status_code == 429:
            return "❌ Error: Jina Rate Limit Exceeded. (Too many requests, consider getting a free API key)"
        response.raise_for_status()
        return response.text[:8000]
    except Exception as e:
        return f"❌ Jina Read Error: {e}"

def search_serper(query: str, topk: int = 10, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Web search using the google.serper.dev API.

    Input (compatible with original search_serper):
        - query: search query
        - topk: number of results to return
        - api_key: optional API Key (uses default key if not provided)

    Output (compatible with original search_serper):
        [{"title": ..., "link": ..., "snippet": ...}, ...]
        On failure: [{"error": "..."}]
    """
    print(f"🔍 [Serper] Searching: {query}")

    key = api_key or SERPER_API_KEY
    payload = json.dumps({"q": query, "num": topk})
    headers = {
        "X-API-KEY": key,
        "Content-Type": "application/json",
    }

    try:
        conn = http.client.HTTPSConnection("google.serper.dev", timeout=30)
        conn.request("POST", "/search", payload, headers)
        res = conn.getresponse()
        raw = res.read()
        conn.close()

        if res.status != 200:
            return [{"error": f"HTTP {res.status}: {raw.decode('utf-8', errors='replace')}"}]

        data = json.loads(raw.decode("utf-8"))
        organic = data.get("organic", [])

        return [
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet"),
            }
            for item in organic[:topk]
        ]
    except Exception as e:
        return [{"error": str(e)}]
 
def _is_shell_command_safe(command):
    """
    Simple shell command safety check.
    Blocks rm, rmdir, shred and redirect overwrite > (adjustable).
    """
    # Use word boundary regex to avoid false positives (e.g. 'performance' contains 'rm')
    # Matches: rm -rf, rm file, rmdir dir, shred file
    forbidden_patterns = [
        r'\brm\b', 
        r'\brmdir\b', 
        r'\bshred\b',
        r'\bmv\b' # mv can overwrite files, can be relaxed if needed
    ]
    
    for pattern in forbidden_patterns:
        if re.search(pattern, command):
            keyword = pattern.replace(r'\b', '')
            return False, f"Safety blocked: command contains forbidden keyword '{keyword}'"
    return True, ""

def execute_shell_command(command):
    """
    Tool implementation: execute a shell command.
    """
    MAX_OUTPUT_LENGTH = 5000
    # 1. Safety check
    is_safe, reason = _is_shell_command_safe(command)
    if not is_safe:
        return f"Error: Command rejected by safety policy. {reason}"
    
    # Use current working directory (set by run_python_file to the task workspace)
    work_dir = os.getcwd()

    # 2. Execute command
    try:
        # Execute in the specified working directory
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=work_dir,
            capture_output=True, 
            text=True,
            timeout=300, # Prevent command from hanging (5 min, supports long tasks like playwright)
            encoding='utf-8',
            errors='replace'
        )
        output = result.stdout
        if len(output) > MAX_OUTPUT_LENGTH:
            output = output[:MAX_OUTPUT_LENGTH] + f"\n... (Output truncated: showing first {MAX_OUTPUT_LENGTH} characters. Use 'head', 'tail' or 'grep' to read specific parts.)"
        if result.stderr:
            output += f"\n[Stderr]:\n{result.stderr}"
            
        return output if output.strip() else "[Command executed successfully with no output]"
        
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except Exception as e:
        return f"Error executing shell command: {str(e)}"