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
        
        # Click 新建
        btn = page.query_selector('button:has-text("新建")')
        if btn:
            btn.click(force=True)
            page.wait_for_timeout(3000)
            evidence_log.append("Clicked 新建")
        
        # Click 表格
        items = page.query_selector_all('button.create-create-item')
        for item in items:
            text = item.inner_text().strip()
            if text == '表格':
                item.click(force=True)
                evidence_log.append("Clicked 表格")
                break
        
        page.wait_for_timeout(5000)
        page.screenshot(path="debug_iframe_1.png")
        evidence_log.append("Screenshot 1 saved")
        
        # Check for iframes
        iframes = page.frames
        evidence_log.append(f"Number of frames: {len(iframes)}")
        for i, frame in enumerate(iframes):
            evidence_log.append(f"  Frame {i}: name={frame.name}, url={frame.url}")
        
        # Check body text of main page
        body = page.evaluate("() => document.body.innerText")
        evidence_log.append(f"Main page body (first 3000):\n{body[:3000]}")
        
        # Look for iframe elements in DOM
        iframe_info = page.evaluate("""() => {
            const iframes = document.querySelectorAll('iframe');
            const results = [];
            for (const iframe of iframes) {
                const rect = iframe.getBoundingClientRect();
                results.push(`<iframe> src="${iframe.src || ''}" name="${iframe.name || ''}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)}) style.display=${window.getComputedStyle(iframe).display}`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Iframe elements:\n{iframe_info}")
        
        # Look for any modal/dialog/panel that appeared
        panel_info = page.evaluate("""() => {
            const results = [];
            const els = document.querySelectorAll('[class*="panel"], [class*="modal"], [class*="dialog"], [class*="drawer"], [class*="overlay"], [class*="popup"], [class*="template"], [class*="mall"]');
            for (const el of els) {
                const rect = el.getBoundingClientRect();
                if (rect.width < 10 || rect.height < 10) continue;
                const style = window.getComputedStyle(el);
                if (style.display === 'none') continue;
                const cls = (el.className || '').toString().slice(0, 150);
                const text = (el.innerText || '').trim().slice(0, 200);
                results.push(`<${el.tagName}> class="${cls}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)}) text="${text}"`);
            }
            return results.join('\\n');
        }""")
        evidence_log.append(f"Panel/modal elements:\n{panel_info}")
        
        # Try to interact with the iframe if found
        mall_frame = None
        for frame in page.frames:
            if 'mall' in frame.url or 'panel' in frame.url:
                mall_frame = frame
                break
        
        if mall_frame:
            evidence_log.append(f"\n=== Found mall/panel iframe: {mall_frame.url} ===")
            try:
                # Get content of the iframe
                frame_body = mall_frame.evaluate("() => document.body.innerText")
                evidence_log.append(f"Iframe body (first 3000):\n{frame_body[:3000]}")
                
                # Get interactive elements in iframe
                frame_elements = mall_frame.evaluate("""() => {
                    const sels = 'button, a, [role="button"], [class*="item"], [class*="card"], [class*="template"], [class*="blank"], div[tabindex]';
                    const els = document.querySelectorAll(sels);
                    const results = [];
                    let id = 0;
                    for (const el of els) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 5 || rect.height < 5) continue;
                        const style = window.getComputedStyle(el);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        id++;
                        const text = (el.innerText || '').trim().slice(0, 80);
                        const tag = el.tagName.toLowerCase();
                        const cls = (el.className || '').toString().slice(0, 120);
                        const href = el.getAttribute('href') || '';
                        results.push(`[${id}] <${tag}> class="${cls}" text="${text}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
                    }
                    return results.join('\\n');
                }""")
                evidence_log.append(f"Iframe interactive elements:\n{frame_elements[:5000]}")
                
                # Look specifically for "空白" or "blank" or first item
                blank_items = mall_frame.evaluate("""() => {
                    const results = [];
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        const text = (el.innerText || el.textContent || '').trim();
                        if (text.includes('空白') || text.includes('新建') || text.includes('blank')) {
                            if (el.children.length < 3) {  // Leaf-ish nodes
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 5 && rect.height > 5) {
                                    results.push(`<${el.tagName}> class="${(el.className||'').toString().slice(0,80)}" text="${text.slice(0,60)}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
                                }
                            }
                        }
                    }
                    return results.join('\\n');
                }""")
                evidence_log.append(f"Blank/new items in iframe:\n{blank_items}")
                
            except Exception as e:
                evidence_log.append(f"Error interacting with iframe: {e}")
        else:
            evidence_log.append("No mall/panel iframe found")
            
            # Maybe it's not an iframe but a panel on the page
            # Let's look at what appeared after clicking 表格
            evidence_log.append("\n=== Looking for template picker on main page ===")
            template_items = page.evaluate("""() => {
                const results = [];
                const els = document.querySelectorAll('*');
                for (const el of els) {
                    const text = (el.innerText || el.textContent || '').trim();
                    if ((text.includes('空白') || text === '表格' || text.includes('新建表格') || text.includes('blank')) && text.length < 20) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 5 && rect.height > 5 && rect.width < 500) {
                            const cls = (el.className || '').toString().slice(0, 80);
                            results.push(`<${el.tagName}> class="${cls}" text="${text}" rect=(${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)}x${Math.round(rect.height)})`);
                        }
                    }
                }
                return results.join('\\n');
            }""")
            evidence_log.append(f"Template items on main page:\n{template_items}")
        
        # Check all pages again
        evidence_log.append(f"\nAll pages ({len(context.pages)}):")
        for i, cp in enumerate(context.pages):
            try:
                evidence_log.append(f"  Page {i}: {cp.url}")
            except:
                evidence_log.append(f"  Page {i}: (error)")
        
        evidence_log.append(f"Popup pages: {len(popup_pages)}")
        for i, pp in enumerate(popup_pages):
            try:
                evidence_log.append(f"  Popup {i}: {pp.url}")
            except:
                evidence_log.append(f"  Popup {i}: (error)")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Analyze the debug findings about the template picker panel in Tencent Docs.",
        messages=[{"role": "user", "content": f"Debug findings:\n{evidence_str}\n\nAnalyze: 1) Is there a template picker iframe/panel? 2) What options are available? 3) How to click 'blank spreadsheet'? 4) What's the correct flow to create a new blank spreadsheet?"}],
        max_tokens=2000
    )
    
    return {"answer": evidence_str[:4000], "summary": summary}
