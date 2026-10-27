"""The surface over a real socket: routes, status codes, and /health.

Everything else tests the functions behind the routes. This starts the actual
server on an ephemeral port and talks HTTP to it, because the failures that
reach a browser live in the wiring: a route that was renamed and not
re-registered, a HEAD that answers 501, a probe that triggers a rebuild.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from tools.demo.__main__ import build_parser
from tools.demo.server import Build, _Server, make_handler


@pytest.fixture(scope="module")
def server():
    """A live server on a port the OS picks, with no scenarios built.

    `Build` is never started. The scripted page takes seconds to produce and
    none of the routes under test need it, so the suite checks what an
    unfinished build serves, which is also what a real first request sees.
    """
    args = build_parser().parse_args(["--no-open", "--port", "0"])
    httpd = _Server(("127.0.0.1", 0), make_handler(args, Build(args)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(base, path, method="GET"):
    request = urllib.request.Request(f"{base}{path}", method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read()


def test_health_answers_with_the_store_it_reached(server):
    status, body = get(server, "/health")
    report = json.loads(body)

    assert status == 200
    assert report["status"] in ("ok", "degraded")
    assert report["store"]["reachable"] is True
    assert report["store"]["backend"] in ("files", "postgres")
    assert "version" in report and "uptime_s" in report


def test_healthz_is_the_same_route(server):
    assert json.loads(get(server, "/healthz")[1])["version"] == \
           json.loads(get(server, "/health")[1])["version"]


def test_head_is_answered_rather_than_501(server):
    """Uptime monitors probe with HEAD, and a 501 reads as unhealthy."""
    status, body = get(server, "/health", method="HEAD")

    assert status == 200
    assert body == b""


def test_the_interactive_page_serves_without_a_build(server):
    status, body = get(server, "/clinic")

    assert status == 200
    assert b"<!doctype html>" in body.lower()


def test_the_site_registry_serves(server):
    status, body = get(server, "/sites")
    assert status == 200
    assert b"SITE-A" in body

    status, body = get(server, "/api/sites")
    assert status == 200
    assert [s["site_id"] for s in json.loads(body)["sites"]]


def test_the_vocabulary_comes_from_the_pack(server):
    payload = json.loads(get(server, "/api/vocabulary")[1])

    assert payload["molecules"], "the browser cannot build a patient without drugs"
    assert payload["checks"], "nor show which gate checks exist"


def test_an_unknown_path_is_404(server):
    assert get(server, "/nope")[0] == 404
    assert get(server, "/api/job?id=nothing")[0] == 404


def test_a_favicon_never_costs_a_rebuild(server):
    """It used to cost a full set of model calls, once per browser tab."""
    assert get(server, "/favicon.ico")[0] == 204


def test_a_run_with_no_patients_is_refused(server):
    request = urllib.request.Request(
        f"{server}/api/run", data=b'{"patients": []}', method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=20)

    with caught.value as refusal:
        assert refusal.code == 400
        assert "no patients" in json.loads(refusal.read())["error"]


def test_a_body_that_is_not_json_is_refused_by_name(server):
    request = urllib.request.Request(
        f"{server}/api/generate", data=b"not json at all", method="POST",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=20)

    with caught.value as refusal:
        assert refusal.code == 400
