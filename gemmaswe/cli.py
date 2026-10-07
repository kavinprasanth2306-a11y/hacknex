"""Rich interactive Command-Line Interface for GemmaSWE."""

import sys
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn

from gemmaswe.agent.swe_agent import GemmaSweAgent
from gemmaswe.llm.gemma_provider import get_gemma_client
from gemmaswe.benchmark.suite import BenchmarkEvaluator
from gemmaswe.config import config

console = Console(force_terminal=True, legacy_windows=False)

def print_banner():
    console.print(Panel.fit(
        "[bold cyan]* GemmaSWE *[/bold cyan]\n"
        "[dim]Autonomous AI Software Engineering Agent powered by Google Gemma[/dim]\n"
        "[yellow]Regression-Immune | No Fake APIs | Minimal Diffs | Self-Verifying[/yellow]",
        border_style="cyan"
    ))

def handle_cli_events(event: dict):
    etype = event.get("type")
    if etype == "start":
        console.print(f"[bold green]>> Initializing GemmaSWE on repo:[/bold green] {event.get('repo')}")
        console.print(f"[dim]Model: {event.get('model')}[/dim]")
    elif etype == "baseline":
        console.print(f"[blue][Baseline Tests][/blue] {event.get('passed')} passed, {event.get('failed')} failed (Total: {event.get('total')})")
    elif etype == "thought":
        console.print(Panel(event.get('thought', ''), title=f"[magenta]Step {event.get('step')} Gemma Reasoning[/magenta]", border_style="magenta"))
    elif etype == "tool_call":
        console.print(f"[yellow][Action][/yellow] [bold]{event.get('action')}[/bold] with args: [dim]{event.get('args')}[/dim]")
    elif etype == "tool_result":
        res_str = str(event.get('result', ''))
        preview = res_str[:400] + ("..." if len(res_str) > 400 else "")
        console.print(f"[cyan]-> Result:[/cyan] {preview}\n")
    elif etype == "warning":
        console.print(f"[bold red]! {event.get('message')}[/bold red]")
    elif etype == "error":
        console.print(f"[bold red]X {event.get('error')}[/bold red]")

def run_agent_cli(repo_path: str, task: str, test_cmd: str = None, provider: str = None):
    print_banner()
    client = get_gemma_client(provider=provider)
    agent = GemmaSweAgent(repo_path=repo_path, client=client, event_callback=handle_cli_events)

    with console.status("[bold green]GemmaSWE is investigating and solving...[/bold green]"):
        result = agent.run(task_description=task, test_command=test_cmd)

    console.print("\n" + "="*60 + "\n")
    if result["success"]:
        console.print("[bold green][SUCCESS] TASK COMPLETED SUCCESSFULLY![/bold green]")
    else:
        console.print("[bold red][FAILED] TASK INCOMPLETE OR TESTS FAILING[/bold red]")

    # Print explanation
    if result.get("explanation"):
        console.print(Panel(result["explanation"], title="[bold green]Root Cause & Solution Explanation[/bold green]"))

    # Print Diff
    if result.get("diff"):
        console.print(Panel(
            Syntax(result["diff"], "diff", theme="monokai", line_numbers=True),
            title="[bold yellow]Minimal Applied Diff[/bold yellow]"
        ))

    # Print Audit Scorecard
    audit = result.get("audit", {})
    if audit:
        table = Table(title="Judge Evaluation & Rule Compliance Scorecard", border_style="cyan")
        table.add_column("Criterion", style="white")
        table.add_column("Score", justify="right", style="green")
        table.add_column("Status", style="bold")

        sb = audit.get("score_breakdown", {})
        table.add_row("Regression Immunity (Working tests preserved)", f"{sb.get('regression_immunity', 0)}/30", "PASS" if sb.get('regression_immunity', 0) > 0 else "FAIL")
        table.add_row("Real APIs Only (Zero fake imports/modules)", f"{sb.get('real_apis_only', 0)}/20", "PASS" if sb.get('real_apis_only', 0) > 0 else "FAIL")
        table.add_row("Clean & Minimal Code Patch", f"{sb.get('clean_and_minimal', 0)}/15", "PASS" if sb.get('clean_and_minimal', 0) > 0 else "FAIL")
        table.add_row("Visible Acceptance Tests Pass", f"{sb.get('tests_pass', 0)}/25", "PASS" if sb.get('tests_pass', 0) > 0 else "FAIL")
        table.add_row("Root Cause Explanation Quality", f"{sb.get('explanation_quality', 0)}/10", "PASS" if sb.get('explanation_quality', 0) > 0 else "FAIL")
        table.add_section()
        table.add_row("[bold]TOTAL SCORE[/bold]", f"[bold]{audit.get('total_score', 0)}/100[/bold]", f"[bold]{audit.get('verdict', 'N/A')}[/bold]")
        console.print(table)

def run_benchmark_cli():
    print_banner()
    console.print("[bold cyan]Running Autonomous SWE Benchmark Suite (with 30-Pt Hidden Tests)...[/bold cyan]\n")
    res = BenchmarkEvaluator.run_auth_scenario(provider=config.provider)

    table = Table(title="Benchmark Evaluation Results", border_style="green")
    table.add_column("Scenario", style="cyan")
    table.add_column("Visible Tests", style="green")
    table.add_column("Hidden Tests (30 pts)", style="yellow")
    table.add_column("Diff Size", style="magenta")
    table.add_column("Verdict", style="bold green")

    visible_status = "PASS" if res["agent_success"] else "FAIL"
    hidden_status = f"{res['hidden_score']}/30 PASS" if res["hidden_tests_passed"] else "0/30 FAIL"
    audit = res.get("audit", {})
    diff_size = f"+{audit.get('lines_added', 0)} / -{audit.get('lines_removed', 0)}"

    table.add_row(
        res["scenario"],
        visible_status,
        hidden_status,
        diff_size,
        audit.get("verdict", "DONE")
    )
    console.print(table)

def main():
    parser = argparse.ArgumentParser(description="GemmaSWE: Autonomous AI Software Engineering Agent")
    subparsers = parser.add_subparsers(dest="command")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run agent on a codebase")
    run_parser.add_argument("repo", help="Path to local codebase repository or git URL")
    run_parser.add_argument("--task", required=True, help="Task description or bug to fix")
    run_parser.add_argument("--test-cmd", default=None, help="Custom test command")
    run_parser.add_argument("--provider", default=None, help="LLM provider: google, groq, openrouter, ollama, mock")

    # Benchmark command
    subparsers.add_parser("benchmark", help="Run the full benchmark suite with hidden test scoring")

    # Serve web dashboard
    serve_parser = subparsers.add_parser("serve", help="Launch the interactive Web Dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on")

    args = parser.parse_args()

    if args.command == "run":
        run_agent_cli(args.repo, args.task, test_cmd=args.test_cmd, provider=args.provider)
    elif args.command == "benchmark":
        run_benchmark_cli()
    elif args.command == "serve":
        from gemmaswe.web.server import start_server
        start_server(host=args.host, port=args.port)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
