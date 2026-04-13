# Spotify for Artists — Playlist Streams Scraper

Scrapes playlist stream counts from [Spotify for Artists](https://artists.spotify.com) using Playwright browser automation. Built to track how songs perform across specific playlists over different time windows (7 days, 28 days, 12 months).

## How It Works

The scraper logs into Spotify for Artists with a saved browser session, navigates to each song's playlist page, and pulls stream numbers from the UI. It can either output raw CSV or fill in an existing `.xlsx` spreadsheet — writing results incrementally so progress isn't lost if something breaks mid-run.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

**Requirements:** Python 3.10+, Chromium (installed via Playwright).

## Authentication

First run requires a manual login — the scraper opens a browser window and waits for you to sign in:

```bash
python3 scraper.py --login
```

This saves your session to `.auth_state.json` (gitignored). Subsequent runs reuse it automatically. Re-run with `--login` if your session expires.

## Usage

### Spreadsheet Mode

Reads song rows from an `.xlsx` file, scrapes missing data, and writes results back in-place. Only fills empty cells — existing data is left untouched. A `.backup` copy is created before any writes.

```bash
# Default sheet name: "March 2026"
python3 scraper.py --xlsx "Playlist performance Overview March.xlsx"

# Specify a different sheet
python3 scraper.py --xlsx "Playlist performance Overview March.xlsx" --sheet "April 2026"

# Force re-login + scrape
python3 scraper.py --login --xlsx "Playlist performance Overview March.xlsx"
```

**Expected spreadsheet layout:**

| | A | B | C | D | E | F | G | H | I | J | K | L | M | N |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **1** | | | Mainstage | | | Essentials | | | Guest List | | | Soave | | |
| **2** | Artist | Song | 7d | 28d | 12mo | 7d | 28d | 12mo | 7d | 28d | 12mo | 7d | 28d | 12mo |
| **3** | John Summit | Silence | | | | | | | | | | | | |

Data rows start at row 3. Column A = artist name, column B = song title.

### Standalone Mode

Pass Spotify URLs or track IDs directly. Results go to `playlist_streams.csv`.

```bash
# Single track URL
python3 scraper.py https://artists.spotify.com/c/artist/ABC123/song/XYZ789/playlists

# Multiple track IDs
python3 scraper.py 2OP7UAuQF1OJbjeYXa5fhm 4iV5W9uYEdYUVa79Axb7Rh

# From a file (one URL/ID per line, # comments supported)
python3 scraper.py --file songs.txt

# Custom output path
python3 scraper.py --file songs.txt -o results.csv
```

## Tracked Playlists

The scraper targets these Tomorrowland playlists (mapped to spreadsheet column names):

| Spreadsheet Column | Spotify Playlist Name |
|---|---|
| Mainstage | Tomorrowland MainStage 2026 |
| Essentials | Tomorrowland Essentials |
| Guest List | Tomorrowland Guest List |
| Soave | Tomorrowland 2026 Playlist |

To track different playlists, edit `PLAYLIST_MAP` and `PLAYLIST_COLUMNS` in `scraper.py`.

## CLI Reference

```
python3 scraper.py [OPTIONS] [SONGS...]

positional arguments:
  SONGS                  Spotify track URLs or IDs (standalone mode)

options:
  --xlsx PATH            .xlsx file to read from and write to
  --sheet NAME           Sheet name (default: "March 2026")
  --file, -f PATH        Text file with one URL/ID per line
  --output, -o PATH      Output CSV path (default: playlist_streams.csv)
  --login                Force browser login (re-save session)
```

## Notes

- Runs in **headed** mode (visible browser) — Spotify for Artists requires it.
- The scraper auto-switches between artists if your account manages multiple.
- Session tokens expire periodically — re-run with `--login` when scrapes start failing.
- Spreadsheet mode creates a `.backup` file on first run as a safety net.
