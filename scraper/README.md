# Roblox Charts Scraper

Collects the games on Roblox's Discover/charts surface — name, description, genre, age rating, popularity, creator, and logo — into a single CSV. Built as the data layer for a game-similarity graph.

Output: **~800 games × 21 columns**, in about 3 minutes.

---

## Quick start

```bash
pip install requests
python scrape_roblox.py
```

Writes `games.csv` next to the script.

To also download the logo image files:

```python
DOWNLOAD_IMAGES = True    # near the top of the script
```

That adds ~800 requests (~5 min, 30–60 MB) and writes `logos/{universe_id}.png`.

---

## What it's actually doing

Roblox's website is a React app. If you fetch `roblox.com/charts` and parse the HTML, you get an empty shell — the content arrives afterward, when the page's JavaScript calls Roblox's JSON APIs.

So this script skips the browser and calls those same APIs directly. Same data the page shows you, already structured. No BeautifulSoup, no Selenium, one dependency.

All endpoints are public and unauthenticated.

---

## The four steps

### Step 1 — Page through the Discover sorts

```
GET https://apis.roblox.com/explore-api/v1/get-sorts
      ?sessionId=<uuid>&device=computer&country=us
      [&sortsPageToken=<token>]
```

Returns the sections of the charts page — "Top Trending", "Top Earning", "Trending in RPG", and so on.

**The response is paginated.** It returns 6 entries at a time plus a `nextSortsPageToken`. Following that token is the difference between 5 sorts and **26 sorts** — miss it and you lose two-thirds of your data.

Each sort arrives with **its games already attached** (~96 per sort), so there's no follow-up call needed to expand a row.

Two details the code handles:

- One entry per page has `contentType: "Filters"` — that's the device/country dropdown config, not a sort. It has a `sortId` but no games, so it's skipped.
- `MAX_SORT_PAGES` caps the loop at 25 pages so a misbehaving token can't spin forever. Real runs stop at 5.

Games are collected into a dict keyed by ID, which deduplicates the heavy overlap between sorts. A game also records **which sorts it appeared in** — if two games keep co-occurring, Roblox's own curation already considers them related.

### Step 2 — Fetch full details

```
GET https://games.roblox.com/v1/games?universeIds=123,456,...
```

Different host (`games.roblox.com`). This is the only place **descriptions** live, along with creator, visits, favorites, and dates.

### Step 3 — Fetch logos

```
GET https://thumbnails.roblox.com/v1/games/icons
      ?size=512x512&format=Png&isCircular=false&universeIds=123,456,...
```

Third host. Returns CDN **URLs**, not image bytes. Entries can come back `state: "Pending"` or `"Blocked"` instead of an image — those leave `logo_url` blank rather than failing.

### Step 4 — Merge and write

The sorts response and the details response each carry fields the other lacks. Age ratings and vote counts come only from step 1; descriptions come only from step 2. Step 4 joins them on `universe_id`.

---

## Output columns

| Column | Source | Notes |
|---|---|---|
| `universe_id` | sorts | Primary key. Not the same as the place ID in a Roblox URL |
| `name` | details → sorts | Falls back to the sorts value |
| `description` | details | Free text. Messy — see below |
| `genre` | details → sorts | Roblox's own top-level label |
| `subgenre` | details | Often empty |
| `content_maturity` | sorts | `minimal` / `mild` / `moderate` |
| `minimum_age` | sorts | Integer |
| `sorts` | sorts | Pipe-separated list of sections it charted in |
| `sort_count` | sorts | How many — a rough "how hard is Roblox pushing this" |
| `logo_url` | thumbnails | CDN URL, blank if not ready |
| `creator_name` / `creator_type` / `creator_id` | details | `type` is User or Group |
| `playing` | details → sorts | Concurrent players at scrape time |
| `visits` | details | Lifetime |
| `favorites` | details | |
| `up_votes` / `down_votes` | sorts | Quality signal independent of popularity |
| `max_players` | details | Server capacity |
| `created` / `updated` | details | ISO timestamps |

---

## Configuration

| Setting | Default | What it does |
|---|---|---|
| `COUNTRY` | `"us"` | Which country's charts to read |
| `DEVICE` | `"computer"` | Mobile and desktop chart differently |
| `BATCH_SIZE` | `25` | Games per batched request |
| `PAUSE` | `0.4` | Seconds between requests |
| `MAX_SORT_PAGES` | `25` | Safety stop on sort pagination |
| `DOWNLOAD_IMAGES` | `False` | Save logo files, not just URLs |

---

## Two design decisions worth knowing

### `fetch_batch` splits on failure

The batch endpoints return a bare `400` for two different problems — too many IDs, or one dead ID in the list — and they're indistinguishable from outside.

Rather than diagnosing, a failed batch is split in half and each half retried, recursively. Whatever is broken gets isolated: a genuinely dead game ends up alone, is skipped with a note, and everything else in that batch survives. It also self-corrects if `BATCH_SIZE` is set too high, so it can't get permanently stuck.

Occasional `! skipping game <id>` output is normal — usually a game deleted or made private since it charted.

### URLs are built by hand

`requests` encodes commas in query params as `%2C`, and these endpoints reject that. So batch URLs are assembled by string concatenation instead of passed as `params`.

**This means `universeIds` must stay last in `DETAILS_URL` and `LOGOS_URL`.** Moving it breaks them.

---

## Limits

**~800 games is the ceiling here.** 26 sorts × 96 games each, with heavy overlap. There's no deeper pagination — `get-sort-content` returns exactly the same 96 games already inlined in step 1, with no page token, which is why that call was removed entirely.

To go beyond, either:

- **Union multiple countries.** Each country is a *different ranking*, not a different catalog — `country=all` returns 809 games to `us`'s 798, overlapping on only 709. Measured across 10 countries, the union reaches ~1,321. Culturally distant markets add most (jp +91, kr +65); close ones add least (de +27).
- **Use `omni-search`** across genre keywords. Reaches games that never chart at all, but changes what you're sampling — no longer "popular games" but "a slice of the catalog."

**This is a US-desktop-popularity sample**, not a representative sample of Roblox. Worth stating plainly in any analysis built on it.

**Descriptions are messy.** Expect emoji, changelogs, promo codes, tag spam, and Discord links. Cleaning them is real work and largely determines whether downstream clustering is any good.

**The API is undocumented.** Roblox can change these endpoints without notice. Nothing here is a stable contract.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| "No games found" | No connection, or the sorts response changed shape |
| Only ~280 games | Sort pagination isn't being followed — check `nextSortsPageToken` |
| Many `! skipping game` lines | Normal in small numbers. If constant, the details endpoint changed |
| All `logo_url` blank | Thumbnails endpoint down, or the `state` field was renamed |
| Requests failing after a while | Rate limited — raise `PAUSE` |

To inspect any endpoint yourself: open it directly in a browser, or use DevTools → Network → Fetch/XHR on `roblox.com/charts` and watch what the page calls.

---

## Etiquette

Public, unauthenticated data at a deliberately slow request rate, for a personal project. Keep `PAUSE` at 0.4s or higher, and don't republish the raw dataset.
