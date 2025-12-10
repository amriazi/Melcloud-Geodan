# Hydronic Floor Heating Controller

Trajectory-based flow temperature controller for LK Systems floor heating with Mitsubishi Ecodan/Geodan heat pump via MELCloud.

**Current Version:** 5.5 🎯  
**Target Precision:** ±0.05°C  
**Prediction Lookahead:** 2 hours (accounts for thermal lag)  
**Update Interval:** 10 minutes (monitoring), 60 minutes (decision + application)  
**Last Updated:** 2025-11-14

---

## 🔒 Security Note

Credentials are now stored in `.env` file (git-ignored). Copy `.env.example` to `.env` and fill in your credentials before running.

---

## Quick Start

### Prerequisites

**Using venv (recommended for Linux/Ubuntu):**
```bash
# Create virtual environment
python3 -m venv venv

# Activate venv
source venv/bin/activate  # On Linux/Mac
# or
venv\Scripts\activate     # On Windows PowerShell

# Install dependencies
pip install -r requirements.txt
```

**Without venv:**
```powershell
pip install -r requirements.txt
```

Or manually:
```powershell
pip install requests aiohttp pymelcloud python-dotenv
```

### Run
```powershell
cd C:\Projects\Flow_controller
python melcloud_flow_controller.py
```

### Schedule

**Windows:**
Schedule to run every 10 minutes via Windows Task Scheduler.

**Ubuntu/Linux (Cron with venv):**
```bash
# Create logs directory
mkdir -p /home/amir/controller/logs

# Edit crontab
crontab -e

# Add this line (runs at :00, :10, :20, :30, :40, :50 every hour)
# Uses venv Python: /home/amir/controller/venv/bin/python3
*/10 * * * * cd /home/amir/controller && /home/amir/controller/venv/bin/python3 melcloud_flow_controller.py >> /home/amir/controller/logs/cron.log 2>&1
```

**Note:** If your venv is in a different location, adjust the Python path accordingly. To find your venv Python path: `which python3` (while venv is activated).

**Logs:**
- CSV log: `/home/amir/controller/logs/heating_log.csv`
- Cron output: `/home/amir/controller/logs/cron.log`

**View logs:**
```bash
tail -f /home/amir/controller/logs/cron.log
tail -f /home/amir/controller/logs/heating_log.csv
```

---

## Features

✅ **Pure Hourly Rhythm** - Single-step changes (±1°C) at top of hour  
✅ **Two Zones** - STABLE (hold optimal), NORMAL (single-step)  
✅ **Trajectory-Based** - 2-hour history, 2-hour lookahead prediction  
✅ **Weather Curve Min/Max** - Physics-based constraints always enforced  
✅ **DHW Integration** - Automatic valve closure during hot water cycles  
✅ **Symmetric Control** - Identical logic for warming and cooling  
✅ **Simplified Logic** - Removed consecutive pause mechanism for more coherent control  

---

## Version History

### v5.4 - Simplified Control Logic (2025-11-14) 🎯

**REMOVED CONSECUTIVE PAUSE MECHANISM**

Removed the consecutive pause mechanism to simplify the control logic and make it more coherent.

**Why This Change:**
- The pause mechanism added complexity for limited benefit
- Single-step adjustments (±1°C/hour) are already conservative
- Trajectory prediction accounts for thermal lag
- Weather curve bounds provide natural limits
- STABLE zone already holds when near target
- Analysis of v5.3 logs showed pause triggered only 2 times in 24 hours with minimal impact

**v5.4 Solution:**
> **"Simpler is better. Trust the trajectory prediction and single-step logic."**

**What Changed:**
- Removed PAUSE zone entirely
- Removed flow history tracking (flow_2h_ago, flow_3h_ago)
- Simplified to two zones: STABLE and NORMAL
- Control logic is now more straightforward and easier to understand

**Benefits:**
- ✅ **Simpler logic** - Easier to understand and maintain
- ✅ **Less complexity** - Fewer edge cases to handle
- ✅ **More coherent** - Single-step + trajectory + weather bounds provide sufficient control
- ✅ **Still safe** - Weather curve min/max still enforced on all decisions

**Files Modified:**
- `control_logic.py`: Removed pause detection and PAUSE zone
- `state_manager.py`: Removed flow_2h_ago and flow_3h_ago tracking
- `melcloud_flow_controller.py`: Removed pause-related parameters
- `config.py`: Updated to v5.4

---

### v4.7 - Directional Pause (2025-11-09) 🎯

**SMARTER PAUSE - Allow Opposite Direction Corrections**

After 2 consecutive steps in one direction, pause **only** from continuing in that **same direction**. Allow opposite direction corrections for faster recovery.

**Why This Change:**
- v4.6 blocked ALL actions after 2 consecutive steps
- Problem: If system overshot (predicting hot after 2 increases), pause prevented correction
- User's log: `16:00 PAUSE at 29°C despite predicting hot -0.35°C` ❌

**v4.7 Solution:**
> **"Pause from continuing, not from correcting."**

**How It Works:**
```
After 2 consecutive increases (e.g., 28→29→30):
  - If predicting COLD (+0.10°C) → wants +1°C → PAUSE (same direction, block)
  - If predicting HOT (-0.35°C) → wants -1°C → ALLOW (opposite direction, let through)
  - If predicting STABLE (0.02°C) → wants hold → ALLOW (not same direction)
```

