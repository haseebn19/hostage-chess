"""Shared fixtures: a test database, a server using it, and a way to set up positions."""

import json
import sqlite3
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from hostage_chess.server import database as db
from hostage_chess.server.app import RequestHandler


@pytest.fixture
def database(tmp_path, monkeypatch):
    """Point the database at a new file for the test, create its tables, and return its path."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    return path


@pytest.fixture
def server(database):  # noqa: ARG001 (the server stores its games in the test database)
    """Run the server on a free port with its own database and return its (host, port)."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


@pytest.fixture
def set_position(database):
    """Return a function that replaces the stored position of a turn.

    Prisons and airfields are empty unless given, for example `white_airfield=["N"]`.
    """

    def set_position(game_no, turn_no, fen, **hostages):
        hostage_state = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
            **hostages,
        }
        with sqlite3.connect(database) as conn:
            conn.execute(
                "UPDATE boards SET board_fen = ?, hostage_state = ? "
                "WHERE game_no = ? AND turn_no = ?",
                (fen, json.dumps(hostage_state), game_no, turn_no),
            )
        conn.close()

    return set_position
