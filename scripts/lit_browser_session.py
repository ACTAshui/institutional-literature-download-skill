#!/usr/bin/env python3
"""Download authorized article PDFs through a visible Playwright browser session."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse


PDF_LINK_HINTS = (
    "pdf",
    "download pdf",
    "view pdf",
    "article pdf",
    "full text pdf",
)

STOP_TEXT_PATTERNS = (
    "verify you are human",
    "captcha",
    "robot",
    "access denied",
    "purchase access",
    "rent this article",
    "get access",
    "sign in through your institution",
    "institutional login",
    "openathens",
    "shibboleth",
    "there was a problem providing the content you requested",
    "cpe00001",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open a visible persistent browser, wait for manual institutional login "
            "when requested, then download PDFs from authorized article URLs."
        )
    )
    parser.add_argument("--url", action="append", default=[], help="Target article URL; repeatable.")
    parser.add_argument("--urls-file", help="Text file with one target URL per line.")
    parser.add_argument("--manual-login-url", help="Institution/library/login URL to open before targets.")
    parser.add_argument("--pause-for-login", action="store_true", help="Wait for manual login and verification.")
    parser.add_argument("--download-dir", required=True, help="Directory where PDFs and manifest are saved.")
    parser.add_argument("--profile-dir", required=True, help="Persistent browser profile directory.")
    parser.add_argument("--cdp-url", help="Attach to Chrome started by the user with --remote-debugging-port, e.g. http://127.0.0.1:9222.")
    parser.add_argument("--browser-channel", help="Optional Playwright browser channel such as chrome.")
    parser.add_argument("--headless", action="store_true", help="Run headless; not recommended for login.")
    parser.add_argument("--slow-mo", type=int, default=100, help="Playwright slow_mo milliseconds.")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="Navigation and action timeout.")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of target URLs.")
    return parser.parse_args()


def read_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.url or [])
    if args.urls_file:
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                urls.append(stripped)
    if args.limit:
        urls = urls[: args.limit]
    return urls


def safe_name(value: str, fallback: str) -> str:
    value = unquote(value).strip()
    value = re.sub(r"https?://", "", value, flags=re.I)
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._-")
    if not value:
        value = fallback
    return value[:140]


def filename_for(url: str, index: int, title: str | None = None) -> str:
    if title:
        base = safe_name(title, f"article_{index:03d}")
    else:
        parsed = urlparse(url)
        base = safe_name(parsed.path or parsed.netloc, f"article_{index:03d}")
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return f"{index:03d}_{base}"


def page_has_stop_text(page) -> str | None:
    try:
        body = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        return None
    for pattern in STOP_TEXT_PATTERNS:
        if pattern in body:
            return pattern
    return None


def collect_pdf_candidates(page) -> list[dict[str, str]]:
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    anchors = page.locator("a, link, meta").evaluate_all(
        """els => els.map(a => ({
            href: a.href || a.content || a.getAttribute("href") || "",
            text: (
                a.innerText ||
                a.getAttribute("aria-label") ||
                a.getAttribute("title") ||
                a.getAttribute("name") ||
                a.getAttribute("property") ||
                a.getAttribute("data-aa-name") ||
                a.getAttribute("rel") ||
                ""
            ).trim()
        }))"""
    )
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in anchors:
        href = item.get("href", "")
        text = item.get("text", "")
        haystack = f"{href} {text}".lower()
        if href and (any(hint in haystack for hint in PDF_LINK_HINTS) or "citation_pdf_url" in haystack) and href not in seen:
            seen.add(href)
            candidates.append({"href": href, "text": text})
    return candidates


def science_direct_article_url(value: str) -> str:
    m = re.search(r"/pii/([A-Za-z0-9]+)", value or "")
    if not m:
        return ""
    return f"https://www.sciencedirect.com/science/article/pii/{m.group(1)}"


def science_direct_pdf_candidates(value: str) -> list[str]:
    article_url = science_direct_article_url(value)
    if not article_url:
        return []
    return [article_url + "/pdfft?isDTMRedir=true&download=true"]


def arxiv_pdf_candidate(value: str) -> str:
    m = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?", value or "", flags=re.I)
    return f"https://arxiv.org/pdf/{m.group(1)}.pdf" if m else ""


def save_response_pdf(response, output_path: Path) -> bool:
    content_type = (response.headers.get("content-type") or "").lower()
    body = response.body()
    if b"%PDF" not in body[:1024] and "pdf" not in content_type:
        return False
    output_path.write_bytes(body)
    return True


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def try_request_download(context, candidate_url: str, output_path: Path) -> tuple[bool, str]:
    try:
        response = context.request.get(candidate_url, timeout=45000)
        if not response.ok:
            return False, f"HTTP {response.status}"
        if save_response_pdf(response, output_path):
            return True, "saved authenticated PDF response"
        return False, "candidate did not return PDF content"
    except Exception as exc:
        return False, f"request failed: {exc}"


def try_browser_pdf_fetch(context, candidate_url: str, output_path: Path) -> tuple[bool, str]:
    """Open a PDF viewer URL and capture/fetch from inside that browser page.

    ScienceDirect may return 403 to background API requests while the same
    authorized Chrome page can load the signed PDF asset. Prefer CDP Fetch
    response capture so Chrome's PDF viewer wrapper cannot hide the raw PDF.
    """
    pdf_page = context.new_page()
    session = None
    captured: dict[str, object] = {}
    try:
        if "sciencedirect.com" in candidate_url or "sciencedirectassets.com" in candidate_url:
            session = context.new_cdp_session(pdf_page)

            def handle_paused(event: dict) -> None:
                request_id = event.get("requestId")
                request = event.get("request") or {}
                url = request.get("url", "")
                try:
                    if event.get("responseStatusCode") and (
                        "pdf.sciencedirectassets.com" in url
                        or "/science/article/pii/" in url and "/pdfft" in url
                    ):
                        body = session.send("Fetch.getResponseBody", {"requestId": request_id})
                        raw = body.get("body", "")
                        data = base64.b64decode(raw) if body.get("base64Encoded") else raw.encode()
                        if b"%PDF" in data[:2048]:
                            captured["data"] = data
                            captured["url"] = url
                    session.send("Fetch.continueRequest", {"requestId": request_id})
                except Exception as exc:
                    captured.setdefault("error", str(exc))
                    try:
                        session.send("Fetch.continueRequest", {"requestId": request_id})
                    except Exception:
                        pass

            session.on("Fetch.requestPaused", handle_paused)
            session.send(
                "Fetch.enable",
                {
                    "patterns": [
                        {"urlPattern": "*pdf.sciencedirectassets.com*", "requestStage": "Response"},
                        {"urlPattern": "*sciencedirect.com/science/article/pii*/pdfft*", "requestStage": "Response"},
                    ]
                },
            )

        pdf_page.goto(candidate_url, wait_until="domcontentloaded", timeout=60000)
        try:
            pdf_page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        pdf_page.wait_for_timeout(2500)
        if captured.get("data"):
            output_path.write_bytes(captured["data"])
            return True, "saved PDF via CDP Fetch response capture"

        result = pdf_page.evaluate(
            """async () => {
                const response = await fetch(window.location.href, {credentials: "include", cache: "no-store"});
                const buffer = await response.arrayBuffer();
                return {
                    status: response.status,
                    contentType: response.headers.get("content-type") || "",
                    bytes: Array.from(new Uint8Array(buffer))
                };
            }"""
        )
        data = bytes(result.get("bytes") or [])
        content_type = result.get("contentType") or ""
        if result.get("status") and int(result["status"]) >= 400:
            return False, f"browser fetch HTTP {result['status']}"
        if b"%PDF" in data[:2048]:
            output_path.write_bytes(data)
            return True, "saved PDF via browser-page fetch"
        return False, f"browser fetch did not return PDF bytes: {content_type}"
    except Exception as exc:
        return False, f"browser fetch failed: {exc}"
    finally:
        try:
            if session:
                session.send("Fetch.disable")
        except Exception:
            pass
        try:
            pdf_page.close()
        except Exception:
            pass


def try_click_download(page, output_path: Path) -> tuple[bool, str]:
    locators = [
        page.get_by_role("link", name=re.compile(r"download\s+pdf|view\s+pdf|full\s+text\s+pdf|\bpdf\b", re.I)).first,
        page.get_by_role("button", name=re.compile(r"download\s+pdf|view\s+pdf|full\s+text\s+pdf|\bpdf\b", re.I)).first,
        page.get_by_text(re.compile(r"download\s+pdf|view\s+pdf|full\s+text\s+pdf", re.I)).first,
        page.locator("[aria-label*='PDF' i]").first,
        page.locator("[data-aa-name*='pdf' i]").first,
    ]
    for locator in locators:
        try:
            if locator.count() == 0:
                continue
            with page.expect_download(timeout=8000) as download_info:
                locator.click(timeout=8000)
            download = download_info.value
            download.save_as(str(output_path))
            return True, "saved browser download"
        except Exception:
            continue
    return False, "no clickable download completed"


def process_url(page, context, url: str, index: int, download_dir: Path) -> dict[str, str]:
    record = {"url": url, "status": "started", "file": "", "note": ""}
    try:
        public_pdf = arxiv_pdf_candidate(url)
        if public_pdf:
            output_path = unique_path(download_dir / filename_for(url, index))
            ok, note = try_request_download(context, public_pdf, output_path)
            if ok:
                record.update(status="downloaded", file=str(output_path), note=note, final_url=public_pdf)
                return record

        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(1500)
        article_url = science_direct_article_url(page.url)
        if article_url and urlparse(page.url).netloc == "linkinghub.elsevier.com":
            try:
                page.goto(article_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)
                record["final_url"] = page.url
            except Exception:
                record["final_url"] = article_url
        if response:
            content_type = (response.headers.get("content-type") or "").lower()
            if "pdf" in content_type:
                output_path = unique_path(download_dir / filename_for(url, index))
                if save_response_pdf(response, output_path):
                    record.update(status="downloaded", file=str(output_path), note="landing URL returned PDF")
                    return record

        stop_reason = page_has_stop_text(page)
        if stop_reason:
            record.update(status="needs_user", note=f"page contains stop text: {stop_reason}")
            return record

        title = None
        try:
            title = page.title()
        except Exception:
            pass

        output_path = unique_path(download_dir / filename_for(url, index, title))
        candidates = collect_pdf_candidates(page)
        for candidate in candidates:
            ok, note = try_request_download(context, candidate["href"], output_path)
            if ok:
                record.update(status="downloaded", file=str(output_path), note=note)
                return record
            if science_direct_article_url(candidate["href"]) or "pdf.sciencedirectassets.com" in candidate["href"]:
                ok, note = try_browser_pdf_fetch(context, candidate["href"], output_path)
                if ok:
                    record.update(status="downloaded", file=str(output_path), note=note)
                    return record

        for candidate_url in science_direct_pdf_candidates(page.url):
            ok, note = try_request_download(context, candidate_url, output_path)
            if ok:
                record.update(status="downloaded", file=str(output_path), note=f"{note}; ScienceDirect PII PDF endpoint")
                return record
            ok, note = try_browser_pdf_fetch(context, candidate_url, output_path)
            if ok:
                record.update(status="downloaded", file=str(output_path), note=f"{note}; ScienceDirect browser PDF endpoint")
                return record

        ok, note = try_click_download(page, output_path)
        if ok:
            record.update(status="downloaded", file=str(output_path), note=note)
            return record

        record.update(status="not_found", note="no accessible PDF link or browser download detected")
        return record
    except Exception as exc:
        record.update(status="error", note=str(exc))
        return record


def main() -> int:
    args = parse_args()
    urls = read_urls(args)
    download_dir = Path(args.download_dir).expanduser().resolve()
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    download_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    if not urls and not args.manual_login_url:
        print("Provide --url, --urls-file, or --manual-login-url.", file=sys.stderr)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run: python -m pip install playwright", file=sys.stderr)
        return 2

    manifest: list[dict[str, str]] = []
    with sync_playwright() as playwright:
        browser = None
        if args.cdp_url:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
        else:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=args.headless,
                accept_downloads=True,
                downloads_path=str(download_dir),
                slow_mo=args.slow_mo,
                channel=args.browser_channel or None,
            )
        context.set_default_timeout(args.timeout_ms)
        page = context.pages[0] if context.pages else context.new_page()

        if args.manual_login_url:
            page.goto(args.manual_login_url, wait_until="domcontentloaded", timeout=args.timeout_ms)

        if args.pause_for_login:
            print("\nComplete institutional login, CAPTCHA/robot checks, and 2FA in the browser.")
            print("Do not paste credentials into this terminal or chat.")
            input("Press Enter here after authorized access is active...")

        for index, url in enumerate(urls, start=1):
            print(f"[{index}/{len(urls)}] {url}")
            record = process_url(page, context, url, index, download_dir)
            manifest.append(record)
            print(f"  -> {record['status']}: {record.get('note', '')}")
            time.sleep(1)

        if not browser:
            context.close()

    manifest_path = download_dir / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    downloaded = sum(1 for item in manifest if item["status"] == "downloaded")
    print(f"\nDownloaded {downloaded}/{len(manifest)} PDFs.")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
