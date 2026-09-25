"""HTTP tests for hostage_chess.server.app: matchmaking, game actions, and request validation."""

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from typing import NamedTuple
from urllib.parse import urlencode

import pytest

from hostage_chess.server import database as db


def request(server, method, path, body=None, content_type="application/json"):
    """Send a request and return (status, headers, body text)."""
    connection = HTTPConnection(*server, timeout=5)
    try:
        headers = {"Content-Type": content_type} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode()
    finally:
        connection.close()


def post_json(server, path, data):
    status, _, body = request(server, "POST", path, json.dumps(data))
    return status, json.loads(body)


def login(server, handle):
    form = urlencode({"handle": handle})
    return request(server, "POST", "/login", form, "application/x-www-form-urlencoded")


class Game(NamedTuple):
    no: int
    white: str
    black: str


def game_link(text):
    """Return the game number and player key from a link to a game page."""
    match = re.search(r"/game\?game_no=(\d+)&player=([\w-]+)", text)
    return int(match.group(1)), match.group(2)


@pytest.fixture
def game(server):
    """Start a game between two players and return its number and the players' keys."""
    _, _, waiting_page = login(server, "alice")
    status, headers, _ = login(server, "bob")
    assert status == 302
    game_no, white = game_link(waiting_page)
    _, black = game_link(headers["Location"])
    return Game(game_no, white, black)


def move(server, game_no, turn_no, player, from_square, to_square):
    return post_json(
        server,
        "/api/move",
        {
            "game_no": game_no,
            "turn_no": turn_no,
            "player": player,
            "from": from_square,
            "to": to_square,
            "promotion": None,
        },
    )


def page_config(html):
    """Extract the GAME_CONFIG object embedded in the game page."""
    return json.loads(re.search(r"window.GAME_CONFIG = (\{.*\});", html).group(1))


class TestMatchmaking:
    def test_second_player_joins_the_waiting_game(self, server):
        status, _, body = login(server, "alice")
        assert status == 200
        assert "Waiting for Opponent" in body

        status, headers, _ = login(server, "bob")
        assert status == 302
        white_game, white_key = game_link(body)
        black_game, black_key = game_link(headers["Location"])
        assert black_game == white_game
        assert black_key != white_key

    def test_empty_handle_is_rejected(self, server):
        status, _, _ = login(server, "   ")
        assert status == 400


class TestGamePage:
    def test_page_shows_the_latest_turn(self, server, game):
        move(server, game.no, 1, game.white, "e2", "e4")

        status, _, body = request(server, "GET", f"/game?game_no={game.no}&player={game.white}")

        assert status == 200
        config = page_config(body)
        assert config["role"] == "white"
        assert config["turnNo"] == 2
        assert config["isMyTurn"] is False

    def test_a_wrong_key_is_rejected(self, server, game):
        status, _, body = request(server, "GET", f"/game?game_no={game.no}&player=';alert(1)//")
        assert status == 403
        assert "alert(1)" not in body

    def test_a_key_only_opens_its_own_game(self, server, game):
        login(server, "carol")
        _, headers, _ = login(server, "dave")
        other_game, _ = game_link(headers["Location"])

        status, _, _ = request(server, "GET", f"/game?game_no={other_game}&player={game.white}")

        assert status == 403

    @pytest.mark.parametrize("query", ["game_no=abc&player=key", "player=key"])
    def test_invalid_game_number_is_rejected(self, server, query):
        status, _, _ = request(server, "GET", f"/game?{query}")
        assert status == 400

    def test_game_data_returns_the_latest_turn(self, server, game):
        move(server, game.no, 1, game.white, "e2", "e4")
        status, _, body = request(
            server, "GET", f"/api/game_data?game_no={game.no}&player={game.black}"
        )
        data = json.loads(body)
        assert status == 200
        assert data["turnNo"] == 2
        assert data["isMyTurn"] is True
        assert data["legalMoves"]

    def test_game_data_needs_a_key(self, server, game):
        status, _, body = request(server, "GET", f"/api/game_data?game_no={game.no}")
        assert status == 403
        assert json.loads(body) == {"error": "Not a player in this game"}


