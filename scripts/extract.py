"""Airaa paid-creator extractor.

Usage:
    python airaa_extract.py <tweet_url> [--out results.csv]

Given an X post URL, scrapes paid.airaa.xyz and writes a CSV of every paid
creator listed, including handle, followers, tier, engagement, snippet, and
the creator's quote-tweet URL.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


AIRAA_URL = "https://paid.airaa.xyz/"
SCAN_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 3


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def parse_results(html: str) -> list[dict]:
    """Parse paid.airaa.xyz results HTML into a list of creator rows."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []

    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        handle_link = tr.select_one('a[href^="https://x.com/"]')
        if not handle_link or not handle_link.get_text(strip=True).startswith("@"):
            continue

        handle = handle_link.get_text(strip=True)
        profile_url = handle_link["href"]

        # Name + avatar — the row's <img> element carries both
        name = ""
        avatar_url = ""
        avatar = tr.select_one("img[alt]")
        if avatar:
            name = (avatar.get("alt") or "").strip()
            avatar_url = (avatar.get("src") or "").strip()
            # Twitter serves a "_normal" (48x48) avatar — bump to "_bigger" (73x73) for crispness
            avatar_url = avatar_url.replace("_normal.", "_bigger.")

        followers_cell = tds[1]
        followers = ""
        tier = ""
        spans = followers_cell.find_all("span")
        if spans:
            followers = spans[0].get_text(strip=True)
            if len(spans) > 1:
                tier = spans[1].get_text(strip=True)

        likes = _text(tds[2]) if len(tds) > 2 else ""
        rts = _text(tds[3]) if len(tds) > 3 else ""
        views = _text(tds[4]) if len(tds) > 4 else ""

        snippet_cell = tds[5] if len(tds) > 5 else None
        snippet = _text(snippet_cell) if snippet_cell else ""
        snippet = re.sub(r"View ↗$", "", snippet).strip()

        # The "View ↗" link (usually in the last td) points to the QT URL
        qt_url = ""
        for a in tr.find_all("a"):
            txt = a.get_text(strip=True)
            if txt.startswith("View") and "/status/" in (a.get("href") or ""):
                qt_url = a["href"]
                break

        rows.append({
            "handle": handle,
            "name": name,
            "avatar_url": avatar_url,
            "followers": followers,
            "tier": tier,
            "likes": likes,
            "rts": rts,
            "views": views,
            "snippet": snippet,
            "qt_url": qt_url,
            "profile_url": profile_url,
        })

    return rows


async def fetch_results(tweet_url: str, headless: bool = True) -> str:
    """Drive paid.airaa.xyz with Playwright and return the results HTML."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            await page.goto(AIRAA_URL, wait_until="networkidle")
            await page.fill('input[placeholder*="x.com"]', tweet_url)
            await page.click('button[type="submit"]')

            deadline = asyncio.get_event_loop().time() + SCAN_TIMEOUT_SECONDS
            last = (-1, -1)
            stable_checks = 0
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                text = await page.inner_text("body")
                m_paid = re.search(r"(\d+)\s+Paid found", text)
                m_qts = re.search(r"(\d+)\s+QTs scanned", text)
                paid = int(m_paid.group(1)) if m_paid else 0
                qts = int(m_qts.group(1)) if m_qts else 0
                stop_visible = await page.locator("text=Stop").count()
                print(f"  paid={paid} qts_scanned={qts} stop_visible={bool(stop_visible)}", file=sys.stderr)

                if (paid, qts) == last and paid + qts > 0:
                    stable_checks += 1
                else:
                    stable_checks = 0
                last = (paid, qts)

                if stop_visible == 0 and (paid or qts):
                    break
                if stable_checks >= 3:  # counts haven't moved for ~9s
                    break

            return await page.content()
        finally:
            await browser.close()


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


_TWEET_URL_RE = re.compile(r"(?:x|twitter)\.com/([^/]+)/status/(\d+)")


def _parse_tweet_url(url: str) -> tuple[str, str]:
    m = _TWEET_URL_RE.search(url)
    if not m:
        return "", ""
    return m.group(1), m.group(2)  # (source_handle, tweet_id)


def _fetch_source_display_name(tweet_url: str) -> str:
    """Ask X's public oEmbed endpoint for the source tweet author's display name.

    Works without auth. Fails silently and returns "" if the endpoint refuses.
    """
    oembed = (
        "https://publish.twitter.com/oembed?omit_script=1&url="
        + urllib.parse.quote(tweet_url, safe="")
    )
    try:
        with urllib.request.urlopen(oembed, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            return (data.get("author_name") or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"  (oembed lookup failed: {exc})", file=sys.stderr)
        return ""


def write_json(rows: list[dict], path: Path, tweet_url: str) -> None:
    source_handle, tweet_id = _parse_tweet_url(tweet_url)
    source_name = _fetch_source_display_name(tweet_url) if source_handle else ""
    payload = {
        "tweet_url": tweet_url,
        "source_handle": source_handle,
        "source_name": source_name,
        "tweet_id": tweet_id,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(rows),
        "creators": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def _infer_format(path: Path, explicit: str | None) -> str:
    if explicit and explicit != "auto":
        return explicit
    suffix = path.suffix.lower().lstrip(".")
    return suffix if suffix in ("csv", "json") else "csv"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Extract paid creators from paid.airaa.xyz")
    parser.add_argument("tweet_url", help="X/Twitter post URL")
    parser.add_argument("--out", default="airaa_results.csv", help="Output path (.csv or .json)")
    parser.add_argument(
        "--format",
        choices=["auto", "csv", "json"],
        default="auto",
        help="Output format. Default: auto (infer from --out extension, fallback to csv)",
    )
    parser.add_argument("--show-browser", action="store_true", help="Run Chromium in headed mode")
    args = parser.parse_args()

    print(f"Scanning paid.airaa.xyz for: {args.tweet_url}", file=sys.stderr)
    html = await fetch_results(args.tweet_url, headless=not args.show_browser)
    rows = parse_results(html)
    out = Path(args.out)
    fmt = _infer_format(out, args.format)
    if fmt == "json":
        write_json(rows, out, args.tweet_url)
    else:
        write_csv(rows, out)
    print(f"\nWrote {len(rows)} creators ({fmt.upper()}) → {out.resolve()}", file=sys.stderr)
    for r in rows[:5]:
        print(f"{r['handle']:20}  {r['followers']:>6}  {r['tier']:5}  likes={r['likes']:>4}  rts={r['rts']:>3}  views={r['views']:>6}")
    if len(rows) > 5:
        print(f"... +{len(rows) - 5} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
