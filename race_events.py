import random
import logging
from typing import Dict, List, Tuple, Optional # Optional をインポート

logger = logging.getLogger(__name__)

class RaceCourse:
    def __init__(self) -> None:
        self.courses = {
            "HamCup World サーキット": "HamCupの世界観を余すところなく詰め込んだ『可愛いは正義』のサーキット🐹",
            "オズモニグリーン サーキット": "一面が緑のアフロに覆われた目に優しいサーキット🟢たまにホワイトアウトならぬグリーンアウトすることもあるとか？？",
            "むら&らーめんサーキット": "世界初！商店街を走り抜けるサーキット。その興奮はモナコどころではない！",
            "アイスサーキット": "コース全面が氷に覆われ雪が降り続くサーキット。寒くて滑るのはサーキットの置かれた環境のせい……のはず。",
            "アユカモサーキット": "滑ったら止まったり大荒れだったり、天候が不安定なサーキット。コースのポテンシャルは計り知れない。"
        }

    def get_random_course(self) -> Tuple[str, str]:
        """ランダムなコースとその説明を取得"""
        if not self.courses:
            logger.error("No courses defined in RaceCourse.")
            return "デフォルトコース", "説明なし"
        course_name = random.choice(list(self.courses.keys()))
        return course_name, self.courses[course_name]

