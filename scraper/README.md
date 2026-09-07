# Roblox Charts Scraper

Collects the games on Roblox's Discover/charts surface — name, description, genre, age rating, popularity, creator, and logo — into a single CSV. Built as the data layer for a game-similarity graph.

Output: **~800 games × 21 columns**, in about 3 minutes.

---

## Quick start

```bash
pip install requests
python scrape_roblox.py
```

Writes `games.csv` next to the script (moved to ../data/). To also download the logo image files: DOWNLOAD_IMAGES = True

---

Roblox's website is a React app. If you fetch `roblox.com/charts` and parse the HTML, contains mostly the application shell — the content arrives afterward, when the page's JavaScript calls Roblox's public JSON APIs.

Instead of using Selenium/Playwright and scraping rendered HTML, we can call those JSON endpoints directly with Python. So this script skips the browser and calls those same APIs directly. All endpoints are public and unauthenticated.

---

### Step 1 — Page through the Discover sorts

```
GET https://apis.roblox.com/explore-api/v1/get-sorts
      ?sessionId=<uuid>&device=computer&country=us
      [&sortsPageToken=<token>]
```

Returns the sections of the charts page — "Top Trending", "Top Earning", "Trending in RPG", and so on.

**The response is paginated.** It returns 6 entries at a time plus a `nextSortsPageToken` for retrieving subsequent pages. 

Each sort includes its associated games directly in the response (~96 games per sort), eliminating the need for additional requests to expand individual rows.

Games are collected into a dict keyed by ID, which deduplicates the heavy overlap between sorts. A game also records **which sorts it appeared in** — if two games keep co-occurring, Roblox's own curation already considers them related.

### Step 2 — Fetch full details (metadata)

```
GET https://games.roblox.com/v1/games?universeIds=123,456,...
```

Different host (`games.roblox.com`). This is the only place **descriptions** live, along with creator, visits, favorites, and dates.

### Step 3 — Fetch logos

```
GET https://thumbnails.roblox.com/v1/games/icons
      ?size=512x512&format=Png&isCircular=false&universeIds=123,456,...
```

Third host. Returns CDN **URLs** Entries can come back `state: "Pending"` or `"Blocked"` instead of an image — those leave `logo_url` blank rather than failing.

### Step 4 — Merge and write

The sorts response and the details response each carry fields the other lacks. Age ratings and vote counts come only from step 1; descriptions come only from step 2. Step 4 joins them on `universe_id`.

---
**This is a US-desktop-popularity sample**, not a representative sample of Roblox. 