**Real Example from User's Log (Fixed in v4.7):**
```csv
BEFORE (v4.6):
15:00,29,NORMAL,"+1°C (pred cold +0.45)"
16:00,29,PAUSE,"After 20→28→29; hold at 29°C" ❌ predicting hot -0.35°C!

AFTER (v4.7):
15:00,29,NORMAL,"+1°C (pred cold +0.45)"
16:00,28,NORMAL,"After 2 increases, but allowing opposite correction; -1°C" ✅
```

**Files Modified:**
- `control_logic.py`: Check desired direction before pausing
- `config.py`, `melcloud_flow_controller.py`, `state_manager.py`: Updated to v4.7
- `README.md`, `CHANGELOG.md`: Documentation

**Expected Behavior:**
- ✅ Prevents overshoot (blocks continuing same direction)
- ✅ Enables fast recovery (allows opposite direction)
- ✅ Natural for STABLE (not same direction = no pause)
- ✅ Weather min/max still enforced (physics > strategy)

**CSV Output:**
```csv
14:00,28,NORMAL,"Turn ON"
15:00,29,NORMAL,"Pred cold; +1°C"
16:00,30,NORMAL,"Pred cold; +1°C" ← 2 consecutive increases
17:00,30,PAUSE,"Pause from continuing increases; hold" ← Still predicting cold
18:00,29,NORMAL,"After 2 increases, but allowing opposite; -1°C" ← Now predicting hot
```

---

### v4.6 - Pause After 2 Consecutive Steps (2025-11-09) 🛑

**NEW FEATURE - Adaptive Damping for Overshoot Prevention**

Implements a 1-hour pause after detecting 2 consecutive steps in the same direction.

**Why This Change:**
- Floor heating has 1-2 hour thermal lag
- After 2 consecutive steps (e.g., 28→29→30), momentum can cause overshoot
- Pausing gives the system time to respond before continuing

**v4.6 Solution:**
> **"Step, step, pause. Let the floor catch up."**

**How It Works:**
1. **Track History**: Flow from 3h ago, 2h ago, and 1h ago
2. **Detect Pattern**: If both steps are in same direction (both up OR both down)
3. **Pause Action**: Hold current flow for 1 hour
4. **Resume**: Normal control resumes next hour

**Examples:**

**Pause After Increases:**
```
Hour 1: 28°C
Hour 2: 29°C (step +1)
Hour 3: 30°C (step +1) ← 2nd consecutive increase
Hour 4: 30°C PAUSE ← Hold to prevent overshoot
Hour 5: Resume normal control
```

**Pause After Decreases:**
```
Hour 1: 30°C
Hour 2: 29°C (step -1)
Hour 3: 28°C (step -1) ← 2nd consecutive decrease
Hour 4: 28°C PAUSE ← Hold to prevent undershoot
Hour 5: Resume normal control
```

**Also Applies To OFF/ON Transitions:**
```
Hour 1: 20°C (OFF)
Hour 2: 28°C (ON, step +8)
Hour 3: 29°C (step +1) ← 2nd step after turn-on
Hour 4: 29°C PAUSE ← Dampen aggressive ramp-up
```

**Technical Implementation:**
```python
# Detect 2 consecutive steps in same direction
step1 = flow_2h_ago - flow_3h_ago  # e.g., 29 - 28 = +1
step2 = last_flow - flow_2h_ago     # e.g., 30 - 29 = +1

if (abs(step1) >= 1 and abs(step2) >= 1):
    if (step1 > 0 and step2 > 0) or (step1 < 0 and step2 < 0):
        # Both steps in same direction → PAUSE
        return PAUSE zone (hold current flow)
```

**Files Modified:**
- `state_manager.py`: Track flow_3h_ago for pattern detection
- `control_logic.py`: Add PAUSE zone before STABLE/NORMAL
- `melcloud_flow_controller.py`: Pass flow_3h_ago to decision function
- `config.py`: VERSION = "4.6"
- `README.md`, `CHANGELOG.md`: Documentation

**Expected Behavior:**
- ✅ Prevents aggressive ramp-ups (3 steps in 3 hours → 2 steps + pause)
- ✅ Prevents overshoot from momentum
- ✅ Natural damping without complex PID tuning
- ✅ Weather min/max enforced during pause (physics > strategy)
- ✅ Still allows STABLE zone to override (if perfectly on target)

**CSV Output:**
```csv
timestamp,flow_cmd,decision_zone,comment
10:00,28,NORMAL,"Turn ON (28°C)"
11:00,29,NORMAL,"Pred cold (0.08°C); +1°C"
12:00,30,NORMAL,"Pred cold (0.12°C); +1°C"
13:00,30,PAUSE,"Pause after 2 consecutive increases: 28→29→30°C"
14:00,30,STABLE,"Stable near target"
```

**Weather Enforcement During Pause:**
```csv
11:00,29,NORMAL,"+1°C"
12:00,30,NORMAL,"+1°C"
13:00,32,PAUSE,"Pause after 2 increases; but weather min=32°C - adjusting to 32°C"
```

---

### v4.5 - Monitor Only Between Hours (2025-11-08) 📊

**EFFICIENCY IMPROVEMENT - Cleaner Logs and Less Computation**

Control decisions now run ONLY at top of hour. Between-hour runs are monitoring-only.

**Why This Change:**
- v4.4 was calculating flow decisions every 10 minutes (6x per hour)
- But only applying once per hour (at XX:00)
- Result: Redundant calculations and repetitive log comments
- Example: "Turn OFF" logged 5 times before actually applying at next hour

**v4.5 Solution:**
> **"Decide at XX:00. Monitor between hours."**

