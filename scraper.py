#!/usr/bin/env python3
"""
Spotify for Artists - Playlist Streams Scraper

Extracts stream counts for specific Tomorrowland playlists from Spotify for Artists.

Usage:
    python3 scraper.py <song_url_or_id> [song_url_or_id ...]
    python3 scraper.py --file songs.txt

Songs can be:
    - Spotify track URLs: https://open.spotify.com/track/2AUVVfU9CmmbWcudIAJ5vD
    - Spotify track IDs: 2AUVVfU9CmmbWcudIAJ5vD
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TARGET_PLAYLISTS = [
    "Tomorrowland 2026 Playlist 💙 EDM HITS",
    "Tomorrowland Guest List",
    "Tomorrowland Essentials",
    "Tomorrowland MainStage 2026",
]

AUTH_STATE_PATH = os.path.join(os.path.dirname(__file__), ".auth_state.json")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "playlist_streams.csv")


def parse_song_input(song_input: str) -> dict:
    """Extract track ID and optionally artist ID from a Spotify URL or plain ID.

    Returns dict with 'track_id' and optionally 'artist_id'.
    """
    song_input = song_input.strip()

    # artists.spotify.com URL: .../artist/{aid}/song/{tid}/playlists
    match = re.search(
        r"artists\.spotify\.com/c/artist/([a-zA-Z0-9]+)/song/([a-zA-Z0-9]+)",
        song_input,
    )
    if match:
        return {"artist_id": match.group(1), "track_id": match.group(2)}

    # open.spotify.com URL: /track/XXXXX?si=...
    match = re.search(r"track/([a-zA-Z0-9]{22})", song_input)
    if match:
        return {"track_id": match.group(1)}

    # Plain ID
    if re.match(r"^[a-zA-Z0-9]{22}$", song_input):
        return {"track_id": song_input}

    raise ValueError(f"Cannot extract track ID from: {song_input}")


def login_and_save_state(playwright):
    """Open browser for manual login, save auth state for reuse."""
    print("\n🔐 Opening browser for Spotify for Artists login...")
    print("   Log in manually, then press ENTER here when you're on the dashboard.\n")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://artists.spotify.com/c/artist/")

    input("   >> Press ENTER after you've logged in and see the dashboard... ")

    context.storage_state(path=AUTH_STATE_PATH)
    print("   Auth state saved. Future runs will reuse this session.\n")
    browser.close()


def scrape_song_playlists(page, track_id: str, artist_id: str) -> dict:
    """Navigate to a song's playlist page and extract stream data."""
    url = f"https://artists.spotify.com/c/artist/{artist_id}/song/{track_id}/playlists"
    print(f"\n   Navigating to playlist stats for track {track_id}...")
    page.goto(url, wait_until="networkidle", timeout=30000)
    time.sleep(3)  # let dynamic content load

    # Get the song title from the page
    song_title = "Unknown"
    try:
        title_el = page.query_selector("h1, [data-testid='song-title'], [class*='Title']")
        if title_el:
            song_title = title_el.inner_text().strip()
    except Exception:
        pass

    result = {
        "track_id": track_id,
        "song_title": song_title,
    }

    # Try to find playlist rows in the table/list
    # Spotify for Artists renders playlist data in a table-like structure
    for playlist_name in TARGET_PLAYLISTS:
        result[playlist_name] = None  # default: not found

    # Strategy 1: Look for playlist names in the page content and extract nearby numbers
    try:
        # Get all text content from playlist rows/items
        rows = page.query_selector_all(
            "tr, [role='row'], [class*='playlist'], [class*='Playlist'], "
            "[data-testid*='playlist'], li"
        )

        for row in rows:
            row_text = row.inner_text()
            for playlist_name in TARGET_PLAYLISTS:
                if playlist_name.lower() in row_text.lower():
                    # Extract numbers (streams) from this row
                    numbers = re.findall(r"[\d,]+", row_text)
                    # Filter out very small numbers, take the largest as stream count
                    stream_counts = []
                    for n in numbers:
                        val = int(n.replace(",", ""))
                        if val > 0:
                            stream_counts.append(val)
                    if stream_counts:
                        result[playlist_name] = max(stream_counts)
                    else:
                        result[playlist_name] = 0
                    print(f"   ✓ Found '{playlist_name}': {result[playlist_name]:,} streams")
    except Exception as e:
        print(f"   ⚠ Strategy 1 failed: {e}")

    # Strategy 2: Intercept API responses (fallback)
    unfound = [p for p in TARGET_PLAYLISTS if result[p] is None]
    if unfound:
        print(f"   Playlists not found on page: {unfound}")
        # Try scrolling to load more
        try:
            for _ in range(5):
                page.mouse.wheel(0, 500)
                time.sleep(1)

            rows = page.query_selector_all(
                "tr, [role='row'], [class*='playlist'], [class*='Playlist'], li"
            )
            for row in rows:
                row_text = row.inner_text()
                for playlist_name in unfound:
                    if playlist_name.lower() in row_text.lower() and result[playlist_name] is None:
                        numbers = re.findall(r"[\d,]+", row_text)
                        stream_counts = [int(n.replace(",", "")) for n in numbers if int(n.replace(",", "")) > 0]
                        if stream_counts:
                            result[playlist_name] = max(stream_counts)
                        else:
                            result[playlist_name] = 0
                        print(f"   ✓ Found '{playlist_name}': {result[playlist_name]:,} streams")
        except Exception as e:
            print(f"   ⚠ Strategy 2 failed: {e}")

    return result


