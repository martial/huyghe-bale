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
    from api import trolley_timelines, trolley_control, vents_control, bridge, protocol_test
    from api.playback import set_engine
    from api.timelines import set_engine as set_timelines_engine
    from api.trolley_timelines import set_engine as set_trolley_timelines_engine
    from api.settings import _read as read_settings, on_change as on_settings_change
    from api.bridge import set_bridge
    from engine.playback import PlaybackEngine
    from engine.osc_receiver import OscReceiver
    from engine.osc_bridge import OscBridge
    from storage.json_store import JsonStore

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
    app.register_blueprint(trolley_timelines.bp, url_prefix="/api/v1/trolley-timelines")
    app.register_blueprint(trolley_control.bp, url_prefix="/api/v1/trolley-control")
    app.register_blueprint(vents_control.bp, url_prefix="/api/v1/vents-control")
    app.register_blueprint(bridge.bp, url_prefix="/api/v1/bridge")
    app.register_blueprint(protocol_test.bp, url_prefix="/api/v1/protocol-test")

    # Import endpoint is under /api/v1/import
    @app.route("/api/v1/import/timeline", methods=["POST"])
    def import_timeline_route():
        return export.import_timeline()

    # Initialize playback engine
    engine = PlaybackEngine()
    set_engine(engine)
    set_timelines_engine(engine)
    set_trolley_timelines_engine(engine)

    # Initialize and start OSC Receiver
    receiver = OscReceiver(port=9001)
    if start_osc:
        receiver.start()

    # Initialize OSC Bridge (external source → admin → devices).
    # Devices are looked up fresh on every message so add/remove takes effect
    # without a restart.
    _device_store = JsonStore(
        data_dir if data_dir is not None else
        os.path.join(os.path.dirname(__file__), "data"),
        "devices", "dev",
    )
    _bridge_settings = read_settings()
    osc_bridge = OscBridge(
        port=int(_bridge_settings.get("bridge_port", 9002)),
        routing=str(_bridge_settings.get("bridge_routing", "type-match")),
        device_provider=_device_store.list_all,
    )
    set_bridge(osc_bridge)
    if start_osc and _bridge_settings.get("bridge_enabled"):
        osc_bridge.start()

    # Live-apply setting changes so the Settings page can toggle the bridge
    # without a backend restart.
    def _on_bridge_enabled(_old, new):
        if new:
            osc_bridge.start()
        else:
            osc_bridge.stop()

    def _on_bridge_port(_old, new):
        osc_bridge.reconfigure(port=int(new))

    def _on_bridge_routing(_old, new):
        osc_bridge.reconfigure(routing=str(new))

    on_settings_change("bridge_enabled", _on_bridge_enabled)
    on_settings_change("bridge_port", _on_bridge_port)
    on_settings_change("bridge_routing", _on_bridge_routing)

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
