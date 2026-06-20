import asyncio
import sys
import uuid
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Confirm, Prompt
from rich.theme import Theme
from rich.table import Table

from config.settings import settings
from core.agent_loop import AgentLoop
from core.orchestrator import GeminiOrchestrator
from storage.memory import MemoryManager
from security.guardrails import CommandGuard, SecurityLevel

# Setup gorgeous rich colors
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "danger": "bold red",
    "success": "bold green",
    "title": "bold white on blue",
    "prompt": "bold yellow"
})

console = Console(theme=custom_theme)
app = typer.Typer(help="GenAIShell: The production-grade GenAI Terminal Assistant.")

# Global state
session_id = str(uuid.uuid4())
memory = MemoryManager()


def cli_confirm_callback(command: str, reason: str) -> bool:
    """Injectable safety callback that renders a gorgeous Rich panel asking for user execution confirmation."""
    console.print("\n")
    panel_content = (
        f"[bold yellow]⚠️ SECURITY CHECKPOINT[/bold yellow]\n\n"
        f"[bold white]Action:[/bold white] {command}\n"
        f"[bold white]Reason:[/bold white] {reason}\n\n"
        f"[dim]Please review this action carefully before giving authorization.[/dim]"
    )
    console.print(Panel(panel_content, border_style="yellow", expand=False))
    
    # Block and wait for User Interactive response
    approved = Confirm.ask("[prompt]Do you authorize executing this system action?[/prompt]", default=False)
    console.print("\n")
    return approved


async def run_goal_async(prompt_text: str):
    """Orchestrates running a single natural language task with an animated loading spinner."""
    # Check if Groq key is set before running
    if not settings.groq_api_key:
        console.print("[danger]Error: GROQ_API_KEY environment variable is not configured.[/danger]")
        console.print("Please set it in your .env file or export it in your shell environment.")
        raise typer.Exit(code=1)

    agent = AgentLoop(session_id=session_id, confirm_callback=cli_confirm_callback)

    def stream_cb(text: str):
        # We can stream incremental updates or print log actions
        if "Executing tool" in text:
            console.print(f"[info]⚡ {text.strip()}[/info]")

    console.print("\n[bold blue]GenAIShell is planning and executing your goal...[/bold blue]")
    try:
        response = await agent.execute_goal(prompt_text, streaming_callback=stream_cb)
    except Exception as e:
        console.print(f"[danger]Execution failed with error: {e}[/danger]")
        raise typer.Exit(code=1)

    console.print("\n")
    console.print(Panel(Markdown(response), title="[bold green]GenAIShell Response[/bold green]", border_style="green"))


@app.command()
def ask(
    prompt: str = typer.Argument(..., help="Natural language goal to execute (e.g. 'Create folders src and tests')")
):
    """Executes a single natural language command securely and exits."""
    asyncio.run(run_goal_async(prompt))


@app.command()
def interactive():
    """Launches an immersive, continuous interactive chat console with session persistence."""
    console.print("\n")
    welcome_msg = (
        "[bold green]✨ Welcome to GenAIShell Terminal Assistant! ✨[/bold green]\n"
        f"[dim]Session: {session_id} | Platform: {sys.platform} | Safe Mode: {settings.safe_mode_enabled}[/dim]\n\n"
        "I am ready. Ask me to perform file operations, git workflows, system checks,\n"
        "kill ports, search local docs, or run custom CLI shell tasks.\n"
        "Type [bold cyan]exit[/bold cyan] or [bold cyan]quit[/bold cyan] to terminate this session."
    )
    console.print(Panel(welcome_msg, border_style="cyan"))

    if not settings.groq_api_key:
        console.print("[danger]Error: GROQ_API_KEY environment variable is missing. Set it in .env to continue.[/danger]")
        raise typer.Exit(code=1)

    agent = AgentLoop(session_id=session_id, confirm_callback=cli_confirm_callback)

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]GenAIShell[/bold cyan]").strip()
            
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                console.print("[dim cyan]Closing session. Goodbye! 🚀[/dim cyan]")
                break

            def stream_cb(text: str):
                if "Executing tool" in text:
                    console.print(f"[info]⚡ {text.strip()}[/info]")

            console.print("\n[bold blue]Thinking...[/bold blue]")
            response = asyncio.run(agent.execute_goal(user_input, streaming_callback=stream_cb))

            console.print("\n")
            console.print(Panel(Markdown(response), title="[bold green]GenAIShell Response[/bold green]", border_style="green"))

        except KeyboardInterrupt:
            console.print("\n[dim cyan]Session interrupted. Goodbye![/dim cyan]")
            break
        except Exception as e:
            console.print(f"[danger]Error occurred during transaction: {e}[/danger]")


@app.command()
def clear_history():
    """Clears all SQLite conversation histories and local semantic vector store indexes."""
    confirm = Confirm.ask("[warning]Are you sure you want to purge all conversation logs and semantic memory?[/warning]", default=False)
    if not confirm:
        console.print("[info]Purge operation aborted.[/info]")
        return

    # Clear SQLite session memory
    try:
        memory.clear_session(session_id)
        # Clear vector index
        orchestrator = GeminiOrchestrator()
        orchestrator.vector_store.clear()
        
        console.print("[success]Memory successfully cleared and database indices truncated.[/success]")
    except Exception as e:
        console.print(f"[danger]Failed to clear memory databases: {e}[/danger]")


@app.command()
def docs_index(
    path: str = typer.Argument(..., help="Path to text/markdown document to index for semantic local RAG searches"),
    category: str = typer.Option("Documentation", help="Metadata category tag for search filters")
):
    """Indexes text/markdown documentation files into the vector database for local RAG support."""
    doc_path = Path(path).resolve()
    if not doc_path.exists():
        console.print(f"[danger]Error: Target file not found at {path}[/danger]")
        raise typer.Exit(code=1)

    if doc_path.is_dir():
        console.print(f"[danger]Error: Targeting directory. Please supply a single text/markdown file.[/danger]")
        raise typer.Exit(code=1)

    console.print(f"[info]Reading file contents at {doc_path}...[/info]")
    try:
        with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read().strip()

        if not content:
            console.print("[warning]Target file is empty. Indexing skipped.[/warning]")
            return

        orchestrator = GeminiOrchestrator()
        
        # Chunk document simple-style by paragraphs or 1000 characters if too large
        chunks = []
        words = content.split()
        chunk_size = 200  # Words per chunk
        for i in range(0, len(words), chunk_size):
            chunks.append(" ".join(words[i:i+chunk_size]))

        console.print(f"[info]Generating vector embeddings for {len(chunks)} chunks using local model...[/info]")
        
        with console.status("[bold blue]Computing embeddings...[/bold blue]", spinner="earth"):
            for idx, chunk in enumerate(chunks):
                orchestrator.add_to_rag_store(chunk, category=category)

        console.print(f"[success]Indexing completed! Added {len(chunks)} records to vector DB under category: '{category}'[/success]")
    except Exception as e:
        console.print(f"[danger]Failed to complete vector indexing: {e}[/danger]")


if __name__ == "__main__":
    app()
