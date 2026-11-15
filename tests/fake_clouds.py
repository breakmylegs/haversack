"""Fake WebDAV, S3 and Google Drive servers on ``http.server`` for the store contract tests.

Each implements only what Keepsake's store uses, with the rules the service
documents: WebDAV ``If-None-Match: *`` (412) and PROPFIND multistatus; S3
conditional PUT (412), payload hash checks, paginated ListObjectsV2 and 204 on
deleting a missing key; Drive's appDataFolder with duplicate names allowed,
server-assigned ``createdTime`` and ``sha256Checksum``. Every fake can be told to
ignore create-only headers, to prove Keepsake refuses such a server.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape


class _Server:
    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.lock = threading.Lock()
        self.ignore_create_only = False
        self.page_size = 2
        self.log: list[tuple[str, str]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, status, body=b"", headers=None):
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body and self.command != "HEAD":
                    self.wfile.write(body)

            def body(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                return self.rfile.read(length) if length else b""

            def handle_any(self):
                fake.log.append((self.command, self.path))
                fake.handle(self)

            do_GET = do_PUT = do_POST = do_DELETE = do_HEAD = do_MKCOL = do_PROPFIND = handle_any

        return Handler


class FakeWebDav(_Server):
    BASE = "/dav/"

    def __init__(self, username="user", password="secret"):
        self.folders = {""}
        self.expected = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        super().__init__()
        self.base_url = self.origin + self.BASE

    def handle(self, h):
        if h.headers.get("Authorization") != self.expected:
            return h.send(401)
        path = urllib.parse.unquote(urllib.parse.urlsplit(h.path).path)
        if not path.startswith(self.BASE):
            return h.send(404)
        rel = path[len(self.BASE) :]
        with self.lock:
            if h.command == "MKCOL":
                rel = rel.rstrip("/")
                if rel in self.folders:
                    return h.send(405)
                parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
                if parent not in self.folders:
                    return h.send(409)
                self.folders.add(rel)
                return h.send(201)
            if h.command == "PUT":
                data = h.body()
                parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
                if parent not in self.folders:
                    return h.send(409)
                if rel in self.files and h.headers.get("If-None-Match") == "*" and not self.ignore_create_only:
                    return h.send(412)
                existed = rel in self.files
                self.files[rel] = data
                return h.send(204 if existed else 201)
            if h.command == "GET":
                if rel not in self.files:
                    return h.send(404)
                return h.send(200, self.files[rel])
            if h.command == "DELETE":
                if rel not in self.files:
                    return h.send(404)
                del self.files[rel]
                return h.send(204)
            if h.command == "PROPFIND":
                h.body()
                folder = rel.rstrip("/")
                if folder not in self.folders:
                    return h.send(404)
                return h.send(207, self._multistatus(folder), {"Content-Type": "application/xml"})
        return h.send(405)

    def _multistatus(self, folder):
        prefix = f"{folder}/" if folder else ""

        def response(name, is_folder, size=0):
            href = urllib.parse.quote(self.BASE + name + ("/" if is_folder else ""))
            kind = "<d:resourcetype><d:collection/></d:resourcetype>" if is_folder else "<d:resourcetype/>"
            length = "" if is_folder else f"<d:getcontentlength>{size}</d:getcontentlength>"
            return (
                f"<d:response><d:href>{escape(href)}</d:href><d:propstat><d:prop>{kind}{length}"
                "</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
            )

        parts = [response(folder, True)]
        for sub in sorted(self.folders):
            if sub and sub.startswith(prefix) and "/" not in sub[len(prefix) :]:
                parts.append(response(sub, True))
        for name, data in sorted(self.files.items()):
            if name.startswith(prefix) and "/" not in name[len(prefix) :]:
                parts.append(response(name, False, len(data)))
        return ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + "".join(parts) + "</d:multistatus>").encode()


class FakeS3(_Server):
    BUCKET = "saves"
    NS = "http://s3.amazonaws.com/doc/2006-03-01/"

    def __init__(self):
        super().__init__()
        self.endpoint = self.origin

    def handle(self, h):
        auth = h.headers.get("Authorization", "")
        if not auth.startswith("AWS4-HMAC-SHA256 Credential=") or "x-amz-date" not in {k.lower() for k in h.headers}:
            return h.send(403)
        parsed = urllib.parse.urlsplit(h.path)
        path = urllib.parse.unquote(parsed.path)
        if not path.startswith(f"/{self.BUCKET}"):
            return h.send(404)
        key = path[len(self.BUCKET) + 2 :]
        with self.lock:
            if h.command == "GET" and not key:
                return self._list(urllib.parse.parse_qs(parsed.query), h)
            if h.command == "PUT":
                data = h.body()
                if hashlib.sha256(data).hexdigest() != h.headers.get("x-amz-content-sha256"):
                    return h.send(400, b"<Error><Code>XAmzContentSHA256Mismatch</Code></Error>")
                if key in self.files and h.headers.get("If-None-Match") == "*" and not self.ignore_create_only:
                    return h.send(412, b"<Error><Code>PreconditionFailed</Code></Error>")
                self.files[key] = data
                return h.send(200)
            if h.command in ("GET", "HEAD"):
                if key not in self.files:
                    return h.send(404, b"<Error><Code>NoSuchKey</Code></Error>")
                return h.send(200, self.files[key])
            if h.command == "DELETE":
                self.files.pop(key, None)
                return h.send(204)
        return h.send(405)

    def _list(self, query, h):
        prefix = query.get("prefix", [""])[0]
        start = int(query.get("continuation-token", ["0"])[0])
        names = [n for n in sorted(self.files) if n.startswith(prefix)]
        page = names[start : start + self.page_size]
        truncated = start + self.page_size < len(names)
        items = "".join(f"<Contents><Key>{escape(n)}</Key><Size>{len(self.files[n])}</Size></Contents>" for n in page)
        token = f"<NextContinuationToken>{start + self.page_size}</NextContinuationToken>" if truncated else ""
        body = (
            f'<?xml version="1.0"?><ListBucketResult xmlns="{self.NS}"><Name>{self.BUCKET}</Name>'
            f"<IsTruncated>{'true' if truncated else 'false'}</IsTruncated>{items}{token}</ListBucketResult>"
        )
        return h.send(200, body.encode(), {"Content-Type": "application/xml"})


class FakeDrive(_Server):
    def __init__(self):
        self.meta: dict[str, dict] = {}  # id -> {name, created}
        self.ids = itertools.count(1)
        self.clock = itertools.count(1)
        self.valid_tokens = {"good"}
        self.redirect_downloads = False
        self.before_create = None  # hook: another device's upload landing first
        super().__init__()
        self.api = self.origin + "/drive/v3"
        self.upload = self.origin + "/upload/drive/v3"

    def _file(self, file_id):
        m = self.meta[file_id]
        data = self.files[file_id]
        return {
            "id": file_id,
            "name": m["name"],
            "size": str(len(data)),
            "createdTime": f"2026-11-15T10:00:{m['created']:02d}.000Z",
            "sha256Checksum": hashlib.sha256(data).hexdigest(),
        }

    def handle(self, h):
        if h.headers.get("Authorization", "")[7:] not in self.valid_tokens:
            return h.send(401)
        parsed = urllib.parse.urlsplit(h.path)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        path = parsed.path
        with self.lock:
            if path == "/drive/v3/files" and h.command == "GET":
                if query.get("spaces") != "appDataFolder":
                    return h.send(403)
                match = re.search(r"name = '([^']*)'", query.get("q", ""))
                found = [
                    self._file(i)
                    for i in sorted(self.meta, key=int)
                    if not match or self.meta[i]["name"] == match.group(1)
                ]
                start = int(query.get("pageToken", "0"))
                size = min(int(query.get("pageSize", "100")), self.page_size)
                body = {"files": found[start : start + size]}
                if start + size < len(found):
                    body["nextPageToken"] = str(start + size)
                return h.send(200, json.dumps(body).encode())
            if path == "/upload/drive/v3/files" and h.command == "POST":
                boundary = h.headers["Content-Type"].split("boundary=")[1]
                parts = h.body().split(f"--{boundary}".encode())
                metadata = json.loads(parts[1].split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n"))
                content = parts[2].split(b"\r\n\r\n", 1)[1][:-2]
                if metadata.get("parents") != ["appDataFolder"]:
                    return h.send(403)
                if self.before_create:
                    hook, self.before_create = self.before_create, None
                    hook(metadata["name"])
                file_id = str(next(self.ids))
                self.meta[file_id] = {"name": metadata["name"], "created": next(self.clock)}
                self.files[file_id] = content
                return h.send(200, json.dumps(self._file(file_id)).encode())
            m = re.fullmatch(r"/drive/v3/files/(\d+)", path)
            if m and m.group(1) in self.meta:
                if h.command == "DELETE":
                    del self.meta[m.group(1)]
                    del self.files[m.group(1)]
                    return h.send(204)
                if h.command == "GET" and query.get("alt") == "media":
                    if self.redirect_downloads:
                        return h.send(302, headers={"Location": "https://elsewhere.example/x"})
                    return h.send(200, self.files[m.group(1)])
            if m:
                return h.send(404)
        return h.send(400)

    def names(self):
        return sorted(m["name"] for m in self.meta.values())


class FakeGoogleTokens:
    def __init__(self, token="good"):
        self.token = token
        self.refreshes = 0

    def access_token(self, force_refresh=False):
        if force_refresh:
            self.refreshes += 1
            self.token = "good"
        return self.token
