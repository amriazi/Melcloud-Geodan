#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CSV state persistence manager.

Version 5.6 - APPEND-ONLY CSV, NO MIGRATION
- Append-only writes; never rewrites/migrates existing CSV
- Always writes current VERSION; never infers from comment
- Shelly backup columns (shelly_temp, shelly_humidity) appended only if present in header
- Prevents CSV corruption by using last known good values for missing data
- No migration logic - preserves all historical data exactly as written
- Backward compatible with v3.x/v4.x format
- Minimal state columns (only EMA and DHW start time)
- V5.4: Removed flow history tracking (flow_2h_ago, flow_3h_ago) - no longer needed
- V5.5: Supports holiday mode and manual mode (version written to CSV)
- V5.6: Supports date/time-based holiday mode
"""

import csv
import json
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime

from utils import fmt1, fmt2, log
from config import CONFIG, VERSION


# CSV columns - v4.1 Pure Hourly Rhythm
# All control data in dedicated columns for analysis with Python/Excel
BASE_COLS = [
    # Time & Version
    "timestamp",            # ISO timestamp (YYYY-MM-DDTHH:MM)
    "version",              # Algorithm version (e.g. "4.1") - filter by version in analysis
    
    # Temperature Inputs
    "outside_temp",         # Raw outdoor sensor (°C)
    "ema_tout",             # Smoothed outdoor (°C) - what algorithm uses
    "avg_temp",             # Weighted room average (°C) - CONTROLLED VARIABLE
    
    # Control Action
    "flow_cmd",             # Heat pump flow setpoint (°C) - CONTROL OUTPUT
    
    # Measured Feedback
    "flow_temp",            # Actual measured flow (°C)
    "return_temp",          # Actual measured return (°C)
    
    # DHW Status
    "tank_temp_current",    # DHW tank temperature (°C)
    "tank_temp_target",     # DHW target (°C)
    
    # Control Parameters
    "set_room_temp",        # Target room temperature (°C) - usually 23.6
    
    # Trajectory Analysis
    "traj_slope",           # Temperature change rate (°C/hour) - based on 2h history
    "predicted_temp",       # Predicted temperature 1h ahead (°C)
    "predicted_error",      # Predicted error (target - predicted) (°C) - KEY DECISION METRIC
    
    # Control Decision Details
    "reference_flow",       # Weather curve reference (°C) - baseline from outdoor temp
    "adjustment",           # Flow adjustment made (°C) - applied to reference
    "decision_zone",        # Control zone: STABLE (hold) or NORMAL (single-step) in v4.1
    "dhw_active",           # DHW heating active: 0=no, 1=yes - indicates disturbance
]

COMMENT_COL = "comment"  # Human-readable explanation (descriptive text only, no data)


class CSVStateManager:
    """Manages CSV state persistence with simplified format."""
    
    def __init__(self, csv_path: Optional[Path] = None):
        """
        Initialize CSV state manager.
        
        Args:
            csv_path: Path to CSV file (defaults to config)
        """
        self.csv_path = csv_path or CONFIG["csv"]["path"]
    
    def desired_header(self, room_names: List[str]) -> List[str]:
        """
        Generate desired CSV header with room columns.
        
        Args:
            room_names: List of room names
        
        Returns:
            List of column names
        """
        room_cols = [f"room::{name}" for name in sorted(room_names)]
        # V4.8: Add Shelly columns after rooms, before comment
        shelly_cols = ["shelly_temp", "shelly_humidity"]
        return BASE_COLS + room_cols + shelly_cols + [COMMENT_COL]
    
    def read_header(self) -> Optional[List[str]]:
        """
        Read CSV header if file exists.
        
        Returns:
            List of column names or None if file doesn't exist
        """
        if not self.csv_path.exists():
            return None
        
        with self.csv_path.open("r", encoding="utf-8") as f:
            line = f.readline()
            if not line:
                return None
            return [h.strip() for h in line.strip().split(",")]
    
    def read_rows(self) -> List[List[str]]:
        """
        Read all CSV rows.
        
        Returns:
            List of rows (each row is a list of strings)
        """
        if not self.csv_path.exists():
            return []
        
        with self.csv_path.open("r", encoding="utf-8") as f:
            return list(csv.reader(f))
    
    def write_header(self, header: List[str]) -> None:
        """
        Write CSV header.
        
        Args:
            header: List of column names
        """
        with self.csv_path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)
    
    def append_rows(self, rows: List[List[str]]) -> None:
        """
        Append rows to CSV.
        
        Args:
            rows: List of rows (each row is a list of strings)
        """
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)
    
    def migrate_header_if_needed(self, room_names: List[str]) -> List[str]:
        """
        Append-only header handling (v4.9):
        - If no header exists, write desired header.
        - If header exists (even if different), DO NOT rewrite/migrate. Return current.
        
        This prevents CSV corruption from migration logic that rewrites historical rows.
        
        Args:
            room_names: List of room names
        
        Returns:
            Current header (never migrated/rewritten)
        """
        want = self.desired_header(room_names)
        current = self.read_header()
        
        if current is None:
            self.write_header(want)
            log(f"CSV created with v3.0+ format ({len(want)} columns)")
            return want
        
        # v4.9: No migration of existing files to avoid corruption/version rewriting
        if current != want:
            log(f"[INFO] CSV header differs from desired ({len(current)} vs {len(want)} columns); running in append-only mode without migration")
        return current
    
    def read_last_state(self) -> Tuple[
        Optional[float],  # ema_tout
        Optional[float],  # last_flow_cmd (from 10 min ago)
        Optional[float],  # last_hourly_flow (from 1 hour ago, for single-step)
        Optional[float],  # flow_2h_ago (from 2 hours ago, for pause detection)
        Optional[float],  # flow_3h_ago (from 3 hours ago, for pause detection)
        Optional[List[Tuple[str, float]]],   # temp_history: list of (timestamp, temp)
        Optional[float],  # prev_tank_temp
        Optional[str],    # dhw_start_time (reconstructed if DHW active)
    ]:
        """
        Read last state from CSV.
        Reconstructs state from previous rows when possible.
        
        Returns:
            (ema_tout, last_flow_cmd, last_hourly_flow, flow_2h_ago, flow_3h_ago, temp_history, prev_tank_temp, dhw_start_time)
        """
        rows = self.read_rows()
        if not rows or len(rows) == 1:
            return (None, None, None, None, None, None, None, None)
        
        header = rows[0]
        
        # Build index
        idx = {col: i for i, col in enumerate(header)}
        
        def get_float(row: List[str], col: str) -> Optional[float]:
            """Get float value from row."""
            # Try new column name
            if col in idx and idx[col] < len(row):
                try:
                    val = row[idx[col]].strip()
                    return float(val) if val != "" else None
                except (ValueError, IndexError):
                    pass
            # Try old column name (state_* prefix)
            old_col = f"state_{col}" if not col.startswith("state_") else col
            if old_col in idx and idx[old_col] < len(row):
                try:
                    val = row[idx[old_col]].strip()
                    return float(val) if val != "" else None
                except (ValueError, IndexError):
                    pass
            return None
        
        last_row = rows[-1]
        
        # Get EMA outdoor temp
        ema_tout = get_float(last_row, "ema_tout")
        if ema_tout is None:
            ema_tout = get_float(last_row, "state_ema_tout")
        
        # Get last flow command (from current row or previous row's flow_cmd)
        last_flow_cmd = get_float(last_row, "flow_cmd")
        if last_flow_cmd is None and len(rows) > 2:
            last_flow_cmd = get_float(rows[-2], "flow_cmd")
        
        # Get last hourly flow (from last top-of-hour timestamp where we actually applied)
        # Look for the most recent row with timestamp ending in ":00"
        last_hourly_flow = None
        if "timestamp" in idx:
            # Search backwards through recent rows (skip current/last row)
            for row in reversed(rows[:-1]):
                if row == header:  # Skip header
                    continue
                try:
                    timestamp = row[idx["timestamp"]] if len(row) > idx["timestamp"] else ""
                    # Check if this is a top-of-hour timestamp (ends with :00)
                    if timestamp.endswith(":00") or timestamp.endswith("T00"):
                        last_hourly_flow = get_float(row, "flow_cmd")
                        if last_hourly_flow is not None:
                            break
                except (IndexError, ValueError):
                    continue
        
        if last_hourly_flow is None:
            # Fallback to last flow command if no top-of-hour found
            last_hourly_flow = last_flow_cmd
        
        # Reconstruct temperature history from last 12 rows of avg_temp
        temp_history = []
        if "avg_temp" in idx and "timestamp" in idx:
            for row in rows[-12:]:  # Last 12 rows (including current)
                if row == header:  # Skip header
                    continue
                temp = get_float(row, "avg_temp")
                timestamp = row[idx["timestamp"]] if len(row) > idx["timestamp"] else None
                if temp is not None and timestamp is not None:
                    temp_history.append((timestamp, temp))
        
        # If old format has state_temp_history, use it if available
        if not temp_history and "state_temp_history" in idx:
            try:
                val = last_row[idx["state_temp_history"]].strip()
                if val and val != "":
                    temp_history = json.loads(val)
            except (ValueError, IndexError, json.JSONDecodeError):
                pass
        
        # Get previous tank temp (from current row or reconstruct from previous)
        prev_tank_temp = get_float(last_row, "tank_temp_current")
        if prev_tank_temp is None and "state_prev_tank_temp" in idx:
            prev_tank_temp = get_float(last_row, "state_prev_tank_temp")
        
        # Reconstruct DHW start time by looking for tank temp rise
        dhw_start_time = None
        if "state_dhw_start_time" in idx:
            try:
                val = last_row[idx["state_dhw_start_time"]].strip()
                dhw_start_time = val if val != "" else None
            except (ValueError, IndexError):
                pass
        
        # If no DHW start time in state, check if DHW is currently active
        # by looking at recent tank temp history
        if dhw_start_time is None and "tank_temp_current" in idx and len(rows) > 2:
            try:
                curr_tank = get_float(last_row, "tank_temp_current")
                prev_row_tank = get_float(rows[-2], "tank_temp_current")
                if curr_tank and prev_row_tank:
                    temp_rise = curr_tank - prev_row_tank
                    if temp_rise >= 3.0:
                        # DHW just started, use current timestamp
                        dhw_start_time = last_row[idx["timestamp"]] if "timestamp" in idx else None
            except:
                pass
        
        return (ema_tout, last_flow_cmd, last_hourly_flow, temp_history, prev_tank_temp, dhw_start_time)
    
    def read_last_flow_temps(self, count: Optional[int] = None) -> List[Optional[float]]:
        """
        Read last N flow_temp readings from CSV (most recent first).
        
        Args:
            count: Number of readings to return. If None, uses CONFIG['overshoot']['readings'].
                   If 0, returns empty list (disables overshoot detection).
        
        Returns:
            List of last N flow_temp values (length == count). Values may be None.
            Empty list if count=0 (disables overshoot).
        """
        if count is None:
            try:
                count = int(CONFIG.get("overshoot", {}).get("readings", 3))
            except Exception:
                count = 3
        # V5.1: Allow count=0 to disable overshoot (removed max(1, ...) safeguard)
        count = max(0, int(count))  # Allow 0, but prevent negative
        
        rows = self.read_rows()
        if not rows or len(rows) == 1:
            return [None] * count if count > 0 else []
        
        header = rows[0]
        idx = {col: i for i, col in enumerate(header)}
        
        if "flow_temp" not in idx:
            return [None] * count if count > 0 else []
        
        def get_float(row: List[str], col: str) -> Optional[float]:
            if col in idx and idx[col] < len(row):
                try:
                    val = row[idx[col]].strip()
                    return float(val) if val != "" else None
                except (ValueError, IndexError):
                    return None
            return None
        
        flow_temps: List[Optional[float]] = []
        for row in reversed(rows[1:]):  # skip header, iterate backwards
            if len(flow_temps) >= count:
                break
            flow_temps.append(get_float(row, "flow_temp"))
        
        while len(flow_temps) < count:
            flow_temps.append(None)
        
        return flow_temps[:count] if count > 0 else []
    
    def append_row(
        self,
        timestamp: datetime,
        outside_temp: Optional[float],
        avg_temp: Optional[float],
        flow_cmd: float,
        flow_temp: Optional[float],
        return_temp: Optional[float],
        tank_current: Optional[float],
        tank_target: Optional[float],
        set_room_temp: float,
        traj_slope: float,
        predicted_temp: float,
        predicted_error: float,
        reference_flow: float,
        adjustment: float,
        decision_zone: str,
        dhw_active: bool,
        room_map: Dict[str, float],
        ema_tout: float,
        dhw_start_time: Optional[str],
        shelly_temp: Optional[float],      # V4.8: Add
        shelly_humidity: Optional[float],  # V4.8: Add
        comment: str,
    ) -> None:
        """
        Append a row to CSV with all values in dedicated columns.
        
        Args:
            timestamp: Timestamp for this row
            outside_temp: Outdoor temperature (°C)
            avg_temp: Weighted average room temperature (°C)
            flow_cmd: Commanded flow temperature (°C)
            flow_temp: Measured flow temperature (°C)
            return_temp: Measured return temperature (°C)
            tank_current: Current tank temperature (°C)
            tank_target: Target tank temperature (°C)
            set_room_temp: Room setpoint (°C)
            traj_slope: Trajectory slope (°C/hour)
            predicted_temp: Predicted temperature 2h ahead (°C)
            predicted_error: Predicted error (target - predicted) (°C)
            reference_flow: Weather curve reference (°C)
            adjustment: Flow adjustment applied (°C)
            decision_zone: Control zone (STABLE/LANDING/EMERGENCY/NORMAL)
            dhw_active: DHW heating active (True/False)
            room_map: Dict mapping room name to temperature
            ema_tout: EMA of outdoor temperature (°C)
            dhw_start_time: ISO timestamp when DHW started (for internal tracking)
            shelly_temp: Shelly backup temperature (°C) - V4.8
            shelly_humidity: Shelly backup humidity (%) - V4.8
            comment: Descriptive comment (text only, no data values)
        """
        header = self.migrate_header_if_needed(list(room_map.keys()))
        room_cols = [h for h in header if h.startswith("room::")]
        
        # v4.9: Detect Shelly columns in current header (append only if present)
        has_shelly_temp = "shelly_temp" in header
        has_shelly_humidity = "shelly_humidity" in header
        
        # V4.8: Read last row to get previous values for fallback (prevent empty strings)
        last_row_values = {}
        if self.csv_path.exists():
            try:
                rows = self.read_rows()
                if len(rows) > 1:
                    header_prev = rows[0]
                    idx = {col: i for i, col in enumerate(header_prev)}
                    last_row = rows[-1]
                    
                    # Store last known values
                    for col_name in ["avg_temp", "shelly_temp", "shelly_humidity"]:
                        if col_name in idx and idx[col_name] < len(last_row):
                            val = last_row[idx[col_name]].strip()
                            if val and val != "":
                                try:
                                    last_row_values[col_name] = float(val)
                                except ValueError:
                                    pass
                    
                    # Store last known room temperatures
                    for col in [h for h in header_prev if h.startswith("room::")]:
                        if col in idx and idx[col] < len(last_row):
                            val = last_row[idx[col]].strip()
                            if val and val != "":
                                try:
                                    name = col.replace("room::", "")
                                    last_row_values[f"room_{name}"] = float(val)
                                except ValueError:
                                    pass
            except Exception:
                pass  # If we can't read, proceed with None values
        
        # Build row - use last known good values if current is None
        row = [
            timestamp.isoformat(timespec="minutes"),
            VERSION,
            fmt1(outside_temp),
            fmt1(ema_tout),
            fmt2(avg_temp) if avg_temp is not None else fmt2(last_row_values.get("avg_temp")),  # V4.8: Use last known
            fmt1(flow_cmd),
            fmt1(flow_temp),
            fmt1(return_temp),
            fmt1(tank_current),
            fmt1(tank_target),
            fmt1(set_room_temp) if set_room_temp is not None else "",
            fmt2(traj_slope),
            fmt2(predicted_temp),
            fmt2(predicted_error),
            fmt1(reference_flow),
            fmt1(adjustment),
            decision_zone,
            "1" if dhw_active else "0",  # DHW active flag
        ]
        
        # Add room temperatures - use last known if current is missing
        for col in room_cols:
            name = col.replace("room::", "")
            current_temp = room_map.get(name)
            if current_temp is not None:
                row.append(fmt1(current_temp))
            else:
                # V4.8: Use last known value for this room
                last_temp = last_row_values.get(f"room_{name}")
                row.append(fmt1(last_temp) if last_temp is not None else "")
        
        # v4.9: Only append Shelly columns if present in header
        if has_shelly_temp:
            row.append(fmt1(shelly_temp) if shelly_temp is not None else fmt1(last_row_values.get("shelly_temp")))
        if has_shelly_humidity:
            row.append(fmt1(shelly_humidity) if shelly_humidity is not None else fmt1(last_row_values.get("shelly_humidity")))
        
        # Add comment (descriptive text only)
        row.append(comment)
        
        self.append_rows([row])
