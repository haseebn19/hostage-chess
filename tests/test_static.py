"""HTTP checks for the assets required by the installed game."""

from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread

import pytest

from hostage_chess.server.app import RequestHandler


@pytest.fixture
def asset_server():
    server = HTTPServer(("127.0.0.1", 0), RequestHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("css/style.css", "text/css"),
        ("js/game.js", "application/javascript"),
        ("img/Chess_Pieces_Sprite.svg", "image/svg+xml"),
        ("vendor/jquery-3.4.1.min.js", "application/javascript"),
        ("vendor/chessboard-1.0.0.js", "application/javascript"),
        ("vendor/chessboard-1.0.0.css", "text/css"),
    ],
)
def test_game_assets_are_served(asset_server, path, content_type):
    connection = HTTPConnection(*asset_server, timeout=5)
    try:
        connection.request("GET", f"/static/{path}")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == content_type
        assert response.read()
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("path", "status"),
    [("/static/missing.css", 404), ("/static/../server/app.py", 403)],
)
def test_invalid_asset_paths_are_rejected(asset_server, path, status):
    connection = HTTPConnection(*asset_server, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == status
        response.read()
    finally:
        connection.close()
