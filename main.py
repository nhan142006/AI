"""Pygame interface: play the AI, read its reasoning, get coached, or run the prediction study."""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from time import perf_counter

import pygame

from engine import (COLS, ROWS, DEMO_POSITIONS, EMPTY, analyze, cell, drop, hint, label, legal_moves, outcome,
                    replay, review, why_not, won)

BG = "#101829"
PANEL = "#1b2940"
WHITE = "#edf4ff"
MUTED = "#a8b8ce"
YELLOW = "#ffce66"
RED = "#ff737e"
TEAL = "#75dfcf"
HINT = "#8be38f"
CHIP = {"win": "#1f6357", "loss": "#7a2f3b", "eval": "#2a3a57"}
VERDICT = {"best": TEAL, "good": TEAL, "inaccuracy": YELLOW, "missed win": RED, "blunder": RED}
WINDOW = (1100, 720)
BOARD = pygame.Rect(25, 164, 504, 432)
SIZE = 72
TEXT_X, TEXT_WIDTH = 582, 470
RESULTS = Path(__file__).with_name("results")
STUDY_DEPTH = 4
HINT_EXTRA_DEPTH = 2  # The hint looks further ahead than the AI it plays against.
HINT_MAX_DEPTH = 7
AI_TAB = pygame.Rect(578, 114, 222, 34)
COACH_TAB = pygame.Rect(812, 114, 245, 34)
PREVIEW_BUTTON = pygame.Rect(25, 674, 266, 30)
VIEWPORT = pygame.Rect(TEXT_X, 168, TEXT_WIDTH, 482)


class Game:
    """Everything the screen shows. `study` is None outside the prediction study."""

    def __init__(self, study=None):
        self.depth = STUDY_DEPTH
        self.explain = not study or study["condition"] == "explain"
        self.coaching = not study
        self.hinting = False
        self.study = study
        self.games = 0
        self.reset()

    def reset(self, board=EMPTY, turn=0, demo=None):
        for running in (getattr(self, "job", None), getattr(self, "hint_job", None)):
            if running is not None:
                running.cancel()
        self.board, self.turn, self.demo = board, turn, demo
        self.analysis = self.analyzed = self.coach = self.contrast = None
        self.job = self.pending = self.guess = None
        self.elapsed, self.moves, self.rated = 0.0, 0, False
        self.human = (None, None)  # Board before the human's last move, and that move.
        self.view, self.preview, self.scroll, self.max_scroll = "ai", False, 0, 0
        self.error = None
        self.hint = self.hint_job = None

    @property
    def hint_depth(self):
        return min(self.depth + HINT_EXTRA_DEPTH, HINT_MAX_DEPTH)

    @property
    def hint_ready(self):
        """True when a hint for the current board can be shown."""
        return (self.hinting and not self.study and self.turn == 0 and not self.over and not self.error
                and self.hint is not None and self.hint["board"] == self.board
                and self.hint["depth"] == self.hint_depth)

    @property
    def over(self):
        return won(self.board[0]) or won(self.board[1]) or not legal_moves(self.board)

    @property
    def status(self):
        if self.error:
            return "Analysis failed - press R to start again"
        if won(self.board[0]):
            text = "You win!"
        elif won(self.board[1]):
            text = "AI wins!"
        elif not legal_moves(self.board):
            text = "Draw"
        elif self.pending:
            return "Guess: click the column the AI will play"
        else:
            return "AI is thinking..." if self.turn else "Your turn"
        if self.study:
            text += "  Press R for the next game" if self.rated else "  Rate 1-5: how well did you understand the AI?"
        return text


def think(before, col, board, depth, coaching):
    """Background work for one AI turn: coach the human's move, then choose and explain a reply."""
    feedback = review(before, 0, depth, col) if coaching and col is not None else None
    if won(board[0]) or won(board[1]) or not legal_moves(board):
        return feedback, None, 0.0
    start = perf_counter()
    analysis = analyze(board, 1, depth)
    return feedback, analysis, (perf_counter() - start) * 1000


def log(filename, header, row):
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / filename
    fresh = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        if fresh:
            writer.writerow(header)
        writer.writerow(row)


def play_ai_move(game, feedback, analysis, elapsed):
    game.coach, game.analysis, game.elapsed = feedback, analysis, elapsed
    game.scroll, game.preview = 0, False
    if feedback is not None and game.coaching and not game.study:
        game.view = "coach"
    if analysis is None:
        game.turn, game.analyzed, game.contrast = 0, None, None
        return
    game.analyzed = game.board
    alt = analysis["alternative"]
    game.contrast = None if alt is None else {"column": alt, "text": analysis["comparison"], "line": analysis["line"]}
    game.board, game.turn = drop(game.board, analysis["column"], 1), 0


