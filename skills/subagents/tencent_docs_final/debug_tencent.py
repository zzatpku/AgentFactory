import os, json, re, time
from playwright.sync_api import sync_playwright
from llm import call_llm
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

def main(query):
    """Debug subagent to explore Tencent Docs and understand the actual page structure."""
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
        
        # Step 1: Navigate to docs.qq.com and see what we get
        evidence_log.append("=== Step 1: Navigate to docs.qq.com ===")
        page.goto("https://docs.qq.com", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        
        url_after_nav = page.url
        evidence_log.append(f"URL after navigation: {url_after_nav}")
        
        # Take screenshot
        page.screenshot(path="debug_step1.png")
        evidence_log.append("Screenshot saved: debug_step1.png")
        
        # Get page title
        title = page.title()
        evidence_log.append(f"Page title: {title}")
        
        # Get visible text
        try:
            body_text = page.evaluate("() => document.body.innerText")
            evidence_log.append(f"Page body text (first 3000 chars):\n{body_text[:3000]}")
        except Exception as e:
            evidence_log.append(f"Error getting body text: {e}")
        
        # Get all interactive elements
        JS_GET_ELEMENTS = """() => {
            document.querySelectorAll('[data-bid]').forEach(e => e.removeAttribute('data-bid'));
            const sels = 'button, input, textarea, select, a[href], [role="button"], [role="tab"], [role="textbox"], [role="combobox"], [role="option"], [contenteditable="true"], .ant-btn, [class*="btn"], [class*="create"], [class*="new"], div[tabindex], span[tabindex], li[role], [class*="menu-item"], [class*="card"]';
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
        
        elements = page.evaluate(JS_GET_ELEMENTS)
        evidence_log.append(f"Interactive elements:\n{elements[:5000]}")
        
        # Step 2: Check if we are logged in or need to login
        evidence_log.append("\n=== Step 2: Check login status ===")
        # Look for login indicators
        login_check = page.evaluate("""() => {
            const text = document.body.innerText;
            const hasLogin = text.includes('登录') || text.includes('Login') || text.includes('注册');
            const hasUser = text.includes('我的') || text.includes('最近') || text.includes('新建') || text.includes('创建');
            return {hasLoginPrompt: hasLogin, hasUserContent: hasUser, url: window.location.href};
        }""")
        evidence_log.append(f"Login check result: {json.dumps(login_check, ensure_ascii=False)}")
        
        # Step 3: Check if the previously reported URL works
        evidence_log.append("\n=== Step 3: Check reported URL ===")
        page.goto("https://docs.qq.com/sheet/DWklMQXVlUWl0aEVa", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        url_check = page.url
        title_check = page.title()
        try:
            body_check = page.evaluate("() => document.body.innerText")
            evidence_log.append(f"URL after checking sheet: {url_check}")
            evidence_log.append(f"Title: {title_check}")
            evidence_log.append(f"Body text (first 2000 chars):\n{body_check[:2000]}")
        except Exception as e:
            evidence_log.append(f"Error: {e}")
        
        page.screenshot(path="debug_step3.png")
        evidence_log.append("Screenshot saved: debug_step3.png")
        
        context.close()
    
    evidence_str = "\n".join(evidence_log)
    
    summary = call_llm(
        system="Summarize what was found during the debug exploration of Tencent Docs.",
        messages=[{"role": "user", "content": f"Debug findings:\n{evidence_str}\n\nSummarize: 1) Is the user logged in? 2) What does the homepage look like? 3) Does the previously reported URL work? 4) What are the available interactive elements for creating a new document?"}],
        max_tokens=2000
    )
    
    return {"answer": evidence_str[:3000], "summary": summary}
