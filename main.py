"""Pygame interface for the playable game and three prepared demo positions."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pygame

from engine import COLS, ROWS, DEMO_POSITIONS, EMPTY, analyze, cell, drop, heuristic, legal_moves, replay, won

BG = "#101829"
PANEL = "#1b2940"
WHITE = "#edf4ff"
MUTED = "#a8b8ce"
YELLOW = "#ffce66"
RED = "#ff737e"
TEAL = "#75dfcf"
BOARD = pygame.Rect(25, 135, 504, 432)
SIZE = 72


def main(smoke=False):
    pygame.init()
    screen = pygame.display.set_mode((980, 650))
    pygame.display.set_caption("Connect Four | Explainable AI")
    clock = pygame.time.Clock()
    fonts = {size: pygame.font.SysFont("arial", size, bold=size >= 24) for size in (15, 18, 20, 24, 32)}
    depth = 4
    selected_demo = 0
    demos = list(DEMO_POSITIONS)
    analysis, job = None, None
    board, turn = EMPTY, 0
    elapsed = 0.0
    running = True

    def label(value, x, y, size=18, color=WHITE):
        screen.blit(fonts[size].render(str(value), True, color), (x, y))

    def paragraph(value, y, color=WHITE):
        words = value.split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if fonts[20].size(candidate)[0] > 365:
                label(line, 573, y, 20, color)
                line, y = word, y + 27
            else:
                line = candidate
        label(line, 573, y, 20, color)
        return y + 27

    with ThreadPoolExecutor(max_workers=1) as executor:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if event.key == pygame.K_r:
                        board, turn, analysis, selected_demo = EMPTY, 0, None, 0
                        if job:
                            job.cancel()
                        job = None
                    if event.key in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
                        selected_demo = event.key - pygame.K_F1 + 1
                        position, player = replay(DEMO_POSITIONS[demos[selected_demo - 1]])
                        board = position if player == 1 else position[::-1]
                        turn, analysis = 1, None
                        if job:
                            job.cancel()
                        job = None
                    if event.key in (pygame.K_2, pygame.K_4, pygame.K_6):
                        depth = event.key - pygame.K_0
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and BOARD.collidepoint(event.pos):
                    col = (event.pos[0] - BOARD.x) // SIZE
                    if turn == 0 and col in legal_moves(board) and not won(board[1]) and not won(board[0]):
                        board, turn = drop(board, col, 0), 1

            if running and turn == 1 and legal_moves(board) and not won(board[0]) and not won(board[1]):
                if job is None:
                    before, started = board, perf_counter()
                    job = executor.submit(analyze, before, 1, depth)
                if job.done():
                    analyzed_board = before
                    analysis = job.result()
                    elapsed = (perf_counter() - started) * 1000
                    board = drop(before, analysis["column"], 1)
                    turn, job = 0, None

            screen.fill(BG)
            label("Connect Four", 25, 24, 32)
            label("You play yellow  •  AI plays red", 25, 69, 18, MUTED)
            label(f"Depth {depth}  ·  Press 2 / 4 / 6", 683, 32, 20, TEAL)
            for col in range(COLS):
                label(col + 1, BOARD.x + col * SIZE + 30, 108, 18, MUTED)
            pygame.draw.rect(screen, "#2d5090", BOARD, border_radius=16)
            for row in range(ROWS):
                for col in range(COLS):
                    bit = cell(row, col)
                    color = YELLOW if board[0] & bit else RED if board[1] & bit else BG
                    point = (BOARD.x + col * SIZE + 36, BOARD.bottom - row * SIZE - 36)
                    pygame.draw.circle(screen, color, point, 28)
            if analysis:
                col = analysis["column"]
                row = ((analyzed_board[0] | analyzed_board[1]) & sum(cell(row, col) for row in range(ROWS))).bit_count()
                point = (BOARD.x + col * SIZE + 36, BOARD.bottom - row * SIZE - 36)
                pygame.draw.circle(screen, WHITE, point, 30, 2)
            status = ("You win!" if won(board[0]) else "AI wins!" if won(board[1])
                      else "Draw" if not legal_moves(board) else "AI is thinking..." if turn else "Your turn")
            label(status, 25, 580, 24, YELLOW)
            label("R  New game    F1  Win    F2  Block    F3  Search", 25, 618, 18, MUTED)
            pygame.draw.rect(screen, PANEL, (552, 104, 403, 504), border_radius=16)
            label("AI move analysis", 573, 126, 24)
            if selected_demo:
                label(demos[selected_demo - 1], 573, 165, 18, TEAL)
            if analysis:
                chosen, alt = analysis["column"], analysis["alternative"]
                label(f"Selected column {chosen + 1}  ·  score {analysis['score']}", 573, 202, 20, YELLOW)
                y = paragraph(analysis["explanation"], 235)
                if alt is not None:
                    label(f"Alternative column {alt + 1}  ·  score {analysis['scores'][alt]}", 573, y + 18, 20, TEAL)
                y = paragraph(analysis["comparison"], y + 52, MUTED)
                y = paragraph(f"Static heuristic after the selected move: {heuristic(drop(analyzed_board, chosen, 1), 1)}.",
                              y + 22, MUTED) if analysis["reason"] != "win" else y + 22
                label(f"Depth {analysis['depth']}  ·  {analysis['nodes']:,} nodes  ·  {elapsed:.0f} ms", 573, y + 16, 18)
                paragraph("Scores are from the AI's perspective.", y + 48, MUTED)
            else:
                paragraph("Play a move or load a demo position to see the AI's decision.", 217, MUTED)

            pygame.display.flip()
            if smoke:
                running = False
            clock.tick(60)
    pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Render one frame and exit.")
    main(parser.parse_args().smoke)
