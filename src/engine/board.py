"""Board state representation, FEN conversion, and serialisation for Hostage Chess."""

from __future__ import annotations

from dataclasses import dataclass, field

# Piece characters: uppercase = white, lowercase = black
# K/k = King, Q/q = Queen, R/r = Rook, B/b = Bishop, N/n = Knight, P/p = Pawn

INITIAL_BOARD = [
    ["R", "N", "B", "Q", "K", "B", "N", "R"],  # rank 1 (white back rank)
    ["P", "P", "P", "P", "P", "P", "P", "P"],  # rank 2 (white pawns)
    [" ", " ", " ", " ", " ", " ", " ", " "],  # rank 3
    [" ", " ", " ", " ", " ", " ", " ", " "],  # rank 4
    [" ", " ", " ", " ", " ", " ", " ", " "],  # rank 5
    [" ", " ", " ", " ", " ", " ", " ", " "],  # rank 6
    ["p", "p", "p", "p", "p", "p", "p", "p"],  # rank 7 (black pawns)
    ["r", "n", "b", "q", "k", "b", "n", "r"],  # rank 8 (black back rank)
]

WHITE = "w"
BLACK = "b"


@dataclass
class GameState:
    """Complete state of a Hostage Chess game.

    Board indexing: board[rank][file] where rank 0 = rank 1 (white's back rank),
    file 0 = a-file.
    """

    board: list[list[str]] = field(default_factory=lambda: [row[:] for row in INITIAL_BOARD])

    # Pieces captured by white (held in white's prison)
    white_prison: list[str] = field(default_factory=list)
    # Pieces rescued/available for white to drop (white's airfield)
    white_airfield: list[str] = field(default_factory=list)
    # Pieces captured by black (held in black's prison)
    black_prison: list[str] = field(default_factory=list)
    # Pieces rescued/available for black to drop (black's airfield)
    black_airfield: list[str] = field(default_factory=list)

    active: str = WHITE  # 'w' or 'b'
    castling: str = "KQkq"  # Available castling rights
    en_passant: str = "-"  # En passant target square in algebraic, or '-'
    halfmove: int = 0  # Halfmove clock (for 50-move rule)
    fullmove: int = 1  # Fullmove counter (increments after black's turn)


def new_game() -> GameState:
    """Create a fresh game state with the standard starting position."""
    return GameState()


def piece_at(state: GameState, rank: int, file: int) -> str:
    """Return the piece character at the given board position, or ' ' if empty."""
    return state.board[rank][file]


def is_white_piece(piece: str) -> bool:
    """Return True if the piece character represents a white piece."""
    return piece.isupper() and piece != " "


def is_black_piece(piece: str) -> bool:
    """Return True if the piece character represents a black piece."""
    return piece.islower() and piece != " "


def piece_colour(piece: str) -> str | None:
    """Return 'w' for white pieces, 'b' for black pieces, None for empty."""
    if is_white_piece(piece):
        return WHITE
    if is_black_piece(piece):
        return BLACK
    return None


def is_empty(state: GameState, rank: int, file: int) -> bool:
    """Return True if the given square is empty."""
    return state.board[rank][file] == " "


def in_bounds(rank: int, file: int) -> bool:
    """Return True if the rank and file are within the 8x8 board."""
    return 0 <= rank < 8 and 0 <= file < 8


def board_to_fen_placement(board: list[list[str]]) -> str:
    """Convert an 8x8 board array to a FEN piece placement string.

    Board is indexed [rank][file] with rank 0 = rank 1 (white's back rank).
    FEN reads from rank 8 (index 7) down to rank 1 (index 0).
    """
    ranks = []
    for rank_idx in range(7, -1, -1):
        fen_rank = ""
        empty_count = 0
        for file_idx in range(8):
            piece = board[rank_idx][file_idx]
            if piece == " ":
                empty_count += 1
            else:
                if empty_count > 0:
                    fen_rank += str(empty_count)
                    empty_count = 0
                fen_rank += piece
        if empty_count > 0:
            fen_rank += str(empty_count)
        ranks.append(fen_rank)
    return "/".join(ranks)


def fen_placement_to_board(placement: str) -> list[list[str]]:
    """Convert a FEN piece placement string to an 8x8 board array."""
    board = [[" "] * 8 for _ in range(8)]
    ranks = placement.split("/")
    for fen_rank_idx, fen_rank in enumerate(ranks):
        rank_idx = 7 - fen_rank_idx  # FEN starts from rank 8
        file_idx = 0
        for char in fen_rank:
            if char.isdigit():
                file_idx += int(char)
            else:
                board[rank_idx][file_idx] = char
                file_idx += 1
    return board


def to_fen(state: GameState) -> str:
    """Convert a GameState to a full FEN string (board portion only, no hostage data)."""
    placement = board_to_fen_placement(state.board)
    return (
        f"{placement} {state.active} {state.castling} "
        f"{state.en_passant} {state.halfmove} {state.fullmove}"
    )


def from_fen(fen: str) -> GameState:
    """Create a GameState from a FEN string. Prisons and airfields start empty."""
    parts = fen.split()
    placement = parts[0]
    active = parts[1] if len(parts) > 1 else WHITE
    castling = parts[2] if len(parts) > 2 else "KQkq"
    en_passant = parts[3] if len(parts) > 3 else "-"
    halfmove = int(parts[4]) if len(parts) > 4 else 0
    fullmove = int(parts[5]) if len(parts) > 5 else 1

    board = fen_placement_to_board(placement)
    return GameState(
        board=board,
        active=active,
        castling=castling,
        en_passant=en_passant,
        halfmove=halfmove,
        fullmove=fullmove,
    )


def to_dict(state: GameState) -> dict:
    """Serialise a GameState to a JSON-compatible dictionary."""
    return {
        "fen": to_fen(state),
        "white_prison": state.white_prison[:],
        "white_airfield": state.white_airfield[:],
        "black_prison": state.black_prison[:],
        "black_airfield": state.black_airfield[:],
    }


def from_dict(data: dict) -> GameState:
    """Deserialise a GameState from a dictionary."""
    state = from_fen(data["fen"])
    state.white_prison = data.get("white_prison", [])[:]
    state.white_airfield = data.get("white_airfield", [])[:]
    state.black_prison = data.get("black_prison", [])[:]
    state.black_airfield = data.get("black_airfield", [])[:]
    return state


def copy_state(state: GameState) -> GameState:
    """Create a deep copy of a GameState."""
    return GameState(
        board=[row[:] for row in state.board],
        white_prison=state.white_prison[:],
        white_airfield=state.white_airfield[:],
        black_prison=state.black_prison[:],
        black_airfield=state.black_airfield[:],
        active=state.active,
        castling=state.castling,
        en_passant=state.en_passant,
        halfmove=state.halfmove,
        fullmove=state.fullmove,
    )


def algebraic_to_indices(square: str) -> tuple[int, int]:
    """Convert algebraic notation (e.g. 'e4') to (rank, file) indices."""
    file_idx = ord(square[0]) - ord("a")
    rank_idx = int(square[1]) - 1
    return rank_idx, file_idx


def indices_to_algebraic(rank: int, file: int) -> str:
    """Convert (rank, file) indices to algebraic notation."""
    return chr(file + ord("a")) + str(rank + 1)
