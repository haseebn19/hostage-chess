"""Hostage Chess mechanics: captures, drops, exchanges, and move application.

In Hostage Chess, captured pieces go to the captor's prison. On their turn a player can:
1. Make a normal move (with captures going to prison)
2. Drop a piece from their airfield onto an empty square
3. Exchange a hostage: pay a piece from their prison to rescue one of their own pieces
   from the opponent's prison, then immediately drop the rescued piece

The payment must be worth at least as much as the rescued piece: Q > R > B = N > P.
A rook dropped on its starting square can castle if its king has never moved.
"""

from __future__ import annotations

from typing import NamedTuple, TypedDict

from hostage_chess.engine.board import (
    BLACK,
    GameState,
    airfield,
    copy_state,
    indices_to_algebraic,
    is_empty,
    opponent,
    prison,
)
from hostage_chess.engine.moves import Move, apply_board_move, captured_piece, is_in_check

# Piece values for hostage exchanges (higher = more valuable). Kings are never captured.
PIECE_VALUES = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9}

# The castling right lost when a piece leaves or is captured on each rook's starting square
CASTLING_CORNERS = {(0, 0): "Q", (0, 7): "K", (7, 0): "q", (7, 7): "k"}


class Drop(NamedTuple):
    """Dropping the piece at `airfield_idx` in the player's airfield onto an empty square."""

    airfield_idx: int
    to_rank: int
    to_file: int
    piece: str


class ExchangeOption(TypedDict):
    """A hostage exchange the player can make, with the squares the rescued piece can land on."""

    rescue: str
    rescue_idx: int
    payment: str
    payment_idx: int
    valid_drops: list[str]


def _drop_squares(state: GameState, piece: str) -> list[tuple[int, int]]:
    """Return the empty squares where the active player can drop the piece.

    Pawns cannot be dropped on the first or last rank, and a drop must not leave the
    player's own king in check.
    """
    squares: list[tuple[int, int]] = []
    for r in range(8):
        if piece.upper() == "P" and r in (0, 7):
            continue
        for f in range(8):
            if not is_empty(state, r, f):
                continue
            test_state = copy_state(state)
            test_state.board[r][f] = piece
            if not is_in_check(test_state, state.active):
                squares.append((r, f))
    return squares


def get_drop_moves(state: GameState) -> list[Drop]:
    """Generate all legal drops from the active player's airfield."""
    pieces = airfield(state, state.active)
    squares_for = {piece: _drop_squares(state, piece) for piece in set(pieces)}
    return [
        Drop(airfield_idx, r, f, piece)
        for airfield_idx, piece in enumerate(pieces)
        for r, f in squares_for[piece]
    ]


def _pay_ransom(state: GameState, rescue_idx: int, payment_idx: int) -> tuple[GameState, str]:
    """Return a copy of the state with the exchange made in the prisons, and the rescued piece.

    The payment goes to the opponent's airfield, ready for them to drop.
    """
    colour = state.active
    new_state = copy_state(state)
    rescued = prison(new_state, opponent(colour)).pop(rescue_idx)
    airfield(new_state, opponent(colour)).append(prison(new_state, colour).pop(payment_idx))
    return new_state, rescued


def get_exchange_options(state: GameState) -> list[ExchangeOption]:
    """Get the hostage exchanges available to the active player.

    Each option rescues one of the player's pieces from the opponent's prison by paying a
    piece of equal or greater value from the player's own prison. Options are only listed
    when the rescued piece has at least one legal drop square, and identical pairs of
    pieces are listed once.
    """
    colour = state.active
    hostages = prison(state, opponent(colour))  # The player's pieces the opponent captured
    payments = prison(state, colour)  # The opponent's pieces the player captured

    options: list[ExchangeOption] = []
    seen: set[tuple[str, str]] = set()

    for rescue_idx, rescue in enumerate(hostages):
        for payment_idx, payment in enumerate(payments):
            if (rescue, payment) in seen:
                continue
            if PIECE_VALUES[payment.upper()] < PIECE_VALUES[rescue.upper()]:
                continue
            seen.add((rescue, payment))

            # The prisons decide which pawns can promote, and so which squares they attack
            ransomed, _ = _pay_ransom(state, rescue_idx, payment_idx)
            valid_drops = [indices_to_algebraic(r, f) for r, f in _drop_squares(ransomed, rescue)]
            if valid_drops:
                options.append(
                    {
                        "rescue": rescue,
                        "rescue_idx": rescue_idx,
                        "payment": payment,
                        "payment_idx": payment_idx,
                        "valid_drops": valid_drops,
                    }
                )

    return options