**What Changed:**
- ✅ **XX:00-XX:09**: Run full control decision → Apply → Log with full comment
- ✅ **XX:10-XX:59**: Monitor only → Use last applied flow → Log "Monitoring (last applied: {flow}°C)"
- ✅ **6x less computation** - Control logic runs once per hour instead of 6 times
- ✅ **Cleaner logs** - No repetitive decision comments
- ✅ **CSV clarity** - `decision_zone="MONITOR"` clearly marks monitoring rows

**Technical Changes:**
```python
# Check timing first
if is_top_of_hour(now):
    # Run control decision
    flow_cmd = hourly_rhythm_decision(...)
    apply_flow(flow_cmd)
    comment = full_decision_comment
else:
    # Monitor only
    flow_cmd = last_applied_flow
    comment = "Monitoring (last applied: {flow}°C)"
    skip_apply()
```

**Files Modified:**
- `melcloud_flow_controller.py`: Check timing before running decision
- `config.py`: VERSION = "4.5"
- `control_logic.py`, `state_manager.py`: Updated docstrings
- `README.md`, `CHANGELOG.md`: Added v4.5 documentation

**Expected Behavior:**
```
00:00 → [DECISION] Run control → flow=20°C → "Turn OFF" → Apply
00:10 → [MONITOR] Skip decision → flow=20°C → "Monitoring (last applied: 20°C)"
00:20 → [MONITOR] Skip decision → flow=20°C → "Monitoring (last applied: 20°C)"
...
01:00 → [DECISION] Run control → flow=28°C → "Turn ON" → Apply
```

**Benefits:**
- ✅ Cleaner, more readable logs
- ✅ Less CPU usage (1/6th the control calculations)
- ✅ CSV shows clear distinction between decisions and monitoring
- ✅ Same control quality (decisions still happen hourly as designed)
- ✅ Preserves all v4.4 improvements (hourly tracking, 2h lookahead, STABLE hold)

---

### v4.4 - Fixed Hourly Tracking (2025-11-07) 🎯

**CRITICAL BUG FIX - Hold Optimal Flow**

Fixed STABLE zone to correctly hold the optimal flow temperature instead of reverting to reference.

**Problem in v4.3:**
- At 23:00, system was STABLE at 29°C (slope -0.01, error 0.01)
- Should have held 29°C, but reverted to 28°C
- Bug: Was counting back 6 rows (60 min) instead of finding last applied flow at XX:00
- Example: At 23:00, counted back to 21:50 (28°C) instead of 22:00 (29°C)

**The Fix:**
```python
# OLD: Count back 6 rows (WRONG)
last_hourly_flow = rows[-7]  # Gets random non-applied flow

# NEW: Find last XX:00 timestamp (CORRECT)
for row in reversed(rows[:-1]):
    if timestamp.endswith(":00"):
        last_hourly_flow = row["flow_cmd"]
        break
```

**Technical Changes:**
- `state_manager.py`: Search backwards for last `:00` timestamp
- Ensures STABLE zone holds current optimal flow (29°C stays 29°C)
- Weather curve reference/min/max remain rigid constraints
- Single-step increments still based on last *applied* hourly flow

**Expected Behavior:**
- Find 29°C is optimal → Hold 29°C until trajectory indicates change needed
- Weather curve = start reference (e.g., 28°C at 10°C outdoor)
- System adapts UP to optimal (e.g., 29°C), then HOLDS it
- Min/max boundaries from weather curve always enforced

**Benefits:**
- ✅ STABLE truly means stable - holds what works
- ✅ No spurious reverts to reference when optimal flow is higher
- ✅ Single-step increments correctly based on last hour
- ✅ Respects weather curve min/max as rigid constraints

---

### v4.3 - 2-Hour Lookahead (2025-11-07) 🔭

**MAJOR IMPROVEMENT - Thermal Lag Compensation**

Extended prediction from 1 hour to **2 hours ahead** to account for floor heating thermal lag.

**Problem in v4.2:**
- Floor heating takes 1-2 hours to affect room temperature
- 1-hour prediction was too short → aggressive ramp-ups
- Example: 28→29→30→31°C in 30 minutes → overshoot

**Solution in v4.3:**
- **2-hour lookahead**: Predicts temperature 2 hours ahead
- **Strictly hourly**: Only applies changes at XX:00 (monitors at XX:10-XX:50)
- **Single-step from last hour**: Steps from flow applied 1 hour ago, not 10 min ago

**Impact:**
- Smoother control (no aggressive ramps)
- Less overshoot (anticipates thermal lag)
- True hourly rhythm (one change per hour)

---

### v4.2 - Weather Minimum Fix (2025-11-07) 🔧

**CRITICAL BUG FIX**

Fixed weather minimum enforcement to only force ON when `min_flow >= 28°C` (heat pump minimum).

**Before (v4.1):**
- At 6.5°C outdoor (min=25°C): Forced ON to 28°C ❌
- Logic: `min_flow > 20°C` → force ON

**After (v4.2):**
- At 6.5°C outdoor (min=25°C): Allows OFF ✅
- Logic: `min_flow >= 28°C` → force ON

**Impact:**
- Allows OFF when mildly warm (6-10°C outdoor)
- Prevents unnecessary heating when already above target
- More efficient and coherent

---

### v4.1 - Pure Hourly Rhythm (2025-11-07) ⚡

**ULTIMATE SIMPLIFICATION - Two zones only, no exceptions**

