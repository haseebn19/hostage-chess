"""Tests for hostage_chess.engine.hostage: captures, drops, exchanges, and move application."""

from hostage_chess.engine.board import algebraic_to_indices, from_fen, new_game
from hostage_chess.engine.hostage import (
    PIECE_VALUES,
    apply_drop,
    apply_exchange,
    apply_move,
    get_drop_moves,
    get_exchange_options,
)
from hostage_chess.engine.moves import Move

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


def move(from_square: str, to_square: str, promotion: str | None = None) -> Move:
    return Move(*algebraic_to_indices(from_square), *algebraic_to_indices(to_square), promotion)


class TestCaptures:
    def test_captured_pieces_go_to_the_captors_prison(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        assert apply_move(state, move("e4", "d5")).white_prison == ["p"]

        state.active = "b"
        assert apply_move(state, move("d5", "e4")).black_prison == ["P"]

    def test_en_passant_capture_goes_to_prison(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3")
        new_state = apply_move(state, move("e5", "d6"))
        assert new_state.white_prison == ["p"]
        assert new_state.board[4][3] == " "


class TestApplyMove:
    def test_turn_and_move_counters(self):
        after_white = apply_move(new_game(), move("g1", "f3"))
        assert (after_white.active, after_white.halfmove, after_white.fullmove) == ("b", 1, 1)

        after_black = apply_move(after_white, move("g8", "f6"))
        assert (after_black.active, after_black.halfmove, after_black.fullmove) == ("w", 2, 2)

    def test_double_step_sets_the_en_passant_square(self):
        new_state = apply_move(new_game(), move("e2", "e4"))
        assert new_state.en_passant == "e3"
        assert new_state.halfmove == 0

    def test_king_move_loses_both_castling_rights(self):
        state = from_fen("r3k2r/pppppppp/8/8/8/8/8/R3K2R w KQkq - 0 1")
        new_state = apply_move(state, move("e1", "e2"))
        assert new_state.castling == "kq"
        assert new_state.white_king_moved and not new_state.black_king_moved

    def test_capturing_a_rook_on_its_corner_loses_that_castling_right(self):
        state = from_fen("4k3/8/8/8/8/8/6b1/4K2R b K - 0 1")
        new_state = apply_move(state, move("g2", "h1"))
        assert new_state.castling == "-"
        assert new_state.black_prison == ["R"]

    def test_promotion_takes_the_piece_from_prison_and_leaves_the_pawn(self):
        state = from_fen("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1")
        state.black_prison = ["N"]
        new_state = apply_move(state, move("b7", "b8", "N"))
        assert new_state.board[7][1] == "N"
        assert new_state.black_prison == ["P"]
        assert new_state.halfmove == 0


class TestDrops:
    def test_every_empty_square_for_a_piece(self):
        state = from_fen(KINGS_ONLY)
        state.white_airfield = ["N"]
        assert len(get_drop_moves(state)) == 62

    def test_no_drops_with_an_empty_airfield(self):
        assert get_drop_moves(new_game()) == []

    def test_pawns_cannot_be_dropped_on_the_first_or_last_rank(self):
        state = from_fen(KINGS_ONLY)
        state.white_airfield = ["P"]
        assert {drop.to_rank for drop in get_drop_moves(state)} == set(range(1, 7))

    def test_drop_places_the_piece_and_ends_the_turn(self):
        state = from_fen(KINGS_ONLY)
        state.white_airfield = ["N"]
        new_state = apply_drop(state, 0, 3, 3)
        assert new_state.board[3][3] == "N"
        assert new_state.white_airfield == []
        assert new_state.active == "b"

    def test_drop_must_block_check(self):
        # The black rook on e8 checks the white king on e1, so a drop has to block on the e-file
        state = from_fen("k3r3/8/8/8/8/8/8/4K3 w - - 0 1")
        state.white_airfield = ["N"]
        squares = {(drop.to_rank, drop.to_file) for drop in get_drop_moves(state)}
        assert squares == {(rank, 4) for rank in range(1, 7)}

    def test_rook_dropped_on_its_corner_can_castle_if_the_king_never_moved(self):
        state = from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        state.white_airfield = ["R"]
        assert apply_drop(state, 0, 0, 7).castling == "K"

        state.white_king_moved = True
        assert apply_drop(state, 0, 0, 7).castling == "-"

    def test_rook_dropped_elsewhere_or_on_the_other_sides_corner_cannot_castle(self):
        state = from_fen(KINGS_ONLY)
        state.white_airfield = ["R"]
        assert apply_drop(state, 0, 0, 6).castling == "-"
        assert apply_drop(state, 0, 7, 7).castling == "-"


class TestExchanges:
    def test_needs_a_piece_in_each_prison(self):
        assert get_exchange_options(new_game()) == []

    def test_payment_must_be_worth_at_least_the_rescued_piece(self):
        state = from_fen(KINGS_ONLY)
        state.white_prison = ["p", "q"]
        state.black_prison = ["R", "P"]
        pairs = {(option["rescue"], option["payment"]) for option in get_exchange_options(state)}
        assert pairs == {("R", "q"), ("P", "p"), ("P", "q")}

    def test_identical_exchanges_are_listed_once(self):
        state = from_fen(KINGS_ONLY)
        state.white_prison = ["p", "p"]
        state.black_prison = ["P", "P"]
        options = get_exchange_options(state)
        assert [(option["rescue"], option["payment"]) for option in options] == [("P", "p")]

    def test_paying_with_the_only_promotion_piece_can_end_a_check(self):
        # The black pawn on d2 checks the king on e1 only while black has a queen to promote to
        state = from_fen("4k3/8/8/8/8/8/3p4/4K3 w - - 0 1")
        state.white_prison = ["q"]
        state.black_prison = ["P"]
        [option] = get_exchange_options(state)
        assert len(option["valid_drops"]) == 47

    def test_apply_exchange(self):
        state = from_fen(KINGS_ONLY)
        state.white_prison = ["p"]
        state.black_prison = ["P"]
        new_state = apply_exchange(state, rescue_idx=0, payment_idx=0, drop_rank=3, drop_file=3)
        assert new_state.board[3][3] == "P"
        assert new_state.black_airfield == ["p"]
        assert new_state.white_prison == new_state.black_prison == []
        assert new_state.active == "b"


def test_piece_values_follow_q_r_b_n_p():
    assert PIECE_VALUES["Q"] > PIECE_VALUES["R"] > PIECE_VALUES["B"] > PIECE_VALUES["P"]
    assert PIECE_VALUES["B"] == PIECE_VALUES["N"]
    assert set(PIECE_VALUES) == {"P", "N", "B", "R", "Q"}
