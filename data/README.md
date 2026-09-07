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
