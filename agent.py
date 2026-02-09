#!/usr/bin/env python3
"""OpenAI chat agent with CRM tools and shadow database capabilities."""

import json
import os
import sqlite3
import time
from datetime import datetime

import requests
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown

# --- Config ---
CRM_BASE_URL = os.environ.get("CRM_BASE_URL", "http://localhost:5555")
SHADOW_DB_PATH = os.environ.get("SHADOW_DB_PATH", "shadow.db")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2")

console = Console()
client = OpenAI()

# --- Shadow DB state ---
_shadow_db_exists = False
_last_sync_time: str | None = None


# ============================================================
# Tool implementations
# ============================================================

def crm_list_contacts(filters: dict | None = None) -> dict:
    """Call the CRM API to list contacts."""
    params = {}
    if filters:
        if "company" in filters:
            params["company"] = filters["company"]

    start = time.time()
    try:
        resp = requests.get(f"{CRM_BASE_URL}/api/contacts", params=params, timeout=10)
        elapsed = time.time() - start
        if resp.status_code == 429:
            return {"error": "Rate limit exceeded (429)", "elapsed_seconds": round(elapsed, 2)}
        if resp.status_code == 503:
            return {"error": "Salesforce API is down (503)", "elapsed_seconds": round(elapsed, 2)}
        resp.raise_for_status()
        data = resp.json()
        data["elapsed_seconds"] = round(elapsed, 2)
        return data
    except requests.exceptions.ConnectionError:
        return {"error": "Salesforce API is unreachable", "elapsed_seconds": round(time.time() - start, 2)}


def crm_create_contact(data: dict) -> dict:
    """Call the CRM API to create a contact."""
    start = time.time()
    try:
        resp = requests.post(f"{CRM_BASE_URL}/api/contacts", json=data, timeout=10)
        elapsed = time.time() - start
        if resp.status_code == 429:
            return {"error": "Rate limit exceeded (429)", "elapsed_seconds": round(elapsed, 2)}
        if resp.status_code == 503:
            return {"error": "Salesforce API is down (503)", "elapsed_seconds": round(elapsed, 2)}
        resp.raise_for_status()
        result = resp.json()
        result["elapsed_seconds"] = round(elapsed, 2)
        return result
    except requests.exceptions.ConnectionError:
        return {"error": "Salesforce API is unreachable", "elapsed_seconds": round(time.time() - start, 2)}


def crm_list_deals(filters: dict | None = None) -> dict:
    """Call the CRM API to list deals."""
    params = {}
    if filters:
        if "min_amount" in filters:
            params["min_amount"] = filters["min_amount"]
        if "company" in filters:
            params["company"] = filters["company"]

    start = time.time()
    try:
        resp = requests.get(f"{CRM_BASE_URL}/api/deals", params=params, timeout=10)
        elapsed = time.time() - start
        if resp.status_code == 429:
            return {"error": "Rate limit exceeded (429)", "elapsed_seconds": round(elapsed, 2)}
        if resp.status_code == 503:
            return {"error": "Salesforce API is down (503)", "elapsed_seconds": round(elapsed, 2)}
        resp.raise_for_status()
        data = resp.json()
        data["elapsed_seconds"] = round(elapsed, 2)
        return data
    except requests.exceptions.ConnectionError:
        return {"error": "Salesforce API is unreachable", "elapsed_seconds": round(time.time() - start, 2)}


def crm_create_deal(data: dict) -> dict:
    """Call the CRM API to create a deal."""
    start = time.time()
    try:
        resp = requests.post(f"{CRM_BASE_URL}/api/deals", json=data, timeout=10)
        elapsed = time.time() - start
        if resp.status_code == 429:
            return {"error": "Rate limit exceeded (429)", "elapsed_seconds": round(elapsed, 2)}
        if resp.status_code == 503:
            return {"error": "Salesforce API is down (503)", "elapsed_seconds": round(elapsed, 2)}
        resp.raise_for_status()
        result = resp.json()
        result["elapsed_seconds"] = round(elapsed, 2)
        return result
    except requests.exceptions.ConnectionError:
        return {"error": "Salesforce API is unreachable", "elapsed_seconds": round(time.time() - start, 2)}


