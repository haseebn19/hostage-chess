"""Tests for hostage_chess.engine.result: checkmate and stalemate detection."""

from hostage_chess.engine.board import from_fen, new_game
from hostage_chess.engine.result import check_game_result


class TestCheckmate:
    def test_scholars_mate(self):
        state = from_fen("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
        assert check_game_result(state) == "White wins by checkmate"

    def test_back_rank_mate(self):
        # The rook on a8 checks the king on g8, which is boxed in by its own pawns
        state = from_fen("R5k1/5ppp/8/8/8/8/8/4K3 b - - 0 1")
        assert check_game_result(state) == "White wins by checkmate"

    def test_black_checkmates_white(self):
        # The rook on c1 checks the king on a1, and the king on b3 covers its escape squares
        state = from_fen("8/8/8/8/8/1k6/8/K1r5 w - - 0 1")
        assert check_game_result(state) == "Black wins by checkmate"

    def test_a_drop_that_blocks_the_check_saves_the_game(self):
        state = from_fen("R5k1/5ppp/8/8/8/8/8/4K3 b - - 0 1")
        state.black_airfield = ["n"]
        assert check_game_result(state) is None


class TestStalemate:
    def test_king_with_no_moves_and_not_in_check(self):
        state = from_fen("k7/2Q5/1K6/8/8/8/8/8 b - - 0 1")
        assert check_game_result(state) == "Draw by stalemate"

    def test_a_drop_avoids_stalemate(self):
        state = from_fen("k7/2Q5/1K6/8/8/8/8/8 b - - 0 1")
        state.black_airfield = ["n"]
        assert check_game_result(state) is None


class TestOngoingGame:
    def test_positions_with_moves_have_no_result(self):
        assert check_game_result(new_game()) is None
        state = from_fen("r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 1 1")
        assert check_game_result(state) is None
