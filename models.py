from app import db # dbオブジェクトをapp.pyからインポート
# from flask_login import UserMixin # UserMixinは不要になったので削除
from datetime import datetime, timedelta
import logging
from sqlalchemy import func
# from flask_sqlalchemy import SQLAlchemy # 不要になったので削除

# db = SQLAlchemy() # 不要になったので削除

# UserモデルはDiscordボットに不要なため削除しました。
# class User(UserMixin, db.Model):
#     __tablename__ = 'user'
#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(150), nullable=False, unique=True)
#     email = db.Column(db.String(150), nullable=False, unique=True)
#     password = db.Column(db.String(150), nullable=False)
#
#     def __repr__(self):
#         return f'<User {self.username}>'

class PlayerPoints(db.Model):
    __tablename__ = 'player_points' # テーブル名を明示的に指定 (推奨)
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(20), nullable=False) # Discord ID (ユーザーまたはCPU_X形式)
    guild_id = db.Column(db.String(20), nullable=False) # サーバーID追加
    points = db.Column(db.Integer, default=0)
    total_games = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('discord_id', 'guild_id', name='unique_player_guild'),
    )

    @staticmethod
    def add_points(discord_id: str, guild_id: str, points: int):
        """プレイヤーにポイントを追加し、履歴も記録する"""
        if not discord_id or not isinstance(discord_id, str):
            logging.error(f"Invalid discord_id provided: {discord_id}")
            raise ValueError(f"Invalid discord_id: {discord_id}")

        if not guild_id or not isinstance(guild_id, str):
            logging.error(f"Invalid guild_id provided: {guild_id}")
            raise ValueError(f"Invalid guild_id: {guild_id}")

        # ポイントが0の場合も記録するように変更 (参加ポイントなど)
        if not isinstance(points, int): # pointsが負になることは通常ないと想定
            logging.error(f"Invalid points value provided: {points}")
            raise ValueError(f"Invalid points value: {points}")

        try:
            player = PlayerPoints.query.filter_by(
                discord_id=discord_id,
                guild_id=guild_id
            ).first()

            # ポイントを追加する際は必ずゲーム数を1増やす
            new_total_games = 1
            if player is None:
                logging.info(f"Creating new player record for discord_id: {discord_id} in guild: {guild_id}")
                player = PlayerPoints(
                    discord_id=discord_id,
                    guild_id=guild_id,
                    points=points,
                    total_games=new_total_games # 新規作成時は1
                )
                db.session.add(player)
            else:
                logging.info(f"Updating existing player record for discord_id: {discord_id} in guild: {guild_id}")
                player.points += points
                new_total_games = player.total_games + 1 # 既存プレイヤーは+1
                player.total_games = new_total_games
                player.last_updated = datetime.utcnow()

            # ポイント履歴を記録
            history = PlayerPointHistory(
                discord_id=discord_id,
                guild_id=guild_id,
                points_earned=points,
                total_points=player.points, # 更新後の累計ポイント
                game_number=new_total_games # 何回目のゲームでの獲得か
            )
            db.session.add(history)
            db.session.commit()
            logging.info(f"Successfully added {points} points to player {discord_id} in guild {guild_id}. New total: {player.points}")

        except Exception as e:
            db.session.rollback()
            logging.error(f"Database error while adding points: {str(e)}", exc_info=True)
            # エラーを再発生させることで呼び出し元に通知
            raise Exception(f"Error adding points for discord_id {discord_id} in guild {guild_id}: {str(e)}")

    @staticmethod
    def get_rankings(guild_id: str, period: str = 'all', limit: int = 5):
        """指定されたサーバーの指定された期間のランキングを取得する"""
        try:
            if period not in ['weekly', 'monthly', 'all']:
                logging.error(f"Invalid period value: {period}")
                return []

            if not guild_id or not isinstance(guild_id, str):
                logging.error(f"Invalid guild_id provided: {guild_id}")
                return []

            now = datetime.utcnow()
            rankings = [] # 結果リストを初期化

            if period == 'weekly':
                start_date = now - timedelta(days=7)
                rankings = db.session.query(
                    PlayerPointHistory.discord_id,
                    func.sum(PlayerPointHistory.points_earned).label('total_points')
                ).filter(
                    PlayerPointHistory.timestamp >= start_date,
                    PlayerPointHistory.guild_id == guild_id
                ).group_by(
                    PlayerPointHistory.discord_id
                ).order_by(
                    func.sum(PlayerPointHistory.points_earned).desc()
                ).limit(limit).all()

            elif period == 'monthly':
                start_date = now - timedelta(days=30)
                rankings = db.session.query(
                    PlayerPointHistory.discord_id,
                    func.sum(PlayerPointHistory.points_earned).label('total_points')
                ).filter(
                    PlayerPointHistory.timestamp >= start_date,
                    PlayerPointHistory.guild_id == guild_id
                ).group_by(
                    PlayerPointHistory.discord_id
                ).order_by(
                    func.sum(PlayerPointHistory.points_earned).desc()
                ).limit(limit).all()

            else: # all
                rankings = db.session.query(
                    PlayerPoints.discord_id,
                    PlayerPoints.points.label('total_points')
                ).filter(
                    PlayerPoints.guild_id == guild_id
                ).order_by(
                    PlayerPoints.points.desc()
                ).limit(limit).all()

            logging.info(f"Successfully retrieved {len(rankings)} {period} rankings for guild {guild_id}")
            # 結果を [(discord_id, points), ...] の形式で返す
            return [(r.discord_id, r.total_points) for r in rankings]

        except Exception as e:
            logging.error(f"Error fetching {period} rankings for guild {guild_id}: {str(e)}", exc_info=True)
            return []

    # get_cpu_name 静的メソッドは削除しました。

class PlayerPointHistory(db.Model):
    """ポイント獲得履歴を記録するテーブル"""
    __tablename__ = 'player_point_history' # テーブル名を明示的に指定 (推奨)
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(20), nullable=False)
    guild_id = db.Column(db.String(20), nullable=False) # サーバーID追加
    points_earned = db.Column(db.Integer, nullable=False)
    total_points = db.Column(db.Integer, nullable=False) # この履歴追加後の累計ポイント
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    game_number = db.Column(db.Integer) # 何回目のゲームでのポイント獲得か (追加)

    def __repr__(self):
        return f'<PlayerPointHistory G:{self.guild_id} P:{self.discord_id} earned:{self.points_earned} total:{self.total_points} time:{self.timestamp}>'