def record_guess(game, col):
    feedback, analysis, elapsed = game.pending
    study, actual = game.study, analysis["column"]
    game.moves += 1
    log("study.csv", ("time", "participant", "condition", "game", "ai_move", "legal_moves", "guess",
                      "actual", "correct", "reason", "depth"),
        (datetime.now().isoformat(timespec="seconds"), study["participant"], study["condition"], game.games + 1,
         game.moves, len(legal_moves(game.board)), col + 1, actual + 1, int(col == actual),
         analysis["reason"], analysis["depth"]))
    game.pending, game.guess = None, col
    play_ai_move(game, feedback, analysis, elapsed)


def record_rating(game, rating):
    study = game.study
    result = "win" if won(game.board[0]) else "loss" if won(game.board[1]) else "draw"
    log("study_ratings.csv", ("time", "participant", "condition", "game", "player_result", "understanding_1_to_5"),
        (datetime.now().isoformat(timespec="seconds"), study["participant"], study["condition"],
         game.games + 1, result, rating))
    game.rated = True
    game.games += 1


def handle(game, event):
    """Apply one input event. Returns False when the player quits."""
    if event.type == pygame.QUIT:
        return False
    study = game.study
    if event.type == pygame.MOUSEWHEEL and VIEWPORT.collidepoint(pygame.mouse.get_pos()):
        game.scroll = max(0, min(game.max_scroll, game.scroll - event.y * 48))
    if event.type == pygame.KEYDOWN:
        key = event.key
        if key == pygame.K_ESCAPE:
            return False
        if key == pygame.K_r and not (study and game.over and not game.rated):
            game.reset()
        elif study:
            if game.over and not game.rated and pygame.K_1 <= key <= pygame.K_5:
                record_rating(game, key - pygame.K_0)
        elif key in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
            name = list(DEMO_POSITIONS)[key - pygame.K_F1]
            position, player = replay(DEMO_POSITIONS[name])
            game.reset(position if player == 1 else position[::-1], 1, name)
        elif key in (pygame.K_2, pygame.K_4, pygame.K_6):
            game.depth = key - pygame.K_0
        elif key == pygame.K_e:
            game.explain = not game.explain
            game.preview, game.scroll = False, 0
        elif key == pygame.K_h:
            game.hinting = not game.hinting
            game.scroll = 0
        elif key == pygame.K_c:
            game.coaching = not game.coaching
            game.preview, game.scroll = False, 0
            if not game.coaching:
                game.view = "ai"
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not study:
        if AI_TAB.collidepoint(event.pos):
            game.view, game.preview, game.scroll = "ai", False, 0
        elif COACH_TAB.collidepoint(event.pos) and game.coaching:
            game.view, game.preview, game.scroll = "coach", False, 0
        elif PREVIEW_BUTTON.collidepoint(event.pos) and game.view == "coach" and game.coach and game.explain:
            game.preview = not game.preview
    if event.type == pygame.MOUSEBUTTONDOWN and BOARD.collidepoint(event.pos) and not game.preview and not game.error:
        col = (event.pos[0] - BOARD.x) // SIZE
        if event.button == 1 and game.pending:
            if col in legal_moves(game.board):
                record_guess(game, col)
        elif event.button == 1 and game.turn == 0 and not game.over and col in legal_moves(game.board):
            before = game.board
            game.board, game.turn = drop(before, col, 0), 1
            game.human = (before, col)
            game.preview, game.scroll, game.coach, game.hint = False, 0, None, None
        elif event.button == 3 and game.analysis and game.explain:
            game.contrast = why_not(game.analyzed, 1, game.analysis["depth"], game.analysis, col)
            game.view, game.scroll = "ai", 0
    return True


def advance_hint(game, executor):
    """While hints are on, find a suggested move for the human in the background."""
    job = game.hint_job
    if job is not None and job.done():
        game.hint_job = None
        try:
            result = job.result()
        except Exception:  # A hint is optional: never let it stop the game.
            result = None
        if result is not None and result["board"] == game.board and result["depth"] == game.hint_depth:
            game.hint = result
        return
    wanted = game.hinting and not game.study and game.turn == 0 and not game.over and not game.error
    stale = game.hint is None or game.hint["board"] != game.board or game.hint["depth"] != game.hint_depth
    if wanted and job is None and stale:
        board, depth = game.board, game.hint_depth
        game.hint_job = executor.submit(lambda: {**hint(board, 0, depth), "board": board})


