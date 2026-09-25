"""HTML page templates for the Hostage Chess web interface."""

from __future__ import annotations

import html
import json

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
    <main class="page-container">
        <div class="lobby-card">
            <div class="lobby-icon" aria-hidden="true">♟</div>
            <h1>Hostage Chess</h1>
            <p class="subtitle">A chess variant where captured pieces become hostages</p>
            <form action="/login" method="post" class="lobby-form">
                <input type="text" name="handle" placeholder="Enter your handle"
                       aria-label="Your handle" required maxlength="20" autocomplete="off"
                       id="handle-input">
                <button type="submit" id="enter-lobby">Play</button>
            </form>
            <a href="/history" class="history-link" id="view-history">View Game History</a>
        </div>
    </main>
</body>
</html>"""


def waiting_page(game_no: int, key: str) -> str:
    """Render the waiting-for-opponent page. `key` is the waiting player's key for the game."""
    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Waiting</title>
    {COMMON_HEAD}
    <script>
        async function checkForOpponent() {{
            try {{
                const response = await fetch("/api/poll?game_no={game_no}&turn_no=0");
                const data = await response.json();
                if (data.opponent_joined) {{
                    window.location.href = "/game?game_no={game_no}&player={key}";
                    return;
                }}
            }} catch {{
                // Keep waiting and ask again
            }}
            setTimeout(checkForOpponent, 1000);
        }}
        setTimeout(checkForOpponent, 1000);
    </script>
</head>
<body>
    <main class="page-container">
        <div class="waiting-card">
            <div class="spinner"></div>
            <h1>Waiting for Opponent</h1>
            <p class="subtitle">The game starts as soon as another player joins from the lobby.</p>
        </div>
    </main>
</body>
</html>"""


def _script_json(data: dict) -> str:
    """Serialize data for an inline script, so no value can close the script element."""
    return json.dumps(data).replace("</", "<\\/")


def game_page(view: dict) -> str:
    """Render the main game page. game.js fills in the board, trays, clocks, and controls."""
    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Game {view["gameNo"]}</title>
    {COMMON_HEAD}
</head>
<body>
    <main class="game-container">
        <div class="game-header">
            <div>
                <h1>Hostage Chess</h1>
                <p class="game-subtitle">Game {view["gameNo"]}, playing {view["role"].capitalize()}</p>
            </div>
            <span class="status-badge" id="status-text" role="status"></span>
        </div>

        <div class="game-layout">
            <div class="side-panel opponent-panel">
                <h2>Opponent's Airfield</h2>
                <div class="piece-tray" id="opponent-airfield"></div>
                <h2>Opponent's Prison</h2>
                <div class="piece-tray" id="opponent-prison"></div>
            </div>

            <div class="board-area">
                <div class="timer-bar">
                    <div class="timer" id="black-timer">
                        <span class="timer-label">Black</span> <span id="blackTime"></span>
                    </div>
                    <div class="timer" id="white-timer">
                        <span class="timer-label">White</span> <span id="whiteTime"></span>
                    </div>
                </div>
                <div id="myBoard"></div>
                <div class="move-controls">
                    <button type="button" id="btn-drop" class="control-btn" disabled>Drop Piece</button>
                    <button type="button" id="btn-exchange" class="control-btn" disabled>
                        Exchange Hostage
                    </button>
                    <button type="button" id="btn-resign" class="control-btn danger">Resign</button>
                </div>
            </div>

            <div class="side-panel player-panel">
                <h2>Your Airfield</h2>
                <div class="piece-tray" id="player-airfield"></div>
                <h2>Your Prison</h2>
                <div class="piece-tray" id="player-prison"></div>
            </div>
        </div>
    </main>

    <dialog class="modal-card" id="exchange-modal" aria-labelledby="exchange-title">
        <h2 id="exchange-title">Hostage Exchange</h2>
        <p>Choose one of your pieces to rescue and a prisoner to pay for it.
           You then place the rescued piece on the board.</p>
        <div class="exchange-options" id="exchange-options"></div>
        <button type="button" class="control-btn" id="cancel-exchange">Cancel</button>
    </dialog>

    <dialog class="modal-card" id="promotion-modal" aria-labelledby="promotion-title">
        <h2 id="promotion-title">Pawn Promotion</h2>
        <p>Your pawn swaps places with one of your pieces held in your opponent's prison.</p>
        <div class="promotion-options" id="promotion-options"></div>
        <button type="button" class="control-btn" id="cancel-promotion">Cancel</button>
    </dialog>

    {COMMON_SCRIPTS}
    <script>
        window.GAME_CONFIG = {_script_json(view)};
    </script>
    <script src="/static/js/game.js"></script>
</body>
</html>"""


def game_over_page(game_no: int, result: str) -> str:
    """Render the game over page."""
    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Game {game_no} Over</title>
    {COMMON_HEAD}
</head>
<body>
    <main class="page-container">
        <div class="game-over-card">
            <div class="game-over-icon" aria-hidden="true">♚</div>
            <h1>Game Over</h1>
            <p class="result-text">{html.escape(result)}</p>
            <div class="game-over-links">
                <a href="/history" class="link-btn">Game History</a>
                <a href="/" class="link-btn primary">New Game</a>
            </div>
        </div>
    </main>
</body>
</html>"""


def history_page(games: list[dict]) -> str:
    """Render the game history page."""
    rows = "".join(
        f"""
                <tr>
                    <td><a href="/gamelog?game_no={game["game_no"]}">{game["game_no"]}</a></td>
                    <td>{html.escape(game["white_handle"])}</td>
                    <td>{html.escape(game["black_handle"] or "Waiting")}</td>
                    <td>{html.escape(game["result"] or "In progress")}</td>
                </tr>"""
        for game in games
    )
    if games:
        content = f"""<table>
                <thead><tr><th>Game</th><th>White</th><th>Black</th><th>Result</th></tr></thead>
                <tbody>{rows}
                </tbody>
            </table>"""
    else:
        content = '<p class="empty-msg">No games played yet.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | History</title>
    {COMMON_HEAD}
</head>
<body>
    <main class="page-container">
        <div class="history-card">
            <h1>Game History</h1>
            {content}
            <a href="/" class="link-btn primary">Back to Lobby</a>
        </div>
    </main>
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
                <h2>{label}</h2>
                <div id="board{turn_no}" class="log-board"></div>
            </div>"""

        boards_js += f"""
            boards.push(Chessboard("board{turn_no}", {{
                position: "{board_fen}",
                pieceTheme: "/static/img/Chess_Pieces_Sprite.svg#{{piece}}",
            }}));"""

    return f"""<!doctype html>
<html lang="en">
<head>
    <title>Hostage Chess | Game {game_no} Log</title>
    {COMMON_HEAD}
</head>
<body>
    <main class="page-container">
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
    </main>

    {COMMON_SCRIPTS}
    <script>
        $(() => {{
            const boards = [];
            {boards_js}
            $(window).on("resize", () => boards.forEach((board) => board.resize()));
        }});
    </script>
</body>
</html>"""
