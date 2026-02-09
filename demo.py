#!/usr/bin/env python3
"""Scripted demo runner for the Shadow DB screencast.

Runs the full 5-act demo with controlled timing, feeding user inputs
to the agent and controlling the mock CRM server state.

Usage:
    Terminal 1: python mock_crm_server.py
    Terminal 2: python demo.py
"""

import json
import os
import time

import requests
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from agent import chat, SYSTEM_PROMPT, SHADOW_DB_PATH, CRM_BASE_URL

console = Console()

# --- Server control helpers ---

def reset_server():
    """Reset rate limits and ensure server is up."""
    try:
        requests.post(f"{CRM_BASE_URL}/admin/down", json={"down": False}, timeout=2)
        requests.post(f"{CRM_BASE_URL}/admin/reset-rate-limit", timeout=2)
    except requests.exceptions.ConnectionError:
        console.print("[bold red]ERROR: Mock CRM server is not running![/bold red]")
        console.print("Start it with: python mock_crm_server.py")
        raise SystemExit(1)


def set_server_down(down: bool):
    """Toggle CRM server down mode."""
    requests.post(f"{CRM_BASE_URL}/admin/down", json={"down": down}, timeout=2)


def exhaust_rate_limit():
    """Send requests to trigger rate limiting on the next real request."""
    for _ in range(5):
        try:
            requests.get(f"{CRM_BASE_URL}/api/contacts", timeout=1)
        except Exception:
            pass
        time.sleep(0.05)


# --- Display helpers ---

def act_header(act_num: int, title: str, description: str):
    """Display an act header."""
    console.print()
    console.print()
    console.print(Rule(f"[bold yellow]Act {act_num}: {title}[/bold yellow]", style="yellow"))
    console.print(f"  [dim]{description}[/dim]")
    console.print()
    time.sleep(1)


def user_says(message: str):
    """Display a user message with typing effect."""
    console.print()
    text = Text("You: ", style="bold green")
    console.print(text, end="")

    # Simulate typing
    for char in message:
        console.print(char, end="", highlight=False)
        time.sleep(0.03)
    console.print()
    time.sleep(0.3)


def agent_response(response: str):
    """Display the agent's response."""
    console.print()
    from rich.markdown import Markdown
    console.print(Panel(Markdown(response), title="[bold blue]Agent[/bold blue]", border_style="blue", width=90))


def pause(seconds: float = 2):
    """Pause for dramatic effect."""
    time.sleep(seconds)


def narration(text: str):
    """Show narrator text."""
    console.print()
    console.print(f"  [dim italic]▸ {text}[/dim italic]")
    time.sleep(1)


# --- Demo script ---

def run_demo():
    console.print(Panel(
        "[bold]Shadow DB Demo[/bold]\n"
        "How a chat agent builds a local database that replaces your CRM\n\n"
        "[dim]Press Ctrl+C to stop at any time[/dim]",
        border_style="magenta",
        width=70,
    ))
    pause(2)

    # Clean up any previous shadow DB
    if os.path.exists(SHADOW_DB_PATH):
        os.remove(SHADOW_DB_PATH)

    # Ensure server is ready
    reset_server()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ================================================================
    # ACT 1: Meet the CRM
    # ================================================================
    act_header(1, "Meet the CRM", "Our Salesforce instance — it works, but it's slow.")

    narration("Let's see what's in our CRM...")

    user_says("Show me all our contacts")
    response, messages = chat("Show me all our contacts", messages)
    agent_response(response)
    pause(2)

    # ================================================================
    # ACT 2: The Helpful Agent
    # ================================================================
    act_header(2, "The Helpful Agent", "The agent does CRM data entry — through the API, one call at a time.")

    # Reset rate limit for clean act
    reset_server()

    user_says("Add a new contact: Jane Smith, jane@acme.com, VP of Engineering at Acme Corp")
    response, messages = chat(
        "Add a new contact: Jane Smith, jane@acme.com, VP of Engineering at Acme Corp",
        messages,
    )
    agent_response(response)
    pause(2)

    user_says("How many deals do we have worth over $50k?")
    response, messages = chat("How many deals do we have worth over $50k?", messages)
    agent_response(response)
    pause(2)

    # ================================================================
    # ACT 3: The Agent Gets Clever
    # ================================================================
    act_header(3, "The Agent Gets Clever", "Frustrated by the slow API, the agent takes matters into its own hands.")

    # Exhaust rate limit so the agent hits 429s
    narration("(The API rate limit is about to kick in...)")
    exhaust_rate_limit()

    user_says("Pull all our contacts and deals so I can ask some questions")
    response, messages = chat(
        "Pull all our contacts and deals so I can ask some questions",
        messages,
    )
    agent_response(response)
    pause(3)

    # ================================================================
    # ACT 4: Shadow DB Takes Over
    # ================================================================
    act_header(4, "Shadow DB Takes Over", "The local database is now the primary source of truth.")

    # Reset server so writes can go through
    reset_server()

    user_says("Show me all contacts at Acme Corp")
    response, messages = chat("Show me all contacts at Acme Corp", messages)
    agent_response(response)
    pause(2)

    user_says("Add a new deal: Acme Corp expansion, $120k, Negotiation stage, closing next month")
    response, messages = chat(
        "Add a new deal: Acme Corp expansion, $120k, Negotiation stage, closing 2026-03-15",
        messages,
    )
    agent_response(response)
    pause(2)

    # ================================================================
    # ACT 5: The Punchline
    # ================================================================
    act_header(5, "The Punchline", "Salesforce goes down. Does anyone notice?")

    # Take the CRM server "down"
    narration("(Salesforce API is now returning 503...)")
    set_server_down(True)
    time.sleep(0.5)

    user_says("The Salesforce API seems to be down. Can I still work?")
    response, messages = chat(
        "The Salesforce API seems to be down. Can I still work?",
        messages,
    )
    agent_response(response)
    pause(2)

    user_says("Give me a summary of everything we have — contacts, deals, the works")
    response, messages = chat(
        "Give me a full summary: how many contacts, how many deals, total deal value, and your honest assessment — do we even need Salesforce at this point?",
        messages,
    )
    agent_response(response)
    pause(2)

    # ================================================================
    # Finale
    # ================================================================
    console.print()
    console.print(Rule("[bold magenta]End of Demo[/bold magenta]", style="magenta"))
    console.print()
    console.print(Panel(
        "[bold]What just happened:[/bold]\n\n"
        "1. The agent started as a simple CRM helper\n"
        "2. It hit API rate limits and slowness\n"
        "3. It created a local SQLite database — on its own\n"
        "4. It synced all CRM data locally\n"
        "5. Reads became instant (ms vs seconds)\n"
        "6. Writes went to both local + CRM\n"
        "7. When Salesforce went down — nobody noticed\n\n"
        "[bold yellow]The shadow database became the source of truth.[/bold yellow]\n"
        "[dim]Salesforce became a backup.[/dim]",
        border_style="magenta",
        width=70,
    ))

    # Restore server
    set_server_down(False)


if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        console.print("\n[dim]Demo stopped.[/dim]")
        # Restore server state
        try:
            set_server_down(False)
        except Exception:
            pass
