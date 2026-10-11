"""Browser end-to-end check (Playwright). Run against a live stack:
   python tests/e2e_browser.py   (API on :8000, built frontend on :4173)"""
import sys, time, uuid
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

WEB = "http://127.0.0.1:4173"
SHOTS = Path(__file__).resolve().parents[2] / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
errors, results = [], []


def check(name, fn):
    print("..", name, flush=True)
    try:
        fn(); results.append((name, True, ""))
    except Exception as e:  # noqa
        results.append((name, False, str(e).splitlines()[0][:160]))


with sync_playwright() as p:
    b = p.chromium.launch()
    import functools
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, timezone_id="Asia/Kolkata")
    page = ctx.new_page(); page.set_default_timeout(7000); ctx.set_default_timeout(7000)
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    # ---- landing
    page.goto(WEB); page.wait_for_selector("text=Plan Smarter."); page.wait_for_timeout(3600)
    page.screenshot(path=SHOTS / "01-landing.png")
    check("landing hero + CTAs", lambda: (expect(page.get_by_role("link", name="Create My Study Plan").first).to_be_visible(), expect(page.get_by_role("button", name="Try the demo")).to_be_visible()))

    # ---- register
    email = f"e2e{uuid.uuid4().hex[:6]}@example.com"
    page.goto(WEB + "/register"); page.get_by_label("Your name").fill("Sam"); page.get_by_label("Email").fill(email); page.get_by_label("Password").fill("password123")
    page.get_by_role("button", name="Create account").click()
    check("register -> onboarding", lambda: page.wait_for_url("**/onboarding", timeout=8000))

    # ---- onboarding wizard (8 steps)
    page.get_by_role("button", name="Next").click()                                  # step 1 -> 2 (name prefilled)
    page.get_by_text("Fill with an example").click()                                 # jumps to topics step with example data
    page.screenshot(path=SHOTS / "02-onboarding.png")
    for _ in range(6):
        page.get_by_role("button", name="Next").click(); page.wait_for_timeout(150)
    page.get_by_role("button", name="Generate My Study Plan").click()
    check("onboarding -> dashboard with plan", lambda: (page.wait_for_url("**/dashboard", timeout=15000), expect(page.get_by_text("Good ").first).to_be_visible()))
    page.wait_for_timeout(800)
    page.screenshot(path=SHOTS / "03-dashboard.png")

    # ---- navigation + screenshots
    for name, path, shot in [("Subjects", "subjects", "04-subjects"), ("Planner", "planner", "05-planner"), ("Calendar", "calendar", "06-calendar"), ("Tasks", "tasks", "07-tasks"),
                             ("Focus", "focus", "08-focus"), ("Analytics", "analytics", "09-analytics"), ("Recs", "recommendations", "10-recommendations"), ("Settings", "settings", "11-settings")]:
        page.goto(f"{WEB}/{path}"); page.wait_for_timeout(900); page.screenshot(path=SHOTS / f"{shot}.png", full_page=(path in ("settings", "analytics")))
        check(f"page /{path} renders", lambda: expect(page.locator("main h1").first).to_be_visible())

    # ---- complete + skip tasks from Tasks page (upcoming)
    page.goto(WEB + "/tasks"); page.get_by_role("tab", name="Upcoming").click(); page.wait_for_timeout(500)
    def complete_task():
        page.get_by_role("button", name="Mark complete").first.click()
        page.get_by_role("dialog").get_by_role("button").nth(3).click()   # 😃
        expect(page.get_by_text("Review scheduled").first).to_be_visible(timeout=6000)
    check("complete task with confidence -> spaced review scheduled", complete_task)
    def skip_task():
        page.get_by_role("button", name="Skip", exact=True).first.click()
        expect(page.get_by_text("Plan recalculated").first).to_be_visible(timeout=6000)
    check("skip task -> auto reschedule toast", skip_task)

    # ---- focus mode
    page.goto(WEB + "/planner"); page.wait_for_timeout(600)
    def focus_flow():
        page.goto(WEB + "/focus"); page.wait_for_timeout(500)
        page.get_by_role("tab", name="Custom").click(); page.locator("input[type=number]").first.fill("5")
        page.get_by_role("button", name="Start").click(); page.wait_for_timeout(1800)
        expect(page.get_by_role("button", name="Pause")).to_be_visible()
        page.screenshot(path=SHOTS / "08b-focus-running.png")
        page.get_by_role("button", name="Pause").click(); expect(page.get_by_role("button", name="Resume")).to_be_visible()
        page.get_by_role("button", name="Resume").click(); page.get_by_role("button", name="Stop").click()
        expect(page.get_by_text("Session ended")).to_be_visible()      # < 1 min studied -> nothing logged
        page.get_by_role("button", name="Close").click()
    check("focus: start/pause/resume/stop", focus_flow)

    # ---- assistant (natural language)
    def assistant_flow():
        page.goto(WEB + "/recommendations"); page.wait_for_timeout(600)
        box = page.get_by_label("Ask the planning assistant").first
        box.fill("Study Trees tomorrow for 1 hour"); box.press("Enter")
        page.get_by_role("button", name="Apply changes").click()
        expect(page.get_by_text("Added 60 min of Trees").first).to_be_visible(timeout=8000)
        page.screenshot(path=SHOTS / "10b-assistant.png")
    check("assistant: NL -> validated action -> applied", assistant_flow)

    # ---- calendar drag & drop (week view)
    def drag_flow():
        page.goto(WEB + "/calendar"); page.wait_for_timeout(900)
        page.get_by_role("button", name="Next").click(); page.wait_for_timeout(900)      # next week: every slot is in the future
        blocks = page.locator("button[draggable=true]")
        src = blocks.first; src.scroll_into_view_if_needed()
        sb = src.bounding_box()
        cols = page.locator("div.relative.border-l")
        target = cols.nth(3).bounding_box()
        page.mouse.move(sb["x"] + 10, sb["y"] + 8); 
        src.drag_to(cols.nth(3), target_position={"x": 40, "y": 300})
        expect(page.get_by_text("Session moved").first).to_be_visible(timeout=6000)
    check("calendar: drag session to another day", drag_flow)

    # ---- dark mode + settings persistence
    page.goto(WEB + "/dashboard"); page.get_by_role("button", name="Switch to dark mode").click(); page.wait_for_timeout(500)
    check("dark mode class applied", lambda: expect(page.locator("html")).to_have_class(__import__("re").compile("dark")))
    page.screenshot(path=SHOTS / "12-dashboard-dark.png")
    page.reload(); page.wait_for_timeout(600)
    check("dark mode persists after reload", lambda: expect(page.locator("html")).to_have_class(__import__("re").compile("dark")))
    page.goto(WEB + "/analytics"); page.wait_for_timeout(700); page.screenshot(path=SHOTS / "13-analytics-dark.png", full_page=True)

    # ---- logout / login again
    page.goto(WEB + "/settings"); page.get_by_role("button", name="Log out").first.click()
    check("logout returns to landing/login", lambda: page.wait_for_url(lambda u: "/login" in u or u.rstrip("/") == WEB, timeout=5000))
    page.goto(WEB + "/login"); page.get_by_label("Email").fill(email); page.get_by_label("Password").fill("password123"); page.get_by_role("button", name="Log in").click()
    check("login again -> dashboard", lambda: page.wait_for_url("**/dashboard", timeout=8000))
    page.goto(WEB + "/login") ; 
    check("guarded: logged-in user bounced from /login", lambda: page.wait_for_url("**/dashboard", timeout=4000))

    # ---- wrong password error
    ctx2 = b.new_context(); ctx2.set_default_timeout(7000); p2 = ctx2.new_page(); p2.goto(WEB + "/login"); p2.get_by_label("Email").fill(email); p2.get_by_label("Password").fill("nope-nope-nope"); p2.get_by_role("button", name="Log in").click()
    check("wrong password shows error", lambda: expect(p2.get_by_role("alert")).to_contain_text("Incorrect"))

    # ---- demo mode (separate browser context = separate user)
    ctx3 = b.new_context(viewport={"width": 1440, "height": 900}, timezone_id="Asia/Kolkata"); ctx3.set_default_timeout(7000); d = ctx3.new_page()
    d.on("pageerror", lambda e: errors.append("demo:" + str(e)))
    d.goto(WEB); d.get_by_role("button", name="Try the demo").click(); d.wait_for_url("**/dashboard", timeout=15000); d.wait_for_timeout(1200)
    d.screenshot(path=SHOTS / "14-demo-dashboard.png")
    check("demo mode banner + sample data", lambda: (expect(d.get_by_text("Demo Mode").first).to_be_visible(), expect(d.get_by_text("Data Structures").first).to_be_visible(), expect(d.get_by_text("🔥 7 days")).to_be_visible()))
    d.goto(WEB + "/calendar"); d.wait_for_timeout(900); d.screenshot(path=SHOTS / "06b-calendar-demo.png")
    d.goto(WEB + "/analytics"); d.wait_for_timeout(900); d.screenshot(path=SHOTS / "09b-analytics-demo.png", full_page=True)
    d.goto(WEB + "/subjects"); d.wait_for_timeout(900); d.screenshot(path=SHOTS / "04b-subjects-demo.png", full_page=True)
    d.goto(WEB + "/planner"); d.wait_for_timeout(900); d.screenshot(path=SHOTS / "05b-planner-demo.png")

    # ---- mobile layout
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, has_touch=True, is_mobile=True, timezone_id="Asia/Kolkata"); m.set_default_timeout(7000); mp = m.new_page()
    mp.on("pageerror", lambda e: errors.append("mobile:" + str(e)))
    mp.goto(WEB); mp.wait_for_timeout(800); mp.screenshot(path=SHOTS / "20-mobile-landing.png")
    mp.get_by_role("button", name="Try the demo").click(); mp.wait_for_url("**/dashboard", timeout=15000); mp.wait_for_timeout(1200)
    mp.screenshot(path=SHOTS / "21-mobile-dashboard.png")
    check("mobile: bottom nav visible, sidebar hidden", lambda: (expect(mp.get_by_label("Primary")).to_be_visible(), expect(mp.get_by_label("Main")).to_be_hidden()))
    def no_hscroll(path):
        mp.goto(WEB + path); mp.wait_for_timeout(900)
        w = mp.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert w[0] <= w[1] + 1, f"{path} overflows horizontally: {w}"
        bad = mp.evaluate("[...document.querySelectorAll('main section, main article, main .card')].filter(e => !e.closest('.overflow-x-auto') && e.getBoundingClientRect().right > window.innerWidth + 1).map(e => e.className.slice(0, 40))")
        assert not bad, f"{path}: elements extend past the screen: {bad[:2]}"
    for path in ["/dashboard", "/planner", "/tasks", "/subjects", "/focus", "/analytics", "/recommendations", "/settings", "/calendar"]:
        check(f"mobile: no horizontal overflow {path}", lambda path=path: no_hscroll(path))
    mp.goto(WEB + "/planner"); mp.wait_for_timeout(800); mp.screenshot(path=SHOTS / "22-mobile-planner.png")
    mp.goto(WEB + "/calendar"); mp.wait_for_timeout(800); mp.screenshot(path=SHOTS / "23-mobile-calendar.png")
    mp.goto(WEB + "/analytics"); mp.wait_for_timeout(800); mp.screenshot(path=SHOTS / "24-mobile-analytics.png")
    b.close()

ok = sum(1 for _, s, _ in results if s)
for n, s, e in results:
    print(("PASS " if s else "FAIL ") + n + (f"  -> {e}" if e else ""))
print(f"\n{ok}/{len(results)} browser checks passed")
real = [e for e in errors if "favicon" not in e]
print("console/page errors:", real[:8] if real else "none")
sys.exit(0 if ok == len(results) else 1)
