"""HTTP server and request routing for Hostage Chess."""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from src.engine.board import (
    GameState,
    from_dict,
    indices_to_algebraic,
    new_game,
    to_fen,
)
from src.engine.hostage import (
    apply_drop,
    apply_exchange,
    apply_move,
    get_drop_moves,
    get_exchange_options,
)
from src.engine.moves import get_legal_board_moves
from src.engine.result import check_game_result
from src.server import database as db
from src.server import templates

GAME_TIME = 300  # Seconds per player
STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Hostage Chess server."""

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default request logging for cleaner output."""

    # ── GET routes ──────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        """Route GET requests."""
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self._send_html(templates.lobby_page())
        elif path == "/game":
            self._handle_game_page()
        elif path == "/history":
            self._handle_history()
        elif path == "/gamelog":
            self._handle_gamelog()
        elif path == "/game_over":
            self._handle_game_over_page()
        elif path == "/api/poll":
            self._handle_poll()
        elif path == "/api/state":
            self._handle_state()
        elif path == "/api/game_data":
            self._handle_game_data()
        elif path.startswith("/static/"):
            self._serve_static(path)
        else:
            self.send_error(404, "Not Found")

    # ── POST routes ─────────────────────────────────────────────────────────

    def do_POST(self) -> None:
        """Route POST requests."""
        path = self.path

        if path == "/login":
            self._handle_login()
        elif path == "/api/move":
            self._handle_move()
        elif path == "/api/drop":
            self._handle_drop()
        elif path == "/api/exchange":
            self._handle_exchange()
        elif path == "/api/timeout":
            self._handle_timeout()
        elif path == "/api/resign":
            self._handle_resign()
        else:
            self.send_error(404, "Not Found")

    # ── Page handlers ───────────────────────────────────────────────────────

    def _handle_login(self) -> None:
        """Process login form and matchmake."""
        form = self._parse_form()
        handle = form.get("handle", "").strip()
        if not handle:
            self.send_error(400, "Handle required")
            return

        waiting = db.find_waiting_game()
        if waiting:
            game_no = waiting
            state = new_game()
            fen = to_fen(state)
            hostage = {
                "white_prison": [],
                "white_airfield": [],
                "black_prison": [],
                "black_airfield": [],
            }
            db.join_game(game_no, handle, fen, hostage, GAME_TIME)
            self._redirect(f"/game?game_no={game_no}&turn_no=1&role=black")
        else:
            game_no = db.create_game(handle)
            self._send_html(templates.waiting_page(game_no))

    def _handle_game_page(self) -> None:
        """Serve the game page for a player."""
        params = self._query_params()
        game_no = int(params.get("game_no", "0"))
        turn_no = int(params.get("turn_no", "0"))
        role = params.get("role", "white")

        # Check if game is over
        result = db.get_result(game_no)
        if result:
            self._send_html(templates.game_over_page(game_no, result))
            return

        turn_data = db.get_turn(game_no, turn_no)
        if not turn_data:
            self.send_error(404, "Game state not found")
            return

        turn = turn_data["turn"]
        board_fen = turn_data["board_fen"]
        hostage_state = turn_data["hostage_state"]

        # Reconstruct state to calculate times
        state = self._get_state_from_turn(turn_data)
        white_time, black_time = self._calculate_times(state, turn_data)

        is_my_turn = (role == "white" and turn == "w") or (role == "black" and turn == "b")

        # Generate legal moves if it's this player's turn
        legal_moves_json = "[]"
        drop_moves_json = "[]"
        exchange_json = "[]"

        if is_my_turn:
            board_moves = get_legal_board_moves(state)
            legal_moves_json = json.dumps(
                [
                    {
                        "from": indices_to_algebraic(m[0], m[1]),
                        "to": indices_to_algebraic(m[2], m[3]),
                        "promotion": m[4],
                    }
                    for m in board_moves
                ]
            )

            drops = get_drop_moves(state)
            drop_moves_json = json.dumps(
                [
                    {
                        "airfieldIdx": d[1],
                        "to": indices_to_algebraic(d[2], d[3]),
                        "piece": d[4],
                    }
                    for d in drops
                ]
            )

            exchanges = get_exchange_options(state)
            exchange_json = json.dumps(exchanges)

        self._send_html(
            templates.game_page(
                game_no=game_no,
                turn_no=turn_no,
                role=role,
                turn=turn,
                board_fen=board_fen,
                hostage_state=hostage_state,
                white_time=white_time,
                black_time=black_time,
                is_my_turn=is_my_turn,
                legal_moves_json=legal_moves_json,
                drop_moves_json=drop_moves_json,
                exchange_options_json=exchange_json,
            )
        )

    def _handle_history(self) -> None:
        """Serve the game history page."""
        games = db.get_game_history()
        self._send_html(templates.history_page(games))

    def _handle_gamelog(self) -> None:
        """Serve a specific game's log."""
        params = self._query_params()
        game_no = int(params.get("game_no", "0"))
        result = db.get_result(game_no) or "In Progress"
        turns = db.get_game_log(game_no)
        self._send_html(templates.gamelog_page(game_no, result, turns))

    def _handle_game_over_page(self) -> None:
        """Serve the game over page."""
        params = self._query_params()
        game_no = int(params.get("game_no", "0"))
        result = db.get_result(game_no) or "Unknown"
        self._send_html(templates.game_over_page(game_no, result))

    # ── API handlers ────────────────────────────────────────────────────────

    def _handle_poll(self) -> None:
        """Poll for game state updates (used by waiting pages)."""
        params = self._query_params()
        game_no = int(params.get("game_no", "0"))
        turn_no = int(params.get("turn_no", "0"))

        # Check if game has ended
        result = db.get_result(game_no)
        if result:
            self._send_json({"update_available": True, "game_over": True})
            return

        # For turn_no=0, check if opponent has joined (waiting page)
        if turn_no == 0:
            black = db.get_black_handle(game_no)
            self._send_json({"opponent_joined": black is not None})
            return

        # Check for new turns
        latest = db.get_latest_turn_no(game_no)
        if latest and latest > turn_no:
            self._send_json({"update_available": True, "new_turn_no": latest})
        else:
            self._send_json({"update_available": False})

    def _handle_state(self) -> None:
        """Get the current game state as JSON."""
        params = self._query_params()
        game_no = int(params.get("game_no", "0"))
        turn_no = int(params.get("turn_no", "0"))
        turn_data = db.get_turn(game_no, turn_no)
        if turn_data:
            self._send_json(turn_data)
        else:
            self.send_error(404, "Turn not found")

    def _handle_game_data(self) -> None:
        """Return full game config as JSON for in-place client refresh."""
        params = self._query_params()
        game_no = int(params.get("game_no", "0"))
        turn_no = int(params.get("turn_no", "0"))
        role = params.get("role", "white")

        result = db.get_result(game_no)
        if result:
            self._send_json({"game_over": True, "result": result})
            return

        turn_data = db.get_turn(game_no, turn_no)
        if not turn_data:
            self._send_json({"error": "Game state not found"}, 404)
            return

        turn = turn_data["turn"]
        board_fen = turn_data["board_fen"]
        hostage_state = turn_data["hostage_state"]

        state = self._get_state_from_turn(turn_data)
        white_time, black_time = self._calculate_times(state, turn_data)

        is_my_turn = (role == "white" and turn == "w") or (role == "black" and turn == "b")

        legal_moves = []
        drop_moves = []
        exchange_options = []

        if is_my_turn:
            board_moves = get_legal_board_moves(state)
            legal_moves = [
                {
                    "from": indices_to_algebraic(m[0], m[1]),
                    "to": indices_to_algebraic(m[2], m[3]),
                    "promotion": m[4],
                }
                for m in board_moves
            ]

            drops = get_drop_moves(state)
            drop_moves = [
                {
                    "airfieldIdx": d[1],
                    "to": indices_to_algebraic(d[2], d[3]),
                    "piece": d[4],
                }
                for d in drops
            ]

            exchange_options = get_exchange_options(state)

        # Build hostage panel data for this role
        if role == "white":
            player_prison = hostage_state.get("white_prison", [])
            player_airfield = hostage_state.get("white_airfield", [])
            opponent_prison = hostage_state.get("black_prison", [])
            opponent_airfield = hostage_state.get("black_airfield", [])
        else:
            player_prison = hostage_state.get("black_prison", [])
            player_airfield = hostage_state.get("black_airfield", [])
            opponent_prison = hostage_state.get("white_prison", [])
            opponent_airfield = hostage_state.get("white_airfield", [])

        self._send_json(
            {
                "turnNo": turn_no,
                "turn": turn,
                "boardFen": board_fen,
                "whiteTime": white_time,
                "blackTime": black_time,
                "isMyTurn": is_my_turn,
                "legalMoves": legal_moves,
                "dropMoves": drop_moves,
                "exchangeOptions": exchange_options,
                "hostageState": {
                    "playerPrison": player_prison,
                    "playerAirfield": player_airfield,
                    "opponentPrison": opponent_prison,
                    "opponentAirfield": opponent_airfield,
                },
            }
        )

    def _handle_move(self) -> None:
        """Process a board move submitted by the client."""
        data = self._parse_json()
        game_no = data["game_no"]
        turn_no = data["turn_no"]
        role = data["role"]
        from_sq = data["from"]
        to_sq = data["to"]
        promotion = data.get("promotion")

        turn_data = db.get_turn(game_no, turn_no)
        if not turn_data:
            self._send_json({"error": "Invalid turn"}, 400)
            return

        state = self._get_state_from_turn(turn_data)

        # Validate it's the right player's turn
        if (role == "white" and state.active != "w") or (role == "black" and state.active != "b"):
            self._send_json({"error": "Not your turn"}, 400)
            return

        # Find the matching legal move
        from src.engine.board import algebraic_to_indices

        from_r, from_f = algebraic_to_indices(from_sq)
        to_r, to_f = algebraic_to_indices(to_sq)

        legal = get_legal_board_moves(state)
        matching = [
            m for m in legal if m[0] == from_r and m[1] == from_f and m[2] == to_r and m[3] == to_f
        ]

        if promotion:
            matching = [m for m in matching if m[4] == promotion]
        else:
            matching = [m for m in matching if m[4] is None]

        if not matching:
            self._send_json({"error": "Illegal move"}, 400)
            return

        move = matching[0]
        new_state = apply_move(state, move)

        # Time management
        wt, bt = self._calculate_times(state, turn_data)

        # Check for timeout
        if (state.active == "w" and wt <= 0) or (state.active == "b" and bt <= 0):
            result = "Black wins on time" if state.active == "w" else "White wins on time"
            db.set_result(game_no, result)
            self._send_json({"game_over": True, "result": result})
            return

        # Save turn
        new_turn_no = turn_no + 1
        new_fen = to_fen(new_state)
        new_hostage = self._get_hostage_dict(new_state)
        db.save_turn(game_no, new_turn_no, new_state.active, new_fen, new_hostage, wt, bt)

        # Check for game result
        game_result = check_game_result(new_state)
        if game_result:
            db.set_result(game_no, game_result)
            self._send_json({"game_over": True, "result": game_result})
            return

        self._send_json({"ok": True, "new_turn_no": new_turn_no})

    def _handle_drop(self) -> None:
        """Process a drop move (place piece from airfield)."""
        data = self._parse_json()
        game_no = data["game_no"]
        turn_no = data["turn_no"]
        role = data["role"]
        airfield_idx = data["airfield_idx"]
        to_sq = data["to"]

        turn_data = db.get_turn(game_no, turn_no)
        if not turn_data:
            self._send_json({"error": "Invalid turn"}, 400)
            return

        state = self._get_state_from_turn(turn_data)

        if (role == "white" and state.active != "w") or (role == "black" and state.active != "b"):
            self._send_json({"error": "Not your turn"}, 400)
            return

        from src.engine.board import algebraic_to_indices

        to_r, to_f = algebraic_to_indices(to_sq)

        # Validate the drop is legal
        drops = get_drop_moves(state)
        matching = [d for d in drops if d[1] == airfield_idx and d[2] == to_r and d[3] == to_f]
        if not matching:
            self._send_json({"error": "Illegal drop"}, 400)
            return

        new_state = apply_drop(state, airfield_idx, to_r, to_f)

        wt, bt = self._calculate_times(state, turn_data)

        new_turn_no = turn_no + 1
        new_fen = to_fen(new_state)
        new_hostage = self._get_hostage_dict(new_state)
        db.save_turn(game_no, new_turn_no, new_state.active, new_fen, new_hostage, wt, bt)

        game_result = check_game_result(new_state)
        if game_result:
            db.set_result(game_no, game_result)
            self._send_json({"game_over": True, "result": game_result})
            return

        self._send_json({"ok": True, "new_turn_no": new_turn_no})

    def _handle_exchange(self) -> None:
        """Process a hostage exchange."""
        data = self._parse_json()
        game_no = data["game_no"]
        turn_no = data["turn_no"]
        role = data["role"]
        rescue_idx = data["rescue_idx"]
        payment_idx = data["payment_idx"]
        drop_sq = data["drop_square"]

        turn_data = db.get_turn(game_no, turn_no)
        if not turn_data:
            self._send_json({"error": "Invalid turn"}, 400)
            return

        state = self._get_state_from_turn(turn_data)

        if (role == "white" and state.active != "w") or (role == "black" and state.active != "b"):
            self._send_json({"error": "Not your turn"}, 400)
            return

        # Validate the exchange is legal
        exchanges = get_exchange_options(state)
        matching = [
            e
            for e in exchanges
            if e["rescue_idx"] == rescue_idx
            and e["payment_idx"] == payment_idx
            and drop_sq in e.get("valid_drops", [])
        ]
        if not matching:
            self._send_json({"error": "Illegal exchange"}, 400)
            return

        from src.engine.board import algebraic_to_indices

        dr, df = algebraic_to_indices(drop_sq)
        if state.board[dr][df] != " ":
            self._send_json({"error": "Drop square not empty"}, 400)
            return

        new_state = apply_exchange(state, rescue_idx, payment_idx, dr, df)

        wt, bt = self._calculate_times(state, turn_data)

        new_turn_no = turn_no + 1
        new_fen = to_fen(new_state)
        new_hostage = self._get_hostage_dict(new_state)
        db.save_turn(game_no, new_turn_no, new_state.active, new_fen, new_hostage, wt, bt)

        game_result = check_game_result(new_state)
        if game_result:
            db.set_result(game_no, game_result)
            self._send_json({"game_over": True, "result": game_result})
            return

        self._send_json({"ok": True, "new_turn_no": new_turn_no})

    def _handle_timeout(self) -> None:
        """Handle timeout notification from client."""
        data = self._parse_json()
        game_no = data["game_no"]
        turn_no = data["turn_no"]

        turn_data = db.get_turn(game_no, turn_no)
        if not turn_data:
            self._send_json({"error": "Invalid turn"}, 400)
            return

        current_turn = turn_data["turn"]
        result = "Black wins on time" if current_turn == "w" else "White wins on time"
        db.set_result(game_no, result)
        self._send_json({"game_over": True, "result": result})

    def _handle_resign(self) -> None:
        """Handle resignation request from client."""
        data = self._parse_json()
        game_no = data["game_no"]
        role = data["role"]

        player = "White" if role == "white" else "Black"
        result = f"{player} resigned"
        db.set_result(game_no, result)
        self._send_json({"game_over": True, "result": result})

    # ── Static files ────────────────────────────────────────────────────────

    def _serve_static(self, path: str) -> None:
        """Serve files from the static directory."""
        relative = path.removeprefix("/static/")
        
        try:
            filepath = (STATIC_DIR / relative).resolve()
        except Exception:
            self.send_error(400, "Bad Request")
            return

        if not filepath.is_relative_to(STATIC_DIR.resolve()):
            self.send_error(403, "Forbidden")
            return

        if not filepath.exists() or not filepath.is_file():
            self.send_error(404, "Not Found")
            return

        # Determine content type
        suffix = filepath.suffix.lower()
        content_types = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        content_type = content_types.get(suffix, "application/octet-stream")

        content = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _parse_form(self) -> dict[str, str]:
        """Parse URL-encoded form data from a POST request."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        return dict(urllib.parse.parse_qsl(body))

    def _parse_json(self) -> dict:
        """Parse JSON body from a POST request."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def _query_params(self) -> dict[str, str]:
        """Parse query parameters from the URL."""
        if "?" in self.path:
            query = self.path.split("?", 1)[1]
            return dict(urllib.parse.parse_qsl(query))
        return {}

    def _send_html(self, content: str, status: int = 200) -> None:
        """Send an HTML response."""
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, url: str) -> None:
        """Send a 302 redirect."""
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    @staticmethod
    def _elapsed_since(iso_time: str) -> int:
        """Calculate seconds elapsed since the given ISO time string."""
        return int((datetime.now(timezone.utc) - datetime.fromisoformat(iso_time)).total_seconds())

    def _get_state_from_turn(self, turn_data: dict) -> GameState:
        """Reconstruct GameState from turn_data dictionary."""
        return from_dict({"fen": turn_data["board_fen"], **turn_data["hostage_state"]})

    def _calculate_times(self, state: GameState, turn_data: dict) -> tuple[int, int]:
        """Calculate remaining time for both players based on elapsed real time."""
        elapsed = self._elapsed_since(turn_data["real_time"])
        wt, bt = turn_data["white_time"], turn_data["black_time"]
        if state.active == "w":
            wt = max(0, wt - elapsed)
        else:
            bt = max(0, bt - elapsed)
        return wt, bt

    def _get_hostage_dict(self, state: GameState) -> dict:
        """Return hostage data in dictionary format for saving."""
        return {
            "white_prison": state.white_prison,
            "white_airfield": state.white_airfield,
            "black_prison": state.black_prison,
            "black_airfield": state.black_airfield,
        }


def run_server(port: int) -> None:
    """Initialise the database and start the HTTP server."""
    db.init_db()
    server = HTTPServer(("0.0.0.0", port), RequestHandler)
    print(f"Hostage Chess server running on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
