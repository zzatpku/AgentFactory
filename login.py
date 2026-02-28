from playwright.sync_api import sync_playwright
import os, tools

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(tools.__file__)), ".browser_profile")

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        USER_DATA_DIR,
        headless=False,
        channel="chrome",
        viewport={"width": 1280, "height": 800},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.new_page()
    page.goto("https://meeting.tencent.com/", wait_until="domcontentloaded")
    input("Press Enter to close the browser after logging in....")
    context.close()
