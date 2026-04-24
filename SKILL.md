---
name: paid-collab-extractor
description: >
  Extract every creator paid for a collab on an X/Twitter post via paid.airaa.xyz.
  Use when the user gives a tweet/X URL and asks to find paid creators, paid collaborators,
  sponsored creators, who was paid to promote a tweet, who got paid for the collab,
  or references paid.airaa.xyz, airaa.xyz, or Airaa. Outputs a CSV with handle, display name,
  followers, tier (Nano/Mid/Macro/Mega), likes, RTs, views, snippet, quote-tweet URL,
  and profile URL. Triggers on "who was paid for this tweet", "paid collabs", "airaa",
  "paid promotions", "who got paid to post this", "sponsored creators on this tweet",
  "extract paid collaborators", "/paid-collab-extractor".
---

# Paid Collab Extractor

Drives headless Chromium via Playwright, feeds an X post URL to `paid.airaa.xyz`, waits
for the scan to finish, and writes a CSV of every paid creator listed.

No LLM calls, no API keys — pure deterministic Playwright + BeautifulSoup.

## Steps

1. **Confirm the input URL.** Expect an X post URL like `https://x.com/user/status/1234...`.
   If the user didn't give one, ask for one before continuing.

2. **Bootstrap the venv (first run only).** Check for the skill's `.venv`:

   ```bash
   cd ~/.claude/skills/paid-collab-extractor && \
     [ -d .venv ] || ( \
       python3 -m venv .venv && \
       source .venv/bin/activate && \
       pip install --quiet -r scripts/requirements.txt && \
       python -m playwright install chromium \
     )
   ```

   This takes ~30–60s the first time (downloads Chromium). Subsequent runs skip it.

3. **Run the extractor.** Default output is `airaa_results.csv` in the user's current
   working directory. If the tweet URL contains a status ID, prefer
   `airaa_<status_id>.csv` for clarity.

   ```bash
   source ~/.claude/skills/paid-collab-extractor/.venv/bin/activate && \
     python ~/.claude/skills/paid-collab-extractor/scripts/extract.py \
       "<TWEET_URL>" --out "<OUTPUT_PATH>"
   ```

4. **Report results.** Show the user:
   - Total paid creators found
   - Absolute path to the CSV
   - A 5-row preview sorted by followers (the site's default order)

## Output schema

Columns produced in the CSV:

| Column | Example | Notes |
|---|---|---|
| `handle` | `@historyinmemes` | X handle with `@` prefix |
| `name` | `Historic Vids` | Display name pulled from avatar `alt` |
| `followers` | `6.2M` | Raw string as rendered (K/M suffix) |
| `tier` | `Mega` | Nano / Mid / Macro / Mega |
| `likes` | `45` | On the creator's quote-tweet |
| `rts` | `3` | Retweets on the QT |
| `views` | `60.3K` | Views on the QT |
| `snippet` | `In the Medieval Era...` | First line of the QT text |
| `qt_url` | `https://x.com/.../status/...` | That creator's QT |
| `profile_url` | `https://x.com/historyinmemes` | Creator's X profile |

## Edge cases

- **No paid collabs.** The scan completes with `0 paid found`. Report that plainly
  instead of producing an empty CSV.
- **Scan stalls.** Max wait is 120s. If counts stop moving for ~9s the script exits
  with whatever it has. This is normal even for complete scans.
- **Private/deleted tweet.** The site may show an error state. Relay the error text
  to the user rather than pretending the scan worked.
- **Zero results repeatedly.** Back off a few minutes before retrying — likely
  transient rate limiting.

## Chaining

After running, common next steps:
- Filter to Mega/Macro tier with `awk -F, '$4 ~ /Mega|Macro/' airaa_results.csv`
- Pull each creator's full profile → chain to `twitter-scrape-analyze`
- Draft outreach → chain to `direct-response-copy`
