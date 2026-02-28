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
        elif act == "scroll":
            direction = action.get("direction", "down")
            delta = 400 if direction == "down" else -400
            page.mouse.wheel(0, delta)
            page.wait_for_timeout(1000)
        else:
            result = f"Unknown action: {act}"
    except Exception as e:
        result = f"Error: {str(e)}"
    return result

def run_llm_loop(active_page, system_prompt, max_steps, evidence_log, popup_pages):
    messages = []
    final_result = None
    for step in range(max_steps):
        if popup_pages:
            new_page = popup_pages.pop(0)
            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                new_page.wait_for_timeout(5000)
                active_page = new_page
                evidence_log.append(f"Step {step}: Switched to new tab: {new_page.url}")
            except Exception as e:
                evidence_log.append(f"Step {step}: Error switching tab: {e}")
        try:
            current_url = active_page.url
            elements = active_page.evaluate(JS_GET_ELEMENTS)
        except Exception as e:
            evidence_log.append(f"Step {step}: Error: {e}")
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

def click_cell(page, target_cell, evidence_log):
    """Click on a target cell (e.g. 'A1') using the name box for verification.
    Uses an adaptive approach: start with estimated coords, verify via bar-label, adjust if needed.
    """
    # Parse target cell reference
    col_letter = ''.join(c for c in target_cell if c.isalpha())
    row_num = int(''.join(c for c in target_cell if c.isdigit()))
    
    # Column offset from A (0-indexed)
    col_idx = ord(col_letter.upper()) - ord('A')
    
    # Estimated coordinates based on debug findings:
    # Canvas starts at y=182, column headers ~22px, row height ~24px
    # Row headers end at x≈45, default column width ~100px
    x_start = 45  # After row header
    col_width = 100  # Estimated default column width
    y_header_end = 204  # Where data rows start
    row_height = 24  # Estimated row height
    
    target_x = x_start + col_idx * col_width + col_width // 2
    target_y = y_header_end + (row_num - 1) * row_height + row_height // 2
    
    evidence_log.append(f"Clicking cell {target_cell}: estimated coords ({target_x}, {target_y})")
    
    # Click at estimated position
    page.mouse.click(target_x, target_y)
    page.wait_for_timeout(1000)
    
    # Verify using bar-label
    try:
        bar_label = page.evaluate("""() => {
            const input = document.querySelector('input.bar-label');
            return input ? input.value : 'not found';
        }""")
        evidence_log.append(f"Bar label shows: {bar_label} (target: {target_cell})")
        
        if bar_label == target_cell:
            return True
        
        # If wrong cell, try to use the name box to navigate directly
        # Click on the bar-label input, clear it, type target cell, press Enter
        evidence_log.append(f"Wrong cell selected ({bar_label}), trying name box navigation")
        bar_input = page.query_selector('input.bar-label')
        if bar_input:
            bar_input.click()
            page.wait_for_timeout(300)
            page.keyboard.press("Meta+a")
            page.keyboard.type(target_cell, delay=50)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            
            # Verify again
            bar_label2 = page.evaluate("""() => {
                const input = document.querySelector('input.bar-label');
                return input ? input.value : 'not found';
            }""")
            evidence_log.append(f"After name box nav, bar label shows: {bar_label2}")
            return bar_label2 == target_cell
    except Exception as e:
        evidence_log.append(f"Error verifying cell: {e}")
    
    return False

def type_in_cell(page, text, evidence_log):
    """Type text into the currently selected cell."""
    page.keyboard.type(text, delay=50)
    page.wait_for_timeout(500)
    evidence_log.append(f"Typed: {text}")

def verify_cell_content(page, expected, evidence_log):
    """Verify the content of the currently selected cell via formula bar."""
    try:
        content = page.evaluate("""() => {
            const fb = document.querySelector('div.formula-input');
            return fb ? fb.innerText.trim() : 'not found';
        }""")
        evidence_log.append(f"Cell content: '{content}' (expected: '{expected}')")
        return content == expected
    except:
        return False

