# KaupBudget

Budget app that reads your receipts, learns your categories, and keeps each receipt with its purchase.

## Start it

- **Desktop:** double-click the **KaupBudget** icon on your desktop. If the icon is missing, right-click `create_desktop_shortcut.ps1` and choose *Run with PowerShell*.
- **Browser instead of a window:** `KaupBudget.bat --browser`
- **AWS EC2:**
  ```bash
  pip install -r requirements.txt
  export KAUP_PASSWORD='pick-a-strong-one'
  python run.py --server            # listens on port 8000
  ```
  Put it behind HTTPS (for example Caddy or an AWS load balancer) before you open it to the internet.

## First-time setup

1. **Settings → Receipt reader:** pick an AI and paste its API key.
   - Claude: get a key at console.anthropic.com
   - Gemini: get a key at aistudio.google.com
   - Ollama: install Ollama, then run `ollama pull qwen2.5vl`
2. **Settings → Import bank charges:** import a CSV exported from US Bank.
3. **Add receipt:** drop in a PDF or photo. Check the fields, pick a category, choose the matching bank charge, then click Save.

## Keeping secrets out of GitHub

API keys live in the app's database, outside this folder. Three checks make sure no key or private data gets pushed:

1. **Local check:** runs on every commit and every push, and blocks it if it finds a key, database file or receipt image. Turn it on once in each copy of the repo:
   ```bash
   git config core.hooksPath .githooks
   ```
2. **GitHub check:** `.github/workflows/secret-scan.yml` scans every push and pull request, including old commits.
3. **GitHub push protection:** on GitHub, go to *Settings → Code security* and turn on **Secret scanning** and **Push protection**. GitHub then rejects any push that contains a known key format.

If a key ever does reach GitHub, deleting it in a later commit isn't enough, because it stays in the history. Revoke it right away in the Anthropic or Google console and make a new one.

## How it works

| Piece | File |
|---|---|
| Server and API | `kaupbudget/server.py` |
| Swappable AI readers | `kaupbudget/extractors/` (claude, gemini, ollama) |
| Category learning (top 3 suggestions) | `kaupbudget/categorize.py` |
| Matching receipts to bank charges | `kaupbudget/matching.py` |
| Bank import (CSV now, live sync later) | `kaupbudget/bank/` |
| Reports | `kaupbudget/reports.py` |
| Screens | `kaupbudget/static/` |

- **Your data** (database and receipt JPEGs) lives in `%LOCALAPPDATA%\KaupBudget\data`, not in this folder. That keeps Google Drive from syncing the database while it's in use. Set the `KAUP_DATA_DIR` environment variable to store it somewhere else.
- **Category learning:** only categories you pick yourself are learned from. Categories filled in automatically show in grey with a `?` until you confirm them.
- **When a receipt and a bank charge differ:** the receipt wins (vendor, date, and the total including tip). The bank's original details are kept and shown in the purchase details.
