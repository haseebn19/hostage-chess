"""Tests for src.engine.hostage: capture, drop, exchange, and move application."""

import pytest

from src.engine.board import from_fen, new_game
from src.engine.hostage import (
    PIECE_VALUES,
    apply_drop,
    apply_exchange,
    apply_move,
    get_drop_moves,
    get_exchange_options,
)
from src.engine.moves import get_legal_board_moves


class TestCaptureToPrison:
    """Tests that captures properly add pieces to prison."""

    def test_white_captures_black_pawn(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
        moves = get_legal_board_moves(state)
        # Find e4xd5
        capture = None
        for m in moves:
            if m[0] == 3 and m[1] == 4 and m[2] == 4 and m[3] == 3:
                capture = m
                break
        assert capture is not None
        new_state = apply_move(state, capture)
        assert "p" in new_state.white_prison

    def test_black_captures_white_pawn(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 2")
        moves = get_legal_board_moves(state)
        # d5xe4
        capture = None
        for m in moves:
            if m[0] == 4 and m[1] == 3 and m[2] == 3 and m[3] == 4:
                capture = m
                break
        assert capture is not None
        new_state = apply_move(state, capture)
        assert "P" in new_state.black_prison

    def test_en_passant_capture_goes_to_prison(self):
        state = from_fen("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3")
        moves = get_legal_board_moves(state)
        ep = None
        for m in moves:
            if m[0] == 4 and m[1] == 4 and m[2] == 5 and m[3] == 3:
                ep = m
                break
        assert ep is not None
        new_state = apply_move(state, ep)
        assert "p" in new_state.white_prison
        assert new_state.board[4][3] == " "  # Captured pawn removed


class TestApplyMove:
    """Tests for move application state updates."""

    def test_active_player_switches(self):
        state = new_game()
        moves = get_legal_board_moves(state)
        new_state = apply_move(state, moves[0])
        assert new_state.active == "b"

    def test_fullmove_increments_after_black(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        moves = get_legal_board_moves(state)
        new_state = apply_move(state, moves[0])
        assert new_state.fullmove == 2

    def test_en_passant_set_on_double_push(self):
        state = new_game()
        # Find e2-e4
        for m in get_legal_board_moves(state):
            if m[0] == 1 and m[1] == 4 and m[2] == 3 and m[3] == 4:
                new_state = apply_move(state, m)
                assert new_state.en_passant == "e3"
                return
        pytest.fail("Could not find e2-e4 move")

    def test_castling_rights_removed_on_king_move(self):
        state = from_fen("r3k2r/pppppppp/8/8/8/8/8/R3K2R w KQkq - 0 1")
        # Move king e1-e2 (no pawns blocking)
        for m in get_legal_board_moves(state):
            if m[0] == 0 and m[1] == 4 and m[2] == 1 and m[3] == 4:
                new_state = apply_move(state, m)
                assert "K" not in new_state.castling
                assert "Q" not in new_state.castling
                return
        pytest.fail("Could not find Ke1-e2 move")

    def test_castling_moves_rook(self):
        state = from_fen("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
        # Kingside castle
        for m in get_legal_board_moves(state):
            if m[0] == 0 and m[1] == 4 and m[2] == 0 and m[3] == 6:
                new_state = apply_move(state, m)
                assert new_state.board[0][6] == "K"  # King on g1
                assert new_state.board[0][5] == "R"  # Rook on f1
                assert new_state.board[0][7] == " "  # h1 empty
                return
        pytest.fail("Could not find kingside castle move")


class TestDropMoves:
    """Tests for piece drops from airfield."""

    def test_drop_generates_moves_when_airfield_has_pieces(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        state.white_airfield = ["N"]
        drops = get_drop_moves(state)
        assert len(drops) > 0

    def test_no_drops_with_empty_airfield(self):
        state = new_game()
        drops = get_drop_moves(state)
        assert len(drops) == 0

    def test_pawn_cannot_be_dropped_on_rank_1_or_8(self):
        state = from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        state.white_airfield = ["P"]
        drops = get_drop_moves(state)
        for d in drops:
            to_rank = d[2]
            assert to_rank != 0 and to_rank != 7

    def test_drop_places_piece(self):
        state = from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        state.white_airfield = ["N"]
        new_state = apply_drop(state, 0, 3, 3)  # Drop knight on d4
        assert new_state.board[3][3] == "N"
        assert len(new_state.white_airfield) == 0
        assert new_state.active == "b"

    def test_drop_cannot_target_occupied_square(self):
        state = new_game()
        state.white_airfield = ["N"]
        drops = get_drop_moves(state)
        for d in drops:
            assert state.board[d[2]][d[3]] == " "


class TestExchangeOptions:
    """Tests for hostage exchange mechanics."""

    def test_exchange_requires_pieces_in_both_prisons(self):
        state = new_game()
        assert get_exchange_options(state) == []

    def test_exchange_available_with_matching_values(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        state.white_prison = ["p"]  # White captured a black pawn
        state.black_prison = ["P"]  # Black captured a white pawn
        options = get_exchange_options(state)
        # White can rescue P by paying p (equal value)
        assert len(options) >= 1
        assert any(o["rescue"] == "P" and o["payment"] == "p" for o in options)

    def test_exchange_requires_equal_or_greater_value(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        state.white_prison = ["p"]  # White has a black pawn
        state.black_prison = ["R"]  # Black captured a white rook
        options = get_exchange_options(state)
        # Can't pay a pawn (value 1) to rescue a rook (value 5)
        assert len(options) == 0

    def test_exchange_high_value_payment(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        state.white_prison = ["q"]  # White has a black queen
        state.black_prison = ["P"]  # Black captured a white pawn
        options = get_exchange_options(state)
        # Can pay a queen (value 9) to rescue a pawn (value 1)
        assert len(options) >= 1

    def test_apply_exchange(self):
        state = from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
        state.white_prison = ["p"]
        state.black_prison = ["P"]
        new_state = apply_exchange(state, rescue_idx=0, payment_idx=0, drop_rank=3, drop_file=3)
        # Rescued P should be on the board at d4
        assert new_state.board[3][3] == "P"
        # Payment p should have moved to black's airfield
        assert "p" in new_state.black_airfield
        # Both prisons should be empty
        assert len(new_state.black_prison) == 0
        assert len(new_state.white_prison) == 0
        assert new_state.active == "b"


class TestPieceValues:
    """Tests for the piece value hierarchy."""

    def test_queen_most_valuable(self):
        assert PIECE_VALUES["Q"] > PIECE_VALUES["R"]
        assert PIECE_VALUES["Q"] > PIECE_VALUES["B"]
        assert PIECE_VALUES["Q"] > PIECE_VALUES["N"]
        assert PIECE_VALUES["Q"] > PIECE_VALUES["P"]

    def test_bishop_equals_knight(self):
        assert PIECE_VALUES["B"] == PIECE_VALUES["N"]

    def test_case_insensitive_values(self):
        assert PIECE_VALUES["Q"] == PIECE_VALUES["q"]
        assert PIECE_VALUES["R"] == PIECE_VALUES["r"]
