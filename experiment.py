"""Reproducible search, game and explanation evaluation."""

import csv
from collections import Counter
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter

from engine import DEMO_POSITIONS, ORDER, analyze, drop, legal_moves, replay, search, winning_columns, won

OUTPUT = Path(__file__).with_name("results")


def write_csv(filename, header, rows):
    OUTPUT.mkdir(exist_ok=True)
    with (OUTPUT / filename).open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def benchmark():
    rows = []
    positions = {"Opening": [], **DEMO_POSITIONS, "Midgame": [4, 3, 5, 4, 2, 6, 3, 5]}
    for name, moves in positions.items():
        board, player = replay(moves)
        for depth in (2, 4, 6):
            expected = None
            for algorithm, pruning, order in (
                ("Minimax", False, ORDER),
                ("Alpha-Beta", True, ORDER),
                ("Alpha-Beta left first", True, tuple(range(7))),
            ):
                times = []
                for _ in range(3):
                    start = perf_counter()
                    col, score, _, stats = search(board, player, depth, pruning=pruning, order=order)
                    times.append((perf_counter() - start) * 1000)
                if expected is None:
                    expected = (col, score)
                assert score == expected[1]
                if algorithm == "Alpha-Beta":
                    assert col == expected[0]
                rows.append((name, depth, algorithm, col + 1, score, stats.nodes, stats.cutoffs,
                             round(median(times), 3)))
    write_csv("search.csv", ("position", "depth", "algorithm", "column", "score", "nodes",
                             "cutoffs", "median_ms"), rows)
    return rows


def playing_strength():
    rows = []
    for depth in (2, 4, 6):
        for baseline in ("Random", "Greedy"):
            for seed in range(10):
                for ai in (0, 1):
                    rng = Random(seed)
                    opening = [rng.randint(1, 7) for _ in range(2)]
                    board, turn = replay(opening)
                    plies = len(opening)
                    while legal_moves(board):
                        if turn == ai:
                            col = search(board, turn, depth)[0]
                        elif baseline == "Greedy":
                            col = search(board, turn, 1)[0]
                        else:
                            col = rng.choice(legal_moves(board))
                        board = drop(board, col, turn)
                        plies += 1
                        if won(board[turn]):
                            outcome = "win" if turn == ai else "loss"
                            break
                        turn = 1 - turn
                    else:
                        outcome = "draw"
                    rows.append((depth, baseline, seed, ai == 0, outcome, plies, "-".join(map(str, opening))))
    write_csv("games.csv", ("depth", "opponent", "seed", "ai_first", "outcome", "plies", "opening"), rows)
    summary = []
    for depth in (2, 4, 6):
        for baseline in ("Random", "Greedy"):
            counts = Counter(row[4] for row in rows if row[:2] == (depth, baseline))
            summary.append((depth, baseline, counts["win"], counts["draw"], counts["loss"]))
    write_csv("games_summary.csv", ("depth", "opponent", "wins", "draws", "losses"), summary)
    return summary


def verify_explanations():
    rows = []
    cases = (
        ("Immediate win", DEMO_POSITIONS["Immediate win"], "win", 4),
        ("Must block", DEMO_POSITIONS["Must block"], "block", 4),
        ("Search comparison", DEMO_POSITIONS["Search comparison"], "search", 4),
        ("Opening", [], "search", 4),
        ("Mirrored block", [7, 1, 6, 1, 5], "block", 4),
        ("Vertical block", [1, 7, 1, 7, 1], "block", 1),
        ("Vertical win", [7, 1, 7, 1, 6, 1, 6], "win", 1),
        ("Tied winning moves", [7, 2, 7, 3, 6, 4, 6], "win", 5),
    )
    for name, moves, expected_reason, expected_col in cases:
        board, player = replay(moves)
        result = analyze(board, player, 4)
        col, alt = result["column"], result["alternative"]
        after = drop(board, col, player)
        assert (result["reason"], col + 1) == (expected_reason, expected_col), (name, result)
        assert result == analyze(board, player, 4)
        expected_scores = search(board, player, 4, pruning=False, exact_alternatives=True)[2]
        assert result["scores"] == expected_scores, name
        assert result["score"] == max(result["scores"].values())
        if expected_reason == "win":
            assert won(after[player])
        if expected_reason == "block":
            assert winning_columns(board, 1 - player)
            assert not winning_columns(after, 1 - player)
            assert winning_columns(drop(board, alt, player), 1 - player)
            assert "could win next" in result["comparison"]
        if name == "Tied winning moves":
            assert result["scores"][alt] == result["score"]
            assert "ties" in result["comparison"]
        rows.append((name, expected_reason, expected_col, col + 1, alt + 1 if alt is not None else "",
                     result["score"], result["explanation"], result["comparison"], "PASS"))
    write_csv("explanations.csv", ("case", "expected_reason", "expected_column", "actual_column",
                                  "alternative", "score", "explanation", "comparison", "result"), rows)
    return len(rows)


if __name__ == "__main__":
    print(f"Explanation checks: {verify_explanations()} passed", flush=True)
    print(f"Search benchmark: {len(benchmark())} configurations", flush=True)
    for depth, opponent, wins, draws, losses in playing_strength():
        print(f"Depth {depth} vs {opponent}: {wins}W / {draws}D / {losses}L", flush=True)
    print(f"CSV results: {OUTPUT}", flush=True)