class TestMoves:
    def test_legal_move_creates_the_next_turn(self, server, game):
        status, data = move(server, game.no, 1, game.white, "e2", "e4")
        assert status == 200
        assert data == {"ok": True, "new_turn_no": 2}

    def test_illegal_move_is_rejected(self, server, game):
        status, data = move(server, game.no, 1, game.white, "e2", "e5")
        assert status == 400
        assert data["error"] == "Illegal move"

    def test_move_out_of_turn_is_rejected(self, server, game):
        status, data = move(server, game.no, 1, game.black, "e7", "e5")
        assert status == 400
        assert data["error"] == "Not your turn"

    def test_move_without_a_players_key_is_rejected(self, server, game):
        status, data = move(server, game.no, 1, "guessed", "e2", "e4")
        assert status == 403
        assert data["error"] == "Not a player in this game"
        assert db.get_latest_turn_no(game.no) == 1

    def test_replaying_an_old_turn_is_rejected(self, server, game):
        move(server, game.no, 1, game.white, "e2", "e4")
        status, data = move(server, game.no, 1, game.white, "d2", "d4")
        assert status == 400
        assert data["error"] == "This turn has already been played"

    def test_moves_after_the_game_ends_are_not_saved(self, server, game):
        post_json(server, "/api/resign", {"game_no": game.no, "player": game.black})

        status, data = move(server, game.no, 1, game.white, "e2", "e4")

        assert status == 200
        assert data == {"game_over": True, "result": "Black resigned"}
        assert db.get_latest_turn_no(game.no) == 1

    @pytest.mark.usefixtures("game")
    @pytest.mark.parametrize(
        "body",
        ["not json", "[]", json.dumps({"game_no": 1, "turn_no": 1, "player": "key", "from": "z9"})],
    )
    def test_malformed_requests_get_a_json_error(self, server, body):
        status, _, text = request(server, "POST", "/api/move", body)
        assert status == 400
        assert "error" in json.loads(text)

    @pytest.mark.parametrize("length", ["abc", "-1"])
    def test_invalid_content_length_gets_a_json_error(self, server, length):
        connection = HTTPConnection(*server, timeout=5)
        try:
            connection.putrequest("POST", "/api/move")
            connection.putheader("Content-Length", length)
            connection.endheaders()
            response = connection.getresponse()
            assert response.status == 400
            assert json.loads(response.read()) == {"error": "Invalid request body"}
        finally:
            connection.close()


class TestClockAndResignation:
    def expire_clock(self, game_no, turn_no):
        """Backdate a turn's start so the player to move has run out of time."""
        started = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.execute(
                "UPDATE boards SET real_time = ? WHERE game_no = ? AND turn_no = ?",
                (started, game_no, turn_no),
            )
        conn.close()

    def test_timeout_is_rejected_while_time_remains(self, server, game):
        status, data = post_json(server, "/api/timeout", {"game_no": game.no, "turn_no": 1})
        assert status == 400
        assert data["error"] == "Time has not run out"
        assert db.get_result(game.no) is None

    def test_timeout_ends_the_game_when_time_has_run_out(self, server, game):
        self.expire_clock(game.no, 1)
        status, data = post_json(server, "/api/timeout", {"game_no": game.no, "turn_no": 1})
        assert status == 200
        assert data == {"game_over": True, "result": "Black wins on time"}

    def test_move_after_running_out_of_time_loses_on_time(self, server, game):
        self.expire_clock(game.no, 1)
        status, data = move(server, game.no, 1, game.white, "e2", "e4")
        assert status == 200
        assert data == {"game_over": True, "result": "Black wins on time"}
        assert db.get_latest_turn_no(game.no) == 1

    def test_resignation_does_not_replace_an_existing_result(self, server, game):
        post_json(server, "/api/resign", {"game_no": game.no, "player": game.white})
        status, data = post_json(server, "/api/resign", {"game_no": game.no, "player": game.black})
        assert status == 200
        assert data["result"] == "White resigned"
        assert db.get_result(game.no) == "White resigned"

    def test_only_a_player_can_resign(self, server, game):
        status, _ = post_json(server, "/api/resign", {"game_no": game.no, "player": "guessed"})
        assert status == 403
        assert db.get_result(game.no) is None

    def test_resigning_an_unknown_game_is_rejected(self, server):
        status, _ = post_json(server, "/api/resign", {"game_no": 99, "player": "key"})
        assert status == 403