def detect_artist_id(page) -> str:
    """Extract the artist ID from the current URL after login."""
    url = page.url
    match = re.search(r"/artist/([a-zA-Z0-9]+)", url)
    if match:
        return match.group(1)
    # Navigate to home to find it
    page.goto("https://artists.spotify.com/c/artist/", wait_until="networkidle")
    time.sleep(2)
    url = page.url
    match = re.search(r"/artist/([a-zA-Z0-9]+)", url)
    if match:
        return match.group(1)
    raise RuntimeError("Could not detect artist ID from URL. Are you logged in?")


def main():
    parser = argparse.ArgumentParser(description="Scrape Spotify for Artists playlist streams")
    parser.add_argument("songs", nargs="*", help="Spotify track URLs or IDs")
    parser.add_argument("--file", "-f", help="Text file with one song URL/ID per line")
    parser.add_argument("--login", action="store_true", help="Force re-login")
    parser.add_argument("--output", "-o", default=OUTPUT_CSV, help="Output CSV path")
    args = parser.parse_args()

    # Collect song inputs
    song_inputs = list(args.songs)
    if args.file:
        with open(args.file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    song_inputs.append(line)

    if not song_inputs and not args.login:
        parser.print_help()
        print("\nExample:")
        print("  python3 scraper.py https://open.spotify.com/track/2AUVVfU9CmmbWcudIAJ5vD")
        print("  python3 scraper.py --file songs.txt")
        sys.exit(1)

    # Parse song inputs
    parsed_songs = []
    for s in song_inputs:
        try:
            parsed_songs.append(parse_song_input(s))
        except ValueError as e:
            print(f"⚠ Skipping: {e}")

    with sync_playwright() as pw:
        # Login if needed
        if args.login or not os.path.exists(AUTH_STATE_PATH):
            login_and_save_state(pw)

        if not parsed_songs:
            print("No tracks to process.")
            sys.exit(0)

        # Launch browser with saved auth
        print("🚀 Launching browser with saved session...")
        browser = pw.chromium.launch(headless=False)  # visible so you can debug
        context = browser.new_context(storage_state=AUTH_STATE_PATH)
        page = context.new_page()

        # Detect artist ID (use from URL if provided, otherwise auto-detect)
        default_artist_id = None
        for p in parsed_songs:
            if "artist_id" in p:
                default_artist_id = p["artist_id"]
                break
        if not default_artist_id:
            default_artist_id = detect_artist_id(page)
        print(f"   Artist ID: {default_artist_id}")

        # Scrape each song
        all_results = []
        for i, song in enumerate(parsed_songs, 1):
            track_id = song["track_id"]
            artist_id = song.get("artist_id", default_artist_id)
            print(f"\n{'='*60}")
            print(f"[{i}/{len(parsed_songs)}] Processing track: {track_id}")
            try:
                result = scrape_song_playlists(page, track_id, artist_id)
                all_results.append(result)
            except Exception as e:
                print(f"   ❌ Error: {e}")
                all_results.append({
                    "track_id": track_id,
                    "song_title": "ERROR",
                    **{p: None for p in TARGET_PLAYLISTS},
                })

        browser.close()

        # Write CSV
        print(f"\n{'='*60}")
        print(f"📄 Writing results to {args.output}")
        fieldnames = ["track_id", "song_title"] + TARGET_PLAYLISTS
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in all_results:
                writer.writerow(r)

        # Print summary table
        print(f"\n{'Song':<40} ", end="")
        for p in TARGET_PLAYLISTS:
            short = p[:20]
            print(f"{short:<22} ", end="")
        print()
        print("-" * (40 + 23 * len(TARGET_PLAYLISTS)))
        for r in all_results:
            print(f"{r['song_title']:<40} ", end="")
            for p in TARGET_PLAYLISTS:
                val = r[p]
                display = f"{val:,}" if val is not None else "—"
                print(f"{display:<22} ", end="")
            print()

        print(f"\n✅ Done! Results saved to {args.output}")


if __name__ == "__main__":
    main()
