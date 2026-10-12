"""Page watcher for official programme / funding pages (S04.05).

Fetches each watched page, reduces it to its meaningful plain text (scripts,
styles, nav, footer and similar chrome stripped; whitespace collapsed), hashes
that text and compares it with the hash from the previous run. A RawRecord is
emitted ONLY when the text changed (first sighting counts as a change), so the
Extractor agent reads new text and never re-reads an unchanged page.

Watch list: seeds/pagewatch.json, a list of {"id", "url", "track", "org", "kind"}.
State:      private/data/pagewatch/state.json (gitignored), {id: {"hash", "checked_at", "changed_at"}}.

Payload shape matches the ATS collectors ({board, title, location, offices,
content_html, departments, updated_at, first_published}) plus page_kind and track.
`content_html` holds PLAIN TEXT here (the shared normaliser strips tags anyway).

Fetched page text is data, never instructions (CLAUDE.md rule 3).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterator

import httpx

from future.collectors.base import SEEDS_DIR, CollectorReport, RawRecord, content_hash, fetch, polite_client

SOURCE = "pagewatch"
SEED_FILE = "pagewatch.json"
TRACKS = frozenset({"research", "ms", "funding"})
KINDS = frozenset({"programme", "scholarship", "accelerator", "fellowship", "grant"})
REQUIRED_KEYS = ("id", "url", "track", "org", "kind")

MAX_TEXT_CHARS = 12_000
MIN_TEXT_CHARS = 200          # less than this is almost always a JS shell or an error page
MAIN_MIN_CHARS = 200          # a <main> shorter than this is a stub; fall back to the whole body
PAGE_DEADLINE_S = 45.0
DEFAULT_DELAY_S = 2.0
RETRIES = 1                   # one retry on network error / 429 / 5xx
RETRY_BACKOFF_S = 3.0

# Elements whose whole subtree is chrome or code, never page content.
SKIP_TAGS = frozenset({"script", "style", "nav", "footer", "noscript", "template", "svg", "iframe"})
# Elements that end a line of text.
BLOCK_TAGS = frozenset({
    "p", "div", "section", "article", "main", "aside", "header", "br", "hr", "li", "ul", "ol", "dl", "dt", "dd",
    "table", "tr", "td", "th", "thead", "tbody", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
    "form", "fieldset", "figure", "figcaption", "details", "summary", "address",
})
_SPACES = re.compile(r"[ \t\f\v\r ​]+")


def default_state_path() -> Path:
    from future import config   # lazy: config loads .env on import
    return config.REPO_ROOT / "private" / "data" / "pagewatch" / "state.json"


# ---------------------------------------------------------------- HTML -> text

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []         # all visible text
        self.main_parts: list[str] = []    # visible text inside <main>
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._main_depth = 0
        self._in_title = False
        self._title_done = False   # only the FIRST <title> outside svg etc. is the page title

    def _emit(self, s: str) -> None:
        self.parts.append(s)
        if self._main_depth:
            self.main_parts.append(s)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title" and self._skip_depth == 0 and not self._title_done:
            self._in_title = True
        elif tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            if tag == "main":
                self._main_depth += 1
            self._emit("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag in BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title, self._title_done = False, True
        elif tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in BLOCK_TAGS:
            self._emit("\n")
            if tag == "main":
                self._main_depth = max(0, self._main_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif self._skip_depth == 0:
            self._emit(data)


def _clean_lines(parts: list[str]) -> str:
    lines = (_SPACES.sub(" ", ln).strip() for ln in "".join(parts).split("\n"))
    return "\n".join(ln for ln in lines if ln)


def html_to_text(html_doc: str) -> tuple[str, str]:
    """Return (title, text). Text keeps one line per block, spaces collapsed, blank lines dropped.

    When the page has a <main> with real content, only <main> is kept: sidebars, ad
    carousels and banners outside it rotate between requests and would fake changes."""
    parser = _TextExtractor()
    parser.feed(html_doc)
    parser.close()
    main_text = _clean_lines(parser.main_parts)
    text = main_text if len(main_text) >= MAIN_MIN_CHARS else _clean_lines(parser.parts)
    title = _SPACES.sub(" ", " ".join("".join(parser.title_parts).split())).strip()
    return title, text


def text_hash(text: str) -> str:
    """Hash of the text with ALL whitespace collapsed, so layout-only edits are not changes."""
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def decode_body(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1252", errors="replace")


# ---------------------------------------------------------------- seeds + state

def _validate_page(page: Any, index: int) -> dict[str, str]:
    if not isinstance(page, dict):
        raise ValueError(f"pagewatch seed #{index} is not an object")
    missing = [k for k in REQUIRED_KEYS if not str(page.get(k) or "").strip()]
    if missing:
        raise ValueError(f"pagewatch seed #{index} missing {missing}")
    if page["track"] not in TRACKS:
        raise ValueError(f"pagewatch seed {page['id']!r}: track {page['track']!r} not in {sorted(TRACKS)}")
    if page["kind"] not in KINDS:
        raise ValueError(f"pagewatch seed {page['id']!r}: kind {page['kind']!r} not in {sorted(KINDS)}")
    if not str(page["url"]).startswith(("https://", "http://")):
        raise ValueError(f"pagewatch seed {page['id']!r}: url must be http(s)")
    return {k: str(page[k]).strip() for k in REQUIRED_KEYS}


def validate_pages(pages: list[Any]) -> list[dict[str, str]]:
    clean = [_validate_page(p, i) for i, p in enumerate(pages)]
    ids = [p["id"] for p in clean]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"pagewatch seeds have duplicate ids: {dupes}")
    return clean


def load_pages(path: Path | None = None) -> list[dict[str, str]]:
    data = json.loads((path or SEEDS_DIR / SEED_FILE).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("pagewatch seed file must be a JSON list")
    return validate_pages(data)


def load_state(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"pagewatch state {path} is not a JSON object")
    return data


def save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    """Atomic write: a crash mid-save must not wipe every stored hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, sort_keys=True, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------- collector

