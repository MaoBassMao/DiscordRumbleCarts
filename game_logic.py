import random
from typing import List, Optional, Set, Dict, Tuple
from models import PlayerPoints, PlayerPointHistory
from app import app, db
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from race_events import RaceEvents

logger = logging.getLogger(__name__)

# --- ポイント定数 ---
WINNER_POINTS = 10
SECOND_PLACE_POINTS = 7
PARTICIPATION_POINTS = 2
GREAT_COMEBACK_SECOND_PLACE_POINTS = 5

# --- 作戦関連定数 ---
STRATEGY_START_DASH = 'start_dash'
STRATEGY_TOP_SPEED = 'top_speed'
STRATEGY_CORNERING = 'cornering'

class Player:
    def __init__(self, id: int, name: str, is_bot: bool = False):
        self.id = id
        self.name = name
        self.is_bot = is_bot
        self.is_active = True
        self.eliminated = False
        self.used_in_current_lap = False
        self.strategy: Optional[str] = None

    def __eq__(self, other):
        if not isinstance(other, Player): return NotImplemented
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

class GameState:
    STRATEGIES: List[str] = [STRATEGY_START_DASH, STRATEGY_TOP_SPEED, STRATEGY_CORNERING]
    STRATEGY_WIN_BONUS_RATE = 0.55 # 55%
    # ★ 強制脱落イベントの確率計算パラメータ
    FORCED_ELIM_BASE_CHANCE = 0.0 # 5人未満の基本確率
    FORCED_ELIM_CHANCE_PER_PLAYER = 0.02 # 5人を超えた場合に1人あたり加算される確率
    FORCED_ELIM_MAX_CHANCE = 0.15 # 最大確率 (15%)
    FORCED_ELIM_MIN_PLAYERS = 5 # 最低発生人数

    def __init__(self, guild_id: str, race_events: 'RaceEvents'):
        self.players: List[Player] = []
        self.race_started = False
        self.current_lap = 0
        self.final_duel = False
        self.next_lap_final_duel = False
        self.winner: Optional[Player] = None
        self.second_place: Optional[Player] = None
        self.eliminated_this_lap: List[Player] = []
        self.revived_this_lap: List[Player] = []
        self.game_finished = False
        self.great_comeback_occurred = False
        self.great_comeback_winner: Optional[Player] = None
        self.great_comeback_losers: List[Player] = []

        self.guild_id: str = guild_id
        self.race_events: 'RaceEvents' = race_events
        self.strategy_advantage: Dict[str, float] = self._calculate_strategy_advantage()

        self._initialize_cpu_players()
        self.initial_players: List[Player] = list(self.players)
        # ★追加: 初期参加者数を記録 (Lap1のバトル数計算用)
        self.initial_participant_count: int = len(self.players)

    def _calculate_strategy_advantage(self) -> Dict[str, float]:
        # (変更なし)
        num_strategies = len(self.STRATEGIES)
        if num_strategies == 0: return {}
        base_prob = 1.0 / num_strategies
        max_fluctuation = 0.05
        probabilities = []
        current_sum = 0.0
        for i in range(num_strategies):
             if i < num_strategies - 1:
                  fluctuation = random.uniform(-max_fluctuation, max_fluctuation)
                  prob = base_prob + fluctuation; probabilities.append(max(0.01, prob)); current_sum += probabilities[-1]
             else:
                  last_prob = 1.0 - current_sum; probabilities.append(max(0.01, last_prob))
        final_sum = sum(probabilities)
        normalized_probabilities = [p / final_sum for p in probabilities]
        advantage = dict(zip(self.STRATEGIES, normalized_probabilities))
        logger.info(f"Calculated strategy advantage: {advantage}")
        return advantage

    def get_favored_strategy(self) -> Optional[str]:
         # (変更なし)
         if not self.strategy_advantage: return None
         return max(self.strategy_advantage, key=self.strategy_advantage.get)

    def add_player(self, player: Player) -> bool:
        # (変更なし)
        if not player.is_bot and player not in self.players and not self.race_started:
            self.players.append(player)
            self.initial_players.append(player)
            logger.info(f"Player {player.name} (ID: {player.id}, Strategy: {player.strategy}) joined the game in guild {self.guild_id}.")
            return True
        elif player in self.players: logger.warning(f"Player {player.name} already in game."); return False
        elif self.race_started: logger.warning(f"Race already started. Cannot add {player.name}."); return False
        return False

    def _initialize_cpu_players(self, count: int = 7):
        # (変更なし)
        cpu_names = ["イケハヤ", "road", "ROKU", "BUN", "HYDE", "デーモン小暮", "れんたろう"]
        num_names = len(cpu_names); actual_count = min(count, num_names)
        if count > num_names: logger.warning(f"Requested {count} CPUs, only {num_names} names. Using {num_names}.")
        for i in range(actual_count):
            cpu_player = Player(id=-(i + 1), name=cpu_names[i], is_bot=True)
            cpu_player.strategy = random.choice(self.STRATEGIES)
            self.players.append(cpu_player)
        logger.info(f"Initialized {actual_count} CPU players with random strategies.")

    def get_player_count(self) -> int: return len([p for p in self.players if not p.is_bot])
    def get_human_players(self) -> List[Player]: return [p for p in self.players if not p.is_bot]
    def get_players(self) -> List[Player]: return list(self.players)
    def get_active_players(self) -> List[Player]: return [p for p in self.players if p.is_active and not p.eliminated]

    def eliminate_player(self, player: Player):
        # (変更なし)
        target_player = next((p for p in self.players if p.id == player.id), None)
        if target_player and target_player.is_active:
            target_player.is_active = False; target_player.eliminated = True
            if target_player not in self.eliminated_this_lap: self.eliminated_this_lap.append(target_player)
            logger.info(f"Player {target_player.name} eliminated.")

    def revive_player(self, player: Player):
         # (変更なし)
         target_player = next((p for p in self.players if p.id == player.id), None)
         if target_player and not target_player.is_active and target_player.eliminated:
              target_player.is_active = True; target_player.eliminated = False; target_player.used_in_current_lap = False
              if target_player not in self.revived_this_lap: self.revived_this_lap.append(target_player)
              logger.info(f"Player {target_player.name} revived.")

    def reset_lap_usage(self):
        # (変更なし)
        self.current_lap += 1; self.eliminated_this_lap = []; self.revived_this_lap = []
        for p in self.players: p.used_in_current_lap = False
        if self.next_lap_final_duel:
            active_players = self.get_active_players()
            if len(active_players) == 2: self.final_duel = True; self.next_lap_final_duel = False; logger.info("Entering final duel!")
            else: logger.warning(f"Cancelling final duel. Active: {len(active_players)}"); self.next_lap_final_duel = False; self.final_duel = False

    # ★★★ ペア対決ロジック修正 ★★★
    def process_lap_pairwise(self) -> List[str]:
        """ペア対決方式(バトル数上限あり)でラップを処理し、イベントテキストのリストを返す"""
        messages = []
        active_players = self.get_active_players()
        available_players = [p for p in active_players if not p.used_in_current_lap]
        num_available = len(available_players)

        if num_available < 2: # ペアを作れない場合
             # 残ったプレイヤー全員にスキルイベント
             for player in available_players:
                  if player.is_active: # 念のため生存確認
                       text = self.race_events.get_skill_text(player) #, player.strategy) # 作戦情報渡す準備
                       messages.append(text)
                       player.used_in_current_lap = True
                       logger.debug(f"Skill (no pairs possible): {player.name}. Text: {text}")
             # ラップ終了後の生存者チェックも忘れずに
             active_after_lap = self.get_active_players()
             if len(active_after_lap) == 2: self.next_lap_final_duel = True
             return messages

        # --- バトル数の計算 ---
        if self.current_lap == 1:
            # Lap 1 は初期参加者数で計算
            battle_count_base = self.initial_participant_count
        else:
            # Lap 2 以降は現在の利用可能プレイヤー数で計算
            # (注意: 前ラップ生存者数ではなく、このラップ開始時の生存者数を使う方がシンプル)
            battle_count_base = num_available # 利用可能なプレイヤー数

        # min(8, max(1, S // 4)) を適用
        num_battles = min(8, max(1, battle_count_base // 4))
        # ただし、実際に組めるペア数を超えないようにする
        num_battles = min(num_battles, num_available // 2)
        logger.info(f"Lap {self.current_lap}: Base={battle_count_base}, Num Battles Calculated={num_battles}")
        # --- 計算ここまで ---

        random.shuffle(available_players) # シャッフル

        # ペアを組むプレイヤー (最大 num_battles * 2 人)
        paired_players_list = available_players[:num_battles * 2]
        # スキルイベント対象のプレイヤー (ペアにならなかった残り)
        single_players_list = available_players[num_battles * 2:]

        # ペアの処理 (num_battles 組)
        favored_strategy = self.get_favored_strategy()
        for i in range(0, len(paired_players_list), 2):
            player1 = paired_players_list[i]
            player2 = paired_players_list[i+1]

            # 作戦ボーナス判定
            winner, loser = None, None
            p1_is_favored = player1.strategy == favored_strategy
            p2_is_favored = player2.strategy == favored_strategy
            if p1_is_favored == p2_is_favored: winner, loser = random.sample([player1, player2], 2)
            elif p1_is_favored: winner, loser = (player1, player2) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player2, player1)
            else: winner, loser = (player2, player1) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player1, player2)

            was_advantageous = (winner.strategy == favored_strategy) and (loser.strategy != favored_strategy)
            text = self.race_events.get_overtake_text(winner, loser) #, winner.strategy, was_advantageous) # 準備
            messages.append(text)
            self.eliminate_player(loser)
            player1.used_in_current_lap = True
            player2.used_in_current_lap = True
            logger.debug(f"Overtake: {winner.name}({winner.strategy}) vs {loser.name}({loser.strategy}). Favored: {favored_strategy}. WinAdv: {was_advantageous}. Text: {text}")

        # シングルプレイヤー (スキルイベント) の処理
        for player in single_players_list:
            if player.is_active: # ペア対決中に強制脱落などで消えていないか確認
                text = self.race_events.get_skill_text(player) #, player.strategy) # 準備
                messages.append(text)
                player.used_in_current_lap = True
                logger.debug(f"Skill: {player.name}({player.strategy}). Text: {text}")

        # ラップ終了後の生存者チェック
        active_after_lap = self.get_active_players()
        if len(active_after_lap) == 2:
            self.next_lap_final_duel = True
            logger.info("Two players remaining. Next lap will be final duel.")

        return messages

    def process_final_duel(self) -> Tuple[List[str], str]:
        # (変更なし)
        duelists = self.get_active_players()
        if len(duelists) != 2: logger.error("Final duel with != 2 players."); return [], "エラー"
        player1, player2 = duelists
        battle_texts = self.race_events.get_random_final_battle_text(player1, player2)
        winner, loser = None, None
        favored_strategy = self.get_favored_strategy()
        p1_is_favored = player1.strategy == favored_strategy
        p2_is_favored = player2.strategy == favored_strategy
        if p1_is_favored == p2_is_favored: winner, loser = random.sample(duelists, 2)
        elif p1_is_favored: winner, loser = (player1, player2) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player2, player1)
        else: winner, loser = (player2, player1) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player1, player2)
        self.winner = winner; self.second_place = loser; self.game_finished = True
        logger.info(f"Final duel finished. Winner: {winner.name}({winner.strategy}), Second: {loser.name}({loser.strategy}). Favored: {favored_strategy}.")
        outcome_text = f"🏁🏁🏁 {winner.name}が{loser.name}との激闘の末、勝利を掴んだ！ 🏁🏁🏁"
        self._calculate_and_save_points()
        return battle_texts, outcome_text

    # --- ランダムイベント ---
    def process_revivals(self) -> Tuple[List[Player], List[str]]:
        # (変更なし)
        revived_players = []; messages = []
        if self.current_lap < 2: return [], []
        revival_chance = self._get_revival_chance(self.current_lap)
        eligible_for_revival = [p for p in self.players if p.eliminated and p not in self.eliminated_this_lap]
        for player in eligible_for_revival:
            if random.random() < revival_chance:
                self.revive_player(player); revived_players.append(player)
                messages.append(self.race_events.get_revival_text(player))
        if revived_players: logger.info(f"Revival: Players {', '.join([p.name for p in revived_players])} revived.")
        return revived_players, messages

    # ★★★ 強制脱落ロジック修正 ★★★
    def process_forced_elimination(self) -> Tuple[List[Player], List[str]]:
        """強制脱落イベント(確率変動式)。脱落者リストとメッセージリストを返す"""
        eliminated_players = []
        messages = []
        active_players = self.get_active_players()
        active_count = len(active_players)

        # 最低発生人数チェック
        if active_count < self.FORCED_ELIM_MIN_PLAYERS: return [], []

        # --- ★ 発生確率の計算 ---
        trigger_prob = max(0.0, min(self.FORCED_ELIM_MAX_CHANCE,
                                   self.FORCED_ELIM_BASE_CHANCE +
                                   self.FORCED_ELIM_CHANCE_PER_PLAYER * (active_count - self.FORCED_ELIM_MIN_PLAYERS)))
        logger.debug(f"Forced elimination check: Active={active_count}, Prob={trigger_prob:.2f}")

        # 発生判定
        if random.random() >= trigger_prob: # 確率未満なら発生しない
             return [], []
        # --- ★ 確率計算ここまで ---

        # 脱落させる人数を決定 (ロジックは変更なし)
        max_eliminations = min(6, active_count - 3)
        if max_eliminations < 2: return [], []
        num_eliminations = random.randint(2, max_eliminations)

        # 脱落者を選定
        eliminated_candidates = random.sample(active_players, num_eliminations)
        for player in eliminated_candidates:
            self.eliminate_player(player)
            eliminated_players.append(player)

        # メッセージ生成
        if eliminated_players:
            event_text, result_text = self.race_events.get_forced_elimination_text(eliminated_players)
            messages = [event_text, result_text]
            logger.info(f"Forced elimination triggered ({trigger_prob*100:.1f}% chance): {num_eliminations} players eliminated ({', '.join([p.name for p in eliminated_players])}).")

        return eliminated_players, messages

    def process_revolution(self) -> Tuple[bool, str, List[Player], List[Player]]:
        # (変更なし)
        if self.current_lap < 3: return False, "", [], []
        if random.random() >= 0.04: return False, "", [], []
        active_players = list(self.get_active_players()); eliminated_players = [p for p in self.players if p.eliminated]
        if len(active_players) < 4 or not eliminated_players: return False, "", [], []
        logger.info("Revolution event triggered!")
        demoted = list(active_players); promoted = list(eliminated_players)
        for player in demoted: self.eliminate_player(player)
        for player in promoted: self.revive_player(player)
        message = self.race_events.get_revolution_text()
        return True, message, demoted, promoted

    def process_great_comeback(self) -> Tuple[bool, str]:
        # (変更なし)
        if not self.final_duel: return False, ""
        if random.random() >= 0.04: return False, ""
        logger.info("Great Comeback event triggered!")
        eliminated_players = [p for p in self.players if p.eliminated]; final_duelists = list(self.get_active_players())
        if not eliminated_players or len(final_duelists) != 2: return False, ""
        comeback_player = random.choice(eliminated_players); loser1, loser2 = final_duelists
        self.revive_player(comeback_player); self.eliminate_player(loser1); self.eliminate_player(loser2)
        self.winner = comeback_player; self.second_place = None; self.game_finished = True; self.great_comeback_occurred = True
        self.great_comeback_winner = comeback_player; self.great_comeback_losers = final_duelists
        message = self.race_events.get_great_comeback_text(comeback_player, loser1, loser2)
        self._calculate_and_save_points()
        return True, message

    def check_game_end(self) -> bool:
        # (変更なし)
        if self.game_finished: return True
        active_players = self.get_active_players()
        if len(active_players) == 1:
            self.winner = active_players[0]
            if self.second_place is None: logger.warning(f"Game ended with one survivor ({self.winner.name}), but second place was not set.")
            self.game_finished = True; logger.info(f"Game ended normally. Winner: {self.winner.name}")
            self._calculate_and_save_points(); return True
        elif len(active_players) == 0:
             logger.warning("Game ended with zero active players."); self.game_finished = True
             self._calculate_and_save_points(); return True
        return False

    def get_lap_summary(self) -> Dict[str, str]:
        # (変更なし)
        active_count = len(self.get_active_players()); eliminated_names = [p.name for p in self.eliminated_this_lap]; revived_names = [p.name for p in self.revived_this_lap]
        summary = {"lap": str(self.current_lap), "survivors_count": str(active_count), "eliminated_names": ", ".join(eliminated_names) if eliminated_names else "なし"}
        if revived_names: summary["revived_names"] = ", ".join(revived_names)
        return summary

    def _calculate_and_save_points(self):
        # (変更なし)
        logger.info(f"Calculating points for guild {self.guild_id}...")
        if not self.guild_id: logger.error("Guild ID not set."); return
        try:
            with app.app_context():
                points_to_add: Dict[str, int] = {}
                if self.great_comeback_occurred and self.great_comeback_winner:
                    logger.info("Calculating points for Great Comeback.")
                    winner_id = f"CPU_{abs(self.great_comeback_winner.id)}" if self.great_comeback_winner.is_bot else str(self.great_comeback_winner.id)
                    points_to_add[winner_id] = WINNER_POINTS
                    for loser in self.great_comeback_losers:
                        loser_id = f"CPU_{abs(loser.id)}" if loser.is_bot else str(loser.id); points_to_add[loser_id] = GREAT_COMEBACK_SECOND_PLACE_POINTS
                elif self.winner:
                    logger.info("Calculating points for normal finish.")
                    winner_id = f"CPU_{abs(self.winner.id)}" if self.winner.is_bot else str(self.winner.id)
                    points_to_add[winner_id] = WINNER_POINTS
                    if self.second_place:
                        second_id = f"CPU_{abs(self.second_place.id)}" if self.second_place.is_bot else str(self.second_place.id)
                        points_to_add[second_id] = SECOND_PLACE_POINTS
                else: logger.info("Calculating points for no winner scenario.")
                for player in self.initial_players:
                     player_id_str = f"CPU_{abs(player.id)}" if player.is_bot else str(player.id)
                     if player_id_str not in points_to_add: points_to_add[player_id_str] = PARTICIPATION_POINTS
                logger.info(f"Points calculated: {points_to_add}")
                for discord_id, points in points_to_add.items():
                    try: PlayerPoints.add_points(discord_id, self.guild_id, points)
                    except Exception as db_err: logger.error(f"Failed to save points for {discord_id}: {db_err}", exc_info=True)
        except Exception as e: logger.error(f"Critical error in _calculate_and_save_points: {e}", exc_info=True)

    def _get_revival_chance(self, lap: int) -> float:
        # (変更なし)
        revival_chances = {2: 0.50, 3: 0.40, 4: 0.30, 5: 0.20, 6: 0.10, 7: 0.08, 8: 0.06, 9: 0.04}
        return revival_chances.get(lap, 0.02)