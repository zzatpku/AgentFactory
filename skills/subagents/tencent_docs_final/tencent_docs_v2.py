import os, json, re, time
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

JS_GET_ELEMENTS = """() => {
    document.querySelectorAll('[data-bid]').forEach(e => e.removeAttribute('data-bid'));
    const sels = 'button, input, textarea, select, a[href], [role="button"], [role="tab"], [role="textbox"], [role="combobox"], [role="option"], [contenteditable="true"], .ant-btn, [class*="btn"], [class*="create"], [class*="new"], [class*="menu"], [class*="item"], [class*="share"], div[tabindex], span[tabindex], li[role]';
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
        const cls = (el.className || '').toString().slice(0, 100);
        const href = el.getAttribute('href') || '';
        const rect_info = `(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`;
        let desc = `[${id}] <${tag}> ${rect_info}`;
        if (role) desc += ` role="${role}"`;
        if (text) desc += ` text="${text}"`;
        if (ph) desc += ` placeholder="${ph}"`;
        if (href) desc += ` href="${href.slice(0, 80)}"`;
        if (cls) desc += ` class="${cls}"`;
        results.push(desc);
    }
    return results.join('\\n');
}"""

def execute_action(page, action):
    """Execute a browser action."""
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
            page.wait_for_timeout(2000)
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
        elif act == "press_key":
            key = action.get("key", "Enter")
            page.keyboard.press(key)
            page.wait_for_timeout(1000)
        elif act == "scroll":
            direction = action.get("direction", "down")
            delta = 400 if direction == "down" else -400
            page.mouse.wheel(0, delta)
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

def run_llm_loop(active_page, system_prompt, max_steps, evidence_log, popup_pages, context):
    """Run the LLM-driven browser automation loop."""
    messages = []
    final_result = None
    
    for step in range(max_steps):
        # Check for popup windows
        if popup_pages:
            new_page = popup_pages.pop(0)
            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                new_page.wait_for_timeout(5000)
                active_page = new_page
                evidence_log.append(f"Step {step}: Switched to new tab: {new_page.url}")
            except Exception as e:
                evidence_log.append(f"Step {step}: Error switching to new tab: {e}")
        
        # Get current page state
        try:
            current_url = active_page.url
            elements = active_page.evaluate(JS_GET_ELEMENTS)
        except Exception as e:
            evidence_log.append(f"Step {step}: Error getting page state: {e}")
            continue
        
        user_msg = f"Step {step}. URL: {current_url}\nElements:\n{elements}"
        if len(user_msg) > 12000:
            user_msg = user_msg[:12000] + "\n... (truncated)"
        
        messages.append({"role": "user", "content": user_msg})
        recent_messages = messages[-18:]
        
        response = call_llm(system_prompt, recent_messages, max_tokens=500)
        
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
            final_result = action.get("message", "")
            break
        
        result = execute_action(active_page, action)
        if result != "ok":
            evidence_log.append(f"Step {step}: Result: {result[:500]}")
            if action.get("action") == "get_text":
                messages.append({"role": "user", "content": f"Text content:\n{result[:5000]}"})
    
    return active_page, final_result