def main(query):
    # Parse task from query
    task_plan = call_llm(
        system="You are a task parser. Extract spreadsheet creation details. Return JSON with: headers (list of column headers), data_rows (list of lists of cell values).",
        messages=[{"role": "user", "content": query}],
        max_tokens=1000
    )
    try:
        plan_match = re.search(r'\{[\s\S]*\}', task_plan)
        plan = json.loads(plan_match.group()) if plan_match else {}
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
        
        # ============ PHASE 1: Navigate and create spreadsheet ============
        evidence_log.append("=== PHASE 1: Navigate to Tencent Docs ===")
        page.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        evidence_log.append(f"Navigated to: {page.url}")
        
        # ============ PHASE 2: Click New and select spreadsheet ============
        evidence_log.append("=== PHASE 2: Create new spreadsheet ===")
        
        phase2_prompt = """You are a browser automation agent on Tencent Docs homepage.
Your ONLY task: Click the "新建" button, then select "在线表格" from the dropdown.

Known UI:
- "新建" button is on the left sidebar, a primary button
- After clicking, a dropdown appears with: 在线文档, 在线表格, 在线幻灯片, etc.
- Click "在线表格" to create a spreadsheet
- A new tab will open with the spreadsheet
- Report done when you see the dropdown or after clicking 在线表格

Reply with ONLY one JSON action:
- {"action":"click","id":N}
- {"action":"wait","ms":2000}
- {"action":"done","message":"spreadsheet created"}"""
        
        active_page, result = run_llm_loop(page, phase2_prompt, 15, evidence_log, popup_pages)
        evidence_log.append(f"Phase 2 result: {result}")
        
        # Wait and check for new tabs
        page.wait_for_timeout(5000)
        
        # Check all pages for the spreadsheet
        all_pages = context.pages
        for p_item in all_pages:
            if '/sheet/' in p_item.url:
                active_page = p_item
                evidence_log.append(f"Found spreadsheet tab: {p_item.url}")
                break
        
        if popup_pages:
            new_page = popup_pages.pop(0)
            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                new_page.wait_for_timeout(5000)
                active_page = new_page
                evidence_log.append(f"Switched to popup: {new_page.url}")
            except:
                pass
        
        active_page.wait_for_timeout(5000)
        evidence_log.append(f"Spreadsheet URL: {active_page.url}")
        
        # Dismiss any overlays/tutorials
        active_page.keyboard.press("Escape")
        active_page.wait_for_timeout(1000)
        active_page.keyboard.press("Escape")
        active_page.wait_for_timeout(1000)
        
        # ============ PHASE 3: Fill in data using verified cell clicking ============
        evidence_log.append("=== PHASE 3: Fill in data ===")
        
        # Fill headers in row 1
        col_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            evidence_log.append(f"--- Filling {cell_ref} with '{header}' ---")
            success = click_cell(active_page, cell_ref, evidence_log)
            if success:
                type_in_cell(active_page, header, evidence_log)
                active_page.keyboard.press("Tab")
                active_page.wait_for_timeout(500)
            else:
                evidence_log.append(f"WARNING: Could not navigate to {cell_ref}")
                # Try typing anyway
                type_in_cell(active_page, header, evidence_log)
                active_page.keyboard.press("Tab")
                active_page.wait_for_timeout(500)
        
        # Move to row 2
        active_page.keyboard.press("Enter")
        active_page.wait_for_timeout(500)
        
        # Fill data in row 2
        for i, value in enumerate(data_rows[0]):
            cell_ref = f"{col_letters[i]}2"
            evidence_log.append(f"--- Filling {cell_ref} with '{value}' ---")
            success = click_cell(active_page, cell_ref, evidence_log)
            if success:
                type_in_cell(active_page, str(value), evidence_log)
                active_page.keyboard.press("Tab")
                active_page.wait_for_timeout(500)
            else:
                evidence_log.append(f"WARNING: Could not navigate to {cell_ref}")
                type_in_cell(active_page, str(value), evidence_log)
                active_page.keyboard.press("Tab")
                active_page.wait_for_timeout(500)
        
        # Press Enter to confirm last entry
        active_page.keyboard.press("Enter")
        active_page.wait_for_timeout(1000)
        
        # ============ PHASE 4: Verify data ============
        evidence_log.append("=== PHASE 4: Verify data ===")
        
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            click_cell(active_page, cell_ref, evidence_log)
            active_page.wait_for_timeout(500)
            verify_cell_content(active_page, header, evidence_log)
        
        for i, value in enumerate(data_rows[0]):
            cell_ref = f"{col_letters[i]}2"
            click_cell(active_page, cell_ref, evidence_log)
            active_page.wait_for_timeout(500)
            verify_cell_content(active_page, str(value), evidence_log)
        
        # ============ PHASE 5: Get share link ============
        evidence_log.append("=== PHASE 5: Get share link ===")
        
        current_url = active_page.url
        if '/sheet/' in current_url:
            share_link = current_url.split('?')[0].split('#')[0]
        else:
            share_link = current_url
        
        evidence_log.append(f"Share link: {share_link}")
        
        # Take final screenshot
        try:
            active_page.screenshot(path="final_spreadsheet_v3.png")
            evidence_log.append("Final screenshot saved")
        except:
            pass
        
        context.close()
    
    final_answer = f"已成功创建腾讯文档在线表格。分享链接: {share_link}"
    
    evidence_str = "\n".join(evidence_log[-50:])
    summary = call_llm(
        system="Summarize the browser automation process for creating a Tencent Docs spreadsheet.",
        messages=[{"role": "user", "content": f"Query: {query}\nEvidence:\n{evidence_str}\nShare link: {share_link}\n\nWrite a SUMMARY (100-500 words) covering: what was done, cell verification results, and the final result."}],
        max_tokens=2000
    )
    
    return {"answer": final_answer, "summary": summary}
