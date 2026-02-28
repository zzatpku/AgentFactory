import os, json, re, time
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
        evidence_log.append(f"Initial URL: {page.url}")
        evidence_log.append(f"Initial pages count: {len(context.pages)}")
        
        # Click 新建
        btn = page.query_selector('button:has-text("新建")')
        if btn:
            btn.click(force=True)
            page.wait_for_timeout(3000)
            evidence_log.append("Clicked 新建")
        
        # Find 表格 button
        items = page.query_selector_all('button.create-create-item')
        evidence_log.append(f"Found {len(items)} create items")
        table_btn = None
        for idx, item in enumerate(items):
            text = item.inner_text().strip()
            evidence_log.append(f"  Item {idx}: '{text}'")
            if text == '表格':
                table_btn = item
        
        if table_btn:
            box = table_btn.bounding_box()
            evidence_log.append(f"表格 button box: {box}")
            
            # Listen for navigation and new pages
            nav_events = []
            page.on("framenavigated", lambda frame: nav_events.append(f"Frame navigated: {frame.url}"))
            
            # Click the button
            evidence_log.append("About to click 表格...")
            table_btn.click(force=True)
            evidence_log.append("Clicked 表格")
            
            # Wait and observe what happens
            for wait_step in range(30):  # 15 seconds total
                page.wait_for_timeout(500)
                
                # Check for new popup pages
                if popup_pages:
                    for pp in popup_pages:
                        try:
                            evidence_log.append(f"  Wait {wait_step}: New popup URL = {pp.url}")
                        except:
                            evidence_log.append(f"  Wait {wait_step}: New popup (can't get URL)")
                
                # Check all context pages
                all_urls = []
                for cp in context.pages:
                    try:
                        all_urls.append(cp.url)
                    except:
                        all_urls.append("(error getting URL)")
                
                # Check if any page has /sheet/ in URL
                has_sheet = any('/sheet/' in u for u in all_urls)
                
                if wait_step % 5 == 0:  # Log every 2.5 seconds
                    evidence_log.append(f"  Wait {wait_step}: pages={all_urls}, has_sheet={has_sheet}")
                
                if has_sheet:
                    evidence_log.append(f"  FOUND sheet page at wait step {wait_step}!")
                    break
                
                # Check current page URL
                try:
                    current = page.url
                    if '/sheet/' in current:
                        evidence_log.append(f"  Current page navigated to sheet: {current}")
                        break
                except:
                    pass
            
            # Log navigation events
            evidence_log.append(f"Navigation events: {nav_events}")
            
            # Final state
            evidence_log.append(f"\nFinal state:")
            evidence_log.append(f"  Main page URL: {page.url}")
            evidence_log.append(f"  Number of popup pages: {len(popup_pages)}")
            evidence_log.append(f"  Total context pages: {len(context.pages)}")
            for i, cp in enumerate(context.pages):
                try:
                    evidence_log.append(f"  Page {i}: URL={cp.url}, title={cp.title()}")
                except:
                    evidence_log.append(f"  Page {i}: (error)")
            
            # Take screenshot of current page
            page.screenshot(path="debug_after_table_click.png")
            evidence_log.append("Screenshot of main page saved")
            
            # Get body text of main page
            try:
                body = page.evaluate("() => document.body.innerText")
                evidence_log.append(f"Main page body (first 2000):\n{body[:2000]}")
            except:
                pass
            
            # Check each popup page
            for pp_idx, pp in enumerate(popup_pages):
                try:
                    pp.wait_for_load_state("domcontentloaded", timeout=5000)
                    pp.wait_for_timeout(3000)
                    pp.screenshot(path=f"debug_popup_{pp_idx}.png")
                    evidence_log.append(f"Popup {pp_idx}: URL={pp.url}, title={pp.title()}")
                    pp_body = pp.evaluate("() => document.body.innerText")
                    evidence_log.append(f"Popup {pp_idx} body (first 2000):\n{pp_body[:2000]}")
                except Exception as e:
                    evidence_log.append(f"Popup {pp_idx} error: {e}")
            
            # Also check if maybe the main page changed
            page.wait_for_timeout(5000)
            evidence_log.append(f"\nAfter extra wait:")
            evidence_log.append(f"  Main page URL: {page.url}")
            for i, cp in enumerate(context.pages):
                try:
                    evidence_log.append(f"  Page {i}: URL={cp.url}")
                except:
                    pass
        else:
            evidence_log.append("ERROR: 表格 button not found")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Analyze what happens after clicking the table creation button in Tencent Docs.",
        messages=[{"role": "user", "content": f"Debug findings:\n{evidence_str}\n\nAnalyze: 1) What happened after clicking 表格? 2) Did a new tab/page open? 3) Where did the spreadsheet actually go? 4) What should we do differently?"}],
        max_tokens=2000
    )
    
    return {"answer": evidence_str[:4000], "summary": summary}
