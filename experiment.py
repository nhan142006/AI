"""Reproducible search, game and explanation evaluation."""

import csv
from collections import Counter
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter

from engine import (DEMO_POSITIONS, EMPTY, ORDER, WIN, analyze, best_line, drop, heuristic, legal_moves,
                    outcome, replay, search, winning_columns, won)

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


def random_positions(count, seed=2026):
    """Distinct unfinished positions reached by 2 to 30 random moves, with the side to move."""
    rng, seen = Random(seed), set()
    while len(seen) < count:
        board, player = EMPTY, 0
        for _ in range(rng.randint(2, 30)):
            board = drop(board, rng.choice(legal_moves(board)), player)
            if won(board[player]) or not legal_moves(board):
                break
            player = 1 - player
        else:
            if board not in seen:
                seen.add(board)
                yield board, player


def forces(board, turn, plies, attacker):
    """Exhaustive check, independent of search(): can `attacker` make four within `plies` plies?"""
    if won(board[attacker]):
        return True
    if won(board[1 - attacker]) or plies <= 0:
        return False
    replies = (forces(drop(board, col, turn), 1 - turn, plies - 1, attacker) for col in legal_moves(board))
    return any(replies) if turn == attacker else all(replies)


def check_claims(board, player, result):
    """Replay every claim an explanation makes. Returns (claim, holds) pairs."""
    depth, col, scores = result["depth"], result["column"], result["scores"]
    opponent, after = 1 - player, drop(board, result["column"], player)
    checks = [("chosen has the top score", scores[col] == max(scores.values()))]
    for move, score in scores.items():
        position = drop(board, move, player)
        kind, moves = outcome(score, depth)
        if kind == "eval":
            holds = not forces(position, opponent, depth - 1, player) and not forces(position, opponent, depth - 1, opponent)
        else:
            side = player if kind == "win" else opponent
            plies = 2 * moves - 1 if kind == "win" else 2 * moves
            shorter = plies >= 3 and forces(position, opponent, plies - 3, side)
            holds = forces(position, opponent, plies - 1, side) and not shorter
        checks.append((f"label of column {move + 1}", holds))
    reason, threats = result["reason"], winning_columns(board, opponent)
    losing = [move for move in scores if move != col and scores[move] <= -WIN]
    if reason == "win":
        checks.append(("wins immediately", won(after[player])))
    if reason == "block":
        checks.append(("blocks the threat", bool(threats) and not winning_columns(after, opponent)))
    if reason == "lost":
        checks.append(("every move loses", all(score <= -WIN for score in scores.values())))
        if "cannot block both" in result["explanation"]:
            checks.append(("two winning columns", len(threats) > 1))
    if reason == "avoid":
        checks.append(("named columns lose by force", bool(losing) and all(
            forces(drop(board, move, player), opponent, depth - 1, opponent) for move in losing)))
    if reason == "threat":
        checks.append(("creates a threat", bool(winning_columns(after, player))))
    alt = result["alternative"]
    if alt is not None:
        if "could win next" in result["comparison"]:
            checks.append(("alternative allows an immediate win", bool(winning_columns(drop(board, alt, player), opponent))))
        if "ties" in result["comparison"]:
            checks.append(("alternative ties", scores[alt] == scores[col]))
        # The expected line must be legal and end in the position the score describes.
        position, turn, line = board, player, result["line"]
        legal = bool(line) and line[0] == alt
        for move in line:
            legal = legal and move in legal_moves(position) and not won(position[0]) and not won(position[1])
            if legal:
                position, turn = drop(position, move, turn), 1 - turn
        if legal and won(position[1 - turn]):
            end = (WIN + depth - len(line)) * (1 if 1 - turn == player else -1)
        elif legal and not legal_moves(position):
            end = 0
        else:
            end = heuristic(position, player) if legal and len(line) == depth else None
        checks.append(("expected line reaches the claimed score", end == scores[alt]))
        checks.append(("line score matches the search", best_line(board, player, depth, alt)[0] == scores[alt]))
    return checks


def faithfulness(plan=((4, 1000), (6, 200))):
    """RQ1: are the explanations true? Replays each claim on random positions."""
    rows, failures = [], []
    for depth, count in plan:
        for index, (board, player) in enumerate(random_positions(count, seed=2026 + depth)):
            result = analyze(board, player, depth)
            if depth <= 4:  # Unpruned Minimax is affordable here: scores must match exactly.
                extra = [("scores equal unpruned Minimax",
                          result["scores"] == search(board, player, depth, pruning=False, exact_alternatives=True)[2])]
            else:
                extra = []
            checks = check_claims(board, player, result) + extra
            failed = [claim for claim, holds in checks if not holds]
            failures += [(depth, index, result["reason"], claim) for claim in failed]
            rows.append((depth, index, (board[0] | board[1]).bit_count(), result["reason"], len(checks), len(failed)))
    write_csv("faithfulness.csv", ("depth", "position", "plies", "reason", "claims", "failed"), rows)
    write_csv("faithfulness_failures.csv", ("depth", "position", "reason", "claim"), failures)
    summary = []
    for depth, _ in plan:
        for reason in ("win", "block", "forced_win", "lost", "avoid", "threat", "search"):
            group = [row for row in rows if row[0] == depth and row[3] == reason]
            if group:
                summary.append((depth, reason, len(group), sum(row[5] == 0 for row in group),
                                sum(row[4] for row in group), sum(row[5] for row in group)))
    write_csv("faithfulness_summary.csv", ("depth", "reason", "positions", "positions_all_true",
                                           "claims", "claims_false"), summary)
    return summary


def overhead(count=20, depths=(2, 4, 6, 8)):
    """RQ3: cost of choosing a move (Alpha-Beta) against choosing and explaining it."""
    rows = []
    for index, (board, player) in enumerate(random_positions(count, seed=7)):
        for depth in depths:
            plain, explained = [], []
            for _ in range(3):
                start = perf_counter()
                stats = search(board, player, depth)[3]
                plain.append((perf_counter() - start) * 1000)
                start = perf_counter()
                result = analyze(board, player, depth)
                explained.append((perf_counter() - start) * 1000)
            # analyze() also searches the expected line; that search is timed but has no node counter.
            rows.append((index, depth, stats.nodes, result["nodes"], round(median(plain), 3), round(median(explained), 3)))
    write_csv("overhead.csv", ("position", "depth", "nodes_plain", "nodes_explained", "ms_plain", "ms_explained"), rows)
    return rows


if __name__ == "__main__":
    print(f"Explanation checks: {verify_explanations()} passed", flush=True)
    for depth, reason, positions, passed, claims, false in faithfulness():
        print(f"Faithfulness depth {depth} {reason}: {passed}/{positions} positions, {claims - false}/{claims} claims", flush=True)
    print(f"Overhead: {len(overhead())} measurements", flush=True)
    print(f"Search benchmark: {len(benchmark())} configurations", flush=True)
    for depth, opponent, wins, draws, losses in playing_strength():
        print(f"Depth {depth} vs {opponent}: {wins}W / {draws}D / {losses}L", flush=True)
    print(f"CSV results: {OUTPUT}", flush=True)
