# extract-paid-twitter-collabs

A Claude Code skill (and standalone Python CLI) that extracts every creator paid for a collab on an X/Twitter post via [paid.airaa.xyz](https://paid.airaa.xyz/).

Feed it a tweet URL, it drives headless Chromium through the Airaa scan, and writes a CSV of every paid creator listed — handle, display name, followers, tier, likes, RTs, views, snippet, and the URL of their quote-tweet.

No LLM calls, no API keys. Just Playwright + BeautifulSoup.

## Example output

```
handle,name,followers,tier,likes,rts,views,snippet,qt_url,profile_url
@historyinmemes,Historic Vids,6.2M,Mega,45,3,60.7K,"In the Medieval Era, networking was done...",https://x.com/historyinmemes/status/...,https://x.com/historyinmemes
@NoContextHumans,Out of Context Human Race,4.3M,Mega,65,2,88.6K,...
@greg16676935420,greg,1.5M,Mega,172,6,33.2K,...
```

One row per paid creator. Typical viral tweets return 50–150 rows.

## Install as a Claude Code skill

Clone the repo straight into your user skills directory:

```bash
git clone https://github.com/shannhk/extract-paid-twitter-collabs \
  ~/.claude/skills/paid-collab-extractor
```

Then in any Claude Code session, trigger it by pasting an X URL and asking something like:

- *"who was paid for this tweet?"*
- *"extract paid collabs from `<url>`"*
- *"airaa scan this"*

The skill bootstraps its own venv + Chromium on first run (~30–60s) and reuses it after.

## Use as a standalone CLI

```bash
git clone https://github.com/shannhk/extract-paid-twitter-collabs
cd extract-paid-twitter-collabs

python3 -m venv .venv
source .venv/bin/activate
pip install -r scripts/requirements.txt
python -m playwright install chromium

python scripts/extract.py "https://x.com/user/status/1234567890" --out paid.csv
```

Flags:

| Flag | Default | Notes |
|---|---|---|
| `<tweet_url>` | required | Any `x.com` or `twitter.com` post URL |
| `--out` | `airaa_results.csv` | Output CSV path |
| `--show-browser` | off | Run Chromium in headed mode for debugging |

## CSV schema

| Column | Example | Notes |
|---|---|---|
| `handle` | `@historyinmemes` | X handle with `@` prefix |
| `name` | `Historic Vids` | Display name from the creator's avatar |
| `followers` | `6.2M` | Raw string, K/M suffix preserved |
| `tier` | `Mega` | `Nano` / `Mid` / `Macro` / `Mega` |
| `likes` | `45` | On that creator's quote-tweet |
| `rts` | `3` | Retweets on the QT |
| `views` | `60.3K` | Views on the QT |
| `snippet` | `In the Medieval Era...` | First line of the QT text |
| `qt_url` | `https://x.com/.../status/...` | Link to the creator's QT |
| `profile_url` | `https://x.com/historyinmemes` | Creator's profile |

## How it works

1. Navigates to `https://paid.airaa.xyz/`
2. Fills the tweet URL into the input, clicks submit
3. Polls `Paid found` and `QTs scanned` counts until they stabilize (max 120s)
4. Parses the results table with BeautifulSoup
5. Writes a CSV

Site layout changes will break the selectors. They're documented in `scripts/extract.py` — easy to patch.

## Why not just use the X API / Firecrawl / Browser Use?

- **X API** — doesn't expose Airaa's paid-collab detection. This skill reads what Airaa already computed.
- **Firecrawl** — paid service, overkill for a single deterministic flow.
- **Browser Use (cloud)** — requires paid credits; the interaction here is simple enough that an LLM-driven agent is overkill.

Plain Playwright is the right tool: free, local, deterministic.

## License

MIT
