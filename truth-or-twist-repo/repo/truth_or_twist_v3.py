# v3.0.0
# { "Depends": "py-genlayer:test" }

from genlayer import *
import json


class TruthOrTwist(gl.Contract):

    # -- ROOM STATE ----------------------------------------
    room_host:              TreeMap[str, str]
    room_players:           TreeMap[str, str]
    room_status:            TreeMap[str, str]
    room_current_round:     TreeMap[str, str]
    room_statement_indices: TreeMap[str, str]
    room_final_ranking:     TreeMap[str, str]
    room_counter:           str

    # -- ANSWERS & SCORING ---------------------------------
    player_scores:          TreeMap[str, str]
    submission_answers:     TreeMap[str, str]
    submission_explanations:TreeMap[str, str]
    submission_times:       TreeMap[str, str]
    round_submitted:        TreeMap[str, str]

    # -- AI-GENERATED WEEKLY QUESTIONS ---------------------
    # Stored as week:index -> field
    weekly_stmt_text:       TreeMap[str, str]
    weekly_stmt_answer:     TreeMap[str, str]
    weekly_stmt_explanation:TreeMap[str, str]
    weekly_stmt_difficulty: TreeMap[str, str]
    weekly_stmt_count:      str
    current_week_str:       str
    current_week_topic:     str   # the topic AI used this week

    # -- PLAYER PROFILES -----------------------------------
    # profile_<field>[address] = value
    profile_nickname:       TreeMap[str, str]
    profile_join_nonce:     TreeMap[str, str]   # block nonce at registration = on-chain activity proof
    profile_last_nonce:     TreeMap[str, str]   # updated each game = keeps wallet active
    profile_total_xp:       TreeMap[str, str]
    profile_games_played:   TreeMap[str, str]
    profile_wins:           TreeMap[str, str]
    profile_best_score:     TreeMap[str, str]
    profile_streak:         TreeMap[str, str]   # current win streak
    profile_best_streak:    TreeMap[str, str]
    all_players:            str                 # comma-separated registered addresses

    def __init__(self) -> None:
        self.weekly_stmt_count  = "0"
        self.current_week_str   = "1"
        self.current_week_topic = ""
        self.all_players        = ""
        self.room_counter       = "0"

    # -- INTERNAL HELPERS ----------------------------------

    def _split(self, value: str) -> list:
        if not value:
            return []
        return [x for x in value.split(",") if x]

    def _get_statement(self, week: int, index: int) -> dict:
        key = f"{week}:{index}"
        return {
            "statement":   self.weekly_stmt_text.get(key, ""),
            "answer":      self.weekly_stmt_answer.get(key, "TRUE"),
            "explanation": self.weekly_stmt_explanation.get(key, ""),
            "difficulty":  self.weekly_stmt_difficulty.get(key, "medium"),
        }

    def _ensure_profile(self, address: str) -> None:
        """Create a blank profile if the player has never registered."""
        if self.profile_join_nonce.get(address, "") == "":
            nonce = "reg_" + self.room_counter  # unique registration marker
            self.profile_join_nonce[address] = nonce
            self.profile_total_xp[address]     = "0"
            self.profile_games_played[address]  = "0"
            self.profile_wins[address]          = "0"
            self.profile_best_score[address]    = "0"
            self.profile_streak[address]        = "0"
            self.profile_best_streak[address]   = "0"
            # Add to global player list
            known = self._split(self.all_players)
            if address not in known:
                self.all_players = (self.all_players + "," + address).lstrip(",")

    def _touch_player(self, address: str) -> None:
        """Record latest nonce for this player (proves on-chain activity)."""
        self.profile_last_nonce[address] = self.room_counter  # records on-chain activity

    # ======================================================
    # AI WEEKLY QUESTION GENERATION
    # ======================================================

    @gl.public.write
    def generate_ai_questions(self) -> str:
        """
        Use GenLayer's AI to generate 10 fresh trivia questions for this week.
        Call this with Leader Only mode - takes ~30-60s but runs reliably.
        Questions rotate weekly by topic.
        """
        week_num = int(self.current_week_str)

        topics = [
            "science and nature",
            "world history and ancient civilizations",
            "space and astronomy",
            "human biology and medicine",
            "technology and famous inventions",
            "geography and world records",
            "food, nutrition and cooking",
            "famous landmarks and architecture",
            "animals and the natural world",
            "mathematics and surprising numbers",
        ]
        topic = topics[(week_num - 1) % len(topics)]
        self.current_week_topic = topic

        prompt = f"""You are creating trivia questions for a game called "Truth or Twist".

TOPIC FOR THIS WEEK: {topic}

Generate exactly 10 trivia statements. Each statement is either TRUE (accurate fact) or TWIST (contains a common misconception or subtle falsehood that sounds plausible).

Rules:
- Mix of TRUE and TWIST - aim for roughly 5 each
- Include 3 easy, 4 medium, and 3 hard questions
- Easy = well-known facts or myths most people have heard of
- Medium = less obvious, requires real knowledge
- Hard = counterintuitive, niche, or surprising facts
- Each statement must be a single sentence, max 20 words
- Explanation must be 1-2 sentences clarifying WHY it is true or twisted
- Keep statements factual, family-friendly, interesting

Respond ONLY with a JSON array. No markdown, no preamble, no trailing text.
Format exactly:
[
  {{"statement": "...", "answer": "TRUE", "explanation": "...", "difficulty": "easy"}},
  {{"statement": "...", "answer": "TWIST", "explanation": "...", "difficulty": "medium"}},
  ...
]"""

        raw = gl.exec_prompt(prompt)
        raw = raw.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        questions = json.loads(raw)

        # Validate and store
        stored = 0
        for i, q in enumerate(questions[:10]):
            stmt  = str(q.get("statement", "")).strip()
            ans   = str(q.get("answer", "TRUE")).strip().upper()
            expl  = str(q.get("explanation", "")).strip()
            diff  = str(q.get("difficulty", "medium")).strip().lower()

            if not stmt or ans not in ("TRUE", "TWIST"):
                continue

            if diff not in ("easy", "medium", "hard"):
                diff = "medium"

            key = f"{week_num}:{i}"
            self.weekly_stmt_text[key]        = stmt
            self.weekly_stmt_answer[key]      = ans
            self.weekly_stmt_explanation[key] = expl
            self.weekly_stmt_difficulty[key]  = diff
            stored += 1

        self.weekly_stmt_count = str(stored)
        self.current_week_str  = str(week_num)

        return json.dumps({
            "week": week_num,
            "topic": topic,
            "questions_generated": stored,
        })

    @gl.public.write
    def generate_statements(self) -> str:
        """
        Fallback: generate hardcoded statements if AI is unavailable.
        Kept for compatibility with existing server startup code.
        """
        week_num = int(self.current_week_str)

        fallback = [
            {"statement": "The Great Wall of China is not visible from space with the naked eye.", "answer": "TRUE",  "explanation": "The wall is too narrow to see from orbit without optical aid.", "difficulty": "easy"},
            {"statement": "Honey never expires - archaeologists found 3000-year-old honey still edible.", "answer": "TRUE",  "explanation": "Honey's low moisture and acidic pH prevent bacterial growth indefinitely.", "difficulty": "easy"},
            {"statement": "A day on Venus is shorter than a year on Venus.", "answer": "TWIST", "explanation": "A Venus day (243 Earth days) is actually LONGER than its year (225 Earth days).", "difficulty": "easy"},
            {"statement": "Octopuses have three hearts and blue blood.", "answer": "TRUE",  "explanation": "Two hearts pump to gills, one to body. Copper-based blood is blue.", "difficulty": "easy"},
            {"statement": "The Eiffel Tower was built as a permanent Paris landmark.", "answer": "TWIST", "explanation": "It was a temporary exhibit for the 1889 World's Fair, slated for demolition.", "difficulty": "easy"},
            {"statement": "Bananas are technically berries, but strawberries are not.", "answer": "TRUE",  "explanation": "Botanically, bananas are berries; strawberries are accessory fruits.", "difficulty": "medium"},
            {"statement": "Mount Everest is the tallest mountain measured from its base.", "answer": "TWIST", "explanation": "Mauna Kea is taller base-to-peak; Everest wins only by sea-level height.", "difficulty": "medium"},
            {"statement": "The human brain uses about 20% of the body's total energy.", "answer": "TRUE",  "explanation": "The brain is 2% of body weight but burns ~20% of all calories.", "difficulty": "medium"},
            {"statement": "Lightning strikes the Earth about 100 times every second.", "answer": "TRUE",  "explanation": "Earth sees ~8 million strikes per day - roughly 100 per second.", "difficulty": "medium"},
            {"statement": "Cleopatra lived closer in time to the Moon landing than to the Great Pyramid.", "answer": "TRUE",  "explanation": "Pyramids ~2560 BC, Cleopatra ~30 BC, Moon landing 1969 AD.", "difficulty": "hard"},
        ]

        for i, q in enumerate(fallback):
            key = f"{week_num}:{i}"
            self.weekly_stmt_text[key]        = q["statement"]
            self.weekly_stmt_answer[key]      = q["answer"]
            self.weekly_stmt_explanation[key] = q["explanation"]
            self.weekly_stmt_difficulty[key]  = q["difficulty"]

        self.weekly_stmt_count  = str(len(fallback))
        self.current_week_topic = "mixed trivia"

        return f"Loaded {len(fallback)} fallback statements for week {week_num}"

    @gl.public.write
    def new_week(self) -> str:
        """
        Advance to next week. Call this before generate_ai_questions() each week.
        Clears nothing - old week data stays in storage for history.
        """
        week_num = int(self.current_week_str) + 1
        self.current_week_str = str(week_num)
        self.weekly_stmt_count = "0"
        return f"Advanced to week {week_num}"

    # ======================================================
    # PLAYER PROFILES & REGISTRATION
    # ======================================================

    @gl.public.write
    def register_player(self, address: str, nickname: str) -> str:
        """
        Register a wallet on-chain. Creates profile if new.
        Updates nickname if already registered.
        Each call writes to the chain -> keeps wallet active on GenLayer.
        """
        self._ensure_profile(address)
        self._touch_player(address)

        # Update nickname (trimmed, max 20 chars)
        nick = nickname.strip()[:20] if nickname else ""
        if nick:
            self.profile_nickname[address] = nick

        nonce = self.profile_join_nonce.get(address, "")
        return json.dumps({
            "address": address,
            "nickname": self.profile_nickname.get(address, ""),
            "join_nonce": nonce,
            "total_xp": int(self.profile_total_xp.get(address, "0")),
            "games_played": int(self.profile_games_played.get(address, "0")),
            "registered": True,
        })

    @gl.public.write
    def update_player_stats(
        self,
        address: str,
        xp_earned: int,
        won: bool,
        game_score: int,
    ) -> str:
        """
        Called by server after each game ends.
        Updates on-chain profile and leaderboard.
        Writing to chain = on-chain activity for this wallet.
        """
        self._ensure_profile(address)
        self._touch_player(address)

        old_xp     = int(self.profile_total_xp.get(address, "0"))
        old_games  = int(self.profile_games_played.get(address, "0"))
        old_wins   = int(self.profile_wins.get(address, "0"))
        old_best   = int(self.profile_best_score.get(address, "0"))
        old_streak = int(self.profile_streak.get(address, "0"))
        old_bstrk  = int(self.profile_best_streak.get(address, "0"))

        new_xp    = old_xp + xp_earned
        new_games = old_games + 1
        new_wins  = old_wins + (1 if won else 0)
        new_best  = max(old_best, game_score)

        if won:
            new_streak = old_streak + 1
        else:
            new_streak = 0
        new_bstrk = max(old_bstrk, new_streak)

        self.profile_total_xp[address]    = str(new_xp)
        self.profile_games_played[address] = str(new_games)
        self.profile_wins[address]         = str(new_wins)
        self.profile_best_score[address]   = str(new_best)
        self.profile_streak[address]       = str(new_streak)
        self.profile_best_streak[address]  = str(new_bstrk)

        return json.dumps({
            "address": address,
            "total_xp": new_xp,
            "games_played": new_games,
            "wins": new_wins,
            "win_streak": new_streak,
        })

    # ======================================================
    # ROOM LIFECYCLE (unchanged from v2 logic)
    # ======================================================

    @gl.public.write
    def create_room(self, player_address: str) -> str:
        self._ensure_profile(player_address)
        self._touch_player(player_address)

        room_num = int(self.room_counter) + 1
        self.room_counter = str(room_num)
        room_id = f"ROOM-{room_num:04d}"

        total = int(self.weekly_stmt_count) if self.weekly_stmt_count != "0" else 10
        start = room_num % max(1, total - 4)
        indices = [str((start + i) % total) for i in range(5)]

        self.room_host[room_id]              = player_address
        self.room_players[room_id]           = player_address
        self.room_status[room_id]            = "waiting"
        self.room_current_round[room_id]     = "0"
        self.room_statement_indices[room_id] = ",".join(indices)
        self.room_final_ranking[room_id]     = "[]"
        self.player_scores[f"{room_id}:{player_address}"] = "0"

        return room_id

    @gl.public.write
    def join_room(self, room_id: str, player_address: str) -> str:
        self._ensure_profile(player_address)
        self._touch_player(player_address)

        status = self.room_status.get(room_id, "")
        if not status:
            raise Exception(f"Room {room_id} does not exist!")
        if status != "waiting":
            raise Exception("Game already started!")

        players = self._split(self.room_players.get(room_id, ""))
        if len(players) >= 8:
            raise Exception("Room is full (max 8 players)!")
        if player_address in players:
            raise Exception("Already in this room!")

        players.append(player_address)
        self.room_players[room_id] = ",".join(players)
        self.player_scores[f"{room_id}:{player_address}"] = "0"
        return f"Joined {room_id}!"

    @gl.public.write
    def start_game(self, room_id: str, host_address: str) -> str:
        status = self.room_status.get(room_id, "")
        if not status:
            raise Exception(f"Room {room_id} not found!")
        if self.room_host.get(room_id, "") != host_address:
            raise Exception("Only the host can start!")
        players = self._split(self.room_players.get(room_id, ""))
        if len(players) < 2:
            raise Exception("Need at least 2 players!")
        if status != "waiting":
            raise Exception("Game already started!")

        self.room_status[room_id]         = "active"
        self.room_current_round[room_id]  = "1"

        week    = int(self.current_week_str)
        indices = self._split(self.room_statement_indices.get(room_id, ""))
        stmt    = self._get_statement(week, int(indices[0]))
        return stmt["statement"]

    @gl.public.write
    def submit_answer(
        self,
        room_id: str,
        player_address: str,
        answer: str,
        explanation: str,
        submission_time: int,
    ) -> str:
        if self.room_status.get(room_id, "") != "active":
            raise Exception("Game is not active!")

        players = self._split(self.room_players.get(room_id, ""))
        if player_address not in players:
            raise Exception("You are not in this room!")
        if answer not in ("TRUE", "TWIST"):
            raise Exception("Answer must be TRUE or TWIST")

        round_num = self.room_current_round.get(room_id, "0")
        sub_key   = f"{room_id}:{round_num}:{player_address}"

        if self.submission_answers.get(sub_key, "") != "":
            raise Exception("Already submitted this round!")

        self.submission_answers[sub_key]      = answer
        self.submission_explanations[sub_key] = explanation or ""
        self.submission_times[sub_key]        = str(submission_time)

        rnd_key  = f"{room_id}:{round_num}"
        existing = self.round_submitted.get(rnd_key, "")
        self.round_submitted[rnd_key] = (existing + "," + player_address).lstrip(",")

        return "Submitted!"

    @gl.public.write
    def score_round(self, room_id: str) -> str:
        """Server-side scoring handles XP - this just marks the round complete on-chain."""
        if self.room_status.get(room_id, "") != "active":
            raise Exception("Game is not active!")

        round_num = self.room_current_round.get(room_id, "0")
        players   = self._split(self.room_players.get(room_id, ""))
        week      = int(self.current_week_str)
        indices   = self._split(self.room_statement_indices.get(room_id, ""))
        stmt      = self._get_statement(week, int(indices[int(round_num) - 1]))

        game_over = int(round_num) >= 5
        if game_over:
            self.room_status[room_id] = "finished"
            self._finalize_game(room_id, players)
        else:
            self.room_current_round[room_id] = str(int(round_num) + 1)

        return json.dumps({
            "round_complete": True,
            "round_number": int(round_num),
            "correct_answer": stmt["answer"],
            "real_explanation": stmt["explanation"],
            "difficulty": stmt["difficulty"],
            "game_over": game_over,
        })

    def _finalize_game(self, room_id: str, players: list) -> None:
        scores = []
        for addr in players:
            score = int(self.player_scores.get(f"{room_id}:{addr}", "0"))
            scores.append((addr, score))
        scores.sort(key=lambda x: x[1], reverse=True)

        ranking = [
            {"rank": i + 1, "player": addr, "score": score}
            for i, (addr, score) in enumerate(scores)
        ]
        self.room_final_ranking[room_id] = json.dumps(ranking)

    # ======================================================
    # READ-ONLY VIEWS
    # ======================================================

    @gl.public.view
    def get_weekly_topic(self) -> dict:
        return {
            "week_number": int(self.current_week_str),
            "topic": self.current_week_topic or "Mixed Trivia",
            "statements_ready": self.weekly_stmt_count != "0",
            "total_statements": int(self.weekly_stmt_count),
        }

    @gl.public.view
    def get_weekly_questions(self) -> list:
        """Return all questions for the current week (for display/preview)."""
        week  = int(self.current_week_str)
        count = int(self.weekly_stmt_count)
        qs = []
        for i in range(count):
            key = f"{week}:{i}"
            qs.append({
                "index":       i,
                "statement":   self.weekly_stmt_text.get(key, ""),
                "answer":      self.weekly_stmt_answer.get(key, ""),
                "explanation": self.weekly_stmt_explanation.get(key, ""),
                "difficulty":  self.weekly_stmt_difficulty.get(key, "medium"),
            })
        return qs

    @gl.public.view
    def get_room_state(self, room_id: str) -> dict:
        status = self.room_status.get(room_id, "")
        if not status:
            raise Exception(f"Room {room_id} not found!")

        players   = self._split(self.room_players.get(room_id, ""))
        round_num = self.room_current_round.get(room_id, "0")

        scores = {addr: int(self.player_scores.get(f"{room_id}:{addr}", "0")) for addr in players}

        state = {
            "room_id":       room_id,
            "host":          self.room_host.get(room_id, ""),
            "players":       players,
            "player_count":  len(players),
            "status":        status,
            "current_round": int(round_num),
            "total_rounds":  5,
            "scores":        scores,
        }

        if status == "active" and int(round_num) > 0:
            week    = int(self.current_week_str)
            indices = self._split(self.room_statement_indices.get(room_id, ""))
            stmt    = self._get_statement(week, int(indices[int(round_num) - 1]))
            state["current_statement"] = stmt["statement"]
            rnd_key = f"{room_id}:{round_num}"
            submitted = self._split(self.round_submitted.get(rnd_key, ""))
            state["submitted_count"] = len(submitted)
            state["waiting_for"]     = len(players) - len(submitted)

        if status == "finished":
            state["final_ranking"] = json.loads(self.room_final_ranking.get(room_id, "[]"))

        return state

    @gl.public.view
    def get_player_profile(self, address: str) -> dict:
        """Full on-chain player profile."""
        games = int(self.profile_games_played.get(address, "0"))
        return {
            "address":       address,
            "nickname":      self.profile_nickname.get(address, ""),
            "join_nonce":    self.profile_join_nonce.get(address, ""),
            "last_nonce":    self.profile_last_nonce.get(address, ""),
            "total_xp":      int(self.profile_total_xp.get(address, "0")),
            "games_played":  games,
            "wins":          int(self.profile_wins.get(address, "0")),
            "best_score":    int(self.profile_best_score.get(address, "0")),
            "win_streak":    int(self.profile_streak.get(address, "0")),
            "best_streak":   int(self.profile_best_streak.get(address, "0")),
            "registered":    self.profile_join_nonce.get(address, "") != "",
        }

    @gl.public.view
    def get_leaderboard(self) -> list:
        """Top 20 players by total XP - reads from on-chain profiles."""
        known = self._split(self.all_players)
        entries = []
        for addr in known:
            xp = int(self.profile_total_xp.get(addr, "0"))
            if xp > 0:
                entries.append((addr, xp))
        entries.sort(key=lambda x: x[1], reverse=True)

        return [
            {
                "rank":         i + 1,
                "player":       addr,
                "nickname":     self.profile_nickname.get(addr, ""),
                "total_xp":     xp,
                "games_played": int(self.profile_games_played.get(addr, "0")),
                "wins":         int(self.profile_wins.get(addr, "0")),
                "best_score":   int(self.profile_best_score.get(addr, "0")),
                "win_streak":   int(self.profile_best_streak.get(addr, "0")),
            }
            for i, (addr, xp) in enumerate(entries[:20])
        ]
