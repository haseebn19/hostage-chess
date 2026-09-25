"""Tests for hostage_chess.server.database: SQLite operations."""

import sqlite3

import pytest

from hostage_chess.server import database as db
from hostage_chess.server.database import (
    create_game,
    get_black_handle,
    get_game_history,
    get_game_log,
    get_latest_turn_no,
    get_player_role,
    get_result,
    get_turn,
    init_db,
    join_waiting_game,
    save_turn,
    set_result,
)

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
NO_HOSTAGES = {"white_prison": [], "white_airfield": [], "black_prison": [], "black_airfield": []}

pytestmark = pytest.mark.usefixtures("database")


def create(handle):
    return create_game(handle, f"{handle}-key")


def join(handle):
    return join_waiting_game(handle, f"{handle}-key", START_FEN, NO_HOSTAGES, 300)


@pytest.fixture
def started_game():
    """Create a game between alice (white) and bob (black) and return its number."""
    create("alice")
    return join("bob")


class TestInitDB:
    def test_init_creates_tables(self, database):
        with sqlite3.connect(database) as conn:
            tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        conn.close()
        assert {"games", "boards"} <= tables

    def test_init_is_idempotent(self):
        init_db()

    def test_init_adds_key_columns_to_an_older_database(self, tmp_path, monkeypatch):
        path = tmp_path / "old.db"
        monkeypatch.setattr(db, "DB_PATH", path)
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE games (game_no INTEGER PRIMARY KEY AUTOINCREMENT, "
                "white_handle TEXT NOT NULL, black_handle TEXT, result TEXT)"
            )
            conn.execute("INSERT INTO games (white_handle) VALUES ('alice')")
        conn.close()

        init_db()

        assert join("bob") == 1
        assert get_player_role(1, "bob-key") == "black"


class TestMatchmaking:
    def test_create_game_returns_id(self):
        assert create("alice") > 0

    def test_join_starts_the_waiting_game(self):
        game_no = create("alice")

        assert join("bob") == game_no
        assert get_black_handle(game_no) == "bob"
        assert get_latest_turn_no(game_no) == 1

    def test_join_without_a_waiting_game_returns_none(self):
        assert join("bob") is None

    def test_join_takes_the_oldest_waiting_game(self):
        first = create("alice")
        create("carol")
        assert join("bob") == first

    def test_a_started_game_is_not_joined_again(self, started_game):
        assert join("carol") is None
        assert get_black_handle(started_game) == "bob"

    def test_each_key_belongs_to_one_side_of_one_game(self, started_game):
        assert get_player_role(started_game, "alice-key") == "white"
        assert get_player_role(started_game, "bob-key") == "black"
        assert get_player_role(started_game, "carol-key") is None
        assert get_player_role(started_game + 1, "alice-key") is None


class TestTurnStorage:
    def test_get_turn_after_join(self, started_game):
        turn = get_turn(started_game, 1)
        assert turn is not None
        assert turn["turn"] == "w"
        assert turn["board_fen"] == START_FEN
        assert turn["white_time"] == 300

    def test_save_and_get_turn(self, started_game):
        new_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        save_turn(started_game, 2, "b", new_fen, NO_HOSTAGES, 295, 300)

        turn = get_turn(started_game, 2)
        assert turn["turn"] == "b"
        assert turn["board_fen"] == new_fen
        assert turn["white_time"] == 295

    def test_saving_the_same_turn_twice_fails(self, started_game):
        save_turn(started_game, 2, "b", START_FEN, NO_HOSTAGES, 295, 300)
        with pytest.raises(sqlite3.IntegrityError):
            save_turn(started_game, 2, "b", START_FEN, NO_HOSTAGES, 290, 300)

    def test_get_latest_turn_no(self, started_game):
        save_turn(started_game, 2, "b", START_FEN, NO_HOSTAGES, 295, 300)
        assert get_latest_turn_no(started_game) == 2

    def test_get_turn_nonexistent(self):
        assert get_turn(999, 1) is None


class TestResults:
    def test_set_and_get_result(self):
        game_no = create("alice")
        assert get_result(game_no) is None

        set_result(game_no, "White wins by checkmate")
        assert get_result(game_no) == "White wins by checkmate"

    def test_the_first_result_stands(self):
        game_no = create("alice")

        assert set_result(game_no, "White resigned") == "White resigned"
        assert set_result(game_no, "Black wins on time") == "White resigned"
        assert get_result(game_no) == "White resigned"


class TestHistory:
    def test_game_history(self, started_game):
        set_result(started_game, "Draw by stalemate")
        create("carol")

        history = get_game_history()
        assert history == [
            {
                "game_no": started_game + 1,
                "white_handle": "carol",
                "black_handle": None,
                "result": None,
            },
            {
                "game_no": started_game,
                "white_handle": "alice",
                "black_handle": "bob",
                "result": "Draw by stalemate",
            },
        ]

    def test_game_log(self, started_game):
        log = get_game_log(started_game)
        assert len(log) == 1
        assert log[0]["turn_no"] == 1

    def test_empty_history(self):
        assert get_game_history() == []
