# Flow Controller - Complete Changelog

**Project**: Hydronic Floor Heating Flow Temperature Controller  
**Hardware**: LK Systems floor heating + Mitsubishi Ecodan/Geodan heat pump via MELCloud  
**Goal**: Maintain indoor temperature at 23.6°C with minimal oscillation and heat pump short-cycling  

---

## Version 5.4 - Simplified Control Logic (2025-11-14) 🎯

### **REMOVED CONSECUTIVE PAUSE MECHANISM**

**User Request:**
> "let's remove it in v5.4 and make the logic more coherent."

**Analysis:**
After analyzing v5.3 logs, the consecutive pause mechanism:
- Triggered only 2 times in ~24 hours
- Added complexity for limited benefit
- Single-step adjustments (±1°C/hour) are already conservative
- Trajectory prediction accounts for thermal lag
- Weather curve bounds provide natural limits
- STABLE zone already holds when near target

**v5.4 Solution:**
> **"Simpler is better. Trust the trajectory prediction and single-step logic."**

**What Changed:**

**1. Removed PAUSE zone from control logic**
```python
# control_logic.py - REMOVED (lines 204-269)
# ===== DIRECTIONAL PAUSE: After 2 consecutive steps in same direction =====
# ... entire pause detection and handling logic removed
```

**2. Removed flow history tracking**
```python
# state_manager.py - REMOVED
# Get flow from 2 and 3 hours ago (for pause detection after consecutive steps)
flow_2h_ago = None
flow_3h_ago = None
# ... tracking logic removed
```

**3. Simplified function signatures**
```python
# control_logic.py
def hourly_rhythm_decision(
    # ... other params ...
    last_flow: float,
    # REMOVED: flow_2h_ago: Optional[float],
    # REMOVED: flow_3h_ago: Optional[float],
    dhw_active: bool,
) -> Tuple[float, float, float, float, float, str, str]:
```

**4. Updated return values**
```python
# state_manager.py
# BEFORE: return (ema_tout, last_flow_cmd, last_hourly_flow, flow_2h_ago, flow_3h_ago, temp_history, prev_tank_temp, dhw_start_time)
# AFTER:  return (ema_tout, last_flow_cmd, last_hourly_flow, temp_history, prev_tank_temp, dhw_start_time)
```

**Control Zones:**
- **BEFORE (v5.3)**: Three zones - PAUSE (directional), STABLE (hold optimal), NORMAL (single-step)
- **AFTER (v5.4)**: Two zones - STABLE (hold optimal), NORMAL (single-step)

**Files Modified:**
- `control_logic.py`: 
  - Removed pause detection logic (lines 204-269)
  - Removed `flow_2h_ago` and `flow_3h_ago` parameters
  - Updated docstring to v5.4
- `state_manager.py`: 
  - Removed flow history tracking (flow_2h_ago, flow_3h_ago)
  - Updated return tuple
  - Updated docstring to v5.4
- `melcloud_flow_controller.py`: 
  - Removed flow_2h_ago and flow_3h_ago from read_last_state unpacking
  - Removed from hourly_rhythm_decision call
  - Updated docstring to v5.4
- `config.py`: VERSION = "5.4"
- `README.md`: Added v5.4 section
- `CHANGELOG.md`: Added v5.4 section

**Benefits:**
- ✅ **Simpler logic** - Easier to understand and maintain
- ✅ **Less complexity** - Fewer edge cases to handle
- ✅ **More coherent** - Single-step + trajectory + weather bounds provide sufficient control
- ✅ **Still safe** - Weather curve min/max still enforced on all decisions
- ✅ **Cleaner code** - Removed ~65 lines of pause detection logic

**Expected Behavior:**
- System now relies on:
  1. Single-step adjustments (±1°C/hour) - inherently conservative
  2. Trajectory prediction (2-hour lookahead) - accounts for thermal lag
  3. Weather curve bounds (min/max) - physics-based limits
  4. STABLE zone - holds when near target
- No artificial pauses - system responds immediately to trajectory predictions
- Weather curve min/max still enforced on all decisions

**Learning:**
> "Complexity should be justified by clear benefit. The pause mechanism added complexity but analysis showed minimal impact. Simplifying the logic makes it more maintainable and easier to reason about."

---

## Version 4.7 - Directional Pause (2025-11-09) 🎯

### **SMARTER PAUSE - Allow Opposite Direction Corrections**

**User Request:**
> "I forgot to say I want after 2 consecutive increase or decrease in one direction, pausing from increment in the same direction. If it would be a different direction it would be allowed. And as always weather curve max and min have the 1st prio."

**Problem with v4.6:**

User's log showed the pause was too restrictive:
```csv
15:00,29°C,NORMAL,"+1°C (pred cold +0.45°C)"
16:00,29°C,PAUSE,"After 20→28→29; hold at 29°C"
     BUT predicting hot -0.35°C! Should allow -1°C!
```

After 2 consecutive increases (20→28→29), system paused at 29°C even though it was predicting hot and wanted to decrease. The pause blocked ALL actions, preventing necessary corrections.

**v4.7 Solution:**
> **"Pause from continuing, not from correcting."**

After detecting 2 consecutive steps in the same direction:
- **PAUSE** if desired action would continue in same direction (risk of overshoot)
- **ALLOW** if desired action is opposite direction (enables correction)
- **ALLOW** if desired action is stable/hold (not same direction)

**How It Works:**

```python
# control_logic.py - Directional Pause

if step1_direction == step2_direction:
    # 2 consecutive steps detected (e.g., 28→29→30, both +1)
    
    # Determine what we WANT to do based on prediction
    if predicted_error > 0.05:
        desired_direction = +1  # Want to increase (predicting cold)
    elif predicted_error < -0.05:
        desired_direction = -1  # Want to decrease (predicting hot)
    else:
        desired_direction = 0   # Want to hold (predicting stable)
    
    # Only PAUSE if desired direction matches momentum direction
    if desired_direction == step2_direction:
        # PAUSE: Would continue in same direction → risk of overshoot
        return PAUSE
    else:
        # ALLOW: Different direction or stable → let it through
        # Add comment and fall through to STABLE/NORMAL zones
        if desired_direction == -step2_direction:
            comment += "After 2 increases/decreases, but allowing opposite correction"
```

