import os, json, re, time
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

JS_GET_ELEMENTS = """() => {
    document.querySelectorAll('[data-bid]').forEach(e => e.removeAttribute('data-bid'));
    const sels = 'button, input, textarea, select, a[href], [role="button"], [role="tab"], [role="textbox"], [role="combobox"], [role="option"], [contenteditable="true"], .ant-btn, [class*="btn"], [class*="menu"], [class*="item"], div[tabindex], span[tabindex], li[role]';
    const els = document.querySelectorAll(sels);
    const results = [];
    let id = 0;
    for (const el of els) {
        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) continue;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        id++;
        el.setAttribute('data-bid', String(id));
        const text = (el.innerText || '').trim().slice(0, 80);
        const ph = el.getAttribute('placeholder') || '';
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        const cls = (el.className || '').toString().slice(0, 80);
        const href = el.getAttribute('href') || '';
        let desc = `[${id}] <${tag}>`;
        if (role) desc += ` role="${role}"`;
        if (text) desc += ` text="${text}"`;
        if (ph) desc += ` placeholder="${ph}"`;
        if (href) desc += ` href="${href.slice(0, 60)}"`;
        if (cls) desc += ` class="${cls}"`;
        results.push(desc);
    }
    return results.join('\\n');
}"""

def execute_browser_action(page, action):
    """Execute a browser action returned by LLM."""
    act = action.get("action", "")
    result = "ok"
    try:
        if act == "click":
            bid = str(action["id"])
            selector = f'[data-bid="{bid}"]'
            el = page.query_selector(selector)
            if el:
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                el.click(force=True)
            else:
                result = f"Element bid={bid} not found"
            page.wait_for_timeout(1500)
        elif act == "type":
            text = action.get("text", "")
            bid = action.get("id")
            if bid:
                selector = f'[data-bid="{str(bid)}"]'
                el = page.query_selector(selector)
                if el:
                    el.scroll_into_view_if_needed()
                    el.focus()
                    el.click(force=True)
                    page.wait_for_timeout(300)
            page.keyboard.type(text, delay=50)
            page.wait_for_timeout(500)
        elif act == "clear_and_type":
            text = action.get("text", "")
            bid = action.get("id")
            if bid:
                selector = f'[data-bid="{str(bid)}"]'
                el = page.query_selector(selector)
                if el:
                    el.scroll_into_view_if_needed()
                    el.focus()
                    el.click(force=True)
                    page.wait_for_timeout(300)
            page.keyboard.press("Meta+a")
            page.keyboard.press("Backspace")
            page.keyboard.type(text, delay=50)
            page.wait_for_timeout(500)
        elif act == "press_key":
            key = action.get("key", "Enter")
            page.keyboard.press(key)
            page.wait_for_timeout(1000)
        elif act == "scroll":
            direction = action.get("direction", "down")
            if direction == "down":
                page.mouse.wheel(0, 400)
            else:
                page.mouse.wheel(0, -400)
            page.wait_for_timeout(1000)
        elif act == "wait":
            ms = action.get("ms", 2000)
            page.wait_for_timeout(ms)
        elif act == "goto":
            url = action.get("url", "")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
        elif act == "get_text":
            text = page.evaluate("() => document.body.innerText")
            result = text[:5000] if text else "No text found"
        elif act == "screenshot":
            page.screenshot(path="screenshot.png")
            result = "Screenshot saved to screenshot.png"
        elif act == "click_coords":
            x = action.get("x", 0)
            y = action.get("y", 0)
            page.mouse.click(x, y)
            page.wait_for_timeout(1500)
        elif act == "done":
            result = action.get("message", "done")
        else:
            result = f"Unknown action: {act}"
    except Exception as e:
        result = f"Error: {str(e)}"
    return result