**Problems with v4.0:**
- ❌ **Emergency zone bypassed weather minimum** (violated physics-based constraints)
- ❌ **Emergency incompatible with hourly rhythm** (acted immediately, not hourly)
- ❌ **Emergency used current error, not trajectory** (reactive, not predictive)
- ❌ **DHW flow moderation unnecessary** (added complexity without benefit)

**v4.1 Pure Control:**
```
┌─────────────────────────────────────────────────────────┐
│  Two zones:        STABLE (hold) & NORMAL (single-step)│
│  Decision basis:   Trajectory prediction (2h history)   │
│  Constraints:      Weather curve minimum (always)       │
│  Exceptions:       None                                 │
└─────────────────────────────────────────────────────────┘
```

**What Changed:**
- ✅ **Removed emergency zone** - No more 0.30°C panic threshold
- ✅ **Removed DHW flow moderation** - DHW guard stays for valve control only
- ✅ **Two zones only**: STABLE (±0.05°C) and NORMAL (everything else)
- ✅ **Weather minimum always enforced** - No path can bypass it
- ✅ **Pure trajectory-based** - No reactive panic on current error
- ✅ **Symmetric** - Warming and cooling use identical logic

**Control Logic (Pure):**
```python
# At every hour (XX:00):
if within ±0.05°C predicted:
    → Hold (STABLE)
else:
    → Single-step based on predicted error (NORMAL)
    → Always enforce weather minimum
```

