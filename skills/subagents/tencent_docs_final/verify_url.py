import os, json, re
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

def main(query):
    """Verify if a Tencent Docs URL exists and contains expected content."""
    # Extract URL from query
    url_match = re.search(r'https?://[^\s]+', query)
    url = url_match.group() if url_match else ""
    
    if not url:
        return {"answer": "No URL found in query", "summary": "No URL to verify"}
    
    evidence_log = []
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            channel="chrome",
            locale="zh-CN",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        
        final_url = page.url
        title = page.title()
        evidence_log.append(f"Navigated to: {url}")
        evidence_log.append(f"Final URL: {final_url}")
        evidence_log.append(f"Page title: {title}")
        
        try:
            body_text = page.evaluate("() => document.body.innerText")
            evidence_log.append(f"Body text (first 3000 chars):\n{body_text[:3000]}")
        except Exception as e:
            evidence_log.append(f"Error getting body text: {e}")
        
        page.screenshot(path="verify_screenshot.png")
        evidence_log.append("Screenshot saved: verify_screenshot.png")
        
        # Check if document exists
        doc_exists = "文档不存在" not in (body_text or "")
        has_sheet_content = "/sheet/" in final_url
        evidence_log.append(f"Document exists: {doc_exists}")
        evidence_log.append(f"Is sheet URL: {has_sheet_content}")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Summarize the URL verification results.",
        messages=[{"role": "user", "content": f"Verification results:\n{evidence_str}\n\nDoes the document exist and contain spreadsheet data?"}],
        max_tokens=1000
    )
    
    answer = f"Document exists: {doc_exists}. URL: {final_url}. Title: {title}"
    return {"answer": answer, "summary": summary}
