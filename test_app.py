"""Regression checks for Coach review, board previews and prediction study isolation."""

import csv
import os
from concurrent.futures import Future, ThreadPoolExecutor

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

import main as app
from engine import EMPTY, best_line, drop, replay, review, search


@pytest.fixture
def display():
    pygame.init()
    screen = pygame.display.set_mode(app.WINDOW)
    fonts = {size: pygame.font.SysFont("arial", size, bold=size >= 24) for size in (15, 18, 20, 24, 32)}
    yield screen, fonts
    pygame.quit()


def click(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def board_click(column):
    return click((app.BOARD.x + column * app.SIZE + 20, app.BOARD.y + 20))


def finish(game, executor):
    app.advance(game, executor)
    game.job.result(timeout=10)
    app.advance(game, executor)


def test_coach_lines_and_score_gap_share_the_pre_move_board():
    board, player = replay([5, 1, 6, 2, 5, 3])
    feedback = review(board, player, 4, 6)
    scores = search(board, player, 4, pruning=False, exact_alternatives=True)[2]
    assert feedback["before"] == board
    assert feedback["best"] == 3
    assert feedback["scores"] == scores
    assert feedback["best_score"] == max(scores.values())
    assert feedback["score_gap"] == scores[3] - scores[6]
    assert feedback["played_line"] == best_line(board, player, 4, 6)[1]
    assert feedback["best_line"] == best_line(board, player, 4, 3)[1]
    assert feedback["nodes"] > 0 and feedback["cutoffs"] > 0
    assert drop(board, 6, player) != feedback["before"]


def test_coach_accepts_a_tied_winning_move():
    board, player = replay([2, 7, 3, 7, 4, 6])
    feedback = review(board, player, 4, 0)
    assert feedback["best"] != feedback["column"]
    assert feedback["verdict"] == "best" and feedback["score_gap"] == 0
    with pytest.raises(ValueError):
        review(board, player, 4, 9)


def test_winning_human_drop_is_reviewed_without_an_ai_reply():
    game = app.Game()
    game.board, game.turn = replay([1, 2, 1, 2, 1, 3])
    app.handle(game, board_click(0))
    terminal_board = game.board
    assert game.over
    with ThreadPoolExecutor(max_workers=1) as executor:
        finish(game, executor)
        app.advance(game, executor)
    assert game.board == terminal_board and game.turn == 0
    assert game.coach["verdict"] == "best"
    assert game.coach["before"] != game.board
    assert game.analysis is None and game.job is None


def test_preview_is_read_only_and_live_board_keeps_accepting_moves(display):
    screen, fonts = display
    game = app.Game()
    game.depth = 2
    with ThreadPoolExecutor(max_workers=1) as executor:
        app.handle(game, board_click(3))
        finish(game, executor)
        live = game.board
        assert game.view == "coach" and not game.preview
        app.handle(game, click(app.PREVIEW_BUTTON.center))
        assert game.preview
        app.draw(screen, fonts, game)
        app.handle(game, board_click(2))
        assert game.board == live and game.turn == 0
        app.handle(game, click(app.PREVIEW_BUTTON.center))
        assert not game.preview
        app.handle(game, board_click(2))
        assert game.board != live and game.turn == 1
        finish(game, executor)
    app.draw(screen, fonts, game)
    assert game.max_scroll > 0
    game.scroll = 100_000
    app.draw(screen, fonts, game)
    assert game.scroll == game.max_scroll
    app.handle(game, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    assert not game.explain and not game.preview
    app.draw(screen, fonts, game)


def test_reset_discards_a_running_future_result():
    game = app.Game()
    app.handle(game, board_click(3))
    old_board = game.board
    game.job = old = Future()
    old.set_running_or_notify_cancel()
    game.reset()
    old.set_result(app.think(EMPTY, 3, old_board, 2, True))
    with ThreadPoolExecutor(max_workers=1) as executor:
        app.advance(game, executor)
    assert game.board == EMPTY and game.analysis is None and game.coach is None
    assert game.job is None and game.turn == 0


@pytest.mark.parametrize("condition", ["control", "explain"])
def test_study_still_requires_guess_and_logs_without_coach(condition, tmp_path, monkeypatch, display):
    screen, fonts = display
    monkeypatch.setattr(app, "RESULTS", tmp_path)
    game = app.Game({"participant": "PTEST", "condition": condition})
    for key in (pygame.K_c, pygame.K_e, pygame.K_F1, pygame.K_2):
        app.handle(game, pygame.event.Event(pygame.KEYDOWN, key=key))
    app.handle(game, click(app.COACH_TAB.center))
    assert game.view == "ai" and not game.coaching and game.depth == 4
    assert game.explain == (condition == "explain")
    with ThreadPoolExecutor(max_workers=1) as executor:
        app.handle(game, board_click(3))
        finish(game, executor)
    assert game.pending is not None and game.analysis is None
    before_guess = game.board
    actual = game.pending[1]["column"]
    app.draw(screen, fonts, game)
    app.handle(game, board_click(actual))
    assert game.pending is None and game.board != before_guess
    assert game.coach is None and game.view == "ai"
    rows = list(csv.DictReader((tmp_path / "study.csv").open(encoding="utf-8")))
    assert len(rows) == 1 and rows[0]["correct"] == "1" and rows[0]["condition"] == condition
    app.draw(screen, fonts, game)
    if condition == "control":
        assert game.max_scroll == 0


def test_worker_error_does_not_crash_the_ui(display):
    screen, fonts = display
    game = app.Game()
    game.turn = 1
    game.job = Future()
    game.job.set_exception(RuntimeError("test worker failure"))
    with ThreadPoolExecutor(max_workers=1) as executor:
        app.advance(game, executor)
    assert game.error == "RuntimeError"
    app.draw(screen, fonts, game)
    game.reset()
    assert game.error is None
