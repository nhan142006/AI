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


def analyze(board, player, depth):
    chosen, score, scores, stats = search(board, player, depth, exact_alternatives=True)
    if chosen is None:
        raise ValueError("Game is over")
    selected_board = drop(board, chosen, player)
    alternative = max((col for col in scores if col != chosen), key=scores.get, default=None)
    opponent = 1 - player
    threats = winning_columns(board, opponent)
    remaining_threats = winning_columns(selected_board, opponent)
    if won(selected_board[player]):
        reason = "win"
        explanation = f"Column {chosen + 1} makes four in a row and wins immediately."
    elif threats and not remaining_threats:
        reason = "block"
        explanation = f"Column {chosen + 1} removes all immediate winning replies."
        # Prefer an illustrative alternative that actually leaves a winning reply.
        unsafe = [col for col in scores if col != chosen
                  and winning_columns(drop(board, col, player), opponent)]
        if unsafe:
            alternative = max(unsafe, key=scores.get)
    else:
        reason = "search"
        explanation = f"Column {chosen + 1} has the highest Minimax score at depth {depth}."
    comparison = "Only one legal move remains."
    if alternative is not None:
        alternative_board = drop(board, alternative, player)
        replies = winning_columns(alternative_board, opponent)
        if replies and not won(alternative_board[player]) and reason != "win" and not remaining_threats:
            reply_text = ", ".join(str(col + 1) for col in replies)
            comparison = f"If AI played {alternative + 1}, you could win next in column {reply_text}."
        elif scores[alternative] == score:
            comparison = f"Column {alternative + 1} ties. AI keeps the first move in center-first order."
        else:
            comparison = f"Column {alternative + 1} scores lower at this search depth."
    return {
        "column": chosen, "score": score, "scores": scores, "alternative": alternative,
        "reason": reason, "explanation": explanation, "comparison": comparison,
        "depth": depth, "nodes": stats.nodes,
    }


DEMO_POSITIONS = {
    "Immediate win": [7, 1, 7, 2, 6, 3, 6],
    "Must block": [1, 7, 2, 7, 3],
    "Search comparison": [4, 3, 5],
}
