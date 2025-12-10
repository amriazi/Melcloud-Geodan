#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configuration constants for the heating flow controller.

Version 4.1 - PURE HOURLY RHYTHM CONTROL
- Applies flow temperature changes only once per hour (at XX:00)
- Single-step changes (±1°C or OFF↔28°C) for natural damping
- Two zones only: STABLE (hold) and NORMAL (single-step)
- No emergency overrides, no DHW flow moderation
- Pure trajectory-based prediction with weather curve constraints
- Symmetric response for warming and cooling
"""

from pathlib import Path
import os

# Load environment variables from .env file (if python-dotenv is installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed - environment variables must be set manually
    pass

# ================== Credentials ==================
# Loaded from environment variables (.env file)

CREDENTIALS = {
    "lk_email": os.getenv("LK_EMAIL", ""),
    "lk_password": os.getenv("LK_PASSWORD", ""),
    "mel_email": os.getenv("MEL_EMAIL", ""),
    "mel_password": os.getenv("MEL_PASSWORD", ""),
}

# ================== Manual Mode (v5.5) ==================
# IMPORTANT: When enabled (1), deactivates flow temperature application to MELCloud
# Code continues as usual - calculates and logs everything, but does not apply flow temp
# Works for both normal mode and holiday mode
# Set to 1 to enable, 0 to disable

MANUAL_MODE = {
    "enable": 0,  # 1 = manual mode (no MELCloud application), 0 = automatic mode
}

# ================== Holiday Mode (v5.5) ==================
# When enabled (1), uses separate target temp, weather curve, control zones, and flow limits
# Set to 1 to enable, 0 to disable

HOLIDAY_MODE = {
    "enable": 0,  # 1 = holiday mode (energy-saving), 0 = normal mode
}

# ================== Flow Temperature Limits ==================

FLOW_LIMITS = {
    "off": 20.0,      # OFF flow temperature (°C)
    "min_on": 28.0,   # Minimum ON flow temperature (°C)
    "max": 38.0,      # Maximum flow temperature (°C) - safety cap
}

# ================== Control Parameters ==================

CONTROL = {
    "target_room_temp": 23.1,  # Comfort setpoint (°C)
}

# ================== Application Rhythm (v4.0) ==================

APPLICATION = {
    "monitor_interval_minutes": 10,    # Script runs every 10 minutes for monitoring/logging
    "apply_interval_minutes": 60,      # Apply flow changes only once per hour (at XX:00)
    "max_step_per_hour": 1,            # Maximum ±1°C change per hour (or OFF↔28°C)
    "apply_window_minutes": 10,        # Apply if within 10 minutes of hour boundary
}

# ================== Weather Curve with Min/Ref/Max (v4.0) ==================

WEATHER_CURVE = {
    # (outdoor_temp, min_flow, reference_flow, max_flow)
    # Min = minimum flow for this outdoor temp (can't go below without turning OFF)
    # Reference = starting point for steady state
    # Max = upper limit for this outdoor temperature
    "anchors": [
        (-15, 32, 34, 35),  # Ultra cold: 33-38°C range
        (-10, 31, 33, 34),  # Extreme cold: 33-37°C range
        (-5,  30, 32, 33),  # Very cold: 31-35°C range
        (0,   29, 31, 32),  # Cold: 29-32°C range
        (5,   28, 29, 30),  # Cool: 28-30°C range
        (10,  20, 28, 29),  # Mild: OFF or 28-30°C
        (15,  20, 20, 28),  # Warm: OFF preferred, up to 28°C if needed
        (20,  20, 20, 20),  # Hot: always OFF
    ],
}

# ================== Control Zones (v4.1 - Two Zones Only) ==================

CONTROL_ZONES = {
    # Stable zone: perfect or near-perfect (hold current flow)
    "stable_error": 0.05,       # ±0.05°C = stable (°C)
    "stable_pred_error": 0.05,  # Predicted within ±0.05°C = stable
    
    # Normal zone: everything else (single-step changes based on trajectory)
    # No emergency zone - trust the hourly rhythm and weather curve minimum
}

# ================== Prediction Parameters ==================

PREDICTION = {
    "lookback_readings": 12,       # Analyze last 2 hours (12 × 10min)
    "lookahead_minutes": 120,      # Predict 2 hours ahead (accounts for floor heating thermal lag)
    "transition_damping": 0.5,     # During rapid outdoor changes, use 50% lookahead (60 min)
}

# ================== Single-Step Control (v4.0) ==================
# No complex adjustments - just ±1°C per hour based on prediction
# Hourly rhythm provides natural damping, no hysteresis needed

# ================== EMA Parameters ==================

EMA = {
    "alpha_outdoor": 0.058,  # Smoothing factor for outdoor temperature EMA (~2-3 hour window)
}

# ================== DHW Guard Parameters ==================

DHW_GUARD = {
    "enable": True,             # Enable DHW guard to suppress aggressive actions during DHW cycles
    "temp_rise_threshold": 3.0, # Minimum tank temp rise to detect DHW heating (°C)
    "timeout_minutes": 90,      # Force DHW off after this many minutes (safety timeout)
}

# ================== HTTP/Network Parameters ==================

NETWORK = {
    "timeout": 120,     # HTTP request timeout (seconds) - 2 minutes for LK Systems and MELCloud
    "retries": 3,       # Number of retry attempts
    "retry_sleep": 3,   # Seconds to wait between retries
}

# ================== Shelly Backup Configuration ==================

SHELLY = {
    "enable": True,                    # Enable Shelly backup thermometer
    "server_uri": "https://shelly-103-eu.shelly.cloud",
    "auth_key": os.getenv("SHELLY_AUTH_KEY", ""),  # Loaded from .env file
    "device_id": os.getenv("SHELLY_DEVICE_ID", ""),  # Loaded from .env file
    "timeout": 20,                     # Shelly API timeout (seconds)
}

# ================== Room Configuration ==================

ROOMS = {
    "excluded_names": {"Garage"},  # Room names to exclude from average
}

# ================== CSV Configuration ==================

CSV = {
    "path": Path("/home/amir/controller/logs/heating_log.csv"),  # Path to CSV log file
}

# ================== Overshoot Detection (v5.1) ==================

OVERSHOOT = {
    # Number of recent flow_temp readings to check for overshoot detection.
    # Overshoot triggers if last applied flow was 28°C but any of the last N
    # measured flow_temp readings reached 29°C or higher.
    # 
    # Examples:
    #   - readings=1: Check only the most recent reading (fastest response)
    #   - readings=2: Check last 2 readings (balanced)
    #   - readings=3: Check last 3 readings (most conservative, default)
    #   - readings=0: DISABLE overshoot detection entirely
    #
    # Recommendation: Start with 1-2 for faster response, increase to 3 if
    # you see false positives from single measurement spikes.
    "readings": 0,
    
    # Minimum current error threshold for overshoot to trigger (°C).
    # Overshoot detection only works if the room is NOT too cold.
    #
    # current_error = setpoint - avg_temp
    # Overshoot triggers only if: current_error >= error_threshold
    #
    # Examples:
    #   - error_threshold=-0.1: Overshoot works if room is NOT 0.1°C+ under target
    #     (i.e., avg_temp <= setpoint + 0.1°C). Prevents turning OFF when already too cold.
    #   - error_threshold=0.0: Overshoot works if room is at or above target
    #   - error_threshold=-0.2: More permissive, allows overshoot even if 0.2°C under
    #
    # Recommendation: -0.1°C prevents overshoot from triggering when the room
    # is already too cold, avoiding making a bad situation worse.
    "error_threshold": -0.1,
}

# Holiday mode uses more conservative settings for energy savings
HOLIDAY_CONTROL = {
    "target_room_temp": 18.0,  # Lower target for energy savings (°C)
}

HOLIDAY_WEATHER_CURVE = {
    # More conservative weather curve - lower flow temperatures
    "anchors": [
        (-15, 25, 27, 28),  # Ultra cold: Lower than normal
        (-10, 24, 26, 27),  # Extreme cold: Lower than normal
        (-5,  23, 24, 26),  # Very cold: Lower than normal
        (0,   20, 23, 24),  # Cold: Lower than normal
        (5,   20, 23, 23),  # Cool: OFF or 28°C
        (10,  20, 20, 20),  # Mild: OFF preferred
        (15,  20, 20, 20),  # Warm: always OFF
        (20,  20, 20, 20),  # Hot: always OFF
    ],
}

HOLIDAY_CONTROL_ZONES = {
    # Wider stable zone for holiday mode (less frequent adjustments)
    "stable_error": 0.15,       # ±0.15°C = stable (°C) - wider than normal
    "stable_pred_error": 0.15,   # Predicted within ±0.15°C = stable
}

HOLIDAY_FLOW_LIMITS = {
    "off": 20.0,      # OFF flow temperature (°C)
    "min_on": 23.0,  # Minimum ON flow temperature (°C)
    "max": 28.0,      # Maximum flow temperature (°C) - lower cap for energy savings
}

# ================== Combined Config Dict ==================

CONFIG = {
    "credentials": CREDENTIALS,
    "flow_limits": FLOW_LIMITS,
    "control": CONTROL,
    "application": APPLICATION,
    "weather_curve": WEATHER_CURVE,
    "control_zones": CONTROL_ZONES,
    "prediction": PREDICTION,
    "ema": EMA,
    "dhw_guard": DHW_GUARD,
    "network": NETWORK,
    "shelly": SHELLY,
    "overshoot": OVERSHOOT,
    "rooms": ROOMS,
    "csv": CSV,
    "manual_mode": MANUAL_MODE,  # IMPORTANT: Controls MELCloud application (affects both normal and holiday mode)
    "holiday_mode": HOLIDAY_MODE,
    "holiday_control": HOLIDAY_CONTROL,
    "holiday_weather_curve": HOLIDAY_WEATHER_CURVE,
    "holiday_control_zones": HOLIDAY_CONTROL_ZONES,
    "holiday_flow_limits": HOLIDAY_FLOW_LIMITS,
}

# ================== Version ==================

VERSION = "5.5"  # Added holiday mode and manual mode switches
