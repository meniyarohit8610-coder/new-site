# Private Portal - Live Couple Team

A private, end-to-end encrypted real-time communication portal for couples with **P2P Audio/Video Calls**, **Live Couple Team Hub**, **Python Backend with SQLite Database**, and **Protected Master Security PIN**.

---

## 🌟 Key Updates & Features

### 1. 💑 Live Couple Team Feature
- **Dual-Avatar Couple Badge**: Displays both partners with an animated pulsating neon heart connection in the header.
- **Live Mutual Status**: Real-time status indicator showing when both partners are connected (`Couple Connected 💕` / `1/2 Active`).
- **Live Couple Team Hub (Modal)**:
  - **Days in Love Counter**: Real-time counter of days together based on anniversary date.
  - **Mutual Live Mood Sync**: Select your current vibe (`🥰 In Love`, `💖 Missing You`, `☕ Working`, `😴 Sleepy`, `🥳 Excited`) which synchronizes live between both screens.
  - **Shared Live Love Scratchpad**: A shared romantic memo pad stored in SQLite and synchronized live.
  - **Real-Time Love Pings**: Quick-action heart button (`Love Ping 💕`) that fires a burst of floating hearts across both partners' screens!

### 2. 🔐 Completely Hidden Master PIN (Only You Know It)
- **Zero UI Leaks**: All plain-text hints, placeholders, and labels (`(0000)`) have been eliminated from the UI.
- **Zero Frontend Code Exposure**: The master PIN is **never** hardcoded in client-side HTML or JavaScript.
- **Server-Side Verification**: Authentication and credential resets verify the master PIN strictly on the Python backend against `config.json` / SQLite.
- **Configurable**: Only you, as the server owner, have access to `config.json` where your `master_pin` is stored. You can change it anytime in `config.json`.

### 3. 🐍 Python Backend with SQLite Database (`server.py`)
- **Zero Dependencies**: Uses Python's standard library (`http.server`, `sqlite3`, `hashlib`, etc.). No `pip install` required!
- **Persistent SQLite Storage (`portal.db`)**:
  - `users`: User profiles, passwords, display names, avatars, and moods.
  - `messages`: All chat messages, media metadata, timestamps, and seen receipts.
  - `call_logs`: Full audio & video call logs with durations.
  - `couple_team`: Couple names, anniversary date, love memo, love ping count.
- **RESTful Endpoints**:
  - `POST /api/login` & `POST /api/verify-master-pin`
  - `POST /api/reset-credentials` (Protected by Master PIN)
  - `GET /api/messages` & `POST /api/messages`
  - `GET /api/couple-team` & `POST /api/couple-team`
  - `GET /api/call-logs` & `POST /api/call-logs`

### 4. 🎨 Luxury Romantic CSS Redesign (`style.css`)
- **Deep Midnight & Rose-Amethyst Glassmorphism**: High-end modern dark theme with smooth blurred surfaces and radiant romantic glows.
- **Polished Micro-Interactions**: Animated heart loaders, hover effects, floating call dock, floating love hearts.
- **Fully Responsive**: Adapts seamlessly from mobile screens (`100dvh` viewport handling) to tablets and desktops.

---

## 🚀 How to Run the Server

1. **Double-click `start_server.bat`** (or open a terminal in this folder and run `python server.py`).
2. Open your web browser to:
   ```
   http://localhost:8080
   ```
   *(Or access it from your phone on the same Wi-Fi using your computer's local IP, e.g., `http://192.168.x.x:8080`)*

3. **Default Credentials**:
   - **Admin Account**: Username `admin` | Password `adminpassword123`
   - **Partner Account**: Username `user` | Password `userpassword123`
   - **Secret Master PIN**: Configured inside `config.json` (default `8610`).
