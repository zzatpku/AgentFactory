import os, json, re, time
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

def get_cell_ref(page):
    try:
        return page.evaluate("""() => {
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
    except:
        return ''

def get_formula_content(page):
    try:
        return page.evaluate("""() => {
            const fb = document.querySelector('div.formula-input, [class*="formula-bar"]');
            if (fb) return fb.innerText.trim();
            return '';
        }""")
    except:
        return ''

def navigate_to_cell(page, target_cell, evidence_log):
    """Navigate to cell using name box input."""
    try:
        # First, press Escape to exit any cell editing mode
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        
        bar_info = page.evaluate("""() => {
            const selectors = ['input.bar-label', 'input[class*="name-box"]'];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const rect = el.getBoundingClientRect();
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, sel: sel};
                }
            }
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.x < 100 && rect.y > 100 && rect.y < 200 && rect.width > 30 && rect.width < 150) {
                    return {found: true, x: rect.x + rect.width/2, y: rect.y + rect.height/2, sel: 'fallback'};
                }
            }
            return {found: false};
        }""")
        
        if bar_info and bar_info.get('found'):
            # Click on the name box to focus it
            page.mouse.click(bar_info['x'], bar_info['y'])
            page.wait_for_timeout(500)
            
            # Triple-click to select all text in the input
            page.mouse.click(bar_info['x'], bar_info['y'], click_count=3)
            page.wait_for_timeout(300)
            
            # Also try Meta+a (Mac) and Control+a (Linux/Win)
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(100)
            
            # Type the target cell reference
            page.keyboard.type(target_cell, delay=30)
            page.wait_for_timeout(300)
            
            # Press Enter to navigate
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            
            current = get_cell_ref(page)
            evidence_log.append(f"Nav to {target_cell}: current={current}")
            return current == target_cell
        else:
            evidence_log.append(f"Name box not found for {target_cell}")
    except Exception as e:
        evidence_log.append(f"Nav error for {target_cell}: {e}")
    return False

def type_in_cell(page, text, evidence_log):
    """Type text into the currently selected cell via the formula bar."""
    try:
        # Click on the formula bar to focus it
        fb = page.query_selector('div.formula-input')
        if fb:
            fb.click()
            page.wait_for_timeout(300)
            # Type the text
            page.keyboard.type(text, delay=50)
            page.wait_for_timeout(300)
            # Press Enter to commit the value to the cell
            page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            evidence_log.append(f"Typed '{text}' via formula bar")
            return True
        else:
            evidence_log.append("Formula bar not found!")
            return False
    except Exception as e:
        evidence_log.append(f"Type error: {e}")
        return False

def main(query):
    # Parse task
    task_plan = call_llm(
        system="Extract spreadsheet creation details. Return JSON: {\"headers\": [list of column headers], \"data_rows\": [[list of row values]]}",
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
        
        popup_pages = []
        context.on("page", lambda new_page: popup_pages.append(new_page))
        
        page = context.new_page()
        
        # PHASE 1: Navigate
        evidence_log.append("=== PHASE 1: Navigate ===")
        page.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        evidence_log.append(f"URL: {page.url}")
        
        # PHASE 2: Click 新建
        evidence_log.append("=== PHASE 2: Click 新建 ===")
        btn = page.query_selector('button:has-text("新建")')
        if btn:
            btn.click(force=True)
            page.wait_for_timeout(3000)
            evidence_log.append("Clicked 新建")
        
        # PHASE 3: Click 表格 in dropdown
        evidence_log.append("=== PHASE 3: Click 表格 ===")
        items = page.query_selector_all('button.create-create-item')
        for item in items:
            text = item.inner_text().strip()
            if text == '表格':
                item.click(force=True)
                evidence_log.append("Clicked 表格")
                break
        
        page.wait_for_timeout(5000)
        
        # PHASE 4: Click 空白表格 inside the iframe
        evidence_log.append("=== PHASE 4: Click 空白表格 in iframe ===")
        
        # Find the tmall-panel-iframe
        mall_frame = None
        for frame in page.frames:
            if 'mall' in frame.url or 'panel' in frame.url:
                mall_frame = frame
                evidence_log.append(f"Found iframe: {frame.url[:100]}")
                break
        
        if mall_frame:
            # Click the 空白表格 card inside the iframe
            try:
                # Try clicking by text within iframe
                blank_card = mall_frame.query_selector('div.card--2L0vJ:has-text("空白表格")')
                if blank_card:
                    blank_card.click(force=True)
                    evidence_log.append("Clicked 空白表格 card via selector")
                else:
                    # Try alternative selectors
                    blank_card = mall_frame.query_selector('text=空白表格')
                    if blank_card:
                        blank_card.click(force=True)
                        evidence_log.append("Clicked 空白表格 via text selector")
                    else:
                        # Fallback: click at known coordinates within iframe
                        # Iframe is at (101, 61) on main page, card is at (217, 80) within iframe
                        # Absolute: x=101+217+99=417, y=61+80+45=186
                        evidence_log.append("Using coordinate click for 空白表格")
                        page.mouse.click(316, 125)  # Center of first card in iframe coords
                        evidence_log.append("Clicked at absolute coords (316, 125)")
            except Exception as e:
                evidence_log.append(f"Error clicking 空白表格: {e}")
                # Fallback to absolute coords
                page.mouse.click(316, 125)
                evidence_log.append("Fallback: clicked at (316, 125)")
        else:
            evidence_log.append("No iframe found, trying absolute coords")
            page.mouse.click(316, 125)
        
        # Wait for new spreadsheet tab
        evidence_log.append("Waiting for spreadsheet tab...")
        spreadsheet_page = None
        
        for wait_i in range(40):  # 20 seconds
            page.wait_for_timeout(500)
            
            # Check popup pages
            while popup_pages:
                pp = popup_pages.pop(0)
                try:
                    pp_url = pp.url
                    evidence_log.append(f"  Popup detected: {pp_url}")
                    if '/sheet/' in pp_url and len(pp_url) > len('https://docs.qq.com/sheet/'):
                        pp.wait_for_load_state("domcontentloaded", timeout=15000)
                        pp.wait_for_timeout(3000)
                        spreadsheet_page = pp
                        evidence_log.append(f"  Found spreadsheet: {pp_url}")
                    elif pp_url == 'about:blank':
                        # Wait for it to navigate
                        try:
                            pp.wait_for_url("**/sheet/**", timeout=15000)
                            spreadsheet_page = pp
                            evidence_log.append(f"  about:blank navigated to: {pp.url}")
                        except:
                            evidence_log.append(f"  about:blank didn't navigate")
                except:
                    pass
            
            if spreadsheet_page:
                break
            
            # Check context pages
            for cp in context.pages:
                try:
                    if '/sheet/' in cp.url and len(cp.url) > len('https://docs.qq.com/sheet/') + 5:
                        spreadsheet_page = cp
                        evidence_log.append(f"  Found sheet in context: {cp.url}")
                        break
                except:
                    pass
            
            if spreadsheet_page:
                break
        
        if not spreadsheet_page:
            # Log all pages for debugging
            evidence_log.append("No spreadsheet found. All pages:")
            for cp in context.pages:
                try:
                    evidence_log.append(f"  {cp.url}")
                except:
                    pass
            context.close()
            evidence_str = "\n".join(evidence_log)
            return {"answer": "Failed to create spreadsheet", "summary": evidence_str}
        
        # We have the spreadsheet!
        spreadsheet_page.wait_for_timeout(5000)
        share_link = spreadsheet_page.url.split('?')[0].split('#')[0]
        evidence_log.append(f"Spreadsheet URL: {share_link}")
        
        # Dismiss overlays
        spreadsheet_page.keyboard.press("Escape")
        spreadsheet_page.wait_for_timeout(1000)
        spreadsheet_page.keyboard.press("Escape")
        spreadsheet_page.wait_for_timeout(1000)
        
        # PHASE 5: Fill data
        evidence_log.append("=== PHASE 5: Fill data ===")
        col_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            success = navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
            if not success:
                spreadsheet_page.wait_for_timeout(1000)
                navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
            type_in_cell(spreadsheet_page, header, evidence_log)
            evidence_log.append(f"Filled '{header}' in {cell_ref}")
        
        for row_idx, row_data in enumerate(data_rows):
            for i, value in enumerate(row_data):
                cell_ref = f"{col_letters[i]}{row_idx + 2}"
                success = navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
                if not success:
                    spreadsheet_page.wait_for_timeout(1000)
                    navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
                type_in_cell(spreadsheet_page, str(value), evidence_log)
                evidence_log.append(f"Filled '{value}' in {cell_ref}")
        
        spreadsheet_page.wait_for_timeout(1000)
        
        # PHASE 6: Verify
        evidence_log.append("=== PHASE 6: Verify ===")
        all_correct = True
        
        for i, header in enumerate(headers):
            cell_ref = f"{col_letters[i]}1"
            navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
            spreadsheet_page.wait_for_timeout(500)
            content = get_formula_content(spreadsheet_page)
            match = content == header
            evidence_log.append(f"Verify {cell_ref}: expected='{header}', got='{content}', match={match}")
            if not match: all_correct = False
        
        for row_idx, row_data in enumerate(data_rows):
            for i, value in enumerate(row_data):
                cell_ref = f"{col_letters[i]}{row_idx + 2}"
                navigate_to_cell(spreadsheet_page, cell_ref, evidence_log)
                spreadsheet_page.wait_for_timeout(500)
                content = get_formula_content(spreadsheet_page)
                match = content == str(value)
                evidence_log.append(f"Verify {cell_ref}: expected='{value}', got='{content}', match={match}")
                if not match: all_correct = False
        
        evidence_log.append(f"All correct: {all_correct}")
        
        spreadsheet_page.screenshot(path="final_spreadsheet.png")
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
