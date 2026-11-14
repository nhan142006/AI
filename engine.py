"""Connect Four rules, heuristic, adversarial search and move explanations."""

from dataclasses import dataclass
from math import inf

ROWS, COLS = 6, 7
ORDER = (3, 2, 4, 1, 5, 0, 6)
WIN = 100_000
EMPTY = (0, 0)


def cell(row, col):
    return 1 << (col * 7 + row)


WINDOWS = tuple(
    sum(cell(row + step * dr, col + step * dc) for step in range(4))
    for row in range(ROWS)
    for col in range(COLS)
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1))
    if 0 <= row + 3 * dr < ROWS and 0 <= col + 3 * dc < COLS
)
CENTER = sum(cell(row, 3) for row in range(ROWS))
TOP = tuple(cell(ROWS - 1, col) for col in range(COLS))
COLUMN = tuple(sum(cell(row, col) for row in range(ROWS)) for col in range(COLS))
BOTTOM = tuple(cell(0, col) for col in range(COLS))


def legal_moves(board, order=ORDER):
    occupied = board[0] | board[1]
    return [col for col in order if not occupied & TOP[col]]


def drop(board, col, player):
    occupied = board[0] | board[1]
    bit = ((occupied & COLUMN[col]) + BOTTOM[col]) & COLUMN[col]
    if not bit:
        raise ValueError("Column is full")
    pieces = list(board)
    pieces[player] |= bit
    return tuple(pieces)


def won(bits):
    for shift in (1, 7, 6, 8):
        pairs = bits & (bits >> shift)
        if pairs & (pairs >> (2 * shift)):
            return True
    return False


def replay(columns):
    board, player = EMPTY, 0
    for column in columns:
        if won(board[1 - player]) or column - 1 not in legal_moves(board):
            raise ValueError("Illegal move in demo position")
        board = drop(board, column - 1, player)
        player = 1 - player
    return board, player


def heuristic(board, player):
    own, opponent = board[player], board[1 - player]
    score = 3 * (own & CENTER).bit_count()
    for window in WINDOWS:
        if not opponent & window:
            count = (own & window).bit_count()
            score += (0, 0, 2, 5, 0)[count]
        elif not own & window and (opponent & window).bit_count() == 3:
            score -= 4
    return score


@dataclass
class SearchStats:
    nodes: int = 0
    cutoffs: int = 0


def search(board, player, depth, *, pruning=True, order=ORDER, exact_alternatives=False):
    """Return best column, root score, exact candidate scores if requested, and counters.

    Depth counts moves from the current position. Player numbers are 0 and 1.
    Node count includes the root and each visited terminal or heuristic leaf.
    """
    if depth < 1:
        raise ValueError("Search depth must be at least 1")
    stats = SearchStats(nodes=1)

    def visit(position, turn, remaining, alpha, beta):
        stats.nodes += 1
        if won(position[1 - turn]):
            return (WIN + remaining) * (1 if turn != player else -1)
        moves = legal_moves(position, order)
        if not moves:
            return 0
        if not remaining:
            return heuristic(position, player)
        maximizing = turn == player
        value = -inf if maximizing else inf
        for col in moves:
            child = visit(drop(position, col, turn), 1 - turn, remaining - 1, alpha, beta)
            if maximizing:
                value = max(value, child)
                alpha = max(alpha, value)
            else:
                value = min(value, child)
                beta = min(beta, value)
            if pruning and alpha >= beta:
                stats.cutoffs += 1
                break
        return value

    if won(board[player]):
        return None, WIN, {}, stats
    if won(board[1 - player]):
        return None, -WIN, {}, stats

    best_col, best_score, scores = None, -inf, {}
    for col in legal_moves(board, order):
        alpha = -inf if exact_alternatives else best_score
        score = visit(drop(board, col, player), 1 - player, depth - 1, alpha, inf)
        if exact_alternatives:
            scores[col] = score
        if score > best_score:
            best_col, best_score = col, score
    return best_col, (0 if best_col is None else best_score), scores, stats


def winning_columns(board, player):
    return [col for col in legal_moves(board) if won(drop(board, col, player)[player])]


def outcome(score, depth):
    """Read a root score as ("win" | "loss" | "eval", moves the winner still needs).

    "eval" means the search found no forced result within the depth.
    """
    if score >= WIN:
        return "win", (depth - (score - WIN) + 1) // 2
    if score <= -WIN:
        return "loss", (depth + score + WIN) // 2
    return "eval", None


def label(score, depth):
    kind, moves = outcome(score, depth)
    return f"{score:+d}" if kind == "eval" else f"{kind.capitalize()} in {moves}"


def turns(count):
    return "1 move" if count == 1 else f"{count} moves"


def names(columns):
    return " and ".join(str(col + 1) for col in columns)


def best_line(board, player, depth, first):
    """Return the exact score of `first` and the line of best play behind it.

    Scores and tie-breaks match search(): `player` maximizes, center-first order.
    """
    def visit(position, turn, remaining, alpha, beta):
        if won(position[1 - turn]):
            return (WIN + remaining) * (1 if turn != player else -1), []
        moves = legal_moves(position)
        if not moves:
            return 0, []
        if not remaining:
            return heuristic(position, player), []
        maximizing = turn == player
        best, line = (-inf if maximizing else inf), []
        for col in moves:
            value, tail = visit(drop(position, col, turn), 1 - turn, remaining - 1, alpha, beta)
            if value > best if maximizing else value < best:
                best, line = value, [col] + tail
            if maximizing:
                alpha = max(alpha, best)
            else:
                beta = min(beta, best)
            if alpha >= beta:
                break
        return best, line

    score, tail = visit(drop(board, first, player), 1 - player, depth - 1, -inf, inf)
    return score, [first] + tail


