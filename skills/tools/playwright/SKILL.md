---
name: playwright
description: Browser automation via Playwright. Enables opening web pages, clicking elements, typing text, reading DOM, handling modals, and more.
---

# Playwright Browser Automation Tool

Playwright is a Python library for automating Chromium, Firefox, and WebKit browsers. It allows your subagent to interact with web pages programmatically — navigate URLs, click buttons, fill forms, read page content, take screenshots, and handle popups/modals.

## Usage

```python
from playwright.sync_api import sync_playwright
```

## Core Concepts

### 1. Launch Browser and Open Page

```python
from playwright.sync_api import sync_playwright
import os, json, re, tools

PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")

with sync_playwright() as p:
    # Use persistent context to preserve login sessions across runs
    context = p.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=False,       # set True for headless, False to see the browser
        channel="chrome",
        locale="zh-CN",
        viewport={"width": 1280, "height": 800},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.new_page()
    page.goto("https://example.com", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    # ... do work ...
    context.close()
```

### 2. Find Interactive Elements (with iframe support)

Inject JavaScript to discover **all visible interactive elements** across the main page and all iframes. Each element is tagged with a unique `data-bid` and described with rich attributes.

```python
JS_TAG_ELEMENTS = """(startId) => {
    document.querySelectorAll('[data-bid]').forEach(e => e.removeAttribute('data-bid'));
    const sels = 'button, input, textarea, select, a[href], ' +
        '[role="button"], [role="tab"], [role="link"], [role="menuitem"], ' +
        '[role="option"], [role="switch"], [role="textbox"], [role="combobox"], ' +
        '[role="checkbox"], [role="radio"], [contenteditable="true"], ' +
        '[onclick], [tabindex]:not([tabindex="-1"])';
    const candidates = [...document.querySelectorAll(sels)];
    // Catch styled divs/spans acting as buttons (cursor:pointer)
    document.querySelectorAll('div, span, li, label, td, img, svg').forEach(el => {
        if (el.matches(sels)) return;
        try {
            if (window.getComputedStyle(el).cursor === 'pointer') candidates.push(el);
        } catch(e) {}
    });
    const seen = new Set();
    const results = [];
    let id = startId;
    for (const el of candidates) {
        if (seen.has(el)) continue;
        seen.add(el);
        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) continue;
        // Only include elements visible in the current viewport
        if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
        if (rect.right < 0 || rect.left > window.innerWidth) continue;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
        id++;
        el.setAttribute('data-bid', String(id));
        const text = (el.innerText || '').trim().slice(0, 80);
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        const ariaLabel = el.getAttribute('aria-label') || '';
        const title = el.getAttribute('title') || '';
        const ph = el.getAttribute('placeholder') || '';
        const type = el.getAttribute('type') || '';
        const cls = (el.className || '').toString().slice(0, 80);
        const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
        const checked = el.checked === true;
        const ariaSelected = el.getAttribute('aria-selected');
        const ariaExpanded = el.getAttribute('aria-expanded');
        const value = (tag === 'input' || tag === 'textarea') ? (el.value || '').slice(0, 40) : '';
        let desc = '[' + id + '] <' + tag + '>';
        if (role) desc += ' role="' + role + '"';
        if (text) desc += ' "' + text + '"';
        if (ariaLabel && ariaLabel !== text) desc += ' aria="' + ariaLabel + '"';
        if (title && title !== text) desc += ' title="' + title + '"';
        if (ph) desc += ' placeholder="' + ph + '"';
        if (type) desc += ' type="' + type + '"';
        if (cls) desc += ' class="' + cls + '"';
        if (disabled) desc += ' [disabled]';
        if (checked) desc += ' [checked]';
        if (ariaSelected === 'true') desc += ' [selected]';
        if (ariaExpanded !== null) desc += ' expanded=' + ariaExpanded;
        if (value) desc += ' value="' + value + '"';
        desc += ' @(' + Math.round(rect.x) + ',' + Math.round(rect.y) + ',' + Math.round(rect.width) + 'x' + Math.round(rect.height) + ')';
        results.push(desc);
    }
    return JSON.stringify({text: results.join('\\n'), nextId: id});
}"""

def get_all_elements(page):
    """Discover interactive elements across main page AND all iframes.
    Returns (elements_text, element_frames_dict).
    element_frames maps bid(int) -> frame, used by click_element / type_in_element.
    """
    element_frames = {}
    all_text = []
    next_id = 0
    for i, frame in enumerate(page.frames):
        try:
            raw = frame.evaluate(JS_TAG_ELEMENTS, next_id)
            result = json.loads(raw)
            if result['text']:
                label = "Main Page" if i == 0 else frame.url.split('?')[0][-50:]
                all_text.append(f"── {label} ──\n{result['text']}")
                for bid in range(next_id + 1, result['nextId'] + 1):
                    element_frames[bid] = frame
                next_id = result['nextId']
        except:
            pass
    return "\n".join(all_text), element_frames
```

