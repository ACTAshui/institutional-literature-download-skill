---
name: institutional-literature-download
description: Download academic papers and full-text PDFs through authorized institutional browser access. Use when the user has legitimate access via a university, library, company, VPN, proxy, Shibboleth/OpenAthens/SSO, Web of Science, ScienceDirect, Elsevier, Springer, Wiley, IEEE, ACM, PubMed, DOI pages, or journal websites, and asks Codex to guide browser login, wait for manual CAPTCHA/2FA/verification, then automate article navigation, PDF downloads, filename cleanup, and manifest creation. Do not use for bypassing paywalls, defeating anti-bot systems, scraping without permission, credential handling, or downloading content the user is not authorized to access.
---

# Institutional Literature Download

## Principles

Use a visible browser and keep the user in control of authentication. The user must manually complete institutional login, CAPTCHA, robot checks, 2FA, consent pages, and any publisher verification. After access is granted, automate only ordinary browser actions the user could perform: opening authorized article pages, clicking PDF/full-text buttons, saving files, and recording results.

Never ask for passwords, tokens, cookies, or session exports. Never attempt to solve or bypass CAPTCHA, rate limits, paywalls, DRM, robots blocks, or access controls. Stop and ask the user to intervene when a site presents a login, verification, license warning, access denied page, or unusual anti-automation flow.

## Workflow

1. Clarify the source list and access path:
   - Accept DOI, PMID, title list, article URLs, Web of Science records, ScienceDirect pages, publisher pages, or a local text/CSV file.
   - Ask whether the institution requires VPN/proxy or library SSO if the route is not clear.
   - Confirm the intended output folder and filename pattern when the user cares about organization.

2. Start a visible persistent browser session:
   - Prefer the bundled helper `scripts/lit_browser_session.py` for repeated downloads.
   - Use a profile directory under the task workspace or a user-approved path so login survives within the session.
   - If the user already has a working browser session, prefer attaching to a Chrome session started with `--remote-debugging-port` via `--cdp-url`; otherwise use `--browser-channel chrome` before falling back to bundled Chromium.
   - Open the institution/library login URL or the first target page.

3. Guide manual verification:
   - Tell the user exactly what to do in the browser: choose institution, sign in, approve 2FA, complete CAPTCHA/robot verification, and reach a page showing institutional access.
   - Wait for the user to confirm before continuing. Do not collect credentials in chat.

4. Automate authorized retrieval:
   - Run a legal resolver pass before browser work when DOI/PMID/arXiv IDs are available: arXiv/PMC/native public PDFs, Unpaywall/OpenAlex/Crossref metadata, then publisher/institutional pages.
   - Visit each target URL or the resolved publisher landing page.
   - Prefer publisher-provided PDF/full-text buttons over constructing undocumented URLs.
   - Use page cookies/session state from the visible browser when fetching PDF links.
   - For ScienceDirect PDF-viewer or signed asset pages that reject background requests, first use CDP `Fetch` response-stage capture for the `pdf.sciencedirectassets.com` response, then fall back to an authorized browser-page `fetch(window.location.href)`; save only if the returned bytes start with `%PDF`.
   - Save only files that return PDF content or trigger a browser download.
   - Record successes, skipped pages, access-denied pages, provider errors, and manual-search-needed cases in a manifest.

5. Verify outputs:
   - Check that files exist, are non-empty, and start with `%PDF` when possible.
   - Report the download folder, counts, failed URLs, and next manual action needed.

## Helper Script

Use the helper when the user provides URLs or a URL file:

```powershell
python "C:\Users\lenovo\.codex\skills\institutional-literature-download\scripts\lit_browser_session.py" `
  --urls-file "C:\path\to\articles.txt" `
  --download-dir "C:\path\to\downloads" `
  --profile-dir "C:\path\to\browser-profile" `
  --manual-login-url "https://library.example.edu" `
  --pause-for-login
```

Attach to a user-controlled Chrome session when publisher automation profiles are fragile:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\path\to\chrome-debug-profile"

python "C:\Users\lenovo\.codex\skills\institutional-literature-download\scripts\lit_browser_session.py" `
  --urls-file "C:\path\to\articles.txt" `
  --download-dir "C:\path\to\downloads" `
  --profile-dir "C:\path\to\unused-profile" `
  --cdp-url "http://127.0.0.1:9222" `
  --pause-for-login
```

If Playwright is missing, install it in the active environment and install Chromium:

```powershell
python -m pip install playwright
python -m playwright install chromium
```

Useful options:

- `--url <URL>`: add one target URL; repeat for multiple URLs.
- `--urls-file <PATH>`: read one URL per line; blank lines and `#` comments are ignored.
- `--manual-login-url <URL>`: open the institutional login/library page before processing targets.
- `--pause-for-login`: pause until the user finishes login/verification and presses Enter.
- `--download-dir <PATH>`: save PDFs and `download_manifest.json`.
- `--profile-dir <PATH>`: store browser state for this authorized session.
- `--browser-channel chrome`: launch installed Google Chrome instead of bundled Chromium.
- `--cdp-url <URL>`: attach to a user-opened Chrome with remote debugging enabled.
- `--slow-mo 150`: slow visible automation if the site is fragile.

## Site Handling Notes

Read `references/site-notes.md` when a task involves a specific platform such as ScienceDirect, Web of Science, DOI resolver pages, or publisher sites. Use it for platform-specific cues and failure modes, not as permission to bypass site controls.

## User Guidance Template

When invoking this skill, guide the user like this:

```text
I opened a visible browser. Please complete your institution login, any CAPTCHA/robot check, and 2FA there. Do not paste credentials here. Once you can see that institutional access is active, return to Codex and say "logged in"; I will continue with the authorized downloads and summarize anything that still needs manual attention.
```
