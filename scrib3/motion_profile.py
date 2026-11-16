"""John's tested drawing/travel baseline, in native GRBL units."""

DRAW_FEED = 8890.0  # 350 in/min
TRAVEL_FEED = 8890.0
JOG_FEED = 150.0
SMOOTH_SETTINGS = {11: .020, 110: TRAVEL_FEED, 111: TRAVEL_FEED, 120: 25.0, 121: 25.0}
