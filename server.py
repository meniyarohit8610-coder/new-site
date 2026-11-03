#!/usr/bin/env python3
"""
=============================================================================
Private Portal - Backend Server with SQLite Database
Features:
 - Secure SQLite storage for Couple Team, Messages, Call Logs, Profiles
 - Protected Master PIN validation (Kept strictly server-side)
 - Live Couple Team synchronization APIs
 - Zero external dependencies (runs out of the box with standard Python 3)
=============================================================================
"""

import http.server
import socketserver
import sqlite3
import json
import hashlib
import os
import sys
import mimetypes
from urllib.parse import urlparse, parse_qs
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "portal.db")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Default Server Configuration
DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8080,
    "master_pin": "8610",
    "couple_name": "admin & user",
    "partner1_name": "admin",
    "partner2_name": "user"
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {**DEFAULT_CONFIG, **cfg}
        except Exception as e:
            print(f"[Config] Error loading config.json: {e}")
    return DEFAULT_CONFIG

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[Config] Error saving config.json: {e}")

# ==================== DATABASE INITIALIZATION ====================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    cfg = load_config()
    with get_db() as conn:
        cursor = conn.cursor()

        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                display_name TEXT,
                avatar TEXT,
                mood TEXT DEFAULT '🥰 In Love',
                target_peer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Messages Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                sender TEXT NOT NULL,
                receiver TEXT NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                time TEXT,
                status TEXT DEFAULT 'sent',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Call History Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                peer TEXT NOT NULL,
                type TEXT NOT NULL,
                duration TEXT,
                date TEXT,
                time TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Couple Team Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS couple_team (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Insert Default Users if not present
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO users (username, password, role, display_name, avatar, mood, target_peer)
                VALUES 
                ('admin', 'adminpassword123', 'Admin', 'admin', '', '🥰 In Love', 'user'),
                ('user', 'userpassword123', 'User', 'user', '', '💖 Thinking of You', 'admin')
            """)
            print("[Database] Seeded initial couple users (admin / user).")

        # Insert Default Couple Team Data
        default_team = {
            "couple_name": cfg.get("couple_name", "admin & user"),
            "anniversary_date": "2024-01-01",
            "shared_note": "Welcome to our private space ❤️ Forever and always.",
            "love_ping_count": "0",
            "last_love_sender": ""
        }
        for k, v in default_team.items():
            cursor.execute("INSERT OR IGNORE INTO couple_team (key, value) VALUES (?, ?)", (k, v))

        conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    print("[Database] SQLite database initialized successfully at:", DB_FILE)

# ==================== HTTP REQUEST HANDLER ====================

class PortalRequestHandler(http.server.SimpleHTTPRequestHandler):

    def log_message(self, format, *args):
        # Format clean server logs
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} - {args[1]} {args[2]}")

    def end_headers(self):
        # Add CORS and Security headers
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def parse_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                raw_data = self.rfile.read(content_length).decode("utf-8")
                return json.loads(raw_data)
        except Exception as e:
            print(f"[Error parsing JSON body]: {e}")
        return {}

    # ----------------- GET ROUTES -----------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/api/"):
            self.handle_api_get(path, query)
        else:
            self.handle_static_file(path)

    def handle_api_get(self, path, query):
        if path == "/api/status":
            self.send_json({"status": "online", "system": "Private Portal SQLite Backend", "time": datetime.now().isoformat()})

        elif path == "/api/couple-team":
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM couple_team")
                rows = cursor.fetchall()
                team_data = {row["key"]: row["value"] for row in rows}

                # Also grab live mood of both users
                cursor.execute("SELECT username, display_name, mood, avatar FROM users")
                users_info = {u["username"]: dict(u) for u in cursor.fetchall()}
                team_data["users"] = users_info

                self.send_json({"success": True, "couple_team": team_data})

        elif path == "/api/messages":
            user = query.get("user", [""])[0].lower()
            peer = query.get("peer", [""])[0].lower()
            with get_db() as conn:
                cursor = conn.cursor()
                if user and peer:
                    cursor.execute("""
                        SELECT id, sender, receiver, type, content, time, status, created_at
                        FROM messages
                        WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
                        ORDER BY rowid ASC
                    """, (user, peer, peer, user))
                elif user:
                    cursor.execute("""
                        SELECT id, sender, receiver, type, content, time, status, created_at
                        FROM messages
                        WHERE sender = ? OR receiver = ?
                        ORDER BY rowid ASC
                    """, (user, user))
                else:
                    cursor.execute("SELECT * FROM messages ORDER BY rowid ASC")

                messages = [dict(row) for row in cursor.fetchall()]
                self.send_json({"success": True, "messages": messages})

        elif path == "/api/call-logs":
            user = query.get("user", [""])[0].lower()
            with get_db() as conn:
                cursor = conn.cursor()
                if user:
                    cursor.execute("""
                        SELECT id, user, peer, type, duration, date, time
                        FROM call_logs
                        WHERE user = ? OR peer = ?
                        ORDER BY id DESC
                    """, (user, user))
                else:
                    cursor.execute("SELECT * FROM call_logs ORDER BY id DESC")
                logs = [dict(row) for row in cursor.fetchall()]
                self.send_json({"success": True, "logs": logs})

        elif path == "/api/users":
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT username, role, display_name, avatar, mood, target_peer FROM users")
                users = [dict(row) for row in cursor.fetchall()]
                self.send_json({"success": True, "users": users})

        else:
            self.send_json({"error": "Endpoint not found"}, status_code=404)

    # ----------------- POST ROUTES -----------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.parse_json_body()

        cfg = load_config()
        master_pin = cfg.get("master_pin", "8610")

        # 1. Login Authentication
        if path == "/api/login":
            username = body.get("username", "").strip().lower()
            password = body.get("password", "").strip()

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
                user = cursor.fetchone()

                if not user:
                    self.send_json({"success": False, "error": "Invalid username or password."}, status_code=401)
                    return

                # Check standard password OR Master PIN
                is_valid = (user["password"] == password) or (password == master_pin)
                if is_valid:
                    user_dict = {
                        "username": user["username"],
                        "password": user["password"],
                        "role": user["role"],
                        "displayName": user["display_name"] or user["username"],
                        "avatar": user["avatar"] or "",
                        "mood": user["mood"] or "🥰 In Love",
                        "targetPeer": user["target_peer"]
                    }
                    self.send_json({"success": True, "user": user_dict})
                else:
                    self.send_json({"success": False, "error": "Invalid credentials."}, status_code=401)

        # 2. Master PIN Verification (Keeps PIN hidden, never returned to client)
        elif path == "/api/verify-master-pin":
            entered_pin = body.get("pin", "").strip()
            if entered_pin and entered_pin == master_pin:
                self.send_json({"success": True, "valid": True})
            else:
                self.send_json({"success": False, "valid": False, "error": "Incorrect Master Security PIN. Access Denied."}, status_code=403)

        # 3. Reset Password / Credentials (Requires Master PIN)
        elif path == "/api/reset-credentials":
            entered_pin = body.get("master_pin", "").strip()
            if entered_pin != master_pin:
                self.send_json({"success": False, "error": "Invalid Master Security PIN! Access Denied."}, status_code=403)
                return

            target_user = body.get("target_user", "").strip().lower()
            new_username = body.get("new_username", "").strip().lower()
            new_password = body.get("new_password", "").strip()

            if not new_username or not new_password:
                self.send_json({"success": False, "error": "Username and password cannot be empty."}, status_code=400)
                return

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE username = ?", (target_user,))
                row = cursor.fetchone()
                if not row:
                    self.send_json({"success": False, "error": "Target user not found."}, status_code=404)
                    return

                if new_username != target_user:
                    # Update target user and fix partner references
                    cursor.execute("UPDATE users SET username = ?, password = ? WHERE username = ?", (new_username, new_password, target_user))
                    cursor.execute("UPDATE users SET target_peer = ? WHERE target_peer = ?", (new_username, target_user))
                else:
                    cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_password, target_user))

                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True, "message": "Credentials updated successfully via Master Key."})

        # 4. Update Profile
        elif path == "/api/update-profile":
            username = body.get("username", "").strip().lower()
            display_name = body.get("display_name", "")
            avatar = body.get("avatar", "")
            mood = body.get("mood", "")

            with get_db() as conn:
                cursor = conn.cursor()
                updates = []
                params = []
                if display_name:
                    updates.append("display_name = ?")
                    params.append(display_name)
                if avatar:
                    updates.append("avatar = ?")
                    params.append(avatar)
                if mood:
                    updates.append("mood = ?")
                    params.append(mood)

                if updates:
                    params.append(username)
                    query = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
                    cursor.execute(query, params)
                    conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True})

        # 5. Save New Message
        elif path == "/api/messages":
            msg_id = body.get("id")
            sender = body.get("sender", "").strip().lower()
            receiver = body.get("receiver", "").strip().lower()
            mtype = body.get("type", "text")
            content = body.get("content", "")
            time_str = body.get("time", "")
            status = body.get("status", "sent")

            if not msg_id or not sender:
                self.send_json({"success": False, "error": "Missing message id or sender."}, status_code=400)
                return

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO messages (id, sender, receiver, type, content, time, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (msg_id, sender, receiver, mtype, content, time_str, status))
                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True, "id": msg_id})

        # 6. Mark Messages as Seen
        elif path == "/api/messages/seen":
            msg_id = body.get("id")
            receiver = body.get("receiver", "").strip().lower()

            with get_db() as conn:
                cursor = conn.cursor()
                if msg_id:
                    cursor.execute("UPDATE messages SET status = 'seen' WHERE id = ?", (msg_id,))
                elif receiver:
                    cursor.execute("UPDATE messages SET status = 'seen' WHERE receiver = ?", (receiver,))
                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True})

        # 7. Edit Message
        elif path == "/api/messages/edit":
            msg_id = body.get("id")
            new_content = body.get("content")

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE messages SET content = ? WHERE id = ?", (new_content, msg_id))
                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True})

        # 8. Delete Message
        elif path == "/api/messages/delete":
            msg_id = body.get("id")
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True})

        # 9. Clear Chat History
        elif path == "/api/messages/clear":
            user = body.get("user", "").strip().lower()
            peer = body.get("peer", "").strip().lower()

            with get_db() as conn:
                cursor = conn.cursor()
                if user and peer:
                    cursor.execute("""
                        DELETE FROM messages 
                        WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)
                    """, (user, peer, peer, user))
                elif user:
                    cursor.execute("DELETE FROM messages WHERE sender = ? OR receiver = ?", (user, user))
                else:
                    cursor.execute("DELETE FROM messages")
                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True})

        # 10. Save Call Log
        elif path == "/api/call-logs":
            user = body.get("user", "")
            peer = body.get("peer", "")
            ctype = body.get("type", "voice")
            duration = body.get("duration", "0:00")
            date_str = body.get("date", datetime.now().strftime("%Y-%m-%d"))
            time_str = body.get("time", datetime.now().strftime("%I:%M %p"))

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO call_logs (user, peer, type, duration, date, time)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user, peer, ctype, duration, date_str, time_str))
                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True})

        # 11. Update Couple Team Info / Send Love Ping
        elif path == "/api/couple-team":
            action = body.get("action", "update")
            with get_db() as conn:
                cursor = conn.cursor()

                if action == "love-ping":
                    sender = body.get("sender", "Partner")
                    cursor.execute("SELECT value FROM couple_team WHERE key = 'love_ping_count'")
                    row = cursor.fetchone()
                    count = int(row["value"]) + 1 if row else 1
                    cursor.execute("INSERT OR REPLACE INTO couple_team (key, value) VALUES ('love_ping_count', ?)", (str(count),))
                    cursor.execute("INSERT OR REPLACE INTO couple_team (key, value) VALUES ('last_love_sender', ?)", (sender,))
                    conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
                    self.send_json({"success": True, "count": count, "sender": sender})
                    return

                # Normal settings update
                allowed_keys = ["couple_name", "anniversary_date", "shared_note"]
                for k in allowed_keys:
                    if k in body:
                        cursor.execute("INSERT OR REPLACE INTO couple_team (key, value) VALUES (?, ?)", (k, str(body[k])))
                conn.commit()

        # ------------------------------------------------------------
        # Friends System Table
        # Stores bidirectional friendship relations between users.
        # Each row represents a directed link; a mutual friendship is
        # stored as two rows (A -> B and B -> A) with a UNIQUE constraint
        # on (user_id, friend_id) to avoid duplicates.
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friends (
                user_id INTEGER NOT NULL,
                friend_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(friend_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # ------------------------------------------------------------
        # Friend Requests Table
        # Stores pending friend request notifications.
        # status: 'pending', 'accepted', 'rejected' (for record keeping).
        # ------------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                to_user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_user_id, to_user_id),
                FOREIGN KEY(from_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(to_user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

            self.send_json({"success": True})

        else:
            self.send_json({"error": "Unknown POST route"}, status_code=404)

    # ----------------- STATIC FILES -----------------
    def handle_static_file(self, path):
        if path == "/" or path == "":
            path = "/index.html"

        # Prevent directory traversal
        clean_path = os.path.normpath(path.lstrip("/"))
        file_path = os.path.join(BASE_DIR, clean_path)

        if not os.path.isfile(file_path):
            self.send_error(404, "File Not Found")
            return

        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Server Error reading file: {e}")

# ==================== MAIN SERVER ENTRY POINT ====================

def run_server():
    cfg = load_config()
    host = cfg.get("host", "0.0.0.0")
    port = int(cfg.get("port", 8080))

    init_db()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), PortalRequestHandler) as httpd:
        print("\n" + "="*60)
        print("  💖 PRIVATE PORTAL - COUPLE TEAM SERVER RUNNING 💖")
        print("="*60)
        print(f"  • Local Web URL:    http://localhost:{port}")
        print(f"  • Network Web URL:  http://127.0.0.1:{port}")
        print(f"  • Database:         {DB_FILE} (SQLite)")
        print(f"  • Config File:      {CONFIG_FILE}")
        print("  • Master Security PIN is safely protected on this server.")
        print("="*60 + "\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Server] Shutting down gracefully...")
            httpd.server_close()

if __name__ == "__main__":
    run_server()