**Example Scenarios:**

**Scenario 1: Block continuing same direction (prevents overshoot)**
```csv
14:00,28°C,NORMAL,"Turn ON"
15:00,29°C,NORMAL,"Pred cold (+0.08°C); +1°C"
16:00,30°C,NORMAL,"Pred cold (+0.12°C); +1°C" ← 2 consecutive increases
17:00,30°C,PAUSE,"Pause from continuing increases" ← Still predicting cold (+0.10°C)
```

**Scenario 2: Allow opposite direction (enables correction)** ✅
```csv
14:00,28°C,NORMAL,"Turn ON"
15:00,29°C,NORMAL,"Pred cold; +1°C"
16:00,30°C,NORMAL,"Pred cold; +1°C" ← 2 consecutive increases
17:00,29°C,NORMAL,"After 2 increases, but allowing opposite; -1°C" ← Now predicting hot (-0.15°C)
```

**Scenario 3: Allow stable (not same direction)**
```csv
14:00,28°C,NORMAL,"Turn ON"
15:00,29°C,NORMAL,"+1°C"
16:00,30°C,NORMAL,"+1°C" ← 2 consecutive increases
17:00,30°C,STABLE,"Stable near target" ← Predicting perfect (0.02°C)
```

**Real User Log Example (v4.6 → v4.7):**

**BEFORE (v4.6 - blocked correction):**
```csv
15:00,29,NORMAL,"+1°C (pred cold +0.45)"
16:00,29,PAUSE,"After 2 increases: 20→28→29°C" ❌
     Pred hot -0.35°C but couldn't decrease!
```

**AFTER (v4.7 - allows correction):**
```csv
15:00,29,NORMAL,"+1°C (pred cold +0.45)"
16:00,28,NORMAL,"After 2 increases, but allowing opposite; -1°C" ✅
     Pred hot -0.35°C → allowed to decrease
```

**Files Modified:**
- `control_logic.py`: 
  - Check desired direction before deciding to pause
  - Only return PAUSE if desired_direction == momentum_direction
  - Otherwise fall through with optional comment
- `config.py`: VERSION = "4.7"
- `melcloud_flow_controller.py`, `state_manager.py`: Updated docstrings
- `README.md`: Added v4.7 section
- `CHANGELOG.md`: Added v4.7 section

**Benefits:**
- ✅ **Prevents overshoot**: Still blocks continuing in same direction
- ✅ **Enables fast recovery**: Allows opposite direction corrections
- ✅ **More responsive**: No artificial delays when correction is needed
- ✅ **Weather enforced**: Min/max constraints still override (physics > strategy)
- ✅ **Symmetric**: Works identically for warming and cooling

**Learning:**
> "Damping is good for preventing overshoot, but shouldn't block corrections.
>  Let momentum carry you past target? Pause. Need to reverse? Allow it immediately."

---

## Version 4.6 - Pause After 2 Consecutive Steps (2025-11-09) 🛑

### **NEW FEATURE - Adaptive Damping to Prevent Overshoot**

**User Request:**
> "I think we just keep the logic and just give it a single step pause after two consecutive decrease or increase in same direction. v4.6 and test"

**Motivation:**

Floor heating systems have significant thermal lag (1-2 hours). After making 2 consecutive adjustments in the same direction, the system builds momentum that can cause overshoot or undershoot. A pause allows the floor to "catch up" and stabilize before continuing.

**Pattern Examples:**

**Ramp-up overshoot:**
```
10:00 → 28°C (Turn ON)
11:00 → 29°C (+1°C, predicting cold)
12:00 → 30°C (+1°C, still predicting cold) ← 2nd consecutive increase
13:00 → Should pause to see if 30°C is enough
```

**Cooling undershoot:**
```
10:00 → 30°C
11:00 → 29°C (-1°C, predicting hot)
12:00 → 28°C (-1°C, still predicting hot) ← 2nd consecutive decrease
13:00 → Should pause to see if 28°C stabilizes
```

**v4.6 Solution:**
> **"Step, step, pause. Let the floor catch up."**

**What Changed:**

**1. Track flow history (3 hours back)**
```python
# state_manager.py
flow_3h_ago = None  # NEW: Track 3rd hourly flow
flow_2h_ago = None  # Already tracked
last_hourly_flow = None  # Already tracked (1h ago)

# Search backward for flows at XX:00 timestamps
for row in reversed(rows):
    if timestamp.endswith(":00"):
        hourly_timestamps_found += 1
        if hourly_timestamps_found == 2:
            flow_2h_ago = get_float(row, "flow_cmd")
        elif hourly_timestamps_found == 3:
            flow_3h_ago = get_float(row, "flow_cmd")
            break
```

**2. Detect 2 consecutive steps**
```python
# control_logic.py - NEW PAUSE ZONE (checked before STABLE/NORMAL)

step1 = flow_2h_ago - flow_3h_ago  # Change from 3h ago to 2h ago
step2 = last_flow - flow_2h_ago    # Change from 2h ago to 1h ago

# Check if both steps are significant (>= 1°C)
if abs(step1) >= 1 and abs(step2) >= 1:
    # Check if both steps in same direction
    step1_direction = 1 if step1 > 0 else -1
    step2_direction = 1 if step2 > 0 else -1
    
    if step1_direction == step2_direction:
        # PAUSE detected
        return (last_flow, ..., "PAUSE", f"Pause after 2 consecutive {direction_name}: {flow_3h_ago}→{flow_2h_ago}→{last_flow}°C")
```

**3. Pass flow_3h_ago through the chain**
```python
# melcloud_flow_controller.py
prev_ema, ..., flow_2h_ago, flow_3h_ago, ... = state_mgr.read_last_state()

# Pass to decision function
flow_cmd, ... = hourly_rhythm_decision(
    ...,
    flow_2h_ago=flow_2h_ago,
    flow_3h_ago=flow_3h_ago,  # NEW parameter
    ...
)
```

