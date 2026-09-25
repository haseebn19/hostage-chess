"""HTTP checks for the assets required by the installed game."""

from http.client import HTTPConnection

import pytest


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
def test_game_assets_are_served(server, path, content_type):
    connection = HTTPConnection(*server, timeout=5)
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
def test_invalid_asset_paths_are_rejected(server, path, status):
    connection = HTTPConnection(*server, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == status
        response.read()
    finally:
        connection.close()
