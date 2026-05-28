"""Legal move generation for all chess pieces.

Move format: (from_rank, from_file, to_rank, to_file, promotion)
- promotion is None for non-promotion moves, or a piece character ('Q', 'R', 'B', 'N').
"""

from __future__ import annotations

from src.engine.board import (
    BLACK,
    WHITE,
    GameState,
    copy_state,
    in_bounds,
    is_empty,
    piece_at,
    piece_colour,
)

# Type alias for a move tuple
Move = tuple[int, int, int, int, str | None]


def _opponent(colour: str) -> str:
    """Return the opponent's colour."""
    return BLACK if colour == WHITE else WHITE


def _is_friendly(piece: str, colour: str) -> bool:
    """Return True if the piece belongs to the given colour."""
    return piece_colour(piece) == colour


def _is_enemy(piece: str, colour: str) -> bool:
    """Return True if the piece belongs to the opponent."""
    pc = piece_colour(piece)
    return pc is not None and pc != colour


def _pawn_moves(state: GameState, rank: int, file: int, colour: str) -> list[Move]:
    """Generate pseudo-legal pawn moves (forward, double, capture, en passant, promotion)."""
    moves: list[Move] = []
    direction = 1 if colour == WHITE else -1
    start_rank = 1 if colour == WHITE else 6
    promo_rank = 7 if colour == WHITE else 0
    promo_pieces = ["Q", "R", "B", "N"] if colour == WHITE else ["q", "r", "b", "n"]

    # Single forward
    to_rank = rank + direction
    if in_bounds(to_rank, file) and is_empty(state, to_rank, file):
        if to_rank == promo_rank:
            for promo in promo_pieces:
                moves.append((rank, file, to_rank, file, promo))
        else:
            moves.append((rank, file, to_rank, file, None))
            # Double forward from starting position
            double_rank = rank + 2 * direction
            if rank == start_rank and is_empty(state, double_rank, file):
                moves.append((rank, file, double_rank, file, None))

    # Captures (diagonal)
    for df in [-1, 1]:
        to_file = file + df
        if not in_bounds(to_rank, to_file):
            continue
        target = piece_at(state, to_rank, to_file)
        if _is_enemy(target, colour):
            if to_rank == promo_rank:
                for promo in promo_pieces:
                    moves.append((rank, file, to_rank, to_file, promo))
            else:
                moves.append((rank, file, to_rank, to_file, None))

    # En passant
    if state.en_passant != "-":
        ep_file = ord(state.en_passant[0]) - ord("a")
        ep_rank = int(state.en_passant[1]) - 1
        if to_rank == ep_rank and abs(file - ep_file) == 1:
            moves.append((rank, file, ep_rank, ep_file, None))

    return moves


def _knight_moves(state: GameState, rank: int, file: int, colour: str) -> list[Move]:
    """Generate pseudo-legal knight moves."""
    offsets = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
    moves: list[Move] = []
    for dr, df in offsets:
        tr, tf = rank + dr, file + df
        if in_bounds(tr, tf) and not _is_friendly(piece_at(state, tr, tf), colour):
            moves.append((rank, file, tr, tf, None))
    return moves


def _sliding_moves(
    state: GameState,
    rank: int,
    file: int,
    colour: str,
    directions: list[tuple[int, int]],
) -> list[Move]:
    """Generate pseudo-legal sliding moves (bishop, rook, queen)."""
    moves: list[Move] = []
    for dr, df in directions:
        tr, tf = rank + dr, file + df
        while in_bounds(tr, tf):
            target = piece_at(state, tr, tf)
            if target == " ":
                moves.append((rank, file, tr, tf, None))
            elif _is_enemy(target, colour):
                moves.append((rank, file, tr, tf, None))
                break
            else:
                break  # Friendly piece blocks
            tr += dr
            tf += df
    return moves


def _bishop_moves(state: GameState, rank: int, file: int, colour: str) -> list[Move]:
    """Generate pseudo-legal bishop moves."""
    return _sliding_moves(state, rank, file, colour, [(-1, -1), (-1, 1), (1, -1), (1, 1)])


def _rook_moves(state: GameState, rank: int, file: int, colour: str) -> list[Move]:
    """Generate pseudo-legal rook moves."""
    return _sliding_moves(state, rank, file, colour, [(-1, 0), (1, 0), (0, -1), (0, 1)])


def _queen_moves(state: GameState, rank: int, file: int, colour: str) -> list[Move]:
    """Generate pseudo-legal queen moves."""
    return _sliding_moves(
        state,
        rank,
        file,
        colour,
        [(-1, -1), (-1, 1), (1, -1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1)],
    )


def _king_normal_moves(state: GameState, rank: int, file: int, colour: str) -> list[Move]:
    """Generate pseudo-legal king moves (one square, no castling)."""
    moves: list[Move] = []
    for dr in [-1, 0, 1]:
        for df in [-1, 0, 1]:
            if dr == 0 and df == 0:
                continue
            tr, tf = rank + dr, file + df
            if in_bounds(tr, tf) and not _is_friendly(piece_at(state, tr, tf), colour):
                moves.append((rank, file, tr, tf, None))
    return moves


