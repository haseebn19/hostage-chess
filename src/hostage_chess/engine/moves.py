"""Legal board moves, check detection, and applying a move to the board."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, NamedTuple

from hostage_chess.engine.board import (
    WHITE,
    GameState,
    algebraic_to_indices,
    copy_state,
    in_bounds,
    is_empty,
    opponent,
    piece_at,
    piece_colour,
    prison,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class Move(NamedTuple):
    """A board move. `promotion` is the piece a pawn swaps places with on the last rank."""

    from_rank: int
    from_file: int
    to_rank: int
    to_file: int
    promotion: str | None = None


KNIGHT_OFFSETS = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
KING_OFFSETS = [(dr, df) for dr in (-1, 0, 1) for df in (-1, 0, 1) if (dr, df) != (0, 0)]
ROOK_DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]
BISHOP_DIRECTIONS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]


def _is_friendly(piece: str, colour: str) -> bool:
    return piece_colour(piece) == colour


def _is_enemy(piece: str, colour: str) -> bool:
    return piece_colour(piece) == opponent(colour)


def promotion_pieces(state: GameState, colour: str) -> list[str]:
    """Return the pieces a pawn of this colour can promote to.

    A pawn can only promote by swapping places with one of its side's queens, rooks, bishops,
    or knights held in the opponent's prison. Until one is there, the pawn cannot reach the
    last rank and does not attack it.
    """
    held = prison(state, opponent(colour))
    candidates = "QRBN" if colour == WHITE else "qrbn"
    return [piece for piece in candidates if piece in held]


def _pawn_moves(state: GameState, rank: int, file: int, colour: str) -> list[Move]:
    """Generate pseudo-legal pawn moves (forward, double, capture, en passant, promotion)."""
    moves: list[Move] = []
    direction = 1 if colour == WHITE else -1
    start_rank = 1 if colour == WHITE else 6
    promo_rank = 7 if colour == WHITE else 0
    to_rank = rank + direction

    def add(to_file: int) -> None:
        if to_rank == promo_rank:
            pieces = promotion_pieces(state, colour)
            moves.extend(Move(rank, file, to_rank, to_file, piece) for piece in pieces)
        else:
            moves.append(Move(rank, file, to_rank, to_file))

    # Single and double forward
    if in_bounds(to_rank, file) and is_empty(state, to_rank, file):
        add(file)
        double_rank = rank + 2 * direction
        if rank == start_rank and is_empty(state, double_rank, file):
            moves.append(Move(rank, file, double_rank, file))

    # Diagonal captures
    for to_file in (file - 1, file + 1):
        if in_bounds(to_rank, to_file) and _is_enemy(piece_at(state, to_rank, to_file), colour):
            add(to_file)

    # En passant
    if state.en_passant != "-":
        ep_rank, ep_file = algebraic_to_indices(state.en_passant)
        if to_rank == ep_rank and abs(file - ep_file) == 1:
            moves.append(Move(rank, file, ep_rank, ep_file))

    return moves


def _step_moves(
    state: GameState, rank: int, file: int, colour: str, offsets: list[tuple[int, int]]
) -> list[Move]:
    """Generate pseudo-legal single-step moves (knight, king)."""
    moves: list[Move] = []
    for dr, df in offsets:
        tr, tf = rank + dr, file + df
        if in_bounds(tr, tf) and not _is_friendly(piece_at(state, tr, tf), colour):
            moves.append(Move(rank, file, tr, tf))
    return moves


def _sliding_moves(
    state: GameState, rank: int, file: int, colour: str, directions: list[tuple[int, int]]
) -> list[Move]:
    """Generate pseudo-legal sliding moves (bishop, rook, queen)."""
    moves: list[Move] = []
    for dr, df in directions:
        tr, tf = rank + dr, file + df
        while in_bounds(tr, tf):
            target = piece_at(state, tr, tf)
            if _is_friendly(target, colour):
                break
            moves.append(Move(rank, file, tr, tf))
            if target != " ":
                break  # Captures end the slide
            tr += dr
            tf += df
    return moves


# Move generator for each piece type, called as generator(state, rank, file, colour)
PIECE_MOVES: dict[str, Callable[[GameState, int, int, str], list[Move]]] = {
    "P": _pawn_moves,
    "N": partial(_step_moves, offsets=KNIGHT_OFFSETS),
    "B": partial(_sliding_moves, directions=BISHOP_DIRECTIONS),
    "R": partial(_sliding_moves, directions=ROOK_DIRECTIONS),
    "Q": partial(_sliding_moves, directions=ROOK_DIRECTIONS + BISHOP_DIRECTIONS),
    "K": partial(_step_moves, offsets=KING_OFFSETS),
}


def _is_square_attacked(state: GameState, rank: int, file: int, by_colour: str) -> bool:
    """Return True if any piece of by_colour attacks the square.

    Used for check detection and castling validation.
    """

    def own(piece: str) -> str:
        return piece if by_colour == WHITE else piece.lower()

    def any_piece_at(offsets: list[tuple[int, int]], pieces: tuple[str, ...]) -> bool:
        return any(
            in_bounds(rank + dr, file + df) and piece_at(state, rank + dr, file + df) in pieces
            for dr, df in offsets
        )

    def any_slider(directions: list[tuple[int, int]], pieces: tuple[str, ...]) -> bool:
        for dr, df in directions:
            r, f = rank + dr, file + df
            while in_bounds(r, f) and is_empty(state, r, f):
                r += dr
                f += df
            if in_bounds(r, f) and piece_at(state, r, f) in pieces:
                return True
        return False

    # Pawns attack diagonally forward, so look one rank back from the attacker's point of view.
    # A pawn only attacks the last rank when it has a piece to promote to.
    pawn_rank = -1 if by_colour == WHITE else 1
    last_rank = 7 if by_colour == WHITE else 0
    pawns_attack = rank != last_rank or bool(promotion_pieces(state, by_colour))
    return (
        (pawns_attack and any_piece_at([(pawn_rank, -1), (pawn_rank, 1)], (own("P"),)))
        or any_piece_at(KNIGHT_OFFSETS, (own("N"),))
        or any_piece_at(KING_OFFSETS, (own("K"),))
        or any_slider(ROOK_DIRECTIONS, (own("R"), own("Q")))
        or any_slider(BISHOP_DIRECTIONS, (own("B"), own("Q")))
    )


def is_in_check(state: GameState, colour: str) -> bool:
    """Return True if the given colour's king is in check."""
    king_char = "K" if colour == WHITE else "k"
    for r in range(8):
        for f in range(8):
            if state.board[r][f] == king_char:
                return _is_square_attacked(state, r, f, opponent(colour))
    return False  # King not found (shouldn't happen in normal play)