**Example output:**
```
── Main Page ──
[1] <button> "Submit" class="primary-btn" @(50,12,80x36)
[2] <input> placeholder="Search..." type="text" class="search-box" value="" @(200,12,300x36)
[3] <a> "Home" class="nav-link" @(50,60,80x24)
[4] <div> "Click me" class="action-card" @(400,200,150x40)
[5] <button> "Save" class="save-btn" [disabled] @(500,12,60x36)
[6] <input> type="checkbox" class="toggle" [checked] @(600,14,16x16)
[7] <button> "Menu" class="dropdown-trigger" expanded=false @(700,12,80x36)
── /embedded-iframe-path ──
[8] <button> role="button" "Confirm" aria="Confirm action" class="btn-ok" @(100,80,120x36)
[9] <span> "Cancel" class="btn-cancel" @(240,80,80x36)
```

### 3. Interact with Elements (cross-frame)

Use these helper functions to interact with elements. They automatically find the correct frame for each `data-bid`.

```python
def click_element(page, element_frames, bid):
    """Click element by bid, automatically finding the right frame."""
    bid = int(bid)
    frame = element_frames.get(bid, page.main_frame)
    selector = f'[data-bid="{bid}"]'
    el = frame.query_selector(selector)
    if el:
        el.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        el.click(force=True)
    else:
        frame.evaluate("""(bid) => {
            const el = document.querySelector(`[data-bid="${bid}"]`);
            if (el) { el.scrollIntoView({block:'center'}); el.click(); }
        }""", str(bid))
    page.wait_for_timeout(1500)

def type_in_element(page, element_frames, bid, text, clear_first=False):
    """Focus element by bid and type text. Set clear_first=True to clear existing content."""
    bid = int(bid)
    frame = element_frames.get(bid, page.main_frame)
    frame.evaluate("""(bid) => {
        const el = document.querySelector(`[data-bid="${bid}"]`);
        if (el) { el.scrollIntoView({block:'center'}); el.focus(); el.click(); }
    }""", str(bid))
    page.wait_for_timeout(300)
    if clear_first:
        page.keyboard.press("Meta+a")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(200)
    page.keyboard.type(text, delay=50)
    page.wait_for_timeout(500)

def hover_element(page, element_frames, bid):
    """Hover over element by bid. Use this to reveal dropdown menus, tooltips, etc."""
    bid = int(bid)
    frame = element_frames.get(bid, page.main_frame)
    el = frame.query_selector(f'[data-bid="{bid}"]')
    if el:
        el.scroll_into_view_if_needed()
        el.hover()
    page.wait_for_timeout(1000)

def select_option(page, element_frames, bid, value):
    """Select an option from a native <select> element by visible text or value."""
    bid = int(bid)
    frame = element_frames.get(bid, page.main_frame)
    el = frame.query_selector(f'[data-bid="{bid}"]')
    if el:
        el.select_option(label=value)
    page.wait_for_timeout(500)

# Press keys
page.keyboard.press("Enter")
page.keyboard.press("Escape")

# Scroll
page.mouse.wheel(0, 400)   # scroll down
page.mouse.wheel(0, -400)  # scroll up
```

### 4. Handle Popup Windows

Many web apps open new windows/tabs when clicking buttons. Set up a popup handler to capture them, otherwise you'll be stuck operating on the old page while the real content is in the new window.

```python
# Set up popup handler BEFORE any clicks that might open new windows
popup_pages = []
context.on("page", lambda new_page: popup_pages.append(new_page))

# In your automation loop, check for popups after each action:
if popup_pages:
    new_page = popup_pages.pop(0)
    new_page.wait_for_load_state("domcontentloaded", timeout=10000)
    new_page.wait_for_timeout(3000)
    active_page = new_page  # Switch to the new window
```

### 5. LLM-Driven Automation Loop

The most powerful pattern: use `call_llm` to decide what to do at each step based on the current page state.

