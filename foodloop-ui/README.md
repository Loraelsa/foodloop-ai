# FoodLoop AI: front end

Four role portals in one React app: Customer, Restaurant, NGO, Admin.

## Quickest way to see it
Double-click `FoodLoop.html`. No install needed. Pick a role on the sign-in screen (credentials are pre-filled).

## Run it in VS Code (needs Node.js 18+ from nodejs.org)
    npm install
    npm run dev        # opens http://localhost:5173
    npm run build      # creates dist/index.html (single file)

## What is real and what is a stand-in
- Shared state (restaurant listings -> customer shop -> NGO pickups -> admin) is real and saved in the browser (localStorage).
- `src/engine.js` holds the decision rule (shelf-life table + thresholds), the route optimiser (nearest neighbour + 2-opt) and the impact maths.
  These are front-end stand-ins. When the FastAPI backend exists, replace `decide()` and `optimiseRoute()` with API calls to the XGBoost model and OR-Tools.
- The 14-day chart history is sample data and is labelled "Sample history" in the UI.
- Restaurant names are fictional; localities are real Bengaluru areas with approximate coordinates.

## Demo accounts
Customer: Aarav Sharma | Restaurant: Saffron Tiffin Room | NGO: Annapurna Seva Trust | Admin: Platform Admin
Admin > "Reset demo data" restores the sample data.
