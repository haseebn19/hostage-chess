"""Browser tests for the game page script, static/js/game.js.

Two players share a game in separate browser contexts. These tests need Playwright
(`pip install -e ".[dev,browser]"`, then `playwright install chromium`) and are skipped
when it is not installed.
"""

import re
from typing import NamedTuple

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

KINGS_ONLY = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


class Game(NamedTuple):
    number: int
    white: object
    black: object


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def game(browser, server):
    """Log two players in from the lobby and return the game once both pages show it."""
    base_url = "http://{}:{}".format(*server)
    errors = []
    pages = []
    for handle in ("alice", "bob"):
        page = browser.new_context().new_page()
        page.on("pageerror", lambda error: errors.append(error))
        page.goto(base_url)
        page.fill("#handle-input", handle)
        page.click("#enter-lobby")
        pages.append(page)

    white, black = pages
    white.wait_for_url(re.compile(r"/game\?.*player="))
    black.wait_for_url(re.compile(r"/game\?.*player="))
    number = int(re.search(r"game_no=(\d+)", white.url).group(1))

    yield Game(number, white, black)

    for page in pages:
        page.context.close()
    assert errors == []


def piece_on(page, square):
    return page.locator(f'#myBoard [data-square="{square}"] img')


def drag(page, from_square, to_square):
    page.drag_and_drop(
        f'#myBoard [data-square="{from_square}"] img', f'#myBoard [data-square="{to_square}"]'
    )


def test_a_move_reaches_the_opponent(game):
    expect(game.white.locator("#status-text")).to_have_text("Your turn")
    expect(game.black.locator("#status-text")).to_have_text("Opponent's turn")

    drag(game.white, "e2", "e4")

    expect(piece_on(game.black, "e4")).to_have_attribute("data-piece", "wP")
    expect(game.black.locator("#status-text")).to_have_text("Your turn")
    expect(game.white.locator("#status-text")).to_have_text("Opponent's turn")
    expect(game.black.locator("#black-timer")).to_have_class(re.compile("timer-active"))


def test_illegal_moves_snap_back(game):
    drag(game.white, "e2", "e5")

    expect(piece_on(game.white, "e2")).to_have_attribute("data-piece", "wP")
    expect(piece_on(game.white, "e5")).to_have_count(0)
    expect(game.white.locator("#status-text")).to_have_text("Your turn")


def test_dropping_a_piece_from_the_airfield(game, set_position):
    set_position(game.number, 1, KINGS_ONLY, white_airfield=["N"])
    game.white.reload()

    game.white.click("#player-airfield .tray-piece-btn")
    expect(game.white.locator(".highlight-drop")).to_have_count(62)
    expect(game.white.locator("#btn-drop")).to_have_text("Cancel Drop")

    game.white.click('#myBoard [data-square="d4"]')

    expect(piece_on(game.black, "d4")).to_have_attribute("data-piece", "wN")
    expect(game.white.locator("#player-airfield img")).to_have_count(0)


def test_exchanging_a_hostage(game, set_position):
    set_position(game.number, 1, KINGS_ONLY, white_prison=["p"], black_prison=["P"])
    game.white.reload()

    game.white.click("#btn-exchange")
    expect(game.white.locator("#exchange-modal")).to_be_visible()
    game.white.click(".exchange-btn")
    expect(game.white.locator("#exchange-modal")).to_be_hidden()
    expect(game.white.locator("#status-text")).to_have_text(
        "Click a highlighted square to place your pawn"
    )

    game.white.click('#myBoard [data-square="d4"]')

    expect(piece_on(game.black, "d4")).to_have_attribute("data-piece", "wP")
    expect(game.black.locator("#player-airfield img")).to_have_count(1)


def test_escape_cancels_an_exchange(game, set_position):
    set_position(game.number, 1, KINGS_ONLY, white_prison=["p"], black_prison=["P"])
    game.white.reload()

    game.white.click("#btn-exchange")
    game.white.click(".exchange-btn")
    game.white.keyboard.press("Escape")

    expect(game.white.locator(".highlight-drop")).to_have_count(0)
    expect(game.white.locator("#btn-exchange")).to_have_text("Exchange Hostage")
    expect(game.white.locator("#status-text")).to_have_text("Your turn")


def test_promotion_offers_the_pieces_in_prison_and_can_be_cancelled(game, set_position):
    set_position(game.number, 1, "4k3/1P6/8/8/8/8/8/4K3 w - - 0 1", black_prison=["N", "Q"])
    game.white.reload()

    drag(game.white, "b7", "b8")
    expect(game.white.locator("#promotion-modal")).to_be_visible()
    expect(game.white.locator(".promotion-btn")).to_have_count(2)
    game.white.keyboard.press("Escape")
    expect(game.white.locator("#promotion-modal")).to_be_hidden()
    expect(piece_on(game.white, "b7")).to_have_attribute("data-piece", "wP")

    drag(game.white, "b7", "b8")
    game.white.click('[aria-label="Promote to knight"]')

    expect(piece_on(game.black, "b8")).to_have_attribute("data-piece", "wN")
    expect(game.black.locator("#player-prison img")).to_have_count(2)


def test_dialogs_take_focus(game, set_position):
    set_position(game.number, 1, KINGS_ONLY, white_prison=["p"], black_prison=["P"])
    game.white.reload()

    game.white.click("#btn-exchange")

    expect(game.white.locator(".exchange-btn")).to_be_focused()
    game.white.keyboard.press("Escape")
    expect(game.white.locator("#exchange-modal")).to_be_hidden()
    expect(game.white.locator("#btn-exchange")).to_have_text("Exchange Hostage")


def test_check_is_shown(game, set_position):
    set_position(game.number, 1, "k3r3/8/8/8/8/8/8/4K3 w - - 0 1")
    game.white.reload()
    expect(game.white.locator("#status-text")).to_have_text("Your turn, you are in check")


def test_resigning_ends_the_game_for_both_players(game):
    game.white.once("dialog", lambda dialog: dialog.accept())
    game.white.click("#btn-resign")

    game.white.wait_for_url(re.compile(r"/game_over"))
    game.black.wait_for_url(re.compile(r"/game_over"))
    expect(game.black.locator(".result-text")).to_have_text("White resigned")
