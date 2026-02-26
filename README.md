# 🧠 Truth or Twist — GenLayer Multiplayer Trivia

A fully on-chain multiplayer trivia game built on [GenLayer](https://genlayer.com), where players decide if statements are **TRUE** or a **TWIST** (misleading/false).

**Live Demo:** [truth-or-twist.netlify.app](https://truth-or-twist.netlify.app)  
**Backend:** [truth-or-twist-production.up.railway.app](https://truth-or-twist-production.up.railway.app/health)  
**Contract (v3):** [`0x68850c902d8193fa29419e3a3a043054d416CA08`](https://studio.genlayer.com) on GenLayer Studionet  
**GitHub:** [github.com/Investorquab/truth-or-twist](https://github.com/Investorquab/truth-or-twist)

---

## What Makes This a GenLayer App

This game uses GenLayer's unique capabilities that no other blockchain can provide:

| Feature | How GenLayer Powers It |
|---|---|
| **AI Question Generation** | `gl.exec_prompt()` generates fresh trivia questions weekly — the contract calls an LLM directly |
| **On-Chain Player Profiles** | Every `register_player()` and `update_player_stats()` call writes to chain, keeping wallets active |
| **Optimistic Democracy** | All game transactions go through GenLayer's consensus — `create_room`, `join_room`, `start_game`, `submit_answer`, `score_round` |
| **Leader Only Mode** | Fast game transactions use Leader Only execution for near-instant confirmation |
| **Persistent Leaderboard** | Player XP, wins, streaks stored in contract `TreeMap` state, readable by anyone |

---

## Gameplay

1. Enter your nickname + wallet address
2. Create a room or join with a code
3. Host picks difficulty: **Easy / Medium / Hard / Mixed**
4. 5 rounds — each round shows a statement
5. Pick **TRUE ✅** or **TWIST ❌** as fast as possible
6. **Speed bonus XP** — faster correct answers earn more
7. **Streak bonus** — consecutive correct answers build a fire streak 🔥
8. Game over → final ranking → on-chain profiles updated

---

## Tech Stack

```
Frontend      → Vanilla HTML/CSS/JS (single file, no framework)
Backend       → Node.js + Express + Socket.IO
Blockchain    → GenLayer Studionet
Smart Contract → Python (GenLayer Contract SDK)
Real-time     → WebSockets via Socket.IO
```

---

## Smart Contract — `truth_or_twist_v3.py`

**Deployed at:** `0x68850c902d8193fa29419e3a3a043054d416CA08`

### Key Methods

| Method | Type | Description |
|---|---|---|
| `generate_ai_questions()` | write | AI generates 10 trivia questions via `gl.exec_prompt()` |
| `generate_statements()` | write | Fallback: loads hardcoded questions |
| `register_player(address, nickname)` | write | Creates on-chain profile, proves wallet activity |
| `update_player_stats(address, xp, won, score)` | write | Updates profile after each game |
| `create_room(player_address)` | write | Creates a game room on-chain |
| `join_room(room_id, player_address)` | write | Joins existing room |
| `start_game(room_id, host_address)` | write | Starts game, returns first statement |
| `submit_answer(room_id, player, answer, ...)` | write | Records player answer on-chain |
| `score_round(room_id)` | write | Marks round complete, advances state |
| `new_week()` | write | Advances week counter for fresh AI questions |
| `get_player_profile(address)` | view | Returns full on-chain player profile |
| `get_leaderboard()` | view | Top 20 players by XP |
| `get_weekly_questions()` | view | Current week's AI-generated questions |

### Contract Evolution

| Version | Description |
|---|---|
| `v1` | Basic room + answer mechanics |
| `v2` | Hardcoded statements, on-chain scoring |
| `v3` | AI question generation, player profiles, persistent leaderboard |

---

## Project Structure

```
truth-or-twist/
├── index.html                  # Complete frontend (single file)
├── truth_or_twist_v3.py        # Active GenLayer smart contract
├── truth_or_twist_v2.py        # Previous version
├── truth_or_twist.py           # Original version
├── README.md                   # This file
└── backend/
    ├── server.js               # Node.js backend (Express + Socket.IO)
    ├── package.json
    ├── .env.example            # Environment variables template
    └── leaderboard.json        # Disk-persisted leaderboard (auto-generated)
```

---

## Running Locally

### Prerequisites
- Node.js 18+
- A GenLayer Studio account at [studio.genlayer.com](https://studio.genlayer.com)
- Keep Studio open in a browser tab while playing (required for transaction processing)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/truth-or-twist
cd truth-or-twist

# 2. Install backend dependencies
cd backend
npm install

# 3. Create environment file
cp .env.example .env
# Edit .env with your operator private key

# 4. Start the backend
npm run dev

# 5. Open index.html in your browser
# Or serve it: npx serve . -p 8080
```

### Environment Variables

```env
OPERATOR_PRIVATE_KEY=0x...    # Your GenLayer operator wallet private key
CONTRACT_ADDRESS=0x68850c902d8193fa29419e3a3a043054d416CA08
PORT=3001
```

---

## Deploying

### Backend → Railway
1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the `backend/` folder
4. Add environment variables in Railway dashboard
5. Railway gives you a URL like `https://truth-or-twist-backend.up.railway.app`

### Frontend → Vercel / Netlify
1. Update `const BACKEND` in `index.html` to your Railway URL
2. Drag and drop `index.html` to [vercel.com](https://vercel.com) or [netlify.com](https://netlify.com)
3. Done — share the link!

---

## Features

- 🎮 **Real-time multiplayer** — up to 8 players per room
- 🤖 **AI-generated questions** — GenLayer contract calls LLM weekly
- ⚡ **Speed bonus XP** — faster answers = more XP
- 🔥 **Streak system** — consecutive correct answers tracked on-chain
- 👁️ **Spectator mode** — join mid-game to watch
- 🏆 **On-chain leaderboard** — persistent across sessions
- 👤 **Player profiles** — XP, wins, streaks stored on GenLayer
- 🎵 **Sound effects** — Web Audio API, zero dependencies
- 🎊 **Confetti** — fires on wins and streaks
- 📱 **Mobile responsive** — works on any device
- 🌙 **Dark theme** — easy on the eyes

---

## Built By

Built for the **GenLayer ecosystem** — showcasing what's possible when smart contracts have native AI capabilities.

> GenLayer's `gl.exec_prompt()` is what makes the AI question generation possible — no other blockchain lets a smart contract call an LLM directly as part of consensus.
