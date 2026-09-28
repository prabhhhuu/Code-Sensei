from flask import Flask
from database import init_db, close_db, init_challenge_table
from routes.auth_routes import auth_bp
from routes.editor_routes import editor_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # Close DB connection after every request
    app.teardown_appcontext(close_db)

    init_db()
    init_challenge_table()

    app.register_blueprint(auth_bp)
    app.register_blueprint(editor_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
