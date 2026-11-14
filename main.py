"""Pygame interface: play the AI, read its reasoning, get coached, or run the prediction study."""

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from time import perf_counter

import pygame

from engine import (COLS, ROWS, DEMO_POSITIONS, EMPTY, analyze, cell, drop, label, legal_moves, outcome,
                    replay, review, why_not, won)

BG = "#101829"
PANEL = "#1b2940"
WHITE = "#edf4ff"
MUTED = "#a8b8ce"
YELLOW = "#ffce66"
RED = "#ff737e"
TEAL = "#75dfcf"
CHIP = {"win": "#1f6357", "loss": "#7a2f3b", "eval": "#2a3a57"}
VERDICT = {"best": TEAL, "good": TEAL, "inaccuracy": YELLOW, "missed win": RED, "blunder": RED}
WINDOW = (1100, 720)
BOARD = pygame.Rect(25, 164, 504, 432)
SIZE = 72
TEXT_X, TEXT_WIDTH = 582, 470
RESULTS = Path(__file__).with_name("results")
STUDY_DEPTH = 4


class Game:
    """Everything the screen shows. `study` is None outside the prediction study."""

    def __init__(self, study=None):
        self.depth = STUDY_DEPTH
        self.explain = not study or study["condition"] == "explain"
        self.coaching = not study
        self.study = study
        self.games = 0
        self.reset()

    def reset(self, board=EMPTY, turn=0, demo=None):
        self.board, self.turn, self.demo = board, turn, demo
        self.analysis = self.analyzed = self.coach = self.contrast = None
        self.job = self.pending = self.guess = None
        self.elapsed, self.moves, self.rated = 0.0, 0, False
        self.human = (None, None)  # Board before the human's last move, and that move.

    @property
    def over(self):
        return won(self.board[0]) or won(self.board[1]) or not legal_moves(self.board)

    @property
    def status(self):
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
        elif key == pygame.K_c:
            game.coaching = not game.coaching
    if event.type == pygame.MOUSEBUTTONDOWN and BOARD.collidepoint(event.pos):
        col = (event.pos[0] - BOARD.x) // SIZE
        if event.button == 1 and game.pending:
            if col in legal_moves(game.board):
                record_guess(game, col)
        elif event.button == 1 and game.turn == 0 and not game.over and col in legal_moves(game.board):
            before = game.board
            game.board, game.turn = drop(before, col, 0), 1
            game.human = (before, col)
        elif event.button == 3 and game.analysis and game.explain:
            game.contrast = why_not(game.analyzed, 1, game.analysis["depth"], game.analysis, col)
    return True


def advance(game, executor):
    """Start the AI's turn in the background and collect its result."""
    if game.turn != 1 or game.over or game.pending:
        return
    if game.job is None:
        before, col = game.human
        game.job = executor.submit(think, before, col, game.board, game.depth, game.coaching)
    elif game.job.done():
        result, game.job = game.job.result(), None
        if game.study:
            game.pending = result
        else:
            play_ai_move(game, *result)


