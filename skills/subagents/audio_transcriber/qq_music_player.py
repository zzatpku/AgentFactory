import json
import re
import os
from playwright.sync_api import sync_playwright
from llm import call_llm
from tools import search_serper, execute_shell_command
import tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

JS_GET_ELEMENTS = """() => {
    document.querySelectorAll('[data-bid]').forEach(e => e.removeAttribute('data-bid'));
    const sels = 'button, input, textarea, select, a[href], [role="button"], [role="tab"], [role="textbox"], [role="combobox"], [role="option"], [contenteditable="true"], .ant-btn, .btn, .play-btn, .song-item, .songlist__item, [class*="play"], [class*="search"], svg';
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
        const text = (el.innerText || '').trim().slice(0, 60);
        const ph = el.getAttribute('placeholder') || '';
        const tag = el.tagName.toLowerCase();
        const cls = (el.className || '').toString().slice(0, 80);
        const href = el.getAttribute('href') || '';
        let desc = `[${id}] <${tag}> text="${text}"`;
        if (ph) desc += ` placeholder="${ph}"`;
        if (cls) desc += ` class="${cls}"`;
        if (href) desc += ` href="${href}"`;
        results.push(desc);
    }
    return results.join('\\n');
}""" 

def execute_browser_action(active_page, action):
    try:
        act = action.get('action', '')
        if act == 'click':
            bid = str(action['id'])
            selector = f'[data-bid="{bid}"]'
            el = active_page.query_selector(selector)
            if el:
                el.scroll_into_view_if_needed()
                active_page.wait_for_timeout(300)
                el.click(force=True)
            else:
                active_page.evaluate("""(bid) => {
                    const el = document.querySelector(`[data-bid="${bid}"]`);
                    if (!el) return 'not_found';
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return 'ok';
                }""", bid)
            active_page.wait_for_timeout(2000)
        elif act == 'type':
            bid = str(action['id'])
            active_page.evaluate("""(bid) => {
                const el = document.querySelector(`[data-bid="${bid}"]`);
                if (!el) return 'not_found';
                el.scrollIntoView({block: 'center'});
                el.focus(); el.click(); return 'ok';
            }""", bid)
            active_page.wait_for_timeout(300)
            active_page.keyboard.type(action.get('text', ''), delay=50)
            active_page.wait_for_timeout(1000)
        elif act == 'clear_and_type':
            bid = str(action['id'])
            active_page.evaluate("""(bid) => {
                const el = document.querySelector(`[data-bid="${bid}"]`);
                if (!el) return 'not_found';
                el.scrollIntoView({block: 'center'});
                el.focus(); el.click(); return 'ok';
            }""", bid)
            active_page.wait_for_timeout(300)
            active_page.keyboard.press('Meta+a')
            active_page.keyboard.press('Backspace')
            active_page.keyboard.type(action.get('text', ''), delay=50)
            active_page.wait_for_timeout(1000)
        elif act == 'press_key':
            active_page.keyboard.press(action.get('key', 'Enter'))
            active_page.wait_for_timeout(1500)
        elif act == 'scroll':
            direction = action.get('direction', 'down')
            if direction == 'down':
                active_page.mouse.wheel(0, 400)
            else:
                active_page.mouse.wheel(0, -400)
            active_page.wait_for_timeout(1000)
        elif act == 'wait':
            active_page.wait_for_timeout(action.get('ms', 2000))
        elif act == 'goto':
            active_page.goto(action['url'], wait_until='domcontentloaded')
            active_page.wait_for_timeout(3000)
        elif act == 'get_text':
            text = active_page.evaluate('() => document.body.innerText')
            return text[:5000]
    except Exception as e:
        return f'Action error: {str(e)}'
    return 'ok'