def why_not(board, player, depth, result, col):
    """Contrast `col` with the move the search chose. `result` comes from analyze()."""
    chosen, scores = result["column"], result["scores"]
    if col == chosen:
        return {"column": col, "text": f"Column {col + 1} is the move AI played.", "line": []}
    if col not in scores:
        return {"column": col, "text": f"Column {col + 1} is full.", "line": []}
    score, line = best_line(board, player, depth, col)
    after = drop(board, col, player)
    replies = winning_columns(after, 1 - player)
    kind, moves = outcome(score, depth)
    name = f"Column {col + 1}"
    if score == result["score"]:
        text = f"{name} ties with column {chosen + 1}. AI keeps the first move in center-first order."
    elif replies and not won(after[player]):
        text = f"If AI played {col + 1}, you could win next in column {names(replies)}."
    elif kind == "loss":
        text = f"{name} loses by force: you could win in {turns(moves)}."
    elif kind == "win":
        text = f"{name} also wins, but in {turns(moves)} instead of {turns(outcome(result['score'], depth)[1])}."
    else:
        text = f"{name} gives {label(score, depth)}; column {chosen + 1} gives {label(result['score'], depth)}."
    return {"column": col, "text": text, "line": line}


def analyze(board, player, depth):
    """Choose a move for `player` (the AI) and explain it to the opponent ("you")."""
    chosen, score, scores, stats = search(board, player, depth, exact_alternatives=True)
    if chosen is None:
        raise ValueError("Game is over")
    opponent = 1 - player
    after = drop(board, chosen, player)
    kind, moves = outcome(score, depth)
    threats = winning_columns(board, opponent)
    losing = [col for col in sorted(scores) if col != chosen and scores[col] <= -WIN]
    created = winning_columns(after, player)
    others = [col for col in scores if col != chosen]
    alternative = max(others, key=scores.get, default=None)
    name = f"Column {chosen + 1}"
    if won(after[player]):
        reason = "win"
        explanation = f"{name} makes four in a row and wins immediately."
    elif threats and not winning_columns(after, opponent):
        reason = "block"
        explanation = f"{name} blocks your four in a row."
        if kind == "win":
            explanation += f" AI can then force a win in {turns(moves)}."
        if kind == "loss":
            explanation += f" You can still force a win in {turns(moves)}."
        # Prefer an illustrative alternative that actually leaves a winning reply.
        unsafe = [col for col in others if winning_columns(drop(board, col, player), opponent)]
        if unsafe:
            alternative = max(unsafe, key=scores.get)
    elif kind == "loss":
        reason = "lost"
        if len(threats) > 1:
            explanation = f"You threaten to win in columns {names(threats)} and AI cannot block both."
        else:
            explanation = f"Every move loses against best play. {name} delays your win the longest: {turns(moves)}."
    elif kind == "win":
        reason = "forced_win"
        explanation = f"{name} forces a win in {turns(moves)}, whatever you reply."
    elif losing:
        reason = "avoid"
        explanation = f"{name} avoids a forced loss. Column {names(losing)} would lose by force."
        alternative = max(losing, key=scores.get)
    elif created:
        reason = "threat"
        explanation = (f"{name} has the highest Minimax score at depth {depth} "
                       f"and threatens four in a row in column {names(created)}.")
    else:
        reason = "search"
        explanation = f"{name} has the highest Minimax score at depth {depth}."
    result = {
        "column": chosen, "score": score, "scores": scores, "alternative": alternative,
        "labels": {col: label(value, depth) for col, value in scores.items()},
        "reason": reason, "explanation": explanation,
        "depth": depth, "nodes": stats.nodes, "cutoffs": stats.cutoffs,
    }
    contrast = why_not(board, player, depth, result, alternative) if alternative is not None else None
    result["comparison"] = contrast["text"] if contrast else "Only one legal move remains."
    result["line"] = contrast["line"] if contrast else []
    return result


def review(board, player, depth, col):
    """Coach feedback on the move `col` that `player` (the human) just chose on `board`."""
    best_col, best, scores, _ = search(board, player, depth, exact_alternatives=True)
    score = scores[col]
    best_kind, best_moves = outcome(best, depth)
    kind, moves = outcome(score, depth)
    name, better = f"Column {col + 1}", f"column {best_col + 1}"
    if score == best:
        verdict, text = "best", f"{name} was the best move at depth {depth} ({label(score, depth)})."
    elif best_kind == "win" and kind != "win":
        verdict, text = "missed win", f"{better.capitalize()} would have won in {turns(best_moves)}."
    elif best_kind == "win":
        verdict = "good"
        text = f"Still winning, but {better} wins faster: {turns(best_moves)} instead of {turns(moves)}."
    elif kind == "loss" and best_kind != "loss":
        verdict = "blunder"
        text = (f"AI can now force a win in {turns(moves)}. "
                f"{better.capitalize()} was safe ({label(best, depth)}).")
    elif kind == "loss":
        verdict, text = "inaccuracy", f"Lost either way, but {better} would have held out longer."
    else:
        verdict = "good" if best - score <= 3 else "inaccuracy"
        text = f"{better.capitalize()} scored higher: {best:+d} against {score:+d} at depth {depth}."
    return {"column": col, "verdict": verdict, "text": text, "best": best_col,
            "score": score, "scores": scores, "depth": depth}


DEMO_POSITIONS = {
    "Immediate win": [7, 1, 7, 2, 6, 3, 6],
    "Must block": [1, 7, 2, 7, 3],
    "Search comparison": [4, 3, 5],
}
