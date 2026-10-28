"""Fills a running FoodLoop AI server with demo data through the real API, so every screen has something to show.
Usage (server already running):   python scripts/seed_demo.py http://localhost:8000
Safe to run once on a fresh database. Demo accounts share one password: set DEMO_PASSWORD in .env, or it is generated and shown below."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _creds import ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_PASSWORD  # noqa: E402
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
ADMIN = (ADMIN_EMAIL, ADMIN_PASSWORD)
PW = DEMO_PASSWORD


def call(path, method="GET", body=None, token=None):
    for attempt in range(8):
        req = urllib.request.Request(BASE + "/api" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:                      # login/register are rate limited: wait and retry
                time.sleep(7); continue
            raise RuntimeError(f"{method} {path} -> {e.code} {e.read().decode()[:200]}")
    raise RuntimeError("rate limited too long")


admin = call("/auth/login", "POST", {"email": ADMIN[0], "password": ADMIN[1]})["token"]
accounts = []


def reg(name, email, role, lat, lon):
    try:
        r = call("/auth/register", "POST", {"name": name, "email": email, "password": PW, "role": role, "lat": lat, "lon": lon})
        if role in ("vendor", "ngo"):
            call(f"/admin/users/{r['user']['id']}/verify", "POST", {"approve": True}, token=admin)
    except RuntimeError:                           # already exists: just log in
        r = call("/auth/login", "POST", {"email": email, "password": PW})
    accounts.append((role, email))
    return r["token"]


V = {k: reg(*a) for k, a in {
    "spice": ("Spice Villa Restaurant", "spice@demo.in", "vendor", 28.6315, 77.2167),
    "sunrise": ("Sunrise Bakery", "sunrise@demo.in", "vendor", 28.6139, 77.2090),
    "green": ("Green Leaf Caterers", "green@demo.in", "vendor", 28.5921, 77.2290),
    "dairy": ("Daily Dairy Mart", "dairy@demo.in", "vendor", 28.6448, 77.1925),
    "urban": ("Urban Canteen", "urban@demo.in", "vendor", 28.5706, 77.2436),
    "sweet": ("Mithai Ghar", "sweet@demo.in", "vendor", 28.6250, 77.2300),
    "haveli": ("Haveli Caterers", "haveli@demo.in", "vendor", 28.6692, 77.2538),
    "metro": ("Metro Food Court", "metro@demo.in", "vendor", 28.5355, 77.2910),
}.items()}
C = [reg("Ananya Rao", "ananya@demo.in", "citizen", 28.6200, 77.2100),
     reg("Rohan Mehta", "rohan@demo.in", "citizen", 28.6180, 77.2120),
     reg("Meera Nair", "meera@demo.in", "citizen", 28.6220, 77.2080)]
ngo = reg("Annapurna Seva Trust", "ngo@demo.in", "ngo", 28.6139, 77.2090)


def item(v, name, cat, kg, mrp, h, storage="ambient", temp=30):
    return call("/listings", "POST", dict(item_name=name, category=cat, quantity_kg=kg, mrp=mrp, hours_since_prepared=h, storage=storage, ambient_temp_c=temp), token=V[v])


# 1. history: collected orders with star ratings, so vendors show ratings on the market
history = [("spice", "Dal Tadka (lunch)", "cooked_meal", 3, 400, 0.5, [5, 4, 5]), ("sunrise", "Multigrain Loaf", "bakery", 2, 220, 1, [4, 4, 5]),
           ("green", "Vegetable Pulao", "cooked_meal", 4, 500, 0.5, [5, 5]), ("dairy", "Paneer Block", "dairy", 1.5, 300, 6, [3, 4]),
           ("urban", "Cut Fruit Cups", "produce", 2, 260, 1, [4]), ("sweet", "Kaju Katli Box", "dessert", 1, 700, 2, [5, 5, 4])]
for v, name, cat, kg, mrp, h, ratings in history:
    for i, stars in enumerate(ratings):
        l = item(v, name, cat, kg, mrp, h, "refrigerated" if cat in ("dairy", "produce") else "ambient", 28)
        who = C[i % 3]
        call(f"/listings/{l['id']}/reserve", "POST", token=who)
        call(f"/listings/{l['id']}/complete", "POST", token=V[v])
        call(f"/listings/{l['id']}/review", "POST", {"stars": stars}, token=who)

# 2. today's food on the market (all fresh enough to be sold at a discount)
today = [("spice", "Paneer Butter Masala (tray)", "cooked_meal", 4.5, 650, 1.0, "hot_held", 32), ("spice", "Jeera Rice (lunch batch)", "cooked_meal", 6, 420, 1.5, "hot_held", 31),
         ("spice", "Butter Naan Basket", "bakery", 2, 240, 1.0, "hot_held", 30), ("sunrise", "Whole-wheat Bread Loaves", "bakery", 6, 480, 3.0, "ambient", 29),
         ("sunrise", "Butter Croissants", "bakery", 1.8, 360, 6, "ambient", 28), ("sunrise", "Day-old Pav Buns", "bakery", 3, 240, 18, "ambient", 30),
         ("green", "Veg Biryani (party leftover)", "cooked_meal", 9, 1200, 1.5, "hot_held", 30), ("green", "Rajma Chawal Boxes", "cooked_meal", 5, 650, 1.0, "hot_held", 30),
         ("dairy", "Fresh Curd Tubs", "dairy", 3.2, 320, 10, "refrigerated", 28), ("dairy", "Sweet Lassi Bottles", "dairy", 2.4, 240, 12, "refrigerated", 28),
         ("urban", "Mixed Fruit Salad", "produce", 2.5, 300, 5, "refrigerated", 25), ("urban", "Veg Sandwich Platter", "packaged", 2.0, 280, 3, "refrigerated", 25),
         ("sweet", "Gulab Jamun Tin", "dessert", 1.5, 450, 0.5, "refrigerated", 26), ("sweet", "Boondi Ladoo Box", "dessert", 1.2, 380, 0.5, "ambient", 26),
         ("metro", "Idli Sambar Combo", "cooked_meal", 3, 360, 1.0, "hot_held", 30), ("haveli", "Chole Bhature Trays", "cooked_meal", 6, 780, 1.2, "hot_held", 30)]
made = [item(*t) for t in today]
for m in made:
    print(f"{m['item_name']:34s} {m['decision']:8s} {m['remaining_hours']:6.2f} h  Rs {m['price']}")

# 3. food that is too close to expiry to sell: NGO donations
for t in [("haveli", "Chole Rice (catering surplus)", "cooked_meal", 10, 1400, 4.1), ("metro", "Sambar Rice Trays", "cooked_meal", 6.5, 800, 4.2),
          ("green", "Dal Makhani (large pot)", "cooked_meal", 7, 900, 4.0), ("spice", "Mixed Veg Curry (tray)", "cooked_meal", 5, 600, 4.0),
          ("urban", "Pasta Trays", "cooked_meal", 4, 520, 4.1), ("dairy", "Khichdi Pots", "cooked_meal", 6, 540, 4.2)]:
    item(*t)

# 4. one active order, one collected order awaiting a rating, and two complaints (one answered)
active = next(m for m in made if m["item_name"].startswith("Whole-wheat"))
call(f"/listings/{active['id']}/reserve", "POST", token=C[0])
done = next(m for m in made if m["item_name"].startswith("Paneer Butter"))
call(f"/listings/{done['id']}/reserve", "POST", token=C[0])
call(f"/listings/{done['id']}/complete", "POST", token=V["spice"])
c1 = call("/complaints", "POST", {"topic": "food_quality", "message": "The paneer tasted slightly sour when I reached home.", "listing_id": done["id"]}, token=C[0])
call(f"/admin/complaints/{c1['id']}/reply", "POST", {"status": "resolved", "response": "Sorry about that. We have flagged the vendor and refunded the amount at the counter."}, token=admin)
call("/complaints", "POST", {"topic": "pickup_problem", "message": "The vendor said the code was invalid at first, it worked on the second try."}, token=C[1])

print("\nDemo accounts (all share the demo password below; admin uses ADMIN_PASSWORD)")
print(f"  demo password: {PW}")
print(f"  admin    {ADMIN_EMAIL}")
for role, email in accounts:
    print(f"  {role:8s} {email}")