**Files Modified:**
- `state_manager.py`: 
  - Added `flow_3h_ago` tracking
  - Updated `read_last_state()` return tuple (7→8 values)
  - Search for 3rd hourly timestamp
- `control_logic.py`: 
  - Added `flow_3h_ago` parameter to `hourly_rhythm_decision()`
  - New PAUSE zone detection (before STABLE/NORMAL)
  - Updated docstring to mention 3 zones
- `melcloud_flow_controller.py`: 
  - Unpack `flow_3h_ago` from `read_last_state()`
  - Pass `flow_3h_ago` to `hourly_rhythm_decision()`
  - Updated docstring
- `config.py`: VERSION = "4.6" with new description
- `README.md`: Updated Features + v4.6 section
- `CHANGELOG.md`: Added v4.6 section

**Expected Behavior:**

**Scenario: Ramp-up during cold spell**
```csv
timestamp,flow_cmd,zone,comment
10:00,28,NORMAL,"Turn ON (28°C)"
11:00,29,NORMAL,"Pred cold (0.08°C); +1°C"
12:00,30,NORMAL,"Pred cold (0.12°C); +1°C"  ← 2nd consecutive increase
13:00,30,PAUSE,"Pause after 2 consecutive increases: 28→29→30°C"  ← Hold 1h
14:00,30,STABLE,"Stable near target"  ← Resume normal control
```

**Scenario: Cooling during warm spell**
```csv
timestamp,flow_cmd,zone,comment
10:00,30,NORMAL,"Hold 30°C"
11:00,29,NORMAL,"Pred hot (-0.07°C); -1°C"
12:00,28,NORMAL,"Pred hot (-0.09°C); -1°C"  ← 2nd consecutive decrease
13:00,28,PAUSE,"Pause after 2 consecutive decreases: 30→29→28°C"  ← Hold 1h
14:00,20,NORMAL,"Turn OFF"  ← Resume, now predicting very hot
```

**Scenario: STABLE overrides pause**
```csv
timestamp,flow_cmd,zone,comment
10:00,28,NORMAL,"Turn ON"
11:00,29,NORMAL,"+1°C"
12:00,30,NORMAL,"+1°C"  ← Would trigger pause next hour
13:00,30,STABLE,"Stable near target"  ← STABLE takes precedence over PAUSE
```

**Benefits:**
- ✅ **Prevents overshoot**: Natural damping after consecutive adjustments
- ✅ **Accounts for lag**: Gives 1-2h for floor to respond
- ✅ **Simple logic**: No complex tuning, just "step, step, pause"
- ✅ **Symmetric**: Works for both warming and cooling
- ✅ **Weather enforced**: Min/max constraints override pause (physics > strategy)
- ✅ **Doesn't interfere**: STABLE zone can still hold optimal flow

**Weather Enforcement Example:**
```csv
Scenario: Cold snap during pause
11:00,29°C,NORMAL,"+1°C (outdoor=6°C, min=28°C)"
12:00,30°C,NORMAL,"+1°C (outdoor=4°C, min=29°C)"
13:00,32°C,PAUSE,"Pause after 2 increases; but weather min=32°C at 1°C outdoor - adjusting to 32°C"
→ Pause detected, but outdoor dropped to 1°C, min curve now requires 32°C
→ System adjusts to 32°C instead of holding at 30°C
```

**Learning:**
> "Floor heating is slow. After 2 moves in same direction, give it time to catch up.
>  But physics-based constraints (weather min/max) always win over strategy."

---

## Version 4.5 - Monitor Only Between Hours (2025-11-08) 📊

### **EFFICIENCY IMPROVEMENT - Decide Once, Monitor 5 Times**

**User Observation:**
> "At every hour the flow_cmd is decided and applied, but in the 10-minute intervals between, we're recalculating and logging decisions that aren't applied. When the decision is made at XX:00, the following intervals should just monitor with the same flow_cmd until the next hour."

**Problem in v4.4:**
- Script runs every 10 minutes (6 times per hour)
- Control decision calculated every 10 minutes
- But flow command only applied once per hour (at XX:00)
- Result: 5 redundant calculations per hour with repetitive log messages

**Real Log Example (v4.4):**
```
00:00 → flow_cmd=20°C, zone=NORMAL, "Turn OFF"     [APPLIED]
00:10 → flow_cmd=20°C, zone=NORMAL, "Turn OFF"     [NOT APPLIED - redundant]
00:20 → flow_cmd=20°C, zone=NORMAL, "Hold OFF"     [NOT APPLIED - redundant]
00:30 → flow_cmd=20°C, zone=NORMAL, "Hold OFF"     [NOT APPLIED - redundant]
00:40 → flow_cmd=20°C, zone=NORMAL, "Hold OFF"     [NOT APPLIED - redundant]
00:50 → flow_cmd=20°C, zone=NORMAL, "Hold OFF"     [NOT APPLIED - redundant]
01:00 → flow_cmd=28°C, zone=NORMAL, "Turn ON"      [APPLIED]
```

**The Issue:**
1. Control logic ran 6 times per hour
2. Same decision logged 5-6 times
3. Comments repeated ("Turn OFF", "Hold OFF", etc.)
4. User couldn't easily see when actual decisions were made
5. Unnecessary CPU usage for redundant calculations

**v4.5 Solution:**
> **"Decide at top of hour. Monitor in between."**

**What Changed:**
- ✅ **XX:00-XX:09**: Full control decision → Apply → Log full comment
- ✅ **XX:10-XX:59**: Skip decision → Use last applied flow → Monitor only
- ✅ **6x efficiency**: Control logic runs once per hour instead of 6 times
- ✅ **Clear logging**: Decision vs. monitoring clearly distinguished
- ✅ **CSV clarity**: `decision_zone="MONITOR"` for monitoring-only rows

