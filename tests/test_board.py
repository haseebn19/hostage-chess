"""Tests for hostage_chess.engine.board: board state, FEN conversion, and serialization."""

from hostage_chess.engine.board import (
    INITIAL_BOARD,
    algebraic_to_indices,
    board_to_fen_placement,
    copy_state,
    fen_placement_to_board,
    from_dict,
    from_fen,
    in_bounds,
    indices_to_algebraic,
    is_empty,
    new_game,
    piece_at,
    piece_colour,
    to_dict,
    to_fen,
)

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class TestNewGame:
    def test_pieces_start_on_their_home_squares(self):
        state = new_game()
        assert state.board[0] == ["R", "N", "B", "Q", "K", "B", "N", "R"]
        assert state.board[1] == ["P"] * 8
        assert all(state.board[rank] == [" "] * 8 for rank in range(2, 6))
        assert state.board[6] == ["p"] * 8
        assert state.board[7] == ["r", "n", "b", "q", "k", "b", "n", "r"]

    def test_white_moves_first_with_every_castling_right_and_empty_trays(self):
        state = new_game()
        assert (state.active, state.castling, state.en_passant) == ("w", "KQkq", "-")
        assert (state.halfmove, state.fullmove) == (0, 1)
        assert state.white_prison == state.black_prison == []
        assert state.white_airfield == state.black_airfield == []
        assert not state.white_king_moved and not state.black_king_moved


class TestPieceHelpers:
    def test_piece_colour(self):
        assert piece_colour("K") == "w"
        assert piece_colour("n") == "b"
        assert piece_colour(" ") is None

    def test_piece_at_and_is_empty(self):
        state = new_game()
        assert piece_at(state, 0, 0) == "R"
        assert piece_at(state, 7, 4) == "k"
        assert is_empty(state, 4, 4)
        assert not is_empty(state, 0, 0)

    def test_in_bounds(self):
        assert in_bounds(0, 0) and in_bounds(7, 7)
        assert not in_bounds(-1, 0) and not in_bounds(0, 8) and not in_bounds(8, 0)


class TestAlgebraicNotation:
    def test_converts_between_squares_and_indices(self):
        assert algebraic_to_indices("a1") == (0, 0)
        assert algebraic_to_indices("e4") == (3, 4)
        assert indices_to_algebraic(7, 7) == "h8"

    def test_round_trips_every_square(self):
        for rank in range(8):
            for file in range(8):
                assert algebraic_to_indices(indices_to_algebraic(rank, file)) == (rank, file)


class TestFEN:
    def test_initial_position(self):
        assert to_fen(new_game()) == START_FEN
        assert from_fen(START_FEN).board == INITIAL_BOARD

    def test_reads_every_field(self):
        state = from_fen("r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 2")
        assert state.board[5][2] == "n"
        assert (state.active, state.castling, state.en_passant) == ("b", "KQkq", "e3")
        assert (state.halfmove, state.fullmove) == (0, 2)

    def test_empty_board(self):
        assert from_fen("8/8/8/8/8/8/8/8 w - - 0 1").board == [[" "] * 8 for _ in range(8)]

    def test_placement_round_trip(self):
        placement = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R"
        assert board_to_fen_placement(fen_placement_to_board(placement)) == placement


class TestDictSerialization:
    def test_round_trip_keeps_trays_and_king_moves(self):
        state = new_game()
        state.white_prison = ["p", "n"]
        state.black_airfield = ["R"]
        state.white_king_moved = True

        restored = from_dict(to_dict(state))

        assert restored.board == state.board
        assert restored.white_prison == ["p", "n"]
        assert restored.black_airfield == ["R"]
        assert restored.white_king_moved and not restored.black_king_moved

    def test_older_saves_without_king_moves_load(self):
        restored = from_dict({"fen": START_FEN, "white_prison": ["p"]})
        assert restored.white_prison == ["p"]
        assert not restored.white_king_moved and not restored.black_king_moved


class TestCopyState:
    def test_copy_does_not_share_the_board_or_trays(self):
        state = new_game()
        state.white_prison = ["p"]
        copy = copy_state(state)

        copy.board[0][0] = "Q"
        copy.white_prison.append("n")

        assert state.board[0][0] == "R"
        assert state.white_prison == ["p"]