def _end_turn(
    new_state: GameState, en_passant: str = "-", reset_halfmove: bool = False
) -> GameState:
    """Update the en passant square and move counters, then pass the turn to the opponent."""
    new_state.en_passant = en_passant
    new_state.halfmove = 0 if reset_halfmove else new_state.halfmove + 1
    if new_state.active == BLACK:
        new_state.fullmove += 1
    new_state.active = opponent(new_state.active)
    return new_state


def apply_move(state: GameState, move: Move) -> GameState:
    """Apply a board move, then update castling rights, the en passant square, and the clocks."""
    piece = state.board[move.from_rank][move.from_file]
    captured = captured_piece(state, move)
    new_state = apply_board_move(state, move)

    new_state.castling = _update_castling(state.castling, piece, move)
    if piece == "K":
        new_state.white_king_moved = True
    elif piece == "k":
        new_state.black_king_moved = True

    en_passant = "-"
    if piece.upper() == "P" and abs(move.to_rank - move.from_rank) == 2:
        en_passant = indices_to_algebraic((move.from_rank + move.to_rank) // 2, move.from_file)

    return _end_turn(
        new_state, en_passant=en_passant, reset_halfmove=piece.upper() == "P" or captured != " "
    )


def _place(state: GameState, piece: str, rank: int, file: int) -> None:
    """Drop a piece on the board, giving a rook on its starting square its castling right."""
    state.board[rank][file] = piece
    right = CASTLING_CORNERS.get((rank, file))
    king_moved = state.white_king_moved if piece.isupper() else state.black_king_moved
    if piece.upper() == "R" and right and right.isupper() == piece.isupper() and not king_moved:
        state.castling = "".join(c for c in "KQkq" if c in state.castling or c == right)


def apply_drop(state: GameState, airfield_idx: int, to_rank: int, to_file: int) -> GameState:
    """Drop the piece at `airfield_idx` in the player's airfield onto an empty square."""
    new_state = copy_state(state)
    _place(new_state, airfield(new_state, state.active).pop(airfield_idx), to_rank, to_file)
    return _end_turn(new_state)


def apply_exchange(
    state: GameState, rescue_idx: int, payment_idx: int, drop_rank: int, drop_file: int
) -> GameState:
    """Pay the prisoner at `payment_idx` to rescue the hostage at `rescue_idx`, then drop it."""
    new_state, rescued = _pay_ransom(state, rescue_idx, payment_idx)
    _place(new_state, rescued, drop_rank, drop_file)
    return _end_turn(new_state)


def _update_castling(castling: str, piece: str, move: Move) -> str:
    """Remove the castling rights lost by this move.

    Moving the king loses both of that side's rights. Moving a piece from, or capturing on,
    a rook's starting square loses the right that uses that rook.
    """
    rights = set(castling) - {"-"}

    if piece == "K":
        rights -= {"K", "Q"}
    elif piece == "k":
        rights -= {"k", "q"}

    for square in ((move.from_rank, move.from_file), (move.to_rank, move.to_file)):
        rights.discard(CASTLING_CORNERS.get(square, ""))

    # Keep the standard FEN order
    return "".join(c for c in "KQkq" if c in rights) or "-"