**Technical Implementation:**
```python
# melcloud_flow_controller.py

# Check timing BEFORE running control logic
at_top_of_hour = is_top_of_hour(now, window=10)

if at_top_of_hour:
    # TOP OF HOUR (XX:00-XX:09)
    log("[DECISION] Top of hour - running control decision")
    
    # Run full control decision
    flow_cmd, pred_temp, pred_err, ref, adj, zone, comment = hourly_rhythm_decision(...)
    
    # Apply to heat pump
    await set_flow_temperature(flow_cmd)
    log(f"✓ Applied flow={flow_cmd}°C")
    
else:
    # MONITORING (XX:10-XX:59)
    log("[MONITOR] Between hours - monitoring only")
    
    # Use last applied flow
    flow_cmd = last_applied_flow
    
    # Set monitoring values
    decision_zone = "MONITOR"
    comment = f"Monitoring (last applied: {flow_cmd}°C at {hour}:00)"
    
    # Log current state
    log(f"  Last applied: {flow_cmd}°C, next decision at {next_hour}:00")
    log(f"  Current: avg_temp={avg_temp}°C, slope={slope}°C/h")
```

**Files Modified:**
- `melcloud_flow_controller.py`: Restructured to check timing before decision
- `config.py`: VERSION = "4.5"
- `control_logic.py`: Updated docstring ("Called ONLY at XX:00")
- `state_manager.py`: Added note about "MONITOR" decision zone
- `README.md`: Added v4.5 section
- `CHANGELOG.md`: Added v4.5 section

**Expected Log Output:**

**v4.4 (redundant):**
```
00:00 [APPLY] flow=20°C "Turn OFF"
00:10 [MONITOR] flow=20°C "Turn OFF" (not applied, but calculated)
00:20 [MONITOR] flow=20°C "Hold OFF" (not applied, but calculated)
...
```

**v4.5 (clean):**
```
00:00 [DECISION] Top of hour - running control decision
      Control: flow=20°C, zone=NORMAL, pred_err=-0.12°C
      Turn OFF
      [APPLY] ✓ Applied flow=20°C

00:10 [MONITOR] Between hours - monitoring only
      Last applied: 20°C, next decision at 01:00
      Current: avg_temp=23.63°C, slope=0.05°C/h

00:20 [MONITOR] Between hours - monitoring only
      Last applied: 20°C, next decision at 01:00
      Current: avg_temp=23.65°C, slope=0.06°C/h
```

**CSV Format:**
```csv
timestamp,avg_temp,flow_cmd,decision_zone,comment
2025-11-08T00:00,23.61,20,NORMAL,"Turn OFF"
2025-11-08T00:10,23.63,20,MONITOR,"Monitoring (last applied: 20°C at 00:00)"
2025-11-08T00:20,23.65,20,MONITOR,"Monitoring (last applied: 20°C at 00:00)"
2025-11-08T01:00,23.52,28,NORMAL,"Turn ON (28°C)"
```

**Benefits:**
- ✅ **Cleaner logs** - No repetitive decision comments
- ✅ **Less CPU** - Control logic runs 1x per hour instead of 6x
- ✅ **CSV clarity** - Easy to filter: `decision_zone != "MONITOR"` for actual decisions
- ✅ **Same control** - All v4.4 improvements preserved (hourly tracking, 2h lookahead, STABLE hold)
- ✅ **User request** - Exactly what was asked for: "no decisions or comments between hours"

**Learning:**
> "If you're not applying the decision, don't calculate it. 
>  Monitoring is different from deciding.
>  One decision per hour, five monitoring checks in between."

---

## Version 4.4 - Fixed Hourly Tracking (2025-11-07) 🎯

### **CRITICAL BUG FIX - STABLE Zone Now Holds Optimal Flow**

**Problem Found in v4.3:**
- System identified 29°C as optimal and entered STABLE zone
- Should have held 29°C, but reverted to 28°C
- Root cause: Incorrectly tracking "last applied hourly flow"
- Was counting back 6 rows (60 minutes) instead of finding last XX:00 timestamp

**Real Log Example (v4.3):**
```
22:00 → flow_cmd=29°C, adjustment=+1.0, zone=NORMAL
         (Applied 29°C to heat pump)
22:10-22:50 → Monitoring only (not top of hour)
23:00 → avg_temp=23.61, slope=-0.01, pred_err=+0.02
         zone=STABLE ("Stable near target")
         BUT flow_cmd=28°C (WRONG! Should hold 29°C)
         
WHY? At 23:00, system looked back 6 rows:
  rows[-1] = 22:50 (current, skip)
  rows[-7] = 21:50 (got 28°C)
  
Should have looked for last XX:00:
  rows[22:00] = 29°C ✓
```

**The Root Issue:**
```python
# OLD LOGIC (BROKEN):
last_hourly_flow = rows[-7]  # 6 rows back from current
# At 23:00, this gets 21:50's flow, not 22:00's applied flow!

# Why broken:
# - rows[-1] = 22:50 (last logged, but not applied)
# - rows[-7] = 21:50 (6 rows back, also not applied)
# - rows[22:00] = THE ONE WE APPLIED ← Need this!
```

**v4.4 Solution:**
> **"Find the last XX:00 timestamp - that's where we actually applied."**

**What Changed:**
- ✅ **Correct hourly tracking** - Search backwards for last `:00` timestamp
- ✅ **STABLE holds optimal** - If 29°C is working, stay at 29°C
- ✅ **Weather curve = constraints** - Min/ref/max still enforced
- ✅ **Single-step from applied** - Increments from actual applied flow

**Technical Changes:**
```python
# state_manager.py - read_last_state()

OLD:
# Get last hourly flow (6 rows back)
last_hourly_flow = rows[-7]  # WRONG

NEW:
# Find last top-of-hour timestamp where we applied
for row in reversed(rows[:-1]):
    timestamp = row["timestamp"]
    if timestamp.endswith(":00"):
        last_hourly_flow = row["flow_cmd"]
        break  # Found the last applied flow!
```

