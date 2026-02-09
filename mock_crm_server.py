#!/usr/bin/env python3
"""Mock Salesforce CRM API with artificial delays, rate limiting, and down mode."""

import os
import sqlite3
import time
import threading
from flask import Flask, request, jsonify

from seed_data import seed, DB_PATH

app = Flask(__name__)

# --- Configuration ---
READ_DELAY = 2.0       # seconds delay for GET requests
WRITE_DELAY = 1.5      # seconds delay for POST requests
RATE_LIMIT = 5          # max requests per window
RATE_WINDOW = 10        # window in seconds

# --- State ---
_down_mode = False
_down_lock = threading.Lock()

_request_timestamps: list[float] = []
_rate_lock = threading.Lock()


def _is_down() -> bool:
    with _down_lock:
        return _down_mode


def _check_rate_limit() -> bool:
    """Returns True if rate limited."""
    now = time.time()
    with _rate_lock:
        # Prune old timestamps
        _request_timestamps[:] = [t for t in _request_timestamps if now - t < RATE_WINDOW]
        if len(_request_timestamps) >= RATE_LIMIT:
            return True
        _request_timestamps.append(now)
        return False


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --- Middleware-like checks ---

def guard():
    """Check down mode and rate limit. Returns error response or None."""
    if _is_down():
        return jsonify({"error": "Service Unavailable", "message": "Salesforce API is currently down for maintenance"}), 503
    if _check_rate_limit():
        return jsonify({"error": "Too Many Requests", "message": "Rate limit exceeded. Max 5 requests per 10 seconds."}), 429
    return None


# --- Contacts ---

@app.route("/api/contacts", methods=["GET"])
def list_contacts():
    err = guard()
    if err:
        return err

    time.sleep(READ_DELAY)

    db = get_db()
    company = request.args.get("company")
    if company:
        rows = db.execute("SELECT * FROM contacts WHERE company = ? ORDER BY last_name", (company,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM contacts ORDER BY last_name").fetchall()
    db.close()

    contacts = [dict(r) for r in rows]
    return jsonify({"contacts": contacts, "count": len(contacts)})


@app.route("/api/contacts", methods=["POST"])
def create_contact():
    err = guard()
    if err:
        return err

    time.sleep(WRITE_DELAY)

    data = request.json
    required = ["first_name", "last_name", "email", "company", "title"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    from datetime import datetime
    db = get_db()
    cursor = db.execute(
        "INSERT INTO contacts (first_name, last_name, email, company, title, phone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["first_name"], data["last_name"], data["email"], data["company"],
         data["title"], data.get("phone", ""), datetime.now().isoformat()),
    )
    db.commit()
    contact_id = cursor.lastrowid
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    db.close()

    return jsonify({"contact": dict(row), "message": "Contact created successfully"}), 201


# --- Deals ---

@app.route("/api/deals", methods=["GET"])
def list_deals():
    err = guard()
    if err:
        return err

    time.sleep(READ_DELAY)

    db = get_db()
    min_amount = request.args.get("min_amount", type=float)
    company = request.args.get("company")

    query = "SELECT * FROM deals"
    params = []
    conditions = []

    if min_amount is not None:
        conditions.append("amount >= ?")
        params.append(min_amount)
    if company:
        conditions.append("company = ?")
        params.append(company)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY amount DESC"

    rows = db.execute(query, params).fetchall()
    db.close()

    deals = [dict(r) for r in rows]
    return jsonify({"deals": deals, "count": len(deals)})


@app.route("/api/deals", methods=["POST"])
def create_deal():
    err = guard()
    if err:
        return err

    time.sleep(WRITE_DELAY)

    data = request.json
    required = ["name", "company", "amount", "stage", "close_date"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    from datetime import datetime
    db = get_db()
    cursor = db.execute(
        "INSERT INTO deals (name, company, amount, stage, close_date, contact_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["name"], data["company"], data["amount"], data["stage"],
         data["close_date"], data.get("contact_id"), datetime.now().isoformat()),
    )
    db.commit()
    deal_id = cursor.lastrowid
    row = db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    db.close()

    return jsonify({"deal": dict(row), "message": "Deal created successfully"}), 201


# --- Admin controls (for demo runner) ---

@app.route("/admin/down", methods=["POST"])
def toggle_down():
    """Toggle down mode. Body: {"down": true/false}"""
    global _down_mode
    data = request.json or {}
    with _down_lock:
        _down_mode = data.get("down", not _down_mode)
        state = _down_mode
    return jsonify({"down_mode": state})


@app.route("/admin/reset-rate-limit", methods=["POST"])
def reset_rate_limit():
    """Reset rate limit counters."""
    with _rate_lock:
        _request_timestamps.clear()
    return jsonify({"message": "Rate limit reset"})


@app.route("/admin/status", methods=["GET"])
def status():
    with _down_lock:
        down = _down_mode
    with _rate_lock:
        now = time.time()
        recent = len([t for t in _request_timestamps if now - t < RATE_WINDOW])
    return jsonify({"down_mode": down, "recent_requests": recent, "rate_limit": RATE_LIMIT})


if __name__ == "__main__":
    # Seed the database if it doesn't exist
    if not os.path.exists(DB_PATH):
        print("Seeding CRM database...")
        seed()

    print(f"\nMock Salesforce CRM API")
    print(f"  Listening on: http://localhost:5555")
    print(f"  Read delay:   {READ_DELAY}s")
    print(f"  Write delay:  {WRITE_DELAY}s")
    print(f"  Rate limit:   {RATE_LIMIT} req / {RATE_WINDOW}s")
    print(f"  Database:     {DB_PATH}\n")

    app.run(host="127.0.0.1", port=5555, debug=False)