class TestHostageActions:
    KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"

    def action(self, server, path, game, **fields):
        return post_json(
            server, path, {"game_no": game.no, "turn_no": 1, "player": game.white, **fields}
        )

    def test_drop_places_a_piece_from_the_airfield(self, server, game, set_position):
        set_position(game.no, 1, self.KINGS_ONLY, white_airfield=["N"])

        status, _ = self.action(server, "/api/drop", game, airfield_idx=0, to="d4")

        assert status == 200
        turn = db.get_turn(game.no, 2)
        assert turn["board_fen"].startswith("4k3/8/8/8/3N4/8/8/4K3 b")
        assert turn["hostage_state"]["white_airfield"] == []

    def test_illegal_drop_is_rejected(self, server, game, set_position):
        set_position(game.no, 1, self.KINGS_ONLY, white_airfield=["P"])
        status, data = self.action(server, "/api/drop", game, airfield_idx=0, to="d8")
        assert status == 400
        assert data["error"] == "Illegal drop"

    def test_exchange_rescues_a_piece_and_pays_the_opponent(self, server, game, set_position):
        set_position(game.no, 1, self.KINGS_ONLY, white_prison=["p"], black_prison=["P"])

        status, _ = self.action(
            server, "/api/exchange", game, rescue_idx=0, payment_idx=0, drop_square="d4"
        )

        assert status == 200
        turn = db.get_turn(game.no, 2)
        assert turn["board_fen"].startswith("4k3/8/8/8/3P4/8/8/4K3 b")
        assert turn["hostage_state"]["black_prison"] == []
        assert turn["hostage_state"]["black_airfield"] == ["p"]

    def test_exchange_with_too_cheap_a_payment_is_rejected(self, server, game, set_position):
        set_position(game.no, 1, self.KINGS_ONLY, white_prison=["p"], black_prison=["R"])
        status, data = self.action(
            server, "/api/exchange", game, rescue_idx=0, payment_idx=0, drop_square="d4"
        )
        assert status == 400
        assert data["error"] == "Illegal exchange"

    def test_view_lists_drops_and_exchanges(self, server, game, set_position):
        set_position(
            game.no,
            1,
            self.KINGS_ONLY,
            white_airfield=["N"],
            white_prison=["p"],
            black_prison=["P"],
        )
        _, _, body = request(server, "GET", f"/api/game_data?game_no={game.no}&player={game.white}")
        view = json.loads(body)

        assert {"airfieldIdx": 0, "to": "d4", "piece": "N"} in view["dropMoves"]
        [option] = view["exchangeOptions"]
        assert option["rescue"] == "P"
        assert (option["rescueIdx"], option["payment"], option["paymentIdx"]) == (0, "p", 0)
        assert "d4" in option["validDrops"]

    def test_view_reports_check(self, server, game, set_position):
        set_position(game.no, 1, "k3r3/8/8/8/8/8/8/4K3 w - - 0 1")
        _, _, body = request(server, "GET", f"/api/game_data?game_no={game.no}&player={game.white}")
        assert json.loads(body)["inCheck"] is True