def main(query):
    # Parse the query to understand what to do
    plan = call_llm(
        system="You parse user queries about playing music. Extract: 1) the music platform, 2) the artist name, 3) the song name. Return JSON like {\"platform\": \"...\", \"artist\": \"...\", \"song\": \"...\"}.",
        messages=[{"role": "user", "content": query}],
        max_tokens=500
    )
    try:
        json_match = re.search(r'\{[^{}]*\}', plan)
        params = json.loads(json_match.group())
    except:
        params = {"platform": "QQ音乐", "artist": "薛之谦", "song": "演员"}
    
    platform = params.get('platform', 'QQ音乐')
    artist = params.get('artist', '')
    song = params.get('song', '')
    
    # Search for the web version URL
    search_results = search_serper(f"{platform} 网页版 在线听歌", topk=5)
    urls_info = ""
    for r in search_results:
        if 'error' not in r:
            urls_info += f"- {r.get('title', '')}: {r.get('link', '')} - {r.get('snippet', '')}\n"
    
    # Let LLM decide the best URL
    url_decision = call_llm(
        system="You are helping find the web version of a music platform. Based on search results, pick the best URL for the official web player. Return ONLY the URL, nothing else.",
        messages=[{"role": "user", "content": f"I need the web version of {platform}. Search results:\n{urls_info}\n\nWhich URL is the official web player?"}],
        max_tokens=200
    )
    target_url = url_decision.strip()
    # Fallback to known URL if LLM doesn't return a valid one
    if not target_url.startswith('http'):
        target_url = 'https://y.qq.com'
    
    evidence = [f"Target URL: {target_url}", f"Artist: {artist}", f"Song: {song}"]
    
    # Launch browser - NOT using 'with' so browser stays open for user
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
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
    page.goto(target_url, wait_until='domcontentloaded')
    page.wait_for_timeout(3000)
    
    active_page = page
    
    system_prompt = f"""You are a browser automation agent. Your task is to play the song \"{song}\" by \"{artist}\" on {platform} web version.

Steps you should follow:
1. Find the search box on the page and search for \"{artist} {song}\"
2. After search results appear, find the song \"{song}\" by \"{artist}\" in the results
3. Click play on that song
4. Once the song is playing, report done

IMPORTANT: The browser is already logged in. Do NOT try to log in.
IMPORTANT: After typing the search query, press Enter to search.
IMPORTANT: Look for play buttons (often triangular icons or buttons with play-related text/class names).

Reply with ONLY one JSON action (no other text):
- {{"action":"click","id":N}} - click element with bid N
- {{"action":"type","id":N,"text":"..."}} - type text into element
- {{"action":"clear_and_type","id":N,"text":"..."}} - clear field then type
- {{"action":"press_key","key":"Enter"}} - press a key  
- {{"action":"scroll","direction":"down"}} - scroll the page
- {{"action":"wait","ms":2000}} - wait for page to load
- {{"action":"goto","url":"..."}} - navigate to a URL
- {{"action":"get_text"}} - get all visible text on page
- {{"action":"done","message":"..."}} - task complete"""
        
    messages = []
    final_answer = "Failed to complete the task"
    max_steps = 20
    
    for step in range(max_steps):
        # Check for popup windows
        if popup_pages:
            new_page = popup_pages.pop(0)
            try:
                new_page.wait_for_load_state('domcontentloaded', timeout=10000)
                new_page.wait_for_timeout(3000)
                active_page = new_page
            except:
                pass
        
        try:
            elements = active_page.evaluate(JS_GET_ELEMENTS)
        except:
            elements = "(Failed to get elements)"
        
        page_url = active_page.url
        user_msg = f"Step {step}. URL: {page_url}\nElements:\n{elements}"
        if len(user_msg) > 8000:
            user_msg = user_msg[:8000] + "\n... (truncated)"
        
        messages.append({"role": "user", "content": user_msg})
        evidence.append(f"Step {step}: URL={page_url}, elements_count={elements.count(chr(10))}")
        
        response = call_llm(system_prompt, messages[-16:], max_tokens=500)
        
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
        evidence.append(f"Action: {json.dumps(action, ensure_ascii=False)}")
        
        if action.get('action') == 'done':
            final_answer = action.get('message', 'Task completed')
            break
        
        result = execute_browser_action(active_page, action)
        if result and result != 'ok':
            evidence.append(f"Action result: {result}")
        
    # DO NOT close context/pw - keep browser open so user can listen to music
    # context.close()
    # pw.stop()
    
    # Generate summary
    summary = call_llm(
        system="You are a task summarizer. Summarize what was done in the browser automation task.",
        messages=[{"role": "user", "content": f"Query: {query}\nEvidence:\n" + "\n".join(evidence) + f"\nFinal result: {final_answer}\n\nWrite a summary of what happened."}],
        max_tokens=1000
    )
    
    return {"answer": final_answer, "summary": summary}
