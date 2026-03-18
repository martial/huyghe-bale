"""Flask application — GPIO Timeline Controller admin backend."""

import os
from flask import Flask, send_from_directory
from flask_cors import CORS


def create_app(dist_dir=None, data_dir=None, start_osc=True):
    # Override data directory before API modules read config.DATA_DIR
    if data_dir is not None:
        import config
        config.DATA_DIR = data_dir

    from api import timelines, devices, orchestrations, playback, export, settings, health
    from api.playback import set_engine
    from engine.playback import PlaybackEngine
    from engine.osc_receiver import OscReceiver

    app = Flask(__name__, static_folder=None)
    CORS(app)

    # Register API blueprints
    app.register_blueprint(timelines.bp, url_prefix="/api/v1/timelines")
    app.register_blueprint(devices.bp, url_prefix="/api/v1/devices")
    app.register_blueprint(orchestrations.bp, url_prefix="/api/v1/orchestrations")
    app.register_blueprint(playback.bp, url_prefix="/api/v1/playback")
    app.register_blueprint(export.bp, url_prefix="/api/v1/export")
    app.register_blueprint(settings.bp, url_prefix="/api/v1/settings")
    app.register_blueprint(health.bp, url_prefix="/api/v1/health")

    # Import endpoint is under /api/v1/import
    @app.route("/api/v1/import/timeline", methods=["POST"])
    def import_timeline_route():
        return export.import_timeline()

    # Initialize playback engine
    engine = PlaybackEngine()
    set_engine(engine)

    # Initialize and start OSC Receiver
    receiver = OscReceiver(port=9001)
    if start_osc:
        receiver.start()

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
    port = int(os.environ.get("FLASK_PORT", 5001))
    # Flask debug reloader runs parent (file watcher) + child (server).
    # Only start OSC receiver in the child to avoid double port binding.
    start_osc = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    app = create_app(start_osc=start_osc)
    app.run(debug=True, host="0.0.0.0", port=port)
