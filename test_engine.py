"""Run with: python -m pytest"""

import pytest

from engine import (DEMO_POSITIONS, EMPTY, WIN, analyze, best_line, drop, label, legal_moves, outcome, replay,
                    review, search, why_not, won)
from experiment import check_claims, random_positions


def test_discs_stack_and_full_columns_are_rejected():
    board, player = replay([1] * 6)
    assert 0 not in legal_moves(board) and len(legal_moves(board)) == 6
    with pytest.raises(ValueError):
        drop(board, 0, player)


@pytest.mark.parametrize("moves", [
    [1, 1, 2, 2, 3, 3, 4],              # horizontal
    [1, 2, 1, 2, 1, 2, 1],              # vertical
    [1, 2, 2, 3, 3, 4, 3, 4, 4, 6, 4],  # rising diagonal
    [4, 3, 3, 2, 2, 1, 2, 1, 1, 6, 1],  # falling diagonal
])
def test_four_in_a_row_is_detected_in_every_direction(moves):
    board, player = replay(moves)
    assert won(board[1 - player]) and not won(board[player])


def test_alpha_beta_returns_the_minimax_move_and_score():
    for board, player in random_positions(40, seed=1):
        assert search(board, player, 4)[:2] == search(board, player, 4, pruning=False)[:2]


def test_ai_wins_when_it_can_and_blocks_when_it_must():
    win = analyze(*replay(DEMO_POSITIONS["Immediate win"]), 4)
    block = analyze(*replay(DEMO_POSITIONS["Must block"]), 4)
    assert (win["reason"], win["column"], win["labels"][3]) == ("win", 3, "Win in 1")
    assert (block["reason"], block["column"], block["labels"][2]) == ("block", 3, "Loss in 1")


def test_scores_read_as_moves_to_the_end():
    assert outcome(WIN + 3, 4) == ("win", 1)    # four in a row on the first ply
    assert outcome(WIN + 1, 4) == ("win", 2)    # on the third ply
    assert outcome(-WIN - 2, 4) == ("loss", 1)  # opponent's first reply
    assert outcome(-WIN, 4) == ("loss", 2)
    assert label(7, 4) == "+7" and label(-WIN, 4) == "Loss in 2"


def test_expected_line_scores_match_the_search():
    for board, player in random_positions(25, seed=2):
        result = analyze(board, player, 4)
        for col, score in result["scores"].items():
            assert best_line(board, player, 4, col)[0] == score


def test_why_not_names_the_winning_reply():
    board, player = replay(DEMO_POSITIONS["Must block"])
    contrast = why_not(board, player, 4, analyze(board, player, 4), 2)
    assert "could win next in column 4" in contrast["text"] and contrast["line"] == [2, 3]


def test_coach_flags_a_blunder_and_accepts_the_best_move():
    board, player = replay(DEMO_POSITIONS["Must block"])
    assert review(board, player, 4, 2)["verdict"] == "blunder"
    assert review(board, player, 4, 3)["verdict"] == "best"
    assert review(*replay(DEMO_POSITIONS["Immediate win"]), 4, 0)["verdict"] == "missed win"
    assert review(EMPTY, 0, 4, 3)["verdict"] == "best"


def test_every_claim_holds_and_the_checker_catches_a_false_one():
    board, player = replay(DEMO_POSITIONS["Must block"])
    result = analyze(board, player, 4)
    assert all(holds for _, holds in check_claims(board, player, result))
    result["scores"] = {**result["scores"], 2: 5}  # Pretend the losing column 3 is fine.
    assert not all(holds for _, holds in check_claims(board, player, result))
