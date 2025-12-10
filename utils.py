#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Utility functions for the heating flow controller.
"""

import datetime as dt
from typing import Optional


def fmt1(x) -> str:
    """Format a number to 1 decimal place, or return empty string if invalid."""
    try:
        return f"{float(x):.1f}"
    except (ValueError, TypeError):
        return ""


def fmt2(x) -> str:
    """Format a number to 2 decimal places, or return empty string if invalid."""
    try:
        return f"{float(x):.2f}"
    except (ValueError, TypeError):
        return ""


def log(msg: str) -> None:
    """Print a timestamped log message."""
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def hour_key_from_dt(d: dt.datetime) -> str:
    """Generate hour key string from datetime (YYYYMMDDHH)."""
    return d.strftime("%Y%m%d%H")


def hour_key_from_ts_str(ts_iso_min: str) -> Optional[str]:
    """Generate hour key from ISO timestamp string (YYYY-MM-DDTHH:MM)."""
    try:
        dt_obj = dt.datetime.fromisoformat(ts_iso_min)
        return hour_key_from_dt(dt_obj)
    except (ValueError, TypeError):
        return None


def ema_update(prev: Optional[float], value: float, alpha: float) -> float:
    """
    Update exponential moving average.
    
    Args:
        prev: Previous EMA value (None for first update)
        value: New value to incorporate
        alpha: Smoothing factor (0-1)
    
    Returns:
        Updated EMA value
    """
    if prev is None:
        return value
    return alpha * value + (1.0 - alpha) * prev


def duty_step(prev_acc: Optional[float], duty_fraction: float) -> tuple[float, bool]:
    """
    Update duty cycle accumulator and check if ON threshold reached.
    
    Args:
        prev_acc: Previous accumulator value (0-1)
        duty_fraction: Duty fraction to add (0-1)
    
    Returns:
        (new_accumulator, should_be_on)
        - new_accumulator: Updated accumulator (wraps at 1.0)
        - should_be_on: True if accumulator wrapped (time to turn ON)
    """
    acc = float(prev_acc or 0.0) + float(duty_fraction)
    if acc >= 1.0:
        return acc - 1.0, True
    return acc, False

