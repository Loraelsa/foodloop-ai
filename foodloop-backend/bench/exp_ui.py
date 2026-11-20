"""Experiment 5: end-to-end UI tests (Playwright/Chrome) + page-load metrics + screenshots."""
import asyncio, json, os, sys, time
from playwright.async_api import async_playwright
SH = "/home/claude/report/fig/shots/"
URL = "file:///home/claude/foodloop-ui/dist/index.html"
OUT = "/home/claude/foodloop-backend/bench/out/ui.json"
res = []
def rec(i, name, ok, note=""):
    res.append(dict(id=i, name=name, ok=bool(ok), note=note)); print(("PASS" if ok else "FAIL"), i, name, note)

async def login(pg, role):
    await pg.get_by_role("radio", name=role).click(); await pg.get_by_role("button", name="Sign in as").click(); await pg.wait_for_timeout(350)
async def signout(pg):
    if await pg.get_by_role("button", name="Account menu").count():
        await pg.get_by_role("button", name="Account menu").click()
    await pg.get_by_role("button", name="Sign out").click(); await pg.wait_for_timeout(300)

async def main(offline=False):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
        pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        # ---- load metrics (cold cache each run)
        loads = []
        for _ in range(5):
            c2 = await b.new_context(viewport={"width": 1440, "height": 900}); q = await c2.new_page()
            t0 = time.perf_counter(); await q.goto(URL, wait_until="load"); wall = (time.perf_counter() - t0) * 1000
            m = await q.evaluate("""() => { const n = performance.getEntriesByType('navigation')[0]; const f = performance.getEntriesByType('paint').find(e => e.name === 'first-contentful-paint');
                return {dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd, fcp: f ? f.startTime : null, heap: performance.memory ? performance.memory.usedJSHeapSize/1e6 : null} }""")
            loads.append({**m, "wall": wall}); await c2.close()
        await pg.goto(URL); await pg.wait_for_timeout(500)
        await pg.screenshot(path=SH + "login.jpg", type="jpeg", quality=82)
        # ---- E2E
        await login(pg, "Customer"); rec("E01", "Customer signs in and sees surplus feed", await pg.locator(".rcard").count() >= 3, f"{await pg.locator('.rcard').count()} restaurants")
        await pg.wait_for_timeout(3500); await pg.screenshot(path=SH + "shop.jpg", type="jpeg", quality=82)
        await pg.evaluate("location.hash='/shop/r/v1'"); await pg.wait_for_timeout(400)
        await pg.get_by_role("button", name="ADD").first.click(); await pg.get_by_role("button", name="Add one").first.click(); await pg.get_by_role("button", name="ADD").first.click()
        await pg.screenshot(path=SH + "vendor.jpg", type="jpeg", quality=82)
        cnt = await pg.locator(".cartbtn .count").inner_text(); rec("E02", "Add items to cart updates badge", cnt.strip() == "3", f"badge={cnt}")
        await pg.get_by_role("button", name="View cart").click(); await pg.wait_for_timeout(350); await pg.screenshot(path=SH + "cart.jpg", type="jpeg", quality=82)
        await pg.get_by_role("button", name="Place order").click(); await pg.wait_for_timeout(500)
        rec("E03", "Place order shows pickup code", await pg.get_by_text("Pickup code").count() >= 1 and (await pg.locator("text=Ready for pickup").count()) >= 1)
        await pg.screenshot(path=SH + "orders.jpg", type="jpeg", quality=82)
        await signout(pg)
        await login(pg, "Restaurant"); await pg.wait_for_timeout(300); await pg.screenshot(path=SH + "rest_dash.jpg", type="jpeg", quality=82)
        await pg.evaluate("location.hash='/restaurant/orders'"); await pg.wait_for_timeout(400)
        rec("E04", "Restaurant sees the customer's order as a pickup", await pg.locator("tbody tr").count() == 1)
        await pg.get_by_role("button", name="Mark collected").click(); await pg.wait_for_timeout(300)
        rec("E05", "Mark collected updates status", await pg.get_by_text("Collected").count() >= 1)
        await pg.evaluate("location.hash='/restaurant/add'"); await pg.wait_for_timeout(300)
        await pg.fill("#item", "Rajma Chawal"); await pg.fill("#hrs", "4.5"); await pg.fill("#qty", "12"); await pg.wait_for_timeout(900)
        src = (await pg.get_by_test_id("decision-source").inner_text()).strip()
        rec("E06", "Add-surplus preview uses the backend model" if not offline else "Add-surplus falls back to rule table when backend is off",
            src == ("Rule table (offline)" if offline else "XGBoost model"), f"source={src}")
        await pg.screenshot(path=SH + ("add_offline.jpg" if offline else "add.jpg"), type="jpeg", quality=82)
        t0 = time.perf_counter(); await pg.get_by_role("button", name="Publish listing").click(); await pg.wait_for_timeout(450)
        rec("E07", "Publish routes new listing to listings page", "/restaurant/listings" in await pg.evaluate("location.hash"))
        await pg.screenshot(path=SH + "rest_list.jpg", type="jpeg", quality=82)
        await signout(pg)
        await login(pg, "NGO"); rows = pg.locator(".selrow"); n = await rows.count()
        rec("E08", "NGO sees the new donation", await pg.get_by_text("Rajma Chawal").count() >= 1, f"{n} open donations")
        for i in range(min(4, n)): await rows.nth(i).click()
        t0 = time.perf_counter(); await pg.get_by_role("button", name="Plan optimised route").click(); await pg.get_by_test_id("route-source").wait_for(timeout=8000); rt = (time.perf_counter() - t0) * 1000
        rs = (await pg.get_by_test_id("route-source").inner_text()).strip()
        rec("E09", "Route plan uses OR-Tools API" if not offline else "Route plan falls back to local heuristic", rs == ("Offline heuristic" if offline else "OR-Tools API"), f"source={rs}, {rt:.0f} ms UI round trip")
        await pg.locator(".map").scroll_into_view_if_needed(); await pg.wait_for_timeout(200)
        await pg.screenshot(path=SH + ("route_offline.jpg" if offline else "route.jpg"), type="jpeg", quality=82)
        await pg.get_by_role("button", name="Accept and confirm pickup").click(); await pg.wait_for_timeout(400)
        rec("E10", "Confirming a pickup removes the items from the open list", await pg.locator(".selrow").count() == n - min(4, n))
        await pg.get_by_role("link", name="My pickups").click(); await pg.wait_for_timeout(350); await pg.screenshot(path=SH + "pickups.jpg", type="jpeg", quality=82)
        await signout(pg)
        await login(pg, "Admin"); await pg.wait_for_timeout(300); await pg.screenshot(path=SH + "admin.jpg", type="jpeg", quality=82)
        before = await pg.get_by_role("button", name="Approve").count(); await pg.get_by_role("button", name="Approve").first.click(); await pg.wait_for_timeout(300)
        rec("E11", "Admin approves a pending restaurant", await pg.get_by_role("button", name="Approve").count() == before - 1)
        for name, f in (("Restaurants", "admin_rest"), ("Impact & SDGs", "admin_impact"), ("Decision rules", "admin_rules")):
            await pg.get_by_role("link", name=name).click(); await pg.wait_for_timeout(300); await pg.screenshot(path=SH + f + ".jpg", type="jpeg", quality=82)
        await signout(pg)
        await pg.evaluate("location.hash='/admin'"); await pg.wait_for_timeout(300)
        rec("E12", "Signed-out user cannot open /admin", await pg.get_by_role("button", name="Sign in as").count() == 1)
        # mobile
        m = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2); mp = await m.new_page(); await mp.goto(URL); await login(mp, "Customer"); await mp.wait_for_timeout(3600)
        await mp.screenshot(path=SH + "mobile_shop.jpg", type="jpeg", quality=82)
        ov = await mp.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        rec("E13", "No horizontal overflow on a 390 px phone screen", not ov)
        rec("E14", "No uncaught JavaScript errors in the whole run", not errs, "; ".join(errs[:2]))
        await b.close()
    def med(k):
        v = sorted(x[k] for x in loads if x[k] is not None)
        return v[len(v) // 2] if v else None
    out = dict(tests=res, load=dict(dcl_ms=med("dcl"), load_ms=med("load"), fcp_ms=med("fcp"), heap_mb=med("heap"), runs=loads))
    json.dump(out, open(OUT.replace(".json", "_offline.json" if offline else ".json"), "w"), indent=1)
    print(out["load"]["dcl_ms"], out["load"]["load_ms"], out["load"]["fcp_ms"], out["load"]["heap_mb"])
asyncio.run(main(offline=len(sys.argv) > 1))
