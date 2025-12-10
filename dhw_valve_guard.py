#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DHW Valve Guard - Automatically closes Plan 2 floor heating valves during DHW cycles.

When DHW heating is detected, sets all Plan 2 rooms to 20°C to prevent hot water
from entering the pipes and causing noise. Restores original temps when DHW finishes.

Integrated into main controller - runs every 10 minutes.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from lk_systems import get_lk_temperatures_with_targets, set_lk_temperature
from utils import log
from config import CONFIG

# Configuration
STATE_FILE = Path("./dhw_valve_state.json")
GUARD_TEMP = 20.0  # Temperature to set during DHW cycle


def log_dhw(message: str):
    """Write DHW-related log message."""
    log(f"[DHW_GUARD] {message}")


def read_state() -> Optional[Dict]:
    """Read the current valve guard state from file."""
    if not STATE_FILE.exists():
        return None
    
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_dhw(f"Failed to read state file: {e}")
        return None


def write_state(state: Dict):
    """Write valve guard state to file."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_dhw(f"ERROR: Failed to write state file: {e}")


def backup_and_close_valves():
    """Set Plan 2 rooms to 20°C and backup original temps."""
    creds = CONFIG["credentials"]
    
    try:
        log_dhw("=== DHW DETECTED: Closing Plan 2 valves ===")
        
        # Get all room temperatures with targets
        rooms = get_lk_temperatures_with_targets(creds["lk_email"], creds["lk_password"])
        log_dhw(f"Retrieved {len(rooms)} rooms")
        
        # Filter Plan 2 rooms (case-insensitive)
        plan2_rooms = [
            r for r in rooms 
            if "plan 2" in r.get("plan", "").lower()
        ]
        log_dhw(f"Found {len(plan2_rooms)} Plan 2 rooms")
        
        if not plan2_rooms:
            log_dhw("WARNING: No Plan 2 rooms found!")
            return
        
        # Create backup state
        backup_state = {
            "active": True,
            "start_time": datetime.now().isoformat(),
            "rooms": {}
        }
        
        # Set each Plan 2 room to 20°C
        success_count = 0
        for room in plan2_rooms:
            room_id = room["id"]
            original_temp = room["target_temp"]
            room_name = room["name"]
            
            # Skip if already at guard temp
            if abs(original_temp - GUARD_TEMP) < 0.1:
                log_dhw(f"  {room_name} (ID {room_id}): Already at {GUARD_TEMP}°C, skipping")
                continue
            
            # Backup original temperature
            backup_state["rooms"][str(room_id)] = {
                "name": room_name,
                "original_temp": original_temp,
            }
            
            # Set to guard temp
            if set_lk_temperature(room_id, GUARD_TEMP, creds["lk_email"], creds["lk_password"]):
                log_dhw(f"  {room_name} (ID {room_id}): {original_temp:.1f}°C → {GUARD_TEMP}°C ✓")
                success_count += 1
            else:
                log_dhw(f"  {room_name} (ID {room_id}): FAILED to set temperature")
        
        # Save state
        write_state(backup_state)
        log_dhw(f"Successfully closed {success_count}/{len(plan2_rooms)} valves")
        log_dhw("=== VALVE GUARD ACTIVATED ===")
        
    except Exception as e:
        log_dhw(f"ERROR in backup_and_close_valves: {e}")


def restore_valves():
    """Restore Plan 2 rooms to original temperatures."""
    creds = CONFIG["credentials"]
    state = read_state()
    
    if not state or not state.get("active"):
        log_dhw("No active valve guard state to restore")
        return
    
    try:
        log_dhw("=== DHW FINISHED: Restoring Plan 2 valves ===")
        
        start_time = state.get("start_time", "Unknown")
        log_dhw(f"Restoring from guard started at: {start_time}")
        
        # Restore each room
        success_count = 0
        for room_id_str, room_data in state["rooms"].items():
            room_id = int(room_id_str)
            original_temp = room_data["original_temp"]
            room_name = room_data["name"]
            
            if set_lk_temperature(room_id, original_temp, creds["lk_email"], creds["lk_password"]):
                log_dhw(f"  {room_name} (ID {room_id}): {GUARD_TEMP}°C → {original_temp:.1f}°C ✓")
                success_count += 1
            else:
                log_dhw(f"  {room_name} (ID {room_id}): FAILED to restore")
        
        log_dhw(f"Successfully restored {success_count}/{len(state['rooms'])} valves")
        
        # Mark state as inactive
        state["active"] = False
        state["end_time"] = datetime.now().isoformat()
        write_state(state)
        
        log_dhw("=== VALVE GUARD DEACTIVATED ===")
        
    except Exception as e:
        log_dhw(f"ERROR in restore_valves: {e}")


def update_valve_guard(dhw_active: bool):
    """
    Main function to manage valve guard based on DHW status.
    Called from main controller every 10 minutes.
    
    Args:
        dhw_active: True if DHW guard is currently active (from check_dhw_guard)
    """
    try:
        current_state = read_state()
        guard_active = current_state and current_state.get("active", False)
        
        if dhw_active and not guard_active:
            # DHW started, activate guard
            backup_and_close_valves()
        
        elif not dhw_active and guard_active:
            # DHW finished, restore valves
            restore_valves()
        
        elif dhw_active and guard_active:
            # DHW still active, guard already active
            log_dhw("DHW active, valve guard already active (holding)")
        
        # If not dhw_active and not guard_active: normal operation, no logging needed
    
    except Exception as e:
        log_dhw(f"ERROR in update_valve_guard: {e}")








