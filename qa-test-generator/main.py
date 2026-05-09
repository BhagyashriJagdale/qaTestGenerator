#!/usr/bin/env python3
"""
QA Test Case Generator - CLI Entry Point

Usage:
    python main.py generate "Your requirement here"
    python main.py generate -f requirements.txt
    python main.py server
"""

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()


def cmd_generate(args):
    """Generate test cases from a requirement."""
    from pipeline import generate_test_cases
    from core.models import GenerationConfig, ScenarioType
    from agents.planner_agent import InvalidRequirementError, IncompleteRequirementError
    
    # Get requirement text
    if args.file:
        requirement_text = Path(args.file).read_text()
    else:
        requirement_text = args.requirement
    
    if not requirement_text:
        console.print("[red]Error: No requirement provided[/red]")
        sys.exit(1)
    
    # Parse scenarios
    scenarios = []
    if args.scenarios:
        for s in args.scenarios.split(","):
            try:
                scenarios.append(ScenarioType(s.strip()))
            except ValueError:
                console.print(f"[yellow]Warning: Unknown scenario type '{s}'[/yellow]")
    
    # Create config
    config = GenerationConfig(
        include_manual=not args.no_manual,
        include_api=not args.no_api,
        include_ui=not args.no_ui,
        scenarios=scenarios if scenarios else [
            ScenarioType.HAPPY_PATH,
            ScenarioType.NEGATIVE,
            ScenarioType.EDGE_CASE,
            ScenarioType.BOUNDARY,
            ScenarioType.SECURITY,
        ]
    )
    
    # Run generation
    try:
        result = generate_test_cases(
            requirement_text=requirement_text,
            input_type=args.type,
            project_context=args.context,
            tech_stack=args.tech,
            use_rag=not args.no_rag,
            config=config
        )
    except InvalidRequirementError as e:
        console.print(f"\n[bold red]✗ Invalid Requirement[/bold red]")
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except IncompleteRequirementError as e:
        console.print(f"\n[bold yellow]✗ Incomplete Requirement[/bold yellow]")
        console.print(f"[yellow]{e}[/yellow]")
        sys.exit(1)
    
    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(result.markdown_output)
        console.print(f"\n[green]✓ Output saved to: {output_path}[/green]")
    else:
        console.print("\n" + "=" * 60)
        console.print(result.markdown_output)
    
    return result


def cmd_server(args):
    """Start the API server."""
    from api.server import start_server
    
    console.print(Panel(
        f"[bold green]Starting QA Test Generator API Server[/bold green]\n\n"
        f"Host: {args.host}\n"
        f"Port: {args.port}\n"
        f"Docs: http://{args.host}:{args.port}/docs",
        title="🚀 Server",
        border_style="green"
    ))
    
    import uvicorn
    uvicorn.run(
        "api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


def cmd_rag_stats(args):
    """Show RAG knowledge base statistics."""
    from rag import get_rag_system
    
    rag = get_rag_system()
    stats = rag.get_stats()
    
    console.print(Panel(
        f"[bold]RAG Knowledge Base Statistics[/bold]\n\n"
        f"Status: {stats.get('status', 'unknown')}\n"
        f"Documents: {stats.get('count', 0)}\n"
        f"Persist Dir: {stats.get('persist_dir', 'N/A')}",
        title="📚 RAG Stats",
        border_style="blue"
    ))


def cmd_add_knowledge(args):
    """Add domain knowledge to RAG."""
    from rag import get_rag_system
    
    # Get content
    if args.file:
        content = Path(args.file).read_text()
    else:
        content = args.content
    
    if not content:
        console.print("[red]Error: No content provided[/red]")
        sys.exit(1)
    
    rag = get_rag_system()
    success = rag.add_domain_knowledge(
        content=content,
        domain=args.domain,
        knowledge_type=args.type
    )
    
    if success:
        console.print("[green]✓ Knowledge added successfully[/green]")
    else:
        console.print("[red]✗ Failed to add knowledge[/red]")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="QA Test Case Generator - AI-powered test case generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate test cases from inline requirement
  python main.py generate "User can login with email and password"
  
  # Generate from file
  python main.py generate -f requirements.txt -o tests.md
  
  # Generate only API tests
  python main.py generate "Login API" --no-manual --no-ui
  
  # Start API server
  python main.py server --port 8080
  
  # View RAG stats
  python main.py rag-stats
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate test cases")
    gen_parser.add_argument("requirement", nargs="?", help="Requirement text")
    gen_parser.add_argument("-f", "--file", help="Read requirement from file")
    gen_parser.add_argument("-o", "--output", help="Output file path")
    gen_parser.add_argument("-t", "--type", default="plain_text",
                           choices=["plain_text", "acceptance_criteria", "user_story"],
                           help="Input type")
    gen_parser.add_argument("-c", "--context", help="Project context")
    gen_parser.add_argument("--tech", help="Technology stack")
    gen_parser.add_argument("--scenarios", help="Comma-separated scenario types")
    gen_parser.add_argument("--no-manual", action="store_true", help="Skip manual tests")
    gen_parser.add_argument("--no-api", action="store_true", help="Skip API tests")
    gen_parser.add_argument("--no-ui", action="store_true", help="Skip UI tests")
    gen_parser.add_argument("--no-rag", action="store_true", help="Disable RAG")
    gen_parser.set_defaults(func=cmd_generate)
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Start API server")
    server_parser.add_argument("--host", default="0.0.0.0", help="Server host")
    server_parser.add_argument("--port", type=int, default=8000, help="Server port")
    server_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    server_parser.set_defaults(func=cmd_server)
    
    # RAG stats command
    rag_parser = subparsers.add_parser("rag-stats", help="Show RAG statistics")
    rag_parser.set_defaults(func=cmd_rag_stats)
    
    # Add knowledge command
    know_parser = subparsers.add_parser("add-knowledge", help="Add domain knowledge")
    know_parser.add_argument("content", nargs="?", help="Knowledge content")
    know_parser.add_argument("-f", "--file", help="Read content from file")
    know_parser.add_argument("-d", "--domain", required=True, help="Domain name")
    know_parser.add_argument("-t", "--type", default="best_practice",
                            help="Knowledge type")
    know_parser.set_defaults(func=cmd_add_knowledge)
    
    # Parse and execute
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Show banner
    console.print(Panel(
        "[bold cyan]QA Test Case Generator[/bold cyan]\n"
        "[dim]AI-Powered Test Case Generation[/dim]",
        border_style="cyan"
    ))
    
    # Execute command
    args.func(args)


if __name__ == "__main__":
    main()