**Files Modified:**
- `state_manager.py`: Search for last `:00` timestamp
- `control_logic.py`: Updated docstrings
- `melcloud_flow_controller.py`: Updated docstrings
- `config.py`: VERSION = "4.4"
- `README.md`: Added v4.4 section
- `CHANGELOG.md`: Added v4.4 section

**Expected Behavior:**
```
Hour 1: Start at ref (28°C)
Hour 2: Predict cold → step up to 29°C (NORMAL zone)
Hour 3: Check trajectory → optimal, enter STABLE
        Hold 29°C ✓ (was reverting to 28°C ✗)
Hour N: Still stable → keep holding 29°C
        Trajectory changes → exit STABLE, adjust ±1
```

**Key Principle Reinforced:**
- Weather curve reference (28°C) = starting point
- System adapts UP to find optimal (29°C)
- STABLE zone HOLDS optimal, doesn't revert to reference
- Min/max from weather curve = rigid constraints

**Benefits:**
- ✅ STABLE truly means stable (holds working flow)
- ✅ No spurious returns to weather curve reference
- ✅ Single-step logic correctly references last applied flow
- ✅ Weather curve min/max still enforced

**Learning:**
> "STABLE should preserve what's working, not reset to reference. 
>  Weather curve is a starting guide, not a constant target.
>  Min/max are constraints, reference is initialization."

---

## Version 4.3 - 2-Hour Lookahead (2025-11-07) 🔭

### **MAJOR IMPROVEMENT - Accounts for Floor Heating Thermal Lag**

**Problem Found in v4.2:**
- 1-hour prediction was too short for floor heating thermal lag (1-2 hours)
- System was ramping up aggressively (28→29→30→31°C in 30 minutes)
- Changes were being applied every 10 minutes instead of hourly
- Single-step was from 10-minute-ago flow, not from last applied hourly flow
- Result: Overshoot to 23.85°C and stayed hot for 3.5 hours

**Real Log Example (v4.2):**
```
16:30 → Turn ON to 28°C (good predictive start)
16:40 → Step to 29°C (too aggressive!)
16:50 → Step to 30°C (still ramping!)
17:00 → Step to 31°C (overshoot!)
18:00 → 23.69°C (approaching target)
18:40 → Turn OFF
19:10 → 23.85°C (peak - overshot by 0.25°C!)
```

**v4.3 Solution:**
> **"Predict 2 hours ahead. Apply once per hour. Single-step from last applied."**

**What Changed:**
- ✅ **2-hour lookahead** - Prediction now 2 hours ahead (was 1 hour)
- ✅ **Accounts for thermal lag** - Floor heating takes 1-2 hours to affect room temp
- ✅ **Strictly hourly application** - Only applies at XX:00 (monitoring at XX:10-XX:50)
- ✅ **Single-step from last hourly flow** - Steps from flow applied 1 hour ago, not 10 min ago

**Technical Changes:**
```python
# Prediction lookahead
OLD: lookahead_hours = 1.0
NEW: lookahead_hours = 2.0

# Single-step reference
OLD: last_flow = prev_last_cmd  # From 10 minutes ago
NEW: last_flow = prev_hourly_cmd  # From 1 hour ago (6 rows back)
```

**Expected Behavior (v4.3):**
```
16:00 → Calculate: Turn ON to 28°C → APPLY to MELCloud
16:10 → Calculate: 29°C → MONITOR ONLY (don't apply)
16:20 → Calculate: 30°C → MONITOR ONLY
...
17:00 → Calculate: 29°C → APPLY (single-step from 28°C)
```

**Benefits:**
1. **More accurate prediction** - 2-hour lookahead matches thermal dynamics
2. **Smoother control** - No aggressive multi-step ramps
3. **Less overshoot** - System anticipates thermal lag
4. **True hourly rhythm** - One change per hour, not every 10 minutes

**Files Changed:**
- `config.py` - v4.3, lookahead_minutes: 60→120
- `control_logic.py` - lookahead_hours: 1.0→2.0
- `state_manager.py` - Added last_hourly_flow tracking (6 rows back)
- `melcloud_flow_controller.py` - Use prev_hourly_cmd for single-step

**Impact:**
- Prevents aggressive ramp-ups after turn-ON
- Reduces overshoot by accounting for thermal lag
- True single-step changes once per hour
- More stable, predictable behavior

---

## Version 4.2 - Weather Minimum Fix (2025-11-07) 🔧

### **CRITICAL BUG FIX - Weather Minimum Enforcement**

**Bug Found:**
- Weather minimum enforcement was checking `min_flow > 20°C` (OFF threshold)
- At 6.5°C outdoor: weather min = 25°C → forced ON to 28°C ❌
- Problem: 25°C < 28°C (heat pump minimum) → not enough heat demand → OFF should be allowed

**The Fix:**
```python
# OLD (v4.1):
if min_flow > limits["off"]:  # > 20°C
    force ON

# NEW (v4.2):
if min_flow >= limits["min_on"]:  # >= 28°C
    force ON
```

**Logic:**
| Outdoor | Weather Min | Old Behavior | New Behavior | Correct? |
|---------|-------------|--------------|--------------|----------|
| 10°C | 20°C | Force ON ❌ | Allow OFF ✅ | Yes |
| 6°C | 25°C | Force ON ❌ | Allow OFF ✅ | Yes |
| 5°C | 28°C | Force ON ✅ | Force ON ✅ | Yes |
| 2°C | 29°C | Force ON ✅ | Force ON ✅ | Yes |

**Interpretation:**
- **Weather min < 28°C**: Not enough heat demand to justify running heat pump → OFF is correct
- **Weather min ≥ 28°C**: Sufficient heat demand → Must stay ON

**User's Scenario:**
```
2025-11-07T11:21, outdoor=6.5°C, avg=24.03°C, predicted=-0.63°C (hot)
Weather min: 25°C

v4.1:  28°C (forced ON - wrong!)
v4.2:  20°C (OFF - correct!)
```

**Files Changed:**
- `config.py` - Version bump to 4.2
- `control_logic.py` - Fixed both enforcement locations (STABLE and NORMAL zones)

