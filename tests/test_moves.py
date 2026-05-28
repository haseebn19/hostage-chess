"""Tests for src.engine.moves: legal move generation, check detection."""

from src.engine.board import from_fen, new_game
from src.engine.moves import (
    Move,
    _is_square_attacked,
    get_legal_board_moves,
    has_legal_board_moves,
    is_in_check,
)


def _find_move(moves: list[Move], from_sq: str, to_sq: str, promo=None) -> Move | None:
    """Helper to find a specific move in a list by algebraic notation."""
    from src.engine.board import algebraic_to_indices

    fr, ff = algebraic_to_indices(from_sq)
    tr, tf = algebraic_to_indices(to_sq)
    for m in moves:
        if (
            m[0] == fr
            and m[1] == ff
            and m[2] == tr
            and m[3] == tf
            and (promo is None or m[4] == promo)
        ):
            return m
    return None


class TestPawnMoves:
    """Tests for pawn move generation."""

    def test_white_pawn_single_forward(self):
        state = new_game()
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e2", "e3") is not None

    def test_white_pawn_double_forward(self):
        state = new_game()
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e2", "e4") is not None

    def test_black_pawn_single_forward(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e7", "e6") is not None

    def test_pawn_cannot_move_forward_into_piece(self):
        # Place a pawn directly in front
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/4p3/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e2", "e3") is None

    def test_pawn_capture_diagonal(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e4", "d5") is not None

    def test_en_passant_capture(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e5", "d6") is not None

    def test_pawn_promotion(self):
        state = from_fen("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
        moves = get_legal_board_moves(state)
        # Should have promotion choices
        assert _find_move(moves, "e7", "e8", "Q") is not None
        assert _find_move(moves, "e7", "e8", "R") is not None
        assert _find_move(moves, "e7", "e8", "B") is not None
        assert _find_move(moves, "e7", "e8", "N") is not None


class TestKnightMoves:
    """Tests for knight move generation."""

    def test_knight_from_start(self):
        state = new_game()
        moves = get_legal_board_moves(state)
        # b1 knight can go to a3 or c3
        assert _find_move(moves, "b1", "a3") is not None
        assert _find_move(moves, "b1", "c3") is not None

    def test_knight_central(self):
        state = from_fen("8/8/8/8/4N3/8/8/4K2k w - - 0 1")
        moves = get_legal_board_moves(state)
        # Knight on e4 has 8 squares
        knight_moves = [m for m in moves if m[0] == 3 and m[1] == 4]
        assert len(knight_moves) == 8

    def test_knight_cannot_capture_friendly(self):
        state = from_fen("8/8/5N2/8/4N3/8/8/4K2k w - - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e4", "f6") is None


class TestSlidingMoves:
    """Tests for bishop, rook, and queen moves."""

    def test_bishop_diagonal(self):
        state = from_fen("8/8/8/8/3B4/8/8/4K2k w - - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "d4", "a7") is not None
        assert _find_move(moves, "d4", "g7") is not None

    def test_rook_straight(self):
        state = from_fen("8/8/8/8/3R4/8/8/4K2k w - - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "d4", "d8") is not None
        assert _find_move(moves, "d4", "h4") is not None

    def test_queen_combines(self):
        state = from_fen("8/8/8/8/3Q4/8/8/4K2k w - - 0 1")
        moves = get_legal_board_moves(state)
        # Queen should move both diagonally and straight
        assert _find_move(moves, "d4", "d8") is not None
        assert _find_move(moves, "d4", "a7") is not None

    def test_sliding_blocked_by_friendly(self):
        state = from_fen("8/8/8/3P4/3R4/8/8/4K2k w - - 0 1")
        moves = get_legal_board_moves(state)
        # Rook cannot move through its own pawn
        assert _find_move(moves, "d4", "d5") is None
        assert _find_move(moves, "d4", "d6") is None


class TestKingMoves:
    """Tests for king moves including castling."""

    def test_king_one_square(self):
        state = from_fen("8/8/8/8/3K4/8/8/7k w - - 0 1")
        moves = get_legal_board_moves(state)
        king_moves = [m for m in moves if m[0] == 3 and m[1] == 3]
        assert len(king_moves) == 8

    def test_kingside_castling(self):
        state = from_fen("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e1", "g1") is not None

    def test_queenside_castling(self):
        state = from_fen("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e1", "c1") is not None

    def test_cannot_castle_through_check(self):
        # Rook on f8 attacks f1
        state = from_fen("5r2/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e1", "g1") is None  # f1 is attacked

    def test_cannot_castle_while_in_check(self):
        state = from_fen("4r3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
        moves = get_legal_board_moves(state)
        assert _find_move(moves, "e1", "g1") is None
        assert _find_move(moves, "e1", "c1") is None


class TestCheckDetection:
    """Tests for check detection."""

    def test_not_in_check_initial(self):
        state = new_game()
        assert is_in_check(state, "w") is False
        assert is_in_check(state, "b") is False

    def test_white_in_check(self):
        state = from_fen("8/8/8/8/8/8/4r3/4K3 w - - 0 1")
        assert is_in_check(state, "w") is True

    def test_must_escape_check(self):
        # King in check by rook, must move or block
        state = from_fen("4r3/8/8/8/8/8/8/4K3 w - - 0 1")
        moves = get_legal_board_moves(state)
        # All moves must get king out of check
        for m in moves:
            assert m[0] == 0 and m[1] == 4  # Only king can move

    def test_pinned_piece_cannot_move(self):
        # Bishop is pinned by rook to the king
        state = from_fen("3r4/8/8/8/3B4/8/8/3K4 w - - 0 1")
        moves = get_legal_board_moves(state)
        # Bishop on d4 is pinned and cannot move off the d-file
        bishop_moves = [m for m in moves if m[0] == 3 and m[1] == 3]
        for bm in bishop_moves:
            # Bishop can only move along the d-file (blocking)
            assert bm[3] == 3  # Must stay on file d


class TestSquareAttacked:
    """Tests for square attack detection."""

    def test_square_attacked_by_pawn(self):
        state = from_fen("8/8/8/8/8/3p4/8/4K3 w - - 0 1")
        # Black pawn on d3 attacks e2
        assert _is_square_attacked(state, 1, 4, "b") is True

    def test_square_attacked_by_knight(self):
        state = from_fen("8/8/5n2/8/4K3/8/8/8 w - - 0 1")
        # Black knight on f6 attacks e4
        assert _is_square_attacked(state, 3, 4, "b") is True

    def test_square_not_attacked(self):
        state = from_fen("8/8/8/8/4K3/8/8/7k w - - 0 1")
        assert _is_square_attacked(state, 3, 4, "b") is False


class TestHasLegalMoves:
    """Tests for has_legal_board_moves."""

    def test_initial_position_has_moves(self):
        state = new_game()
        assert has_legal_board_moves(state) is True

    def test_checkmate_position_has_no_moves(self):
        # Scholar's mate position: Black is checkmated by Qf7
        mated = from_fen("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 1")
        assert has_legal_board_moves(mated) is False
