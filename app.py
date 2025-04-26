import os
import logging
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# ロギング設定
logging.basicConfig(level=logging.INFO, # 通常運用ではINFOレベルが良いかもしれません
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# SQLAlchemy 2.0 スタイルのベースクラス定義
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a_very_secret_key_for_dev" # 開発用でももう少し複雑な方が望ましい

# 環境変数からデータベースURLを取得、なければSQLiteを使用
# Renderなどのサービスでは DATABASE_URL が postgres:// で提供されることがあるため置換
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url or "sqlite:///kart_rumble.db" # DBファイル名を変更 (任意)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280, # Renderの無料プランDBタイムアウト(300秒)より短く設定
    "pool_pre_ping": True,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # パフォーマンスのため無効推奨
db.init_app(app) # アプリケーションとSQLAlchemyを連携

# アプリケーションコンテキスト内でデータベースを初期化
# これにより、関連するモデルがimportされた後にテーブルが作成される
with app.app_context():
    try:
        # モデルをインポートしてテーブル作成を認識させる
        # models.py 内で db オブジェクトが使われている必要がある
        import models # noqa: F401 (Unused import warningを抑制)
        logger.info("Initializing database tables...")
        db.create_all() # データベースとテーブルが存在しない場合に作成
        logger.info("Database tables checked/created successfully.")

        # データベース接続テスト (オプション)
        try:
            with db.session.begin(): # トランザクション内で実行
                 db.session.execute(text("SELECT 1"))
            logger.info("Database connection test successful.")
        except Exception as conn_test_e:
             logger.error(f"Database connection test failed: {conn_test_e}", exc_info=True)
             # ここで raise するかは状況による (起動を続けるか否か)

    except ImportError:
        logger.error("Could not import models.py. Make sure it exists and is correctly placed.")
        raise
    except Exception as e:
        logger.error(f"Error initializing database or models: {e}", exc_info=True)
        # 初期化エラーは致命的な可能性があるため、起動を停止させる
        raise

@app.route('/')
def index():
    # このルートは Render などのヘルスチェック用にも使える
    # 必要であれば templates/index.html を用意する
    # return render_template('index.html')
    return "Kart Rumble Backend is running!", 200

# 不要になった create_database 関数は削除しました。
# def create_database():
#     if not os.path.exists('site.db'):
#         db.create_all()
#         print("Database created!")

# このファイルが直接実行された場合にFlask開発サーバーを起動
if __name__ == '__main__':
    # create_database() # 削除: DB初期化は app_context で実行される
    # host='0.0.0.0' は外部からのアクセスを許可 (Dockerやデプロイ環境で必要)
    # port=8080 も環境変数から取得できるようにするとより柔軟
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting Flask app on port {port}")
    # debug=True は開発時のみ有効にすること
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'False') == 'True')