```python
from llm import call_llm

system_prompt = """You are a browser automation agent. Your task is: [describe task].
Each step you see the page URL and all interactive elements with their IDs, attributes, and positions.
Elements may show state: [disabled] (cannot click), [checked], [selected], expanded=true/false, value="..." (current input content).
Reply with ONLY one JSON action (no other text):
- {"action":"click","id":N} - click element with bid N
- {"action":"type","id":N,"text":"..."} - type text into element
- {"action":"clear_and_type","id":N,"text":"..."} - clear field then type
- {"action":"hover","id":N} - hover over element (to reveal dropdown menus, tooltips)
- {"action":"select","id":N,"value":"..."} - select option from a <select> dropdown
- {"action":"press_key","key":"Enter"} - press a key
- {"action":"scroll","direction":"down"} - scroll the page
- {"action":"wait","ms":2000} - wait for page to load
- {"action":"goto","url":"..."} - navigate to a URL
- {"action":"get_text"} - get all visible text on page
- {"action":"done","message":"..."} - task complete, include result in message"""

messages = []
active_page = page
element_frames = {}

for step in range(max_steps):
    # Check for popup windows
    if popup_pages:
        new_page = popup_pages.pop(0)
        new_page.wait_for_load_state("domcontentloaded", timeout=10000)
        new_page.wait_for_timeout(3000)
        active_page = new_page

    elements_text, element_frames = get_all_elements(active_page)
    user_msg = f"Step {step}. URL: {active_page.url}\nElements:\n{elements_text}"
    if len(user_msg) > 50000:
        user_msg = user_msg[:50000] + "\n... (truncated)"
    messages.append({"role": "user", "content": user_msg})

    response = call_llm(system_prompt, messages[-20:], max_tokens=500)

    # Parse JSON from response (LLM may include extra text)
    json_match = re.search(r'\{[^{}]*\}', response)
    if not json_match:
        messages.append({"role": "assistant", "content": response})
        continue
    action = json.loads(json_match.group())
    messages.append({"role": "assistant", "content": response})

    if action["action"] == "done":
        final_answer = action["message"]
        break

    # Execute action and capture errors for feedback
    act = action["action"]
    action_error = None
    try:
        if act == "click":
            click_element(active_page, element_frames, action["id"])
        elif act == "type":
            type_in_element(active_page, element_frames, action["id"], action["text"])
        elif act == "clear_and_type":
            type_in_element(active_page, element_frames, action["id"], action["text"], clear_first=True)
        elif act == "hover":
            hover_element(active_page, element_frames, action["id"])
        elif act == "select":
            select_option(active_page, element_frames, action["id"], action["value"])
        elif act == "press_key":
            active_page.keyboard.press(action.get("key", "Enter"))
            active_page.wait_for_timeout(1500)
        elif act == "scroll":
            dy = 400 if action.get("direction", "down") == "down" else -400
            active_page.mouse.wheel(0, dy)
            active_page.wait_for_timeout(1000)
        elif act == "wait":
            active_page.wait_for_timeout(action.get("ms", 2000))
        elif act == "goto":
            active_page.goto(action["url"], wait_until="domcontentloaded")
            active_page.wait_for_timeout(3000)
        elif act == "get_text":
            text = active_page.evaluate("() => document.body.innerText")
            messages.append({"role": "user", "content": f"Page text:\n{text[:5000]}"})
    except Exception as e:
        action_error = str(e)

    # Feed error back to LLM so it can adjust
    if action_error:
        messages.append({"role": "user", "content": f"⚠ Action '{act}' failed: {action_error}"})
```

## Key Tips

- **Persistent context & User Data**: Always use `launch_persistent_context` with a **fixed, absolute path** as the user data directory. **Do NOT use `os.path.dirname(__file__)`** — subagent scripts run in a workspace subdirectory, so `__file__` points to the wrong location. Instead, derive the project root from an imported module, e.g.:
  ```python
  import tools
  PROJECT_ROOT = os.path.dirname(os.path.abspath(tools.__file__))
  USER_DATA_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")
  ```
  This directory stores cookies, login sessions, localStorage, and other browser state. It ensures that login only needs to happen once — subsequent runs automatically reuse the saved session.
- **Wait after actions**: Always add `page.wait_for_timeout(1000~2000)` after clicks/navigation to let the page update.
- **Modal/dialog handling**: After clicking a button that opens a modal, re-query elements — the modal's elements will appear in the new query.
- **Context window management**: In the LLM loop, keep only the last ~20 messages to avoid exceeding context limits.
- **Error recovery**: If an element is not found, try waiting or scrolling before giving up.
- **headless=False**: Use this during development so you can see what the browser is doing. Switch to `headless=True` for production.

## ⚠️ Critical Best Practices

- **DO NOT hardcode page interactions before the LLM loop.** Never write fixed click/type sequences (e.g., `page.locator('text=XXX').click()`) before entering the LLM-driven loop. These hardcoded actions are fragile — if the page layout differs from your assumption, they silently fail and corrupt the state for the LLM loop. Let the LLM loop handle ALL page interactions from the start.

- **DO NOT assume page state in the LLM system prompt.** Never tell the LLM things like "the button has already been clicked" or "a dialog should be visible" unless you have verified it. If a prior action failed silently, the LLM will operate under a false premise and waste all its steps. The system prompt should describe the GOAL, not assume intermediate states.

- **Verify the target URL before navigating.** Do NOT guess or fabricate URLs for web apps. Many SPAs use client-side routing — a wrong path may render an empty page while still showing the navigation shell, making it look like the page loaded. Use `search_serper` + `read_url_jina` to find the correct entry URL first, or navigate to a known-good root URL and let the LLM loop discover the right path from there.

- **Prefer Playwright native click over JS click.** Use `el.click(force=True)` via `frame.query_selector()` as the primary click method. It properly triggers all browser events (mousedown, mouseup, click, focus, blur). Fall back to JS `el.click()` only when native click fails. Pure JS click misses some event handlers and can cause buttons/modals to not respond.

- **Always handle popup windows.** Set up `context.on("page", ...)` before any interactions. Many web apps open forms, dialogs, or results in new windows. Without a popup handler, your automation will keep operating on the old page and never see the new content.

- **Always use `get_all_elements` (not raw `page.evaluate`).** It traverses all iframes automatically. Many web apps embed key UI (template chooser, form builder, etc.) inside iframes that `document.querySelectorAll` on the main page cannot reach.

## Limitations

- Non-interactive: the script must be fully autonomous — no manual input during execution.