**Real Example (User's Log at 10:50):**
```
Outdoor: 5.7°C, Current: 23.92°C (0.32 above target)
Predicted (1h): 24.10°C, Predicted error: -0.50°C
Weather min: 27.7°C

v4.0: EMERGENCY → Force OFF (wrong! bypassed minimum)
v4.1: NORMAL → step down, but enforce minimum → Hold 28°C ✓
```

**Benefits:**
- **Simpler**: 50 lines less than v4.0
- **Coherent**: One rule, no exceptions
- **Predictive**: Trajectory-only decisions
- **Robust**: No edge cases
- **Symmetric**: ±1°C works identically for warming/cooling

---

### v4.0 - Hourly Rhythm Control (2025-11-07) 🎼

**MAJOR SIMPLIFICATION - Natural damping through hourly rhythm**

**Problems with v3.x (All versions):**
- ❌ **Too frequent changes**: Flow adjusted every 10 minutes (33→32→31→28→20)
- ❌ **Fighting thermal dynamics**: House changes slowly, but controller reacts fast
- ❌ **Unnecessary complexity**: Hysteresis, outdoor transition detection, soft landing gains
- ❌ **API overload**: 144 MELCloud calls per day

**v4.0 Revolutionary Change:**
```
┌─────────────────────────────────────────────────────────┐
│  Script runs:      Every 10 minutes (monitoring/logging)│
│  Flow applied:     Only at XX:00 (top of hour)          │
│  Change limit:     ±1°C per hour, or OFF↔28°C           │
│  Natural damping:  Hourly rhythm prevents oscillation   │
└─────────────────────────────────────────────────────────┘
```

**What Changed:**
- ✅ **Hourly application**: Flow changes only at top of hour (XX:00)
- ✅ **Single-step changes**: Maximum ±1°C per hour (natural damping)
- ✅ **Removed hysteresis**: No longer needed with hourly rhythm
- ✅ **Removed soft landing complexity**: Single steps prevent overshoot
- ✅ **Removed outdoor transition detection**: Hourly changes adapt naturally
- ✅ **Simplified zones**: STABLE, NORMAL, EMERGENCY (removed LANDING/TRANSITION)
- ✅ **6× fewer API calls**: 24/day instead of 144/day

**Control Logic (Simplified):**
```python
# Every hour at XX:00:
if predicted_error > +0.05:
    flow += 1°C  # Need more heat
elif predicted_error < -0.05:
    flow -= 1°C  # Need less heat (or OFF if below 28°C)
else:
    flow = hold  # Stable
```

**Example Behavior:**
```
08:00 → Apply 32°C (currently 33°C, pred_err=+0.20, step down)
  08:10-08:50 → Monitor only, log predictions
09:00 → Apply 31°C (step down, approaching target)
  09:10-09:50 → Monitor only
10:00 → Apply 30°C (step down, soft landing)
11:00 → Hold 30°C (stable, pred_err=0.02)
12:00 → Hold 30°C (continue stable)
```

**Benefits:**
- **Stability**: Matches slow thermal dynamics of house
- **Simplicity**: ~50% less code than v3.3
- **Robustness**: Natural damping, no edge cases
- **Efficiency**: 6× fewer MELCloud API calls
- **Predictability**: One change per hour, easy to understand

**Files Changed:**
- `config.py` - Added APPLICATION settings, removed hysteresis/transitions/adjustments
- `control_logic.py` - Completely rewritten with single-step logic
- `melcloud_flow_controller.py` - Hourly application logic, monitor-only between hours

**Backward Compatible:**
- ✅ Uses same CSV format (continues appending to existing log)
- ✅ Same DHW guard and valve guard features
- ✅ Same trajectory prediction (2-hour history, 1-hour lookahead)

---

### v3.3 - Coherent Soft Landing (2025-11-07) 🎯

**LOGIC IMPROVEMENT - Symmetrical & coherent control**

**Problems Found in v3.2:**
- ❌ **Soft landing broken**: From above → stayed OFF → undershot to 23.50°C
- ❌ **Emergency inconsistent**: Hot emergency hard-coded OFF instead of using unified constraint
- ❌ **3 different OFF rules**: Stable/Normal vs Emergency vs Soft Landing (incoherent)

**v3.3 Improvements:**
- ✅ **Proportional soft landing**: `flow = ref + (pred_err × 5.0)` - symmetrical for both directions
- ✅ **Emergency unified**: Both hot/cold use adjustment, then physical constraint applies
- ✅ **ONE unified rule**: All zones → `if calculated flow < 28°C → OFF`

**Soft Landing Examples:**
```
Approaching from above:
  Current: 23.76°C, pred_err: -0.08°C
  Before v3.3: Stayed OFF → undershot to 23.50°C ❌
  v3.3: flow = 29.6 + (-0.08 × 5) = 29.2°C → lands at 23.62°C ✅

Approaching from below:
  Current: 23.45°C, pred_err: +0.09°C
  Before v3.3: Stayed at 30°C → overshot to 23.68°C ❌
  v3.3: flow = 28.0 + (0.09 × 5) = 28.5°C → lands at 23.62°C ✅
```

**Design Principles:**
- **Symmetrical**: Same formula works both directions (±)
- **Proportional**: Adjustment scales with predicted error
- **Outdoor-aware**: Based on reference flow from weather curve
- **Coherent**: One physical constraint rule everywhere

**Files Changed:**
- `config.py` - Added `landing_gain: 5.0` parameter
- `control_logic.py` - Proportional soft landing, unified emergency logic

---

### v3.2 - Critical Bug Fix (2025-11-07) 🐛

**BUG FIX - Fixed adjustment logic causing overheating**

**Critical Bug Found & Fixed:**
- 🐛 **Adjustment matching bug**: Negative predicted errors incorrectly matched positive thresholds
- 🐛 **Impact**: System heated when it should cool (e.g., pred_err=-0.26 → applied +3°C instead of forcing OFF)
- ✅ **Fixed**: Proper sign matching in threshold logic

**What Changed:**
- 🔧 **Fixed threshold matching** (`if threshold < 0 and pred_err < threshold`)
- 🔧 **Physical constraint rule**: Force OFF when calculated flow < 28°C (heat pump minimum)
- 🔧 **Removed magic number**: Replaced `-100` special case with `-4°C` adjustment

**Files Changed:**
- `control_logic.py` - Fixed adjustment logic bug, added physical constraint
- `config.py` - Updated gains (removed -100, added -4)

---

### v3.1 - Tuned Response (2025-11-06) 🎯

**TUNING UPDATE - Based on 11-hour test data**

**What Changed:**
- 🔧 **Faster emergency response** (trigger at 0.30°C error vs 0.40°C)
- 🔧 **Stronger cooling actions** (added -0.10 step, strengthened -0.15 to -3°C)
- 🔧 **Earlier overheat prevention** (force OFF at -0.20°C predicted vs -0.25°C)
- 🔧 **Less aggressive hysteresis** (0.08 threshold vs 0.12, reduces delays)

**Note:** v3.1 improvements were masked by the adjustment bug (fixed in v3.2)

**Files Changed:**
- `config.py` - 4 parameters tuned (emergency_error, adjustments, hysteresis)

---

### v3.0 - Unified Control (2025-11-06) 🎯

**MAJOR REWRITE - Complete Simplification**

**What Changed:**
- ✅ **Single unified algorithm** (removed cold/warm mode split)
- ✅ **Trajectory-based predictions** (2-hour history → 1-hour lookahead)
- ✅ **Soft landing** (coasts to target with correct momentum)
- ✅ **Outdoor transition detection** (adapts during rapid changes)
- ✅ **Analysis-ready CSV** (18 columns: all values separated, no mixed data/text)
- ✅ **50% code reduction** (562 → 280 lines of control logic)
- ✅ **55% fewer state variables** (11 → 5)
- ✅ **Version tracking** (new column in CSV for easy filtering)
- ✅ **DHW column** (dedicated column for DHW detection)

**Algorithm Overview:**

Every 10 minutes:
1. **Measure** - Read room temps, outdoor temp, heat pump status
2. **Calculate trajectory** - Least squares linear regression on 2-hour history
3. **Predict** - Forecast temperature 1 hour ahead
4. **Decide** - Choose flow based on 4 control zones:
   - **STABLE** (±0.05°C) → Hold current flow
   - **SOFT LANDING** (approaching target) → Coast to target
   - **EMERGENCY** (>0.30°C error in v3.1) → Jump ±5°C or force OFF
   - **NORMAL** → Adjust based on prediction
5. **Apply** - Set heat pump flow temperature immediately

**Expected Performance:**
- Temperature: **23.55-23.65°C** (±0.05-0.10°C precision)
- Response time: **10-20 minutes**
- Smooth outdoor transitions (no fighting)
- No overshoot/undershoot when approaching target

**Files Changed:**
- `config.py` - Unified parameters (168 lines)
- `control_logic.py` - Complete rewrite (280 lines, was 562)
- `state_manager.py` - Simplified state (299 lines, was 386)
- `melcloud_flow_controller.py` - Updated orchestration (244 lines)

**Issues Fixed:**
- ✅ Prolonged OFF periods even when below target
- ✅ Algorithm couldn't predict/prevent undershoot
- ✅ Overcomplicated hot penalty (too_hot_count reaching 40+)
- ✅ Hourly rhythm fighting trajectory predictions
- ✅ Redundant state storage in CSV

---

### v2.3 - Trajectory Prediction (2025-11-05)

**Added predictive control layer**

**Changes:**
- Added 2-hour trajectory analysis
- Hot penalty mechanism for prolonged high temps
- Immediate "mission accomplished" reset when cooling below target
- Consolidated rescue logic (emergency only)
- DHW valve guard with 90-minute timeout
- 2-decimal precision for temperature (faster trend detection)

**Issues:**
- Overcomplicated with multiple prediction layers
- too_hot_count could reach 40+ causing prolonged OFF periods
- Hourly rhythm fought against trajectory predictions
- Couldn't proactively prevent undershoot
- Too many redundant state variables

**Lessons Learned:**
- More layers ≠ better control
- Trust trajectory, don't fight it
- Hourly boundaries create artificial delays

---

### v2.2 - DHW Valve Guard (2025-11-04)

**Integrated noise prevention during hot water cycles**

**Changes:**
- Automatic 2nd-floor (Plan 2) valve closure during DHW heating
- Temperature rise detection (≥3°C = DHW active)
- State persistence across restarts
- Backup and restore valve setpoints

**Impact:**
- Eliminated water flow noise during DHW cycles
- Rooms automatically restored after DHW completion

---

### v2.1 - Trend Detection (2025-11-04)

**Added short-term trend analysis**

**Changes:**
- 10-minute trend layer (in addition to 2-hour trajectory)
- 2-decimal precision for average temperature
- Hybrid hot penalty (gradual + discrete)
- Trend-aware trim in cold mode

**Issues:**
- Too many prediction layers (10-min + 2-hour redundant)
- Increased complexity without proportional benefit
- Removed in v3.0 simplification

---

### v2.0 - Duty Cycling (2025-11-03)

**Warm mode duty cycling**

**Changes:**
- Hourly ON/OFF rhythm in mild weather (outdoor >6°C)
- Base duty fraction from outdoor temperature
- Duty bias from learned error
- Cold curve mode for cold weather (<6°C)
- Learned bias integrator

**Issues:**
- Hourly boundary created artificial response delays
- Duty cycling too rigid
- Mode switching confusing
- Removed in v3.0 for unified approach

---

### v1.0 - Initial Version (2025-10)

**Basic control implementation**

**Features:**
- LK Systems room temperature averaging
- Weighted averaging (de-emphasize hot rooms)
- MELCloud heat pump integration
- Simple weather curve
- Learned bias integrator
- CSV logging

**Issues:**
- No predictive control
- Slow response to disturbances
- Large temperature swings (±0.30°C)
- No outdoor transition handling

---

## Algorithm Explanation (v3.0)

### Core Principle

> **Trust the trajectory. The house tells you what it needs.**

The temperature trajectory (2-hour slope) already captures:
- Outdoor temperature effects
- Solar gain through windows
- Wind effects on heat loss
- DHW heating cycles
- Occupancy and internal gains
- Appliance use (dryer, cooking, etc.)

**No need to model each factor explicitly**—just respond to where the house is actually going.

### Decision Zones

The control algorithm operates in 4 zones:

#### 1. STABLE ZONE (±0.05°C, stable trajectory)
**Condition:** Temperature perfect or near-perfect  
**Action:** Hold current flow  
**Rationale:** System at equilibrium, don't disturb

**Example:**
```
Current: 23.60°C | Target: 23.60°C | Slope: 0.00°C/h
Predicted: 23.60°C (0.00 error)
Decision: HOLD 29°C
```

---

#### 2. SOFT LANDING ZONE (0.05-0.20°C, approaching target)
**Condition:** Small error with correct momentum toward target  
**Action:** Hold current flow (let it coast)  
**Rationale:** Momentum will carry to target, don't interrupt

**Example (Cold but Warming):**
```
Current: 23.55°C | Target: 23.60°C | Slope: +0.04°C/h
Predicted: 23.59°C (+0.01 error, very close!)
Decision: HOLD 30°C ✓ Soft landing!
```

**Example (Warm but Cooling):**
```
Current: 23.65°C | Target: 23.60°C | Slope: -0.03°C/h
Predicted: 23.62°C (-0.02 error, close)
Decision: HOLD 28°C ✓ Soft landing!
```

---

#### 3. EMERGENCY ZONE (>0.40°C error)
**Condition:** Way off target  
**Action:** Large immediate correction  
**Rationale:** Need aggressive response to major deviation

**Too Cold:**
```
Current: 23.20°C | Target: 23.60°C | Error: +0.40°C
Outdoor: 10°C, Reference: 28°C
Decision: 28 + 5 = 33°C (emergency jump)
```

**Too Hot:**
```
Current: 24.05°C | Target: 23.60°C | Error: -0.45°C
Decision: FORCE OFF (20°C)
```

---

#### 4. NORMAL ZONE (0.05-0.40°C error)
**Condition:** Moderate error, use prediction  
**Action:** Adjust based on where temperature is heading

**Outdoor Stable:**
```
Current: 23.50°C | Target: 23.60°C | Slope: -0.08°C/h
Predicted: 23.42°C (+0.18 error predicted)
Outdoor: 10°C, Reference: 28°C
Adjustment: +2°C (pred_err > 0.15)
Decision: 28 + 2 = 30°C
```

**Outdoor Transition (Rapid Change):**
```
Current: 23.65°C | Target: 23.60°C | Slope: +0.06°C/h
Outdoor: 15°C (was 10°C, rapid change!)
Last flow: 30°C
Predicted: 23.71°C (-0.11 error predicted)
Adjustment: -2°C from CURRENT (not -10 from new reference!)
Decision: 30 - 2 = 28°C (gentle step down)
```

---

### Weather Curve Reference

The algorithm uses outdoor temperature to determine a **reference flow** and **maximum flow limit**:

| Outdoor Temp | Reference | Max Flow | House Cooling Rate (OFF) |
|--------------|-----------|----------|--------------------------|
| > 15°C | 20°C | 28°C | -0.02°C/hour (very slow) |
| 10-15°C | 28°C | 30°C | -0.06°C/hour |
| 5-10°C | 30°C | 33°C | -0.10°C/hour |
| 0-5°C | 32°C | 36°C | -0.12°C/hour |
| -5-0°C | 34°C | 38°C | -0.16°C/hour |
| -10 to -5°C | 36°C | 38°C | -0.20°C/hour |
| < -10°C | 38°C | 38°C | -0.25°C/hour (fast) |

**Linear interpolation** between points.

**Usage:**
- **Steady outdoor:** Adjust from reference
- **Rapid outdoor change:** Adjust from current flow (small steps ±2°C)

This prevents fighting the reference curve during sunny days (10°C → 15°C) or cold snaps (5°C → -5°C).

---

### Outdoor Transition Detection

**Rapid change:** Outdoor EMA changes >1°C/hour  
**Behavior:** Make small adjustments (±2°C) from current flow instead of jumping to new reference

**Why?** During a sunny day, outdoor might go 8°C → 16°C over 4 hours:
- ❌ **Without transition mode:** Reference jumps 30°C → 20°C, system fights itself
- ✅ **With transition mode:** 30 → 29 → 28 → 26 → 20 (smooth gradual reduction)

---

## CSV Format

### Current Structure (v3.0)

**18 Analysis Columns + Rooms + Comment:**

```csv
timestamp,version,outside_temp,ema_tout,avg_temp,flow_cmd,flow_temp,return_temp,
tank_temp_current,tank_temp_target,set_room_temp,traj_slope,predicted_temp,
predicted_error,reference_flow,adjustment,decision_zone,dhw_active,room::*,comment
```

**All Values in Dedicated Columns - Ready for Python Analysis:**

| Column | Description | Unit | Purpose |
|--------|-------------|------|---------|
| `timestamp` | Time series index | ISO format | Time axis for plotting |
| `version` | Algorithm version | `3.0` | Filter data by version |
| `outside_temp` | Raw outdoor measurement | °C | External conditions |
| `ema_tout` | Smoothed outdoor (algorithm input) | °C | What algorithm sees |
| `avg_temp` | Weighted room average | °C | **Controlled variable** |
| `flow_cmd` | Heat pump setpoint | °C | **Control action** |
| `flow_temp` | Actual measured flow | °C | Verify command applied |
| `return_temp` | Actual measured return | °C | System efficiency |
| `tank_temp_current` | DHW tank temperature | °C | DHW detection |
| `tank_temp_target` | DHW target | °C | DHW state |
| `set_room_temp` | Target temperature | °C | Always `23.6` |
| `traj_slope` | Temperature trajectory | °C/hour | **Trend indicator** |
| `predicted_temp` | Forecast 1h ahead | °C | **What algorithm expects** |
| `predicted_error` | Predicted deviation | °C | **Key decision metric** |
| `reference_flow` | Weather curve baseline | °C | Reference point |
| `adjustment` | Applied correction | °C | Deviation from reference |
| `decision_zone` | Control mode | text | STABLE/LANDING/EMERGENCY/NORMAL |
| `dhw_active` | DHW heating active | 0/1 | **Disturbance indicator** |
| `room::*` | Individual room temps | °C | Per-room monitoring (10-11 columns) |
| `comment` | Descriptive text only | text | Human-readable explanation |

**Design Philosophy:**
- ✅ **All data values in columns** - No parsing needed
- ✅ **Comment is descriptive only** - No mixed data/text
- ✅ **Easy pandas analysis** - `df['predicted_error'].plot()`
- ✅ **Version tagged** - Filter by algorithm version
- ✅ **Self-documenting** - Column names explain content

**Removed Redundant Columns:**
- ❌ Old v2.x: `duty_base`, `duty_bias`, `duty_eff`, `duty_on`
- ❌ Old v2.x: `state_learn_bias`, `state_last_boost`, `state_too_hot_count`
- ❌ Internal state that can be reconstructed from previous rows

---

### Python Analysis Example

All values in dedicated columns make analysis trivial:

```python
import pandas as pd

# Load CSV
df = pd.read_csv('heating_log.csv')

# Filter by version
df_v3 = df[df['version'] == '3.0']

# Plot controlled variable vs target
df_v3['avg_temp'].plot(label='Actual')
df_v3['set_room_temp'].plot(label='Target')

# Analyze prediction accuracy
df_v3['prediction_error_actual'] = df_v3['set_room_temp'] - df_v3['avg_temp']
error = (df_v3['predicted_error'] - df_v3['prediction_error_actual']).abs()
print(f"Mean prediction error: {error.mean():.3f}°C")

# Zone performance
print(df_v3.groupby('decision_zone')['avg_temp'].describe())

# Flow efficiency
print(f"Time in STABLE zone: {(df_v3['decision_zone']=='STABLE').sum() / len(df_v3) * 100:.1f}%")

# DHW impact analysis
df_normal = df_v3[df_v3['dhw_active'] == 0]  # Normal operation
df_dhw = df_v3[df_v3['dhw_active'] == 1]     # During DHW
print(f"DHW cycles: {len(df_dhw)} / {len(df_v3)} ({len(df_dhw)/len(df_v3)*100:.1f}%)")
print(f"Avg temp drop during DHW: {(df_normal['avg_temp'].mean() - df_dhw['avg_temp'].mean()):.2f}°C")
```

**No comment parsing. No JSON decoding. Just pure data.**

---

### Backward Compatibility

The system **automatically migrates** old CSV files:
- Reads old format (v2.x with 30+ columns)
- Preserves all existing data
- Writes new format (v3.0 with 18+ columns)
- Reconstructs state from previous rows when possible
- Adds new analysis columns (predicted_temp, predicted_error, dhw_active, etc.)

**Migration happens automatically on first run.** No manual intervention needed. Your existing data is safe and will be preserved.

---

## Files

### Core Application
- **`melcloud_flow_controller.py`** - Main entry point (orchestrates everything)
- **`control_logic.py`** - Unified control algorithm
- **`config.py`** - Configuration parameters
- **`state_manager.py`** - CSV persistence and state reconstruction

### Integration Modules
- **`lk_systems.py`** - LK room temperature interface
- **`melcloud.py`** - Heat pump interface (MELCloud API)
- **`dhw_valve_guard.py`** - DHW noise prevention
- **`utils.py`** - Helper functions

### Documentation
- **`README.md`** - This file (comprehensive guide)
- **`UNIFIED_CONTROL_V3_SUMMARY.md`** - Detailed v3.0 explanation with examples
- **`QUICK_START_V3.md`** - Deployment and troubleshooting guide
- **`V3_CHANGES_AT_A_GLANCE.txt`** - Quick reference summary

### Data Files
- **`heating_log.csv`** - Temperature and control log
- **`dhw_valve_guard.log`** - DHW valve operations log
- **`dhw_valve_state.json`** - DHW valve state (runtime)

---

## Configuration

Edit `config.py` to tune performance:

### Adjust Sensitivity
```python
CONTROL_ZONES = {
    "stable_error": 0.05,  # Increase to 0.08 for less sensitivity
    "landing_pred_error": 0.10,  # Increase to 0.15 for wider landing zone
}
```

### Adjust Aggressiveness
```python
ADJUSTMENTS = {
    "gains": [
        (0.25, 3),  # Reduce 3→2 for gentler corrections
        (0.15, 2),  # Reduce 2→1 for very gentle
        ...
    ],
}
```

### Adjust Outdoor Response
```python
OUTDOOR_TRANSITION = {
    "rapid_change_threshold": 0.167,  # Reduce to 0.10 for more transition detection
    "transition_step_limit": 2,        # Reduce to 1 for very cautious transitions
}
```

### Modify Weather Curve
```python
WEATHER_CURVE = {
    "anchors": [
        # (outdoor_temp, reference_flow, max_flow)
        (10, 28, 30),  # Adjust reference/max as needed
        ...
    ],
}
```

---

## Expected Performance

### After 2 Hours (Trajectory Built)
- ✅ Temperature: **23.55-23.65°C** (±0.05-0.10°C)
- ✅ Response: **10-20 minutes** to disturbances
- ✅ Flow stability: Minimal changes at equilibrium
- ✅ Soft landing: No overshoot approaching target
- ✅ Outdoor adaptation: Smooth during sunny days

### Monitoring CSV
Look for these patterns:

**Good (Stable):**
```csv
...,23.60,3.0,10.2,23.60,29,...,0.00,...,STABLE(err=0.00) | v3.0
...,23.58,3.0,10.2,23.58,29,...,-0.01,...,STABLE(err=-0.02) | v3.0
```
→ Locked on target

**Good (Soft Landing):**
```csv
...,23.55,3.0,10.2,23.55,30,...,+0.04,...,SOFT_LAND(cold→warm, err=0.05, pred=0.01) | v3.0
...,23.58,3.0,10.2,23.58,30,...,+0.02,...,SOFT_LAND(cold→warm, err=0.02, pred=0.00) | v3.0
...,23.60,3.0,10.2,23.60,30...,0.00,...,STABLE(err=0.00) | v3.0
```
→ Coasted to target perfectly

---

## Troubleshooting

### Temperature oscillates
**Symptom:** 23.50 → 23.70 → 23.50 repeatedly  
**Cause:** Soft landing zone too narrow  
**Fix:** Increase `landing_error_max` to 0.25 or 0.30

### Temperature drifts away
**Symptom:** Slowly drifts from 23.60 to 23.45  
**Cause:** Stable zone too wide  
**Fix:** Decrease `stable_error` to 0.03 or 0.04

### Too many flow changes
**Symptom:** Flow changes every 10 minutes  
**Cause:** Hysteresis too tight  
**Fix:** Increase `on_threshold` and `off_threshold` to 0.15

### Not responsive to outdoor changes
**Symptom:** Flow doesn't adapt during sunny days  
**Cause:** Transition detection threshold too high  
**Fix:** Reduce `rapid_change_threshold` to 0.10

### CSV errors during migration
**Symptom:** "Column X not found" or similar  
**Cause:** Unexpected old CSV format  
**Fix:** Backup CSV, delete header row, let system recreate

---

## System Requirements

- **Python:** 3.7+
- **OS:** Windows 10+ (Task Scheduler)
- **Hardware:** LK Systems floor heating + Mitsubishi heat pump
- **Network:** Internet access for MELCloud API

---

## Support & Development

**Project:** Private use  
**Created:** 2025-10  
**Last Updated:** 2025-11-06  
**Version:** 3.0

For questions or issues, refer to:
- `UNIFIED_CONTROL_V3_SUMMARY.md` - Detailed explanation
- `QUICK_START_V3.md` - Deployment guide
- CSV `comment` column - Shows decision rationale

---

## License

Private use only.

---

**End of README** | v3.0 | 2025-11-06

