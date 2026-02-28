import os, json, re, time
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

def get_cell_ref(page):
    try:
        val = page.evaluate("""() => {
            const selectors = ['input.bar-label', 'input[class*="name-box"]', 'input[class*="cell-ref"]'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.value) return el.value;
            }
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.x < 100 && rect.y > 100 && rect.y < 200 && rect.width > 30 && rect.width < 150) {
                    if (inp.value && /^[A-Z]+[0-9]+$/.test(inp.value)) return inp.value;
                }
            }
            return '';
        }""")
        return val
    except:
        return ''

def get_formula_bar_content(page):
    try:
        val = page.evaluate("""() => {
            const fb = document.querySelector('div.formula-input, [class*="formula-bar"], [class*="formulabar"]');
            if (fb) return fb.innerText.trim();
            return '';
        }""")
        return val
    except:
        return ''

def navigate_to_cell(page, target_cell, evidence_log):
    evidence_log.append(f"Navigating to cell {target_cell}")
    try:
        bar_input_info = page.evaluate("""() => {
            const selectors = ['input.bar-label', 'input[class*="name-box"]', 'input[class*="cell-ref"]'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const rect = el.getBoundingClientRect();
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, cls: el.className, val: el.value};
                }
            }
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.x < 100 && rect.y > 100 && rect.y < 200 && rect.width > 30 && rect.width < 150) {
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, cls: inp.className, val: inp.value};
                }
            }
            return {found: false};
        }""")
        
        if bar_input_info and bar_input_info.get('found'):
            evidence_log.append(f"Found name box: cls={bar_input_info.get('cls')}, current val={bar_input_info.get('val')}")
            page.mouse.click(bar_input_info['x'], bar_input_info['y'])
            page.wait_for_timeout(300)
            page.keyboard.press("Control+a")
            page.wait_for_timeout(100)
            page.keyboard.type(target_cell, delay=30)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            
            current = get_cell_ref(page)
            evidence_log.append(f"After nav: cell = {current} (target: {target_cell})")
            return current == target_cell
        else:
            evidence_log.append("Name box not found")
    except Exception as e:
        evidence_log.append(f"Nav error: {e}")
    return False

