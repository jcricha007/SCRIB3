"""Plotting speeds in mm/min and the stationary hold before the first stroke."""

START_HOLD_SECONDS = 10
DRAW_FEED = 1500.0  # 25 mm/s
TRAVEL_FEED = DRAW_FEED
JOG_FEED = DRAW_FEED
SMOOTH_SETTINGS = {11: .020, 110: TRAVEL_FEED, 111: TRAVEL_FEED, 120: 25.0, 121: 25.0}
