# game_logic.py (2025-04-28 最終版)
import random
from typing import List, Optional, Set, Dict, Tuple
from models import PlayerPoints, PlayerPointHistory
from app import app, db
import logging
import math # 強制脱落の計算で使用
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
    """プレイヤー情報を保持するクラス"""
    def __init__(self, id: int, name: str, is_bot: bool = False):
        self.id = id
        self.name = name
        self.is_bot = is_bot
        self.is_active = True
        self.eliminated = False
        self.used_in_current_lap = False
        self.strategy: Optional[str] = None # 選択した作戦

    def __eq__(self, other):
        # 同一プレイヤーかどうかの比較用
        if not isinstance(other, Player): return NotImplemented
        return self.id == other.id

    def __hash__(self):
        # Setなどで使うためハッシュ可能にする
        return hash(self.id)

class GameState:
    """1レースのゲーム状態全体を管理するクラス"""
    # クラス変数として定数を定義
    STRATEGIES: List[str] = [STRATEGY_START_DASH, STRATEGY_TOP_SPEED, STRATEGY_CORNERING]
    STRATEGY_WIN_BONUS_RATE = 0.55 # 作戦ボーナス勝率 (55%)

    # 強制脱落イベントのパラメータ
    FORCED_ELIM_BASE_CHANCE = 0.0 # 5人未満の基本確率
    FORCED_ELIM_CHANCE_PER_PLAYER = 0.02 # 5人を超えた場合に1人あたり加算される確率
    FORCED_ELIM_MAX_CHANCE = 0.20 # ★最大確率 (20%) に変更
    FORCED_ELIM_MIN_PLAYERS = 5 # 最低発生人数
    FORCED_ELIM_PERCENTAGE = 0.15 # ★脱落させる割合 (15%)
    FORCED_ELIM_MIN_ABSOLUTE = 2 # ★最低でも脱落させる人数
    FORCED_ELIM_MIN_SURVIVORS = 3 # ★最低でも残す生存者数

    def __init__(self, guild_id: str, race_events: 'RaceEvents'):
        """ゲーム状態の初期化"""
        self.players: List[Player] = [] # 現在の全プレイヤーリスト
        self.race_started = False
        self.current_lap = 0
        self.final_duel = False # 一騎打ちモードか
        self.next_lap_final_duel = False # 次が最終ラップか
        self.winner: Optional[Player] = None # 優勝者
        self.second_place: Optional[Player] = None # 準優勝者
        self.eliminated_this_lap: List[Player] = [] # 現ラップ脱落者リスト
        self.revived_this_lap: List[Player] = [] # 現ラップ復活者リスト
        self.game_finished = False # ゲーム終了フラグ
        # 大逆転イベント用フラグと情報
        self.great_comeback_occurred = False
        self.great_comeback_winner: Optional[Player] = None
        self.great_comeback_losers: List[Player] = []

        self.guild_id: str = guild_id # サーバーID
        self.race_events: 'RaceEvents' = race_events # イベントテキスト生成用
        self.strategy_advantage: Dict[str, float] = self._calculate_strategy_advantage() # 今回の有利作戦確率

        self._initialize_cpu_players() # CPUプレイヤー生成
        # initial_players はポイント計算時の参加賞判定に使う
        self.initial_players: List[Player] = list(self.players) # 初期CPUリストをコピー

    def _calculate_strategy_advantage(self) -> Dict[str, float]:
        """今回のレースでの各作戦の有利度（確率）をランダムに計算"""
        num_strategies = len(self.STRATEGIES)
        if num_strategies == 0: return {}
        base_prob = 1.0 / num_strategies
        max_fluctuation = 0.05 # ±5%程度の変動
        probabilities = []
        current_sum = 0.0
        for i in range(num_strategies):
            if i < num_strategies - 1:
                fluctuation = random.uniform(-max_fluctuation, max_fluctuation)
                prob = base_prob + fluctuation
                probabilities.append(max(0.01, prob)) # 最低1%保証
                current_sum += probabilities[-1]
            else:
                last_prob = 1.0 - current_sum
                probabilities.append(max(0.01, last_prob)) # 最後の要素で合計1.0に調整
        # 正規化
        final_sum = sum(probabilities)
        normalized_probabilities = [p / final_sum for p in probabilities] if final_sum > 0 else [base_prob]*num_strategies
        advantage = dict(zip(self.STRATEGIES, normalized_probabilities))
        logger.info(f"Calculated strategy advantage: {advantage}")
        return advantage

    def get_favored_strategy(self) -> Optional[str]:
        """今回のレースで最も有利な作戦のIDを返す"""
        if not self.strategy_advantage: return None
        return max(self.strategy_advantage, key=self.strategy_advantage.get)

    def add_player(self, player: Player) -> bool:
        """人間プレイヤーをゲーム開始前に追加する"""
        if not player.is_bot and player not in self.players and not self.race_started:
            self.players.append(player)
            self.initial_players.append(player) # 参加賞判定用のリストにも追加
            logger.info(f"Player {player.name} (ID: {player.id}, Strategy: {player.strategy}) joined.")
            return True
        elif player in self.players: logger.warning(f"Player {player.name} already in game."); return False
        elif self.race_started: logger.warning(f"Race already started. Cannot add {player.name}."); return False
        return False

    # game_logic.py の GameState クラス内

    def _initialize_cpu_players(self, count: int = 7): # ★ デフォルトを 7 に戻す
        """CPUプレイヤーを指定された数だけ初期化してリストに追加 (デフォルト7人)"""
        # ★ 元の名前リストを復活
        cpu_names = [
            "イケハヤ", "road", "ROKU", "BUN", "かねりん", "ほんてぃ", "れんたろう"
        ]
        num_names = len(cpu_names)
        # ★ count と num_names の小さい方を採用するロジックも復活
        actual_count = min(count, num_names)
        if count > num_names:
            logger.warning(f"Requested {count} CPUs, but only {num_names} names available. Using {num_names}.")
        elif count < num_names:
             # もし count が 7 未満なら、リストからランダムに選ぶなどの処理も可能
             # ここでは単純にリストの先頭から count 人分を使う
             logger.info(f"Initializing {count} CPU players from the start of the name list.")
             actual_count = count # count を優先

        logger.info(f"Initializing {actual_count} CPU players...")
        # ★ リストから名前を取るようにループを修正
        for i in range(actual_count):
            cpu_name = cpu_names[i] # ★ リストから名前を取得
            cpu_player = Player(
                id=-(i + 1), # IDは負の連番
                name=cpu_name, # ★ リストの名前を使用
                is_bot=True
            )
            if self.STRATEGIES:
                 cpu_player.strategy = random.choice(self.STRATEGIES)
            else:
                 cpu_player.strategy = None

            self.players.append(cpu_player)
        logger.info(f"Initialized {actual_count} CPU players with random strategies.")
    # --- プレイヤーリスト取得系メソッド ---
    def get_player_count(self) -> int: return len([p for p in self.players if not p.is_bot])
    def get_human_players(self) -> List[Player]: return [p for p in self.players if not p.is_bot]
    def get_players(self) -> List[Player]: return list(self.players)
    def get_active_players(self) -> List[Player]: return [p for p in self.players if p.is_active and not p.eliminated]

    # --- プレイヤー状態変更メソッド ---
    def eliminate_player(self, player: Player):
        """指定プレイヤーを脱落状態にする"""
        target_player = next((p for p in self.players if p.id == player.id), None)
        if target_player and target_player.is_active:
            target_player.is_active = False
            target_player.eliminated = True
            if target_player not in self.eliminated_this_lap:
                self.eliminated_this_lap.append(target_player)
            # logger.info(f"Player {target_player.name} eliminated.") # 必要ならログ復活

    def revive_player(self, player: Player):
         """指定プレイヤーを復活状態にする"""
         target_player = next((p for p in self.players if p.id == player.id), None)
         if target_player and not target_player.is_active and target_player.eliminated:
              target_player.is_active = True
              target_player.eliminated = False
              target_player.used_in_current_lap = False
              if target_player not in self.revived_this_lap:
                  self.revived_this_lap.append(target_player)
              # logger.info(f"Player {target_player.name} revived.") # 必要ならログ復活

    def reset_lap_usage(self):
        """ラップ開始時に状態をリセット"""
        self.current_lap += 1
        self.eliminated_this_lap = []
        self.revived_this_lap = []
        for p in self.players: p.used_in_current_lap = False
        # 一騎打ちフラグ更新
        if self.next_lap_final_duel:
            active_players = self.get_active_players()
            if len(active_players) == 2:
                self.final_duel = True; self.next_lap_final_duel = False; logger.info("Entering final duel!")
            else: # 2人以外なら一騎打ちキャンセル
                logger.warning(f"Cancelling final duel. Active players: {len(active_players)} != 2"); self.next_lap_final_duel = False; self.final_duel = False

    # game_logic.py の GameState クラス内

    # ★★★ 戻り値の型ヒントを変更 ★★★
    def process_lap_pairwise(self) -> Tuple[List[str], List[str]]:
        """ペア対決方式(バトル数上限あり)でラップを処理し、
        追い抜きテキストリストとスキルテキストリストをタプルで返す"""
        # ★ リストを2つ用意
        overtake_messages = []
        skill_messages = []

        active_players = self.get_active_players()
        available_players = [p for p in active_players if not p.used_in_current_lap]
        num_available = len(available_players)

        if num_available < 2: # ペアを作れない場合
             for player in available_players:
                  if player.is_active:
                       text = self.race_events.get_skill_text(player)
                       skill_messages.append(text) # ★ スキルリストに追加
                       player.used_in_current_lap = True
                       logger.debug(f"Skill (no pairs possible): {player.name}. Text: {text}")
             active_after_lap = self.get_active_players()
             if len(active_after_lap) == 2: self.next_lap_final_duel = True
             return overtake_messages, skill_messages # ★ 2つのリストを返す

        # バトル数の計算
        battle_count_base = num_available
        num_battles = min(8, max(1, battle_count_base // 4))
        num_battles = min(num_battles, num_available // 2)
        logger.info(f"Lap {self.current_lap}: Available={num_available}, Num Battles Calculated={num_battles}")

        random.shuffle(available_players)
        paired_players_list = available_players[:num_battles * 2]
        single_players_list = available_players[num_battles * 2:]

        # ペア対決処理
        favored_strategy = self.get_favored_strategy()
        for i in range(0, len(paired_players_list), 2):
            player1, player2 = paired_players_list[i], paired_players_list[i+1]
            winner, loser = None, None
            # (勝敗判定ロジックは変更なし)
            p1_is_favored = player1.strategy == favored_strategy; p2_is_favored = player2.strategy == favored_strategy
            if p1_is_favored == p2_is_favored: winner, loser = random.sample([player1, player2], 2)
            elif p1_is_favored: winner, loser = (player1, player2) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player2, player1)
            else: winner, loser = (player2, player1) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player1, player2)
            was_advantageous = (winner.strategy == favored_strategy) and (loser.strategy != favored_strategy)

            text = self.race_events.get_overtake_text(winner, loser)
            overtake_messages.append(text) # ★ 追い抜きリストに追加
            self.eliminate_player(loser)
            player1.used_in_current_lap = True; player2.used_in_current_lap = True
            logger.debug(f"Overtake: W:{winner.name}({winner.strategy}) vs L:{loser.name}({loser.strategy}). Fav:{favored_strategy}. WinAdv:{was_advantageous}.")

        # シングルプレイヤー処理 (スキルイベント)
        for player in single_players_list:
            if player.is_active:
                text = self.race_events.get_skill_text(player)
                skill_messages.append(text) # ★ スキルリストに追加
                player.used_in_current_lap = True
                logger.debug(f"Skill: {player.name}({player.strategy}). Text: {text}")

        # ラップ終了後の生存者チェック
        active_after_lap = self.get_active_players()
        if len(active_after_lap) == 2: self.next_lap_final_duel = True; logger.info("Two players remaining.")

        # ★ 2つのリストをタプルで返す
        return overtake_messages, skill_messages

    def process_final_duel(self) -> Tuple[List[str], str]:
        """最終決戦（大逆転チェック含む）"""
        # 大逆転チェックを先に行う
        gc_happened, gc_message = self.process_great_comeback()
        if gc_happened: return [], gc_message # 大逆転発生時は専用メッセージのみ返す

        # 通常のデュエル処理
        duelists = self.get_active_players()
        if len(duelists) != 2:
            logger.error(f"Final duel error: Expected 2 players, got {len(duelists)}")
            self.game_finished = True # エラーでもゲームは終了
            return [], "エラー：最終決戦のプレイヤー数が不正です。ゲームを終了します。"

        player1, player2 = duelists
        battle_texts = self.race_events.get_random_final_battle_text(player1, player2)
        # 作戦ボーナス込みで勝敗決定
        winner, loser = None, None
        favored_strategy = self.get_favored_strategy(); p1_is_favored = player1.strategy == favored_strategy; p2_is_favored = player2.strategy == favored_strategy
        if p1_is_favored == p2_is_favored: winner, loser = random.sample(duelists, 2)
        elif p1_is_favored: winner, loser = (player1, player2) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player2, player1)
        else: winner, loser = (player2, player1) if random.random() < self.STRATEGY_WIN_BONUS_RATE else (player1, player2)

        self.winner = winner; self.second_place = loser; self.game_finished = True
        logger.info(f"Final duel finished. W:{winner.name}({winner.strategy}), L:{loser.name}({loser.strategy}). Fav:{favored_strategy}.")
        outcome_text = f"🏁🏁🏁 {winner.name}が{loser.name}との激闘の末、勝利を掴んだ！ 🏁🏁🏁"
        # ポイント計算は check_game_end 経由で呼ばれる
        return battle_texts, outcome_text

    # --- 他のクラス変数と共に定義 ---
    MAX_REVIVALS_PER_LAP = 5 # ★ 1ラップあたりの最大復活人数

    def process_revivals(self) -> Tuple[List[Player], List[str]]:
        """復活処理 (★最大復活人数を5人に制限)"""
        revived_players = []; messages = []
        # 特定ラップ以降は発生しない処理 (もし不要ならこのブロック削除)
        REVIVAL_CUTOFF_LAP = 999 # 実質無効化 (以前の案から変更する場合)
        # REVIVAL_CUTOFF_LAP = 15 # Lap 15で打ち切る場合
        if self.current_lap >= REVIVAL_CUTOFF_LAP:
            logger.debug(f"Lap {self.current_lap}: Revival check skipped (>= Lap {REVIVAL_CUTOFF_LAP}).")
            return [], []

        if self.current_lap < 2: return [], [] # Lap 1 は発生しない

        revival_chance = self._get_revival_chance(self.current_lap) # 確率は変更済み (Lap10-15: 0.5%, Lap16+: 0.2%)
        eligible_for_revival = [p for p in self.players if p.eliminated and p not in self.eliminated_this_lap]

        # ★ 追加: このラップで復活した人数をカウント
        revived_count_this_lap = 0

        # 復活判定ループ
        for player in eligible_for_revival:
            # ★ 追加: 既に上限に達していたらループを抜ける
            if revived_count_this_lap >= self.MAX_REVIVALS_PER_LAP:
                logger.debug(f"Revival limit ({self.MAX_REVIVALS_PER_LAP}) reached for Lap {self.current_lap}.")
                break # このラップでの復活処理を打ち切り

            # 確率判定
            if random.random() < revival_chance:
                self.revive_player(player)
                revived_players.append(player)
                messages.append(self.race_events.get_revival_text(player))
                revived_count_this_lap += 1 # ★ カウントを増やす

        if revived_players:
            logger.info(f"Revival ({revival_chance*100:.1f}%): {len(revived_players)} players revived (Limit: {self.MAX_REVIVALS_PER_LAP}).")
        return revived_players, messages

    def _get_revival_chance(self, lap: int) -> float:
        """復活確率を取得 (Lap10-15は0.5%, Lap16以降は0.2%)"""
        # (このメソッドは前回修正した内容のまま)
        revival_chances = {
            2: 0.50, 3: 0.40, 4: 0.30, 5: 0.20,
            6: 0.10, 7: 0.08, 8: 0.06, 9: 0.04
        }
        if lap < 10:
            return revival_chances.get(lap, 0.02 if lap >= 2 else 0.0)
        elif lap <= 15:
            return 0.005 # 0.5%
        else:
            return 0.002 # 0.2%

    def process_forced_elimination(self) -> Tuple[List[Player], List[str]]:
        """強制脱落イベント(確率変動式, 割合脱落)"""
        eliminated_players = []; messages = []
        active_players = self.get_active_players(); active_count = len(active_players)
        if active_count < self.FORCED_ELIM_MIN_PLAYERS: return [], []

        # 発生確率計算 (上限20%に更新済み)
        trigger_prob = max(0.0, min(self.FORCED_ELIM_MAX_CHANCE, self.FORCED_ELIM_BASE_CHANCE + self.FORCED_ELIM_CHANCE_PER_PLAYER * (active_count - self.FORCED_ELIM_MIN_PLAYERS)))
        logger.debug(f"FE check: Active={active_count}, Prob={trigger_prob:.3f}")
        if random.random() >= trigger_prob: return [], [] # 発生せず

        # 脱落人数計算 (割合ベースに修正済み)
        target_elim = math.floor(active_count * self.FORCED_ELIM_PERCENTAGE)
        target_elim = max(self.FORCED_ELIM_MIN_ABSOLUTE, target_elim)
        max_possible_elim = active_count - self.FORCED_ELIM_MIN_SURVIVORS
        num_eliminations = min(target_elim, max_possible_elim)

        if num_eliminations < self.FORCED_ELIM_MIN_ABSOLUTE:
             logger.warning(f"FE calc result ({num_eliminations}) < min ({self.FORCED_ELIM_MIN_ABSOLUTE}). Cancelling."); return [], []

        # 脱落者選定と実行
        eliminated_candidates = random.sample(active_players, num_eliminations)
        for player in eliminated_candidates: self.eliminate_player(player); eliminated_players.append(player)

        # メッセージ生成
        if eliminated_players:
            event_text, result_text = self.race_events.get_forced_elimination_text(eliminated_players)
            messages = [event_text, result_text]
            logger.info(f"FE triggered ({trigger_prob*100:.1f}%): {num_eliminations} players elim ({', '.join([p.name for p in eliminated_players])}).")
        return eliminated_players, messages

    def process_revolution(self) -> Tuple[bool, str, List[Player], List[Player]]:
        """革命イベント"""
        # ループ内ログはコメントアウト済み
        if self.current_lap < 3: return False, "", [], []
        if random.random() >= 0.04: return False, "", [], []
        active_players = list(self.get_active_players()); eliminated_players = [p for p in self.players if p.eliminated]
        if len(active_players) < 4 or not eliminated_players: return False, "", [], []
        logger.info("Revolution event triggered!")
        demoted = list(active_players); promoted = list(eliminated_players)
        for player in demoted: self.eliminate_player(player) # loggerなし
        for player in promoted: self.revive_player(player) # loggerなし
        message = self.race_events.get_revolution_text()
        return True, message, demoted, promoted

    def process_great_comeback(self) -> Tuple[bool, str]:
        """大逆転イベント"""
        # ポイント計算呼び出し削除済み
        if not self.final_duel: return False, ""
        if random.random() >= 0.05: return False, "" # 5%確率
        logger.info("Great Comeback event triggered!")
        eliminated_players = [p for p in self.players if p.eliminated]; final_duelists = list(self.get_active_players())
        if not eliminated_players or len(final_duelists) != 2: logger.warning("GC condition not met."); return False, ""
        comeback_player = random.choice(eliminated_players); loser1, loser2 = final_duelists
        self.revive_player(comeback_player); self.eliminate_player(loser1); self.eliminate_player(loser2)
        self.winner = comeback_player; self.second_place = None; self.game_finished = True; self.great_comeback_occurred = True
        self.great_comeback_winner = comeback_player; self.great_comeback_losers = final_duelists
        message = self.race_events.get_great_comeback_text(comeback_player, loser1, loser2)
        return True, message

    def check_game_end(self) -> bool:
        """ゲーム終了条件をチェックし、終了ならポイント計算を実行"""
        if self.game_finished: return True
        active_players = self.get_active_players()
        game_ended_now = False
        if len(active_players) == 1: # 正常終了
            self.winner = active_players[0]
            if self.second_place is None: logger.warning(f"Game end: 1 survivor ({self.winner.name}), 2nd not set.")
            self.game_finished = True; game_ended_now = True; logger.info(f"Game ended normally. Winner: {self.winner.name}")
        elif len(active_players) == 0: # 異常終了？
             logger.warning("Game ended with zero active players.")
             self.game_finished = True; game_ended_now = True
        # ゲームがこのチェックで終了した場合のみポイント計算
        if game_ended_now: self._calculate_and_save_points()
        return game_ended_now

    def get_lap_summary(self) -> Dict[str, str]:
        """ラップサマリー用データを返す (★生存者5人以下なら名前も返す)"""
        active_players = self.get_active_players() # ★先にアクティブプレイヤーを取得
        active_count = len(active_players)
        eliminated_names = [p.name for p in self.eliminated_this_lap]
        revived_names = [p.name for p in self.revived_this_lap]

        summary = {
            "lap": str(self.current_lap),
            "survivors_count": str(active_count),
            "eliminated_names": ", ".join(eliminated_names) if eliminated_names else "なし",
        }
        if revived_names:
            summary["revived_names"] = ", ".join(revived_names)

        # ★ 追加: 生存者が5人以下なら名前のリストを追加
        if active_count <= 5 and active_count > 0: # 0人の場合は不要
            summary["survivor_names"] = [p.name for p in active_players]

        return summary

    def _calculate_and_save_points(self):
        """ポイント計算とDB保存"""
        # 内部ロジックは変更なし
        logger.info(f"Calculating points for guild {self.guild_id}...")
        if not self.guild_id: logger.error("Guild ID not set."); return
        try:
            with app.app_context():
                points_to_add: Dict[str, int] = {}
                # 大逆転シナリオ
                if self.great_comeback_occurred and self.great_comeback_winner:
                    logger.info("Calculating points for Great Comeback.")
                    winner_id = f"CPU_{abs(self.great_comeback_winner.id)}" if self.great_comeback_winner.is_bot else str(self.great_comeback_winner.id); points_to_add[winner_id] = WINNER_POINTS
                    for loser in self.great_comeback_losers: loser_id = f"CPU_{abs(loser.id)}" if loser.is_bot else str(loser.id); points_to_add[loser_id] = GREAT_COMEBACK_SECOND_PLACE_POINTS
                # 通常終了シナリオ
                elif self.winner:
                    logger.info("Calculating points for normal finish.")
                    winner_id = f"CPU_{abs(self.winner.id)}" if self.winner.is_bot else str(self.winner.id); points_to_add[winner_id] = WINNER_POINTS
                    if self.second_place: second_id = f"CPU_{abs(self.second_place.id)}" if self.second_place.is_bot else str(self.second_place.id); points_to_add[second_id] = SECOND_PLACE_POINTS
                # 勝者なしシナリオ
                else: logger.info("Calculating points for no winner scenario.")
                # 参加ポイント付与
                for player in self.initial_players:
                     player_id_str = f"CPU_{abs(player.id)}" if player.is_bot else str(player.id)
                     if player_id_str not in points_to_add: points_to_add[player_id_str] = PARTICIPATION_POINTS
                # DB保存実行
                logger.info(f"Points calculated: {points_to_add}")
                for discord_id, points in points_to_add.items():
                    try: PlayerPoints.add_points(discord_id, self.guild_id, points)
                    except Exception as db_err: logger.error(f"Failed to save points for {discord_id}: {db_err}", exc_info=True)
        except Exception as e: logger.error(f"Critical error in _calculate_and_save_points: {e}", exc_info=True)

    # game_logic.py の GameState クラス内

    def _get_revival_chance(self, lap: int) -> float:
        """復活確率を取得 (★Lap10-15は0.5%, Lap16以降は0.2%に変更)"""
        revival_chances = {
            2: 0.50, 3: 0.40, 4: 0.30, 5: 0.20,
            6: 0.10, 7: 0.08, 8: 0.06, 9: 0.04
        }
        # ★ 段階的な最低確率を設定
        if lap < 10:
            # Lap 9までは辞書の値を使い、なければ 0.02 (2%) ※Lap 1は対象外
            return revival_chances.get(lap, 0.02 if lap >= 2 else 0.0)
        elif lap <= 15:
            # Lap 10 から 15 までは 0.005 (0.5%)
            return 0.005
        else:
            # Lap 16 以降は 0.002 (0.2%)
            return 0.002
