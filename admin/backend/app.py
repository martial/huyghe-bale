"""Flask application — GPIO Timeline Controller admin backend."""

import os
from flask import Flask, send_from_directory
from flask_cors import CORS


def create_app(dist_dir=None, data_dir=None):
    # Override data directory before API modules read config.DATA_DIR
    if data_dir is not None:
        import config
        config.DATA_DIR = data_dir

    from api import timelines, devices, orchestrations, playback, export, settings
    from api.playback import set_engine
    from engine.playback import PlaybackEngine

    app = Flask(__name__, static_folder=None)
    CORS(app)

    # Register API blueprints
    app.register_blueprint(timelines.bp, url_prefix="/api/v1/timelines")
    app.register_blueprint(devices.bp, url_prefix="/api/v1/devices")
    app.register_blueprint(orchestrations.bp, url_prefix="/api/v1/orchestrations")
    app.register_blueprint(playback.bp, url_prefix="/api/v1/playback")
    app.register_blueprint(export.bp, url_prefix="/api/v1/export")
    app.register_blueprint(settings.bp, url_prefix="/api/v1/settings")

    # Import endpoint is under /api/v1/import
    @app.route("/api/v1/import/timeline", methods=["POST"])
    def import_timeline_route():
        return export.import_timeline()

    # Initialize playback engine
    engine = PlaybackEngine()
    set_engine(engine)

    # SPA fallback — serve frontend dist if it exists
    if dist_dir is None:
        dist_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.isdir(dist_dir):
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_spa(path):
            full_path = os.path.join(dist_dir, path)
            if path and os.path.exists(full_path):
                return send_from_directory(dist_dir, path)
            return send_from_directory(dist_dir, "index.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5001)