def advance(game, executor):
    """Start the AI's turn in the background and collect its result."""
    advance_hint(game, executor)
    if game.turn != 1 or game.pending or game.error:
        return
    if game.over and not (game.coaching and game.human[1] is not None):
        game.turn = 0
        return
    if game.job is None:
        before, col = game.human
        game.job = executor.submit(think, before, col, game.board, game.depth, game.coaching)
    elif game.job.done():
        try:
            result = game.job.result()
        except Exception as error:
            game.error, game.job = type(error).__name__, None
            return
        game.job = None
        if game.study:
            game.pending = result
        else:
            play_ai_move(game, *result)


def draw(screen, fonts, game):
    def text(value, x, y, size=18, color=WHITE):
        screen.blit(fonts[size].render(str(value), True, color), (x, y))

    def spot(row, col):
        return BOARD.x + col * SIZE + 36, BOARD.bottom - row * SIZE - 36

    def height(board, col):
        return ((board[0] | board[1]) & sum(cell(row, col) for row in range(ROWS))).bit_count()

    analysis, study = game.analysis, game.study
    preview = game.preview and game.coach and game.explain and game.view == "coach"
    displayed = game.coach["before"] if preview else game.board
    screen.fill(BG)
    text("Connect Four", 25, 18, 32)
    text("You play yellow  •  AI plays red", 25, 60, 18, MUTED)
    if study:
        text(f"Study  ·  {study['participant']}  ·  {study['condition']}  ·  game {game.games + 1}", 582, 26, 20, TEAL)
        text(f"Depth {game.depth}", 582, 58, 18, MUTED)
    else:
        text(f"Depth {game.depth}  ·  Press 2 / 4 / 6", 582, 26, 20, TEAL)
        text(f"E  Explanations {'on' if game.explain else 'off'}    C  Coach {'on' if game.coaching else 'off'}"
             f"    H  Hint {'on' if game.hinting else 'off'}", 582, 58, 18, MUTED)

    # One chip per column: what the search concluded about each move the AI could have made.
    if preview:
        text("Review: the position BEFORE your last drop", 25, 106, 18, TEAL)
    elif analysis and game.explain:
        text("How the AI rated each column before its move", 25, 86, 15, MUTED)
        for col in range(COLS):
            box = pygame.Rect(BOARD.x + col * SIZE + 3, 106, SIZE - 6, 28)
            if col in analysis["scores"]:
                kind = outcome(analysis["scores"][col], analysis["depth"])[0]
                caption = analysis["labels"][col].replace(" in ", " ")
            else:
                kind, caption = "eval", "full"
            pygame.draw.rect(screen, CHIP[kind], box, border_radius=8)
            if col == analysis["column"]:
                pygame.draw.rect(screen, WHITE, box, 2, border_radius=8)
            width = fonts[15].size(caption)[0]
            text(caption, box.centerx - width // 2, box.y + 5, 15)
    for col in range(COLS):
        text(col + 1, BOARD.x + col * SIZE + 30, 140, 18, MUTED)
    pygame.draw.rect(screen, "#2d5090", BOARD, border_radius=16)
    for row in range(ROWS):
        for col in range(COLS):
            bit = cell(row, col)
            color = YELLOW if displayed[0] & bit else RED if displayed[1] & bit else BG
            pygame.draw.circle(screen, color, spot(row, col), 28)
    if preview:
        for col, color, radius in ((game.coach["column"], YELLOW, 29), (game.coach["best"], TEAL, 23)):
            pygame.draw.circle(screen, color, spot(height(displayed, col), col), radius, 3)
    elif analysis:
        col = analysis["column"]
        pygame.draw.circle(screen, WHITE, spot(height(game.analyzed, col), col), 30, 2)
        contrast = game.contrast
        if (game.explain and contrast and contrast["column"] != col and contrast["column"] in analysis["scores"]
                and not game.hint_ready):
            alt = contrast["column"]
            pygame.draw.circle(screen, TEAL, spot(height(game.analyzed, alt), alt), 30, 2)
    if game.hint_ready:
        col = game.hint["column"]
        pygame.draw.circle(screen, HINT, spot(height(game.board, col), col), 31, 4)
        text(f"Your turn  ·  Hint: column {col + 1}", 25, 606, 24, HINT)
    elif game.hinting and not study and game.turn == 0 and not game.over and not game.error:
        text("Your turn  ·  finding a hint...", 25, 606, 24, YELLOW)
    else:
        text(game.status, 25, 606, 24, YELLOW)
    if study:
        text("Click a column to play or to guess     R  New game     Esc  Quit", 25, 648, 18, MUTED)
    else:
        text("R  New game     F1  Win     F2  Block     F3  Search     Esc  Quit", 25, 648, 18, MUTED)
        if game.view == "coach" and game.coach and game.explain:
            button(screen, fonts, PREVIEW_BUTTON, "Return to live board" if preview else "Show pre-move board", preview)
            text("Yellow: played / teal: best" if preview else "Game over - press R" if game.over else "Live board - keep playing", 303, 681, 15, MUTED)
        else:
            text("Right-click a column to ask why the AI did not play there", 25, 676, 18, MUTED)

    pygame.draw.rect(screen, PANEL, (560, 100, 515, 600), border_radius=16)
    if study:
        text("AI move analysis", TEXT_X, 120, 24)
    else:
        button(screen, fonts, AI_TAB, "AI decision", game.view == "ai")
        button(screen, fonts, COACH_TAB, "Your move / Coach", game.view == "coach", game.coaching)
    content = pygame.Surface((TEXT_WIDTH, 2300))
    content.fill(PANEL)
    content_height = draw_details(content, fonts, game)
    game.max_scroll = max(0, content_height - VIEWPORT.height)
    game.scroll = max(0, min(game.scroll, game.max_scroll))
    screen.blit(content, VIEWPORT.topleft, (0, game.scroll, VIEWPORT.width, VIEWPORT.height))
    if game.max_scroll:
        track = pygame.Rect(VIEWPORT.right + 8, VIEWPORT.y, 4, VIEWPORT.height)
        pygame.draw.rect(screen, "#33476a", track, border_radius=2)
        height_px = max(30, int(VIEWPORT.height ** 2 / content_height))
        thumb_y = track.y + int((track.height - height_px) * game.scroll / game.max_scroll)
        pygame.draw.rect(screen, MUTED, (track.x, thumb_y, track.width, height_px), border_radius=2)
    note = "Scroll inside this panel. Scores favor YOU." if game.view == "coach" and game.coaching else "Scroll inside this panel. Scores favor the AI."
    if study and not game.explain:
        note = ""
    text(note, TEXT_X, 668, 15, MUTED)


def button(screen, fonts, rect, caption, active=False, enabled=True):
    pygame.draw.rect(screen, "#27666a" if active and enabled else "#2a3a57", rect, border_radius=8)
    rendered = fonts[18].render(caption, True, WHITE if enabled else MUTED)
    screen.blit(rendered, rendered.get_rect(center=rect.center))


def draw_details(screen, fonts, game):
    """Draw all evidence into scrollable content with a fixed, reachable header."""
    y = 0

    def paragraph(value, size=20, color=WHITE):
        nonlocal y
        for part in str(value).split("\n"):
            line = ""
            for word in part.split():
                candidate = f"{line} {word}".strip()
                if fonts[size].size(candidate)[0] > TEXT_WIDTH - 12 and line:
                    screen.blit(fonts[size].render(line, True, color), (0, y))
                    line, y = word, y + size + 7
                else:
                    line = candidate
            screen.blit(fonts[size].render(line, True, color), (0, y))
            y += size + 7
        y += 8

    analysis, study = game.analysis, game.study
    if game.error:
        paragraph(f"Analysis failed ({game.error}). Press R to start a new game.", color=RED)
        return y
    if game.hint_ready:
        tip = game.hint
        paragraph(f"Hint for your next move  ·  column {tip['column'] + 1}  ·  {tip['labels'][tip['column']]}", color=HINT)
        paragraph(tip["text"])
        steps = " -> ".join(f"{'You' if index % 2 == 0 else 'AI'} {col + 1}" for index, col in enumerate(tip["line"]))
        paragraph(f"Expected line: {steps}", 18, MUTED)
        others = ", ".join(f"{col + 1}: {tip['labels'][col]}" for col in sorted(tip["scores"]) if col != tip["column"])
        if others:
            paragraph(f"Other columns  {others}", 18, MUTED)
        paragraph(f"Searched {tip['depth']} plies ahead ({tip['nodes']:,} nodes), {tip['depth'] - game.depth} more than "
                  f"the AI. Scores favor you. A hint is the best move found, not a guaranteed win.", 15, MUTED)
    if not game.explain:
        if analysis:
            paragraph(f"AI played column {analysis['column'] + 1}.", color=YELLOW)
        if not study:
            paragraph("Explanations are hidden. Press E to show them.", 18, MUTED)
        return y
    if game.view == "coach" and game.coaching and not study:
        coach = game.coach
        if coach is None:
            paragraph("Play a move with Coach on to review your choice. The review uses the board before your drop.", color=MUTED)
            return y
        paragraph(f"Your column {coach['column'] + 1} - {coach['verdict'].upper()}", color=VERDICT[coach["verdict"]])
        paragraph(coach["text"])
        paragraph(f"Played score {coach['score']:+d}; recommended column {coach['best'] + 1}: {coach['best_score']:+d}. Gap: {coach['score_gap']}.", color=TEAL)
        paragraph(f"Depth {coach['depth']} - {coach['nodes']:,} nodes - {coach['cutoffs']:,} cutoffs", 18)
        paragraph("Every candidate uses the SAME pre-move board and depth. Higher scores favor you. A tied best move is accepted.", 18, MUTED)
        for heading, line in (("Your searched line", coach["played_line"]), ("Recommended line", coach["best_line"])):
            steps = " -> ".join(f"{'You' if index % 2 == 0 else 'AI'} {col + 1}" for index, col in enumerate(line))
            paragraph(f"{heading}: {steps}", 18, TEAL)
        paragraph("All legal choices from your perspective", color=YELLOW)
        for col, score in sorted(coach["scores"].items(), key=lambda item: -item[1]):
            tags = []
            if col == coach["column"]:
                tags.append("played")
            if score == coach["best_score"]:
                tags.append("tied best" if col != coach["best"] else "recommended")
            paragraph(f"Column {col + 1}: {label(score, coach['depth'])}  {' / '.join(tags)}", 18)
        paragraph("Win N counts your winning drops. Loss N counts the AI's winning drops. Lines alternate both players and assume best play within this depth. Signed numbers are heuristic estimates, not win probabilities.", 18, MUTED)
        return y

    if game.demo:
        paragraph(game.demo, color=TEAL)
    if not analysis:
        intro = ("Play a move, then guess where the AI will reply." if study
                 else "Play a move or load a demo position to see the AI's decision.")
        paragraph(intro, color=MUTED)
        return y
    chosen = analysis["column"]
    if game.guess is not None:
        hit = "correct" if game.guess == chosen else "not this time"
        paragraph(f"Your guess: column {game.guess + 1}  ·  {hit}", color=TEAL)
    paragraph(f"AI played column {chosen + 1}  ·  {analysis['labels'][chosen]}", color=YELLOW)
    paragraph(analysis["explanation"])
    contrast = game.contrast
    if contrast:
        alt = contrast["column"]
        heading = f"Why not column {alt + 1}?"
        if alt in analysis["labels"] and alt != chosen:
            heading += f"  ·  {analysis['labels'][alt]}"
        paragraph(heading, color=TEAL)
        paragraph(contrast["text"], color=MUTED)
        if contrast["line"]:
            steps = ", ".join(f"{'AI' if index % 2 == 0 else 'You'} {col + 1}" for index, col in enumerate(contrast["line"]))
            paragraph(f"Expected line: {steps}", 18, MUTED)
    paragraph(f"Depth {analysis['depth']}  ·  {analysis['nodes']:,} nodes  ·  {analysis['cutoffs']:,} cutoffs"
              f"  ·  {game.elapsed:.0f} ms", 18)
    paragraph("These scores describe the position BEFORE the AI's last drop. Win N counts AI drops; Loss N counts your drops. Signed values are depth-limited heuristic estimates, not win probabilities.", 18, MUTED)
    return y


def main(smoke=False, study=None):
    pygame.init()
    screen = pygame.display.set_mode(WINDOW)
    pygame.display.set_caption("Connect Four | Explainable AI")
    clock = pygame.time.Clock()
    fonts = {size: pygame.font.SysFont("arial", size, bold=size >= 24) for size in (15, 18, 20, 24, 32)}
    game = Game(study)
    running = True
    with ThreadPoolExecutor(max_workers=1) as executor:
        while running:
            for event in pygame.event.get():
                running = running and handle(game, event)
            if running:
                advance(game, executor)
            draw(screen, fonts, game)
            pygame.display.flip()
            if smoke:
                running = False
            clock.tick(60)
    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Connect Four with an AI that explains its moves.")
    parser.add_argument("--smoke", action="store_true", help="Render one frame and exit.")
    parser.add_argument("--study", metavar="ID", help="Run the prediction study for this participant, e.g. P01.")
    parser.add_argument("--condition", choices=("explain", "control"), default="explain",
                        help="Study group: explanations shown (explain) or hidden (control).")
    args = parser.parse_args()
    main(args.smoke, {"participant": args.study, "condition": args.condition} if args.study else None)