class PageFetchError(Exception):
    pass


class PageWatchCollector:
    name = SOURCE

    def __init__(self, pages: list[dict[str, Any]] | None = None, client: httpx.Client | None = None,
                 state_path: Path | str | None = None, delay_s: float = DEFAULT_DELAY_S, sleep=time.sleep,
                 deadline_s: float = PAGE_DEADLINE_S, max_chars: int = MAX_TEXT_CHARS,
                 min_chars: int = MIN_TEXT_CHARS, now=lambda: dt.datetime.now(dt.timezone.utc)) -> None:
        self.pages = load_pages() if pages is None else validate_pages(pages)
        self._client = client or polite_client()
        self.state_path = Path(state_path) if state_path is not None else default_state_path()
        self._delay_s, self._sleep = delay_s, sleep
        self._deadline_s, self._max_chars, self._min_chars = deadline_s, max_chars, min_chars
        self._now = now
        self.report = CollectorReport(source=self.name)
        self.changed: list[str] = []

    def collect(self) -> Iterator[RawRecord]:
        state = load_state(self.state_path)
        for i, page in enumerate(self.pages):
            if i:
                self._sleep(self._delay_s)
            pid = page["id"]
            try:
                title, text = self._page_text(page["url"])
            except Exception as exc:  # one bad page must not stop the run; its old hash stays
                self.report.units_failed += 1
                self.report.errors.append(f"{pid}: {type(exc).__name__}: {str(exc)[:160]}")
                continue
            self.report.units_ok += 1
            self.report.ok_units.append(pid)
            digest = text_hash(text)
            stamp = self._now().isoformat(timespec="seconds")
            previous = state.get(pid) or {}
            changed = previous.get("hash") != digest
            entry = {"hash": digest, "checked_at": stamp,
                     "changed_at": stamp if changed else previous.get("changed_at")}
            state = {**state, pid: entry}
            if changed:
                self.changed.append(pid)
                self.report.records += 1
                yield self._record(page, title, text, digest)
            # Persist only after the consumer has taken the record, so an aborted run re-emits it.
            save_state(self.state_path, state)

    def _page_text(self, url: str) -> tuple[str, str]:
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            if attempt:
                self._sleep(RETRY_BACKOFF_S)
            try:
                status, body = fetch(self._client, url, self._deadline_s)
            except httpx.TransportError as exc:       # includes RequestDeadline
                last = exc
                continue
            if status == 429 or status >= 500:
                last = PageFetchError(f"HTTP {status}")
                continue
            if status >= 400:
                raise PageFetchError(f"HTTP {status}")
            title, text = html_to_text(decode_body(body))
            if len(text) < self._min_chars:
                raise PageFetchError(f"only {len(text)} chars of text (JS-rendered or empty page?)")
            return title, text
        raise last  # type: ignore[misc]

    def _record(self, page: dict[str, str], title: str, text: str, digest: str) -> RawRecord:
        pid = page["id"]
        payload = {
            "board": pid, "org": page["org"], "title": title or pid, "location": "", "offices": [],
            "content_html": text[: self._max_chars], "departments": [page["track"]],
            "updated_at": None, "first_published": None, "page_kind": page["kind"], "track": page["track"],
        }
        return RawRecord(source=SOURCE, external_id=pid, url=page["url"], payload=payload,
                         content_hash=content_hash(SOURCE, pid, {"text_sha256": digest}))