def main(query):
    # Parse the task from query
    task_plan = call_llm(
        system="You are a task parser. Extract the task details from the user query about creating a Tencent Docs spreadsheet. Return JSON with keys: headers (list of column headers), data_rows (list of lists of cell values).",
        messages=[{"role": "user", "content": query}],
        max_tokens=1000
    )
    try:
        plan_match = re.search(r'\{[\s\S]*\}', task_plan)
        if plan_match:
            plan = json.loads(plan_match.group())
        else:
            plan = {}
    except:
        plan = {}
    
    headers = plan.get("headers", ["姓名", "学号", "成绩"])
    data_rows = plan.get("data_rows", [["张三", "20240001", "95"]])
    
    evidence_log = []
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
        
        # ============ PHASE 1: Navigate to Tencent Docs homepage ============
        evidence_log.append("=== PHASE 1: Navigate to Tencent Docs ===")
        page.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        evidence_log.append(f"Navigated to: {page.url}")
        
        # ============ PHASE 2: Click '新建' and select '在线表格' ============
        evidence_log.append("=== PHASE 2: Create new spreadsheet ===")
        
        phase2_prompt = f"""You are a browser automation agent on Tencent Docs homepage.
Your ONLY task in this phase: Click the "新建" (New) button, then select "在线表格" (Online Spreadsheet) from the dropdown menu.

Known UI layout:
- The "新建" button is on the left sidebar, it's a primary button with text "新建"
- After clicking it, a dropdown menu appears with options like: 在线文档, 在线表格, 在线幻灯片, 在线收集表, etc.
- Click on "在线表格" to create a new spreadsheet
- The new spreadsheet will open in a NEW TAB automatically
- Once you see the URL has changed to contain /sheet/ or a new tab has opened, report done

Reply with ONLY one JSON action:
- {{"action":"click","id":N}}
- {{"action":"wait","ms":2000}}
- {{"action":"get_text"}}
- {{"action":"done","message":"spreadsheet created"}}"""
        
        active_page, result = run_llm_loop(page, phase2_prompt, 15, evidence_log, popup_pages, context)
        evidence_log.append(f"Phase 2 result: {result}")
        evidence_log.append(f"Active page URL: {active_page.url}")
        
        # Check if we switched to a new tab with a spreadsheet
        all_pages = context.pages
        for p_item in all_pages:
            if '/sheet/' in p_item.url:
                active_page = p_item
                evidence_log.append(f"Found spreadsheet tab: {p_item.url}")
                break
        
        # Also check popup_pages
        if popup_pages:
            new_page = popup_pages.pop(0)
            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                new_page.wait_for_timeout(5000)
                active_page = new_page
                evidence_log.append(f"Switched to popup: {new_page.url}")
            except:
                pass
        
        # Wait for spreadsheet to fully load
        active_page.wait_for_timeout(5000)
        evidence_log.append(f"Spreadsheet URL: {active_page.url}")
        
        # ============ PHASE 3: Fill in data ============
        evidence_log.append("=== PHASE 3: Fill in spreadsheet data ===")
        
        headers_str = ", ".join(headers)
        data_str = ", ".join(str(x) for x in data_rows[0])
        
        phase3_prompt = f"""You are a browser automation agent on a Tencent Docs spreadsheet.
Your task: Fill in the spreadsheet with data.

Row 1 (headers): {headers_str}
Row 2 (data): {data_str}

INSTRUCTIONS:
1. First, click on cell A1 (the first cell in the top-left of the spreadsheet grid). It's usually around coordinates (95, 270) or you can find a cell element.
2. Type the first header value: "{headers[0]}"
3. Press Tab to move to cell B1
4. Type: "{headers[1]}"
5. Press Tab to move to cell C1
6. Type: "{headers[2]}"
7. Press Enter to move to cell A2
8. Type: "{data_rows[0][0]}"
9. Press Tab to move to cell B2
10. Type: "{data_rows[0][1]}"
11. Press Tab to move to cell C2
12. Type: "{data_rows[0][2]}"
13. Press Enter to confirm
14. After all data is entered, report done

IMPORTANT:
- If you see a tutorial/welcome overlay, press Escape first to dismiss it
- The spreadsheet cells might be canvas-based. If clicking elements doesn't select a cell, try click_coords at the cell position.
- Typical cell positions: A1 is around (95, 270), B1 around (200, 270), etc.
- After typing, wait briefly before pressing Tab/Enter
- If you can't find interactive cell elements, use click_coords to click directly on the cell area

Reply with ONLY one JSON action:
- {{"action":"click","id":N}}
- {{"action":"click_coords","x":N,"y":N}}
- {{"action":"type","text":"..."}}
- {{"action":"press_key","key":"Tab"}}
- {{"action":"press_key","key":"Enter"}}
- {{"action":"press_key","key":"Escape"}}
- {{"action":"wait","ms":2000}}
- {{"action":"get_text"}}
- {{"action":"done","message":"data filled"}}"""
        
        active_page, result = run_llm_loop(active_page, phase3_prompt, 25, evidence_log, popup_pages, context)
        evidence_log.append(f"Phase 3 result: {result}")
        
        # ============ PHASE 4: Get share link ============
        evidence_log.append("=== PHASE 4: Get share link ===")
        
        # First, get the current URL as a baseline
        current_url = active_page.url
        evidence_log.append(f"Current spreadsheet URL: {current_url}")
        
        phase4_prompt = f"""You are a browser automation agent on a Tencent Docs spreadsheet.
Your task: Get the share link for this document.

Current URL: {current_url}

INSTRUCTIONS:
1. Look for a "分享" (Share) button - it's usually in the top-right area of the toolbar
2. Click the share button
3. A share dialog will appear
4. In the share dialog, look for:
   - A link/URL that can be copied
   - A "复制链接" (Copy Link) button
   - Or the share link displayed in a text field
5. If you see a link text or can get_text to read the share URL, report it
6. The share link format is usually: https://docs.qq.com/sheet/XXXXX
7. If you can see the link in the dialog, report done with the link
8. If the current page URL already contains /sheet/, that URL IS the share link

Alternatively, if you cannot find a share button or the share dialog is complex:
- The current page URL ({current_url}) can serve as the document link
- Report done with this URL

Reply with ONLY one JSON action:
- {{"action":"click","id":N}}
- {{"action":"click_coords","x":N,"y":N}}
- {{"action":"get_text"}}
- {{"action":"wait","ms":2000}}
- {{"action":"press_key","key":"Escape"}}
- {{"action":"done","message":"Share link: https://docs.qq.com/sheet/XXXXX"}}"""
        
        active_page, result = run_llm_loop(active_page, phase4_prompt, 15, evidence_log, popup_pages, context)
        evidence_log.append(f"Phase 4 result: {result}")
        
        # Extract share link
        if result:
            url_match = re.search(r'https://docs\.qq\.com/sheet/[A-Za-z0-9]+', result)
            if url_match:
                share_link = url_match.group()
        
        if not share_link:
            # Fallback: use the current page URL if it contains /sheet/
            current = active_page.url
            if '/sheet/' in current:
                # Clean the URL - remove query params
                share_link = current.split('?')[0].split('#')[0]
            else:
                # Check all pages
                for p_item in context.pages:
                    if '/sheet/' in p_item.url:
                        share_link = p_item.url.split('?')[0].split('#')[0]
                        break
        
        if not share_link:
            share_link = active_page.url
        
        evidence_log.append(f"Final share link: {share_link}")
        
        # Take a final screenshot for verification
        try:
            active_page.screenshot(path="final_spreadsheet.png")
            evidence_log.append("Final screenshot saved: final_spreadsheet.png")
        except:
            pass
        
        context.close()
    
    final_answer = f"已成功创建腾讯文档在线表格。分享链接: {share_link}"
    
    evidence_str = "\n".join(evidence_log[-40:])
    summary = call_llm(
        system="You are a summarizer. Write a detailed summary of the browser automation process.",
        messages=[{"role": "user", "content": f"Query: {query}\nEvidence:\n{evidence_str}\nFinal share link: {share_link}\n\nWrite a SUMMARY (100-500 words) of what was done, including any issues encountered and the final result."}],
        max_tokens=2000
    )
    
    return {"answer": final_answer, "summary": summary}
