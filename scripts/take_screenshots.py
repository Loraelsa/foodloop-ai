"""Captures real screenshots of the running app for docs/screenshots (run scripts/seed_demo.py first).
Usage: python scripts/take_screenshots.py http://localhost:8000 docs/screenshots"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from _creds import ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_PASSWORD  # noqa: E402

BASE, OUT = sys.argv[1].rstrip("/"), Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)


def login(page, email, pw):
    page.goto(BASE); page.fill("input[type=email]", email); page.fill("input[type=password]", pw)
    page.click("form button.btn"); page.wait_for_selector(".tabs")


with sync_playwright() as p:
    b = p.chromium.launch()
    new = lambda w=1280, h=900, **kw: b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1.5, **kw).new_page()
    pg = new(); pg.goto(BASE); pg.wait_for_selector(".hero"); pg.wait_for_timeout(1500); pg.screenshot(path=OUT / "01_landing.png", full_page=True)
    pg = new(); login(pg, "ananya@demo.in", DEMO_PASSWORD); pg.wait_for_selector(".deal"); pg.wait_for_timeout(600)
    pg.screenshot(path=OUT / "02_citizen_explore.png", full_page=True)
    pg.click(".deal .title-btn >> nth=1"); pg.wait_for_selector(".sheet"); pg.wait_for_timeout(500); pg.screenshot(path=OUT / "03_citizen_food_detail.png"); pg.keyboard.press("Escape")
    pg.click(".tabs >> text=Orders"); pg.wait_for_selector(".order"); pg.wait_for_timeout(500); pg.screenshot(path=OUT / "04_citizen_orders_qr.png", full_page=True)
    pg.click(".tabs >> text=Help"); pg.wait_for_selector(".topics"); pg.wait_for_timeout(400); pg.screenshot(path=OUT / "05_help_complaints.png", full_page=True)
    pg.click(".tabs >> text=Impact"); pg.wait_for_selector(".stat-card"); pg.wait_for_timeout(1500); pg.screenshot(path=OUT / "09_impact_dashboard.png", full_page=True)
    v = new(1280, 1500); login(v, "spice@demo.in", DEMO_PASSWORD); v.wait_for_selector("form")
    v.fill("input[placeholder='e.g. Veg biryani']", "Veg biryani"); v.get_by_label("Hours since prepared").fill("4")
    v.click("text=Check freshness"); v.wait_for_selector(".verdict"); v.wait_for_timeout(1200); v.screenshot(path=OUT / "06_vendor_freshness_verdict.png")
    n = new(); login(n, "ngo@demo.in", DEMO_PASSWORD); n.wait_for_selector("table"); [n.check(f"tbody input[type=checkbox] >> nth={i}") for i in range(n.locator("tbody input[type=checkbox]").count())]
    n.click("text=Plan pickup"); n.wait_for_selector(".route-svg"); n.wait_for_timeout(800); n.screenshot(path=OUT / "07_ngo_route_plan.png", full_page=True)
    a = new(); login(a, ADMIN_EMAIL, ADMIN_PASSWORD); a.wait_for_selector(".ticket"); a.wait_for_timeout(500); a.screenshot(path=OUT / "08_admin_complaints.png", full_page=True)
    ph = new(390, 844, is_mobile=True, has_touch=True); login(ph, "ananya@demo.in", DEMO_PASSWORD); ph.wait_for_selector(".deal"); ph.wait_for_timeout(500); ph.screenshot(path=OUT / "10_phone_explore.png")
    b.close()
print("saved to", OUT)