**Impact:**
- Allows system to turn OFF when mildly warm weather (6-10°C outdoor)
- Prevents unnecessary heating when temperature is already above target
- More efficient, more coherent with weather curve design

---

## Version 4.1 - Pure Hourly Rhythm (2025-11-07) ⚡

### **MAJOR SIMPLIFICATION - Removed All Complexity**

**Problems Found in v4.0:**
- ❌ **Emergency zone bypassed weather minimum**: At 5.7°C outdoor (min=27.7°C), emergency forced OFF violating physics
- ❌ **Emergency incompatible with hourly rhythm**: Acted immediately (within 10 minutes), not hourly
- ❌ **Emergency used current error, not predicted**: Reactive instead of predictive (current=+0.32, predicted=-0.50)
- ❌ **DHW flow moderation added complexity**: Unnecessary with hourly rhythm
- ❌ **Inconsistent logic**: Multiple decision paths with different OFF rules

**v4.1 Revolution:**
> **"Two zones only. Trust the trajectory. No exceptions."**

**What Changed:**
- ✅ **Removed emergency zone** - No more 0.30°C panic threshold
- ✅ **Removed DHW flow moderation** - DHW guard stays for valve control and CSV logging
- ✅ **Two zones only**: STABLE (hold) and NORMAL (single-step)
- ✅ **Weather minimum always enforced** - No path can bypass physics-based constraints
- ✅ **Pure hourly rhythm** - Every decision applied at XX:00, no exceptions
- ✅ **Symmetric response** - Warming and cooling treated identically

**Control Logic (Pure & Simple):**
```python
# At every hour (XX:00):
if within ±0.05°C predicted:
    → Hold current flow (STABLE)
else:
    → Calculate direction from predicted error
    → Apply single-step (±1°C or OFF↔28°C)
    → Enforce weather minimum if needed (NORMAL)
```

**Example From User's Logs:**
```
Time: 10:50, Outdoor: 5.7°C, Current: 23.92°C (0.32 above target)
Trajectory: +0.18°C/h, Predicted: 24.10°C, Error: -0.50°C
Weather min: 27.7°C

v4.0 (with emergency):
  → Current error > 0.30 → EMERGENCY
  → Force OFF (20°C)
  → WRONG! Violates weather minimum of 27.7°C

v4.1 (pure rhythm):
  → Predicted error = -0.50°C → direction = -1
  → Currently ON (28°C) → step down: 28 - 1 = 27°C
  → Check: 27 < weather_min(27.7) → turn OFF
  → Override: OFF violates weather_min → Force ON to 28°C
  → Result: Hold 28°C (respects physics, trusts trajectory)
```

**Benefits:**
- **Simple**: 2 zones, one rule, no exceptions
- **Coherent**: All decisions respect weather minimum
- **Predictive**: Uses trajectory (2h history), not panic on current error
- **Symmetric**: Same formula for warming and cooling
- **Robust**: No edge cases, no special handling

**Files Changed:**
- `config.py` - v4.1, removed emergency settings
- `control_logic.py` - Removed emergency zone and DHW moderation
- `melcloud_flow_controller.py` - Updated to v4.1
- `state_manager.py` - Improved CSV column comments

**Philosophy:**
> *"In complex systems, simplicity emerges not from adding intelligence, but from removing assumptions."*

v4.1 trusts three things only:
1. **Trajectory** - What the house is actually doing
2. **Weather curve minimum** - What physics requires
3. **Hourly rhythm** - What matches thermal dynamics

Everything else is removed.

---

## Version 4.0 - Hourly Rhythm Control (2025-11-07) 🎼

### **Revolutionary Change: Natural Damping Through Hourly Application**

**Problem Identified:**
- All v3.x versions applied flow changes every 10 minutes
- House thermal dynamics are slow (0.06-0.10°C/hour cooling rate)
- Controller was fighting the natural thermal inertia
- Example from logs: Flow changed 33→32→31→28→20 in just 90 minutes
- Result: Oscillation around target instead of stable convergence

**Key Decision:**
> **"Match the controller frequency to the system's thermal time constant"**

**What Changed:**
- Script runs every 10 minutes for monitoring/logging
- Flow commands applied **only at top of hour (XX:00)**
- Single-step changes: ±1°C per hour or OFF↔28°C transitions
- Removed hysteresis (natural hourly rhythm prevents chatter)
- Removed outdoor transition detection (no longer needed)
- Removed soft landing complexity (single steps prevent overshoot)
- Simplified zones: STABLE, NORMAL, EMERGENCY only

**Learnings:**
1. **Thermal inertia is your friend** - A house with floor heating responds very slowly. Single-step hourly changes match this perfectly.
2. **Natural damping beats algorithmic complexity** - Hysteresis, soft landing, and transition detection all became unnecessary with proper timing.
3. **API efficiency matters** - Reduced from 144 to 24 MELCloud calls per day (6× reduction).
4. **Weather curve minimum flows** - Added min/ref/max structure to weather curve. Below minimum for outdoor temp → must turn OFF.

**Technical Details:**
- Weather curve now: (outdoor_temp, min_flow, reference_flow, max_flow)
- Example: At 0°C outdoor → min=29°C, ref=31°C, max=36°C
- Single-step logic: If pred_err > +0.05 → +1°C; if < -0.05 → -1°C
- OFF transition: If stepped flow < weather_min OR < 28°C → force OFF

**Results Expected:**
- Stable approach to target (no oscillation)
- Predictable behavior (one change per hour)
- Reduced API load on MELCloud servers
- Simpler code (~50% less than v3.3)

**Bug Fix (2025-11-07):**
- ✅ **Weather curve minimum enforcement**: System was staying OFF at 4.6°C outdoor (where min=28°C) because it predicted short-term overshoot. Fixed to enforce minimum heat input based on outdoor temp, preventing long-term cooling trends.
- Logic: If OFF and weather min > 20°C → force ON to weather minimum
- Exception: Deliberately turning OFF from ON is still allowed (for actual overheating)

