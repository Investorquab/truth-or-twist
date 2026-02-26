# v0.1.0
# { "Depends": "py-genlayer:test" }

# ==============================================================================
# TRUTH OR TWIST — GenLayer Intelligent Contract
# ==============================================================================
# A multiplayer trivia game where AI judges player explanations,
# and GenLayer's Optimistic Democracy validates the scores fairly.
#
# KEY RULES for GenLayer contracts (read this if you're a beginner!):
#   ✅ Use TreeMap[str, X]  instead of  dict
#   ✅ Use DynArray[str]    instead of  list
#   ✅ Use u64, i32, etc.   instead of  int
#   ✅ Use @allow_storage @dataclass for custom storage objects
#   ✅ AI calls use gl.exec_prompt() inside a def, then eq_principle
#   ✅ Header must say py-genlayer:test
# ==============================================================================

from genlayer import *
from dataclasses import dataclass
import json


class TruthOrTwist(gl.Contract):

    # ==========================================================================
    # STORAGE — Declared at class level with proper GenLayer types
    # ==========================================================================
    # These are the contract's permanent memory fields.
    # IMPORTANT: GenLayer requires all persistent fields declared HERE with types.
    # You CANNOT use plain dict or list — use TreeMap and DynArray instead.
    # You CANNOT use plain int — use u64, i32, u256, etc.

    # --- Room storage ---
    # We use flat compound keys like "room_id:player_addr" because
    # nested TreeMap[str, TreeMap[...]] is not supported.
    # Think of it like a spreadsheet where each cell has a unique row name.

    # Maps room_id -> host wallet address
    room_host: TreeMap[str, str]

    # Maps room_id -> comma-separated player addresses
    # Example: "0xAAA,0xBBB,0xCCC"
    room_players: TreeMap[str, str]

    # Maps room_id -> game status: "waiting", "active", or "finished"
    room_status: TreeMap[str, str]

    # Maps room_id -> current round number as a string ("0", "1" .. "5")
    room_current_round: TreeMap[str, str]

    # Maps "room_id:player_addr" -> that player's total score as string
    player_scores: TreeMap[str, str]

    # Maps "room_id:round:player_addr" -> the answer they chose ("TRUE" or "TWIST")
    submission_answers: TreeMap[str, str]

    # Maps "room_id:round:player_addr" -> their written explanation
    submission_explanations: TreeMap[str, str]

    # Maps "room_id:round:player_addr" -> submission timestamp as string
    submission_times: TreeMap[str, str]

    # Maps "room_id:round" -> comma-separated addresses of players who submitted
    round_submitted: TreeMap[str, str]

    # Maps room_id -> JSON string of the final ranking (set when game ends)
    room_final_ranking: TreeMap[str, str]

    # Maps room_id -> comma-separated statement indices (5 numbers, e.g. "3,4,5,6,7")
    room_statement_indices: TreeMap[str, str]

    # --- Weekly statement storage ---
    # We flatten each statement into separate TreeMaps using "week:index" as key
    # e.g. key "42:0" = week 42, statement index 0

    # Maps "week:index" -> statement text
    weekly_stmt_text: TreeMap[str, str]

    # Maps "week:index" -> correct answer ("TRUE" or "TWIST")
    weekly_stmt_answer: TreeMap[str, str]

    # Maps "week:index" -> real explanation (revealed after round)
    weekly_stmt_explanation: TreeMap[str, str]

    # How many statements exist for the current week (stored as string)
    weekly_stmt_count: str

    # The week number we last generated statements for (stored as string)
    current_week_str: str

    # --- Global leaderboard ---
    # Flat storage: one TreeMap per stat type, keyed by player address

    lb_total_xp: TreeMap[str, str]
    lb_games_played: TreeMap[str, str]
    lb_wins: TreeMap[str, str]
    lb_best_score: TreeMap[str, str]

    # All player addresses who have ever played, comma-separated
    lb_all_players: str

    # ==========================================================================
    # CONSTRUCTOR — Runs ONCE when the contract is first deployed
    # ==========================================================================

    def __init__(self) -> None:
        self.weekly_stmt_count = "0"
        self.current_week_str = "0"
        self.lb_all_players = ""

    # ==========================================================================
    # INTERNAL HELPER: Current week number
    # ==========================================================================
    # 604800 = number of seconds in one week (60 x 60 x 24 x 7)
    # Dividing timestamp by this gives a steadily increasing week counter.

    def _get_week_number(self) -> int:
        return int(gl.get_block_timestamp()) // 604800

    # ==========================================================================
    # INTERNAL HELPER: Split comma-separated string into a list
    # ==========================================================================

    def _split(self, value: str) -> list:
        if value == "" or value is None:
            return []
        return value.split(",")

    # ==========================================================================
    # INTERNAL HELPER: Get statement data by week + index
    # ==========================================================================

    def _get_statement(self, week: int, index: int) -> dict:
        key = f"{week}:{index}"
        return {
            "statement": self.weekly_stmt_text.get(key, ""),
            "answer": self.weekly_stmt_answer.get(key, "TRUE"),
            "explanation": self.weekly_stmt_explanation.get(key, ""),
        }

    # ==========================================================================
    # INTERNAL HELPER: Generate weekly statements using AI
    # ==========================================================================
    # This uses GenLayer's LLM integration.
    # The correct pattern is:
    #   1. Build your prompt string
    #   2. Define a function that calls gl.exec_prompt(prompt)
    #   3. Pass that function to gl.eq_principle_prompt_comparative()
    #
    # Multiple validators independently run the inner function and compare.
    # This is Optimistic Democracy — consensus on AI output.

    def _generate_weekly_statements(self) -> None:
        week_num = self._get_week_number()

        topics = [
            "science and nature",
            "world history",
            "geography",
            "technology and inventions",
            "space and astronomy",
            "human biology",
            "famous landmarks",
            "food and nutrition",
            "world records",
            "ancient civilizations",
        ]
        topic = topics[week_num % len(topics)]

        # Use non-comparative principle: only the leader generates statements,
        # validators just check the output is valid (correct format + count).
        # This is the right approach for creative generation tasks where
        # two AIs will always produce different creative content.
        prompt = f"""You are creating questions for a trivia game called Truth or Twist.
Topic: {topic}
Week: {week_num}

Generate exactly 10 trivia statements about {topic}.
Exactly 5 must be TRUE (surprising but accurate facts).
Exactly 5 must be TWIST (have one subtle factual error).

Rules:
- Max 2 sentences per statement
- Be specific with numbers and facts
- Make TWIST statements believable but wrong in one detail

You MUST respond with ONLY a JSON array. No markdown. No text before or after.
[
  {{"id": 0, "statement": "...", "answer": "TRUE", "explanation": "...why true..."}},
  {{"id": 1, "statement": "...", "answer": "TWIST", "explanation": "...what is wrong..."}}
]"""

        def call_ai():
            raw = gl.exec_prompt(prompt)
            raw = raw.strip()
            # Strip markdown fences
            if raw.startswith("```"):
                lines = raw.split("
")
                raw = "
".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            raw = raw.strip()
            return raw

        # Non-comparative: leader generates, validators verify format only
        # This prevents validator disagreement on creative content
        result = gl.eq_principle_prompt_non_comparative(
            call_ai,
            task="Generate 10 trivia statements as a JSON array",
            criteria="The response must be a valid JSON array with exactly 10 objects. "
                     "Each object must have 'id' (number), 'statement' (string), "
                     "'answer' (either TRUE or TWIST), and 'explanation' (string). "
                     "There must be at least 3 TRUE and at least 3 TWIST answers."
        )

        statements = json.loads(result)

        # Save each statement flat into storage
        count = 0
        for i, stmt in enumerate(statements):
            key = f"{week_num}:{i}"
            self.weekly_stmt_text[key] = str(stmt.get("statement", ""))
            self.weekly_stmt_answer[key] = str(stmt.get("answer", "TRUE"))
            self.weekly_stmt_explanation[key] = str(stmt.get("explanation", ""))
            count = i + 1

        self.weekly_stmt_count = str(count)
        self.current_week_str = str(week_num)

    # ==========================================================================
    # WRITE METHOD: create_room
    # ==========================================================================

    @gl.public.write
    def create_room(self, player_address: str) -> str:

        # Regenerate statements if week changed or none exist yet
        week_num = self._get_week_number()
        stored_week = int(self.current_week_str)
        if week_num != stored_week or self.weekly_stmt_count == "0":
            self._generate_weekly_statements()

        # Build a short unique room code from the timestamp
        ts = int(gl.get_block_timestamp())
        room_id = f"ROOM-{str(ts)[-4:]}"
        if self.room_status.get(room_id, "") != "":
            room_id = f"ROOM-{str(ts)[-5:]}"

        # Pick 5 statement indices pseudo-randomly using the timestamp
        total = int(self.weekly_stmt_count)
        start = (ts // 100) % max(1, total - 5)
        indices = [str(start + i) for i in range(5)]

        # Save room to storage
        self.room_host[room_id] = player_address
        self.room_players[room_id] = player_address
        self.room_status[room_id] = "waiting"
        self.room_current_round[room_id] = "0"
        self.room_statement_indices[room_id] = ",".join(indices)
        self.room_final_ranking[room_id] = "[]"

        # Initialize host score at 0
        self.player_scores[f"{room_id}:{player_address}"] = "0"

        return room_id

    # ==========================================================================
    # WRITE METHOD: join_room
    # ==========================================================================

    @gl.public.write
    def join_room(self, room_id: str, player_address: str) -> str:

        status = self.room_status.get(room_id, "")
        if status == "":
            raise Exception(f"Room {room_id} does not exist!")
        if status != "waiting":
            raise Exception("Game already started!")

        players = self._split(self.room_players.get(room_id, ""))
        if len(players) >= 8:
            raise Exception("Room is full (max 8 players)!")
        if player_address in players:
            raise Exception("You are already in this room!")

        players.append(player_address)
        self.room_players[room_id] = ",".join(players)
        self.player_scores[f"{room_id}:{player_address}"] = "0"

        return f"Joined {room_id}!"

    # ==========================================================================
    # WRITE METHOD: start_game
    # ==========================================================================

    @gl.public.write
    def start_game(self, room_id: str, host_address: str) -> str:

        status = self.room_status.get(room_id, "")
        if status == "":
            raise Exception(f"Room {room_id} not found!")
        if self.room_host.get(room_id, "") != host_address:
            raise Exception("Only the host can start the game!")

        players = self._split(self.room_players.get(room_id, ""))
        if len(players) < 2:
            raise Exception("Need at least 2 players!")
        if status != "waiting":
            raise Exception("Game already started!")

        self.room_status[room_id] = "active"
        self.room_current_round[room_id] = "1"

        # Return the first statement text
        week = int(self.current_week_str)
        indices = self._split(self.room_statement_indices.get(room_id, ""))
        stmt = self._get_statement(week, int(indices[0]))
        return stmt["statement"]

    # ==========================================================================
    # WRITE METHOD: submit_answer
    # ==========================================================================

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

        if answer not in ["TRUE", "TWIST"]:
            raise Exception("Answer must be TRUE or TWIST")

        if len(explanation.strip()) < 10:
            raise Exception("Explanation too short — write more!")

        round_num = self.room_current_round.get(room_id, "0")
        sub_key = f"{room_id}:{round_num}:{player_address}"

        if self.submission_answers.get(sub_key, "") != "":
            raise Exception("Already submitted this round!")

        # Store submission
        self.submission_answers[sub_key] = answer
        self.submission_explanations[sub_key] = explanation
        self.submission_times[sub_key] = str(submission_time)

        # Track who has submitted
        rnd_key = f"{room_id}:{round_num}"
        existing = self.round_submitted.get(rnd_key, "")
        if existing == "":
            self.round_submitted[rnd_key] = player_address
        else:
            self.round_submitted[rnd_key] = existing + "," + player_address

        return "Submitted!"

    # ==========================================================================
    # WRITE METHOD: score_round
    # ==========================================================================
    # AI scoring with Optimistic Democracy.

    @gl.public.write
    def score_round(self, room_id: str) -> str:

        if self.room_status.get(room_id, "") != "active":
            raise Exception("Game is not active!")

        round_num = self.room_current_round.get(room_id, "0")
        players = self._split(self.room_players.get(room_id, ""))

        # Check if everyone submitted
        rnd_key = f"{room_id}:{round_num}"
        submitted = self._split(self.round_submitted.get(rnd_key, ""))
        if len(submitted) < len(players):
            return json.dumps({
                "waiting": True,
                "submitted": len(submitted),
                "total": len(players),
            })

        # Get the statement for this round
        week = int(self.current_week_str)
        indices = self._split(self.room_statement_indices.get(room_id, ""))
        stmt = self._get_statement(week, int(indices[int(round_num) - 1]))
        correct_answer = stmt["answer"]
        statement_text = stmt["statement"]
        real_explanation = stmt["explanation"]

        # Build player lines for the AI prompt
        player_lines = ""
        for addr in players:
            sub_key = f"{room_id}:{round_num}:{addr}"
            p_answer = self.submission_answers.get(sub_key, "?")
            p_explanation = self.submission_explanations.get(sub_key, "")
            short_id = addr[2:8]
            player_lines += (
                f"\nPlayerID: {short_id}\n"
                f"  Chose: {p_answer}\n"
                f"  Explanation: {p_explanation}\n"
            )

        scoring_prompt = f"""You are an AI judge for a trivia game called Truth or Twist.

STATEMENT SHOWN TO PLAYERS: "{statement_text}"
CORRECT ANSWER: {correct_answer}
REAL EXPLANATION: {real_explanation}

PLAYERS AND THEIR EXPLANATIONS:{player_lines}

YOUR JOB: Score each player's explanation quality from 0 to 100.

Scoring guide:
80-100: Excellent — accurate, clear, well-reasoned
60-79: Good — mostly correct with minor gaps
40-59: Average — partially correct
20-39: Weak — mostly wrong but shows thought
0-19: Very poor — off topic or too short

Rules:
- Score explanation QUALITY regardless of their TRUE/TWIST choice
- winner_of_round = the PlayerID with the highest score
- Respond ONLY with valid JSON parseable by json.loads(). No markdown.

{{"scores": {{"PLAYERID": {{"score": 85, "feedback": "One sentence."}}}}, "winner_of_round": "PLAYERID"}}"""

        # Official GenLayer AI call pattern
        def run_ai():
            raw = gl.exec_prompt(scoring_prompt)
            raw = raw.replace("```json", "").replace("```", "").strip()
            return raw

        # Non-comparative: leader scores, validators verify format and fairness
        # Scores will naturally vary slightly between AI runs, so non-comparative
        # is the correct principle here — validators just check it makes sense
        raw_result = gl.eq_principle_prompt_non_comparative(
            run_ai,
            task="Score player explanations for a trivia game round",
            criteria="The response must be valid JSON with a 'scores' object containing "
                     "each player's score (0-100) and one-sentence feedback, plus a "
                     "'winner_of_round' field. Scores must be fair and proportional "
                     "to explanation quality. No player should have a score above 100."
        )

        scoring_data = json.loads(raw_result)
        winner_short_id = scoring_data.get("winner_of_round", "")

        # Find speed bonus winner (first player with correct answer)
        timing = []
        for addr in players:
            sub_key = f"{room_id}:{round_num}:{addr}"
            t = int(self.submission_times.get(sub_key, "0"))
            timing.append((addr, t))
        timing.sort(key=lambda x: x[1])

        first_correct = None
        for addr, _ in timing:
            sub_key = f"{room_id}:{round_num}:{addr}"
            if self.submission_answers.get(sub_key, "") == correct_answer:
                first_correct = addr
                break

        # Calculate XP for each player
        round_results = {}
        for addr in players:
            short_id = addr[2:8]
            sub_key = f"{room_id}:{round_num}:{addr}"
            p_answer = self.submission_answers.get(sub_key, "")
            got_correct = p_answer == correct_answer

            xp = 0
            parts = []

            if got_correct:
                xp += 10
                parts.append("+10 correct")

            score_entry = scoring_data.get("scores", {}).get(short_id, {})
            ai_score = int(score_entry.get("score", 0))
            feedback = score_entry.get("feedback", "")
            eq_xp = ai_score // 5
            xp += eq_xp
            parts.append(f"+{eq_xp} explanation")

            speed = addr == first_correct and got_correct
            if speed:
                xp += 5
                parts.append("+5 fastest!")

            perfect = got_correct and short_id == winner_short_id
            if perfect:
                xp += 10
                parts.append("+10 perfect round!")

            # Update total score
            score_key = f"{room_id}:{addr}"
            old = int(self.player_scores.get(score_key, "0"))
            self.player_scores[score_key] = str(old + xp)

            round_results[addr] = {
                "answer": p_answer,
                "correct": got_correct,
                "ai_score": ai_score,
                "ai_feedback": feedback,
                "round_xp": xp,
                "xp_breakdown": parts,
                "speed_bonus": speed,
                "perfect_round": perfect,
            }

        # Advance round or end game
        game_over = False
        if int(round_num) >= 5:
            self.room_status[room_id] = "finished"
            self._finalize_game(room_id, players)
            game_over = True
        else:
            self.room_current_round[room_id] = str(int(round_num) + 1)

        # Build current scores dict for response
        current_scores = {}
        for addr in players:
            current_scores[addr] = int(
                self.player_scores.get(f"{room_id}:{addr}", "0")
            )

        return json.dumps({
            "round_complete": True,
            "round_number": int(round_num),
            "correct_answer": correct_answer,
            "real_explanation": real_explanation,
            "round_results": round_results,
            "current_scores": current_scores,
            "game_over": game_over,
        })

    # ==========================================================================
    # INTERNAL HELPER: Finalize game + update leaderboard
    # ==========================================================================

    def _finalize_game(self, room_id: str, players: list) -> None:

        # Collect scores and sort
        scores = []
        for addr in players:
            score = int(self.player_scores.get(f"{room_id}:{addr}", "0"))
            scores.append((addr, score))
        scores.sort(key=lambda x: x[1], reverse=True)

        # Save final ranking as JSON
        ranking = [
            {"rank": i + 1, "player": addr, "score": score}
            for i, (addr, score) in enumerate(scores)
        ]
        self.room_final_ranking[room_id] = json.dumps(ranking)

        # Update leaderboard for each player
        for i, (addr, score) in enumerate(scores):
            old_xp = int(self.lb_total_xp.get(addr, "0"))
            old_games = int(self.lb_games_played.get(addr, "0"))
            old_wins = int(self.lb_wins.get(addr, "0"))
            old_best = int(self.lb_best_score.get(addr, "0"))

            self.lb_total_xp[addr] = str(old_xp + score)
            self.lb_games_played[addr] = str(old_games + 1)
            self.lb_wins[addr] = str(old_wins + (1 if i == 0 else 0))
            self.lb_best_score[addr] = str(max(old_best, score))

            # Register player in the global list (for sorting)
            all_p = self.lb_all_players
            known = all_p.split(",") if all_p != "" else []
            if addr not in known:
                self.lb_all_players = (all_p + "," + addr) if all_p != "" else addr

    # ==========================================================================
    # READ METHOD: get_room_state
    # ==========================================================================

    @gl.public.view
    def get_room_state(self, room_id: str) -> dict:

        status = self.room_status.get(room_id, "")
        if status == "":
            raise Exception(f"Room {room_id} not found!")

        players = self._split(self.room_players.get(room_id, ""))
        round_num = self.room_current_round.get(room_id, "0")

        scores = {}
        for addr in players:
            scores[addr] = int(self.player_scores.get(f"{room_id}:{addr}", "0"))

        state = {
            "room_id": room_id,
            "host": self.room_host.get(room_id, ""),
            "players": players,
            "player_count": len(players),
            "status": status,
            "current_round": int(round_num),
            "total_rounds": 5,
            "scores": scores,
        }

        if status == "active" and int(round_num) > 0:
            week = int(self.current_week_str)
            indices = self._split(self.room_statement_indices.get(room_id, ""))
            stmt = self._get_statement(week, int(indices[int(round_num) - 1]))
            state["current_statement"] = stmt["statement"]

            rnd_key = f"{room_id}:{round_num}"
            submitted = self._split(self.round_submitted.get(rnd_key, ""))
            state["submitted_count"] = len(submitted)
            state["waiting_for"] = len(players) - len(submitted)

        if status == "finished":
            state["final_ranking"] = json.loads(
                self.room_final_ranking.get(room_id, "[]")
            )

        return state

    # ==========================================================================
    # READ METHOD: get_leaderboard
    # ==========================================================================

    @gl.public.view
    def get_leaderboard(self) -> list:

        all_raw = self.lb_all_players
        if all_raw == "":
            return []

        entries = []
        for addr in all_raw.split(","):
            if addr == "":
                continue
            xp = int(self.lb_total_xp.get(addr, "0"))
            entries.append((addr, xp))

        entries.sort(key=lambda x: x[1], reverse=True)
        top_20 = entries[:20]

        return [
            {
                "rank": i + 1,
                "player": addr,
                "short_id": addr[2:8],
                "total_xp": xp,
                "games_played": int(self.lb_games_played.get(addr, "0")),
                "wins": int(self.lb_wins.get(addr, "0")),
                "best_score": int(self.lb_best_score.get(addr, "0")),
            }
            for i, (addr, xp) in enumerate(top_20)
        ]

    # ==========================================================================
    # READ METHOD: get_weekly_topic
    # ==========================================================================

    @gl.public.view
    def get_weekly_topic(self) -> dict:

        topics = [
            "science and nature", "world history", "geography",
            "technology and inventions", "space and astronomy",
            "human biology", "famous landmarks", "food and nutrition",
            "world records", "ancient civilizations",
        ]
        week_num = self._get_week_number()

        return {
            "week_number": week_num,
            "topic": topics[week_num % len(topics)],
            "statements_ready": self.weekly_stmt_count != "0",
            "total_statements": int(self.weekly_stmt_count),
        }

    # ==========================================================================
    # READ METHOD: get_player_stats
    # ==========================================================================

    @gl.public.view
    def get_player_stats(self, player_address: str) -> dict:

        games = int(self.lb_games_played.get(player_address, "0"))
        if games == 0:
            return {
                "player": player_address,
                "total_xp": 0,
                "games_played": 0,
                "wins": 0,
                "best_score": 0,
                "on_leaderboard": False,
            }

        return {
            "player": player_address,
            "total_xp": int(self.lb_total_xp.get(player_address, "0")),
            "games_played": games,
            "wins": int(self.lb_wins.get(player_address, "0")),
            "best_score": int(self.lb_best_score.get(player_address, "0")),
            "on_leaderboard": True,
        }
