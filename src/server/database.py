"""SQLite database operations for game storage and retrieval."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DB_PATH = Path("hostage_chess.db")


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create a database connection."""
    return sqlite3.connect(str(db_path))


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Initialise the database schema."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_no INTEGER PRIMARY KEY AUTOINCREMENT,
            white_handle TEXT NOT NULL,
            black_handle TEXT,
            result TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS boards (
            game_no INTEGER NOT NULL,
            turn_no INTEGER NOT NULL,
            turn TEXT NOT NULL,
            board_fen TEXT NOT NULL,
            hostage_state TEXT NOT NULL,
            real_time TEXT NOT NULL,
            white_time INTEGER NOT NULL,
            black_time INTEGER NOT NULL,
            PRIMARY KEY (game_no, turn_no),
            FOREIGN KEY (game_no) REFERENCES games(game_no)
        )
    """)

    conn.commit()
    conn.close()


def create_game(handle: str, db_path: Path = DEFAULT_DB_PATH) -> int:
    """Create a new game with the given player as white. Returns game_no."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO games (white_handle) VALUES (?)", (handle,))
    game_no = cursor.lastrowid
    conn.commit()
    conn.close()
    return game_no


def find_waiting_game(db_path: Path = DEFAULT_DB_PATH) -> int | None:
    """Find a game waiting for a second player. Returns game_no or None."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT game_no FROM games WHERE black_handle IS NULL")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def join_game(
    game_no: int,
    handle: str,
    board_fen: str,
    hostage_state: dict,
    game_time: int,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Join an existing game as black and save the initial board state."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("UPDATE games SET black_handle = ? WHERE game_no = ?", (handle, game_no))

    cursor.execute(
        """
        INSERT INTO boards (game_no, turn_no, turn, board_fen, hostage_state,
                           real_time, white_time, black_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_no,
            1,
            "w",
            board_fen,
            json.dumps(hostage_state),
            datetime.now(UTC).isoformat(),
            game_time,
            game_time,
        ),
    )

    conn.commit()
    conn.close()


def get_black_handle(game_no: int, db_path: Path = DEFAULT_DB_PATH) -> str | None:
    """Get the black player's handle for a game."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT black_handle FROM games WHERE game_no = ?", (game_no,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_turn(game_no: int, turn_no: int, db_path: Path = DEFAULT_DB_PATH) -> dict | None:
    """Get a specific turn's data."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT turn, board_fen, hostage_state, real_time, white_time, black_time
        FROM boards WHERE game_no = ? AND turn_no = ?
        """,
        (game_no, turn_no),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "turn": row[0],
        "board_fen": row[1],
        "hostage_state": json.loads(row[2]),
        "real_time": row[3],
        "white_time": row[4],
        "black_time": row[5],
    }


def get_latest_turn_no(game_no: int, db_path: Path = DEFAULT_DB_PATH) -> int | None:
    """Get the latest turn number for a game."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(turn_no) FROM boards WHERE game_no = ?", (game_no,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else None


def save_turn(
    game_no: int,
    turn_no: int,
    turn: str,
    board_fen: str,
    hostage_state: dict,
    white_time: int,
    black_time: int,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Save a new turn to the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO boards (game_no, turn_no, turn, board_fen, hostage_state,
                           real_time, white_time, black_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_no,
            turn_no,
            turn,
            board_fen,
            json.dumps(hostage_state),
            datetime.now(UTC).isoformat(),
            white_time,
            black_time,
        ),
    )
    conn.commit()
    conn.close()


def get_result(game_no: int, db_path: Path = DEFAULT_DB_PATH) -> str | None:
    """Get the result of a game."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT result FROM games WHERE game_no = ?", (game_no,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def set_result(game_no: int, result: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Set the result of a game."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE games SET result = ? WHERE game_no = ?", (result, game_no))
    conn.commit()
    conn.close()


def get_game_history(db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Get all games for the history page."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT game_no, white_handle, black_handle, result FROM games ORDER BY game_no DESC"
    )
    games = cursor.fetchall()
    conn.close()

    return [
        {
            "game_no": g[0],
            "white_handle": g[1],
            "black_handle": g[2] or "N/A",
            "result": g[3] or "In Progress",
        }
        for g in games
    ]


def get_game_log(game_no: int, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Get all turns for a specific game."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT turn_no, turn, board_fen, hostage_state, real_time, white_time, black_time
        FROM boards WHERE game_no = ? ORDER BY turn_no
        """,
        (game_no,),
    )
    turns = cursor.fetchall()
    conn.close()

    return [
        {
            "turn_no": t[0],
            "turn": t[1],
            "board_fen": t[2],
            "hostage_state": json.loads(t[3]),
            "real_time": t[4],
            "white_time": t[5],
            "black_time": t[6],
        }
        for t in turns
    ]
