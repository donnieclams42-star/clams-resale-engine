OFFICIAL CLAMS + RADAR MERGE

What this pack does:
- Keeps CLAMS / Market Radar as the main FastAPI app
- Adds a real /radar page
- Starts a background Radar worker on app startup
- Writes vetted alerts to cache/radar_results.json
- Writes service health to cache/radar_status.json
- Sends approved alerts to Discord using DISCORD_WEBHOOK
- Uses app cache as the system of record (Discord is notification only)

Required environment variables:
- DISCORD_WEBHOOK
- EBAY_CLIENT_ID
- EBAY_CLIENT_SECRET
- Existing CLAMS vars you already use (OpenAI / Stripe / Supabase if enabled)

Notes:
- Radar worker uses eBay, Mercari, and OfferUp from the provided source package.
- Facebook scanner source was not present in the latest upload, so it is intentionally not wired here.
- This is the safer launch path and avoids hidden pyc-only dependencies.
