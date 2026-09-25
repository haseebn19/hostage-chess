"""HTML page templates for the Hostage Chess web interface."""

from __future__ import annotations

import html

COMMON_HEAD = """
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/static/vendor/chessboard-1.0.0.css">
    <link rel="stylesheet" href="/static/css/style.css">
"""

COMMON_SCRIPTS = """
    <script src="/static/vendor/jquery-3.4.1.min.js"></script>
    <script src="/static/vendor/chessboard-1.0.0.js"></script>
"""


def lobby_page() -> str:
    """Render the lobby/login page."""
    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess</title>
    {COMMON_HEAD}
</head>
<body>
    <div class="page-container">
        <div class="lobby-card">
            <div class="lobby-icon">♟</div>
            <h1>Hostage Chess</h1>
            <p class="subtitle">A chess variant where captured pieces become hostages</p>
            <form action="/login" method="post" class="lobby-form">
                <input type="text" name="handle" placeholder="Enter your handle"
                       required maxlength="20" autocomplete="off" id="handle-input">
                <button type="submit" id="enter-lobby">Play</button>
            </form>
            <a href="/history" class="history-link" id="view-history">View Game History</a>
        </div>
    </div>
</body>
</html>"""


def waiting_page(game_no: int) -> str:
    """Render the waiting-for-opponent page."""
    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Waiting</title>
    {COMMON_HEAD}
    <script>
        var gameNo = {game_no};
        function checkForOpponent() {{
            fetch('/api/poll?game_no=' + gameNo + '&turn_no=0')
            .then(r => r.json())
            .then(data => {{
                if (data.opponent_joined) {{
                    window.location.href = '/game?game_no=' + gameNo + '&turn_no=1&role=white';
                }} else {{
                    setTimeout(checkForOpponent, 1000);
                }}
            }})
            .catch(() => setTimeout(checkForOpponent, 2000));
        }}
        document.addEventListener('DOMContentLoaded', () => setTimeout(checkForOpponent, 1000));
    </script>
</head>
<body>
    <div class="page-container">
        <div class="waiting-card">
            <div class="spinner"></div>
            <h1>Waiting for Opponent</h1>
            <p class="subtitle">Share this page. Another player will join automatically.</p>
        </div>
    </div>
</body>
</html>"""


def game_page(
    game_no: int,
    turn_no: int,
    role: str,
    turn: str,
    board_fen: str,
    hostage_state: dict,
    white_time: int,
    black_time: int,
    is_my_turn: bool,
    legal_moves_json: str,
    drop_moves_json: str,
    exchange_options_json: str,
) -> str:
    """Render the main game page."""
    orientation = "white" if role == "white" else "black"
    status_text = "Your turn" if is_my_turn else "Opponent's turn"

    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Game {game_no}</title>
    {COMMON_HEAD}
</head>
<body>
    <div class="game-container">
        <div class="game-header">
            <h1>Hostage Chess</h1>
            <span class="status-badge {"active" if is_my_turn else "waiting"}"
                  id="status-text">{status_text}</span>
        </div>

        <div class="game-layout">
            <div class="side-panel opponent-panel">
                <h3>Opponent's Airfield</h3>
                <div class="piece-tray" id="opponent-airfield"></div>
                <h3>Opponent's Prison</h3>
                <div class="piece-tray" id="opponent-prison"></div>
            </div>

            <div class="board-area">
                <div class="timer-bar">
                    <div class="timer {"timer-active" if turn == "b" else ""}"
                         id="black-timer">⬛ <span id="blackTime"></span></div>
                    <div class="timer {"timer-active" if turn == "w" else ""}"
                         id="white-timer">⬜ <span id="whiteTime"></span></div>
                </div>
                <div id="myBoard"></div>
                <div class="move-controls" id="move-controls">
                    <button id="btn-drop" class="control-btn" disabled>Drop Piece</button>
                    <button id="btn-exchange" class="control-btn" disabled>Exchange Hostage</button>
                    <button id="btn-resign" class="control-btn danger">Resign</button>
                </div>
            </div>

            <div class="side-panel player-panel">
                <h3>Your Airfield</h3>
                <div class="piece-tray" id="player-airfield"></div>
                <h3>Your Prison</h3>
                <div class="piece-tray" id="player-prison"></div>
            </div>
        </div>
    </div>

    <!-- Exchange modal -->
    <div class="modal-overlay" id="exchange-modal" style="display:none">
        <div class="modal-card">
            <h2>Hostage Exchange</h2>
            <p>Select a piece to rescue and a piece to pay:</p>
            <div class="exchange-options" id="exchange-options"></div>
            <div class="exchange-drop" id="exchange-drop" style="display:none">
                <p>Click an empty square on the board to drop the rescued piece.</p>
            </div>
            <button class="control-btn" id="cancel-exchange">Cancel</button>
        </div>
    </div>

    <!-- Promotion modal -->
    <div class="modal-overlay" id="promotion-modal" style="display:none">
        <div class="modal-card">
            <h2>Pawn Promotion</h2>
            <p>Choose a piece:</p>
            <div class="promotion-options" id="promotion-options"></div>
        </div>
    </div>

    {COMMON_SCRIPTS}
    <script>
        var GAME_CONFIG = {{
            gameNo: {game_no},
            turnNo: {turn_no},
            role: '{role}',
            turn: '{turn}',
            boardFen: '{board_fen}',
            orientation: '{orientation}',
            isMyTurn: {"true" if is_my_turn else "false"},
            whiteTime: {white_time},
            blackTime: {black_time},
            legalMoves: {legal_moves_json},
            dropMoves: {drop_moves_json},
            exchangeOptions: {exchange_options_json},
            hostageState: {_hostage_state_js(hostage_state, role)},
        }};
    </script>
    <script src="/static/js/game.js"></script>
