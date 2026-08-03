"""HTTP-Abruf.

Wichtig fuer diese Maschine: die python.org-Installation hat kein CA-Bundle
verdrahtet, `urllib.request` scheitert deshalb mit CERTIFICATE_VERIFY_FAILED.
`requests` bringt certifi mit und funktioniert. Der Fetch-Layer geht darum
konsequent ueber `requests` - siehe `_session()`.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

from . import config

_LAST_HIT: dict[str, float] = {}
_SESSION: requests.Session | None = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": config.USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
            }
        )
        _SESSION = s
    return _SESSION


def _be_polite(url: str) -> None:
    """Mindestabstand zwischen zwei Anfragen an denselben Host."""
    host = urlsplit(url).netloc
    last = _LAST_HIT.get(host)
    if last is not None:
        wait = config.HOST_DELAY_SECONDS - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _LAST_HIT[host] = time.monotonic()


@dataclass
class FetchResult:
    url: str
    status: int
    body: bytes = b""
    etag: str | None = None
    last_modified: str | None = None
    sha256: str = ""
    changed: bool = True
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and bool(self.body)

    @property
    def not_modified(self) -> bool:
        return self.status == 304


def fetch(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    known_sha: str | None = None,
    timeout: int | None = None,
) -> FetchResult:
    """Holt eine URL mit conditional GET, Retries und Content-Hash-Vergleich.

    Nicht alle Quellen liefern ETag oder Last-Modified (getestet: Guardian und
    Handelsblatt tun es, Tagesschau und BBC nicht). Deshalb zusaetzlich der
    Hash-Vergleich, damit unveraenderte Feeds nicht neu verarbeitet werden.
    """
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    timeout = timeout or config.FETCH_TIMEOUT
    last_error = ""

    for attempt in range(config.FETCH_RETRIES + 1):
        _be_polite(url)
        try:
            resp = _session().get(url, headers=headers, timeout=timeout, allow_redirects=True)
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < config.FETCH_RETRIES:
                time.sleep(config.FETCH_BACKOFF_SECONDS * (attempt + 1))
                continue
            return FetchResult(url=url, status=0, error=last_error, changed=False)

        if resp.status_code == 304:
            return FetchResult(
                url=url, status=304, etag=etag, last_modified=last_modified,
                sha256=known_sha or "", changed=False,
            )

        # 5xx sind oft transient, 4xx nicht - dort lohnt kein Retry.
        if resp.status_code >= 500 and attempt < config.FETCH_RETRIES:
            last_error = f"HTTP {resp.status_code}"
            time.sleep(config.FETCH_BACKOFF_SECONDS * (attempt + 1))
            continue

        body = resp.content or b""
        digest = hashlib.sha256(body).hexdigest()
        return FetchResult(
            url=url,
            status=resp.status_code,
            body=body,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            sha256=digest,
            changed=(digest != known_sha),
            error="" if resp.status_code == 200 else f"HTTP {resp.status_code}",
        )

    return FetchResult(url=url, status=0, error=last_error, changed=False)


def fetch_text(url: str, *, timeout: int | None = None, max_bytes: int = 250_000) -> str:
    """Holt eine HTML-Seite (fuer die og:image-Stufe). Bricht frueh ab.

    Der Kopfbereich reicht: og:image steht immer im <head>.
    """
    _be_polite(url)
    try:
        resp = _session().get(
            url,
            timeout=timeout or config.FETCH_TIMEOUT,
            allow_redirects=True,
            stream=True,
            headers={
                # Artikelseiten liefern Bot-UAs oft nichts aus.
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        if resp.status_code != 200:
            return ""
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(8192):
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                break
        resp.close()
        raw = b"".join(chunks)
        return raw.decode(resp.encoding or "utf-8", errors="replace")
    except requests.RequestException:
        return ""


def fetch_json(url: str, params: dict | None = None, *, timeout: int | None = None):
    _be_polite(url)
    try:
        resp = _session().get(url, params=params, timeout=timeout or config.FETCH_TIMEOUT)
        if resp.status_code != 200:
            return None
        return resp.json()
    except (requests.RequestException, ValueError):
        return None