def draw(screen, fonts, game):
    def text(value, x, y, size=18, color=WHITE):
        screen.blit(fonts[size].render(str(value), True, color), (x, y))

    def paragraph(value, y, size=20, color=WHITE):
        line = ""
        for word in value.split():
            candidate = f"{line} {word}".strip()
            if fonts[size].size(candidate)[0] > TEXT_WIDTH:
                text(line, TEXT_X, y, size, color)
                line, y = word, y + size + 7
            else:
                line = candidate
        text(line, TEXT_X, y, size, color)
        return y + size + 7

    def spot(row, col):
        return BOARD.x + col * SIZE + 36, BOARD.bottom - row * SIZE - 36

    def height(board, col):
        return ((board[0] | board[1]) & sum(cell(row, col) for row in range(ROWS))).bit_count()

    analysis, study = game.analysis, game.study
    screen.fill(BG)
    text("Connect Four", 25, 18, 32)
    text("You play yellow  •  AI plays red", 25, 60, 18, MUTED)
    if study:
        text(f"Study  ·  {study['participant']}  ·  {study['condition']}  ·  game {game.games + 1}", 582, 26, 20, TEAL)
        text(f"Depth {game.depth}", 582, 58, 18, MUTED)
    else:
        text(f"Depth {game.depth}  ·  Press 2 / 4 / 6", 582, 26, 20, TEAL)
        text(f"E  Explanations {'on' if game.explain else 'off'}      C  Coach {'on' if game.coaching else 'off'}",
             582, 58, 18, MUTED)

    # One chip per column: what the search concluded about each move the AI could have made.
    if analysis and game.explain:
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
            color = YELLOW if game.board[0] & bit else RED if game.board[1] & bit else BG
            pygame.draw.circle(screen, color, spot(row, col), 28)
    if analysis:
        col = analysis["column"]
        pygame.draw.circle(screen, WHITE, spot(height(game.analyzed, col), col), 30, 2)
        contrast = game.contrast
        if game.explain and contrast and contrast["column"] != col and contrast["column"] in analysis["scores"]:
            alt = contrast["column"]
            pygame.draw.circle(screen, TEAL, spot(height(game.analyzed, alt), alt), 30, 2)
    text(game.status, 25, 606, 24, YELLOW)
    if study:
        text("Click a column to play or to guess     R  New game     Esc  Quit", 25, 648, 18, MUTED)
    else:
        text("R  New game     F1  Win     F2  Block     F3  Search     Esc  Quit", 25, 648, 18, MUTED)
        text("Right-click a column to ask why the AI did not play there", 25, 676, 18, MUTED)

    pygame.draw.rect(screen, PANEL, (560, 100, 515, 600), border_radius=16)
    text("AI move analysis", TEXT_X, 120, 24)
    if game.demo:
        text(game.demo, TEXT_X, 156, 18, TEAL)
    y = 190
    if not analysis:
        intro = ("Play a move, then guess where the AI will reply." if study
                 else "Play a move or load a demo position to see the AI's decision.")
        paragraph(intro, y, 20, MUTED)
        return
    chosen = analysis["column"]
    if game.guess is not None:
        hit = "correct" if game.guess == chosen else "not this time"
        y = paragraph(f"Your guess: column {game.guess + 1}  ·  {hit}", y, 20, TEAL) + 8
    if not game.explain:
        y = paragraph(f"AI played column {chosen + 1}.", y, 20, YELLOW)
        if not study:
            paragraph("Explanations are hidden. Press E to show them.", y + 8, 18, MUTED)
        return
    y = paragraph(f"AI played column {chosen + 1}  ·  {analysis['labels'][chosen]}", y, 20, YELLOW)
    y = paragraph(analysis["explanation"], y + 4)
    contrast = game.contrast
    if contrast:
        alt = contrast["column"]
        heading = f"Why not column {alt + 1}?"
        if alt in analysis["labels"] and alt != chosen:
            heading += f"  ·  {analysis['labels'][alt]}"
        y = paragraph(heading, y + 16, 20, TEAL)
        y = paragraph(contrast["text"], y + 4, 20, MUTED)
        if contrast["line"]:
            steps = ", ".join(f"{'AI' if index % 2 == 0 else 'You'} {col + 1}" for index, col in enumerate(contrast["line"]))
            y = paragraph(f"Expected line: {steps}", y + 4, 18, MUTED)
    y = paragraph(f"Depth {analysis['depth']}  ·  {analysis['nodes']:,} nodes  ·  {analysis['cutoffs']:,} cutoffs"
                  f"  ·  {game.elapsed:.0f} ms", y + 16, 18)
    if game.coaching and game.coach:
        coach = game.coach
        pygame.draw.line(screen, "#33476a", (TEXT_X, y + 12), (TEXT_X + TEXT_WIDTH, y + 12))
        y = paragraph(f"Coach on your move  ·  column {coach['column'] + 1}", y + 26, 20)
        y = paragraph(coach["verdict"].upper(), y + 2, 18, VERDICT[coach["verdict"]])
        y = paragraph(coach["text"], y + 2, 20, MUTED)
    text("Scores are from the AI's side. Coach scores are from yours.", TEXT_X, 668, 15, MUTED)


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
