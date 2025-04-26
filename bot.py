import os
import discord
from discord.ext import commands
import asyncio
import logging
import random
from dotenv import load_dotenv
from typing import Dict, Optional # Optional をインポート

# UI部品をインポート
from discord import Interaction, ButtonStyle
from discord.ui import View, Button

# 修正: 正しい場所からインポート
from app import app, db # FlaskアプリとDBオブジェクト
from game_logic import GameState, Player, STRATEGY_START_DASH, STRATEGY_TOP_SPEED, STRATEGY_CORNERING # 作戦定数もインポート
from race_events import RaceEvents, RaceCourse # イベントテキストとコース
from models import PlayerPoints, PlayerPointHistory # DBモデル

# ロギング設定 (bot.py 用)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# .envファイルから環境変数を読み込む
load_dotenv()

# トークンの取得
token = os.getenv('DISCORD_TOKEN')
if not token:
    logger.critical("Discord token not found! Please set the DISCORD_TOKEN environment variable.")
    exit(1)

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
# intents.members = True # 必要なら有効化
bot = commands.Bot(command_prefix='!', intents=intents)

# 進行中のゲームをチャンネルIDごとに管理する辞書
games: Dict[int, GameState] = {}

# --- CPU名解決ヘルパー ---
CPU_NAMES_LOOKUP = {
    f"CPU_{i+1}": name
    for i, name in enumerate([
        "イケハヤ", "road", "ROKU", "BUN", "HYDE", "デーモン小暮", "れんたろう"
    ])
}

# --- Botイベントハンドラ ---
@bot.event
async def on_ready():
    """Bot起動時の処理"""
    try:
        logger.info(f'Bot is ready! Logged in as {bot.user.name} (ID: {bot.user.id})')
        logger.info(f'Using discord.py version {discord.__version__}')
        logger.info(f'Connected to {len(bot.guilds)} guilds')
        try:
            with app.app_context():
                from sqlalchemy import text
                db.session.execute(text('SELECT 1'))
            logger.info("Database connection test successful on_ready.")
        except Exception as e:
            logger.error(f"Database connection test failed on_ready: {e}", exc_info=True)
            # await bot.close() # DB接続必須なら終了
        logger.info("Bot is online and ready!")
    except Exception as e:
        logger.error(f"Error in on_ready: {e}", exc_info=True)

# (他の on_disconnect, on_resume, on_error, on_guild_join は省略)
@bot.event
async def on_disconnect():
    logger.warning("Bot disconnected from Discord.")

@bot.event
async def on_resume():
    logger.info("Bot resumed connection with Discord.")

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Unhandled error in event {event}:", exc_info=True)

@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f'Joined new guild: {guild.name} (ID: {guild.id})')