def _is_square_attacked(state: GameState, rank: int, file: int, by_colour: str) -> bool:
    """Return True if the given square is attacked by any piece of by_colour.

    This is used for check detection and castling validation.
    """
    # Pawn attacks
    pawn_dir = -1 if by_colour == WHITE else 1  # Direction pawns attack FROM
    pawn_char = "P" if by_colour == WHITE else "p"
    for df in [-1, 1]:
        pr, pf = rank + pawn_dir, file + df
        if in_bounds(pr, pf) and piece_at(state, pr, pf) == pawn_char:
            return True

    # Knight attacks
    knight_char = "N" if by_colour == WHITE else "n"
    for dr, df in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
        nr, nf = rank + dr, file + df
        if in_bounds(nr, nf) and piece_at(state, nr, nf) == knight_char:
            return True

    # King attacks (for adjacent king detection)
    king_char = "K" if by_colour == WHITE else "k"
    for dr in [-1, 0, 1]:
        for df in [-1, 0, 1]:
            if dr == 0 and df == 0:
                continue
            kr, kf = rank + dr, file + df
            if in_bounds(kr, kf) and piece_at(state, kr, kf) == king_char:
                return True

    # Sliding attacks (rook/queen on straights, bishop/queen on diagonals)
    rook_chars = ("R", "Q") if by_colour == WHITE else ("r", "q")
    for dr, df in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        r, f = rank + dr, file + df
        while in_bounds(r, f):
            p = piece_at(state, r, f)
            if p != " ":
                if p in rook_chars:
                    return True
                break
            r += dr
            f += df

    bishop_chars = ("B", "Q") if by_colour == WHITE else ("b", "q")
    for dr, df in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        r, f = rank + dr, file + df
        while in_bounds(r, f):
            p = piece_at(state, r, f)
            if p != " ":
                if p in bishop_chars:
                    return True
                break
            r += dr
            f += df

    return False


def is_in_check(state: GameState, colour: str) -> bool:
    """Return True if the given colour's king is in check."""
    king_char = "K" if colour == WHITE else "k"
    for r in range(8):
        for f in range(8):
            if state.board[r][f] == king_char:
                return _is_square_attacked(state, r, f, _opponent(colour))
    return False  # King not found (shouldn't happen in normal play)


def _castling_moves(state: GameState, colour: str) -> list[Move]:
    """Generate castling moves if available."""
    moves: list[Move] = []
    if colour == WHITE:
        rank = 0
        king_char, rook_char = "K", "R"
        kingside_right, queenside_right = "K", "Q"
    else:
        rank = 7
        king_char, rook_char = "k", "r"
        kingside_right, queenside_right = "k", "q"

    opponent = _opponent(colour)

    # Check king is on its starting square
    if piece_at(state, rank, 4) != king_char:
        return moves

    # Can't castle while in check
    if _is_square_attacked(state, rank, 4, opponent):
        return moves

    # Kingside castling
    if (
        kingside_right in state.castling
        and piece_at(state, rank, 7) == rook_char
        and is_empty(state, rank, 5)
        and is_empty(state, rank, 6)
        and not _is_square_attacked(state, rank, 5, opponent)
        and not _is_square_attacked(state, rank, 6, opponent)
    ):
        moves.append((rank, 4, rank, 6, None))

    # Queenside castling
    if (
        queenside_right in state.castling
        and piece_at(state, rank, 0) == rook_char
        and is_empty(state, rank, 1)
        and is_empty(state, rank, 2)
        and is_empty(state, rank, 3)
        and not _is_square_attacked(state, rank, 2, opponent)
        and not _is_square_attacked(state, rank, 3, opponent)
    ):
        moves.append((rank, 4, rank, 2, None))

    return moves


def _generate_pseudo_legal_moves(state: GameState, colour: str) -> list[Move]:
    """Generate all pseudo-legal moves (may leave king in check)."""
    moves: list[Move] = []
    for r in range(8):
        for f in range(8):
            piece = state.board[r][f]
            if piece_colour(piece) != colour:
                continue
            p = piece.upper()
            if p == "P":
                moves.extend(_pawn_moves(state, r, f, colour))
            elif p == "N":
                moves.extend(_knight_moves(state, r, f, colour))
            elif p == "B":
                moves.extend(_bishop_moves(state, r, f, colour))
            elif p == "R":
                moves.extend(_rook_moves(state, r, f, colour))
            elif p == "Q":
                moves.extend(_queen_moves(state, r, f, colour))
            elif p == "K":
                moves.extend(_king_normal_moves(state, r, f, colour))

    moves.extend(_castling_moves(state, colour))
    return moves


def _apply_board_move(state: GameState, move: Move) -> GameState:
    """Apply a board move to produce a new state (does not handle hostage captures).

    This is used internally for legality checking. For actual game moves,
    use hostage.apply_move() which handles captures going to prison.
    """
    from_r, from_f, to_r, to_f, promotion = move
    new_state = copy_state(state)
    piece = new_state.board[from_r][from_f]

    # Move the piece
    new_state.board[from_r][from_f] = " "
    new_state.board[to_r][to_f] = promotion if promotion else piece

    # Handle en passant capture
    if piece.upper() == "P" and from_f != to_f and state.board[to_r][to_f] == " ":
        # This is an en passant capture
        capture_rank = to_r - 1 if piece == "P" else to_r + 1
        new_state.board[capture_rank][to_f] = " "

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

    return new_state


def get_legal_board_moves(state: GameState) -> list[Move]:
    """Generate all legal board moves for the active player.

    Filters out moves that would leave the king in check.
    Does not include drop or exchange moves (see hostage module).
    """
    colour = state.active
    pseudo_moves = _generate_pseudo_legal_moves(state, colour)
    legal_moves: list[Move] = []

    for move in pseudo_moves:
        test_state = _apply_board_move(state, move)
        if not is_in_check(test_state, colour):
            legal_moves.append(move)

    return legal_moves


def has_legal_board_moves(state: GameState) -> bool:
    """Return True if the active player has at least one legal board move.

    Short-circuits on the first legal move found, for efficiency.
    """
    colour = state.active
    pseudo_moves = _generate_pseudo_legal_moves(state, colour)

    for move in pseudo_moves:
        test_state = _apply_board_move(state, move)
        if not is_in_check(test_state, colour):
            return True

    return False