---

## Version 3.3 - Coherent Soft Landing (2025-11-07) 🎯

### **Fix: Proportional Soft Landing**

**Problem Found in v3.2:**
- Soft landing from above: System held OFF → undershot to 23.50°C
- Soft landing from below: System held high flow → overshot to 23.68°C
- Emergency hot logic hard-coded OFF instead of using unified constraint
- Three different OFF rules across zones (incoherent)

**Solution:**
- Proportional soft landing: `flow = ref + (pred_err × 5.0)`
- Symmetrical for both warming and cooling approaches
- Emergency logic unified: Both hot/cold use adjustment, then constraint applies
- ONE physical constraint rule everywhere: `if flow < 28°C → OFF`

**Learning:**
> **"Proportional control works, but requires tuning the gain (5.0)"**

The gain of 5.0 means for every 0.1°C predicted error, adjust flow by 0.5°C. This was better than binary hold/don't-hold, but still complex. v4.0 simplifies this entirely with hourly single steps.

---

## Version 3.2 - Critical Bug Fix (2025-11-07) 🐛

### **Bug Fix: Adjustment Logic Matching**

**Critical Bug:**
- Negative predicted errors incorrectly matched positive thresholds
- Example: `pred_err = -0.26` (predicting overheat) matched `threshold = 0.25` (for heating!)
- Result: System heated when it should cool → prolonged overheating

**Root Cause:**
```python
# WRONG (v3.1):
if predicted_error < -abs(threshold):  # Always true for positive thresholds!

# CORRECT (v3.2):
if threshold < 0 and predicted_error < threshold:  # Sign-aware matching
```

**Learning:**
> **"Always test edge cases with opposite signs"**

This bug was masked during warm conditions but became critical when predicting overheat. User logs revealed the issue: system stuck at 30-31°C despite predicting -0.26°C error.

**Additional Fix:**
- Physical constraint: Force OFF when calculated flow < 28°C (heat pump minimum)
- Removed `-100` magic number from gains, replaced with `-4°C`

---

## Version 3.1 - Tuned Response (2025-11-06) 🎯

### **Tuning Based on 11 Hours of v3.0 Data**

**Observations from Logs:**
- Emergency threshold too wide (0.40°C) → slow response to large errors
- Adjustment gains too conservative → system undershot repeatedly
- Hysteresis too wide (0.12°C) → delayed ON/OFF transitions

**Changes:**
- `emergency_error`: 0.40 → **0.30°C** (faster emergency response)
- Added `(-0.10, -2)` gain for moderate cooling
- Strengthened `(-0.15, -3)` and `(-0.20, -100)` for aggressive cooling
- `hysteresis`: ±0.12 → **±0.08°C** (more responsive)

**Learning:**
> **"Tune from real-world data, not theory"**

Initial conservative tuning led to undershooting. Actual logs showed the system needed more aggressive adjustments.

---

## Version 3.0 - Unified Control (2025-11-06) 🚀

### **Major Refactoring: Single Algorithm for All Conditions**

**Problem with v2.x:**
- Cold/Warm mode split created discontinuities at 6°C outdoor
- Duty cycling (ON/OFF time-sharing) was overly complex
- Learning bias accumulated errors over time
- Hourly rhythm fighting against trajectory predictions

**Revolution:**
> **"One algorithm, one rule: Trust the trajectory"**

**What Changed:**
- Removed mode switching (cold/warm unified)
- Removed duty cycling (use continuous flow adjustment)
- Removed learning bias (slow integrator was unstable)
- Introduced weather curve as reference baseline
- Trajectory-based predictions (2-hour history, 1-hour lookahead)
- Zones: STABLE, SOFT_LAND, EMERGENCY, NORMAL, TRANSITION

**Key Insight:**
> **"The house tells you what it needs through temperature trajectory"**

Instead of trying to learn house characteristics or predict based on outdoor alone, measure actual temperature change rate and project forward.

**Technical:**
- Linear regression over last 12 readings (2 hours)
- Predict 1 hour ahead: `predicted_temp = current + (slope × 1.0)`
- Adjustment gains based on predicted error
- Outdoor transition detection for rapid weather changes

**CSV Simplified:**
- Removed: `duty_base`, `duty_bias`, `duty_eff`, `duty_on`, `state_learn_bias`, `state_last_boost`, `state_too_hot_count`, `state_prev_avg_temp`, `state_temp_history`
- Added: `version`, `traj_slope`, `predicted_temp`, `predicted_error`, `reference_flow`, `adjustment`, `decision_zone`, `dhw_active`
- Result: All values in dedicated columns for easy analysis

**Learning:**
> **"Complex != Better. Trajectory + Simple rules > Adaptive learning"**

---

## Version 2.3 - Hot Penalty & Trajectory (2025-11-05)

### **Addressing Persistent Overheating**

**Problem:**
- System staying 0.2°C above target for hours
- `too_hot_count` decayed slowly even when OFF
- No forward-looking prediction

**Solutions Added:**
1. **Hybrid Hot Penalty**: Gradual duty reduction + discrete forced OFF periods
2. **Trajectory Prediction**: 2-hour lookback with linear regression
3. **Trend-Aware Trim**: Cold mode adjusts based on trajectory direction
4. **Immediate Reset**: `too_hot_count = 0` when below target AND OFF

**Learning:**
> **"Reactive control has blind spots. Need predictive element."**

This was the birth of trajectory-based control, though initially bolted onto the existing duty/mode framework. v3.0 made it central.

---

## Version 2.2 - DHW Valve Guard Timeout (2025-11-05)

### **Safety: DHW Timeout**

**Problem:**
- If DHW cycle didn't end (tank sensor failure), system stuck in DHW mode forever
- Valves remained closed indefinitely

**Solution:**
- 90-minute timeout for DHW detection
- Force DHW off and restore valve positions
- Important for both flow control and valve guard

**Learning:**
> **"Always add timeouts to state machines"**

---

## Version 2.1 - DHW Valve Guard Integration (2025-11-05)