def _castling_moves(state: GameState, colour: str) -> list[Move]:
    """Generate castling moves if available."""
    rank = 0 if colour == WHITE else 7
    king_char, rook_char = ("K", "R") if colour == WHITE else ("k", "r")
    kingside_right, queenside_right = ("K", "Q") if colour == WHITE else ("k", "q")
    enemy = opponent(colour)

    # The king must be on its starting square and not in check
    if piece_at(state, rank, 4) != king_char or _is_square_attacked(state, rank, 4, enemy):
        return []

    def can_castle(right: str, rook_file: int, empty_files: range, safe_files: range) -> bool:
        return (
            right in state.castling
            and piece_at(state, rank, rook_file) == rook_char
            and all(is_empty(state, rank, f) for f in empty_files)
            and not any(_is_square_attacked(state, rank, f, enemy) for f in safe_files)
        )

    moves: list[Move] = []
    if can_castle(kingside_right, 7, range(5, 7), range(5, 7)):
        moves.append(Move(rank, 4, rank, 6))
    if can_castle(queenside_right, 0, range(1, 4), range(2, 4)):
        moves.append(Move(rank, 4, rank, 2))
    return moves


def _generate_pseudo_legal_moves(state: GameState, colour: str) -> list[Move]:
    """Generate all pseudo-legal moves (may leave king in check)."""
    moves: list[Move] = []
    for r in range(8):
        for f in range(8):
            piece = state.board[r][f]
            if piece_colour(piece) == colour:
                moves.extend(PIECE_MOVES[piece.upper()](state, r, f, colour))
    moves.extend(_castling_moves(state, colour))
    return moves


def _is_en_passant(state: GameState, move: Move) -> bool:
    """Return True if the move is a pawn capturing en passant."""
    piece = state.board[move.from_rank][move.from_file]
    return (
        piece.upper() == "P"
        and move.from_file != move.to_file
        and is_empty(state, move.to_rank, move.to_file)
    )


def captured_piece(state: GameState, move: Move) -> str:
    """Return the piece the move captures, or ' ' if it captures nothing."""
    if _is_en_passant(state, move):
        # The captured pawn sits beside the capturing pawn, on the target file.
        return state.board[move.from_rank][move.to_file]
    return state.board[move.to_rank][move.to_file]


def apply_board_move(state: GameState, move: Move) -> GameState:
    """Return a copy of the state with the move played on the board and in the prisons.

    Captured pieces go to the mover's prison. A promoting pawn swaps places with the chosen
    piece in the opponent's prison. Castling rights, clocks, and the turn are left for
    `hostage.apply_move`, so this is also used to test whether a move leaves the king in check.
    """
    new_state = copy_state(state)
    board = new_state.board
    piece = board[move.from_rank][move.from_file]
    colour = piece_colour(piece)

    captured = captured_piece(state, move)
    if captured != " ":
        prison(new_state, colour).append(captured)
    if _is_en_passant(state, move):
        board[move.from_rank][move.to_file] = " "

    board[move.from_rank][move.from_file] = " "
    board[move.to_rank][move.to_file] = move.promotion or piece

    if move.promotion:
        held = prison(new_state, opponent(colour))
        held.remove(move.promotion)
        held.append(piece)

    # Castling also moves the rook to the square the king passed over
    if piece.upper() == "K" and abs(move.from_file - move.to_file) == 2:
        rook_from, rook_to = (7, 5) if move.to_file == 6 else (0, 3)
        board[move.from_rank][rook_to] = board[move.from_rank][rook_from]
        board[move.from_rank][rook_from] = " "

    return new_state


def get_legal_board_moves(state: GameState) -> list[Move]:
    """Generate all legal board moves for the active player.

    Filters out moves that would leave the king in check. Does not include drops or
    exchanges (see the hostage module).
    """
    colour = state.active
    return [
        move
        for move in _generate_pseudo_legal_moves(state, colour)
        if not is_in_check(apply_board_move(state, move), colour)
    ]


def has_legal_board_moves(state: GameState) -> bool:
    """Return True if the active player has at least one legal board move.

    Stops at the first legal move found.
    """
    colour = state.active
    return any(
        not is_in_check(apply_board_move(state, move), colour)
        for move in _generate_pseudo_legal_moves(state, colour)
    )