</body>
</html>"""


def _hostage_state_js(hostage_state: dict, role: str) -> str:
    """Format hostage state for JS, labelling player/opponent correctly."""
    import json

    if role == "white":
        return json.dumps(
            {
                "playerPrison": hostage_state.get("white_prison", []),
                "playerAirfield": hostage_state.get("white_airfield", []),
                "opponentPrison": hostage_state.get("black_prison", []),
                "opponentAirfield": hostage_state.get("black_airfield", []),
            }
        )
    else:
        return json.dumps(
            {
                "playerPrison": hostage_state.get("black_prison", []),
                "playerAirfield": hostage_state.get("black_airfield", []),
                "opponentPrison": hostage_state.get("white_prison", []),
                "opponentAirfield": hostage_state.get("white_airfield", []),
            }
        )


def game_over_page(game_no: int, result: str) -> str:
    """Render the game over page."""
    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Game {game_no} Over</title>
    {COMMON_HEAD}
</head>
<body>
    <div class="page-container">
        <div class="game-over-card">
            <div class="game-over-icon">🏁</div>
            <h1>Game Over</h1>
            <p class="result-text">{html.escape(result)}</p>
            <div class="game-over-links">
                <a href="/history" class="link-btn">Game History</a>
                <a href="/" class="link-btn primary">New Game</a>
            </div>
        </div>
    </div>
</body>
</html>"""


def history_page(games: list[dict]) -> str:
    """Render the game history page."""
    rows = ""
    for game in games:
        rows += f"""
            <tr onclick="window.location.href='/gamelog?game_no={game["game_no"]}'">
                <td>{game["game_no"]}</td>
                <td>{html.escape(game["white_handle"])}</td>
                <td>{html.escape(game["black_handle"] or "N/A")}</td>
                <td>{html.escape(game["result"] or "In Progress")}</td>
            </tr>"""

    empty_msg = '<p class="empty-msg">No games played yet.</p>' if not games else ""

    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | History</title>
    {COMMON_HEAD}
</head>
<body>
    <div class="page-container">
        <div class="history-card">
            <h1>Game History</h1>
            {empty_msg}
            {"<table><thead><tr><th>Game</th><th>White</th><th>Black</th><th>Result</th></tr></thead><tbody>" + rows + "</tbody></table>" if games else ""}
            <a href="/" class="link-btn primary">Back to Lobby</a>
        </div>
    </div>
</body>
</html>"""


def gamelog_page(game_no: int, result: str, turns: list[dict]) -> str:
    """Render the detailed game log page."""
    boards_html = ""
    boards_js = ""

    for idx, turn_data in enumerate(turns):
        turn_no = turn_data["turn_no"]
        board_fen = turn_data["board_fen"]

        if idx == 0:
            label = "Initial Position"
        else:
            player_moved = "Black" if turn_data["turn"] == "w" else "White"
            label = f"Move {idx}: {player_moved}"

        boards_html += f"""
            <div class="log-entry">
                <h3>{label}</h3>
                <div id="board{turn_no}" class="log-board"></div>
            </div>"""

        boards_js += f"""
            Chessboard('board{turn_no}', {{
                draggable: false,
                position: '{board_fen}',
                pieceTheme: '/static/img/Chess_Pieces_Sprite.svg#{{piece}}',
            }});"""

    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Game {game_no} Log</title>
    {COMMON_HEAD}
</head>
<body>
    <div class="page-container">
        <div class="gamelog-card">
            <h1>Game {game_no}</h1>
            <p class="result-text">{html.escape(result)}</p>
            <div class="log-boards">
                {boards_html}
            </div>
            <div class="gamelog-links">
                <a href="/history" class="link-btn">Back to History</a>
                <a href="/" class="link-btn primary">New Game</a>
            </div>
        </div>
    </div>

    {COMMON_SCRIPTS}
    <script>
        $(document).ready(function() {{
            {boards_js}
        }});
    </script>
</body>
</html>"""
