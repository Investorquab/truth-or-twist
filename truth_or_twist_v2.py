# v0.1.0
# { "Depends": "py-genlayer:test" }

from genlayer import *
from dataclasses import dataclass
import json

class TruthOrTwist(gl.Contract):

    room_host: TreeMap[str, str]

    room_players: TreeMap[str, str]

    room_status: TreeMap[str, str]

    room_current_round: TreeMap[str, str]

    player_scores: TreeMap[str, str]

    submission_answers: TreeMap[str, str]

    submission_explanations: TreeMap[str, str]

    submission_times: TreeMap[str, str]

    round_submitted: TreeMap[str, str]

    room_final_ranking: TreeMap[str, str]

    room_statement_indices: TreeMap[str, str]

    weekly_stmt_text: TreeMap[str, str]

    weekly_stmt_answer: TreeMap[str, str]

    weekly_stmt_explanation: TreeMap[str, str]

    weekly_stmt_count: str

    current_week_str: str

    lb_total_xp: TreeMap[str, str]
    lb_games_played: TreeMap[str, str]
    lb_wins: TreeMap[str, str]
    lb_best_score: TreeMap[str, str]

    lb_all_players: str
    room_counter: str

    def __init__(self) -> None:
        self.weekly_stmt_count = "0"
        self.current_week_str = "0"
        self.lb_all_players = ""
        self.room_counter = "0"

    def _get_week_number(self) -> int:
        # Use stored week number (incremented manually via new_week())
        return int(self.current_week_str) if self.current_week_str != "0" else 1

    def _split(self, value: str) -> list:
        if value == "" or value is None:
            return []
        return value.split(",")

    def _get_statement(self, week: int, index: int) -> dict:
        key = f"{week}:{index}"
        return {
            "statement": self.weekly_stmt_text.get(key, ""),
            "answer": self.weekly_stmt_answer.get(key, "TRUE"),
            "explanation": self.weekly_stmt_explanation.get(key, ""),
        }

    def _generate_weekly_statements(self) -> None:
        week_num = self._get_week_number()

        # Pre-written statements — no AI timeout risk.
        # AI is still used for scoring player EXPLANATIONS (the fun part).
        statements = [
            {"statement": "The Great Wall of China is not visible from space with the naked eye.", "answer": "TRUE", "explanation": "Despite the myth, the wall is too narrow to see from orbit without aid."},
            {"statement": "Honey never expires — archaeologists found 3000-year-old honey in Egyptian tombs that was still edible.", "answer": "TRUE", "explanation": "Honey's low moisture and acidic pH make it last indefinitely if sealed."},
            {"statement": "A day on Venus is shorter than a year on Venus.", "answer": "TWIST", "explanation": "A day on Venus (243 Earth days) is actually LONGER than its year (225 Earth days)."},
            {"statement": "Octopuses have three hearts and blue blood.", "answer": "TRUE", "explanation": "Two hearts pump blood to the gills; one pumps to the body. Copper-based blood is blue."},
            {"statement": "The Eiffel Tower was originally built as a permanent structure for Paris.", "answer": "TWIST", "explanation": "It was built as a temporary exhibit for the 1889 World's Fair and was meant to be demolished."},
            {"statement": "Bananas are technically berries, but strawberries are not.", "answer": "TRUE", "explanation": "Botanically, bananas qualify as berries; strawberries are accessory fruits."},
            {"statement": "Mount Everest is the tallest mountain on Earth measured from sea level.", "answer": "TRUE", "explanation": "At 8,849m above sea level, Everest is the highest point on Earth."},
            {"statement": "The human brain uses about 80% of the body's total energy.", "answer": "TWIST", "explanation": "The brain uses roughly 20% of the body's energy, not 80%."},
            {"statement": "Lightning strikes the Earth about 100 times every second.", "answer": "TRUE", "explanation": "Earth experiences roughly 8 million lightning strikes per day — about 100 per second."},
            {"statement": "Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid.", "answer": "TRUE", "explanation": "The pyramids were built ~2560 BC; Cleopatra lived ~30 BC; the Moon landing was 1969 AD."},
        ]

        for i, stmt in enumerate(statements):
            key = f"{week_num}:{i}"
            self.weekly_stmt_text[key] = stmt["statement"]
            self.weekly_stmt_answer[key] = stmt["answer"]
            self.weekly_stmt_explanation[key] = stmt["explanation"]

        self.weekly_stmt_count = str(len(statements))
        self.current_week_str = str(week_num)

    @gl.public.write
    def generate_statements(self) -> str:
        """Call this once before the first game to generate weekly questions."""
        week_num = self._get_week_number()
        self._generate_weekly_statements()
        return f"Generated statements for week {week_num}"

    @gl.public.write
    def create_room(self, player_address: str) -> str:
        # NOTE: Call generate_statements() once before creating rooms!
        # create_room no longer triggers generation to avoid non-det + storage bug.

        # Use a counter for unique room IDs (no timestamp needed)
        room_num = int(self.room_counter) + 1
        self.room_counter = str(room_num)
        room_id = f"ROOM-{room_num:04d}"

        # Pick 5 statement indices based on room number
        total = int(self.weekly_stmt_count) if self.weekly_stmt_count != "0" else 10
        start = room_num % max(1, total - 5)
        indices = [str(start + i) for i in range(5)]

        self.room_host[room_id] = player_address
        self.room_players[room_id] = player_address
        self.room_status[room_id] = "waiting"
        self.room_current_round[room_id] = "0"
        self.room_statement_indices[room_id] = ",".join(indices)
        self.room_final_ranking[room_id] = "[]"
        self.player_scores[f"{room_id}:{player_address}"] = "0"

        return room_id

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

        week = int(self.current_week_str)
        indices = self._split(self.room_statement_indices.get(room_id, ""))
        stmt = self._get_statement(week, int(indices[0]))
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

        if answer not in ["TRUE", "TWIST"]:
            raise Exception("Answer must be TRUE or TWIST")

        if len(explanation.strip()) < 10:
            raise Exception("Explanation too short — write more!")

        round_num = self.room_current_round.get(room_id, "0")
        sub_key = f"{room_id}:{round_num}:{player_address}"

        if self.submission_answers.get(sub_key, "") != "":
            raise Exception("Already submitted this round!")

        self.submission_answers[sub_key] = answer
        self.submission_explanations[sub_key] = explanation
        self.submission_times[sub_key] = str(submission_time)

        rnd_key = f"{room_id}:{round_num}"
        existing = self.round_submitted.get(rnd_key, "")
        if existing == "":
            self.round_submitted[rnd_key] = player_address
        else:
            self.round_submitted[rnd_key] = existing + "," + player_address

        return "Submitted!"

    @gl.public.write
    def score_round(self, room_id: str) -> str:

        if self.room_status.get(room_id, "") != "active":
            raise Exception("Game is not active!")

        round_num = self.room_current_round.get(room_id, "0")
        players = self._split(self.room_players.get(room_id, ""))

        rnd_key = f"{room_id}:{round_num}"
        submitted = self._split(self.round_submitted.get(rnd_key, ""))
        if len(submitted) < len(players):
            return json.dumps({
                "waiting": True,
                "submitted": len(submitted),
                "total": len(players),
            })

        week = int(self.current_week_str)
        indices = self._split(self.room_statement_indices.get(room_id, ""))
        stmt = self._get_statement(week, int(indices[int(round_num) - 1]))
        correct_answer = stmt["answer"]
        statement_text = stmt["statement"]
        real_explanation = stmt["explanation"]

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

        raw_result = gl.exec_prompt(scoring_prompt)
        raw_result = raw_result.strip()
        if raw_result.startswith("```"):
            lines = raw_result.split("\n")
            raw_result = "\n".join(lines[1:])
            if raw_result.endswith("```"):
                raw_result = raw_result[:-3].strip()

        scoring_data = json.loads(raw_result)
        winner_short_id = scoring_data.get("winner_of_round", "")

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

        game_over = False
        if int(round_num) >= 5:
            self.room_status[room_id] = "finished"
            self._finalize_game(room_id, players)
            game_over = True
        else:
            self.room_current_round[room_id] = str(int(round_num) + 1)

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

        for i, (addr, score) in enumerate(scores):
            old_xp = int(self.lb_total_xp.get(addr, "0"))
            old_games = int(self.lb_games_played.get(addr, "0"))
            old_wins = int(self.lb_wins.get(addr, "0"))
            old_best = int(self.lb_best_score.get(addr, "0"))

            self.lb_total_xp[addr] = str(old_xp + score)
            self.lb_games_played[addr] = str(old_games + 1)
            self.lb_wins[addr] = str(old_wins + (1 if i == 0 else 0))
            self.lb_best_score[addr] = str(max(old_best, score))

            all_p = self.lb_all_players
            known = all_p.split(",") if all_p != "" else []
            if addr not in known:
                self.lb_all_players = (all_p + "," + addr) if all_p != "" else addr

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
