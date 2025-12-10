#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pure Hourly Rhythm Control Logic for flow temperature.

Version 5.5 - Holiday Mode and Manual Mode
- Single-step changes (±1°C or OFF↔28°C) at top of hour ONLY
- 2-hour trajectory prediction accounts for floor heating thermal lag
- Two zones: STABLE (hold current optimal) and NORMAL (single-step)
- Called ONLY at XX:00 (monitoring uses predictions for visibility)
- Weather curve min/max enforced on all decisions
- V5.4: Removed consecutive pause mechanism - simplified logic
- V5.5: Added holiday mode (separate target temp, weather curve, zones, limits)
- V5.5: Added manual mode (calculation only, no MELCloud application)
- No emergency overrides, no DHW flow moderation

Key principle: Decide once per hour. Monitor with predictions in between.
"""

from typing import Optional, Tuple, List
from utils import log, fmt1, fmt2
from config import CONFIG


def get_weather_curve(outdoor_temp: float, weather_curve_config: Optional[dict] = None) -> Tuple[float, float, float]:
    """
    Get min, reference, and max flow for given outdoor temperature.
    Uses linear interpolation between anchors.
    
    Args:
        outdoor_temp: Outdoor temperature (°C)
        weather_curve_config: Optional weather curve config dict (defaults to CONFIG["weather_curve"])
    
    Returns:
        (min_flow, reference_flow, max_flow) in °C
    """
    if weather_curve_config is None:
        weather_curve_config = CONFIG["weather_curve"]
    anchors = weather_curve_config["anchors"]
    
    # Below lowest anchor
    if outdoor_temp <= anchors[0][0]:
        return (anchors[0][1], anchors[0][2], anchors[0][3])
    
    # Above highest anchor
    if outdoor_temp >= anchors[-1][0]:
        return (anchors[-1][1], anchors[-1][2], anchors[-1][3])
    
    # Linear interpolation between anchors
    for i in range(len(anchors) - 1):
        t0, min0, ref0, max0 = anchors[i]
        t1, min1, ref1, max1 = anchors[i + 1]
        
        if t0 <= outdoor_temp <= t1:
            if t1 == t0:
                return (min0, ref0, max0)
            
            # Interpolate
            ratio = (outdoor_temp - t0) / (t1 - t0)
            min_flow = min0 + ratio * (min1 - min0)
            ref = ref0 + ratio * (ref1 - ref0)
            max_flow = max0 + ratio * (max1 - max0)
            return (min_flow, ref, max_flow)
    
    # Fallback (should never reach here)
    return (anchors[-1][1], anchors[-1][2], anchors[-1][3])


def calculate_trajectory(temp_history: List[Tuple[str, float]], lookback_readings: int = 12) -> Tuple[float, str]:
    """
    Calculate temperature trajectory using linear regression over last N readings.
    
    Args:
        temp_history: List of (timestamp, temperature) tuples
        lookback_readings: Number of readings to analyze (default 12 = 2 hours)
    
    Returns:
        (slope_per_hour, status)
        - slope_per_hour: °C/hour trend (positive = warming, negative = cooling)
        - status: "ok" or "insufficient_data"
    """
    if len(temp_history) < 3:
        return (0.0, "insufficient_data")
    
    # Use last N readings
    recent = temp_history[-lookback_readings:] if len(temp_history) >= lookback_readings else temp_history
    
    if len(recent) < 3:
        return (0.0, "insufficient_data")
    
    # Linear regression
    n = len(recent)
    x_vals = list(range(n))  # Time indices
    y_vals = [t[1] for t in recent]  # Temperatures
    
    sum_x = sum(x_vals)
    sum_y = sum(y_vals)
    sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
    sum_x2 = sum(x * x for x in x_vals)
    
    denominator = n * sum_x2 - sum_x * sum_x
    if abs(denominator) < 1e-10:
        return (0.0, "insufficient_data")
    
    # Slope in °C per reading (10-minute intervals)
    slope_per_reading = (n * sum_xy - sum_x * sum_y) / denominator
    
    # Convert to °C per hour
    slope_per_hour = slope_per_reading * 6.0  # 6 readings per hour
    
    return (slope_per_hour, "ok")


def update_temp_history(
    temp_history: List[Tuple[str, float]],
    timestamp: str,
    temperature: float,
    max_readings: int = 36  # 6 hours of history
) -> List[Tuple[str, float]]:
    """
    Update temperature history with new reading, keeping last max_readings.
    
    Args:
        temp_history: Current history
        timestamp: ISO timestamp string
        temperature: Temperature reading (°C)
        max_readings: Maximum readings to keep
    
    Returns:
        Updated history list
    """
    updated = temp_history + [(timestamp, temperature)]
    
    # Keep only last max_readings
    if len(updated) > max_readings:
        updated = updated[-max_readings:]
    
    return updated


def hourly_rhythm_decision(
    outdoor_ema: float,
    outdoor_temp: float,
    avg_temp: float,
    setpoint: float,
    trajectory_slope: float,
    traj_status: str,
    last_flow: float,
    dhw_active: bool,
    use_holiday_mode: bool = False,
) -> Tuple[float, float, float, float, float, str, str]:
    """
    V5.5 Simplified Control Decision with Holiday Mode Support.
    
    Pure trajectory-based control with 2-hour prediction:
    - Two zones: STABLE (hold current optimal flow) and NORMAL (single-step)
    - Calculate predicted error 2 HOURS ahead using trajectory
    - Accounts for floor heating thermal lag (1-2 hour delay)
    - Apply single-step change (±1°C or OFF↔28°C) ONLY at top of hour
    - STABLE zone holds current optimal flow (e.g., 29°C if that's working)
    - Weather curve min/max enforced on all decisions
    - V5.2: Weather curve uses raw outdoor_temp (not EMA) for faster response
    - V5.3: Fixed weather minimum enforcement - prevents turning OFF when min_flow >= 28°C
    - V5.4: Removed consecutive pause mechanism - simplified and more coherent logic
    - V5.5: Added holiday mode support (separate configs for energy-saving mode)
    - No emergency overrides, no DHW flow moderation
    - Symmetric response for warming and cooling
    
    Args:
        outdoor_ema: Smoothed outdoor temperature (°C) - used for display/logging
        outdoor_temp: Raw outdoor temperature (°C) - used for weather curve calculation (v5.2)
        avg_temp: Current weighted average room temperature (°C)
        setpoint: Target room temperature (°C)
        trajectory_slope: Temperature change rate (°C/hour)
        traj_status: Trajectory calculation status
        last_flow: Last APPLIED flow from XX:00 timestamp (°C)
        dhw_active: Whether DHW heating is active
        use_holiday_mode: If True, use holiday mode configs (default: False)
    
    Returns:
        (flow_cmd, predicted_temp, predicted_error, reference_flow, adjustment, decision_zone, comment)
    """
    # Get configuration (use mode-specific configs if holiday mode is enabled)
    # Note: use_holiday_mode is a boolean (True/False), but config uses 1/0
    if use_holiday_mode:
        zones = CONFIG.get("holiday_control_zones", CONFIG["control_zones"])
        limits = CONFIG.get("holiday_flow_limits", CONFIG["flow_limits"])
        weather_curve_config = CONFIG.get("holiday_weather_curve", CONFIG["weather_curve"])
    else:
        zones = CONFIG["control_zones"]
        limits = CONFIG["flow_limits"]
        weather_curve_config = CONFIG["weather_curve"]
    
    pred_config = CONFIG["prediction"]
    app_config = CONFIG["application"]
    
    # Get weather curve min/ref/max (v5.2: use raw outdoor_temp for faster response)
    min_flow, ref_flow, max_flow = get_weather_curve(outdoor_temp, weather_curve_config)
    
    # Calculate errors
    current_error = setpoint - avg_temp
    
    # Predict future temperature (2 hours ahead to account for thermal lag)
    lookahead_hours = 2.0
    predicted_temp = avg_temp + (trajectory_slope * lookahead_hours)
    predicted_error = setpoint - predicted_temp
    
    # Initialize
    adjustment = 0
    decision_zone = "NORMAL"
    comment_parts = []
    
    # ===== ZONE 1: STABLE =====
    # Perfect or near-perfect - hold current flow
    if (abs(current_error) <= zones["stable_error"] and 
        abs(predicted_error) <= zones["stable_pred_error"]):
        decision_zone = "STABLE"
        comment_parts.append("Stable near target")
        
        # Even in STABLE, enforce weather minimum if currently OFF
        # Only force ON if weather min >= heat pump minimum (28°C)
        if last_flow == limits["off"] and min_flow >= limits["min_on"]:
            new_flow = max(limits["min_on"], int(min_flow))
            adjustment = new_flow - last_flow
            comment_parts.append(f"but weather min={int(min_flow)}°C at {fmt1(outdoor_ema)}°C - forcing ON")
            return (new_flow, predicted_temp, predicted_error, ref_flow, adjustment, decision_zone, "; ".join(comment_parts))
        
        # Otherwise hold
        return (last_flow, predicted_temp, predicted_error, ref_flow, 0, decision_zone, "; ".join(comment_parts))
    
    # ===== ZONE 2: NORMAL (Single-step changes) =====
    # Everything else - single-step based on trajectory
    # Determine desired direction based on predicted error
    if predicted_error > 0.05:
        # Predicting too cold → need more heat
        direction = +1
        comment_parts.append(f"Pred cold ({fmt2(predicted_error)}°C)")
    elif predicted_error < -0.05:
        # Predicting too hot → need less heat
        direction = -1
        comment_parts.append(f"Pred hot ({fmt2(predicted_error)}°C)")
    else:
        # Predicted error is small
        direction = 0
        comment_parts.append("Pred stable")
    
    # Calculate new flow with single-step limit
    max_step = app_config["max_step_per_hour"]
    
    if last_flow == limits["off"]:
        # Currently OFF
        if direction > 0:
            # Need heat: turn ON at minimum
            new_flow = limits["min_on"]
            adjustment = new_flow - last_flow
            comment_parts.append("Turn ON (28°C)")
        else:
            # Stay OFF
            new_flow = limits["off"]
            adjustment = 0
            comment_parts.append("Hold OFF")
    elif last_flow >= limits["min_on"]:
        # Currently ON
        if direction > 0:
            # Need more heat: +1°C (capped at max_flow)
            new_flow = min(last_flow + max_step, max_flow)
            adjustment = new_flow - last_flow
            comment_parts.append(f"+{int(adjustment)}°C")
        elif direction < 0:
            # Need less heat: -1°C (single step)
            new_flow = last_flow - max_step
            
            # If would go below HP minimum (28°C), turn OFF (single step: 28→20)
            if new_flow < limits["min_on"]:
                new_flow = limits["off"]
                comment_parts.append("Turn OFF")
            else:
                comment_parts.append(f"-{int(max_step)}°C")
            adjustment = new_flow - last_flow
        else:
            # Hold current
            new_flow = last_flow
            adjustment = 0
            comment_parts.append("Hold")
    else:
        # Unexpected state: default to reference
        new_flow = ref_flow
        adjustment = new_flow - last_flow
        comment_parts.append("Reset to reference")
    
    # ===== ENFORCE WEATHER CURVE MIN/MAX =====
    # Enforce weather curve constraints on the calculated flow
    
    # 1. Enforce minimum: If below min_flow and min_flow requires heat, hold at min_flow
    if new_flow < min_flow and min_flow > limits["off"]:
        if min_flow >= limits["min_on"]:
            # Weather requires heat (min_flow >= 28°C) - hold at min_flow
            new_flow = max(limits["min_on"], int(min_flow))
            comment_parts.append(f"Weather min={int(min_flow)}°C enforced")
        # If min_flow < 28°C, OFF is allowed, so no change needed
    
    # 2. Enforce maximum: Cap at max_flow
    if new_flow > max_flow:
        new_flow = int(max_flow)
        comment_parts.append(f"Weather max={int(max_flow)}°C enforced")
    
    # 3. If OFF but weather requires heat, force ON
    if new_flow == limits["off"] and min_flow >= limits["min_on"]:
        new_flow = max(limits["min_on"], int(min_flow))
        adjustment = new_flow - limits["off"]
        comment_parts.append(f"Weather min={int(min_flow)}°C at {fmt1(outdoor_temp)}°C - forcing ON")
    
    # ===== FINAL LIMITS =====
    # Ensure within absolute limits
    new_flow = max(limits["off"], min(limits["max"], new_flow))
    
    return (int(new_flow), predicted_temp, predicted_error, ref_flow, adjustment, decision_zone, "; ".join(comment_parts))


# Keep check_dhw_guard function unchanged (it's still needed)
def check_dhw_guard(
    tank_current: Optional[float],
    prev_tank_temp: Optional[float],
    prev_dhw_start_time: Optional[str],
    current_time,
) -> Tuple[bool, Optional[str]]:
    """
    Check if DHW (Domestic Hot Water) heating cycle is active.
    Uses only temp_rise_threshold method.
    Includes 90-minute timeout.
    
    Args:
        tank_current: Current tank temperature (°C)
        prev_tank_temp: Previous tank temperature (°C)
        prev_dhw_start_time: ISO timestamp string when DHW started (or None)
        current_time: Current datetime object
    
    Returns:
        (dhw_active, dhw_start_time)
        - dhw_active: True if DHW heating detected
        - dhw_start_time: ISO timestamp string of DHW start (or None)
    """
    config = CONFIG["dhw_guard"]
    
    if not config["enable"]:
        return (False, None)
    
    if tank_current is None or prev_tank_temp is None:
        return (False, None)
    
    temp_rise = tank_current - prev_tank_temp
    
    # Check for DHW start (temp rising significantly)
    if temp_rise >= config["temp_rise_threshold"]:
        # DHW heating detected
        if prev_dhw_start_time is None:
            # Just started
            dhw_start_time = current_time.isoformat()
            return (True, dhw_start_time)
        else:
            # Already active - check timeout
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(prev_dhw_start_time)
                elapsed_minutes = (current_time - start_dt).total_seconds() / 60
                
                if elapsed_minutes > config["timeout_minutes"]:
                    # Timeout reached - force DHW off
                    return (False, None)
                else:
                    # Still within timeout - keep active
                    return (True, prev_dhw_start_time)
            except Exception:
                # Parse error - assume active
                return (True, prev_dhw_start_time)
    else:
        # Temp not rising - DHW ended
        return (False, None)

