import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "jovx_subscribers.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                stripe_session_id TEXT,
                status TEXT DEFAULT 'active'
            )
        """)
        conn.commit()

def add_subscriber(email: str, days: int = 90, stripe_session_id: str = None):
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Invalid email address"
    
    expires_at = datetime.utcnow() + timedelta(days=days)
    expires_at_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
    
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM subscribers WHERE email = ?", (email,)).fetchone()
        if existing:
            try:
                current_exp = datetime.strptime(existing["expires_at"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                current_exp = datetime.utcnow()
            new_exp = max(datetime.utcnow(), current_exp) + timedelta(days=days)
            conn.execute("UPDATE subscribers SET expires_at = ?, status = 'active' WHERE email = ?", 
                         (new_exp.strftime("%Y-%m-%d %H:%M:%S"), email))
            conn.commit()
            return True, f"Subscription renewed for {days} more days!"
        else:
            conn.execute("""
                INSERT INTO subscribers (email, expires_at, stripe_session_id, status)
                VALUES (?, ?, ?, 'active')
            """, (email, expires_at_str, stripe_session_id))
            conn.commit()
            return True, f"Subscription activated for {days} days!"

def verify_subscriber(email: str):
    email = email.strip().lower()
    if not email:
        return False, 0, "Email not provided"
    
    with get_db() as conn:
        row = conn.execute("SELECT * FROM subscribers WHERE email = ?", (email,)).fetchone()
        if not row:
            return False, 0, "Email not found in PRO subscribers database"
        
        try:
            expires_at = datetime.strptime(row["expires_at"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            expires_at = datetime.utcnow()

        now = datetime.utcnow()
        
        if now > expires_at:
            return False, 0, f"Your 3-month PRO subscription expired on {expires_at.strftime('%m/%d/%Y')}. Renew now!"
        
        days_left = max(1, (expires_at - now).days)
        return True, days_left, expires_at.strftime("%b %d, %Y")

def list_subscribers():
    with get_db() as conn:
        rows = conn.execute("SELECT id, email, created_at, expires_at, status FROM subscribers ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

VIP_SEEDS = [
    ("hsantoseireli@gmail.com", 90),
]

def auto_seed_vips():
    for email, days in VIP_SEEDS:
        add_subscriber(email, days=days, stripe_session_id="VIP_FOUNDER_PASS")

init_db()
auto_seed_vips()
