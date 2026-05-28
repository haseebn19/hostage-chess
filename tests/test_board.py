"""Tests for src.engine.board: board state, FEN conversion, and serialisation."""

from src.engine.board import (
    INITIAL_BOARD,
    algebraic_to_indices,
    board_to_fen_placement,
    copy_state,
    fen_placement_to_board,
    from_dict,
    from_fen,
    in_bounds,
    indices_to_algebraic,
    is_black_piece,
    is_empty,
    is_white_piece,
    new_game,
    piece_at,
    piece_colour,
    to_dict,
    to_fen,
)


class TestNewGame:
    """Tests for initial board setup."""

    def test_initial_board_has_correct_white_back_rank(self):
        state = new_game()
        assert state.board[0] == ["R", "N", "B", "Q", "K", "B", "N", "R"]

    def test_initial_board_has_correct_black_back_rank(self):
        state = new_game()
        assert state.board[7] == ["r", "n", "b", "q", "k", "b", "n", "r"]

    def test_initial_board_has_white_pawns_on_rank_2(self):
        state = new_game()
        assert state.board[1] == ["P"] * 8

    def test_initial_board_has_black_pawns_on_rank_7(self):
        state = new_game()
        assert state.board[6] == ["p"] * 8

    def test_initial_board_has_empty_middle_ranks(self):
        state = new_game()
        for rank in range(2, 6):
            assert state.board[rank] == [" "] * 8

    def test_initial_state_defaults(self):
        state = new_game()
        assert state.active == "w"
        assert state.castling == "KQkq"
        assert state.en_passant == "-"
        assert state.halfmove == 0
        assert state.fullmove == 1
        assert state.white_prison == []
        assert state.white_airfield == []
        assert state.black_prison == []
        assert state.black_airfield == []


class TestPieceHelpers:
    """Tests for piece identification functions."""

    def test_is_white_piece(self):
        for p in "KQRBNP":
            assert is_white_piece(p) is True
        for p in "kqrbnp":
            assert is_white_piece(p) is False
        assert is_white_piece(" ") is False

    def test_is_black_piece(self):
        for p in "kqrbnp":
            assert is_black_piece(p) is True
        for p in "KQRBNP":
            assert is_black_piece(p) is False
        assert is_black_piece(" ") is False

    def test_piece_colour(self):
        assert piece_colour("K") == "w"
        assert piece_colour("n") == "b"
        assert piece_colour(" ") is None

    def test_piece_at(self):
        state = new_game()
        assert piece_at(state, 0, 0) == "R"
        assert piece_at(state, 4, 4) == " "
        assert piece_at(state, 7, 4) == "k"

    def test_is_empty(self):
        state = new_game()
        assert is_empty(state, 4, 4) is True
        assert is_empty(state, 0, 0) is False


class TestBoundsAndAlgebraic:
    """Tests for bounds checking and algebraic notation conversion."""

    def test_in_bounds_valid(self):
        assert in_bounds(0, 0) is True
        assert in_bounds(7, 7) is True
        assert in_bounds(3, 4) is True

    def test_in_bounds_invalid(self):
        assert in_bounds(-1, 0) is False
        assert in_bounds(0, 8) is False
        assert in_bounds(8, 0) is False

    def test_algebraic_to_indices(self):
        assert algebraic_to_indices("a1") == (0, 0)
        assert algebraic_to_indices("e4") == (3, 4)
        assert algebraic_to_indices("h8") == (7, 7)

    def test_indices_to_algebraic(self):
        assert indices_to_algebraic(0, 0) == "a1"
        assert indices_to_algebraic(3, 4) == "e4"
        assert indices_to_algebraic(7, 7) == "h8"

    def test_round_trip_algebraic(self):
        for r in range(8):
            for f in range(8):
                sq = indices_to_algebraic(r, f)
                assert algebraic_to_indices(sq) == (r, f)


class TestFEN:
    """Tests for FEN serialisation/deserialisation."""

    def test_initial_position_fen(self):
        state = new_game()
        fen = to_fen(state)
        assert fen == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    def test_from_fen_initial(self):
        state = from_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        assert state.board == INITIAL_BOARD
        assert state.active == "w"
        assert state.castling == "KQkq"

    def test_fen_round_trip(self):
        state = new_game()
        fen = to_fen(state)
        restored = from_fen(fen)
        assert restored.board == state.board
        assert restored.active == state.active
        assert restored.castling == state.castling
        assert restored.en_passant == state.en_passant

    def test_custom_fen_position(self):
        fen_str = "r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 2"
        state = from_fen(fen_str)
        assert state.active == "b"
        assert state.en_passant == "e3"
        assert state.fullmove == 2

    def test_empty_board_fen(self):
        fen_str = "8/8/8/8/8/8/8/8 w - - 0 1"
        state = from_fen(fen_str)
        for r in range(8):
            assert state.board[r] == [" "] * 8

    def test_fen_placement_to_board_and_back(self):
        placement = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
        board = fen_placement_to_board(placement)
        assert board_to_fen_placement(board) == placement


class TestDictSerialisation:
    """Tests for full state dict serialisation."""

    def test_dict_round_trip(self):
        state = new_game()
        state.white_prison = ["p", "n"]
        state.black_airfield = ["R"]
        d = to_dict(state)
        restored = from_dict(d)
        assert restored.board == state.board
        assert restored.white_prison == ["p", "n"]
        assert restored.black_airfield == ["R"]

    def test_dict_structure(self):
        state = new_game()
        d = to_dict(state)
        assert "fen" in d
        assert "white_prison" in d
        assert "white_airfield" in d
        assert "black_prison" in d
        assert "black_airfield" in d


class TestCopyState:
    """Tests for deep copying game state."""

    def test_copy_is_independent(self):
        state = new_game()
        copy = copy_state(state)
        copy.board[0][0] = "Q"
        assert state.board[0][0] == "R"

    def test_copy_preserves_prison(self):
        state = new_game()
        state.white_prison = ["p"]
        copy = copy_state(state)
        copy.white_prison.append("n")
        assert len(state.white_prison) == 1
