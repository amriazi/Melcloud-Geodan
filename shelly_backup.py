#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shelly HT Gen3 Backup Temperature Sensor

Fetches temperature and humidity from Shelly device as backup for LK Systems.
"""

import requests
import datetime as dt
from typing import Dict, Optional, Tuple

from utils import log, fmt1
from config import CONFIG


def get_shelly_temperature() -> Tuple[Optional[float], Optional[float]]:
    """
    Get temperature and humidity from Shelly device.
    
    Returns:
        (temperature_c, humidity_percent) or (None, None) if unavailable
    """
    shelly_config = CONFIG.get("shelly", {})
    
    if not shelly_config.get("enable", False):
        return (None, None)
    
    try:
        url = f"{shelly_config['server_uri']}/device/status"
        data = f"id={shelly_config['device_id']}&auth_key={shelly_config['auth_key']}"
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        
        timeout = shelly_config.get("timeout", 20)
        response = requests.post(url, data=data, headers=headers, timeout=timeout)
        
        if response.status_code != 200:
            log(f"[SHELLY] HTTP {response.status_code}")
            return (None, None)
        
        result = response.json()
        if not result.get('isok'):
            log("[SHELLY] API returned isok=False")
            return (None, None)
        
        device_data = result.get('data', {})
        if not device_data.get('online'):
            log("[SHELLY] Device offline")
            return (None, None)
        
        # Extract sensor data
        status = device_data.get('device_status', {})
        
        temperature = status.get('temperature:0', {}).get('tC')
        humidity = status.get('humidity:0', {}).get('rh')
        
        if temperature is not None:
            log(f"[SHELLY] temp={fmt1(temperature)}°C, humidity={fmt1(humidity)}%")
        
        return (float(temperature) if temperature is not None else None,
                float(humidity) if humidity is not None else None)
        
    except requests.Timeout:
        log("[SHELLY] Request timeout")
        return (None, None)
    except Exception as e:
        log(f"[SHELLY] Error: {e}")
        return (None, None)