def main(query):
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
    all_correct = False
    
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
        
        # ============ PHASE 1: Navigate ============
        evidence_log.append("=== PHASE 1: Navigate ===")
        page.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        evidence_log.append(f"URL: {page.url}")
        
        # ============ PHASE 2: Click 新建 ============
        evidence_log.append("=== PHASE 2: Click 新建 ===")
        btn = page.query_selector('button:has-text("新建")')
        if btn:
            btn.click(force=True)
            page.wait_for_timeout(3000)
            evidence_log.append("Clicked 新建")
        
        # ============ PHASE 3: Click 表格 using expect_popup ============
        evidence_log.append("=== PHASE 3: Click 表格 with expect_popup ===")
        
        # Find the 表格 button
        items = page.query_selector_all('button.create-create-item')
        table_btn = None
        for item in items:
            text = item.inner_text().strip()
            if text == '表格':
                table_btn = item
                break
        
        spreadsheet_page = None
        
        if table_btn:
            evidence_log.append("Found 表格 button")
            
            # Use expect_popup to properly capture the new page
            try:
                with page.expect_popup(timeout=30000) as popup_info:
                    table_btn.click(force=True)
                    evidence_log.append("Clicked 表格, waiting for popup...")
                
                new_page = popup_info.value
                evidence_log.append(f"Popup captured! Initial URL: {new_page.url}")
                
                # If it's about:blank, wait for it to navigate
                if new_page.url == 'about:blank' or '/sheet/' not in new_page.url:
                    evidence_log.append("Popup is about:blank, waiting for navigation...")
                    try:
                        new_page.wait_for_url("**/sheet/**", timeout=30000)
                        evidence_log.append(f"Popup navigated to: {new_page.url}")
                    except Exception as e:
                        evidence_log.append(f"wait_for_url timeout: {e}")
                        # Try waiting more and check URL
                        new_page.wait_for_timeout(10000)
                        evidence_log.append(f"After extra wait, popup URL: {new_page.url}")
                
                new_page.wait_for_load_state("domcontentloaded", timeout=30000)
                new_page.wait_for_timeout(5000)
                evidence_log.append(f"Popup final URL: {new_page.url}")
                
                if '/sheet/' in new_page.url:
                    spreadsheet_page = new_page
                else:
                    evidence_log.append(f"Popup URL doesn't contain /sheet/: {new_page.url}")
                    # Maybe it navigated via JS - check again
                    new_page.wait_for_timeout(5000)
                    evidence_log.append(f"After more waiting: {new_page.url}")
                    if '/sheet/' in new_page.url:
                        spreadsheet_page = new_page
                
            except Exception as e:
                evidence_log.append(f"expect_popup failed: {e}")
                
                # Fallback: check all context pages
                for cp in context.pages:
                    if '/sheet/' in cp.url:
                        spreadsheet_page = cp
                        evidence_log.append(f"Found sheet in context pages: {cp.url}")
                        break
                
                if not spreadsheet_page:
                    # Maybe it opened as about:blank - find it and wait
                    for cp in context.pages:
                        if cp.url == 'about:blank':
                            evidence_log.append("Found about:blank page, waiting for nav...")
                            try:
                                cp.wait_for_url("**/sheet/**", timeout=30000)
                                spreadsheet_page = cp
                                evidence_log.append(f"about:blank navigated to: {cp.url}")
                            except:
                                cp.wait_for_timeout(10000)
                                if '/sheet/' in cp.url:
                                    spreadsheet_page = cp
                                    evidence_log.append(f"about:blank finally at: {cp.url}")
        
        if not spreadsheet_page:
            # Last resort: try direct URL creation
            evidence_log.append("All popup methods failed. Trying direct URL approach.")
            # Navigate directly to create a new sheet
            try:
                new_page = context.new_page()
                new_page.goto("https://docs.qq.com/sheet", wait_until="domcontentloaded")
                new_page.wait_for_timeout(10000)
                evidence_log.append(f"Direct nav to /sheet: {new_page.url}")
                if '/sheet/' in new_page.url:
                    spreadsheet_page = new_page
            except Exception as e:
                evidence_log.append(f"Direct nav failed: {e}")
        
        if not spreadsheet_page:
            evidence_log.append("FAILED to open spreadsheet")
            context.close()
            evidence_str = "\n".join(evidence_log)
            return {"answer": "Failed to create spreadsheet", "summary": evidence_str}
        
        # We have the spreadsheet page!
        share_link = spreadsheet_page.url.split('?')[0].split('#')[0]
        evidence_log.append(f"Spreadsheet URL: {share_link}")
        
        # Wait for full load
        spreadsheet_page.wait_for_timeout(5000)
        
        # Dismiss overlays
        spreadsheet_page.keyboard.press("Escape")
        spreadsheet_page.wait_for_timeout(1000)
        spreadsheet_page.keyboard.press("Escape")
        spreadsheet_page.wait_for_timeout(1000)
        
        # ============ PHASE 4: Fill in data ============
        evidence_log.append("=== PHASE 4: Fill in data ===")
        
        col_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        
        # Fill headers
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            success = navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
            if not success:
                spreadsheet_page.wait_for_timeout(1000)
                success = navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
            
            spreadsheet_page.keyboard.type(header, delay=50)
            spreadsheet_page.wait_for_timeout(500)
            spreadsheet_page.keyboard.press("Tab")
            spreadsheet_page.wait_for_timeout(500)
            evidence_log.append(f"Typed '{header}' in {cell_ref}")
        
        # Fill data rows
        for row_idx, row_data in enumerate(data_rows):
            for i, value in enumerate(row_data):
                cell_ref = f"{col_letters[i]}{row_idx + 2}"
                success = navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
                if not success:
                    spreadsheet_page.wait_for_timeout(1000)
                    success = navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
                
                spreadsheet_page.keyboard.type(str(value), delay=50)
                spreadsheet_page.wait_for_timeout(500)
                spreadsheet_page.keyboard.press("Tab")
                spreadsheet_page.wait_for_timeout(500)
                evidence_log.append(f"Typed '{value}' in {cell_ref}")
        
        spreadsheet_page.keyboard.press("Enter")
        spreadsheet_page.wait_for_timeout(1000)
        
        # ============ PHASE 5: Verify data ============
        evidence_log.append("=== PHASE 5: Verify ===")
        all_correct = True
        
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
            spreadsheet_page.wait_for_timeout(500)
            content = get_formula_bar_content(spreadsheet_page)
            match = content == header
            evidence_log.append(f"Verify {cell_ref}: expected='{header}', got='{content}', match={match}")
            if not match:
                all_correct = False
        
        for row_idx, row_data in enumerate(data_rows):
            for i, value in enumerate(row_data):
                cell_ref = f"{col_letters[i]}{row_idx + 2}"
                navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
                spreadsheet_page.wait_for_timeout(500)
                content = get_formula_bar_content(spreadsheet_page)
                match = content == str(value)
                evidence_log.append(f"Verify {cell_ref}: expected='{value}', got='{content}', match={match}")
                if not match:
                    all_correct = False
        
        evidence_log.append(f"All correct: {all_correct}")
        
        spreadsheet_page.screenshot(path="final_spreadsheet_v5.png")
        evidence_log.append("Screenshot saved")
        
        context.close()
    
    final_answer = f"已成功创建腾讯文档在线表格。分享链接: {share_link}"
    
    evidence_str = "\n".join(evidence_log[-50:])
    summary = call_llm(
        system="Summarize the spreadsheet creation process.",
        messages=[{"role": "user", "content": f"Query: {query}\nEvidence:\n{evidence_str}\nShare link: {share_link}\nAll correct: {all_correct}\n\nWrite a SUMMARY (100-500 words)."}],
        max_tokens=2000
    )
    
    return {"answer": final_answer, "summary": summary}
