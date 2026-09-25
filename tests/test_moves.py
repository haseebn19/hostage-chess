"""Tests for hostage_chess.engine.moves: legal move generation and check detection."""

from hostage_chess.engine.board import algebraic_to_indices, from_fen, new_game
from hostage_chess.engine.moves import (
    Move,
    _is_square_attacked,
    apply_board_move,
    get_legal_board_moves,
    has_legal_board_moves,
    is_in_check,
    promotion_pieces,
)


def move(from_square: str, to_square: str, promotion: str | None = None) -> Move:
    return Move(*algebraic_to_indices(from_square), *algebraic_to_indices(to_square), promotion)


def moves_from(state, square: str) -> set[str]:
    """The squares the piece on `square` can legally move to."""
    rank, file = algebraic_to_indices(square)
    return {
        "abcdefgh"[m.to_file] + str(m.to_rank + 1)
        for m in get_legal_board_moves(state)
        if (m.from_rank, m.from_file) == (rank, file)
    }


class TestPawnMoves:
    def test_single_and_double_step_from_the_start(self):
        assert moves_from(new_game(), "e2") == {"e3", "e4"}
        state = from_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        assert moves_from(state, "e7") == {"e6", "e5"}

    def test_blocked_pawn_cannot_move_forward(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/4p3/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        assert moves_from(state, "e2") == set()
        assert moves_from(state, "d2") == {"d3", "d4", "e3"}

    def test_diagonal_capture(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        assert "d5" in moves_from(state, "e4")

    def test_en_passant(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3")
        assert "d6" in moves_from(state, "e5")


class TestPromotion:
    def test_pawn_promotes_only_to_pieces_held_in_the_opponents_prison(self):
        state = from_fen("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
        state.black_prison = ["N", "p", "Q", "N"]

        assert promotion_pieces(state, "w") == ["Q", "N"]
        assert move("e7", "e8", "Q") in get_legal_board_moves(state)
        assert move("e7", "e8", "N") in get_legal_board_moves(state)
        assert move("e7", "e8", "R") not in get_legal_board_moves(state)

    def test_pawn_cannot_reach_the_last_rank_without_a_piece_to_promote_to(self):
        state = from_fen("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
        state.black_prison = ["P"]
        assert moves_from(state, "e7") == set()

    def test_promoting_swaps_the_pawn_with_the_piece_in_prison(self):
        state = from_fen("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
        state.black_prison = ["R", "Q"]

        new_state = apply_board_move(state, move("e7", "e8", "Q"))

        assert new_state.board[7][4] == "Q"
        assert new_state.black_prison == ["R", "P"]

    def test_pawn_without_a_promotion_piece_does_not_check_the_back_rank(self):
        state = from_fen("3k4/4P3/8/8/8/8/8/4K3 b - - 0 1")
        assert not is_in_check(state, "b")

        state.black_prison = ["B"]
        assert is_in_check(state, "b")

    def test_capturing_a_piece_the_opponent_could_promote_to_can_be_illegal(self):
        # Rxa4 would put the knight in white's prison, letting the black pawn on e2 promote
        # and so attack the white king on d1
        state = from_fen("4k3/8/8/8/n7/8/4p3/R2K4 w - - 0 1")
        assert moves_from(state, "a1") == {"a2", "a3", "b1", "c1"}


class TestPieceMoves:
    def test_knight(self):
        assert moves_from(new_game(), "b1") == {"a3", "c3"}
        assert len(moves_from(from_fen("8/8/8/8/4N3/8/8/4K2k w - - 0 1"), "e4")) == 8
        assert "f6" not in moves_from(from_fen("8/8/5N2/8/4N3/8/8/4K2k w - - 0 1"), "e4")

    def test_sliding_pieces(self):
        assert {"a7", "g7"} <= moves_from(from_fen("8/8/8/8/3B4/8/8/4K2k w - - 0 1"), "d4")
        assert {"d8", "h4"} <= moves_from(from_fen("8/8/8/8/3R4/8/8/4K2k w - - 0 1"), "d4")
        assert {"d8", "a7"} <= moves_from(from_fen("8/8/8/8/3Q4/8/8/4K2k w - - 0 1"), "d4")

    def test_sliding_piece_is_blocked_by_its_own_side(self):
        state = from_fen("8/8/8/3P4/3R4/8/8/4K2k w - - 0 1")
        assert not {"d5", "d6"} & moves_from(state, "d4")

    def test_king_moves_one_square(self):
        assert len(moves_from(from_fen("8/8/8/8/3K4/8/8/7k w - - 0 1"), "d4")) == 8


class TestCastling:
    def test_both_sides(self):
        state = from_fen("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
        assert {"g1", "c1"} <= moves_from(state, "e1")

    def test_not_through_or_out_of_check(self):
        assert "g1" not in moves_from(from_fen("5r2/8/8/8/8/8/8/R3K2R w KQ - 0 1"), "e1")
        assert not {"g1", "c1"} & moves_from(from_fen("4r3/8/8/8/8/8/8/R3K2R w KQ - 0 1"), "e1")

    def test_castling_moves_the_rook(self):
        state = from_fen("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
        new_state = apply_board_move(state, move("e1", "g1"))
        assert new_state.board[0][4:] == [" ", "R", "K", " "]


class TestCheck:
    def test_detects_check(self):
        assert not is_in_check(new_game(), "w")
        assert is_in_check(from_fen("8/8/8/8/8/8/4r3/4K3 w - - 0 1"), "w")

    def test_moves_must_escape_check(self):
        # Only the king can move, and every move has to leave the rook's file
        state = from_fen("4r3/8/8/8/8/8/8/4K3 w - - 0 1")
        assert moves_from(state, "e1") == {"d1", "d2", "f1", "f2"}
        assert len(get_legal_board_moves(state)) == 4

    def test_pinned_piece_stays_on_the_pin_line(self):
        state = from_fen("3r4/8/8/8/3B4/8/8/3K4 w - - 0 1")
        assert moves_from(state, "d4") == set()

    def test_attacked_squares(self):
        assert _is_square_attacked(from_fen("8/8/8/8/8/3p4/8/4K3 w - - 0 1"), 1, 4, "b")
        assert _is_square_attacked(from_fen("8/8/5n2/8/4K3/8/8/8 w - - 0 1"), 3, 4, "b")
        assert not _is_square_attacked(from_fen("8/8/8/8/4K3/8/8/7k w - - 0 1"), 3, 4, "b")


class TestHasLegalMoves:
    def test_start_position_and_checkmate(self):
        assert has_legal_board_moves(new_game())
        mated = from_fen("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 1")
        assert not has_legal_board_moves(mated)
