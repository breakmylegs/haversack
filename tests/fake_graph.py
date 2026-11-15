"""A fake Microsoft Graph app folder on ``http.server`` for store contract tests.

Implements only what GraphStore uses, with the rules the Graph documentation
states: upload sessions with 320 KiB-multiple chunks, no Authorization header
on upload URLs, 409 ``nameAlreadyExists`` when the final chunk lands on a
taken name, 302 redirects for downloads, paginated children listings.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from keepsake import net
from keepsake.quickxor import reference as quickxor

BASE_PATH = "/v1.0/me/drive/special/approot"
CHUNK_UNIT = 320 * 1024


class FakeGraph:
    def __init__(
        self,
        auto_parents: bool = True,
        report_sha256: bool = False,
        wrong_quickxor: bool = False,
        wrong_sha256: bool = False,
    ):
        self.files: dict[str, bytes] = {}
        self.folders: set[str] = {""}
        self.sessions: dict[str, dict] = {}
        self.auto_parents = auto_parents
        self.report_sha256 = report_sha256
        self.wrong_quickxor = wrong_quickxor
        self.wrong_sha256 = wrong_sha256
        self.valid_tokens = {"good"}
        self.reject_next_token = 0
        self.throttle_next = 0
        self.page_size = 2
        self.log: list[tuple[str, str, bool]] = []  # method, path, had Authorization
        self.cancelled: list[str] = []
        self.lock = threading.Lock()
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.base_url = self.origin + BASE_PATH

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _add_parents(self, path: str) -> None:
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            self.folders.add("/".join(parts[:i]))

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body=b"", headers=None, as_json=None):
                if as_json is not None:
                    body = json.dumps(as_json).encode()
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _body(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                return self.rfile.read(length) if length else b""

            def _authorised(self):
                auth = self.headers.get("Authorization", "")
                if fake.reject_next_token:
                    fake.reject_next_token -= 1
                    return False
                return auth.startswith("Bearer ") and auth[7:] in fake.valid_tokens

            def _route(self, method):
                parsed = urllib.parse.urlsplit(self.path)
                path = urllib.parse.unquote(parsed.path)
                fake.log.append((method, path, "Authorization" in self.headers))
                with fake.lock:
                    if fake.throttle_next and path.startswith(BASE_PATH):
                        fake.throttle_next -= 1
                        return self._send(429, headers={"Retry-After": "0"})
                    if path.startswith("/up/"):
                        return self._upload(method, path[4:])
                    if path.startswith("/download/"):
                        if "Authorization" in self.headers:
                            return self._send(403, as_json={"error": {"code": "tokenLeaked"}})
                        name = path[len("/download/") :]
                        if name not in fake.files:
                            return self._send(404)
                        return self._send(200, fake.files[name])
                    if not path.startswith(BASE_PATH):
                        return self._send(404)
                    if not self._authorised():
                        return self._send(401, as_json={"error": {"code": "InvalidAuthenticationToken"}})
                    return self._graph(method, path[len(BASE_PATH) :], parse_qs(parsed.query))

            def _graph(self, method, rest, query):
                if rest == "" and method == "GET":
                    return self._send(200, as_json={"name": "Keepsake", "id": "root"})
                m = re.fullmatch(r":/(.+?):/(content|createUploadSession|children)", rest) or re.fullmatch(
                    r"/(children)", rest
                )
                if m and m.lastindex == 1:
                    item, action = "", "children"
                elif m:
                    item, action = m.group(1), m.group(2)
                else:
                    plain = re.fullmatch(r":/(.+)", rest)
                    if plain and method == "DELETE":
                        name = plain.group(1)
                        if name in fake.files:
                            del fake.files[name]
                            return self._send(204)
                        return self._send(404)
                    return self._send(400)
                if action == "createUploadSession" and method == "POST":
                    payload = json.loads(self._body() or b"{}")
                    behaviour = payload.get("item", {}).get("@microsoft.graph.conflictBehavior", "fail")
                    parent = item.rsplit("/", 1)[0] if "/" in item else ""
                    if parent not in fake.folders and not fake.auto_parents:
                        return self._send(404, as_json={"error": {"code": "itemNotFound"}})
                    sid = str(len(fake.sessions) + 1)
                    fake.sessions[sid] = {"path": item, "data": bytearray(), "behaviour": behaviour}
                    return self._send(200, as_json={"uploadUrl": f"{fake.origin}/up/{sid}"})
                if action == "content" and method == "GET":
                    if item not in fake.files:
                        return self._send(404, as_json={"error": {"code": "itemNotFound"}})
                    return self._send(302, headers={"Location": f"{fake.origin}/download/{urllib.parse.quote(item)}"})
                if action == "children" and method == "GET":
                    return self._list(item, int(query.get("skip", "0")))
                if action == "children" and method == "POST":
                    payload = json.loads(self._body() or b"{}")
                    name = f"{item}/{payload['name']}" if item else payload["name"]
                    if name in fake.folders:
                        return self._send(409, as_json={"error": {"code": "nameAlreadyExists"}})
                    fake.folders.add(name)
                    return self._send(201, as_json={"name": payload["name"], "folder": {}})
                return self._send(400)

            def _list(self, folder, skip):
                if folder not in fake.folders:
                    return self._send(404, as_json={"error": {"code": "itemNotFound"}})
                prefix = f"{folder}/" if folder else ""
                children = []
                for sub in sorted(fake.folders):
                    if sub and sub.startswith(prefix) and "/" not in sub[len(prefix) :]:
                        children.append({"name": sub[len(prefix) :], "folder": {}})
                for name in sorted(fake.files):
                    if name.startswith(prefix) and "/" not in name[len(prefix) :]:
                        children.append({"name": name[len(prefix) :], "size": len(fake.files[name]), "file": {}})
                page = children[skip : skip + fake.page_size]
                body = {"value": page}
                if skip + fake.page_size < len(children):
                    target = f"{BASE_PATH}:/{folder}:/children" if folder else f"{BASE_PATH}/children"
                    body["@odata.nextLink"] = f"{fake.origin}{urllib.parse.quote(target)}?skip={skip + fake.page_size}"
                return self._send(200, as_json=body)

            def _upload(self, method, sid):
                if "Authorization" in self.headers:
                    return self._send(401, as_json={"error": {"code": "unauthenticated"}})
                session = fake.sessions.get(sid)
                if session is None:
                    return self._send(404)
                if method == "DELETE":
                    fake.cancelled.append(session["path"])
                    del fake.sessions[sid]
                    return self._send(204)
                chunk = self._body()
                start, end, total = map(
                    int, re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", self.headers["Content-Range"]).groups()
                )
                if start != len(session["data"]) or end - start + 1 != len(chunk):
                    return self._send(416)
                final = end + 1 == total
                if not final and len(chunk) % CHUNK_UNIT:
                    return self._send(400, as_json={"error": {"code": "invalidRange"}})
                session["data"] += chunk
                if not final:
                    return self._send(202, as_json={"nextExpectedRanges": [f"{end + 1}-"]})
                path = session["path"]
                if path in fake.files:
                    return self._send(409, as_json={"error": {"code": "nameAlreadyExists"}})
                if fake.auto_parents:
                    fake._add_parents(path)
                fake.files[path] = bytes(session["data"])
                del fake.sessions[sid]
                hashes = {"quickXorHash": "AAAA" if fake.wrong_quickxor else quickxor(fake.files[path])}
                if fake.report_sha256:
                    import hashlib

                    hashes["sha256Hash"] = (
                        "AB" * 32 if fake.wrong_sha256 else hashlib.sha256(fake.files[path]).hexdigest().upper()
                    )
                return self._send(
                    201, as_json={"name": path.rsplit("/", 1)[-1], "size": total, "file": {"hashes": hashes}}
                )

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

            def do_PUT(self):
                self._route("PUT")

            def do_DELETE(self):
                self._route("DELETE")

        return Handler


def parse_qs(query: str) -> dict[str, str]:
    return {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}


def http_transport(method, url, headers=None, body=None, dest=None, **_kwargs):
    """Plain-HTTP stand-in for ``net.request`` (tests only): same contract, no redirects."""
    req = urllib.request.Request(url, data=body, method=method, headers=dict(headers or {}))
    opener = urllib.request.build_opener(net._NoRedirect())
    try:
        with opener.open(req, timeout=10) as response:
            data = response.read()
            status = response.status
            response_headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        data = exc.read() if exc.fp else b""
        status = exc.code
        response_headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
    if dest is not None and status == 200:
        with open(dest, "wb") as out:
            out.write(data)
        data = b""
    return net.HttpResponse(status=status, headers=response_headers, body=data)


class FakeTokens:
    def __init__(self, fake: FakeGraph, token: str = "good"):
        self.fake = fake
        self.token = token
        self.refreshes = 0

    def access_token(self, force_refresh: bool = False) -> str:
        if force_refresh:
            self.refreshes += 1
            self.token = "good"
        return self.token