class RaceEvents:
    def __init__(self) -> None:
        # ★追加: 作戦IDと表示用フレーズのマッピング
        self.strategy_descriptions: Dict[str, str] = {
            'start_dash': "序盤の混戦を抜け出すスタートダッシュ",
            'top_speed': "直線での最高速",
            'cornering': "テクニカルなコーナーリング"
            # 必要に応じて他の作戦も追加
        }

        self.events: Dict[str, List[str]] = {
            'overtake': [ # {winner} {loser}
                "⚡️ {winner}と{loser}が互いの意地をかけて激突！スパークを散らす激しい攻防！",
                "⭐️ {winner}のインベタ！{loser}が外側に弾き飛ばされる！", # 作戦名を削除し汎用的に
                "🎭 {winner}がフェイントで{loser}を欺く！見事なドライビングテクニック！",
                "🌪️ {winner}の気流を読んだ走り！{loser}の前に滑り込む！",
                "🎪 {winner}が魅せる超絶テクニック！{loser}は為す術なし！",
                "🎯 {winner}の絶妙なライン取り！{loser}の守りを崩す！",
                "🌠 {winner}が禁断の裏道を駆使！{loser}を置き去りに！",
                "⚔️ {winner}の真っ向勝負！{loser}との一騎打ちを制する！",
                "🎮 {winner}の神業的なドリフト！{loser}は抜かれるしかない！",
                "💫 {winner}が魅せる完璧なコーナリング！{loser}を一気に引き離す！",
                🚀 {winner}がロケットスタート！{loser}は出遅れる！

🍌 {loser}がバナナに滑った！その隙に{winner}が追い抜く！

⚡️ {loser}に雷直撃！{winner}がチャンスを逃さない！

🔥 {winner}がターボ全開！{loser}を一瞬で置き去りに！

🎲 アイテム運を味方に！{winner}が強アイテムで逆転！

🧊 {loser}が凍る！{winner}がスイスイ通過！

🌀 渦巻くトラップゾーン！{winner}が冷静に抜け、{loser}は翻弄される！

🎈 風船バトル勃発！{winner}が{loser}の風船を撃破！

🚧 {loser}が障害物に激突！{winner}はスムーズに駆け抜ける！

🏎️ {winner}がインから鮮やかに差し込む！{loser}は防げない！

🌟 無敵モード発動！{winner}が無双状態に！{loser}はなす術なし！

👻 ゴースト化した{winner}がすり抜けて奇襲成功！

🧹 {winner}がコースを完璧に掃除！{loser}はミス連発！

🛡️ {loser}の防御を破る一撃！{winner}が流れを引き寄せる！

🏹 狙い澄ました一矢！{winner}が的確に{loser}を打ち抜く！

🪄 魔法のような一手！{winner}が幻想的な走りで{loser}を惑わす！

🌋 {winner}の怒涛のアタック！{loser}、耐えきれるか！？

🛞 タイヤが唸る！{winner}のドリフトが火を吹く！

💥 {winner}と{loser}のスリップストリーム合戦！火花散る超接近戦！

🏴‍☠️ {winner}が海賊スタイルで荒々しく突撃！{loser}は翻弄される！
                # (以下、他のovertakeテキスト)
            ],
            'revolution': [ # 引数なし
                "あーーー！急に雷鳴が轟出した！\n空に何かがいるぞ！あれは！\n『キーーングボンビーーだーー！！！』\nキングボンビーが進行方向を変えてしまった！\n上位と下位がそっくり入れ替わったーーー！！！"
            ],
            'skill': [ # {player}
                 "🏎️ {player}がミニターボで加速！絶妙なタイミング！",
                 "💫 {player}がドリフトを駆使してコーナーを攻める！",
                 "⭐️ {player}がショートカットに成功！大きく時間を稼ぐ！",
                 "🌈 {player}が虹色のドリフトでブースト発動！",
                 "🎯 {player}がアイテムボックスを連続ゲット！",
                 "💨 {player}が空中でトリックを決めて加速！",
                 "🚀 {player}がジャンプ台で大きく飛んだ！", # 地名削除
                 "🌟 {player}が裏道を発見！秘密のルートを駆け抜ける！",
                 "🎪 {player}がスーパードリフトを披露！会場が沸く！",
                 "🌪️ {player}が神がかり的な走りを見せる！",
                 # (以下、他のskillテキスト)
            ],
            # final_battle は get_random_final_battle_text 内で定義
            'great_comeback': [ # {winner} {loser1} {loser2}
                "あーーー！！後ろからものすごい勢いで{winner}が猛追している！！\n"
                "そのまま{loser1}と{loser2}をぶち抜いたーーー！！\n"
                "奇跡の大逆転！！優勝は{winner}だーーーー！！！！"
            ],
            'revival': [ # {player}
                "💫 {player}が三連キノコを駆使して猛追！",
                "⚡️ {player}がブレットビルで一気に追い上げ！",
                "🌟 {player}がスーパースターで無敵状態！", # テキスト変更
                "🚀 {player}が裏道ショートカットを決めて大復活！",
                "⭐️ {player}が完璧なドリフトで一気に追い上げ！",
                "💨 {player}が虹色ターボを決めて猛追！",
                "🎯 {player}が絶妙なアイテム戦略で追い上げ！",
                "✨ {player}が奇跡のコース取りで復活！"
            ],
            'forced_elimination_listening': [ # 引数なし (結果は別テキスト)
                "⚡️ あーーっと！アユフマスペースが始まった！", # 固有名詞を伏せる
                "🌟 うーーーん！おおがねさんの配信が始まったようだ！",
                "💫 なんと！ゲリラでボイスチャンネルが立っている！",
                "🎯 緊急告知！これからHCCのギブアウェイが始まるらしい！",
                "⭐️ 聞き逃せない！かめさんのライブ配信だ！",
                "‼️ むら太組配信が始まってしまったーーーー！！",
                "‼️ HamCup本スぺの時間になってしまったーーーー！！",
                "‼️ オズモニ朝スぺ開始ーーーーー！！",
                "‼️ 伝説のルカの前々スペースが復活ーーーー！！",
                "‼️ ひっそりと、はんじょもラジオが始まっている！？",
                "‼️ トミーズレイディオで騒いでいるぞーーー！！",
            ],
            'forced_elimination_accident': [ # 引数なし (結果は別テキスト)
                "🔥 コース上に障害物！巨大な岩が転がってきた！",
                "😈 オイルが撒かれている！誰かの妨害工作か！？",
                "🚀 ミサイルが飛んできたーー！！危険だ！",
                "🏪 アイテムボックスと思ったらバナナの皮だった！",
                "🐢 緑コウラが壁に反射して襲いかかる！" # テキスト変更
            ]
        }
        self._used_event_texts: Dict[str, set] = {key: set() for key in self.events}

    # --- アナウンサーコメント生成 ---
    def get_announcer_comment(self, favored_strategy: Optional[str], course_name: str) -> str:
        """レース開始時のアナウンスコメントを生成する"""
        base_comments = [
            "さあ、解説の{announcer_name}さん、今日の『{course_name}』、注目ポイントはどこでしょう？",
            "今日の『{course_name}』、実況の私としては{strategy_desc}が鍵を握ると見ています！",
            "『{course_name}』の特性を考えると、今日は{strategy_desc}を重視したマシンが有利かもしれませんね！",
            "解説の{announcer_name}です。この『{course_name}』では、{strategy_desc}が一つのポイントになりそうです。",
        ]
        # アナウンサー名をランダムに選択 (例)
        announcers = ["AI１号", "AI２号", "ボット君"]
        comment_template = random.choice(base_comments)

        strategy_desc = "各レーサーの腕の見せ所" # デフォルト
        if favored_strategy and favored_strategy in self.strategy_descriptions:
            strategy_desc = self.strategy_descriptions[favored_strategy]

        return comment_template.format(
            announcer_name=random.choice(announcers),
            course_name=course_name,
            strategy_desc=strategy_desc
        )

    # --- 既存メソッド (一部引数追加) ---

    def _get_unused_event(self, event_type: str) -> str:
        """指定されたタイプの未使用のイベントテキストを取得"""
        # (変更なし)
        if event_type not in self.events or not self.events[event_type]:
             logger.warning(f"Event type '{event_type}' not found or has no texts.")
             return f"<{event_type} イベント発生>"
        available_events = [ event for event in self.events[event_type] if event not in self._used_event_texts.get(event_type, set()) ]
        if not available_events:
            logger.debug(f"All events of type '{event_type}' used. Resetting used set.")
            self._used_event_texts[event_type] = set()
            available_events = self.events[event_type]
            if not available_events:
                 logger.error(f"No events available for type '{event_type}' even after reset.")
                 return f"<{event_type} イベントエラー>"
        selected_event = random.choice(available_events)
        self._used_event_texts[event_type].add(selected_event)
        return selected_event

    def get_great_comeback_text(self, winner: 'Player', loser1: 'Player', loser2: 'Player') -> str:
        # (変更なし)
        if not self.events['great_comeback']: return "<大逆転発生>"
        event = self.events['great_comeback'][0]
        return event.format(winner=winner.name, loser1=loser1.name, loser2=loser2.name)

    def get_forced_elimination_text(self, eliminated_players: List['Player']) -> Tuple[str, str]:
        # (変更なし、固有名詞を少し修正)
        event_types = ['forced_elimination_listening', 'forced_elimination_accident']
        valid_event_types = [et for et in event_types if self.events.get(et)]
        if not valid_event_types:
             logger.error("No valid event types found for forced elimination.")
             return "<アクシデント発生>", f"{', '.join([p.name for p in eliminated_players])} が巻き込まれた！"
        event_type = random.choice(valid_event_types)
        event_text = self._get_unused_event(event_type)
        players_text = "、".join([p.name for p in eliminated_players])
        if event_type == 'forced_elimination_listening':
            result_text = f"{players_text}がそちらに気を取られてしまった！" # テキスト修正
        else:
            result_text = f"{players_text}がアクシデントに巻き込まれたーー！" # テキスト修正
        return event_text, result_text

    # ★引数追加: winner_strategy, was_advantageous
    def get_overtake_text(self, winner: 'Player', loser: 'Player',
                          winner_strategy: Optional[str] = None,
                          was_advantageous: bool = False) -> str:
        """オーバーテイクイベントのテキストを取得 (作戦情報を受け取る)"""
        base_text = self._get_unused_event('overtake')
        formatted_text = base_text.format(winner=winner.name, loser=loser.name)

        # ★ TODO: 作戦が有利だった場合にフレーバーテキストを追加するロジック
        # if was_advantageous and winner_strategy and winner_strategy in self.strategy_descriptions:
        #    advantage_phrases = [" 作戦が見事にハマった！", " これぞ作戦勝ち！", f" {self.strategy_descriptions[winner_strategy]}が光る！"]
        #    formatted_text += random.choice(advantage_phrases)

        return formatted_text # 現時点ではまだ追加テキストは実装しない

    # ★引数追加: player_strategy
    def get_skill_text(self, player: 'Player', player_strategy: Optional[str] = None) -> str:
        """スキルイベントのテキストを取得 (作戦情報を受け取る)"""
        base_text = self._get_unused_event('skill')
        formatted_text = base_text.format(player=player.name)

        # ★ TODO: 作戦に応じたフレーバーテキストを追加するロジック (任意)
        # if player_strategy and random.random() < 0.1: # たまに言及する程度？
        #     strategy_mention = [" 走りで作戦をアピール！", f" {self.strategy_descriptions.get(player_strategy, '')}を活かそうとしている！"]
        #     formatted_text += random.choice(strategy_mention)

        return formatted_text # 現時点ではまだ追加テキストは実装しない

    def get_revival_text(self, player: 'Player') -> str:
        # (変更なし)
        event = self._get_unused_event('revival')
        return event.format(player=player.name)

    def get_revolution_text(self) -> str:
        # (変更なし)
        if not self.events['revolution']: return "<革命発生>"
        event = self.events['revolution'][0]
        return event

    def get_random_final_battle_text(self, player1: 'Player', player2: 'Player') -> List[str]:
         # ★ 新しいテキスト候補リスト (約30個)
        battle_texts_pool = [
            f"最終コーナー！{player1.name}がインを取る！{player2.name}はアウトからクロスラインを狙うか！？",
            f"スリップストリームから{player2.name}が並びかけた！横一線！どちらも譲らない！",
            f"{player1.name}、渾身のドリフト！火花が散る！{player2.name}も食らいつく！",
            f"マシンが接触！{player1.name}と{player2.name}、わずかにバランスを崩すが立て直す！激しい！",
            f"{player2.name}、勝負をかけたイン強襲！{player1.name}はブロックできるか！？",
            f"最終ストレート！{player1.name}が一瞬前に出た！{player2.name}、最後の伸びはどうか！？",
            f"両者ほぼ同時！見た目ではわからない！勝負の行方はまだ見えない！",
            f"{player1.name}のタイヤが限界か！？マシンが小刻みに揺れる！{player2.name}が迫る！",
            f"{player2.name}、冷静なライン取り。じわじわと{player1.name}にプレッシャーをかける！",
            f"一瞬の隙をついた！{player1.name}が{player2.name}の前に滑り込んだ！見事な判断！",
            f"{player2.name}、アウト側のバンプに乗ったか！？少し挙動が乱れた！{player1.name}がリード！",
            f"ここでミニターボ！{player1.name}がわずかに加速！{player2.name}はついていけるか？",
            f"{player2.name}、レコードラインを外さない完璧な走り！{player1.name}も必死に追う！",
            f"息詰まるデッドヒート！{player1.name}と{player2.name}、どちらが先に仕掛けるか！？",
            f"{player1.name}、わずかにラインが膨らんだ！{player2.name}がその隙を見逃さない！",
            f"両ドライバー、全てのテクニックを出し尽くす！まさに意地と意地のぶつかり合い！",
            f"{player2.name}、マシン性能を引き出す走りで猛追！{player1.name}に迫る！",
            f"{player1.name}、ここ一番の集中力！ミスなく周回を重ねる！{player2.name}は崩せないか！",
            f"観客も総立ち！{player1.name}と{player2.name}の歴史に残る名勝負だ！",
            f"{player2.name}、最終ラップでファステストラップを更新する勢い！{player1.name}を捉えるか！",
            f"左右にマシンを振る{player1.name}！{player2.name}にスリップストリームを使わせない！",
            f"{player2.name}、一か八かのブレーキング勝負！{player1.name}のインを差した！",
            f"{player1.name}、クロスラインで抜き返す！読み合いがすごい！",
            f"シケインを抜ける！{player1.name}と{player2.name}の差はコンマ数秒！",
            f"{player2.name}、縁石ギリギリを攻めるアグレッシブな走り！{player1.name}にプレッシャー！",
            f"{player1.name}、冷静沈着。自分のペースを守り、{player2.name}の追撃を封じる構え。",
            f"ゴールラインが見えてきた！{player1.name}と{player2.name}、最後の力を振り絞る！",
            f"{player2.name}がアウトから並びかける！最後の直線、勝負はまだ分からない！",
            f"{player1.name}、わずかにリードを守ってフィニッシュラインへ向かう！逃げ切れるか！",
            f"{player2.name}、最後の最後で前に出たか！？ものすごいデッドヒート！"
        ]
        # ★ ここまで新しいリスト
        if len(battle_texts_pool) < 7:
            selected_texts = random.choices(battle_texts_pool, k=7)
        else:
             selected_texts = random.sample(battle_texts_pool, 7)
        final_text = f"🔥 残り100メートル！{player1.name}と{player2.name}の運命の瞬間！"
        selected_texts.append(final_text)
        return selected_texts
