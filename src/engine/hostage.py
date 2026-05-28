"""Hostage Chess-specific mechanics: captures, drops, exchanges, and move application.

In Hostage Chess, captured pieces go to the captor's prison. Players can:
1. Make a normal move (with captures going to prison)
2. Drop a piece from their airfield onto an empty square
3. Exchange a hostage: pay a piece from your prison to rescue one of your
   pieces from the opponent's prison, then immediately drop the rescued piece

Piece value hierarchy for exchanges: Q > R > B = N > P
"""

from __future__ import annotations

from src.engine.board import (
    BLACK,
    WHITE,
    GameState,
    copy_state,
    indices_to_algebraic,
    is_empty,
    piece_colour,
)
from src.engine.moves import Move, is_in_check

# Piece values for hostage exchange (higher = more valuable)
PIECE_VALUES = {
    "P": 1,
    "p": 1,
    "N": 3,
    "n": 3,
    "B": 3,
    "b": 3,
    "R": 5,
    "r": 5,
    "Q": 9,
    "q": 9,
    "K": 100,
    "k": 100,
}


# Special move types encoded as from_rank values
DROP_MOVE = -1  # Indicates a drop from airfield
EXCHANGE_MOVE = -2  # Indicates a hostage exchange


def get_drop_moves(state: GameState) -> list[tuple[int, int, int, int, str | None]]:
    """Generate all legal drop moves for the active player.

    A drop places a piece from your airfield onto any empty square.
    Pawns cannot be dropped on rank 1 or rank 8.

    Drop moves are encoded as (DROP_MOVE, airfield_index, to_rank, to_file, piece).
    """
    colour = state.active
    airfield = state.white_airfield if colour == WHITE else state.black_airfield
    moves: list[tuple[int, int, int, int, str | None]] = []

    for af_idx, piece in enumerate(airfield):
        for r in range(8):
            for f in range(8):
                if not is_empty(state, r, f):
                    continue
                # Pawns can't be dropped on rank 1 (idx 0) or rank 8 (idx 7)
                if piece.upper() == "P" and (r == 0 or r == 7):
                    continue
                # Check that the drop doesn't leave the king in check
                test_state = copy_state(state)
                test_state.board[r][f] = piece
                if not is_in_check(test_state, colour):
                    moves.append((DROP_MOVE, af_idx, r, f, piece))

    return moves


def get_exchange_options(state: GameState) -> list[dict]:
    """Get available hostage exchange options for the active player.

    Returns a list of dicts with:
    - 'rescue': piece to rescue from opponent's prison
    - 'rescue_idx': index in opponent's prison
    - 'payment': piece to pay from your own prison
    - 'payment_idx': index in your own prison
    - 'valid_drops': list of valid algebraic square coordinates for the drop

    Payment piece must have equal or greater value than rescued piece.
    The drop must not leave your own king in check.
    """
    colour = state.active
    if colour == WHITE:
        own_prison = state.white_prison  # Pieces white captured (black pieces)
        opponent_prison = state.black_prison  # Pieces black captured (white pieces)
    else:
        own_prison = state.black_prison
        opponent_prison = state.white_prison

    options: list[dict] = []

    for rescue_idx, rescue_piece in enumerate(opponent_prison):
        # Can only rescue your own pieces
        if piece_colour(rescue_piece) != colour:
            continue
        rescue_value = PIECE_VALUES.get(rescue_piece, 0)

        for payment_idx, payment_piece in enumerate(own_prison):
            payment_value = PIECE_VALUES.get(payment_piece, 0)
            if payment_value >= rescue_value:
                from src.engine.moves import is_in_check

                valid_drops = []
                for r in range(8):
                    for f in range(8):
                        if state.board[r][f] == " ":
                            if rescue_piece.upper() == "P" and (r == 0 or r == 7):
                                continue

                            test_state = apply_exchange(state, rescue_idx, payment_idx, r, f)
                            if not is_in_check(test_state, colour):
                                valid_drops.append(indices_to_algebraic(r, f))

                if valid_drops:
                    options.append(
                        {
                            "rescue": rescue_piece,
                            "rescue_idx": rescue_idx,
                            "payment": payment_piece,
                            "payment_idx": payment_idx,
                            "valid_drops": valid_drops,
                        }
                    )

    return options