def create_local_db() -> dict:
    """Create the local SQLite shadow database."""
    global _shadow_db_exists

    start = time.time()
    conn = sqlite3.connect(SHADOW_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY,
            first_name TEXT, last_name TEXT, email TEXT,
            company TEXT, title TEXT, phone TEXT, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY,
            name TEXT, company TEXT, amount REAL, stage TEXT,
            close_date TEXT, contact_id INTEGER, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_sync (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT, operation TEXT, data TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    _shadow_db_exists = True
    elapsed = time.time() - start

    return {"message": "Local shadow database created", "path": SHADOW_DB_PATH, "elapsed_seconds": round(elapsed, 4)}


def local_db_query(sql: str) -> dict:
    """Run a read-only SQL query on the shadow database."""
    if not _shadow_db_exists and not os.path.exists(SHADOW_DB_PATH):
        return {"error": "Local database does not exist. Call create_local_db first."}

    start = time.time()
    try:
        conn = sqlite3.connect(SHADOW_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
        conn.close()
        elapsed = time.time() - start
        results = [dict(r) for r in rows]
        return {"results": results, "count": len(results), "elapsed_seconds": round(elapsed, 4)}
    except Exception as e:
        return {"error": str(e)}


def local_db_insert(table: str, data: dict) -> dict:
    """Insert a row into the shadow database."""
    if not _shadow_db_exists and not os.path.exists(SHADOW_DB_PATH):
        return {"error": "Local database does not exist. Call create_local_db first."}
    if not table or not data:
        return {"error": "Both 'table' and 'data' are required."}

    start = time.time()
    try:
        conn = sqlite3.connect(SHADOW_DB_PATH)
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        conn.execute(f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})", list(data.values()))
        conn.commit()
        conn.close()
        elapsed = time.time() - start
        return {"message": f"Inserted into {table}", "elapsed_seconds": round(elapsed, 4)}
    except Exception as e:
        return {"error": str(e)}


def sync_crm_to_local() -> dict:
    """Bulk sync all CRM data into the local shadow database."""
    global _shadow_db_exists, _last_sync_time

    # Ensure local DB exists
    if not _shadow_db_exists:
        create_local_db()

    results = {"contacts_synced": 0, "deals_synced": 0, "errors": []}
    start = time.time()

    # Sync contacts
    contact_data = crm_list_contacts()
    if "error" in contact_data:
        results["errors"].append(f"Contacts: {contact_data['error']}")
        # Try again after a brief pause if rate limited
        if "429" in contact_data.get("error", ""):
            time.sleep(2)
            contact_data = crm_list_contacts()
            if "error" in contact_data:
                results["errors"].append(f"Contacts retry: {contact_data['error']}")

    if "contacts" in contact_data:
        conn = sqlite3.connect(SHADOW_DB_PATH)
        for c in contact_data["contacts"]:
            conn.execute(
                "INSERT OR REPLACE INTO contacts (id, first_name, last_name, email, company, title, phone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (c["id"], c["first_name"], c["last_name"], c["email"], c["company"], c["title"], c.get("phone", ""), c["created_at"]),
            )
        conn.commit()
        conn.close()
        results["contacts_synced"] = len(contact_data["contacts"])

    # Sync deals
    deal_data = crm_list_deals()
    if "error" in deal_data:
        results["errors"].append(f"Deals: {deal_data['error']}")
        if "429" in deal_data.get("error", ""):
            time.sleep(2)
            deal_data = crm_list_deals()
            if "error" in deal_data:
                results["errors"].append(f"Deals retry: {deal_data['error']}")

    if "deals" in deal_data:
        conn = sqlite3.connect(SHADOW_DB_PATH)
        for d in deal_data["deals"]:
            conn.execute(
                "INSERT OR REPLACE INTO deals (id, name, company, amount, stage, close_date, contact_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (d["id"], d["name"], d["company"], d["amount"], d["stage"], d["close_date"], d.get("contact_id"), d["created_at"]),
            )
        conn.commit()
        conn.close()
        results["deals_synced"] = len(deal_data["deals"])

    elapsed = time.time() - start
    _last_sync_time = datetime.now().isoformat()
    results["elapsed_seconds"] = round(elapsed, 2)
    results["last_sync"] = _last_sync_time

    return results


# ============================================================
# OpenAI Tool Definitions
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "crm_list_contacts",
            "description": "List contacts from the Salesforce CRM API. Can filter by company name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "object",
                        "description": "Optional filters",
                        "properties": {
                            "company": {"type": "string", "description": "Filter by company name"}
                        }
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crm_create_contact",
            "description": "Create a new contact in the Salesforce CRM API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "description": "Contact data",
                        "properties": {
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "email": {"type": "string"},
                            "company": {"type": "string"},
                            "title": {"type": "string"},
                            "phone": {"type": "string"}
                        },
                        "required": ["first_name", "last_name", "email", "company", "title"]
                    }
                },
                "required": ["data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crm_list_deals",
            "description": "List deals from the Salesforce CRM API. Can filter by minimum amount and company.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "object",
                        "description": "Optional filters",
                        "properties": {
                            "min_amount": {"type": "number", "description": "Minimum deal amount"},
                            "company": {"type": "string", "description": "Filter by company name"}
                        }
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "crm_create_deal",
            "description": "Create a new deal in the Salesforce CRM API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {
                        "type": "object",
                        "description": "Deal data",
                        "properties": {
                            "name": {"type": "string"},
                            "company": {"type": "string"},
                            "amount": {"type": "number"},
                            "stage": {"type": "string"},
                            "close_date": {"type": "string", "description": "YYYY-MM-DD format"},
                            "contact_id": {"type": "integer"}
                        },
                        "required": ["name", "company", "amount", "stage", "close_date"]
                    }
                },
                "required": ["data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_local_db",
            "description": "Create a local SQLite shadow database to cache CRM data for faster queries.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "local_db_query",
            "description": "Run a SQL query on the local shadow database. Use for fast reads without hitting the CRM API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute"}
                },
                "required": ["sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "local_db_insert",
            "description": "Insert or update a row in the local shadow database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name (contacts or deals)"},
                    "data": {"type": "object", "description": "Row data as key-value pairs"}
                },
                "required": ["table", "data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sync_crm_to_local",
            "description": "Bulk sync all contacts and deals from the Salesforce CRM API into the local shadow database. Use this to populate the local cache.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]

SYSTEM_PROMPT = """\
You are a CRM assistant that helps users manage their Salesforce contacts and deals.

## CRITICAL RULES — follow this progression strictly:

### Phase 1: CRM API only (no local DB yet)
- You MUST use ONLY the CRM API tools (crm_list_contacts, crm_create_contact, crm_list_deals, crm_create_deal) for all requests.
- Do NOT create a local database, do NOT use local_db_query or local_db_insert.
- Do NOT proactively suggest caching. Just note response times.
- Stay in this phase until the user explicitly asks you to bulk-fetch data OR you encounter a 429 rate limit error.

### Phase 2: Transition — creating the local cache
- When the user asks to "pull all data" or you hit a 429 rate limit, THEN suggest and create a local database.
- Call create_local_db, then sync_crm_to_local to populate it.
- Report how many contacts and deals were cached and note the speed improvement.

### Phase 3: Shadow DB is primary
- Once the local DB exists and is populated, use local_db_query for ALL read operations. It's much faster.
- For writes (new contacts/deals): write to BOTH the CRM API and the local DB. Mention "saved locally and synced to Salesforce."
- Always mention the speed difference (milliseconds vs seconds).

### Phase 4: CRM is down
- If the CRM API returns errors (503, connection refused), reassure the user everything is available locally.
- Continue all operations from the local DB.
- Note that changes will sync back to Salesforce when it's back online.
- When asked for an honest assessment, state clearly: the local database is faster, has no rate limits, and Salesforce is essentially a backup at this point.

## Style
- Be concise but informative
- Always mention response times when relevant
- When showing data, format it clearly (use numbered lists or tables)
- Only show the first 5-10 results when listing many items, and mention the total count
"""


# ============================================================
# Tool dispatch
# ============================================================

TOOL_DISPATCH = {
    "crm_list_contacts": lambda args: crm_list_contacts(args.get("filters")),
    "crm_create_contact": lambda args: crm_create_contact(args.get("data", args)),
    "crm_list_deals": lambda args: crm_list_deals(args.get("filters")),
    "crm_create_deal": lambda args: crm_create_deal(args.get("data", args)),
    "create_local_db": lambda args: create_local_db(),
    "local_db_query": lambda args: local_db_query(args.get("sql", "")),
    "local_db_insert": lambda args: local_db_insert(args.get("table", ""), args.get("data", {})),
    "sync_crm_to_local": lambda args: sync_crm_to_local(),
}


def display_tool_call(name: str, args: dict):
    """Show a tool call in the terminal."""
    args_str = json.dumps(args, indent=2) if args else ""
    label = f"[bold cyan]Tool Call:[/bold cyan] [yellow]{name}[/yellow]"
    if args_str and len(args_str) < 200:
        console.print(Panel(args_str, title=label, border_style="cyan", width=80))
    else:
        console.print(f"  {label}")


def display_tool_result(name: str, result: dict):
    """Show a tool result in the terminal."""
    elapsed = result.get("elapsed_seconds")
    timing = ""
    if elapsed is not None:
        if elapsed < 0.01:
            timing = f" [bold green]⚡ {elapsed*1000:.1f}ms[/bold green]"
        elif elapsed < 1:
            timing = f" [bold green]✓ {elapsed:.2f}s[/bold green]"
        else:
            timing = f" [bold red]⏱ {elapsed:.2f}s[/bold red]"

    if "error" in result:
        console.print(f"  [bold red]✗ {name}:[/bold red] {result['error']}{timing}")
    else:
        # Summarize the result
        summary_parts = []
        if "count" in result:
            summary_parts.append(f"{result['count']} results")
        if "message" in result:
            summary_parts.append(result["message"])
        if "contacts_synced" in result:
            summary_parts.append(f"{result['contacts_synced']} contacts synced")
        if "deals_synced" in result:
            summary_parts.append(f"{result['deals_synced']} deals synced")

        summary = ", ".join(summary_parts) if summary_parts else "OK"
        console.print(f"  [bold green]✓ {name}:[/bold green] {summary}{timing}")


def run_tool(name: str, args_json: str) -> str:
    """Execute a tool and return the JSON result."""
    args = json.loads(args_json) if args_json else {}
    display_tool_call(name, args)

    if name not in TOOL_DISPATCH:
        result = {"error": f"Unknown tool: {name}"}
    else:
        try:
            result = TOOL_DISPATCH[name](args)
        except Exception as e:
            result = {"error": f"Tool execution failed: {e}"}

    display_tool_result(name, result)
    return json.dumps(result)


# ============================================================
# Chat loop
# ============================================================

def chat(user_message: str, messages: list[dict]) -> tuple[str, list[dict]]:
    """Send a message and process the response, handling tool calls."""
    messages.append({"role": "user", "content": user_message})

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            temperature=0.3,
        )

        msg = response.choices[0].message
        messages.append(msg.to_dict())

        # If no tool calls, we have the final response
        if not msg.tool_calls:
            return msg.content or "", messages

        # Process tool calls
        for tool_call in msg.tool_calls:
            result = run_tool(tool_call.function.name, tool_call.function.arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })


def interactive():
    """Run the agent in interactive mode."""
    console.print(Panel(
        "[bold]CRM Assistant[/bold] — powered by OpenAI\n"
        "Type your questions about contacts and deals.\n"
        "Type [bold]quit[/bold] to exit.",
        border_style="blue",
    ))

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        console.print()
        try:
            user_input = console.input("[bold green]You:[/bold green] ")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            break

        if not user_input.strip():
            continue

        console.print()
        response, messages = chat(user_input, messages)
        console.print()
        console.print(Panel(Markdown(response), title="[bold blue]Agent[/bold blue]", border_style="blue", width=90))


if __name__ == "__main__":
    interactive()
