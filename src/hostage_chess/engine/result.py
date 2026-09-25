"""Game result detection: checkmate and stalemate."""

from __future__ import annotations

from hostage_chess.engine.board import BLACK, GameState
from hostage_chess.engine.hostage import get_drop_moves, get_exchange_options
from hostage_chess.engine.moves import has_legal_board_moves, is_in_check


def _has_any_legal_action(state: GameState) -> bool:
    """Return True if the active player can move, drop, or make an exchange."""
    # Exchange options are only listed when the rescued piece has a legal square to land on
    return (
        has_legal_board_moves(state)
        or bool(get_drop_moves(state))
        or bool(get_exchange_options(state))
    )


def check_game_result(state: GameState) -> str | None:
    """Return 'White wins by checkmate', 'Black wins by checkmate', 'Draw by stalemate', or None.

    The game is only over when the player to move has no move, drop, or exchange.
    """
    if _has_any_legal_action(state):
        return None

    if is_in_check(state, state.active):
        winner = "White" if state.active == BLACK else "Black"
        return f"{winner} wins by checkmate"
    return "Draw by stalemate"
