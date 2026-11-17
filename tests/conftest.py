"""Shared test helpers. No network access is used anywhere in the suite."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pokego.schema import AccountFacts, AccountScan, Evidence, PokemonEntry


def make_scan(pokemon=(), **facts) -> AccountScan:
    """Build a scan from a facts dict and an iterable of Pokémon entries."""
    scan = AccountScan(facts=AccountFacts(**facts))
    for entry in pokemon:
        scan.add_pokemon(entry)
    return scan


@pytest.fixture
def stacked_scan() -> AccountScan:
    return make_scan(
        [
            PokemonEntry("Mewtwo", cp=4700, iv_percent=100, shiny=True,
                         legendary=True, background="Special", evidence=Evidence.VERIFIED),
            PokemonEntry("Rayquaza", cp=4300, shiny=True, legendary=True,
                         legacy_move="Dragon Ascent", evidence=Evidence.VERIFIED),
            PokemonEntry("Mew", cp=1800, mythical=True, shiny=True,
                         evidence=Evidence.VERIFIED),
            PokemonEntry("Zacian", cp=4100, legendary=True, evidence=Evidence.VERIFIED),
            PokemonEntry("Pikachu", cp=900, shiny=True, costume="Party Hat",
                         evidence=Evidence.VERIFIED),
            PokemonEntry("Nihilego", cp=3900, ultra_beast=True, evidence=Evidence.VERIFIED),
            PokemonEntry("Kangaskhan", cp=2200, regional=True, evidence=Evidence.VERIFIED),
            PokemonEntry("Machop", cp=1500, shadow=True, evidence=Evidence.VERIFIED),
        ],
        level=62, xp=210_000_000, team="Mystic", total_caught=180_000,
        pokedex_caught=740, pokedex_seen=790, stardust=28_000_000, pokecoins=12_000,
        rare_candy=900, rare_candy_xl=420, medals=["Gold Fisherman"] * 30,
        evidence=Evidence.VERIFIED,
    )


@pytest.fixture
def mini_scan() -> AccountScan:
    return make_scan(
        [PokemonEntry("Pidgey", cp=300), PokemonEntry("Rattata", cp=250)],
        level=12, total_caught=400, pokedex_caught=45, stardust=20_000,
        evidence=Evidence.VERIFIED,
    )


class _MockGemini:
    """A tiny stand-in for the Gemini HTTP API.

    It answers the ``interactions`` endpoint: an image-bearing request gets the
    scan JSON, anything else gets the narrative text.
    """

    def __init__(self, scan: dict, narrative: str = "FINAL DESCRIPTION\nMock narrative."):
        self.scan = scan
        self.narrative = narrative
        self.requests: list[dict] = []
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> "_MockGemini":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the test output clean
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"path": self.path, "body": body})
                has_image = any(
                    part.get("type") == "image" for part in body.get("input", [])
                )
                text = json.dumps(outer.scan) if has_image else outer.narrative
                payload = json.dumps({"output_text": text}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


@pytest.fixture
def mock_gemini():
    servers: list[_MockGemini] = []

    def factory(scan: dict, narrative: str = "FINAL DESCRIPTION\nMock narrative."):
        server = _MockGemini(scan, narrative).start()
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.stop()
