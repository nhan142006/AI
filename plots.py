"""Draw the figures for the essay from the CSV files in results/. Run experiment.py first."""

import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(__file__).with_name("results")
FIGURES = RESULTS / "figures"
BLUE, ORANGE, GRAY, INK = "#2b59c3", "#e08a00", "#8a93a6", "#14213d"
REASONS = ("win", "block", "forced_win", "lost", "avoid", "threat", "search")

plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": GRAY, "axes.labelcolor": INK, "text.color": INK,
                     "xtick.color": INK, "ytick.color": INK, "figure.dpi": 150})


def read(filename):
    path = RESULTS / filename
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def save(figure, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(FIGURES / name)
    plt.close(figure)
    print(f"Saved {FIGURES / name}")


def search_nodes():
    rows = read("search.csv")
    groups = defaultdict(list)
    for row in rows:
        groups[row["algorithm"], int(row["depth"])].append(int(row["nodes"]))
    figure, axis = plt.subplots(figsize=(7, 4.2))
    styles = {"Minimax": (GRAY, "s"), "Alpha-Beta left first": (ORANGE, "^"), "Alpha-Beta": (BLUE, "o")}
    names = {"Minimax": "Minimax", "Alpha-Beta left first": "Alpha-Beta, left to right",
             "Alpha-Beta": "Alpha-Beta, center first"}
    depths = sorted({depth for _, depth in groups})
    for algorithm, (color, marker) in styles.items():
        values = [median(groups[algorithm, depth]) for depth in depths]
        axis.plot(depths, values, color=color, marker=marker, linewidth=2)
        axis.annotate(f"{names[algorithm]}\n{values[-1]:,.0f} nodes", (depths[-1], values[-1]),
                      xytext=(8, 0), textcoords="offset points", va="center", color=color)
    axis.set_yscale("log")
    axis.set_xticks(depths)
    axis.set_xlim(depths[0] - 0.2, depths[-1] + 2.6)
    axis.set_xlabel("Search depth (plies)")
    axis.set_ylabel("Nodes searched (log scale)")
    axis.set_title("Pruning and move ordering cut the search (median of 5 positions)",
                   loc="left", fontweight="bold")
    save(figure, "search_nodes.png")


def overhead():
    rows = read("overhead.csv")
    plain, explained = defaultdict(list), defaultdict(list)
    for row in rows:
        plain[int(row["depth"])].append(float(row["ms_plain"]))
        explained[int(row["depth"])].append(float(row["ms_explained"]))
    depths = sorted(plain)
    figure, axis = plt.subplots(figsize=(7, 4.2))
    for values, color, marker, name in ((plain, GRAY, "s", "Choose a move"),
                                        (explained, BLUE, "o", "Choose and explain")):
        medians = [median(values[depth]) for depth in depths]
        axis.plot(depths, medians, color=color, marker=marker, linewidth=2)
        axis.annotate(f"{name}\n{medians[-1]:,.0f} ms", (depths[-1], medians[-1]), xytext=(8, 0),
                      textcoords="offset points", va="center", color=color)
    for depth in depths:
        ratio = median(explained[depth]) / median(plain[depth])
        axis.annotate(f"×{ratio:.1f}", (depth, median(explained[depth])), xytext=(-8, 6),
                      textcoords="offset points", ha="right", color=BLUE)
    axis.set_yscale("log")
    axis.set_xticks(depths)
    axis.set_xlim(depths[0] - 0.2, depths[-1] + 2.2)
    axis.set_xlabel("Search depth (plies)")
    axis.set_xlim(depths[0] - 0.6, depths[-1] + 2.4)
    axis.set_ylabel("Time per move (ms, log scale)")
    axis.set_title(f"What an explanation costs (median of {len(plain[depths[0]])} positions)",
                   loc="left", fontweight="bold")
    save(figure, "overhead.png")


def faithfulness():
    rows = read("faithfulness_summary.csv")
    positions, true, claims, false = (defaultdict(int) for _ in range(4))
    for row in rows:
        positions[row["reason"]] += int(row["positions"])
        true[row["reason"]] += int(row["positions_all_true"])
        claims[row["reason"]] += int(row["claims"])
        false[row["reason"]] += int(row["claims_false"])
    reasons = [reason for reason in REASONS if positions[reason]][::-1]
    figure, axis = plt.subplots(figsize=(7, 4.2))
    axis.barh(reasons, [positions[reason] for reason in reasons], color="#d5dae4", label="Positions tested")
    axis.barh(reasons, [true[reason] for reason in reasons], color=BLUE, height=0.5, label="Every claim true")
    for reason in reasons:
        axis.annotate(f"{true[reason]}/{positions[reason]} positions, {claims[reason] - false[reason]:,}/{claims[reason]:,} claims",
                      (positions[reason], reason), xytext=(6, 0), textcoords="offset points", va="center")
    axis.set_xlim(0, max(positions.values()) * 1.75)
    axis.set_xlabel("Random positions, by the reason the AI gave")
    axis.set_title(f"Explanations checked by replay: {sum(true.values()):,} of {sum(positions.values()):,} fully true",
                   loc="left", fontweight="bold")
    axis.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    save(figure, "faithfulness.png")


def strength():
    rows = read("games_summary.csv")
    opponents = sorted({row["opponent"] for row in rows}, reverse=True)
    figure, axes = plt.subplots(1, len(opponents), figsize=(7, 3.8), sharey=True)
    for axis, opponent in zip(axes, opponents):
        group = sorted((row for row in rows if row["opponent"] == opponent), key=lambda row: int(row["depth"]))
        labels = [f"Depth {row['depth']}" for row in group]
        bottom = [0] * len(group)
        for key, color, name in (("wins", BLUE, "Win"), ("draws", "#d5dae4", "Draw"), ("losses", ORANGE, "Loss")):
            values = [int(row[key]) for row in group]
            bars = axis.bar(labels, values, bottom=bottom, color=color, label=name, edgecolor="white")
            for bar, value in zip(bars, values):
                if value:
                    axis.annotate(str(value), (bar.get_x() + bar.get_width() / 2, bar.get_y() + value / 2),
                                  ha="center", va="center", color="white" if key != "draws" else INK)
            bottom = [low + value for low, value in zip(bottom, values)]
        axis.set_title(f"Against {opponent}", loc="left")
    axes[0].set_ylabel("Games (20 per bar)")
    axes[0].set_yticks(range(0, 21, 5))
    figure.legend(*axes[-1].get_legend_handles_labels(), frameon=False, loc="upper right", ncol=3)
    figure.suptitle("Playing strength by search depth", x=0.02, ha="left", fontweight="bold")
    save(figure, "strength.png")


def study():
    """RQ2. Needs results/study.csv, which the game writes in --study mode."""
    rows = read("study.csv")
    if not rows:
        print("No study data yet: run `python main.py --study P01 --condition explain` with participants.")
        return
    guesses, hits, people = defaultdict(int), defaultdict(int), defaultdict(set)
    for row in rows:
        guesses[row["condition"]] += 1
        hits[row["condition"]] += int(row["correct"])
        people[row["condition"]].add(row["participant"])
    chance = sum(1 / int(row["legal_moves"]) for row in rows) / len(rows)
    conditions = [condition for condition in ("control", "explain") if guesses[condition]]
    names = {"control": "No explanations", "explain": "With explanations"}
    figure, axis = plt.subplots(figsize=(6, 4))
    for condition, color in zip(conditions, (GRAY, BLUE)):
        rate = hits[condition] / guesses[condition]
        axis.bar(names[condition], rate * 100, color=color, width=0.55)
        axis.annotate(f"{rate:.0%}\n{hits[condition]}/{guesses[condition]} guesses, {len(people[condition])} players",
                      (names[condition], rate * 100), xytext=(0, 6), textcoords="offset points", ha="center")
        print(f"{names[condition]}: {hits[condition]}/{guesses[condition]} correct ({rate:.1%}), "
              f"{len(people[condition])} participants")
    axis.axhline(chance * 100, color=INK, linestyle="--", linewidth=1)
    axis.annotate(f"Random guessing {chance:.0%}", (len(conditions) - 0.5, chance * 100), xytext=(0, 4),
                  textcoords="offset points", ha="right")
    axis.set_ylim(0, 100)
    axis.set_ylabel("AI moves predicted correctly (%)")
    axis.set_title("Can players predict the AI's next move?", loc="left", fontweight="bold")
    save(figure, "study.png")
    ratings = defaultdict(list)
    for row in read("study_ratings.csv"):
        ratings[row["condition"]].append(int(row["understanding_1_to_5"]))
    for condition, values in ratings.items():
        print(f"{names[condition]}: self-rated understanding {sum(values) / len(values):.2f}/5 over {len(values)} games")


if __name__ == "__main__":
    search_nodes()
    overhead()
    faithfulness()
    strength()
    study()
