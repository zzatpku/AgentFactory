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
        
        popup_pages = []
        context.on("page", lambda new_page: popup_pages.append(new_page))
        
        page = context.new_page()
        page.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        evidence_log.append(f"Homepage URL: {page.url}")
        
        # Step 1: Find and click the "新建" button
        evidence_log.append("=== Step 1: Click 新建 button ===")
        
        # Find the button
        btn = page.query_selector('button:has-text("新建")')
        if btn:
            rect = btn.bounding_box()
            evidence_log.append(f"Found 新建 button at: {rect}")
            btn.click(force=True)
            page.wait_for_timeout(3000)
        else:
            evidence_log.append("新建 button not found via selector, trying alternatives")
            # Try by class
            btn2 = page.query_selector('.desktop-create-button-pc')
            if btn2:
                btn2.click(force=True)
                page.wait_for_timeout(3000)
                evidence_log.append("Clicked via class selector")
        
        # Step 2: Screenshot after clicking 新建
        page.screenshot(path="debug_after_xingjian.png")
        evidence_log.append("Screenshot saved: debug_after_xingjian.png")
        
        # Step 3: Analyze what appeared (dropdown/menu)
        body_text = page.evaluate("() => document.body.innerText")
        evidence_log.append(f"Body text after clicking 新建 (first 3000 chars):\n{body_text[:3000]}")
        
        # Get all interactive elements to see dropdown items
        JS_GET_ELEMENTS = """() => {
            document.querySelectorAll('[data-bid]').forEach(e => e.removeAttribute('data-bid'));
            const sels = 'button, input, textarea, select, a[href], [role="button"], [role="tab"], [role="textbox"], [role="menuitem"], [role="option"], [role="listitem"], [contenteditable="true"], .ant-btn, [class*="btn"], [class*="menu"], [class*="item"], [class*="create"], [class*="dropdown"], [class*="popup"], [class*="modal"], div[tabindex], span[tabindex], li[role], li[class]';
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
                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || '';
                const cls = (el.className || '').toString().slice(0, 120);
                const href = el.getAttribute('href') || '';
                const rect_info = `(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`;
                let desc = `[${id}] <${tag}> ${rect_info}`;
                if (role) desc += ` role="${role}"`;
                if (text) desc += ` text="${text}"`;
                if (href) desc += ` href="${href.slice(0, 80)}"`;
                if (cls) desc += ` class="${cls}"`;
                results.push(desc);
            }
            return results.join('\\n');
        }"""
        
        elements = page.evaluate(JS_GET_ELEMENTS)
        evidence_log.append(f"Elements after clicking 新建:\n{elements[:8000]}")
        
        # Step 4: Look specifically for dropdown/popup/menu elements
        dropdown_info = page.evaluate("""() => {
            const results = [];
            // Look for any recently appeared overlay/dropdown
            const overlays = document.querySelectorAll('[class*="dropdown"], [class*="popup"], [class*="menu"], [class*="modal"], [class*="overlay"], [class*="panel"], [class*="popover"], [class*="layer"]');
            for (const el of overlays) {
                const rect = el.getBoundingClientRect();
                if (rect.width < 10 || rect.height < 10) continue;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                const cls = (el.className || '').toString().slice(0, 150);
                const text = (el.innerText || '').trim().slice(0, 300);
                results.push(`<${el.tagName}> class="${cls}" size=${Math.round(rect.width)}x${Math.round(rect.height)} at (${Math.round(rect.x)},${Math.round(rect.y)}) text="${text}"`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Dropdown/popup elements:\n{dropdown_info}")
        
        # Step 5: Try to find and click "在线表格" or similar
        evidence_log.append("=== Step 5: Look for 在线表格 option ===")
        
        # Try to find text containing 表格
        sheet_option = page.query_selector('text=在线表格')
        if sheet_option:
            rect = sheet_option.bounding_box()
            evidence_log.append(f"Found 在线表格 at: {rect}")
            sheet_option.click(force=True)
            page.wait_for_timeout(5000)
            evidence_log.append(f"After clicking 在线表格, URL: {page.url}")
        else:
            evidence_log.append("在线表格 not found directly")
            # Try other selectors
            for text in ['表格', '在线表格', 'Sheet', 'Spreadsheet']:
                el = page.query_selector(f'text="{text}"')
                if el:
                    rect = el.bounding_box()
                    evidence_log.append(f"Found '{text}' at: {rect}")
                    break
        
        # Check for new tabs
        page.wait_for_timeout(3000)
        evidence_log.append(f"Number of popup pages: {len(popup_pages)}")
        all_pages = context.pages
        evidence_log.append(f"Total context pages: {len(all_pages)}")
        for i, pg in enumerate(all_pages):
            evidence_log.append(f"  Page {i}: {pg.url}")
        
        if popup_pages:
            new_page = popup_pages.pop(0)
            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=15000)
                new_page.wait_for_timeout(5000)
                evidence_log.append(f"New tab URL: {new_page.url}")
                evidence_log.append(f"New tab title: {new_page.title()}")
                
                # Analyze the spreadsheet page
                new_page.screenshot(path="debug_new_sheet.png")
                evidence_log.append("New sheet screenshot saved")
                
                # Check for bar-label
                bar_info = new_page.evaluate("""() => {
                    const results = [];
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        const rect = inp.getBoundingClientRect();
                        if (rect.width < 2) continue;
                        const cls = (inp.className || '').toString();
                        const val = inp.value || '';
                        const ph = inp.placeholder || '';
                        results.push(`<input> class="${cls}" value="${val}" placeholder="${ph}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
                    }
                    return results.join('\\n');
                }""")
                evidence_log.append(f"Inputs on new sheet page:\n{bar_info}")
                
                # Check canvas
                canvas_info = new_page.evaluate("""() => {
                    const canvases = document.querySelectorAll('canvas');
                    const results = [];
                    for (const c of canvases) {
                        const rect = c.getBoundingClientRect();
                        results.push(`Canvas: ${rect.width}x${rect.height} at (${rect.x},${rect.y})`);
                    }
                    return results.join('\\n');
                }""")
                evidence_log.append(f"Canvas elements on new sheet:\n{canvas_info}")
                
                # Try clicking at different y positions to find A1
                evidence_log.append("=== Testing cell clicks at different Y positions ===")
                for y in [190, 200, 210, 215, 220, 225, 230, 240, 250, 260]:
                    new_page.mouse.click(100, y)
                    new_page.wait_for_timeout(500)
                    bar_val = new_page.evaluate("""() => {
                        const inputs = document.querySelectorAll('input');
                        for (const inp of inputs) {
                            if (inp.className.includes('bar-label') || inp.className.includes('name') || inp.className.includes('coordinate') || inp.className.includes('cell-input')) {
                                return {cls: inp.className, val: inp.value};
                            }
                        }
                        // Try all visible small inputs
                        for (const inp of inputs) {
                            const rect = inp.getBoundingClientRect();
                            if (rect.width > 20 && rect.width < 120 && rect.height > 15 && rect.height < 40 && rect.x < 200) {
                                return {cls: inp.className, val: inp.value, rect: `${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)}`};
                            }
                        }
                        return {cls: 'none found', val: ''};
                    }""")
                    evidence_log.append(f"  Click at (100, {y}): bar={json.dumps(bar_val, ensure_ascii=False)}")
                
            except Exception as e:
                evidence_log.append(f"Error with new tab: {e}")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Analyze debug findings about the Tencent Docs create-spreadsheet flow.",
        messages=[{"role": "user", "content": f"Debug findings:\n{evidence_str}\n\nAnalyze: 1) Did the 新建 dropdown appear? What options were shown? 2) Was 在线表格 found and clicked? 3) Did a new tab open? 4) What is the correct cell reference input selector? 5) What Y coordinates map to which row numbers?"}],
        max_tokens=2000
    )
    
    return {"answer": evidence_str[:4000], "summary": summary}
