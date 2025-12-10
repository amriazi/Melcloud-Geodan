# Hydronic Floor Heating Controller

A trajectory-based flow temperature controller for hydronic floor heating systems with heat pump integration. Maintains precise indoor temperature control using 2-hour lookahead prediction and weather-based flow temperature optimization.

## 🎯 Key Features

- **Trajectory-Based Control** - Uses 2-hour temperature history and prediction to account for thermal lag
- **Weather Curve Optimization** - Physics-based flow temperature limits based on outdoor conditions
- **Single-Step Adjustments** - Conservative ±1°C/hour changes prevent overshoot
- **Dual Mode Support** - Normal mode for comfort, holiday mode for energy savings
- **Manual Mode** - Calculate and log without applying changes (for testing/tuning)
- **Robust Error Handling** - Shelly backup thermometer, CSV state persistence, graceful API failure handling
- **DHW Integration** - Automatic valve management during domestic hot water cycles

## 📋 Requirements

- Python 3.7+
- Mitsubishi Ecodan/Geodan heat pump with MELCloud API access
- LK Systems floor heating with API access (or Shelly backup thermometer)
- Windows/Linux/MacOS

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:
```env
LK_EMAIL=your_lk_email@example.com
LK_PASSWORD=your_lk_password
MEL_EMAIL=your_melcloud_email@example.com
MEL_PASSWORD=your_melcloud_password
SHELLY_AUTH_KEY=your_shelly_auth_key  # Optional
SHELLY_DEVICE_ID=your_shelly_device_id  # Optional
```

### 3. Configure Settings

Edit `config.py` to adjust:
- Target room temperature
- Weather curve anchors
- Control zones
- Flow temperature limits
- Holiday mode settings (if needed)

### 4. Run

```bash
python melcloud_flow_controller.py
```

### 5. Schedule (Windows Task Scheduler)

Run every 10 minutes for monitoring, control decisions happen at the top of each hour (XX:00).

## 📁 Project Structure

```
Flow_controller/
├── melcloud_flow_controller.py  # Main entry point
├── control_logic.py              # Core control algorithms
├── state_manager.py              # CSV state persistence
├── config.py                     # Configuration (non-sensitive)
├── .env                          # Credentials (git-ignored)
├── .env.example                  # Credentials template
├── melcloud.py                   # MELCloud API integration
├── lk_systems.py                 # LK Systems API integration
├── shelly_backup.py              # Shelly backup thermometer
├── dhw_valve_guard.py            # DHW valve management
├── utils.py                      # Utility functions
└── heating_log.csv               # Operational log (git-ignored)
```

## 🎛️ Configuration

### Normal Mode

- **Target Temperature**: 23.5°C (configurable)
- **Flow Limits**: 20-38°C
- **Control Zones**: STABLE (±0.05°C), NORMAL (single-step)
- **Weather Curve**: Adaptive based on outdoor temperature

### Holiday Mode

Enable in `config.py`:
```python
HOLIDAY_MODE = {"enable": 1}  # 1 = enabled, 0 = disabled
```

- **Target Temperature**: 18.0°C (energy-saving)
- **Flow Limits**: 20-28°C (lower cap)
- **Control Zones**: Wider STABLE zone (±0.15°C)
- **Weather Curve**: More conservative (lower flow temps)

### Manual Mode

Enable in `config.py`:
```python
MANUAL_MODE = {"enable": 1}  # 1 = enabled, 0 = disabled
```

When enabled:
- Calculates flow temperature decisions
- Logs everything to CSV
- **Does NOT apply** changes to heat pump
- All CSV comments show "Manual mode"

## 📊 How It Works

### Control Rhythm

1. **Every 10 minutes**: Fetch temperatures, calculate trajectory, log to CSV
2. **At XX:00 (top of hour)**: Make control decision, apply flow temperature
3. **XX:10-XX:50**: Monitor only, show predictions, no changes

### Decision Logic

1. **Calculate Trajectory**: Linear regression over last 2 hours of temperature data
2. **Predict Future**: Extrapolate 2 hours ahead (accounts for floor heating thermal lag)
3. **Determine Zone**:
   - **STABLE**: Near target (±0.05°C) → Hold current flow
   - **NORMAL**: Need adjustment → Single-step change (±1°C or OFF↔28°C)
4. **Enforce Weather Curve**: Apply min/max limits based on outdoor temperature
5. **Apply**: Set flow temperature via MELCloud API

### Weather Curve

Physics-based limits that prevent:
- Too low flow → Insufficient heating in cold weather
- Too high flow → Energy waste in mild weather

Anchors define min/reference/max flow temperatures for different outdoor temperatures.

## 📈 CSV Logging

All operations are logged to `heating_log.csv` with:
- Timestamps
- Temperatures (outdoor, indoor, flow, return, tank)
- Control decisions (flow command, zone, predicted error)
- Room-by-room temperatures
- Comments explaining decisions

## 🔒 Security

- Credentials stored in `.env` file (git-ignored)
- `.env.example` provided as template (no real credentials)
- Never commit `.env` to version control

## 🛠️ Troubleshooting

### API Failures

- LK Systems fails → Falls back to Shelly thermometer
- Both fail → Uses last known temperature from CSV
- MELCloud fails → Logs warning, retries next cycle

### CSV Corruption

- Uses append-only writes (never rewrites historical data)
- Version tracking prevents data loss
- Backward compatible with older CSV formats

### Manual Adjustments

Use Manual Mode to:
- Test control logic without applying changes
- Analyze predictions vs. actual behavior
- Tune parameters safely

## 📝 Version History

- **v5.5** - Added holiday mode and manual mode switches
- **v5.4** - Simplified control logic (removed consecutive pause)
- **v5.3** - Fixed weather minimum enforcement
- **v5.2** - Weather curve uses raw outdoor temp (faster response)
- **v5.1** - Refined overshoot detection
- **v5.0** - Added overshoot detection
- **v4.9** - Append-only CSV (prevents corruption)
- **v4.8** - Shelly backup thermometer, robust API handling
- **v4.7** - Directional pause mechanism
- **v4.6** - Fixed monitoring display

See `CHANGELOG.md` for detailed history.

## 📄 License

[Add your license here]

## 🤝 Contributing

[Add contribution guidelines if applicable]

## ⚠️ Disclaimer

This software controls heating systems. Use at your own risk. Always verify operation and have manual overrides available.

