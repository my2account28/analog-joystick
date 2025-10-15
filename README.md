# What is this?
A Python application that displays a real-time cursor on the Linux framebuffer controlled by an analog joystick. The system automatically calibrates itself by learning the joystick's range and center position during normal use. This project relies on a Linux with ADC support, like the Luckfox pico / Rockchip rv1103 SoC.

[![Watch the video](https://img.youtube.com/vi/RwOpla9Zhpo/0.jpg)](https://www.youtube.com/watch?v=RwOpla9Zhpo)

## Features
- **Automatic Calibration**: Learns joystick range and center position dynamically
- **Center Lock**: Locks center position after initial calibration period
- **Deadzone Handling**: Automatically snaps cursor to center when idle
- **Range Expansion**: Dynamically expands range as you reach new extremes
- **Framebuffer Support**: Works with 16-bit, 24-bit, and 32-bit framebuffers
- **Efficient Updates**: Only updates changed portions of the screen

## Hardware requirements
- Luckfox Pico (Rockchip RV1103 SoC)
- Analog joystick connected via ADC, voltage compatible with SoC ADC (0 - 1.8V)
- Wires
 
<img width="594" height="253" alt="image" src="https://github.com/user-attachments/assets/18ec56b0-5701-4602-9fbf-52611bac1108" />

## Wiring
<img width="622" height="200" alt="image" src="https://github.com/user-attachments/assets/330e7487-6348-41a9-926a-e430c85c007f" />  

```
SoC (System-on-Chip)
┌─────────────────┐
│                 │
│  Pin 145 ───────┼──→ Joystick X-axis (Analog)
│                 │
│  Pin 144 ───────┼──→ Joystick Y-axis (Analog)
│                 │
│  1V8     ───────┼──→ Joystick VCC
│                 │
│  GND     ───────┼──→ Joystick GND
│                 │
└─────────────────┘
```

| SoC Pin | Joystick Pin | Function | Voltage |
|---------|--------------|----------|---------|
| 145     | X-axis       | Analog X | 1.8V    |
| 144     | Y-axis       | Analog Y | 1.8V    |
| 1V8     | VCC          | Power    | 1.8V    |
| GND     | GND          | Ground   | 0V      |

## How to run
1. Ensure you have Python 3 installed
2. Clone or download this script to your device
3. Make sure the script has read access to the ADC and write access to the framebuffer

Run with `python joystick.py`, the script will:  
- Detect your framebuffer resolution and color depth
- Clear the screen to black
- Display a white cursor controlled by your joystick

For remote viewing, run VNC server: `x11vnc -rawfb console -auth /dev/null -noxdamage -forever -shared -repeat -defer 0 -wait 0 -noxinerama -nowf -nowcr -speeds modem -tightfilexfer` and connect to the server IP with any VNC client:  

![Screencast from 10-14-2025 05-01-18 PM](https://github.com/user-attachments/assets/de4c3a17-8acd-4557-bf8f-ea6bf78fc2ce)

## Algorithm
- Exponential Moving Average (EMA) for smooth cursor movement
- Asymmetric normalization for independent axis calibration
- Dynamic range expansion with smoothing
- Center deadzone with snap-to-center behavior

## Calibration process
1. **Initial Center Learning**: The system learns the center position during the first ~2 seconds
2. **Range Expansion**: As you move the joystick to new extremes, the range expands accordingly
3. **Center Lock**: After the initial period, the center position becomes fixed
4. **Idle Detection**: When the joystick is near center for a short time, the cursor snaps to exact center

## Configuration
You can adjust the behavior by modifying these constants at the top of the script:  
```python
CURSOR_SIZE = 7                    # Size of the cursor in pixels
EMA_ALPHA = 0.25                   # Exponential moving average smoothing factor
DEADZONE_THRESHOLD_V = 0.04        # Voltage threshold for center deadzone
MIN_FRAMES_AT_CENTER = 6           # Frames required to snap to center
CENTER_LOCK_FRAMES = 100           # Frames before center position locks
```
