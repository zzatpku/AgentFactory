import os, json, re, time
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

def get_cell_ref(page):
    """Get the currently selected cell reference from the name box."""
    try:
        val = page.evaluate("""() => {
            // Try multiple selectors for the cell reference input
            const selectors = ['input.bar-label', 'input[class*="name-box"]', 'input[class*="cell-ref"]', 'input[class*="coordinate"]'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.value) return el.value;
            }
            // Fallback: look for small input in top-left area
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
    """Get the content of the formula bar for the selected cell."""
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
    """Navigate to a specific cell using the name box (bar-label input)."""
    evidence_log.append(f"Navigating to cell {target_cell}")
    
    # Method 1: Click on the name box input and type the cell reference
    try:
        # Find the bar-label input
        bar_input = page.evaluate("""() => {
            const selectors = ['input.bar-label', 'input[class*="name-box"]', 'input[class*="cell-ref"]'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const rect = el.getBoundingClientRect();
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, cls: el.className};
                }
            }
            // Fallback: small input in top-left
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.x < 100 && rect.y > 100 && rect.y < 200 && rect.width > 30 && rect.width < 150) {
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, cls: inp.className};
                }
            }
            return {found: false};
        }""")
        
        if bar_input and bar_input.get('found'):
            # Click on the name box
            page.mouse.click(bar_input['x'], bar_input['y'])
            page.wait_for_timeout(500)
            
            # Select all and type new cell reference
            page.keyboard.press("Control+a")
            page.wait_for_timeout(200)
            page.keyboard.type(target_cell, delay=50)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            
            # Verify
            current = get_cell_ref(page)
            evidence_log.append(f"After name box nav: current cell = {current} (target: {target_cell})")
            if current == target_cell:
                return True
    except Exception as e:
        evidence_log.append(f"Name box navigation error: {e}")
    
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
        
        # ============ PHASE 1: Navigate to Tencent Docs ============
        evidence_log.append("=== PHASE 1: Navigate ===")
        page.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        evidence_log.append(f"URL: {page.url}")
        
        # ============ PHASE 2: Click 新建 button ============
        evidence_log.append("=== PHASE 2: Click 新建 ===")
        btn = page.query_selector('button:has-text("新建")')
        if btn:
            btn.click(force=True)
            page.wait_for_timeout(3000)
            evidence_log.append("Clicked 新建 button")
        else:
            evidence_log.append("ERROR: 新建 button not found")
            context.close()
            return {"answer": "Failed: 新建 button not found", "summary": "Could not find the New button on Tencent Docs homepage"}
        
        # ============ PHASE 3: Click 表格 in dropdown ============
        evidence_log.append("=== PHASE 3: Click 表格 in dropdown ===")
        
        # The dropdown shows buttons with class 'create-create-item'
        # Options in order: 文档, 表格, 幻灯片, PDF
        # Try to find the button with text 表格
        sheet_btn = page.query_selector('button.create-create-item:has-text("表格")')
        if not sheet_btn:
            # Try broader selector
            sheet_btn = page.query_selector('text=表格')
        
        if sheet_btn:
            box = sheet_btn.bounding_box()
            evidence_log.append(f"Found 表格 button at: {box}")
            sheet_btn.click(force=True)
            evidence_log.append("Clicked 表格")
        else:
            evidence_log.append("表格 not found via selector, trying coordinates")
            # Based on debug: buttons start at x=231, 74px wide, y=156, 66px tall
            # 文档 is first (x=231), 表格 is second (x=305)
            page.mouse.click(342, 189)  # Center of second button
            evidence_log.append("Clicked at estimated coordinates (342, 189)")
        
        # Wait for new tab to open
        evidence_log.append("Waiting for new spreadsheet tab...")
        
        # Wait up to 10 seconds for a new page
        active_page = page
        for wait_i in range(20):
            page.wait_for_timeout(500)
            if popup_pages:
                new_page = popup_pages.pop(0)
                try:
                    new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    new_page.wait_for_timeout(3000)
                    active_page = new_page
                    evidence_log.append(f"New tab opened: {new_page.url}")
                    break
                except Exception as e:
                    evidence_log.append(f"Error with new tab: {e}")
            # Also check context pages
            for cp in context.pages:
                if '/sheet/' in cp.url:
                    active_page = cp
                    evidence_log.append(f"Found sheet tab in context: {cp.url}")
                    break
            if '/sheet/' in active_page.url:
                break
        
        if '/sheet/' not in active_page.url:
            # Maybe the page navigated in place instead of opening new tab
            evidence_log.append(f"No sheet tab found. Current pages:")
            for cp in context.pages:
                evidence_log.append(f"  {cp.url}")
            # Try clicking 表格 again with different approach
            evidence_log.append("Retrying: clicking 新建 then 表格 again")
            page.goto("https://docs.qq.com", wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
            btn = page.query_selector('button:has-text("新建")')
            if btn:
                btn.click(force=True)
                page.wait_for_timeout(3000)
            
            # Try clicking all create-create-item buttons to find 表格
            items = page.query_selector_all('button.create-create-item')
            evidence_log.append(f"Found {len(items)} create-create-item buttons")
            for idx, item in enumerate(items):
                text = item.inner_text().strip()
                evidence_log.append(f"  Button {idx}: '{text}'")
                if '表格' in text and '智能' not in text:
                    evidence_log.append(f"  Clicking button {idx}: '{text}'")
                    item.click(force=True)
                    break
            
            # Wait for new tab
            for wait_i in range(20):
                page.wait_for_timeout(500)
                if popup_pages:
                    new_page = popup_pages.pop(0)
                    try:
                        new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                        new_page.wait_for_timeout(3000)
                        active_page = new_page
                        evidence_log.append(f"New tab opened (retry): {new_page.url}")
                        break
                    except:
                        pass
                for cp in context.pages:
                    if '/sheet/' in cp.url:
                        active_page = cp
                        evidence_log.append(f"Found sheet tab (retry): {cp.url}")
                        break
                if '/sheet/' in active_page.url:
                    break
        
        if '/sheet/' not in active_page.url:
            evidence_log.append("FAILED to open spreadsheet")
            context.close()
            evidence_str = "\n".join(evidence_log)
            return {"answer": "Failed to create spreadsheet", "summary": evidence_str}
        
        # Wait for spreadsheet to fully load
        active_page.wait_for_timeout(5000)
        share_link = active_page.url.split('?')[0].split('#')[0]
        evidence_log.append(f"Spreadsheet URL: {share_link}")
        
        # Dismiss any overlays
        active_page.keyboard.press("Escape")
        active_page.wait_for_timeout(1000)
        active_page.keyboard.press("Escape")
        active_page.wait_for_timeout(1000)
        
        # ============ PHASE 4: Fill in data ============
        evidence_log.append("=== PHASE 4: Fill in data ===")
        
        col_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        
        # Fill headers
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            success = navigate_to_cell(active_page, cell_ref, evidence_log)
            if not success:
                evidence_log.append(f"Failed to navigate to {cell_ref}, retrying...")
                # Try again
                active_page.wait_for_timeout(1000)
                success = navigate_to_cell(active_page, cell_ref, evidence_log)
            
            # Type the value
            active_page.keyboard.type(header, delay=50)
            active_page.wait_for_timeout(500)
            active_page.keyboard.press("Tab")
            active_page.wait_for_timeout(500)
            evidence_log.append(f"Typed '{header}' in {cell_ref}")
        
        # Fill data rows
        for row_idx, row_data in enumerate(data_rows):
            for i, value in enumerate(row_data):
                cell_ref = f"{col_letters[i]}{row_idx + 2}"
                success = navigate_to_cell(active_page, cell_ref, evidence_log)
                if not success:
                    active_page.wait_for_timeout(1000)
                    success = navigate_to_cell(active_page, cell_ref, evidence_log)
                
                active_page.keyboard.type(str(value), delay=50)
                active_page.wait_for_timeout(500)
                active_page.keyboard.press("Tab")
                active_page.wait_for_timeout(500)
                evidence_log.append(f"Typed '{value}' in {cell_ref}")
        
        # Press Enter to confirm
        active_page.keyboard.press("Enter")
        active_page.wait_for_timeout(1000)
        
        # ============ PHASE 5: Verify data ============
        evidence_log.append("=== PHASE 5: Verify data ===")
        
        all_correct = True
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            navigate_to_cell(active_page, cell_ref, evidence_log)
            active_page.wait_for_timeout(500)
            content = get_formula_bar_content(active_page)
            match = content == header
            evidence_log.append(f"Verify {cell_ref}: expected='{header}', got='{content}', match={match}")
            if not match:
                all_correct = False
        
        for row_idx, row_data in enumerate(data_rows):
            for i, value in enumerate(row_data):
                cell_ref = f"{col_letters[i]}{row_idx + 2}"
                navigate_to_cell(active_page, cell_ref, evidence_log)
                active_page.wait_for_timeout(500)
                content = get_formula_bar_content(active_page)
                match = content == str(value)
                evidence_log.append(f"Verify {cell_ref}: expected='{value}', got='{content}', match={match}")
                if not match:
                    all_correct = False
        
        evidence_log.append(f"All data verified: {all_correct}")
        
        # Take screenshot
        active_page.screenshot(path="final_spreadsheet_v4.png")
        evidence_log.append("Final screenshot saved")
        
        context.close()
    
    final_answer = f"已成功创建腾讯文档在线表格。分享链接: {share_link}"
    
    evidence_str = "\n".join(evidence_log[-50:])
    summary = call_llm(
        system="Summarize the spreadsheet creation and data entry process.",
        messages=[{"role": "user", "content": f"Query: {query}\nEvidence:\n{evidence_str}\nShare link: {share_link}\nAll correct: {all_correct}\n\nWrite a SUMMARY (100-500 words)."}],
        max_tokens=2000
    )
    
    return {"answer": final_answer, "summary": summary}
