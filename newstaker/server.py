"""HTTP-Server: JSON-API plus statische Auslieferung des Frontends.

Bewusst auf http.server aufgebaut - fuer einen persoenlichen Tracker im eigenen
WLAN reicht das, und es kommt ohne jede Fremdabhaengigkeit aus.
"""

from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import config, images, markets, pipeline, store, weather

# Jeder Thread bekommt seine eigene Verbindung - sqlite3-Verbindungen sind
# nicht threadsicher.
_local = threading.local()
# Ein Refresh darf nicht mehrfach parallel laufen.
_refresh_lock = threading.Lock()


def _conn():
    if getattr(_local, "conn", None) is None:
        _local.conn = store.connect()
    return _local.conn


class Handler(BaseHTTPRequestHandler):
    server_version = "NewsTaker"
    protocol_version = "HTTP/1.1"

    # ----------------------------------------------------------- Helfer

    def _send(self, status: int, body: bytes, content_type: str, *, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def log_message(self, fmt: str, *args) -> None:  # ruhiger Server
        return

    # ----------------------------------------------------------- Routen

    def do_GET(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)

        try:
            if path == "/api/board":
                self._json(
                    pipeline.build_board(
                        _conn(),
                        topic=_one(query, "topic"),
                        hide_read=_one(query, "hide_read") in ("1", "true"),
                        cluster_id=_one(query, "cluster"),
                    )
                )
            elif path == "/api/cluster":
                cid = _one(query, "id")
                if not cid:
                    return self._error(400, "id fehlt")
                members = store.cluster_members(_conn(), cid)
                self._json(
                    {
                        "id": cid,
                        "members": [
                            {
                                "id": m["id"],
                                "title": m["title"],
                                "teaser": m["teaser"],
                                "url": m["canonical_url"],
                                "source": m["source_name"],
                                "image": m["image_url"],
                            }
                            for m in members
                        ],
                    }
                )
            elif path == "/api/search":
                self._json(
                    {
                        "query": _one(query, "q"),
                        "results": pipeline.search(
                            _conn(),
                            _one(query, "q"),
                            saved_only=_one(query, "saved") in ("1", "true"),
                        ),
                    }
                )
            elif path == "/api/weather":
                self._json(weather.board_payload(_conn(), _one(query, "city") or config.DEFAULT_CITY))
            elif path == "/api/markets":
                self._json(markets.board_payload(_conn()))
            elif path == "/api/health":
                conn = _conn()
                self._json(
                    {
                        "ok": True,
                        "lastFetchAt": store.get_meta(conn, "last_fetch_at", ""),
                        "items": conn.execute("SELECT COUNT(*) c FROM item").fetchone()["c"],
                        "clusters": conn.execute("SELECT COUNT(*) c FROM cluster").fetchone()["c"],
                    }
                )
            elif path.startswith("/tile/") and path.endswith(".svg"):
                self._serve_tile(path, query)
            else:
                self._serve_static(path)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - der Server soll nicht sterben
            self._error(500, f"{type(exc).__name__}: {exc}")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return self._error(400, "ungueltiges JSON")

            if path == "/api/state":
                item_id = payload.get("id") or ""
                field = payload.get("field") or ""
                value = bool(payload.get("value"))
                if not item_id or field not in ("read", "saved"):
                    return self._error(400, "id oder field fehlt")
                conn = _conn()
                exists = conn.execute("SELECT 1 FROM item WHERE id=?", (item_id,)).fetchone()
                if not exists:
                    return self._error(404, "unbekannte Meldung")
                store.set_state(conn, item_id, field, value)
                conn.commit()
                read_count, saved_count = store.state_counts(conn)
                self._json({"ok": True, "read": read_count, "saved": saved_count})

            elif path == "/api/refresh":
                if not _refresh_lock.acquire(blocking=False):
                    return self._error(409, "Abruf laeuft bereits")
                try:
                    result = pipeline.refresh(_conn(), image_budget=25)
                    self._json({"ok": True, "result": _shrink(result)})
                finally:
                    _refresh_lock.release()
            else:
                self._error(404, "unbekannte Route")
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001
            self._error(500, f"{type(exc).__name__}: {exc}")

    # ----------------------------------------------------------- Ausgabe

    def _serve_tile(self, path: str, query: dict) -> None:
        item_id = path[len("/tile/") : -len(".svg")]
        if not item_id.isalnum():
            return self._error(400, "ungueltige Kachel")
        svg = images.render_tile(
            item_id,
            _one(query, "s") or "News",
            _one(query, "t") or "",
        )
        # Kacheln sind aus der id abgeleitet und aendern sich nie.
        self._send(
            200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8",
            cache="public, max-age=604800",
        )

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (config.WEB_DIR / rel).resolve()
        # Kein Ausbruch aus dem web-Verzeichnis.
        if not str(target).startswith(str(config.WEB_DIR.resolve())) or not target.is_file():
            return self._error(404, "nicht gefunden")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype, cache="no-cache")


def _one(query: dict, key: str) -> str:
    values = query.get(key) or []
    return values[0].strip() if values else ""


def _shrink(result: dict) -> dict:
    """Refresh-Ergebnis ohne die lange Fehlerliste."""
    feeds = dict(result.get("feeds", {}))
    failures = feeds.pop("failures", [])
    return {
        "feeds": feeds,
        "failed": len(failures),
        "images": result.get("images"),
        "clusters": result.get("clusters"),
    }


def serve(host: str | None = None, port: int | None = None) -> None:
    host = host or config.HOST
    port = port or config.PORT
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    shown = "localhost" if host in ("0.0.0.0", "") else host
    print(f"News-Taker laeuft auf http://{shown}:{port}")
    if host == "0.0.0.0":
        print(f"Im WLAN erreichbar unter http://{_lan_ip()}:{port}")
    print("Beenden mit Strg-C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    finally:
        httpd.server_close()


def _lan_ip() -> str:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Es wird nichts gesendet; das Ziel bestimmt nur das Interface.
        sock.connect(("192.168.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()
