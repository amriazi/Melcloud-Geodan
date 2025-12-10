#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LK Systems integration for reading room temperatures.
"""

import time
import requests
import urllib3
from typing import Dict, Any, List, Tuple, Optional

from utils import log, fmt1
from config import CONFIG

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _lk_login(email: str, password: str) -> requests.Session:
    """
    Login to LK Systems API and return authenticated session.
    
    Args:
        email: LK Systems account email
        password: LK Systems account password
    
    Returns:
        Authenticated requests session
    
    Raises:
        RuntimeError: If login fails after retries
    """
    session = requests.Session()
    network_config = CONFIG["network"]
    
    for attempt in range(1, network_config["retries"] + 1):
        try:
            response = session.post(
                "https://my.lk.nu/login",
                data={"email": email, "password": password},
                verify=False,
                timeout=network_config["timeout"],
            )
            if response.status_code != 200:
                raise RuntimeError(f"LK login status {response.status_code}")
            
            data = response.json()
            if "email" not in data or data["email"] != email:
                raise RuntimeError("LK login invalid credentials")
            
            # Set cookie if provided
            if "cookie" in data:
                cookie_data = data["cookie"]
                session.cookies.set(
                    cookie_data.get("name", "user"),
                    cookie_data.get("cookie"),
                    domain=cookie_data.get("domain", ".lk.nu"),
                    path=cookie_data.get("path", "/"),
                )
            
            return session
            
        except Exception as e:
            if attempt == network_config["retries"]:
                raise RuntimeError(f"LK login failed after {network_config['retries']} attempts: {e}")
            time.sleep(network_config["retry_sleep"])
    
    return session


def _hex_to_str(hex_string: str) -> str:
    """
    Decode hex string to UTF-8 or Latin-1.
    
    Args:
        hex_string: Hexadecimal string
    
    Returns:
        Decoded string
    """
    try:
        return bytes.fromhex(hex_string).decode("utf-8")
    except UnicodeDecodeError:
        try:
            return bytes.fromhex(hex_string).decode("latin-1")
        except Exception:
            return hex_string
    except Exception:
        return hex_string


def get_lk_temperatures(email: str, password: str) -> List[Dict[str, Any]]:
    """
    Fetch room temperatures from LK Systems.
    
    Args:
        email: LK Systems account email
        password: LK Systems account password
    
    Returns:
        List of room dictionaries with keys: id, name, temp, plan
    """
    session = _lk_login(email, password)
    rooms = []
    network_config = CONFIG["network"]
    
    try:
        # Get plan names
        try:
            main_response = session.get(
                "https://my.lk.nu/main.json",
                verify=False,
                timeout=network_config["timeout"],
            )
            main_data = main_response.json()
            plan_names = {
                i: _hex_to_str(hex_name)
                for i, hex_name in enumerate(main_data.get("sect_name", []))
            }
        except Exception:
            plan_names = {}
        
        # Fetch each thermostat
        for tid in range(64):
            try:
                thermostat_response = session.get(
                    f"https://my.lk.nu/thermostat.json?tid={tid}",
                    verify=False,
                    timeout=network_config["timeout"],
                )
                thermostat_data = thermostat_response.json()
                
                if "get_room_deg" not in thermostat_data:
                    continue
                
                hex_name = thermostat_data.get("name", "")
                if not hex_name or hex_name == "546865726D6F73746174":  # "Thermostat" in hex
                    continue
                
                name = _hex_to_str(hex_name)
                zones = thermostat_data.get("actuator_zone", [])
                max_zone = max([int(z) for z in zones if z != "0"], default=0)
                plan = plan_names.get(
                    0 if max_zone <= 5 else 1,
                    f"Plan {1 if max_zone <= 5 else 2}",
                )
                temp = float(thermostat_data["get_room_deg"]) / 100.0
                
                rooms.append({
                    "id": tid,
                    "name": name,
                    "temp": temp,
                    "plan": plan,
                })
            except Exception:
                continue
    
    finally:
        session.close()
    
    return rooms


def get_lk_temperatures_with_targets(email: str, password: str) -> List[Dict[str, Any]]:
    """
    Fetch room temperatures AND target setpoints from LK Systems.
    
    Args:
        email: LK Systems account email
        password: LK Systems account password
    
    Returns:
        List of room dictionaries with keys: id, name, temp, target_temp, plan
    """
    session = _lk_login(email, password)
    rooms = []
    network_config = CONFIG["network"]
    
    try:
        # Get plan names
        try:
            main_response = session.get(
                "https://my.lk.nu/main.json",
                verify=False,
                timeout=network_config["timeout"],
            )
            main_data = main_response.json()
            plan_names = {
                i: _hex_to_str(hex_name)
                for i, hex_name in enumerate(main_data.get("sect_name", []))
            }
        except Exception:
            plan_names = {}
        
        # Fetch each thermostat
        for tid in range(64):
            try:
                thermostat_response = session.get(
                    f"https://my.lk.nu/thermostat.json?tid={tid}",
                    verify=False,
                    timeout=network_config["timeout"],
                )
                thermostat_data = thermostat_response.json()
                
                if "get_room_deg" not in thermostat_data:
                    continue
                
                hex_name = thermostat_data.get("name", "")
                if not hex_name or hex_name == "546865726D6F73746174":
                    continue
                
                name = _hex_to_str(hex_name)
                zones = thermostat_data.get("actuator_zone", [])
                max_zone = max([int(z) for z in zones if z != "0"], default=0)
                plan = plan_names.get(
                    0 if max_zone <= 5 else 1,
                    f"Plan {1 if max_zone <= 5 else 2}",
                )
                
                # Current temperature
                temp = float(thermostat_data["get_room_deg"]) / 100.0
                
                # Target temperature (setpoint)
                target_temp = float(thermostat_data.get("set_room_deg", 
                                   thermostat_data.get("comfort_deg", "0"))) / 100.0
                
                rooms.append({
                    "id": tid,
                    "name": name,
                    "temp": temp,
                    "target_temp": target_temp,
                    "plan": plan,
                })
            except Exception:
                continue
    
    finally:
        session.close()
    
    return rooms


def set_lk_temperature(room_id: int, target_temp: float, email: str, password: str) -> bool:
    """
    Set target temperature for a specific room.
    
    Args:
        room_id: Room ID / thermostat ID
        target_temp: Target temperature in Celsius (e.g., 22.0)
        email: LK Systems account email
        password: LK Systems account password
    
    Returns:
        True if successful, False otherwise
    """
    try:
        session = _lk_login(email, password)
        network_config = CONFIG["network"]
        
        # Convert temperature to LK format (multiply by 100)
        temp_value = int(target_temp * 100)
        
        # Send update request
        update_url = f"https://my.lk.nu/update.cgi?tid={room_id}&set_room_deg={temp_value}"
        response = session.get(update_url, verify=False, timeout=network_config["timeout"])
        
        session.close()
        
        return response.status_code == 200
        
    except Exception as e:
        log(f"[ERROR] Failed to set temperature for room {room_id}: {e}")
        return False


def compute_weighted_avg(rooms: List[Dict[str, Any]]) -> Tuple[float, Dict[str, float], Dict[str, float], float]:
    """
    Compute weighted average room temperature.
    
    Rooms more than 0.5°C above simple mean get weight 0.5 (solar/load rooms),
    others get weight 1.0.
    
    Args:
        rooms: List of room dicts with 'name' and 'temp' keys
    
    Returns:
        (weighted_avg, room_temp_map, room_weights, simple_mean)
        - weighted_avg: Weighted average temperature (°C)
        - room_temp_map: Dict mapping room name to temperature
        - room_weights: Dict mapping room name to weight used
        - simple_mean: Simple arithmetic mean (°C)
    
    Raises:
        RuntimeError: If no rooms available after exclusions
    """
    excluded = CONFIG["rooms"]["excluded_names"]
    included_rooms = [
        (r["name"], r["temp"])
        for r in rooms
        if r["name"] not in excluded
    ]
    
    if not included_rooms:
        raise RuntimeError("No rooms available for averaging after exclusions.")
    
    temps = [temp for _, temp in included_rooms]
    simple_mean = sum(temps) / len(temps)
    
    # Assign weights: rooms > mean + 0.5°C get weight 0.5
    weighted_data = []
    for name, temp in included_rooms:
        weight = 0.5 if (temp > simple_mean + 0.5) else 1.0
        weighted_data.append((name, temp, weight))
    
    # Compute weighted average
    numerator = sum(temp * weight for _, temp, weight in weighted_data)
    denominator = sum(weight for _, _, weight in weighted_data)
    weighted_avg = numerator / denominator if denominator > 0 else simple_mean
    
    room_temp_map = {name: temp for name, temp, _ in weighted_data}
    room_weights = {name: weight for name, _, weight in weighted_data}
    
    return weighted_avg, room_temp_map, room_weights, simple_mean



