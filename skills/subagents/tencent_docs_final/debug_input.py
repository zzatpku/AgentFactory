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
        
        # Open the last created spreadsheet to test input
        page.goto("https://docs.qq.com/sheet/DWW5VY29FdGRvZXdP", wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        evidence_log.append(f"URL: {page.url}")
        evidence_log.append(f"Title: {page.title()}")
        
        # Dismiss any overlays
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        
        # Check current state - what's in the cells?
        evidence_log.append("\n=== Current state of cells ===")
        
        # First check all inputs on page
        inputs_info = page.evaluate("""() => {
            const results = [];
            const inputs = document.querySelectorAll('input');
            for (const inp of inputs) {
                const rect = inp.getBoundingClientRect();
                if (rect.width < 2) continue;
                results.push(`<input> class="${inp.className}" value="${inp.value}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"All inputs:\n{inputs_info}")
        
        # Check contenteditable elements
        ce_info = page.evaluate("""() => {
            const results = [];
            const els = document.querySelectorAll('[contenteditable]');
            for (const el of els) {
                const rect = el.getBoundingClientRect();
                if (rect.width < 2) continue;
                results.push(`<${el.tagName}> class="${(el.className||'').toString().slice(0,80)}" text="${(el.innerText||'').slice(0,50)}" ce=${el.contentEditable} rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Contenteditable elements:\n{ce_info}")
        
        # Navigate to A1 using name box
        evidence_log.append("\n=== Test 1: Navigate to A1 and check state ===")
        bar = page.query_selector('input.bar-label')
        if bar:
            bar.click()
            page.wait_for_timeout(300)
            page.mouse.click(bar.bounding_box()['x'] + 20, bar.bounding_box()['y'] + 10, click_count=3)
            page.wait_for_timeout(200)
            page.keyboard.type("A1", delay=30)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            
            bar_val = bar.evaluate("el => el.value")
            evidence_log.append(f"Bar label after nav: {bar_val}")
        else:
            evidence_log.append("No bar-label input found!")
        
        # Check active element and formula bar
        active_info = page.evaluate("""() => {
            const active = document.activeElement;
            return {
                tag: active.tagName,
                cls: (active.className || '').toString().slice(0, 100),
                text: (active.innerText || active.value || '').slice(0, 100),
                ce: active.contentEditable,
                rect: active.getBoundingClientRect()
            };
        }""")
        evidence_log.append(f"Active element after nav to A1: {json.dumps(active_info, ensure_ascii=False, default=str)}")
        
        # Check formula bar
        fb_info = page.evaluate("""() => {
            const fb = document.querySelector('div.formula-input');
            if (fb) {
                return {
                    text: fb.innerText,
                    textContent: fb.textContent,
                    innerHTML: fb.innerHTML.slice(0, 200),
                    ce: fb.contentEditable,
                    rect: fb.getBoundingClientRect()
                };
            }
            return null;
        }""")
        evidence_log.append(f"Formula bar state: {json.dumps(fb_info, ensure_ascii=False, default=str)}")
        
        # Test 2: Try typing directly (without F2)
        evidence_log.append("\n=== Test 2: Type directly without F2 ===")
        page.keyboard.type("TEST1", delay=50)
        page.wait_for_timeout(1000)
        
        # Check what happened
        active_after = page.evaluate("""() => {
            const active = document.activeElement;
            return {
                tag: active.tagName,
                cls: (active.className || '').toString().slice(0, 100),
                text: (active.innerText || active.value || '').slice(0, 100),
                ce: active.contentEditable
            };
        }""")
        evidence_log.append(f"Active after typing: {json.dumps(active_after, ensure_ascii=False)}")
        
        fb_after = page.evaluate("""() => {
            const fb = document.querySelector('div.formula-input');
            if (fb) return {text: fb.innerText, textContent: fb.textContent};
            return null;
        }""")
        evidence_log.append(f"Formula bar after typing: {json.dumps(fb_after, ensure_ascii=False)}")
        
        # Check cell editor
        editor_info = page.evaluate("""() => {
            const editors = document.querySelectorAll('[class*="cell-editor"], [class*="cellEditor"], [class*="editor-container"]');
            const results = [];
            for (const el of editors) {
                const rect = el.getBoundingClientRect();
                results.push(`<${el.tagName}> class="${(el.className||'').toString().slice(0,100)}" text="${(el.innerText||'').slice(0,100)}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Cell editor elements: {editor_info}")
        
        # Press Enter to confirm
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)
        
        # Navigate back to A1 to check if data persisted
        evidence_log.append("\n=== Test 3: Check if TEST1 persisted in A1 ===")
        bar = page.query_selector('input.bar-label')
        if bar:
            bar.click()
            page.wait_for_timeout(300)
            page.mouse.click(bar.bounding_box()['x'] + 20, bar.bounding_box()['y'] + 10, click_count=3)
            page.wait_for_timeout(200)
            page.keyboard.type("A1", delay=30)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            
            bar_val = bar.evaluate("el => el.value")
            evidence_log.append(f"Bar label: {bar_val}")
        
        fb_check = page.evaluate("""() => {
            const fb = document.querySelector('div.formula-input');
            if (fb) return {text: fb.innerText, textContent: fb.textContent, innerHTML: fb.innerHTML.slice(0,200)};
            return null;
        }""")
        evidence_log.append(f"Formula bar for A1: {json.dumps(fb_check, ensure_ascii=False)}")
        
        # Test 4: Try with F2 first
        evidence_log.append("\n=== Test 4: Navigate to B1, press F2, then type ===")
        bar = page.query_selector('input.bar-label')
        if bar:
            bar.click()
            page.wait_for_timeout(300)
            page.mouse.click(bar.bounding_box()['x'] + 20, bar.bounding_box()['y'] + 10, click_count=3)
            page.wait_for_timeout(200)
            page.keyboard.type("B1", delay=30)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
            evidence_log.append(f"Bar label: {bar.evaluate('el => el.value')}")
        
        page.keyboard.press("F2")
        page.wait_for_timeout(500)
        
        active_f2 = page.evaluate("""() => {
            const active = document.activeElement;
            return {
                tag: active.tagName,
                cls: (active.className || '').toString().slice(0, 100),
                text: (active.innerText || active.value || '').slice(0, 100),
                ce: active.contentEditable
            };
        }""")
        evidence_log.append(f"Active after F2: {json.dumps(active_f2, ensure_ascii=False)}")
        
        page.keyboard.type("TEST2", delay=50)
        page.wait_for_timeout(500)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1000)
        
        # Check B1
        bar = page.query_selector('input.bar-label')
        if bar:
            bar.click()
            page.wait_for_timeout(300)
            page.mouse.click(bar.bounding_box()['x'] + 20, bar.bounding_box()['y'] + 10, click_count=3)
            page.wait_for_timeout(200)
            page.keyboard.type("B1", delay=30)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
        
        fb_b1 = page.evaluate("""() => {
            const fb = document.querySelector('div.formula-input');
            if (fb) return {text: fb.innerText, textContent: fb.textContent};
            return null;
        }""")
        evidence_log.append(f"Formula bar for B1: {json.dumps(fb_b1, ensure_ascii=False)}")
        
        # Take screenshot
        page.screenshot(path="debug_input_result.png")
        evidence_log.append("Screenshot saved")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Analyze the debug findings about cell input in Tencent Docs.",
        messages=[{"role": "user", "content": f"Debug findings:\n{evidence_str}\n\nAnalyze: 1) Did typing directly work? 2) Did F2 + typing work? 3) Can we read cell content from formula bar? 4) What's the correct way to input data?"}],
        max_tokens=2000
    )
    
    return {"answer": evidence_str[:4000], "summary": summary}
