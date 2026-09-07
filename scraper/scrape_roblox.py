"""
Scrape Roblox's charts / Discover games into a CSV.

How it works (4 steps):
  1. Page through Roblox's Discover sorts. Each sort ("Top Trending",
     "Trending in RPG", ...) already comes back with its games attached,
     so this one loop gets us the whole catalog surface.
  2. Look up the full details for those games -- descriptions live here
  3. Look up each game's logo image
  4. Write everything to games.csv

These are the same JSON endpoints roblox.com/charts calls in your browser.
Nothing here needs a login.

Run:  python scrape_roblox.py
Needs: pip install requests
"""

import csv
import os
import time
import uuid
import requests

# ---------------------------------------------------------------- settings

OUTPUT_FILE = "games.csv"
PAUSE = 0.4          # seconds between requests, so we don't hammer their API
TIMEOUT = 20         # seconds before giving up on a request
BATCH_SIZE = 25      # games per request (these endpoints 400 if you ask for too many)
MAX_SORT_PAGES = 25  # safety stop; there are ~5 pages of sorts in practice

# "us" gives noticeably more than "all". Change to browse another country's charts.
COUNTRY = "us"
DEVICE = "computer"

# Flip to True to also save the actual logo images to a folder.
# Off by default: the CSV keeps the image URLs either way, which is all the
# graph needs. Turn this on if you want them offline.
DOWNLOAD_IMAGES = False
LOGO_DIR = "logos"
LOGO_SIZE = "512x512"

SORTS_URL = "https://apis.roblox.com/explore-api/v1/get-sorts"

# The two batch endpoints. universeIds has to come last -- we append to these.
DETAILS_URL = "https://games.roblox.com/v1/games?universeIds="
LOGOS_URL = (
    "https://thumbnails.roblox.com/v1/games/icons"
    f"?size={LOGO_SIZE}&format=Png&isCircular=false&universeIds="
)

# Roblox ties Discover results to a session id. Any random UUID works.
SESSION_ID = str(uuid.uuid4())

HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}


def get(url, params=None, quiet=False):
    """
    One GET request that returns JSON. Returns None instead of crashing.

    Pass params=None and put everything in the URL yourself when the endpoint
    is fussy about encoding (see fetch_batch).
    """
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        time.sleep(PAUSE)
        return response.json()
    except Exception as error:
        if not quiet:
            print(f"  ! request failed: {error}")
        time.sleep(1)
        return None


def fetch_batch(base_url, ids):
    """
    Fetch one batch of games from a batch endpoint.

    Two quirks we work around:
      - these endpoints reject commas that requests has URL-encoded, so we
        build the URL by hand instead of passing params
      - they 400 on batches that are too large, and on any single bad ID

    Both look identical from outside (a 400), so on failure we just split the
    batch in half and try again. A genuinely bad ID ends up alone and is
    skipped; a too-big batch shrinks until it fits.
    """
    data = get(base_url + ",".join(str(i) for i in ids), quiet=True)

    if data:
        return data.get("data", [])

    if len(ids) == 1:
        print(f"  ! skipping game {ids[0]}")
        return []

    middle = len(ids) // 2
    return fetch_batch(base_url, ids[:middle]) + fetch_batch(base_url, ids[middle:])


def fetch_all(base_url, universe_ids):
    """Run fetch_batch over every game, BATCH_SIZE at a time."""
    results = []
    for start in range(0, len(universe_ids), BATCH_SIZE):
        results.extend(fetch_batch(base_url, universe_ids[start:start + BATCH_SIZE]))
        print(f"  {len(results)} / {len(universe_ids)}")
    return results


# ---------------------------------------------------------------- the 4 steps

def step1_get_sorts():
    """
    Page through the Discover sorts, collecting the games inside each one.

    Two things worth knowing:
      - the response hands back a `nextSortsPageToken`. Without following it
        you only see the first ~5 sorts, which is most of the catalog missing.
      - each sort arrives with its games already attached, so there's no
        separate "now fetch this sort's games" call to make.

    Returns the games keyed by id (so duplicates across sorts collapse), plus
    a record of which sorts each game appeared in.
    """
    print("Step 1: paging through Discover sorts")

    games_by_id = {}      # universe_id -> the inline game record
    sorts_by_game = {}    # universe_id -> list of sort names it appeared in
    page_token = None

    for page in range(MAX_SORT_PAGES):
        params = {
            "sessionId": SESSION_ID,
            "device": DEVICE,
            "country": COUNTRY,
        }
        if page_token:
            params["sortsPageToken"] = page_token

        data = get(SORTS_URL, params)
        if not data:
            break

        for sort in data.get("sorts", []):
            # the response also contains a "Filters" entry (the device/country
            # dropdowns). It has a sortId but no games, so skip it.
            if sort.get("contentType") != "Games":
                continue

            sort_name = sort.get("sortDisplayName", "?")
            sort_games = sort.get("games", [])

            for game in sort_games:
                universe_id = game.get("universeId")
                if not universe_id:
                    continue
                games_by_id[universe_id] = game
                names = sorts_by_game.setdefault(universe_id, [])
                if sort_name not in names:
                    names.append(sort_name)

            print(f"  {sort_name}: {len(sort_games)} games")

        page_token = data.get("nextSortsPageToken")
        if not page_token:
            break

    print(f"  {len(games_by_id)} unique games across all sorts")
    return games_by_id, sorts_by_game


