# Control Principles & Functions

**Flow Controller v4.6 - Technical Reference**

This document explains the core principles, main functions, and control logic of the 2-Hour Lookahead heating flow temperature controller with fixed monitoring display.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Control Philosophy](#control-philosophy)
3. [Main Functions](#main-functions)
4. [Control Algorithm](#control-algorithm)
5. [Weather Curve](#weather-curve)
6. [Trajectory Prediction](#trajectory-prediction)
7. [DHW Guard](#dhw-guard)
8. [Configuration Parameters](#configuration-parameters)

---

## System Overview

### **Hardware Components**
- **Heat Source**: Mitsubishi Ecodan/Geodan heat pump
- **Heat Distribution**: LK Systems hydronic floor heating
- **Control Interface**: MELCloud API (heat pump) + LK Systems API (room sensors/valves)
- **Sensors**: 11 room thermostats, outdoor temperature, flow/return temperature, DHW tank

### **Control Objective**
Maintain weighted average indoor temperature at **23.6°C** with:
- Minimal oscillation (±0.05°C target)
- No heat pump short-cycling (min 1 hour between changes)
- Efficient energy use (minimal API calls, optimal flow temperatures)
- Robustness to external factors (sun, wind, DHW cycles, occupancy)

### **Update Cycle**
- Script runs: **Every 10 minutes** (monitoring/logging)
- Flow changes applied: **Once per hour at XX:00** (hourly rhythm)
- API calls: **24 per day** (one per hour)

---

## Control Philosophy

### **Core Principles**

#### **1. Trajectory-Based Prediction**
> *"The house tells you what it needs through its temperature trajectory"*

Instead of trying to model the house or learn its characteristics, we directly measure the temperature change rate and predict forward:

```
Current: 23.55°C
Slope: +0.06°C/hour (warming)
Predicted (1h): 23.61°C
Predicted error: 23.60 - 23.61 = -0.01°C (slight overshoot)
Action: Reduce flow slightly
```

**Why it works:**
- Floor heating has long thermal time constants (hours)
- Past 2-hour trajectory is good predictor of next hour
- No need for complex models or adaptive learning

#### **2. Hourly Rhythm = Natural Damping**
> *"Match controller frequency to system dynamics"*

House thermal inertia means temperature changes slowly:
- Cooling rate when OFF: ~0.06°C/hour (at 10°C outdoor)
- Warming rate with floor heating: ~0.10-0.15°C/hour
- Hourly adjustments perfectly match this timescale

**Benefits:**
- No hysteresis needed (hourly rhythm prevents chatter)
- No outdoor transition detection needed (adapts naturally)
- No soft landing complexity (single steps prevent overshoot)

#### **3. Single-Step Changes**
> *"±1°C per hour is sufficient for slow thermal systems"*

Maximum change: ±1°C per hour (or OFF↔28°C)

**Example sequence:**
```
08:00 → 32°C (too warm, step down)
09:00 → 31°C (step down)
10:00 → 30°C (step down)
11:00 → 30°C (hold - stable)
12:00 → 30°C (hold - stable)
```

**Why sufficient:**
- Each 1°C flow change → ~0.05-0.10°C/hour temperature change
- Can correct typical errors in 3-6 hours
- Prevents overshoot that larger steps would cause

#### **4. Weather Curve as Baseline**
> *"Start from physics, adjust from behavior"*

Weather curve provides reference flow based on outdoor temperature:
- -15°C outdoor → 33-38°C flow range
- 0°C outdoor → 29-36°C flow range
- 10°C outdoor → 28-30°C flow range or OFF

Algorithm adjusts from reference based on predicted error.

---

## Main Functions

### **1. `hourly_rhythm_decision()`**
**Location**: `control_logic.py`

**Purpose**: Main control decision function called every 10 minutes.

**Inputs**:
- `outdoor_ema`: Smoothed outdoor temperature (°C)
- `avg_temp`: Weighted average room temperature (°C)
- `setpoint`: Target temperature (23.6°C)
- `trajectory_slope`: Temperature change rate (°C/hour)
- `traj_status`: Trajectory calculation status ("ok" or "insufficient_data")
- `last_flow`: Last APPLIED flow from XX:00 timestamp (°C) - v4.4 fix
- `dhw_active`: Whether DHW heating is active (bool)

**Outputs**:
- `flow_cmd`: Commanded flow temperature (°C)
- `predicted_temp`: Predicted temperature 2h ahead (°C) - v4.3 change
- `predicted_error`: Predicted error = target - predicted (°C)
- `reference_flow`: Weather curve reference (°C)
- `adjustment`: Flow adjustment applied (°C)
- `decision_zone`: Control zone (STABLE or NORMAL)
- `comment`: Descriptive text for logging

**Algorithm (v4.1 - Pure & Simple)**:
```python
1. Get weather curve (min, ref, max) for outdoor temp
2. Calculate current_error = setpoint - avg_temp
3. Predict temperature 1 hour ahead using trajectory
4. Calculate predicted_error = setpoint - predicted_temp

5. Determine zone (TWO ZONES ONLY):
   - STABLE: |current_error| ≤ 0.05 AND |predicted_error| ≤ 0.05
   - NORMAL: everything else

6. Determine action based on zone:
   - STABLE → hold last_flow
   - NORMAL → ±1°C based on predicted_error direction
     • pred_error > +0.05 → direction = +1 (need heat)
     • pred_error < -0.05 → direction = -1 (reduce heat)
     • else → direction = 0 (hold)

7. Apply single-step:
   - If OFF and need heat → turn ON to 28°C
   - If ON and need heat → flow += 1 (up to max)
   - If ON and reduce → flow -= 1 (or OFF if below min)
   - Else → hold

8. Enforce weather curve minimum:
   - If OFF and weather_min > 20 → force ON to weather_min

9. Return flow_cmd and metadata
```

**Example**:
```python
# Inputs:
outdoor_ema = 8.0°C
avg_temp = 23.55°C
setpoint = 23.60°C
trajectory_slope = +0.06°C/h
last_flow = 30°C

# Calculation:
predicted_temp = 23.55 + 0.06 = 23.61°C
predicted_error = 23.60 - 23.61 = -0.01°C

# Decision:
Zone: STABLE (error small, prediction close)
Action: Hold at 30°C

# Output:
flow_cmd = 30°C
decision_zone = "STABLE"
comment = "Stable near target - hold"
```

---

### **2. `get_weather_curve()`**
**Location**: `control_logic.py`

**Purpose**: Get min/ref/max flow temperatures for given outdoor temperature using linear interpolation.

**Input**: `outdoor_temp` (°C)

**Output**: `(min_flow, reference_flow, max_flow)` (°C)

**Algorithm**:
```python
1. Find two anchor points bracketing outdoor_temp
2. Linear interpolation:
   ratio = (outdoor_temp - anchor0) / (anchor1 - anchor0)
   min_flow = min0 + ratio × (min1 - min0)
   ref_flow = ref0 + ratio × (ref1 - ref0)
   max_flow = max0 + ratio × (max1 - max0)
```

**Example**:
```python
# Anchors:
# (0°C,  29, 31, 36)
# (5°C,  28, 29, 33)

outdoor_temp = 2.5°C  # Midpoint

# Interpolation:
ratio = (2.5 - 0) / (5 - 0) = 0.5
min_flow = 29 + 0.5 × (28 - 29) = 28.5°C
ref_flow = 31 + 0.5 × (29 - 31) = 30.0°C
max_flow = 36 + 0.5 × (33 - 36) = 34.5°C

# Output: (28.5, 30.0, 34.5)
```

**Physical Meaning**:
- **min_flow**: Minimum flow for this outdoor temp. Below this → must turn OFF (not enough heat demand).
- **reference_flow**: Baseline for steady state. Start here when turning ON or when stable.
- **max_flow**: Maximum allowed for this outdoor temp. Prevents overheating when outdoor is mild.

---

### **3. `calculate_trajectory()`**
**Location**: `control_logic.py`

**Purpose**: Calculate temperature change rate using linear regression over past readings.

**Inputs**:
- `temp_history`: List of (timestamp, temperature) tuples
- `lookback_readings`: Number of readings to analyze (default 12 = 2 hours)

**Output**: `(slope_per_hour, status)`
- `slope_per_hour`: °C/hour (positive = warming, negative = cooling)
- `status`: "ok" or "insufficient_data"

**Algorithm**:
```python
1. Extract last N readings
2. Perform linear regression:
   - x = [0, 1, 2, ..., n-1]  # Time indices
   - y = [temp0, temp1, ..., tempN]  # Temperatures
   
3. Calculate slope:
   slope = (n × Σ(xy) - Σx × Σy) / (n × Σ(x²) - (Σx)²)
   
4. Convert to °C/hour:
   slope_per_hour = slope × 6  # 6 readings per hour (10-min intervals)
```

**Example**:
```python
# Past 2 hours (12 readings):
Time:   0   10  20  30  40  50  60  70  80  90 100 110 (min)
Temp: 23.5 23.5 23.5 23.6 23.6 23.6 23.6 23.7 23.7 23.7 23.8 23.8 (°C)

# Linear regression:
Slope per reading: 0.010°C per 10-min
Slope per hour: 0.010 × 6 = +0.060°C/h

# Interpretation: Warming at 0.06°C/hour
```

**Physical Meaning**:
- **Positive slope**: House is warming (heating > losses)
- **Negative slope**: House is cooling (heating < losses)
- **Magnitude**: Rate of change reveals system dynamics

---

### **4. `check_dhw_guard()`**
**Location**: `control_logic.py`

**Purpose**: Detect Domestic Hot Water heating cycles (for CSV logging and valve guard only - no flow moderation in v4.1).

**Inputs**:
- `tank_current`: Current DHW tank temperature (°C)
- `prev_tank_temp`: Previous tank temperature (°C)
- `prev_dhw_start_time`: ISO timestamp when DHW started (or None)
- `current_time`: Current datetime

**Output**: `(dhw_active, dhw_start_time)`

**Algorithm**:
```python
1. Calculate temp_rise = tank_current - prev_tank_temp

2. If temp_rise ≥ 3.0°C:
   # DHW heating detected
   
   If prev_dhw_start_time is None:
      # Just started
      Return (True, current_time.isoformat())
   Else:
      # Check timeout
      elapsed = current_time - prev_dhw_start_time
      If elapsed > 90 minutes:
         # Timeout: force DHW off
         Return (False, None)
      Else:
         # Continue DHW
         Return (True, prev_dhw_start_time)

3. Else:
   # Temp not rising: DHW ended
   Return (False, None)
```

**Why Important**:
- During DHW cycles, heat pump diverts heat to tank
- Floor heating temporarily has no heat input
- **v4.1**: No flow moderation (single steps are inherently gentle)
- **CSV logging**: Track DHW disturbances in data
- **Valve guard**: Close Plan 2 valves to prevent noise
- **Timeout**: 90 minutes prevents stuck state

**DHW Valve Guard** (in `dhw_valve_guard.py`):
- When `dhw_active = True`: Close Plan 2 (2nd floor) valves to prevent noise
- When `dhw_active = False`: Restore valve positions
- Backup state saved in temporary file `dhw_valve_state.txt`

---

### **5. `compute_weighted_avg()`**
**Location**: `lk_systems.py`

**Purpose**: Calculate weighted average of room temperatures (de-emphasize solar-heated rooms).

**Input**: `room_map` (dict of room_name → temperature)

**Output**: `weighted_avg` (°C)

**Algorithm**:
```python
1. Calculate simple average (all rooms equal weight)

2. For each room:
   If temp > simple_avg + 0.5°C:
      # This room is significantly warmer (probably solar gain)
      weight = 0.5
   Else:
      weight = 1.0

3. Weighted average = Σ(temp × weight) / Σ(weight)
```

**Example**:
```python
Rooms:
  Vardagsrum (living): 24.7°C  # South-facing, solar heated
  Allrum: 23.5°C
  Big sovrum: 23.4°C
  Small sovrum: 23.6°C
  ... (others similar)

Simple avg: 23.9°C
Vardagsrum is 24.7 - 23.9 = 0.8°C above avg → weight = 0.5

Weighted avg: (24.7×0.5 + 23.5×1.0 + ... ) / (0.5 + 1.0 + ...) ≈ 23.7°C
```

**Why Important**:
- Solar gain in south-facing rooms shouldn't drive down flow temperature
- Weighted average better represents actual heating need

---

## Control Algorithm

### **State Machine (Simplified)**

```
┌─────────────────────────────────────────────────────────┐
│                    HOURLY RHYTHM                        │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │   Every 10 minutes   │
              │   (monitoring/log)   │
              └──────────────────────┘
                          │
              ┌───────────┴───────────┐
              │  At top of hour?      │
              │  (XX:00 - XX:10)      │
              └───────────┬───────────┘
                    Yes   │   No
            ┌─────────────┴─────────────┐
            ▼                           ▼
    ┌───────────────┐          ┌────────────────┐
    │ APPLY FLOW    │          │ MONITOR ONLY   │
    │ (send to HP)  │          │ (log, no send) │
    └───────────────┘          └────────────────┘
            │
            ▼
    ┌───────────────────────────────────────────┐
    │  DECISION ZONES (v4.1: TWO ONLY)          │
    ├───────────────────────────────────────────┤
    │  STABLE:  ±0.05°C → Hold                 │
    │  NORMAL:  All else → ±1°C single-step    │
    │           (no emergency - trust trajectory)│
    └───────────────────────────────────────────┘
```

### **Decision Tree**

```
Start
 │
 ├─ Is avg_temp available?
 │   No → Fallback: flow = 28°C
 │   Yes ↓
 │
 ├─ Calculate trajectory_slope from past 2 hours
 │
 ├─ Predict temperature 1 hour ahead
 │
 ├─ Get weather curve (min, ref, max) for outdoor_ema
 │
 ├─ ZONE CHECK (v4.1: TWO ZONES ONLY):
 │   │
 │   ├─ STABLE? (|curr_err| ≤ 0.05 AND |pred_err| ≤ 0.05)
 │   │   Yes → flow = last_flow (hold)
 │   │   No ↓
 │   │
 │   └─ NORMAL (everything else):
 │       │
 │       ├─ pred_err > +0.05? → Direction: +1 (need heat)
 │       ├─ pred_err < -0.05? → Direction: -1 (reduce heat)
 │       └─ else             → Direction: 0 (hold)
 │
 ├─ APPLY DIRECTION (single-step):
 │   │
 │   ├─ Currently OFF (flow = 20)?
 │   │   ├─ Direction > 0 → Turn ON: flow = 28°C
 │   │   └─ Direction ≤ 0 → Stay OFF: flow = 20°C
 │   │
 │   └─ Currently ON (flow ≥ 28)?
 │       ├─ Direction > 0 → Increase: flow += 1 (max = max_flow)
 │       ├─ Direction < 0 → Decrease: flow -= 1
 │       │   └─ If flow < min_flow OR < 28 → Turn OFF: flow = 20°C
 │       └─ Direction = 0 → Hold: flow = last_flow
 │
 ├─ ENFORCE WEATHER MINIMUM:
 │   If OFF AND weather_min > 20 → Force ON to weather_min
 │
 └─ Return: (flow, pred_temp, pred_err, ref_flow, adj, zone, comment)
```

---

## Weather Curve

### **Purpose**
Provide baseline flow temperature range based on outdoor conditions.

### **Structure**
```python
(outdoor_temp, min_flow, reference_flow, max_flow)
```

### **Current Curve (v4.1)**
```
Outdoor  │  Min  │  Ref  │  Max  │  Interpretation
─────────┼───────┼───────┼───────┼───────────────────────────
  -15°C  │  33°C │  35°C │  38°C │  Extreme cold (continuous high flow)
  -10°C  │  32°C │  34°C │  38°C │  Very cold
   -5°C  │  31°C │  33°C │  38°C │  Cold
    0°C  │  29°C │  31°C │  36°C │  Cool
    5°C  │  28°C │  29°C │  33°C │  Mild (ON/OFF borderline)
   10°C  │  20°C │  28°C │  30°C │  Warm (prefer OFF, 28-30 if needed)
   15°C  │  20°C │  20°C │  28°C │  Very warm (OFF preferred)
   20°C  │  20°C │  20°C │  20°C │  Hot (always OFF)
```

### **Usage in Control**

**Example 1: Cold outdoor (-5°C)**
```
Weather curve: min=31, ref=33, max=38
Current flow: 34°C
Predicted error: +0.10°C (too cold)
Action: +1°C → new flow = 35°C ✓ (within 31-38 range)
```

**Example 2: Mild outdoor (8°C)**
```
Weather curve: min=22, ref=28, max=31 (interpolated)
Current flow: 28°C
Predicted error: -0.12°C (too warm)
Action: -1°C → new flow = 27°C
Check: 27 < min(22) → No, 27 > 22 ✓
Check: 27 < 28 (HP min) → No ✓
Result: Apply 27°C
```

**Example 3: Warm outdoor (11°C)**
```
Weather curve: min=20, ref=28, max=30
Current flow: 28°C
Predicted error: -0.15°C (too warm)
Action: -1°C → new flow = 27°C
Check: 27 < 28 (HP min) → Yes!
Result: Turn OFF (20°C)
```

---

## Trajectory Prediction

### **Why Trajectory?**

Temperature trajectory reveals system state:
- **Slope = 0**: Steady state (heating = losses)
- **Slope > 0**: Heating > losses (warming)
- **Slope < 0**: Heating < losses (cooling)

**Key Insight**: 
> Extrapolating past trend is more reliable than trying to model house physics or learn coefficients.

### **Method: Linear Regression**

**Data**: Last 12 readings (2 hours) at 10-minute intervals

**Why 2 hours?**
- Long enough to filter noise
- Short enough to be recent/relevant
- Captures response to last flow change

**Calculation**:
```
Given: (t₀, T₀), (t₁, T₁), ..., (t₁₁, T₁₁)

Fit: T = a + b×t

Slope b = temperature change per reading
Slope_per_hour = b × 6 readings/hour
```

### **Prediction**

```python
predicted_temp = current_temp + (slope_per_hour × lookahead_hours)

# v4.0: lookahead = 1 hour
predicted_temp = current_temp + slope_per_hour
```

### **Predicted Error**

```python
predicted_error = setpoint - predicted_temp

# Interpretation:
# pred_err > 0 → Will be too cold (need more heat)
# pred_err < 0 → Will be too hot (reduce heat)
# pred_err ≈ 0 → Will be just right (stable)
```

### **Example**

```
Current time: 10:00
Current temp: 23.55°C
Setpoint: 23.60°C

Past 2 hours:
  08:00: 23.40°C
  08:10: 23.41°C
  ...
  09:50: 23.54°C
  10:00: 23.55°C

Linear regression:
  Slope: +0.075°C/hour (warming)

Prediction for 11:00:
  Predicted temp = 23.55 + 0.075 = 23.625°C
  Predicted error = 23.60 - 23.625 = -0.025°C

Decision:
  Zone: STABLE (pred_err < 0.05)
  Action: Hold current flow
```

---

## DHW Guard

### **Purpose**
1. Detect when heat pump is heating DHW tank (not floor)
2. Moderate controller response during DHW cycles
3. Close 2nd-floor valves during DHW to prevent noise

### **Detection Method**

**Trigger**: Tank temperature rise ≥ 3°C between readings (10 minutes)

**Example**:
```
09:50: tank = 42°C
10:00: tank = 45°C  → Rise = 3°C → DHW active!
```

**Timeout**: 90 minutes maximum
- If DHW cycle doesn't end within 90 min → force off
- Prevents getting stuck if tank sensor fails

### **Effects When DHW Active (v4.1)**

**1. CSV Logging**
- `dhw_active` column set to 1 for easy filtering in analysis
- Track DHW disturbances and their effect on temperature

**2. Valve Closure (dhw_valve_guard.py)**
```python
if dhw_active:
    # Close Plan 2 valves (2nd floor rooms)
    set_temperature(Bedroom1, 5°C)  # Close valve
    set_temperature(Bedroom2, 5°C)
    set_temperature(Bath2, 5°C)
    # Save original temps to restore later
else:
    # Restore original temperatures
    restore_temperatures()
```

**Why close valves?**
- DHW cycles cause hot water flow through pipes
- 2nd floor rooms hear flow noise through pipes/radiators
- Closing valves stops flow → eliminates noise

**Restoration**:
- Original temperatures backed up in `dhw_valve_backup_temp.txt`
- Restored automatically when DHW cycle ends
- File overwritten each DHW cycle (no accumulation)

---

## Configuration Parameters

### **Key Tunable Parameters** (in `config.py`)

#### **Control**
```python
target_room_temp = 23.6  # Comfort setpoint (°C)
```

#### **Application Rhythm**
```python
monitor_interval_minutes = 10   # How often script runs
apply_interval_minutes = 60     # How often flow is applied
max_step_per_hour = 1           # Maximum ±1°C per hour
apply_window_minutes = 10       # Apply window at top of hour
```

#### **Control Zones (v4.1 - Simplified)**
```python
stable_error = 0.05          # ±0.05°C = stable zone
stable_pred_error = 0.05     # Predicted within ±0.05°C
# No emergency_error in v4.1 - trust trajectory
```

#### **Prediction**
```python
lookback_readings = 12       # 2 hours of history
lookahead_minutes = 60       # 1 hour ahead prediction
```

#### **EMA (Exponential Moving Average)**
```python
alpha_outdoor = 0.058        # Smoothing for outdoor temp
# Effective window ≈ 2-3 hours
```

#### **DHW Guard**
```python
enable = True                    # Enable DHW guard
temp_rise_threshold = 3.0        # Min rise to detect DHW (°C)
timeout_minutes = 90             # Force DHW off after 90 min
```

#### **Flow Limits**
```python
off = 20.0      # OFF temperature (°C)
min_on = 28.0   # Minimum ON (heat pump limit)
max = 38.0      # Safety maximum
```

---

## Summary

### **What Makes v4.1 Pure & Simple**

1. **One Update Rhythm** (hourly)
   - Matches system dynamics
   - Natural damping (no hysteresis)

2. **One Prediction Method** (trajectory)
   - Direct measurement of behavior
   - No complex models or learning

3. **One Decision Rule** (single-step)
   - ±1°C or OFF↔28°C
   - Clear, predictable behavior

4. **One Baseline** (weather curve with minimum)
   - Physics-based starting point
   - Always enforced (no exceptions)

5. **Two Zones Only**
   - STABLE (hold) and NORMAL (single-step)
   - No emergency, no DHW moderation
   - Trust the trajectory

### **Performance Expectations**

- **Steady state**: ±0.05°C around 23.60°C
- **Convergence**: 3-6 hours from large error
- **API calls**: 24 per day (6× less than v3.x)
- **Robustness**: Handles outdoor swings, DHW cycles, solar gain
- **Coherence**: All paths respect weather minimum

### **Philosophy**

> *"In complex systems, simplicity emerges not from adding intelligence, but from removing assumptions."*

v4.1 achieves this by:
- **Trusting trajectory** (not panicking on current error)
- **Respecting physics** (weather curve minimum always enforced)
- **Matching dynamics** (hourly rhythm = house thermal time constant)
- **No exceptions** (every path follows the same rules)

The result: invisible control that keeps the house stable without abrupt changes or oscillations.

---

**Version**: 4.6  
**Last Updated**: 2025-11-09  
**Author**: AI + User iterative development  
**License**: Personal use