def apply_move(state: GameState, move: Move) -> GameState:
    """Apply a normal board move and handle hostage capture mechanics.

    Captured pieces go to the captor's prison. Also updates castling rights,
    en passant, and move counters.
    """
    from_r, from_f, to_r, to_f, promotion = move
    colour = state.active
    new_state = copy_state(state)
    piece = new_state.board[from_r][from_f]
    captured = new_state.board[to_r][to_f]

    # Handle en passant capture
    is_en_passant = (
        piece.upper() == "P" and from_f != to_f and captured == " " and state.en_passant != "-"
    )
    if is_en_passant:
        ep_capture_rank = to_r - 1 if piece == "P" else to_r + 1
        captured = new_state.board[ep_capture_rank][to_f]
        new_state.board[ep_capture_rank][to_f] = " "

    # Place captured piece in captor's prison
    if captured != " ":
        if colour == WHITE:
            new_state.white_prison.append(captured)
        else:
            new_state.black_prison.append(captured)

    # Move the piece
    new_state.board[from_r][from_f] = " "
    new_state.board[to_r][to_f] = promotion if promotion else piece

    # Handle castling rook movement
    if piece.upper() == "K" and abs(from_f - to_f) == 2:
        if to_f == 6:  # Kingside
            rook = new_state.board[from_r][7]
            new_state.board[from_r][7] = " "
            new_state.board[from_r][5] = rook
        elif to_f == 2:  # Queenside
            rook = new_state.board[from_r][0]
            new_state.board[from_r][0] = " "
            new_state.board[from_r][3] = rook

    # Update castling rights
    new_state.castling = _update_castling(state.castling, piece, from_r, from_f, to_r, to_f)

    # Update en passant target
    if piece.upper() == "P" and abs(to_r - from_r) == 2:
        ep_rank = (from_r + to_r) // 2
        new_state.en_passant = indices_to_algebraic(ep_rank, from_f)
    else:
        new_state.en_passant = "-"

    # Update move counters
    if piece.upper() == "P" or captured != " ":
        new_state.halfmove = 0
    else:
        new_state.halfmove = state.halfmove + 1

    if colour == BLACK:
        new_state.fullmove = state.fullmove + 1

    # Switch active player
    new_state.active = BLACK if colour == WHITE else WHITE

    return new_state


def apply_drop(state: GameState, airfield_idx: int, to_rank: int, to_file: int) -> GameState:
    """Apply a drop move: place a piece from the airfield onto an empty square."""
    colour = state.active
    new_state = copy_state(state)

    if colour == WHITE:
        piece = new_state.white_airfield.pop(airfield_idx)
    else:
        piece = new_state.black_airfield.pop(airfield_idx)

    new_state.board[to_rank][to_file] = piece

    # Reset en passant (drops don't create en passant opportunities)
    new_state.en_passant = "-"

    # Increment halfmove clock (drops are not captures or pawn moves)
    new_state.halfmove = state.halfmove + 1

    if colour == BLACK:
        new_state.fullmove = state.fullmove + 1

    new_state.active = BLACK if colour == WHITE else WHITE
    return new_state


def apply_exchange(
    state: GameState,
    rescue_idx: int,
    payment_idx: int,
    drop_rank: int,
    drop_file: int,
) -> GameState:
    """Apply a hostage exchange: pay a piece to rescue a hostage, then drop it.

    Args:
        state: Current game state
        rescue_idx: Index of piece to rescue from opponent's prison
        payment_idx: Index of piece to pay from own prison
        drop_rank: Rank to drop the rescued piece
        drop_file: File to drop the rescued piece
    """
    colour = state.active
    new_state = copy_state(state)

    if colour == WHITE:
        # Rescue white piece from black's prison
        rescued = new_state.black_prison.pop(rescue_idx)
        # Pay with a piece from white's prison → goes to black's airfield
        payment = new_state.white_prison.pop(payment_idx)
        new_state.black_airfield.append(payment)
    else:
        # Rescue black piece from white's prison
        rescued = new_state.white_prison.pop(rescue_idx)
        # Pay with a piece from black's prison → goes to white's airfield
        payment = new_state.black_prison.pop(payment_idx)
        new_state.white_airfield.append(payment)

    # Drop the rescued piece onto the board
    new_state.board[drop_rank][drop_file] = rescued

    new_state.en_passant = "-"
    new_state.halfmove = state.halfmove + 1
    if colour == BLACK:
        new_state.fullmove = state.fullmove + 1

    new_state.active = BLACK if colour == WHITE else WHITE
    return new_state


def _update_castling(
    castling: str, piece: str, from_r: int, from_f: int, to_r: int, to_f: int
) -> str:
    """Update castling rights after a move."""
    if castling == "-":
        return "-"

    rights = set(castling)

    # King moves remove both castling rights for that colour
    if piece == "K":
        rights.discard("K")
        rights.discard("Q")
    elif piece == "k":
        rights.discard("k")
        rights.discard("q")

    # Rook moves or captures remove the specific castling right
    # White rooks
    if (from_r == 0 and from_f == 0) or (to_r == 0 and to_f == 0):
        rights.discard("Q")
    if (from_r == 0 and from_f == 7) or (to_r == 0 and to_f == 7):
        rights.discard("K")
    # Black rooks
    if (from_r == 7 and from_f == 0) or (to_r == 7 and to_f == 0):
        rights.discard("q")
    if (from_r == 7 and from_f == 7) or (to_r == 7 and to_f == 7):
        rights.discard("k")

    if not rights:
        return "-"

    # Maintain canonical order
    return "".join(c for c in "KQkq" if c in rights)
