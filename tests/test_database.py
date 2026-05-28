"""Tests for src.server.database: SQLite operations."""

import pytest

from src.server.database import (
    create_game,
    find_waiting_game,
    get_black_handle,
    get_game_history,
    get_game_log,
    get_latest_turn_no,
    get_result,
    get_turn,
    init_db,
    join_game,
    save_turn,
    set_result,
)


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database for each test."""
    path = tmp_path / "test.db"
    init_db(path)
    return path


class TestInitDB:
    """Tests for database initialisation."""

    def test_init_creates_tables(self, db_path):
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        assert "games" in tables
        assert "boards" in tables

    def test_init_is_idempotent(self, db_path):
        # Should not error when called twice
        init_db(db_path)


class TestGameCreation:
    """Tests for game creation and matchmaking."""

    def test_create_game_returns_id(self, db_path):
        game_no = create_game("alice", db_path)
        assert game_no > 0

    def test_find_waiting_game(self, db_path):
        game_no = create_game("alice", db_path)
        found = find_waiting_game(db_path)
        assert found == game_no

    def test_no_waiting_game(self, db_path):
        assert find_waiting_game(db_path) is None

    def test_join_game(self, db_path):
        game_no = create_game("alice", db_path)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        hostage = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
        }
        join_game(game_no, "bob", fen, hostage, 300, db_path)
        assert get_black_handle(game_no, db_path) == "bob"

    def test_waiting_game_not_found_after_join(self, db_path):
        game_no = create_game("alice", db_path)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        hostage = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
        }
        join_game(game_no, "bob", fen, hostage, 300, db_path)
        assert find_waiting_game(db_path) is None


class TestTurnStorage:
    """Tests for storing and retrieving turns."""

    def test_get_turn_after_join(self, db_path):
        game_no = create_game("alice", db_path)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        hostage = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
        }
        join_game(game_no, "bob", fen, hostage, 300, db_path)

        turn = get_turn(game_no, 1, db_path)
        assert turn is not None
        assert turn["turn"] == "w"
        assert turn["board_fen"] == fen
        assert turn["white_time"] == 300

    def test_save_and_get_turn(self, db_path):
        game_no = create_game("alice", db_path)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        hostage = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
        }
        join_game(game_no, "bob", fen, hostage, 300, db_path)

        new_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        save_turn(game_no, 2, "b", new_fen, hostage, 295, 300, db_path)

        turn = get_turn(game_no, 2, db_path)
        assert turn["turn"] == "b"
        assert turn["board_fen"] == new_fen
        assert turn["white_time"] == 295

    def test_get_latest_turn_no(self, db_path):
        game_no = create_game("alice", db_path)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        hostage = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
        }
        join_game(game_no, "bob", fen, hostage, 300, db_path)
        save_turn(game_no, 2, "b", fen, hostage, 295, 300, db_path)

        assert get_latest_turn_no(game_no, db_path) == 2

    def test_get_turn_nonexistent(self, db_path):
        assert get_turn(999, 1, db_path) is None


class TestResults:
    """Tests for game result management."""

    def test_set_and_get_result(self, db_path):
        game_no = create_game("alice", db_path)
        assert get_result(game_no, db_path) is None

        set_result(game_no, "White wins by checkmate", db_path)
        assert get_result(game_no, db_path) == "White wins by checkmate"


class TestHistory:
    """Tests for game history and game log."""

    def test_game_history(self, db_path):
        game_no = create_game("alice", db_path)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        hostage = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
        }
        join_game(game_no, "bob", fen, hostage, 300, db_path)
        set_result(game_no, "Draw by stalemate", db_path)

        history = get_game_history(db_path)
        assert len(history) == 1
        assert history[0]["white_handle"] == "alice"
        assert history[0]["black_handle"] == "bob"
        assert history[0]["result"] == "Draw by stalemate"

    def test_game_log(self, db_path):
        game_no = create_game("alice", db_path)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        hostage = {
            "white_prison": [],
            "white_airfield": [],
            "black_prison": [],
            "black_airfield": [],
        }
        join_game(game_no, "bob", fen, hostage, 300, db_path)

        log = get_game_log(game_no, db_path)
        assert len(log) == 1
        assert log[0]["turn_no"] == 1

    def test_empty_history(self, db_path):
        history = get_game_history(db_path)
        assert history == []
