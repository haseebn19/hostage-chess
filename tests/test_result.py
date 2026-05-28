"""Tests for src.engine.result: checkmate, stalemate, and king capture detection."""

from src.engine.board import from_fen
from src.engine.result import check_game_result


class TestCheckmate:
    """Tests for checkmate detection."""

    def test_scholars_mate(self):
        # Black is checkmated: Qf7#
        state = from_fen("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
        result = check_game_result(state)
        assert result == "White wins by checkmate"

    def test_back_rank_mate(self):
        # White rook on a8 delivers back-rank mate, black king on g8 trapped by pawns f7,g7,h7
        state = from_fen("R5k1/5ppp/8/8/8/8/8/4K3 b - - 0 1")
        result = check_game_result(state)
        assert result == "White wins by checkmate"

    def test_black_checkmates_white(self):
        # King + rook mate: Ka1 checked by Rc1, Kb3 covers a2/b1/b2
        state = from_fen("8/8/8/8/8/1k6/8/K1r5 w - - 0 1")
        result = check_game_result(state)
        assert result == "Black wins by checkmate"


class TestStalemate:
    """Tests for stalemate detection."""

    def test_stalemate_king_alone(self):
        # White king has no legal moves but is not in check
        state = from_fen("k7/2Q5/1K6/8/8/8/8/8 b - - 0 1")
        # Black king on a8 is stalemated
        result = check_game_result(state)
        assert result == "Draw by stalemate"

    def test_not_stalemate_with_legal_moves(self):
        state = from_fen("k7/8/1K6/8/8/8/8/8 b - - 0 1")
        result = check_game_result(state)
        assert result is None  # Game continues


class TestOngoingGame:
    """Tests that ongoing positions return None."""

    def test_initial_position(self):
        from src.engine.board import new_game

        state = new_game()
        assert check_game_result(state) is None

    def test_midgame_position(self):
        state = from_fen("r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 1 1")
        assert check_game_result(state) is None


class TestKingCapture:
    """Tests for king capture detection (defensive fallback)."""

    def test_missing_white_king(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQ1BNR w - - 0 1")
        result = check_game_result(state)
        assert result == "Black wins - White king captured"

    def test_missing_black_king(self):
        state = from_fen("rnbq1bnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b - - 0 1")
        result = check_game_result(state)
        assert result == "White wins - Black king captured"


class TestStalemateWithDrops:
    """Tests that drops prevent stalemate when pieces are in airfield."""

    def test_not_stalemate_if_drop_available(self):
        # King alone on a8, normally stalemated by queen on c7 + king on b6
        state = from_fen("k7/2Q5/1K6/8/8/8/8/8 b - - 0 1")
        state.black_airfield = ["n"]  # Black has a knight to drop
        result = check_game_result(state)
        # With a drop available, it's not stalemate
        assert result is None
