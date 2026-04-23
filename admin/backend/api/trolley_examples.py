"""Built-in read-only trolley timelines used for hardware bring-up testing.

These are seeded on app boot (idempotent) and flagged `readonly: true` so
the API refuses to PUT / DELETE them. Users can still play them and use
the Duplicate action to get an editable copy.
"""

EXAMPLES = [
    {
        "id": "trtl_example_home_and_go",
        "name": "Example — Home and go",
        "duration": 45,
        "readonly": True,
        "events": [
            {"id": "ex1_ev_01", "time": 0.0,  "command": "enable",   "value": 1},
            {"id": "ex1_ev_02", "time": 2.0,  "command": "home"},
            {"id": "ex1_ev_03", "time": 10.0, "command": "position", "value": 0.25},
            {"id": "ex1_ev_04", "time": 18.0, "command": "position", "value": 0.75},
            {"id": "ex1_ev_05", "time": 26.0, "command": "position", "value": 0.1},
            {"id": "ex1_ev_06", "time": 34.0, "command": "position", "value": 0.0},
            {"id": "ex1_ev_07", "time": 40.0, "command": "enable",   "value": 0},
        ],
    },
    {
        "id": "trtl_example_ping_pong",
        "name": "Example — Ping-pong",
        "duration": 45,
        "readonly": True,
        "events": [
            {"id": "ex2_ev_01", "time": 0.0,  "command": "enable",   "value": 1},
            {"id": "ex2_ev_02", "time": 2.0,  "command": "home"},
            {"id": "ex2_ev_03", "time": 8.0,  "command": "position", "value": 0.0},
            {"id": "ex2_ev_04", "time": 12.0, "command": "position", "value": 1.0},
            {"id": "ex2_ev_05", "time": 16.0, "command": "position", "value": 0.0},
            {"id": "ex2_ev_06", "time": 20.0, "command": "position", "value": 1.0},
            {"id": "ex2_ev_07", "time": 24.0, "command": "position", "value": 0.0},
            {"id": "ex2_ev_08", "time": 28.0, "command": "position", "value": 1.0},
            {"id": "ex2_ev_09", "time": 32.0, "command": "position", "value": 0.0},
            {"id": "ex2_ev_10", "time": 40.0, "command": "enable",   "value": 0},
        ],
    },
    {
        "id": "trtl_example_step_ramp",
        "name": "Example — Step burst ramp",
        "duration": 45,
        "readonly": True,
        "events": [
            {"id": "ex3_ev_01", "time": 0.0,  "command": "enable", "value": 1},
            {"id": "ex3_ev_02", "time": 2.0,  "command": "home"},
            {"id": "ex3_ev_03", "time": 6.0,  "command": "dir",    "value": 1},
            {"id": "ex3_ev_04", "time": 6.0,  "command": "speed",  "value": 0.2},
            {"id": "ex3_ev_05", "time": 7.0,  "command": "step",   "value": 800},
            {"id": "ex3_ev_06", "time": 14.0, "command": "dir",    "value": 0},
            {"id": "ex3_ev_07", "time": 14.0, "command": "speed",  "value": 0.4},
            {"id": "ex3_ev_08", "time": 15.0, "command": "step",   "value": 1600},
            {"id": "ex3_ev_09", "time": 24.0, "command": "dir",    "value": 1},
            {"id": "ex3_ev_10", "time": 24.0, "command": "speed",  "value": 0.7},
            {"id": "ex3_ev_11", "time": 25.0, "command": "step",   "value": 2400},
            {"id": "ex3_ev_12", "time": 36.0, "command": "stop"},
            {"id": "ex3_ev_13", "time": 40.0, "command": "enable", "value": 0},
        ],
    },
]
