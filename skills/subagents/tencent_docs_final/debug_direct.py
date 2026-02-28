import os, json, re
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

def main(query):
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
        
        # Test 1: Try navigating directly to /sheet/ to create a new one
        evidence_log.append("=== Test 1: Direct nav to /sheet ===" )
        page.goto("https://docs.qq.com/sheet", wait_until="domcontentloaded")
        page.wait_for_timeout(10000)
        evidence_log.append(f"URL after /sheet: {page.url}")
        evidence_log.append(f"Title: {page.title()}")
        page.screenshot(path="debug_direct_sheet.png")
        
        body = page.evaluate("() => document.body.innerText")
        evidence_log.append(f"Body (first 2000):\n{body[:2000]}")
        
        # Check if this is actually a spreadsheet
        canvas_count = page.evaluate("() => document.querySelectorAll('canvas').length")
        evidence_log.append(f"Canvas elements: {canvas_count}")
        
        # Check for bar-label
        inputs_info = page.evaluate("""() => {
            const results = [];
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.width < 2) continue;
                results.push(`<input> class="${inp.className}" value="${inp.value}" placeholder="${inp.placeholder || ''}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Inputs:\n{inputs_info}")
        
        # Test 2: Try creating via the API-like URL
        evidence_log.append("\n=== Test 2: Try /desktop/ with hash create ===")
        page2 = context.new_page()
        page2.goto("https://docs.qq.com/desktop/#newSheet", wait_until="domcontentloaded")
        page2.wait_for_timeout(10000)
        evidence_log.append(f"URL: {page2.url}")
        evidence_log.append(f"Title: {page2.title()}")
        
        # Test 3: Look at network requests when clicking create
        evidence_log.append("\n=== Test 3: Monitor network during creation ===")
        page3 = context.new_page()
        page3.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page3.wait_for_timeout(5000)
        
        # Set up request monitoring
        api_requests = []
        api_responses = []
        
        def on_request(req):
            url = req.url
            if 'create' in url.lower() or 'new' in url.lower() or 'sheet' in url.lower():
                api_requests.append(f"REQ: {req.method} {url}")
        
        def on_response(resp):
            url = resp.url
            if 'create' in url.lower() or 'new' in url.lower():
                try:
                    body = resp.text()
                    api_responses.append(f"RESP: {resp.status} {url} body={body[:500]}")
                except:
                    api_responses.append(f"RESP: {resp.status} {url} (couldn't get body)")
        
        page3.on("request", on_request)
        page3.on("response", on_response)
        
        # Click 新建
        btn = page3.query_selector('button:has-text("新建")')
        if btn:
            btn.click(force=True)
            page3.wait_for_timeout(3000)
        
        # Click 表格
        items = page3.query_selector_all('button.create-create-item')
        for item in items:
            text = item.inner_text().strip()
            if text == '表格':
                item.click(force=True)
                break
        
        # Wait and collect network data
        page3.wait_for_timeout(15000)
        
        evidence_log.append(f"API requests ({len(api_requests)}):")
        for r in api_requests[:20]:
            evidence_log.append(f"  {r}")
        evidence_log.append(f"API responses ({len(api_responses)}):")
        for r in api_responses[:20]:
            evidence_log.append(f"  {r}")
        
        # Check all pages
        evidence_log.append(f"\nAll context pages ({len(context.pages)}):")
        for i, cp in enumerate(context.pages):
            try:
                evidence_log.append(f"  Page {i}: {cp.url} title={cp.title()}")
            except:
                evidence_log.append(f"  Page {i}: (error)")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Analyze the debug findings about creating spreadsheets in Tencent Docs.",
        messages=[{"role": "user", "content": f"Debug findings:\n{evidence_str}\n\nAnalyze: 1) Does navigating to /sheet directly work? 2) What API calls are made during creation? 3) How can we reliably create a new spreadsheet?"}],
        max_tokens=2000
    )
    
    return {"answer": evidence_str[:4000], "summary": summary}
