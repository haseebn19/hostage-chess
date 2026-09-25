"""SQLite database operations for game storage and retrieval."""

from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# Created in the working directory the server is started from. Tests point it at a temporary file.
DB_PATH = Path("hostage_chess.db")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open a connection to `DB_PATH`, commit on success, and always close it."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create the database tables if they do not exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS games (
                game_no INTEGER PRIMARY KEY AUTOINCREMENT,
                white_handle TEXT NOT NULL,
                black_handle TEXT,
                result TEXT,
                white_key TEXT,
                black_key TEXT
            )
        """)
        # Databases made before players had keys lack these columns
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(games)")}
        for column in ("white_key", "black_key"):
            if column not in columns:
                conn.execute(f"ALTER TABLE games ADD COLUMN {column} TEXT")
        conn.execute("""
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


def create_game(handle: str, key: str) -> int:
    """Create a game with the player as white, waiting for an opponent, and return its number."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO games (white_handle, white_key) VALUES (?, ?)", (handle, key)
        )
        return cursor.lastrowid


def _insert_turn(
    conn: sqlite3.Connection,
    game_no: int,
    turn_no: int,
    turn: str,
    board_fen: str,
    hostage_state: dict,
    white_time: int,
    black_time: int,
) -> None:
    conn.execute(
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


def join_waiting_game(
    handle: str,
    key: str,
    board_fen: str,
    hostage_state: dict,
    game_time: int,
) -> int | None:
    """Join the oldest game waiting for a second player, as black, and save its first turn.

    Returns the game number, or None if no game is waiting. Claiming the game is a single
    UPDATE, so two players joining at the same moment can never get the same game.
    """
    with _connect() as conn:
        row = conn.execute(
            """
            UPDATE games SET black_handle = ?, black_key = ?
            WHERE game_no = (SELECT MIN(game_no) FROM games WHERE black_handle IS NULL)
            RETURNING game_no
            """,
            (handle, key),
        ).fetchone()
        if row is None:
            return None
        _insert_turn(conn, row["game_no"], 1, "w", board_fen, hostage_state, game_time, game_time)
    return row["game_no"]


def get_player_role(game_no: int, key: str) -> str | None:
    """Return "white" or "black" for the player the key belongs to, or None if it is not theirs."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT white_key, black_key FROM games WHERE game_no = ?", (game_no,)
        ).fetchone()
    if row is None:
        return None
    for role in ("white", "black"):
        stored = row[f"{role}_key"]
        if stored is not None and secrets.compare_digest(stored, key):
            return role
    return None


def get_black_handle(game_no: int) -> str | None:
    """Return the black player's handle, or None while the game waits for an opponent."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT black_handle FROM games WHERE game_no = ?", (game_no,)
        ).fetchone()
    return row["black_handle"] if row else None


def _turn_from_row(row: sqlite3.Row) -> dict:
    return {**row, "hostage_state": json.loads(row["hostage_state"])}


def get_turn(game_no: int, turn_no: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT turn, board_fen, hostage_state, real_time, white_time, black_time
            FROM boards WHERE game_no = ? AND turn_no = ?
            """,
            (game_no, turn_no),
        ).fetchone()
    return _turn_from_row(row) if row else None


def get_latest_turn_no(game_no: int) -> int | None:
    """Return the latest turn number for a game, or None if the game has not started."""
    with _connect() as conn:
        return conn.execute(
            "SELECT MAX(turn_no) FROM boards WHERE game_no = ?", (game_no,)
        ).fetchone()[0]


def save_turn(
    game_no: int,
    turn_no: int,
    turn: str,
    board_fen: str,
    hostage_state: dict,
    white_time: int,
    black_time: int,
) -> None:
    with _connect() as conn:
        _insert_turn(conn, game_no, turn_no, turn, board_fen, hostage_state, white_time, black_time)


def get_result(game_no: int) -> str | None:
    """Return the result of a game, or None while it is in progress."""
    with _connect() as conn:
        row = conn.execute("SELECT result FROM games WHERE game_no = ?", (game_no,)).fetchone()
    return row["result"] if row else None


def set_result(game_no: int, result: str) -> str | None:
    """Record the result unless the game already has one, and return the game's result.

    The check and the write are one UPDATE, so when two requests end a game at the same
    moment, the first result stands.
    """
    with _connect() as conn:
        conn.execute(
            "UPDATE games SET result = ? WHERE game_no = ? AND result IS NULL", (result, game_no)
        )
        row = conn.execute("SELECT result FROM games WHERE game_no = ?", (game_no,)).fetchone()
    return row["result"] if row else None


def get_game_history() -> list[dict]:
    """Return every game for the history page, newest first.

    `black_handle` is None while a game waits for a second player, and `result` is None
    while a game is in progress.
    """
    with _connect() as conn:
        games = conn.execute(
            "SELECT game_no, white_handle, black_handle, result FROM games ORDER BY game_no DESC"
        ).fetchall()
    return [dict(game) for game in games]


def get_game_log(game_no: int) -> list[dict]:
    """Return every turn of a game, in order."""
    with _connect() as conn:
        turns = conn.execute(
            """
            SELECT turn_no, turn, board_fen, hostage_state, real_time, white_time, black_time
            FROM boards WHERE game_no = ? ORDER BY turn_no
            """,
            (game_no,),
        ).fetchall()
    return [_turn_from_row(turn) for turn in turns]