# --- ゲーム進行ロジック ---
async def run_race_simulation(ctx: commands.Context, game: GameState, course_name: str): # course_name を引数に追加
    """レースのシミュレーションを実行し、Discordに状況を送信する"""
    channel = ctx.channel
    logger.info(f"Starting race simulation in channel {channel.id} (Guild: {game.guild_id})")

    try:
        # 0. コース発表 (run_race_simulation の呼び出し元で行うように変更しても良い)
        # await channel.send(f"🏁 レース開始！今回のコースは『**{course_name}**』！\n*{course_description}*")
        # await asyncio.sleep(3)

        # ★追加: アナウンサーコメント
        favored_strategy = game.get_favored_strategy()
        announcer_comment = game.race_events.get_announcer_comment(favored_strategy, course_name)
        await channel.send(f"🎤 **アナウンス**\n{announcer_comment}")
        await asyncio.sleep(3)

        # 1. メインループ (ゲーム終了まで)
        while not game.check_game_end():
            # 1.1 ラップ開始処理
            game.reset_lap_usage()
            current_lap = game.current_lap
            await channel.send(f"\n━━━━━━━━━━━━━━━━━━━━━\n**📢 LAP {current_lap}!**\n━━━━━━━━━━━━━━━━━━━━━")
            await asyncio.sleep(2)

            # 1.2 イベントフェーズ
            logger.debug(f"Lap {current_lap}: Starting event phase.")
            # (革命)
            rev_happened, rev_msg, _, _ = game.process_revolution()
            if rev_happened:
                await channel.send(f"🚨 **革命発生！** 🚨\n{rev_msg}")
                await asyncio.sleep(3)
                if game.check_game_end(): break
            # (復活)
            revived_players, revival_msgs = game.process_revivals()
            if revival_msgs:
                 await channel.send("✨ **復活チャンス！** ✨") # <- この行
                 for msg in revival_msgs:
                     await channel.send(msg)
                     await asyncio.sleep(1.5)
            # (強制脱落)
            eliminated_players, forced_elim_msgs = game.process_forced_elimination()
            if forced_elim_msgs:
                await channel.send("💥 **アクシデント発生！** 💥")
                await channel.send(forced_elim_msgs[0]); await asyncio.sleep(1)
                await channel.send(forced_elim_msgs[1]); await asyncio.sleep(2)
                if game.check_game_end(): break
            # (大逆転)
            comeback_happened, comeback_msg = game.process_great_comeback()
            if comeback_happened:
                 await channel.send("🎉 **奇跡発生！大逆転！** 🎉"); await channel.send(comeback_msg); await asyncio.sleep(3)
                 break # ゲーム終了

            # 1.3 アクションフェーズ
            logger.debug(f"Lap {current_lap}: Starting action phase.")
            if game.game_finished: break

            if game.final_duel:
                logger.info(f"Lap {current_lap}: Processing final duel.")
                battle_msgs, outcome_msg = game.process_final_duel()
                await channel.send("\n🔥 **最終決戦！一騎打ち！** 🔥"); await asyncio.sleep(1)
                for msg in battle_msgs: await channel.send(msg); await asyncio.sleep(2.5)
                await asyncio.sleep(1); await channel.send(f"\n**{outcome_msg}**")
                break
            else:
                logger.debug(f"Lap {current_lap}: Processing pairwise lap.")
                lap_messages = game.process_lap_pairwise()
                if not lap_messages: await channel.send("🌀 静かなラップ...波乱は起きなかったようだ。"); await asyncio.sleep(1.5)
                else:
                    for msg in lap_messages: await channel.send(msg); await asyncio.sleep(2)

           # 1.4 サマリーフェーズ
            logger.debug(f"Lap {current_lap}: Starting summary phase.")
            if game.game_finished: break

            summary = game.get_lap_summary()
            # ★ 表示名を変更
            summary_msg = (
                f"\n📊 **LAP {current_lap} 結果**\n"
                f" > トップグループ: {summary['survivors_count']}台\n" # 「生存」を「トップグループ」に
                f" > 下位グループ: {summary['eliminated_names']}"    # 「脱落」を「下位グループ」に
            )
            if 'revived_names' in summary:
                 summary_msg += f"\n > 追い上げ: {summary['revived_names']}" # 「復活」を「追い上げ」に
            await channel.send(summary_msg)
            await asyncio.sleep(3)

            if game.check_game_end(): logger.info(f"Game ended after lap {current_lap} summary."); break

        # 2. ループ終了後 (ゲーム終了)
        logger.info(f"Race simulation finished for channel {channel.id}.")
        if game.winner and not game.great_comeback_occurred and not game.final_duel:
             await channel.send(f"\n🏆🏆🏆 **レース終了！ 優勝者は {game.winner.name} です！おめでとう！** 🏆🏆🏆")
        elif not game.winner and game.game_finished:
             await channel.send("\n🏁 レース終了！今回は勝者なしとなりました...！")

    except asyncio.CancelledError:
         logger.warning(f"Race simulation task cancelled for channel {channel.id}")
         await channel.send("⚠️ レースシミュレーションがキャンセルされました。")
    except Exception as e:
        logger.error(f"Error during race simulation in channel {channel.id}: {e}", exc_info=True)
        await channel.send("レースの進行中に予期せぬエラーが発生しました。レースを中断します。")
    finally:
         if channel.id in games: del games[channel.id]; logger.info(f"Removed game state for channel {channel.id}")


