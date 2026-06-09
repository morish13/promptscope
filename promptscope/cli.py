import os
import csv
import json
import typer
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from datetime import datetime

from promptscope.scorer import score_prompt, compare_prompts
from promptscope.db import save_result, get_history, get_by_id, delete_record

app = typer.Typer(help="promptscope — analyze and improve your prompts")
console = Console()


def _score_bar(val: int, width: int = 20) -> str:
    filled = int((val / 10) * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "green" if val >= 7 else "yellow" if val >= 4 else "red"
    return f"[{color}]{bar}[/{color}] {val}/10"


@app.command()
def score(
    prompt: str = typer.Argument(None, help="Prompt text to analyze"),
    file: str = typer.Option(None, "--file", "-f", help="Read prompt from file"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save result to history"),
    rewrite: bool = typer.Option(True, "--rewrite/--no-rewrite", help="Show rewrite suggestion"),
    mock: bool = typer.Option(False, "--mock", help="Run without API (offline mode)"),
):
    """Analyze a prompt and get quality scores."""
    if mock:
        os.environ["PROMPTSCOPE_MOCK"] = "1"
        import importlib
        import promptscope.scorer as sc
        importlib.reload(sc)
        console.print("[dim yellow]⚠ mock mode — no API call[/dim yellow]\n")

    if file:
        try:
            with open(file) as f:
                text = f.read().strip()
        except FileNotFoundError:
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
    elif prompt:
        text = prompt
    elif not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    else:
        text = typer.prompt("Paste your prompt")

    if not text:
        console.print("[red]No prompt provided.[/red]")
        raise typer.Exit(1)

    with console.status("[cyan]Analyzing prompt...[/cyan]"):
        result = score_prompt(text)

    if save:
        rid = save_result(result)
        console.print(f"[dim]Saved as #{rid}[/dim]\n")

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("Dimension", style="bold")
    t.add_column("Score")

    labels = {
        "clarity": "Clarity",
        "specificity": "Specificity",
        "goal_alignment": "Goal Alignment",
        "instruction_following_likelihood": "IFL",
        "ambiguity_risk": "Ambiguity Risk (inv.)",
    }
    for key, label in labels.items():
        val = result.scores.get(key, 0)
        t.add_row(label, _score_bar(val))

    overall_color = "green" if result.overall >= 7 else "yellow" if result.overall >= 4 else "red"
    t.add_row("", "")
    t.add_row("[bold]Overall[/bold]", f"[{overall_color} bold]{result.overall:.1f}/10[/{overall_color} bold]")

    console.print(Panel(t, title="[bold]Prompt Score[/bold]", border_style="cyan"))

    if result.strengths:
        console.print("[green bold]Strengths:[/green bold]")
        for s in result.strengths:
            console.print(f"  [green]✓[/green] {s}")

    if result.weaknesses:
        console.print("\n[red bold]Weaknesses:[/red bold]")
        for w in result.weaknesses:
            console.print(f"  [red]✗[/red] {w}")

    if rewrite and result.rewrite_suggestion:
        console.print("\n")
        console.print(Panel(
            result.rewrite_suggestion,
            title="[yellow bold]Suggested Rewrite[/yellow bold]",
            border_style="yellow",
        ))


@app.command()
def compare(
    prompt_a: str = typer.Argument(None, help="First prompt"),
    prompt_b: str = typer.Argument(None, help="Second prompt"),
    file_a: str = typer.Option(None, "--file-a", "-a"),
    file_b: str = typer.Option(None, "--file-b", "-b"),
    mock: bool = typer.Option(False, "--mock", help="Run without API"),
):
    """Compare two prompts head-to-head."""
    if mock:
        os.environ["PROMPTSCOPE_MOCK"] = "1"
        import importlib
        import promptscope.scorer as sc
        importlib.reload(sc)
        console.print("[dim yellow]⚠ mock mode — no API call[/dim yellow]\n")

    def _read(text, filepath):
        if filepath:
            with open(filepath) as f:
                return f.read().strip()
        if text:
            return text
        return typer.prompt("Paste prompt")

    a = _read(prompt_a, file_a)
    b = _read(prompt_b, file_b)

    with console.status("[cyan]Comparing prompts...[/cyan]"):
        result = compare_prompts(a, b)

    winner = result.get("winner", "tie")
    color = "green" if winner != "tie" else "yellow"
    console.print(f"\n[{color} bold]Winner: Prompt {winner}[/{color} bold]\n")
    console.print(f"[dim]{result.get('reasoning', '')}[/dim]\n")

    t = Table(box=box.SIMPLE)
    t.add_column("Prompt A advantages", style="cyan")
    t.add_column("Prompt B advantages", style="magenta")

    adv_a = result.get("a_advantages", [])
    adv_b = result.get("b_advantages", [])
    for i in range(max(len(adv_a), len(adv_b))):
        t.add_row(
            adv_a[i] if i < len(adv_a) else "",
            adv_b[i] if i < len(adv_b) else "",
        )
    console.print(t)


@app.command()
def batch(
    file: str = typer.Argument(..., help="File with one prompt per line"),
    save: bool = typer.Option(True, "--save/--no-save"),
    mock: bool = typer.Option(False, "--mock", help="Run without API"),
):
    """Score multiple prompts from a file, one per line."""
    if mock:
        os.environ["PROMPTSCOPE_MOCK"] = "1"
        import importlib
        import promptscope.scorer as sc
        importlib.reload(sc)
        console.print("[dim yellow]⚠ mock mode — no API call[/dim yellow]\n")

    try:
        with open(file) as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    if not lines:
        console.print("[red]No prompts found in file.[/red]")
        raise typer.Exit(1)

    results = []
    with console.status(f"[cyan]Scoring {len(lines)} prompts...[/cyan]") as status:
        for i, p in enumerate(lines, 1):
            status.update(f"[cyan]Scoring {i}/{len(lines)}...[/cyan]")
            r = score_prompt(p)
            if save:
                save_result(r)
            results.append(r)

    t = Table(box=box.SIMPLE, title=f"Batch Results ({len(results)} prompts)")
    t.add_column("#", style="dim")
    t.add_column("Prompt")
    t.add_column("Overall", justify="center")

    for i, r in enumerate(results, 1):
        preview = r.raw_prompt[:50] + "..." if len(r.raw_prompt) > 50 else r.raw_prompt
        c = "green" if r.overall >= 7 else "yellow" if r.overall >= 4 else "red"
        t.add_row(str(i), preview, f"[{c}]{r.overall:.1f}[/{c}]")

    console.print(t)

    best = max(results, key=lambda r: r.overall)
    worst = min(results, key=lambda r: r.overall)
    avg = sum(r.overall for r in results) / len(results)

    console.print(f"\n[green]Best:[/green]  {best.overall:.1f} — {best.raw_prompt[:50]}")
    console.print(f"[red]Worst:[/red] {worst.overall:.1f} — {worst.raw_prompt[:50]}")
    console.print(f"[cyan]Average:[/cyan] {avg:.1f}/10")


@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n"),
    full: int = typer.Option(None, "--full", help="Show full detail for a record ID"),
    delete: int = typer.Option(None, "--delete", "-d", help="Delete a record by ID"),
    export: str = typer.Option(None, "--export", help="Export history: json or csv"),
    out: str = typer.Option(None, "--out", "-o", help="Output file path for export"),
):
    """View, export, or delete scoring history."""
    if delete is not None:
        if delete_record(delete):
            console.print(f"[green]Deleted #{delete}[/green]")
        else:
            console.print(f"[red]Record #{record_id} not found[/red]")
        return

    if full is not None:
        rec = get_by_id(full)
        if not rec:
            console.print(f"[red]Record #{full} not found[/red]")
            raise typer.Exit(1)
        console.print(Panel(rec["prompt"], title=f"[bold]#{full} — Prompt[/bold]"))
        console.print(f"Overall: [bold]{rec['overall']:.1f}/10[/bold]")
        console.print(f"Strengths: {', '.join(rec['strengths'])}")
        console.print(f"Weaknesses: {', '.join(rec['weaknesses'])}")
        if rec["rewrite"]:
            console.print(Panel(rec["rewrite"], title="Rewrite", border_style="yellow"))
        return

    rows = get_history(limit=100)

    if export:
        fmt = export.lower()
        filename = out or f"promptscope_export.{fmt}"
        if fmt == "json":
            with open(filename, "w") as f:
                json.dump(rows, f, indent=2)
            console.print(f"[green]Exported {len(rows)} records to {filename}[/green]")
        elif fmt == "csv":
            if not rows:
                console.print("[yellow]No records to export.[/yellow]")
                return
            keys = ["id", "prompt", "overall", "created_at"]
            with open(filename, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for r in rows:
                    writer.writerow({k: r[k] for k in keys})
            console.print(f"[green]Exported {len(rows)} records to {filename}[/green]")
        else:
            console.print(f"[red]Unknown format: {fmt}. Use json or csv.[/red]")
        return

    if not rows:
        console.print("[dim]No history yet. Run: promptscope score \"your prompt\"[/dim]")
        return

    t = Table(box=box.SIMPLE)
    t.add_column("#", style="dim")
    t.add_column("Prompt (truncated)")
    t.add_column("Overall", justify="center")
    t.add_column("Date", style="dim")

    for r in rows[:limit]:
        dt = datetime.fromtimestamp(r["created_at"]).strftime("%b %d %H:%M")
        score_val = r["overall"]
        color = "green" if score_val >= 7 else "yellow" if score_val >= 4 else "red"
        t.add_row(
            str(r["id"]),
            r["prompt"],
            f"[{color}]{score_val:.1f}[/{color}]",
            dt,
        )
    console.print(t)


@app.command()
def trend(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent scores to show"),
):
    """Show how your prompt scores have changed over time."""
    rows = get_history(limit=limit)
    if len(rows) < 2:
        console.print("[yellow]Need at least 2 scored prompts to show a trend.[/yellow]")
        return

    rows = list(reversed(rows))
    scores = [r["overall"] for r in rows]
    dates = [datetime.fromtimestamp(r["created_at"]).strftime("%m/%d %H:%M") for r in rows]

    height = 10
    min_s, max_s = 0, 10
    width = len(scores)

    grid = [[" " for _ in range(width)] for _ in range(height)]
    for col, val in enumerate(scores):
        row = height - 1 - int(round((val - min_s) / (max_s - min_s) * (height - 1)))
        row = max(0, min(height - 1, row))
        grid[row][col] = "●"

    console.print("\n[bold cyan]Score Trend[/bold cyan]")
    for i, row in enumerate(grid):
        label = f"{10 - i:2d} │"
        line = "".join(row)
        colored = line.replace("●", "[cyan]●[/cyan]")
        console.print(f"[dim]{label}[/dim]{colored}")

    console.print(f"[dim]   └{'─' * width}[/dim]")

    avg = sum(scores) / len(scores)
    trend_dir = "↑ improving" if scores[-1] > scores[0] else "↓ declining" if scores[-1] < scores[0] else "→ stable"
    color = "green" if "improving" in trend_dir else "red" if "declining" in trend_dir else "yellow"
    console.print(f"\nAverage: [bold]{avg:.1f}/10[/bold]  Trend: [{color}]{trend_dir}[/{color}]")
    console.print(f"[dim]Showing last {len(scores)} scored prompts[/dim]\n")


def main():
    app()


if __name__ == "__main__":
    main()