### **Feature: Noise Reduction During DHW Cycles**

**Problem:**
- Hot water heating cycles caused noise through 2nd-floor (Plan 2) radiators/pipes
- User wanted automatic valve closure during DHW

**Solution:**
- Integrated DHW valve guard into main controller
- Runs every 10 minutes (same cycle)
- Detects DHW: tank temp rise ≥ 3°C
- Closes Plan 2 valves (Bedroom 1, Bedroom 2, Bath 2)
- Restores valves when DHW cycle ends
- Temporary state file for valve backup

**Technical:**
- Uses LK Systems API to get/set target temps
- Temporary file: `dhw_valve_backup_temp.txt`
- Removed `tank_target_min` method (overly complex)

**Learning:**
> **"Integration > Separation. Single 10-min cycle for all tasks."**

---

## Version 2.0 - Two-Decimal Precision & Trend Detection (2025-11-05)

### **Improvement: Finer Temperature Control**

**Changes:**
- Average temperature: 1 decimal → **2 decimals** (23.6 → 23.62°C)
- Added 10-minute trend detection in cold mode
- 2-hour trajectory prediction introduced

**Why:**
- 0.1°C resolution too coarse for detecting slow trends
- House cooling rate ~0.06°C/hour when OFF
- 2-decimal precision allows detecting trends in 2-3 readings

**Learning:**
> **"Precision enables prediction"**

You can't predict a trend if you can't see it. 2 decimals revealed the slow thermal dynamics of the house.

---

## Version 1.0 - Initial Modular Refactoring (2025-11-04)

### **Foundation: Breaking the Monolith**

**Starting Point:**
- Single 800+ line `old_controller.py` file
- All logic, API calls, state management mixed together
- Hard to test, debug, or modify

**Refactoring:**
Created 7 modular files:
1. `config.py` - All constants and configuration
2. `utils.py` - Helper functions (logging, EMA, formatting)
3. `lk_systems.py` - LK Systems API (room temperatures)
4. `melcloud.py` - MELCloud API (heat pump control)
5. `control_logic.py` - Decision algorithms
6. `state_manager.py` - CSV state persistence
7. `melcloud_flow_controller.py` - Main orchestrator

**Control Modes (v1.0):**
- **Cold mode** (outdoor ≤ 6°C): Continuous flow from weather curve
- **Warm mode** (outdoor > 6°C): Hourly duty cycling (28°C ON / 20°C OFF)
- Learning bias: Slow integrator to adapt to house characteristics

**Learning:**
> **"Modularity is the foundation of iterability"**

Every version since has benefited from this initial structure. Changing control logic doesn't require touching API code, etc.

---

## Key Learnings Across All Versions

### **1. Match Controller to System Dynamics**
- House thermal time constant: ~15-20 hours (to change 1°C when OFF at 10°C outdoor)
- Floor heating response time: 2-4 hours
- Controller update rate: Originally 10 min, now **60 min** (v4.0)
- **Lesson**: Slow system → slow controller

### **2. Trajectory Beats Learning**
- Learning bias (v1-v2): Slow, accumulates errors, hard to tune
- Trajectory prediction (v2.3-v4.0): Fast, direct, observable
- **Lesson**: Measure actual behavior, not try to model it

### **3. Simplicity Emerges from Constraints**
- v1-v2: Mode switching, duty cycling, learning bias, boost logic
- v3: Unified algorithm, trajectory-based, zones
- v4: Single-step hourly changes
- **Lesson**: Constraints (hourly rhythm) simplify design

### **4. CSV as Analysis Tool**
- Every run logs everything: temps, predictions, decisions
- Enables data-driven tuning
- Revealed bugs (v3.2 adjustment matching)
- **Lesson**: Observability drives improvement

### **5. Real-World Edge Cases**
- DHW cycles interfering with control
- Tank sensor failures requiring timeouts
- Outdoor temperature rapid changes (8°C drop in 6 hours)
- Network hiccups with MELCloud API
- **Lesson**: Always add guards, timeouts, and retry logic

### **6. Weather Curve Evolution**
- v1-v3: (outdoor, reference, max)
- v4: (outdoor, **min**, reference, max)
- **Lesson**: Constraints from below (minimum flows) matter as much as from above

---

## Performance Metrics

### **Typical Behavior (v4.0 Expected):**
- **Stability**: ±0.05°C around target
- **Convergence**: 3-6 hours from cold start
- **API calls**: 24 per day (vs 144 in v3.x)
- **Temperature trajectory**: Detectable within 2 hours
- **Response time**: 1 hour (hourly rhythm)

### **Historical Comparison:**
| Version | Stability | Complexity | API Calls/Day |
|---------|-----------|------------|---------------|
| v1.0 | ±0.3°C | High | 144 |
| v2.x | ±0.2°C | Very High | 144 |
| v3.0-3.3 | ±0.10°C | Medium | 144 |
| **v4.0** | **±0.05°C** (expected) | **Low** | **24** |

---

## Future Considerations

### **Potential Improvements:**
1. **Adaptive weather curve** - Tune min/ref/max based on long-term data
2. **Multiple zone control** - Different floors with different setpoints
3. **Occupancy integration** - Lower temp when away
4. **Solar gain prediction** - Use weather forecast for south-facing rooms
5. **Cost optimization** - Prefer night heating if using time-of-use electricity

### **What NOT to Do:**
- ❌ Don't reintroduce duty cycling (v4.0 proves continuous flow works better)
- ❌ Don't reintroduce learning bias (trajectory is more reliable)
- ❌ Don't increase update frequency (hourly is optimal)
- ❌ Don't add mode switching (unified control is simpler)

---

**Current Version**: 4.0  
**Last Updated**: 2025-11-07  
**Total Evolution Time**: 3 days (from monolith to v4.0)  
**Total Rewrites**: 3 major (v2.3→v3.0→v4.0)  
**Lines of Code**: ~1500 → ~1000 (33% reduction from v1.0 to v4.0)  

**Philosophy**: *"Simple systems, emergent complexity"*

