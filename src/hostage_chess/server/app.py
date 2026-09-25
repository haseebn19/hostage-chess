"""HTTP server and request routing for Hostage Chess."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import urllib.parse
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

from hostage_chess.engine.board import (
    BLACK,
    WHITE,
    GameState,
    algebraic_to_indices,
    from_dict,
    hostage_dict,
    indices_to_algebraic,
    new_game,
    to_fen,
)
from hostage_chess.engine.hostage import (
    apply_drop,
    apply_exchange,
    apply_move,
    get_drop_moves,
    get_exchange_options,
)
from hostage_chess.engine.moves import get_legal_board_moves, is_in_check
from hostage_chess.engine.result import check_game_result
from hostage_chess.server import database as db
from hostage_chess.server import templates

if TYPE_CHECKING:
    from collections.abc import Callable

GAME_TIME = 300  # Seconds per player
# Allowance for network delay when a client reports that a clock has run out.
TIMEOUT_TOLERANCE = 1
HANDLE_MAX_LENGTH = 20
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
ROLE_COLOURS = {"white": WHITE, "black": BLACK}
SQUARE_PATTERN = re.compile(r"[a-h][1-8]")
CONTENT_TYPES = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".svg": "image/svg+xml",
}

GET_ROUTES = {
    "/": "_handle_lobby",
    "/index.html": "_handle_lobby",
    "/game": "_handle_game_page",
    "/history": "_handle_history",
    "/gamelog": "_handle_gamelog",
    "/game_over": "_handle_game_over_page",
    "/api/poll": "_handle_poll",
    "/api/game_data": "_handle_game_data",
}

POST_ROUTES = {
    "/login": "_handle_login",
    "/api/move": "_handle_move",
    "/api/drop": "_handle_drop",
    "/api/exchange": "_handle_exchange",
    "/api/timeout": "_handle_timeout",
    "/api/resign": "_handle_resign",
}


class RequestError(Exception):
    """A request that cannot be processed. The message is shown to the client."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


# Input parsing


def _int_value(source: dict, name: str) -> int:
    """Read an integer from query parameters or a JSON body."""
    value = source.get(name)
    if isinstance(value, bool):
        raise RequestError(f"Invalid {name}")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise RequestError(f"Missing or invalid {name}") from None


def _player_role(source: dict, game_no: int) -> str:
    """Return the side ('white' or 'black') of the player whose key the request carries.

    Each player gets a secret key when they join, in the link to their game page, so nobody
    else can move or resign for them.
    """
    key = source.get("player")
    role = db.get_player_role(game_no, key) if isinstance(key, str) else None
    if role is None:
        raise RequestError("Not a player in this game", 403)
    return role


def _square_value(source: dict, name: str) -> tuple[int, int]:
    """Read a square in algebraic notation and return its (rank, file) indices."""
    square = source.get(name)
    if not isinstance(square, str) or not SQUARE_PATTERN.fullmatch(square):
        raise RequestError(f"Invalid {name} square")
    return algebraic_to_indices(square)


# Game state helpers


def _state_from_turn(turn_data: dict) -> GameState:
    """Rebuild a GameState from a stored turn."""
    return from_dict({"fen": turn_data["board_fen"], **turn_data["hostage_state"]})


def _remaining_times(state: GameState, turn_data: dict) -> tuple[int, int]:
    """Return each player's remaining seconds, counting time since the turn started."""
    elapsed = int(
        (datetime.now(UTC) - datetime.fromisoformat(turn_data["real_time"])).total_seconds()
    )
    white_time, black_time = turn_data["white_time"], turn_data["black_time"]
    if state.active == WHITE:
        white_time = max(0, white_time - elapsed)
    else:
        black_time = max(0, black_time - elapsed)
    return white_time, black_time


def _latest_turn(game_no: int, turn_no: int) -> tuple[GameState, int, int]:
    """Return the position at a turn and each player's remaining seconds.

    Requests act on the position the player sees, so the turn must still be the latest one.
    """
    if db.get_latest_turn_no(game_no) != turn_no:
        raise RequestError("This turn has already been played")
    turn_data = db.get_turn(game_no, turn_no)
    state = _state_from_turn(turn_data)
    return state, *_remaining_times(state, turn_data)


