#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MELCloud Flow Controller - Main entry point.

Version 5.5 - Holiday Mode and Manual Mode
Runs every 10 minutes.
Control decisions ONLY at top of hour (XX:00-XX:09).
Between hours (XX:10-XX:59): Monitor only, show predictions without deciding.
Append-only CSV writes - never rewrites/migrates historical data.
Shelly backup thermometer as fallback if LK Systems unavailable.
Single-step adjustments (±1°C or OFF↔28°C) with 2-hour trajectory prediction.
Two zones: STABLE (hold optimal), NORMAL (single-step).
Pure trajectory-based predictions with weather curve min/max enforcement.
V5.2: Weather curve uses raw outdoor_temp (not EMA) for faster response to outdoor changes.
V5.3: Removed overshoot function; Simplified single-step logic; Weather min/max enforced.
V5.4: Removed consecutive pause mechanism - simplified and more coherent logic.
V5.5: Added holiday mode (separate target temp, weather curve, zones, limits).
V5.5: Added manual mode (calculation only, no MELCloud application).
No emergency overrides, no DHW flow moderation.
"""

import os
import sys
import datetime as dt
import asyncio
from typing import Optional

# Windows event loop policy
if os.name == "nt":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

from utils import log, ema_update, fmt1, fmt2
from config import CONFIG, VERSION
from lk_systems import get_lk_temperatures, compute_weighted_avg
from melcloud import HeatPumpController
from shelly_backup import get_shelly_temperature
from control_logic import (
    hourly_rhythm_decision,
    calculate_trajectory,
    update_temp_history,
    check_dhw_guard,
)
from state_manager import CSVStateManager
from dhw_valve_guard import update_valve_guard


def is_top_of_hour(timestamp: dt.datetime, window_minutes: int = 10) -> bool:
    """
    Check if current time is at or near top of hour (XX:00).
    
    Args:
        timestamp: Current datetime
        window_minutes: Apply window (default 10 minutes)
    
    Returns:
        True if within window_minutes of hour boundary
    """
    return timestamp.minute < window_minutes


async def run_once():
    """
    Main control loop - runs once per invocation (every 10 minutes).
    
    Orchestrates:
    1. Fetch LK room temperatures
    2. Compute weighted average
    3. Fetch MELCloud outdoor and key temperatures
    4. Read previous state from CSV
    5. Update EMA of outdoor temperature
    6. Update temperature history
    7. Calculate trajectory
    8. Check DHW guard
    9. Unified control decision
    10. Apply flow command to MELCloud
    11. Append CSV row with all data
    """
    log(f"Running script: {os.path.abspath(__file__)}")
    now = dt.datetime.now()
    
    creds = CONFIG["credentials"]
    flow_limits = CONFIG["flow_limits"]
    control_config = CONFIG["control"]
    
    # Check for manual mode and holiday mode (manual mode affects both normal and holiday mode)
    manual_mode_enabled = CONFIG.get("manual_mode", {}).get("enable", 0) == 1
    holiday_mode_enabled = CONFIG.get("holiday_mode", {}).get("enable", 0) == 1
    
    # Select appropriate control config based on mode
    if holiday_mode_enabled:
        control_config = CONFIG.get("holiday_control", control_config)
        flow_limits = CONFIG.get("holiday_flow_limits", flow_limits)
        log("[HOLIDAY MODE] Using holiday mode settings (lower target temp, conservative weather curve)")
    
    if manual_mode_enabled:
        log("[MANUAL MODE] Flow temperature calculation only - no MELCloud application")
    
    # ========== 1) Fetch LK Room Temperatures ==========
    try:
        rooms = get_lk_temperatures(creds["lk_email"], creds["lk_password"])
        log(f"LK: fetched {len(rooms)} thermostats.")
    except Exception as e:
        log(f"[ERR] LK fetch failed: {e}")
        rooms = []
    
    # ========== 2) Compute Weighted Average ==========
    avg_temp = None
    room_map = {}
    room_weights = {}
    simple_mean = None
    shelly_temp = None
    shelly_humidity = None
    
    if rooms:
        try:
            avg_temp, room_map, room_weights, simple_mean = compute_weighted_avg(rooms)
            temps_str = ", ".join([
                f"{name}={room_map[name]}°C(w={room_weights.get(name, 1.0):.1f})"
                for name in sorted(room_map.keys())
            ])
            log(f"Rooms: {temps_str}")
            log(f"Avg (simple)={simple_mean:.2f}°C, Avg (weighted)={avg_temp:.2f}°C")
        except Exception as e:
            log(f"[ERR] Avg computation failed: {e}")
    
    # ========== 2.5) Fetch Shelly Backup (if LK Systems failed) ==========
    # V4.8: Always fetch Shelly, but use as backup if LK Systems unavailable
    shelly_temp, shelly_humidity = get_shelly_temperature()
    
    if avg_temp is None and shelly_temp is not None:
        # Use Shelly as backup
        avg_temp = shelly_temp
        log(f"[BACKUP] Using Shelly temperature {avg_temp:.2f}°C as avg_temp (LK Systems unavailable)")
        # room_map stays empty (will be handled in CSV write)
    
    # ========== 3) Fetch MELCloud Temperatures ==========
    hp_out = HeatPumpController()
    try:
        outside_temp = await hp_out.get_outdoor_temperature(creds["mel_email"], creds["mel_password"])
        log(f"MEL: outdoor via device.outside_temperature = {outside_temp}°C")
    except Exception as e:
        log(f"[ERR] MEL outdoor fetch failed: {e}")
        outside_temp = None
    
    hp_meas = HeatPumpController()
    try:
        keytemps = await hp_meas.get_key_temperatures(creds["mel_email"], creds["mel_password"])
        flow_meas = keytemps.get("flow")
        return_meas = keytemps.get("return")
        tank_cur = keytemps.get("tank_current")
        tank_tgt = keytemps.get("tank_target")
        log(f"MEL: zone0 flow={fmt1(flow_meas)}°C, return={fmt1(return_meas)}°C; tank_current={fmt1(tank_cur)}°C, tank_target={fmt1(tank_tgt)}°C")
    except Exception as e:
        log(f"[ERR] MEL key temps fetch failed: {e}")
        flow_meas = return_meas = tank_cur = tank_tgt = None
    
    # ========== 4) Read Previous State ==========
    state_mgr = CSVStateManager()
    state_mgr.migrate_header_if_needed(list(room_map.keys()))
    
    prev_ema, prev_last_cmd, prev_hourly_cmd, temp_history, prev_tank_temp, prev_dhw_start_time = (
        state_mgr.read_last_state()
    )
    
    # ========== 4.5) Fallback to Last Known Good Temperature if Both Failed ==========
    # V4.8: If avg_temp is still None (both LK Systems and Shelly failed), use last valid from CSV
    if avg_temp is None:
        last_valid_avg_temp = None
        if temp_history:
            # Get most recent valid temperature from history
            last_valid_avg_temp = temp_history[-1][1] if temp_history else None
        
        # Also try reading from last CSV row directly
        if last_valid_avg_temp is None:
            rows = state_mgr.read_rows()
            if rows and len(rows) > 1:
                header = rows[0]
                idx = {col: i for i, col in enumerate(header)}
                if "avg_temp" in idx:
                    for row in reversed(rows[1:]):  # Search backwards from most recent
                        if idx["avg_temp"] < len(row):
                            val = row[idx["avg_temp"]].strip()
                            if val and val != "":
                                try:
                                    last_valid_avg_temp = float(val)
                                    break
                                except ValueError:
                                    continue
        
        if last_valid_avg_temp is not None:
            avg_temp = last_valid_avg_temp
            log(f"[FALLBACK] Using last known avg_temp={avg_temp:.2f}°C from CSV history")
        else:
            log("[FALLBACK] No temperature data available - cannot make control decision")
    
    # ========== 5) Update EMA of Outdoor Temperature ==========
    if outside_temp is not None:
        ema_tout = ema_update(
            prev_ema,
            float(outside_temp),
            CONFIG["ema"]["alpha_outdoor"]
        ) if prev_ema is not None else float(outside_temp)
    else:
        ema_tout = prev_ema if prev_ema is not None else 8.0
        log("MEL: using previous EMA or default 8.0°C due to missing outdoor.")
    
    log(f"Outdoor EMA={ema_tout:.1f}°C (prev={fmt1(prev_ema)})")
    
    # ========== 6) Update Temperature History ==========
    if avg_temp is not None:
        temp_history = update_temp_history(
            temp_history=temp_history,
            timestamp=now.isoformat(),
            temperature=avg_temp,
            max_readings=CONFIG["prediction"]["lookback_readings"],
        )
    
    # ========== 7) Calculate Trajectory ==========
    traj_slope, traj_status = calculate_trajectory(temp_history)
    
    if traj_status == "ok":
        log(f"Trajectory: slope={fmt2(traj_slope)}°C/h (2h history, {len(temp_history)} readings)")
    else:
        log(f"Trajectory: {traj_status}")
    
    # ========== 8) Check DHW Guard ==========
    dhw_active, dhw_start_time = check_dhw_guard(tank_cur, prev_tank_temp, prev_dhw_start_time, now)
    if CONFIG["dhw_guard"]["enable"]:
        tank_cur_str = fmt1(tank_cur) if tank_cur is not None else "N/A"
        tank_rise = tank_cur - prev_tank_temp if (tank_cur is not None and prev_tank_temp is not None) else 0.0
        
        # Calculate elapsed time if DHW is active
        elapsed_str = ""
        if dhw_active and dhw_start_time:
            try:
                start_dt = dt.datetime.fromisoformat(dhw_start_time)
                elapsed_minutes = int((now - start_dt).total_seconds() / 60)
                elapsed_str = f", elapsed={elapsed_minutes}min"
            except Exception:
                pass
        
        log(f"DHW guard: {'ACTIVE' if dhw_active else 'inactive'} (tank_cur={tank_cur_str}°C, rise={fmt1(tank_rise)}°C{elapsed_str})")
        
        # Update valve guard (close/restore Plan 2 valves)
        update_valve_guard(dhw_active)
    
    # ========== 9) Check if Top of Hour (Control Decision vs. Monitoring) ==========
    # V4.5: Only run control decision at top of hour (XX:00-XX:09)
    # Between hours (XX:10-XX:59): Just monitor, use last applied flow
    app_config = CONFIG["application"]
    at_top_of_hour = is_top_of_hour(now, app_config["apply_window_minutes"])
    
    if at_top_of_hour:
        # ========== TOP OF HOUR: Run Control Decision ==========
        log(f"[DECISION] Top of hour - running control decision")
        
        if avg_temp is None:
            # V4.8: This should rarely happen now (we use Shelly backup and CSV fallback)
            # But if it does, use conservative hold strategy
            log("[FALLBACK] No average temperature available - holding current flow")
            
            # Use last applied flow (conservative hold)
            flow_cmd = prev_last_cmd if prev_last_cmd is not None else 28.0
            flow_cmd = int(round(float(flow_cmd)))
            
            predicted_temp = 0.0
            predicted_error = 0.0
            reference_flow = flow_cmd
            adjustment = 0.0
            decision_zone = "FALLBACK"
            decision_comment = "No average temperature available - holding flow"
            # Override comment if manual mode is enabled
            if manual_mode_enabled:
                decision_comment = "Manual mode"
        else:
            # Use last HOURLY flow (from 1h ago) for single-step logic
            last_flow_for_step = prev_hourly_cmd if prev_hourly_cmd is not None else 28.0
            
            flow_cmd, predicted_temp, predicted_error, reference_flow, adjustment, decision_zone, decision_comment = hourly_rhythm_decision(
                outdoor_ema=ema_tout,
                outdoor_temp=outside_temp if outside_temp is not None else ema_tout,  # V5.2: Use raw temp for weather curve
                avg_temp=avg_temp,
                setpoint=control_config["target_room_temp"],
                trajectory_slope=traj_slope,
                traj_status=traj_status,
                last_flow=last_flow_for_step,
                dhw_active=dhw_active,
                use_holiday_mode=holiday_mode_enabled,
            )
            
            # Override comment if manual mode is enabled
            if manual_mode_enabled:
                decision_comment = "Manual mode"
        
        # Round to integer for MELCloud
        flow_cmd = int(round(float(flow_cmd)))
        
        # Ensure within limits
        flow_cmd = max(int(flow_limits["off"]), min(int(flow_limits["max"]), flow_cmd))
        
        log(f"Control: flow={flow_cmd}°C, zone={decision_zone}, pred_err={fmt2(predicted_error)}°C")
        log(f"  {decision_comment}")
        
        # Apply flow command to MELCloud (skip if manual mode is enabled)
        if manual_mode_enabled:
            log(f"[MANUAL MODE] Skipping MELCloud application - calculated flow={flow_cmd}°C (not applied)")
        else:
            log(f"[APPLY] Applying flow to MELCloud")
            hp_set = HeatPumpController()
            applied_ok = await hp_set.set_flow_temperature_all_zones_int(
                creds["mel_email"],
                creds["mel_password"],
                flow_cmd
            )
            
            if applied_ok:
                log(f"✓ Applied flow={flow_cmd}°C to MELCloud successfully.")
            else:
                log("[WARN] Could not apply flow to MELCloud.")
    
    else:
        # ========== MONITORING: Skip Control Decision ==========
        # Use last applied flow (from previous row, which was at XX:00)
        flow_cmd = prev_last_cmd if prev_last_cmd is not None else 28.0
        flow_cmd = int(round(float(flow_cmd)))
        
        # Calculate prediction for CSV visibility (but don't make decisions)
        if avg_temp is not None and traj_slope is not None:
            # Use same 2-hour lookahead as decision logic
            lookahead_hours = 2.0
            predicted_temp = avg_temp + (traj_slope * lookahead_hours)
            predicted_error = control_config["target_room_temp"] - predicted_temp
        else:
            # V4.8: Use last known values if available
            if avg_temp is not None:
                predicted_temp = avg_temp
                predicted_error = control_config["target_room_temp"] - avg_temp
            else:
                # No data at all - use zeros but log warning
                predicted_temp = 0.0
                predicted_error = 0.0
                log("[WARN] No avg_temp available for prediction")
        
        reference_flow = flow_cmd  # Use current flow as reference
        adjustment = 0.0
        decision_zone = "MONITOR"
        
        # Build monitoring comment
        next_hour = now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)
        decision_comment = f"Monitoring (last applied: {flow_cmd}°C at {now.replace(minute=0, second=0).strftime('%H:%M')})"
        
        log(f"[MONITOR] Between hours - monitoring only")
        log(f"  Last applied: {flow_cmd}°C, next decision at {next_hour.strftime('%H:%M')}")
        log(f"  Current: avg_temp={fmt2(avg_temp)}°C, slope={fmt2(traj_slope)}°C/h, pred_err={fmt2(predicted_error)}°C")
        
        applied_ok = None  # Mark as not applied
    
    # ========== 11) Build Comment and Append CSV Row ==========
    # Build descriptive comment (DHW status now in dedicated column)
    comment = decision_comment
    
    try:
        state_mgr.append_row(
            timestamp=now,
            outside_temp=outside_temp,
            avg_temp=avg_temp,
            flow_cmd=flow_cmd,
            flow_temp=flow_meas,
            return_temp=return_meas,
            tank_current=tank_cur,
            tank_target=tank_tgt,
            set_room_temp=control_config["target_room_temp"],
            traj_slope=traj_slope,
            predicted_temp=predicted_temp,
            predicted_error=predicted_error,
            reference_flow=reference_flow,
            adjustment=adjustment,
            decision_zone=decision_zone,
            dhw_active=dhw_active,
            room_map=room_map,
            ema_tout=ema_tout,
            dhw_start_time=dhw_start_time,
            shelly_temp=shelly_temp,          # V4.8: Add Shelly temperature
            shelly_humidity=shelly_humidity,  # V4.8: Add Shelly humidity
            comment=comment,
        )
        log("CSV row appended.")
    except Exception as e:
        log(f"[ERR] CSV append failed: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(run_once())
        log("Control loop finished.")
    except Exception as e:
        log(f"[FATAL] {e}")
        sys.exit(1)