def step2_get_details(universe_ids):
    """Look up description, creator, visits etc. (descriptions are only here.)"""
    print("Step 2: fetching game details")
    return {game["id"]: game for game in fetch_all(DETAILS_URL, universe_ids)
            if game.get("id")}


def step3_get_logos(universe_ids):
    """
    Look up each game's logo (the square icon you see on the Discover page).

    Returns universe_id -> image URL. Images live on Roblox's CDN, so the URL
    is usually all you need; set DOWNLOAD_IMAGES = True to save the files too.
    """
    print("Step 3: fetching game logos")
    logos = {}

    for item in fetch_all(LOGOS_URL, universe_ids):
        # entries look like {"targetId": 123, "state": "Completed", "imageUrl": "..."}
        # state is "Pending" or "Blocked" when there's no usable image yet
        if item.get("state") == "Completed" and item.get("imageUrl"):
            logos[item["targetId"]] = item["imageUrl"]

    print(f"  got {len(logos)} logos")

    if DOWNLOAD_IMAGES:
        download_logos(logos)

    return logos


def download_logos(logos):
    """Save the logo images to disk. Only runs if DOWNLOAD_IMAGES is True."""
    os.makedirs(LOGO_DIR, exist_ok=True)
    print(f"  downloading images to {LOGO_DIR}/")
    saved = 0

    for universe_id, url in logos.items():
        path = os.path.join(LOGO_DIR, f"{universe_id}.png")
        if os.path.exists(path):     # already have it, skip
            continue
        try:
            response = requests.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            with open(path, "wb") as file:
                file.write(response.content)
            saved += 1
            time.sleep(PAUSE)
        except Exception as error:
            print(f"  ! couldn't download {universe_id}: {error}")

    print(f"  saved {saved} images")


def step4_save(games_by_id, sorts_by_game, details_by_id, logos):
    """
    Merge the three sources into one CSV.

    The sorts response and the details response each carry things the other
    doesn't -- age ratings and vote counts only come from the sorts, and
    descriptions only come from the details.
    """
    print(f"Step 4: writing {OUTPUT_FILE}")

    columns = [
        "universe_id", "name", "description",
        "genre", "subgenre", "content_maturity", "minimum_age",
        "sorts", "sort_count", "logo_url",
        "creator_name", "creator_type", "creator_id",
        "playing", "visits", "favorites", "up_votes", "down_votes",
        "max_players", "created", "updated",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for universe_id, listed in games_by_id.items():
            detail = details_by_id.get(universe_id, {})
            creator = detail.get("creator") or {}
            game_sorts = sorts_by_game.get(universe_id, [])

            writer.writerow({
                "universe_id":      universe_id,
                "name":             detail.get("name") or listed.get("name"),
                "description":      detail.get("description"),
                "genre":            detail.get("genre_l1") or listed.get("genreL1"),
                "subgenre":         detail.get("genre_l2"),
                "content_maturity": listed.get("contentMaturity"),
                "minimum_age":      listed.get("minimumAge"),
                "sorts":            " | ".join(game_sorts),
                "sort_count":       len(game_sorts),
                "logo_url":         logos.get(universe_id, ""),
                "creator_name":     creator.get("name"),
                "creator_type":     creator.get("type"),
                "creator_id":       creator.get("id"),
                "playing":          detail.get("playing") or listed.get("playerCount"),
                "visits":           detail.get("visits"),
                "favorites":        detail.get("favoritedCount"),
                "up_votes":         listed.get("totalUpVotes"),
                "down_votes":       listed.get("totalDownVotes"),
                "max_players":      detail.get("maxPlayers"),
                "created":          detail.get("created"),
                "updated":          detail.get("updated"),
            })


# ---------------------------------------------------------------- main

def main():
    games_by_id, sorts_by_game = step1_get_sorts()
    if not games_by_id:
        print("\nNo games found. Check your connection, or Roblox changed the API.")
        return

    universe_ids = list(games_by_id)
    details_by_id = step2_get_details(universe_ids)
    logos = step3_get_logos(universe_ids)
    step4_save(games_by_id, sorts_by_game, details_by_id, logos)

    print(f"\nDone. {len(games_by_id)} games saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
