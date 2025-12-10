#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MELCloud integration for heat pump control.
"""

import aiohttp
import pymelcloud
from typing import Dict, Optional

from utils import log, fmt1
from config import CONFIG


class HeatPumpController:
    """Controller for MELCloud heat pump operations."""
    
    def __init__(self):
        self.device = None
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with timeout."""
        if self.session is None or self.session.closed:
            network_config = CONFIG["network"]
            timeout = aiohttp.ClientTimeout(total=network_config["timeout"])
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def _close_session(self) -> None:
        """Close aiohttp session if open."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _connect_and_get_device(self, email: str, password: str):
        """
        Connect to MELCloud and get the Air-to-Water heat pump device.
        
        Args:
            email: MELCloud account email
            password: MELCloud account password
        
        Returns:
            Heat pump device object
        
        Raises:
            Exception: If no ATW device found
        """
        session = await self._get_session()
        token = await pymelcloud.login(email, password, session=session)
        devices = await pymelcloud.get_devices(token, session=session)
        
        # Find Air-to-Water devices
        atw_list = []
        if isinstance(devices, dict):
            key = getattr(pymelcloud, "DEVICE_TYPE_ATW", "atw")
            atw_list = (
                devices.get(key) or
                devices.get("atw") or
                devices.get("AirToWater") or
                []
            )
        elif isinstance(devices, (list, tuple)):
            for device in devices:
                device_type = (
                    getattr(device, "device_type", None) or
                    getattr(device, "DeviceType", None)
                )
                if isinstance(device_type, str) and device_type.lower() in ("atw", "airtowater"):
                    atw_list.append(device)
            if not atw_list and devices:
                atw_list = [devices[0]]
        
        if not atw_list:
            raise Exception("No ATW (Air to Water) heat pump found")
        
        device = atw_list[0]
        await device.update()
        self.device = device
        return device
    
    async def get_outdoor_temperature(self, email: str, password: str) -> Optional[float]:
        """
        Get outdoor temperature from heat pump.
        
        Args:
            email: MELCloud account email
            password: MELCloud account password
        
        Returns:
            Outdoor temperature (°C) or None if unavailable
        """
        try:
            device = await self._connect_and_get_device(email, password)
            
            # Try multiple locations for outdoor temp
            val = getattr(device, "outside_temperature", None)
            if val is not None:
                log(f"MEL: outdoor via device.outside_temperature = {fmt1(val)}°C")
                return float(val)
            
            status = getattr(device, "status", None)
            if isinstance(status, dict) and "OutdoorTemperature" in status:
                val = status.get("OutdoorTemperature")
                log(f"MEL: outdoor via status['OutdoorTemperature'] = {fmt1(val)}°C")
                return float(val)
            
            device_conf = getattr(device, "_device_conf", None)
            if isinstance(device_conf, dict):
                dev = device_conf.get("Device") or {}
                if isinstance(dev, dict) and "OutdoorTemperature" in dev:
                    val = dev.get("OutdoorTemperature")
                    log(f"MEL: outdoor via conf['Device']['OutdoorTemperature'] = {fmt1(val)}°C")
                    return float(val)
            
            log("MEL: outdoor temperature not found.")
            return None
            
        finally:
            await self._close_session()
    
    async def get_key_temperatures(self, email: str, password: str) -> Dict[str, Optional[float]]:
        """
        Get key temperatures from heat pump (flow, return, tank).
        
        Args:
            email: MELCloud account email
            password: MELCloud account password
        
        Returns:
            Dict with keys: flow, return, tank_current, tank_target
        """
        try:
            device = await self._connect_and_get_device(email, password)
            
            flow_temp = return_temp = tank_current = tank_target = None
            
            zones = getattr(device, "zones", []) or []
            if zones:
                zone0 = zones[0]
                flow_temp = getattr(zone0, "flow_temperature", None)
                return_temp = getattr(zone0, "return_temperature", None)
            
            tank_current = getattr(device, "tank_temperature", None)
            tank_target = getattr(device, "target_tank_temperature", None)
            
            log(
                f"MEL: zone0 flow={fmt1(flow_temp)}°C, return={fmt1(return_temp)}°C; "
                f"tank_current={fmt1(tank_current)}°C, tank_target={fmt1(tank_target)}°C"
            )
            
            return {
                "flow": float(flow_temp) if flow_temp is not None else None,
                "return": float(return_temp) if return_temp is not None else None,
                "tank_current": float(tank_current) if tank_current is not None else None,
                "tank_target": float(tank_target) if tank_target is not None else None,
            }
            
        finally:
            await self._close_session()
    
    async def set_flow_temperature_all_zones_int(
        self,
        email: str,
        password: str,
        temperature_c: float
    ) -> bool:
        """
        Set flow temperature for all zones.
        
        Args:
            email: MELCloud account email
            password: MELCloud account password
            temperature_c: Target flow temperature (°C), will be rounded to int
        
        Returns:
            True if successful, False otherwise
        """
        try:
            device = await self._connect_and_get_device(email, password)
            target = int(round(float(temperature_c)))
            
            zones = getattr(device, "zones", []) or []
            if not zones and hasattr(device, "set"):
                await device.set({"target_flow_temperature": target})
                log(f"MEL: device-level flow set to {target}°C")
                return True
            
            ok = 0
            for zone in zones:
                await zone.set_target_heat_flow_temperature(target)
                ok += 1
            
            log(f"MEL: set flow to {target}°C on {ok} zone(s).")
            return ok > 0
            
        except Exception as e:
            log(f"[ERR] Failed to set flow temperature: {e}")
            return False
        finally:
            await self._close_session()
    
    async def set_tank_temperature(self, email: str, password: str, temperature: float) -> bool:
        """
        Set tank target temperature (currently unused).
        
        Args:
            email: MELCloud account email
            password: MELCloud account password
            temperature: Target tank temperature (°C)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            device = await self._connect_and_get_device(email, password)
            await device.set({"target_tank_temperature": float(temperature)})
            log(f"MEL: set tank target temperature to {float(temperature):.1f}°C")
            return True
        except Exception as e:
            log(f"[ERR] Failed to set tank temperature: {e}")
            return False
        finally:
            await self._close_session()





