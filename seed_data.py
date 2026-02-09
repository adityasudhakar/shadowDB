#!/usr/bin/env python3
"""Seeds the mock CRM database with realistic contacts and deals."""

import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "crm_data.db")

COMPANIES = [
    "Acme Corp", "Globex Industries", "Initech", "Umbrella Corp",
    "Stark Industries", "Wayne Enterprises", "Cyberdyne Systems",
    "Soylent Corp", "Massive Dynamic", "Hooli", "Pied Piper",
    "Dunder Mifflin", "Sterling Cooper", "Wonka Industries",
    "Aperture Science",
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Daniel",
    "Lisa", "Matthew", "Nancy", "Anthony", "Betty", "Mark", "Sandra",
    "Steven", "Margaret", "Paul", "Ashley", "Andrew", "Dorothy", "Joshua",
    "Kimberly", "Kenneth", "Emily", "Kevin", "Donna", "Brian", "Michelle",
    "George", "Carol", "Timothy", "Amanda", "Ronald", "Melissa",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
]

TITLES = [
    "CEO", "CTO", "CFO", "VP of Engineering", "VP of Sales",
    "VP of Marketing", "Director of Operations", "Director of Engineering",
    "Head of Product", "Head of Sales", "Senior Account Executive",
    "Account Manager", "Sales Engineer", "Product Manager",
    "Engineering Manager",
]

DEAL_STAGES = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]

DEAL_NAMES_TEMPLATES = [
    "{company} - Enterprise License",
    "{company} - Platform Migration",
    "{company} - Annual Renewal",
    "{company} - Expansion Deal",
    "{company} - Pilot Program",
    "{company} - Professional Services",
    "{company} - Data Integration",
]


def create_tables(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT NOT NULL,
            title TEXT NOT NULL,
            phone TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT NOT NULL,
            amount REAL NOT NULL,
            stage TEXT NOT NULL,
            close_date TEXT NOT NULL,
            contact_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (contact_id) REFERENCES contacts(id)
        )
    """)
    conn.commit()


def seed_contacts(conn: sqlite3.Connection, count: int = 47) -> list[int]:
    contact_ids = []
    used_emails = set()
    now = datetime.now()

    for _ in range(count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        company = random.choice(COMPANIES)
        title = random.choice(TITLES)
        domain = company.lower().replace(" ", "").replace(".", "") + ".com"
        base_email = f"{first.lower()}.{last.lower()}@{domain}"

        # Ensure unique emails
        email = base_email
        suffix = 1
        while email in used_emails:
            email = f"{first.lower()}.{last.lower()}{suffix}@{domain}"
            suffix += 1
        used_emails.add(email)

        phone = f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}"
        created = (now - timedelta(days=random.randint(1, 365))).isoformat()

        cursor = conn.execute(
            "INSERT INTO contacts (first_name, last_name, email, company, title, phone, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (first, last, email, company, title, phone, created),
        )
        contact_ids.append(cursor.lastrowid)

    conn.commit()
    return contact_ids


def seed_deals(conn: sqlite3.Connection, contact_ids: list[int], count: int = 23):
    now = datetime.now()

    for _ in range(count):
        company = random.choice(COMPANIES)
        template = random.choice(DEAL_NAMES_TEMPLATES)
        name = template.format(company=company)
        amount = round(random.choice([
            random.uniform(5000, 25000),
            random.uniform(25000, 75000),
            random.uniform(75000, 200000),
            random.uniform(200000, 500000),
        ]), 2)
        stage = random.choice(DEAL_STAGES)
        close_date = (now + timedelta(days=random.randint(-30, 180))).strftime("%Y-%m-%d")
        contact_id = random.choice(contact_ids)
        created = (now - timedelta(days=random.randint(1, 180))).isoformat()

        conn.execute(
            "INSERT INTO deals (name, company, amount, stage, close_date, contact_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, company, amount, stage, close_date, contact_id, created),
        )

    conn.commit()


def seed(db_path: str = DB_PATH):
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    create_tables(conn)

    random.seed(42)  # Reproducible data
    contact_ids = seed_contacts(conn, 47)
    seed_deals(conn, contact_ids, 23)

    # Verify counts
    contacts_count = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    deals_count = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    print(f"Seeded CRM database: {contacts_count} contacts, {deals_count} deals")
    print(f"Database: {db_path}")

    conn.close()


if __name__ == "__main__":
    seed()