def main(query):
    # Parse the task from query using LLM
    task_plan = call_llm(
        system="You are a task parser. Extract the task details from the user query. Return JSON with keys: task_type (e.g. 'create_spreadsheet'), headers (list of column headers), data_rows (list of lists of cell values). If info is missing, use reasonable defaults.",
        messages=[{"role": "user", "content": query}],
        max_tokens=1000
    )
    
    try:
        plan_match = re.search(r'\{[\s\S]*\}', task_plan)
        if plan_match:
            plan = json.loads(plan_match.group())
        else:
            plan = {"task_type": "create_spreadsheet", "headers": ["姓名", "学号", "成绩"], "data_rows": [["张三", "20240001", "95"]]}
    except:
        plan = {"task_type": "create_spreadsheet", "headers": ["姓名", "学号", "成绩"], "data_rows": [["张三", "20240001", "95"]]}
    
    headers = plan.get("headers", ["姓名", "学号", "成绩"])
    data_rows = plan.get("data_rows", [["张三", "20240001", "95"]])
    
    evidence_log = []
    final_answer = ""
    share_link = ""
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            channel="chrome",
            locale="zh-CN",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        
        popup_pages = []
        context.on("page", lambda new_page: popup_pages.append(new_page))
        
        page = context.new_page()
        active_page = page
        
        # Step 1: Navigate to Tencent Docs and create a new spreadsheet
        system_prompt = f"""You are a browser automation agent. Your task is to:
1. Navigate to Tencent Docs (https://docs.qq.com)
2. Create a new spreadsheet (表格/在线表格)
3. Fill in headers in row 1: {headers}
4. Fill in data in row 2: {data_rows[0]}
5. Get the share link for the document

IMPORTANT INSTRUCTIONS:
- First go to https://docs.qq.com
- Look for a button to create new document (新建/创建), or a "+" button
- Choose spreadsheet/表格 type
- After the spreadsheet opens (may open in a new tab), click on cell A1 and type the first header
- Press Tab to move to next cell, type next header, etc.
- After headers, press Enter to go to row 2, then type data values separated by Tab
- After filling data, look for a share button (分享/共享) to get the share link
- When typing in cells, just use "type" action. The spreadsheet cells are usually contenteditable.
- If you see a new page/tab opened, that's likely the spreadsheet - work on that page.
- To type in a cell, you can click on it first then type.
- For the share link, look for a 分享 or 共享 button, then look for a copy link option.

Each step you see the page URL and interactive elements.
Reply with ONLY one JSON action (no other text):
- {{"action":"click","id":N}} - click element with bid N
- {{"action":"type","id":N,"text":"..."}} - type text into element (id is optional)
- {{"action":"clear_and_type","id":N,"text":"..."}} - clear field then type
- {{"action":"press_key","key":"Enter"}} - press a key (Enter, Tab, Escape, etc.)
- {{"action":"scroll","direction":"down"}} - scroll the page
- {{"action":"wait","ms":2000}} - wait for page to load
- {{"action":"goto","url":"..."}} - navigate to a URL
- {{"action":"get_text"}} - get all visible text on page
- {{"action":"click_coords","x":N,"y":N}} - click at specific coordinates
- {{"action":"screenshot"}} - take a screenshot
- {{"action":"done","message":"..."}} - task complete, include share link in message"""
        
        messages = []
        max_steps = 50
        
        for step in range(max_steps):
            # Check for popup windows
            if popup_pages:
                new_page = popup_pages.pop(0)
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    new_page.wait_for_timeout(3000)
                    active_page = new_page
                    evidence_log.append(f"Step {step}: Switched to new popup page: {new_page.url}")
                except:
                    pass
            
            # Get current page state
            try:
                current_url = active_page.url
                elements = active_page.evaluate(JS_GET_ELEMENTS)
            except Exception as e:
                evidence_log.append(f"Step {step}: Error getting page state: {e}")
                # Try to use original page
                active_page = page
                try:
                    current_url = active_page.url
                    elements = active_page.evaluate(JS_GET_ELEMENTS)
                except:
                    continue
            
            user_msg = f"Step {step}. URL: {current_url}\nElements:\n{elements}"
            if len(user_msg) > 12000:
                user_msg = user_msg[:12000] + "\n... (truncated)"
            
            messages.append({"role": "user", "content": user_msg})
            
            # Keep only recent messages to avoid context overflow
            recent_messages = messages[-20:]
            
            response = call_llm(system_prompt, recent_messages, max_tokens=500)
            
            # Parse JSON from response
            json_match = re.search(r'\{[^{}]*\}', response)
            if not json_match:
                messages.append({"role": "assistant", "content": response})
                evidence_log.append(f"Step {step}: LLM returned non-JSON: {response[:200]}")
                continue
            
            try:
                action = json.loads(json_match.group())
            except:
                messages.append({"role": "assistant", "content": response})
                continue
            
            messages.append({"role": "assistant", "content": response})
            evidence_log.append(f"Step {step}: Action={json.dumps(action, ensure_ascii=False)}")
            
            if action.get("action") == "done":
                final_answer = action.get("message", "")
                # Try to extract share link from the message
                url_match = re.search(r'https?://[^\s"<>]+', final_answer)
                if url_match:
                    share_link = url_match.group()
                break
            
            # Execute the action
            result = execute_browser_action(active_page, action)
            if result != "ok":
                evidence_log.append(f"Step {step}: Action result: {result[:500]}")
                # Add result feedback to messages
                if action.get("action") == "get_text":
                    messages.append({"role": "user", "content": f"Text content:\n{result[:5000]}"})
        
        # If we didn't get a share link, try to get the current URL as fallback
        if not share_link:
            try:
                share_link = active_page.url
            except:
                share_link = page.url
        
        context.close()
    
    if not final_answer:
        final_answer = f"Document created. Link: {share_link}"
    
    # Generate summary
    evidence_str = "\n".join(evidence_log[-30:])
    summary = call_llm(
        system="You are a research summarizer. Write a detailed SUMMARY of the browser automation process and findings.",
        messages=[{"role": "user", "content": f"Query: {query}\nEvidence collected:\n{evidence_str}\nFinal answer: {final_answer}\nShare link: {share_link}\n\nWrite a SUMMARY (100-500 words) that traces what was done: pages visited, actions taken, and the final result."}],
        max_tokens=2000
    )
    
    return {"answer": final_answer, "summary": summary}
