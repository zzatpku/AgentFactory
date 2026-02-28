import os, json, re, time
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

def main(query):
    """Debug subagent to explore how cells work in Tencent Docs spreadsheet."""
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
        
        # Open the existing spreadsheet to see where data ended up
        page.goto("https://docs.qq.com/sheet/DWVFERXpTZFRoYW5u", wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        
        evidence_log.append(f"URL: {page.url}")
        evidence_log.append(f"Title: {page.title()}")
        
        # Screenshot to see current state
        page.screenshot(path="debug_cells_1.png")
        evidence_log.append("Screenshot 1 saved: debug_cells_1.png")
        
        # Get page body text to see what's visible
        try:
            body_text = page.evaluate("() => document.body.innerText")
            evidence_log.append(f"Body text (first 5000 chars):\n{body_text[:5000]}")
        except Exception as e:
            evidence_log.append(f"Error getting body text: {e}")
        
        # Explore the DOM structure to understand cell layout
        # Check if it's canvas-based or DOM-based
        dom_analysis = page.evaluate("""() => {
            const results = [];
            
            // Check for canvas elements
            const canvases = document.querySelectorAll('canvas');
            results.push(`Canvas elements: ${canvases.length}`);
            for (const c of canvases) {
                const rect = c.getBoundingClientRect();
                results.push(`  Canvas: ${rect.width}x${rect.height} at (${rect.x},${rect.y})`);
            }
            
            // Check for table/grid elements
            const tables = document.querySelectorAll('table');
            results.push(`Table elements: ${tables.length}`);
            
            // Check for cell-related elements
            const cellEls = document.querySelectorAll('[class*="cell"], [class*="Cell"], [data-row], [data-col]');
            results.push(`Cell-related elements: ${cellEls.length}`);
            for (let i = 0; i < Math.min(cellEls.length, 20); i++) {
                const el = cellEls[i];
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || '').trim().slice(0, 50);
                const cls = (el.className || '').toString().slice(0, 100);
                const row = el.getAttribute('data-row') || '';
                const col = el.getAttribute('data-col') || '';
                results.push(`  [${i}] <${el.tagName}> class="${cls}" text="${text}" row=${row} col=${col} rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            
            // Check for contenteditable
            const editables = document.querySelectorAll('[contenteditable]');
            results.push(`Contenteditable elements: ${editables.length}`);
            for (let i = 0; i < Math.min(editables.length, 10); i++) {
                const el = editables[i];
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || '').trim().slice(0, 50);
                const cls = (el.className || '').toString().slice(0, 100);
                results.push(`  [${i}] <${el.tagName}> class="${cls}" text="${text}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            
            // Check for textarea/input elements
            const inputs = document.querySelectorAll('textarea, input[type="text"]');
            results.push(`Input/textarea elements: ${inputs.length}`);
            for (let i = 0; i < Math.min(inputs.length, 10); i++) {
                const el = inputs[i];
                const rect = el.getBoundingClientRect();
                const cls = (el.className || '').toString().slice(0, 100);
                results.push(`  [${i}] <${el.tagName}> class="${cls}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            
            // Check for row/column headers
            const headers = document.querySelectorAll('[class*="header"], [class*="Header"], [class*="row-index"], [class*="col-index"]');
            results.push(`Header elements: ${headers.length}`);
            for (let i = 0; i < Math.min(headers.length, 20); i++) {
                const el = headers[i];
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || '').trim().slice(0, 30);
                const cls = (el.className || '').toString().slice(0, 100);
                results.push(`  [${i}] <${el.tagName}> class="${cls}" text="${text}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            
            // Get the main spreadsheet container dimensions
            const container = document.querySelector('[class*="spreadsheet"], [class*="Spreadsheet"], [class*="sheet-container"], [class*="editor"]');
            if (container) {
                const rect = container.getBoundingClientRect();
                results.push(`Spreadsheet container: ${rect.width}x${rect.height} at (${rect.x},${rect.y})`);
            }
            
            return results.join('\\n');
        }""")
        evidence_log.append(f"DOM analysis:\n{dom_analysis}")
        
        # Now try clicking on what should be cell A1 and see what happens
        # First, let's find the row/column header positions to understand the grid layout
        grid_info = page.evaluate("""() => {
            const results = [];
            // Find elements with text 'A', 'B', 'C' that could be column headers
            const allEls = document.querySelectorAll('*');
            for (const el of allEls) {
                if (el.children.length > 0) continue;  // Only leaf nodes
                const text = (el.innerText || el.textContent || '').trim();
                if (['A', 'B', 'C', '1', '2', '3'].includes(text)) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.width < 200 && rect.height < 100) {
                        const cls = (el.className || '').toString().slice(0, 60);
                        results.push(`Text="${text}" tag=<${el.tagName}> class="${cls}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
                    }
                }
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Grid header elements:\n{grid_info}")
        
        # Try clicking at a few different positions and take screenshots
        # Click at approximately where A1 should be
        page.mouse.click(100, 270)
        page.wait_for_timeout(2000)
        page.screenshot(path="debug_cells_2_after_click.png")
        evidence_log.append("Screenshot 2 after clicking (100,270): debug_cells_2_after_click.png")
        
        # Check what got selected/focused
        focus_info = page.evaluate("""() => {
            const active = document.activeElement;
            if (!active) return 'No active element';
            const rect = active.getBoundingClientRect();
            const cls = (active.className || '').toString().slice(0, 100);
            const text = (active.innerText || active.value || '').trim().slice(0, 100);
            const tag = active.tagName;
            const ce = active.getAttribute('contenteditable');
            return `Active: <${tag}> class="${cls}" text="${text}" contenteditable=${ce} rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`;
        }""")
        evidence_log.append(f"Focus info after click: {focus_info}")
        
        # Check for any selection indicator
        selection_info = page.evaluate("""() => {
            const results = [];
            // Look for selection indicators
            const selEls = document.querySelectorAll('[class*="select"], [class*="Select"], [class*="active-cell"], [class*="ActiveCell"], [class*="focus"], [class*="highlight"]');
            for (let i = 0; i < Math.min(selEls.length, 15); i++) {
                const el = selEls[i];
                const rect = el.getBoundingClientRect();
                if (rect.width < 2 || rect.height < 2) continue;
                const cls = (el.className || '').toString().slice(0, 100);
                const text = (el.innerText || '').trim().slice(0, 50);
                results.push(`<${el.tagName}> class="${cls}" text="${text}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Selection elements:\n{selection_info}")
        
        # Look for name box / cell reference indicator (e.g., showing "A1")
        namebox_info = page.evaluate("""() => {
            const results = [];
            // Look for name box that shows current cell reference
            const inputs = document.querySelectorAll('input, [class*="name-box"], [class*="NameBox"], [class*="cell-ref"], [class*="coordinate"]');
            for (const el of inputs) {
                const rect = el.getBoundingClientRect();
                if (rect.width < 2) continue;
                const val = el.value || el.innerText || '';
                const cls = (el.className || '').toString().slice(0, 100);
                results.push(`<${el.tagName}> class="${cls}" value="${val}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Name box / cell reference:\n{namebox_info}")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Analyze the debug findings about Tencent Docs spreadsheet cell layout.",
        messages=[{"role": "user", "content": f"Debug findings:\n{evidence_str}\n\nAnalyze: 1) Is the spreadsheet canvas-based or DOM-based? 2) Where are the column headers (A, B, C) and row headers (1, 2, 3) positioned? 3) What is the correct way to click on cell A1? 4) What is the current state of the data in the spreadsheet? 5) How should we interact with cells to type data?"}],
        max_tokens=2000
    )
    
    return {"answer": evidence_str[:4000], "summary": summary}