def _timeout_result(active: str) -> str:
    return "Black wins on time" if active == WHITE else "White wins on time"


def _game_view(game_no: int, turn_no: int, role: str, key: str, turn_data: dict) -> dict:
    """Return everything the game page shows one player for one turn."""
    state = _state_from_turn(turn_data)
    white_time, black_time = _remaining_times(state, turn_data)
    is_my_turn = state.active == ROLE_COLOURS[role]
    hostages = turn_data["hostage_state"]
    player, opponent = ("white", "black") if role == "white" else ("black", "white")

    view = {
        "gameNo": game_no,
        "turnNo": turn_no,
        "role": role,
        "player": key,
        "turn": state.active,
        "boardFen": turn_data["board_fen"],
        "whiteTime": white_time,
        "blackTime": black_time,
        "isMyTurn": is_my_turn,
        "inCheck": is_in_check(state, state.active),
        "legalMoves": [],
        "dropMoves": [],
        "exchangeOptions": [],
        "hostageState": {
            "playerPrison": hostages.get(f"{player}_prison", []),
            "playerAirfield": hostages.get(f"{player}_airfield", []),
            "opponentPrison": hostages.get(f"{opponent}_prison", []),
            "opponentAirfield": hostages.get(f"{opponent}_airfield", []),
        },
    }

    if is_my_turn:
        view["legalMoves"] = [
            {
                "from": indices_to_algebraic(move.from_rank, move.from_file),
                "to": indices_to_algebraic(move.to_rank, move.to_file),
                "promotion": move.promotion,
            }
            for move in get_legal_board_moves(state)
        ]
        view["dropMoves"] = [
            {
                "airfieldIdx": drop.airfield_idx,
                "to": indices_to_algebraic(drop.to_rank, drop.to_file),
                "piece": drop.piece,
            }
            for drop in get_drop_moves(state)
        ]
        view["exchangeOptions"] = [
            {
                "rescue": option["rescue"],
                "rescueIdx": option["rescue_idx"],
                "payment": option["payment"],
                "paymentIdx": option["payment_idx"],
                "validDrops": option["valid_drops"],
            }
            for option in get_exchange_options(state)
        ]

    return view


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Hostage Chess server."""

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the default per-request logging."""

    def do_GET(self) -> None:
        """Route GET requests."""
        path = self.path.split("?")[0]
        if path.startswith("/static/"):
            self._serve_static(path)
        else:
            self._dispatch(GET_ROUTES.get(path))

    def do_POST(self) -> None:
        """Route POST requests."""
        self._dispatch(POST_ROUTES.get(self.path.split("?")[0]))

    def _dispatch(self, handler_name: str | None) -> None:
        """Call a route handler and report invalid requests as JSON or HTML errors."""
        if handler_name is None:
            self.send_error(404, "Not Found")
            return

        try:
            getattr(self, handler_name)()
        except RequestError as error:
            if self.path.startswith("/api/"):
                self._send_json({"error": error.message}, error.status)
            else:
                self.send_error(error.status, error.message)

    # Pages

    def _handle_lobby(self) -> None:
        self._send_html(templates.lobby_page())

    def _handle_login(self) -> None:
        """Process the lobby form and match the player with a waiting game."""
        handle = self._parse_form().get("handle", "").strip()[:HANDLE_MAX_LENGTH]
        if not handle:
            raise RequestError("Handle required")

        key = secrets.token_urlsafe(16)
        start = new_game()
        game_no = db.join_waiting_game(handle, key, to_fen(start), hostage_dict(start), GAME_TIME)
        if game_no is not None:
            self._redirect(f"/game?game_no={game_no}&player={key}")
        else:
            game_no = db.create_game(handle, key)
            self._send_html(templates.waiting_page(game_no, key))

    def _handle_game_page(self) -> None:
        """Serve the game page at the latest turn, so reloading the page keeps the position."""
        params = self._query_params()
        game_no = _int_value(params, "game_no")

        result = db.get_result(game_no)
        if result:
            self._send_html(templates.game_over_page(game_no, result))
            return

        role = _player_role(params, game_no)
        turn_no = db.get_latest_turn_no(game_no)
        if turn_no is None:
            raise RequestError("The game has not started")

        view = _game_view(game_no, turn_no, role, params["player"], db.get_turn(game_no, turn_no))
        self._send_html(templates.game_page(view))

    def _handle_history(self) -> None:
        self._send_html(templates.history_page(db.get_game_history()))

    def _handle_gamelog(self) -> None:
        game_no = _int_value(self._query_params(), "game_no")
        result = db.get_result(game_no) or "In progress"
        self._send_html(templates.gamelog_page(game_no, result, db.get_game_log(game_no)))

    def _handle_game_over_page(self) -> None:
        game_no = _int_value(self._query_params(), "game_no")
        result = db.get_result(game_no) or "In progress"
        self._send_html(templates.game_over_page(game_no, result))

    # Polling

    def _handle_poll(self) -> None:
        """Report whether the game has changed since the client's turn."""
        params = self._query_params()
        game_no = _int_value(params, "game_no")
        turn_no = _int_value(params, "turn_no")

        if db.get_result(game_no):
            self._send_json({"update_available": True, "game_over": True})
            return

        # Turn 0 means the player is on the waiting page.
        if turn_no == 0:
            self._send_json({"opponent_joined": db.get_black_handle(game_no) is not None})
            return

        latest = db.get_latest_turn_no(game_no)
        if latest and latest > turn_no:
            self._send_json({"update_available": True, "new_turn_no": latest})
        else:
            self._send_json({"update_available": False})

    def _handle_game_data(self) -> None:
        """Return the latest game state for an in-place refresh of the game page."""
        params = self._query_params()
        game_no = _int_value(params, "game_no")

        result = db.get_result(game_no)
        if result:
            self._send_json({"game_over": True, "result": result})
            return

        role = _player_role(params, game_no)
        turn_no = db.get_latest_turn_no(game_no)
        if turn_no is None:
            raise RequestError("The game has not started")

        turn_data = db.get_turn(game_no, turn_no)
        self._send_json(_game_view(game_no, turn_no, role, params["player"], turn_data))

    # Game actions

    def _handle_move(self) -> None:
        """Play a board move."""
        data = self._parse_json()
        from_square = _square_value(data, "from")
        to_square = _square_value(data, "to")
        promotion = data.get("promotion")

        def play(state: GameState) -> GameState:
            for move in get_legal_board_moves(state):
                if move == (*from_square, *to_square, promotion):
                    return apply_move(state, move)
            raise RequestError("Illegal move")

        self._play_turn(data, play)

    def _handle_drop(self) -> None:
        """Drop a piece from the player's airfield onto the board."""
        data = self._parse_json()
        airfield_idx = _int_value(data, "airfield_idx")
        to_rank, to_file = _square_value(data, "to")

        def play(state: GameState) -> GameState:
            legal = any(
                (drop.airfield_idx, drop.to_rank, drop.to_file) == (airfield_idx, to_rank, to_file)
                for drop in get_drop_moves(state)
            )
            if not legal:
                raise RequestError("Illegal drop")
            return apply_drop(state, airfield_idx, to_rank, to_file)

        self._play_turn(data, play)

    def _handle_exchange(self) -> None:
        """Exchange a prisoner to rescue a piece and drop it on the board."""
        data = self._parse_json()
        rescue_idx = _int_value(data, "rescue_idx")
        payment_idx = _int_value(data, "payment_idx")
        drop_rank, drop_file = _square_value(data, "drop_square")
        drop_square = indices_to_algebraic(drop_rank, drop_file)

        def play(state: GameState) -> GameState:
            legal = any(
                option["rescue_idx"] == rescue_idx
                and option["payment_idx"] == payment_idx
                and drop_square in option["valid_drops"]
                for option in get_exchange_options(state)
            )
            if not legal:
                raise RequestError("Illegal exchange")
            return apply_exchange(state, rescue_idx, payment_idx, drop_rank, drop_file)

        self._play_turn(data, play)

    def _play_turn(self, data: dict, play: Callable[[GameState], GameState]) -> None:
        """Validate a move, drop, or exchange request, apply it, and save the next turn.

        The request must be for the latest turn of a game in progress, from the player to move,
        whose clock has not run out.
        """
        game_no = _int_value(data, "game_no")
        turn_no = _int_value(data, "turn_no")
        role = _player_role(data, game_no)

        result = db.get_result(game_no)
        if result:
            self._send_json({"game_over": True, "result": result})
            return

        state, white_time, black_time = _latest_turn(game_no, turn_no)
        if state.active != ROLE_COLOURS[role]:
            raise RequestError("Not your turn")
        if (white_time if state.active == WHITE else black_time) <= 0:
            self._end_game(game_no, _timeout_result(state.active))
            return

        new_state = play(state)
        try:
            db.save_turn(
                game_no,
                turn_no + 1,
                new_state.active,
                to_fen(new_state),
                hostage_dict(new_state),
                white_time,
                black_time,
            )
        except sqlite3.IntegrityError:
            raise RequestError("This turn has already been played") from None

        game_result = check_game_result(new_state)
        if game_result:
            self._end_game(game_no, game_result)
        else:
            self._send_json({"ok": True, "new_turn_no": turn_no + 1})

    def _handle_timeout(self) -> None:
        """End the game if the player to move has run out of time."""
        data = self._parse_json()
        game_no = _int_value(data, "game_no")
        turn_no = _int_value(data, "turn_no")

        result = db.get_result(game_no)
        if result:
            self._send_json({"game_over": True, "result": result})
            return

        state, white_time, black_time = _latest_turn(game_no, turn_no)
        if (white_time if state.active == WHITE else black_time) > TIMEOUT_TOLERANCE:
            raise RequestError("Time has not run out")

        self._end_game(game_no, _timeout_result(state.active))

    def _handle_resign(self) -> None:
        """Resign the game for the requesting player."""
        data = self._parse_json()
        game_no = _int_value(data, "game_no")
        role = _player_role(data, game_no)

        if db.get_latest_turn_no(game_no) is None:
            raise RequestError("The game has not started")

        result = db.get_result(game_no)
        if result:
            self._send_json({"game_over": True, "result": result})
        else:
            self._end_game(game_no, f"{role.capitalize()} resigned")

    def _end_game(self, game_no: int, result: str) -> None:
        # If another request ended the game first, its result stands
        self._send_json({"game_over": True, "result": db.set_result(game_no, result)})

    # Static files

    def _serve_static(self, path: str) -> None:
        """Serve a file from the static directory."""
        try:
            filepath = (STATIC_DIR / path.removeprefix("/static/")).resolve()
        except (OSError, ValueError):
            self.send_error(400, "Bad Request")
            return

        if not filepath.is_relative_to(STATIC_DIR.resolve()):
            self.send_error(403, "Forbidden")
            return
        if not filepath.is_file():
            self.send_error(404, "Not Found")
            return

        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type", CONTENT_TYPES.get(filepath.suffix.lower(), "application/octet-stream")
        )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # Request and response helpers

    def _read_body(self) -> str:
        """Read the request body as UTF-8 text."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length < 0:
                raise ValueError(length)
            return self.rfile.read(length).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise RequestError("Invalid request body") from None

    def _parse_form(self) -> dict[str, str]:
        """Parse URL-encoded form data from a POST request."""
        return dict(urllib.parse.parse_qsl(self._read_body()))

    def _parse_json(self) -> dict:
        """Parse a JSON object from the request body."""
        body = self._read_body()
        try:
            data = json.loads(body)
        except ValueError:
            raise RequestError("Invalid JSON") from None
        if not isinstance(data, dict):
            raise RequestError("Invalid JSON")
        return data

    def _query_params(self) -> dict[str, str]:
        """Parse query parameters from the URL."""
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        return dict(urllib.parse.parse_qsl(query))

    def _send_html(self, content: str) -> None:
        encoded = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, url: str) -> None:
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()


def run_server(port: int) -> None:
    """Initialize the database and start the HTTP server."""
    db.init_db()
    server = ThreadingHTTPServer(("0.0.0.0", port), RequestHandler)
    print(f"Hostage Chess server running on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