# --- Botコマンド ---
@bot.command(name='start') # コマンド名
@commands.guild_only()
async def start_race_command(ctx: commands.Context):
    """レースを開始します。"""
    channel_id = ctx.channel.id
    guild_id = str(ctx.guild.id)
    author = ctx.author
    logger.info(f"'start' command received from {author.name} in channel {channel_id} (Guild: {guild_id})")

    if channel_id in games:
        await ctx.send("このチャンネルでは既にレースが進行中です！🏁", ephemeral=True) # 本人のみに通知
        return

    # ★ GameState と RaceEvents を先に生成
    race_events = RaceEvents()
    game_state = GameState(guild_id=guild_id, race_events=race_events)
    games[channel_id] = game_state
    logger.info(f"New game created for channel {channel_id}.")

    # コース情報を先に取得
    race_course = RaceCourse()
    course_name, course_description = race_course.get_random_course()


    # --- ★ 参加ボタンとビューの作成 (作戦選択式) ---
    WAIT_TIME = 60.0 # 待機時間（秒）

    view = View(timeout=WAIT_TIME)

    # ボタンの定義
    button_start_dash = Button(style=ButtonStyle.primary, emoji="🚀", label="参加(スタート重視)", custom_id=f"join_{STRATEGY_START_DASH}")
    button_top_speed = Button(style=ButtonStyle.success, emoji="💨", label="参加(速度重視)", custom_id=f"join_{STRATEGY_TOP_SPEED}")
    button_cornering = Button(style=ButtonStyle.secondary, emoji="✨", label="参加(コーナー重視)", custom_id=f"join_{STRATEGY_CORNERING}")

    async def join_callback(interaction: Interaction):
        """参加ボタンが押されたときの処理"""
        if not interaction.channel_id:
             await interaction.response.send_message("エラー：チャンネル情報が取得できませんでした。", ephemeral=True); return
        if interaction.channel_id not in games:
             await interaction.response.send_message("現在、参加可能なレースはありません。", ephemeral=True); return

        current_game = games[interaction.channel_id]
        user = interaction.user

        if current_game.race_started:
            await interaction.response.send_message("レースは既に開始されています！", ephemeral=True); return

        # custom_id から作戦を決定
        strategy = None
        if interaction.data and 'custom_id' in interaction.data:
             custom_id = interaction.data['custom_id']
             if custom_id == f"join_{STRATEGY_START_DASH}": strategy = STRATEGY_START_DASH
             elif custom_id == f"join_{STRATEGY_TOP_SPEED}": strategy = STRATEGY_TOP_SPEED
             elif custom_id == f"join_{STRATEGY_CORNERING}": strategy = STRATEGY_CORNERING

        if not strategy:
             logger.warning(f"Could not determine strategy from custom_id: {interaction.data.get('custom_id')}")
             await interaction.response.send_message("作戦の選択でエラーが発生しました。", ephemeral=True); return

        # プレイヤー作成・追加
        player = Player(user.id, user.display_name, is_bot=False)
        player.strategy = strategy # ★ 作戦を設定

        if current_game.add_player(player):
            player_count = current_game.get_player_count()
            strategy_map = {STRATEGY_START_DASH: "スタート重視", STRATEGY_TOP_SPEED: "速度重視", STRATEGY_CORNERING: "コーナー重視"}
            strategy_name = strategy_map.get(strategy, "不明な作戦")

            # 参加通知 (一時メッセージ)
            join_notify_embed = discord.Embed(
                 description=f"{user.display_name} が **{strategy_name}** でレースに参加しました！",
                 color=discord.Color.green()
            )
            await interaction.channel.send(embed=join_notify_embed, delete_after=10.0)

            # 募集メッセージの更新
            if interaction.message:
                 try:
                      embed = interaction.message.embeds[0]
                      embed.description = (
                           f"参加作戦を選んでボタンを押してください！\n"
                           f"**約{int(WAIT_TIME)}秒後**にレースが開始されます！\n"
                           f"現在の参加者数: {player_count}人 (CPU除く)"
                      )
                      await interaction.message.edit(embed=embed, view=view)
                      await interaction.response.defer() # 応答（必須）
                 except Exception as e:
                      logger.error(f"Error editing join message: {e}", exc_info=True)
                      await interaction.response.defer() # エラーでも応答
            else:
                 await interaction.response.defer()
        else:
            await interaction.response.send_message("既に参加済みか、レースが開始されています。", ephemeral=True)

    # ボタンにコールバックを設定し、ビューに追加
    button_start_dash.callback = join_callback
    button_top_speed.callback = join_callback
    button_cornering.callback = join_callback
    view.add_item(button_start_dash)
    view.add_item(button_top_speed)
    view.add_item(button_cornering)

    # --- 募集開始メッセージ ---
    initial_embed = discord.Embed(
        title=f"🏎️ カートランブル@{course_name}", # コース名を表示
        description=(
            f"参加作戦を選んでボタンを押してください！\n"
            f"**約{int(WAIT_TIME)}秒後**にレースが開始されます！\n"
            f"現在の参加者数: 0人 (CPU除く)\n\n"
            f"*コース: {course_description}*" # コース説明も追加
        ),
        color=discord.Color.blue()
    )
    # メッセージを送信し、後で編集できるように Message オブジェクトを保存
    sent_message = await ctx.send(embed=initial_embed, view=view)
    # view に message を紐付ける (タイムアウト処理で使うため)
    view.message = sent_message
    logger.info(f"Join message sent to channel {channel_id}. Waiting {WAIT_TIME} seconds...")

    # --- 待機 ---
    await asyncio.sleep(WAIT_TIME)

    # --- 待機終了後 ---
    if channel_id not in games:
         logger.info(f"Game for channel {channel_id} was removed before starting."); return
    game_to_start = games[channel_id]
    if game_to_start.race_started: # 他のプロセスで開始された場合など
         logger.warning(f"Race in {channel_id} already marked as started. Aborting duplicate start process."); return

    # ボタンを無効化
    try:
        # view に紐付けた message を使う
        if view.message:
              view.stop()
              disabled_embed = view.message.embeds[0]
              disabled_embed.description = "参加受付は終了しました。レースを開始します！"
              disabled_embed.color = discord.Color.red()
              await view.message.edit(embed=disabled_embed, view=None)
        else:
             logger.warning("Could not find the original message to disable buttons via view.")
    except Exception as e:
        logger.error(f"Error disabling join button view: {e}", exc_info=True)

    human_players = game_to_start.get_human_players()
    if not human_players:
        await ctx.send("参加者が集まらなかったため、レースは中止となりました。")
        logger.info(f"Race cancelled in channel {channel_id} due to no participants.")
        if channel_id in games: del games[channel_id]
        return

    game_to_start.race_started = True
    logger.info(f"Starting race in channel {channel_id} with {len(human_players)} human players.")

    # ★ コース名を渡してレースシミュレーションを実行
    await run_race_simulation(ctx, game_to_start, course_name)


# --- ランキングコマンド (変更なし、CPU名解決は bot.py 内のヘルパー使用) ---
@bot.command(name='ranking')
@commands.guild_only()
async def show_rankings(ctx: commands.Context):
    """週間・月間・全期間のランキングを表示します。"""
    guild_id = str(ctx.guild.id)
    logger.info(f"'ranking' command received from {ctx.author.name} in guild {guild_id}")
    embed = discord.Embed(title=f"🏆 {ctx.guild.name} ランキング 🏆", color=discord.Color.gold())
    periods = {'weekly': '📅 週間', 'monthly': '🗓️ 月間', 'all': '👑 累計'}
    rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}
    try:
        with app.app_context():
            for period, title_prefix in periods.items():
                rankings_data = PlayerPoints.get_rankings(guild_id=guild_id, period=period, limit=5)
                ranking_text = ""
                if not rankings_data: ranking_text = "まだデータがありません"
                else:
                    for i, (discord_id_str, points) in enumerate(rankings_data, 1):
                        rank_emoji = rank_emojis.get(i, f"{i}.")
                        try:
                            if discord_id_str.startswith("CPU_"):
                                username = CPU_NAMES_LOOKUP.get(discord_id_str, discord_id_str) # CPU名解決
                            else:
                                user = await bot.fetch_user(int(discord_id_str))
                                username = user.display_name if user else f"不明なUser({discord_id_str})"
                        except ValueError: username = f"不正なID({discord_id_str})"
                        except discord.NotFound: username = f"見つからないUser({discord_id_str})"
                        except Exception as e: logger.error(f"Error fetching user {discord_id_str} for ranking: {e}"); username = f"エラー({discord_id_str})"
                        ranking_text += f"{rank_emoji} {username}: {points} ポイント\n"
                embed.add_field(name=f"{title_prefix}ランキング (Top 5)", value=ranking_text, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Error fetching or displaying rankings for guild {guild_id}: {e}", exc_info=True)
        await ctx.send("ランキングの取得中にエラーが発生しました。")

# --- ランキングリセットコマンド (変更なし) ---
@bot.command(name='reset_ranking')
@commands.has_permissions(administrator=True)
@commands.guild_only()
async def reset_ranking(ctx: commands.Context):
    """このサーバーのランキングデータを全てリセットします（管理者のみ）。"""
    # (実装は省略 - 前回のコードと同じ)
    guild_id = str(ctx.guild.id)
    logger.warning(f"'reset_ranking' command initiated by {ctx.author.name} in guild {guild_id}")
    confirm_button = Button(style=ButtonStyle.danger, label="はい、リセットします", custom_id="confirm_reset")
    cancel_button = Button(style=ButtonStyle.secondary, label="キャンセル", custom_id="cancel_reset")
    view = View(timeout=30.0); view.message = None # message を初期化
    async def confirm_callback(interaction: Interaction):
        if interaction.user.id != ctx.author.id: await interaction.response.send_message("コマンド実行者のみ操作できます。", ephemeral=True); return
        logger.info(f"Ranking reset confirmed by {ctx.author.name} for guild {guild_id}.")
        try:
            with app.app_context():
                deleted_points = PlayerPoints.query.filter_by(guild_id=guild_id).delete()
                deleted_history = PlayerPointHistory.query.filter_by(guild_id=guild_id).delete()
                db.session.commit()
                logger.info(f"Deleted {deleted_points} points, {deleted_history} history records for guild {guild_id}.")
                await interaction.response.edit_message(content="✅ ランキングデータがリセットされました。", view=None)
        except Exception as e: db.session.rollback(); logger.error(f"DB error during ranking reset for guild {guild_id}: {e}", exc_info=True); await interaction.response.edit_message(content="❌ DBエラー発生。", view=None)
        view.stop()
    async def cancel_callback(interaction: Interaction):
        if interaction.user.id != ctx.author.id: await interaction.response.send_message("コマンド実行者のみ操作できます。", ephemeral=True); return
        logger.info(f"Ranking reset cancelled by {ctx.author.name} for guild {guild_id}.")
        await interaction.response.edit_message(content="ランキングのリセットはキャンセルされました。", view=None)
        view.stop()
    confirm_button.callback = confirm_callback; cancel_button.callback = cancel_callback
    view.add_item(confirm_button); view.add_item(cancel_button)
    message = await ctx.send(f"⚠️ **警告:** このサーバーの全てのランキングデータ（累計、履歴）を完全に削除します。元に戻せません。\n本当にリセットしますか？", view=view)
    view.message = message # 送信したメッセージを view に紐付け
    # (タイムアウト処理は省略 - 前回のコードと同じ)
    timeout = await view.wait()
    if timeout and view.message: # タイムアウトした場合
        try: await view.message.edit(content="ランキングリセットの確認がタイムアウトしました。", view=None)
        except discord.NotFound: pass
        except Exception as e: logger.error(f"Error editing reset confirmation on timeout: {e}")

# --- エラーハンドラ (変更なし) ---
@bot.event
async def on_command_error(ctx: commands.Context, error):
    """コマンドエラーを一元的に処理"""
    # (実装は省略 - 前回のコードと同じ)
    if isinstance(error, commands.CommandNotFound): return
    elif isinstance(error, commands.MissingPermissions): await ctx.send(f"🚫 権限不足: `{', '.join(error.missing_permissions)}`")
    elif isinstance(error, commands.NotOwner): await ctx.send("🚫 Botオーナー限定コマンドです。")
    elif isinstance(error, commands.GuildNotFound): await ctx.send("🚫 サーバー内限定コマンドです。")
    elif isinstance(error, commands.CheckFailure): await ctx.send("🚫 コマンド実行条件未達。")
    elif isinstance(error, commands.CommandOnCooldown): await ctx.send(f"⏳ クールダウン中。あと {error.retry_after:.2f} 秒。")
    elif isinstance(error, commands.UserInputError): await ctx.send(f"⚠️ コマンドの使い方が不正です。\n`!help {ctx.command.qualified_name}` 確認推奨。\n詳細: {error}")
    else:
        invoke_error = getattr(error, 'original', error) # CommandInvokeError の場合、元のエラーを取得
        logger.error(f"Unhandled command error in command '{ctx.command}': {invoke_error}", exc_info=invoke_error)
        await ctx.send("🤖 予期せぬエラー発生。管理者に連絡してください。")


# Botの起動
if __name__ == "__main__":
    try:
        logger.info("Attempting to start the Discord bot...")
        bot.run(token, log_handler=None)
    except discord.errors.LoginFailure: logger.critical("ログイン失敗。トークンを確認してください。")
    except discord.errors.PrivilegedIntentsRequired: logger.critical("特権インテント（メッセージコンテンツ等）が無効です。Developer Portalで有効化してください。")
    except Exception as e: logger.critical(f"Bot実行中に予期せぬエラー発生: {e}", exc_info=True)