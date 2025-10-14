import time
import os
import struct
import math

ADC_DIR = "/sys/bus/iio/devices/iio:device0"
FB_DEVICE = "/dev/fb0"
FB_SYSFS = "/sys/class/graphics/fb0"

CURSOR_SIZE = 7

# Filtering
EMA_ALPHA = 0.25
DEADZONE_THRESHOLD_V = 0.04
MIN_FRAMES_AT_CENTER = 6

# Center lock after initial settle
CENTER_LOCK_FRAMES = 100

def read_value(file_path):
    with open(file_path, "r") as file:
        return file.read().strip()

def get_framebuffer_info():
    try:
        with open(f"{FB_SYSFS}/virtual_size", "r") as f:
            w, h = map(int, f.read().strip().split(','))
        with open(f"{FB_SYSFS}/bits_per_pixel", "r") as f:
            bpp = int(f.read().strip())
        print(f"Framebuffer detected: {w}x{h}, {bpp} bpp")
        return w, h, bpp
    except Exception as e:
        raise RuntimeError(f"Failed to read framebuffer info: {e}")

def get_pixel_format(bpp):
    if bpp == 16:
        def pack_pixel(r, g, b):
            return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        return 2, pack_pixel
    elif bpp in (24, 32):
        def pack_pixel(r, g, b):
            if bpp == 24:
                return struct.pack("BBB", r, g, b)
            else:
                return struct.pack("<BBBB", b, g, r, 0xFF)
        byte_size = 4 if bpp == 32 else 3
        return byte_size, pack_pixel
    else:
        raise ValueError(f"Unsupported bits per pixel: {bpp}")

def draw_rect(fb, x, y, width, height, color, screen_w, screen_h, bpp):
    """Draw a filled rectangle at (x,y). Clips to screen bounds. Minimal I/O."""
    half_w = width // 2
    half_h = height // 2

    start_x = max(0, x - half_w)
    end_x = min(screen_w, x + half_w + 1)
    start_y = max(0, y - half_h)
    end_y = min(screen_h, y + half_h + 1)

    # Precompute packed color
    color_bytes = struct.pack("H", color) if bpp == 16 else color

    for py in range(start_y, end_y):
        offset_base = py * screen_w * len(color_bytes)
        for px in range(start_x, end_x):
            offset = offset_base + px * len(color_bytes)
            fb.seek(offset)
            fb.write(color_bytes)

def main():
    print("Starting Auto-Calibrating Joystick")
    print("   -> Just use the joystick normally. System learns range automatically.")
    print("   -> Center locks after ~2 seconds of any movement.")
    print("   -> Full range expands as you reach new extremes.")
    print("   -> Cursor snaps to center when idle.")

    SCREEN_WIDTH, SCREEN_HEIGHT, BPP = get_framebuffer_info()
    BYTES_PER_PIXEL, pack_color = get_pixel_format(BPP)

    COLOR_WHITE = pack_color(255,255,255) if BPP==16 else pack_color(255,255,255)
    COLOR_BLACK = pack_color(0,0,0) if BPP==16 else pack_color(0,0,0)

    fb = open(FB_DEVICE, "wb")

    # Clear screen ONCE at startup
    print("Clearing screen...")
    color_bytes = struct.pack("H", COLOR_BLACK) if BPP == 16 else COLOR_BLACK
    for i in range(SCREEN_WIDTH * SCREEN_HEIGHT):
        fb.write(color_bytes)
    fb.flush()

    class JoystickCalibrator:
        def __init__(self):
            self.center_x = None
            self.center_y = None
            self.center_samples = 0
            self.center_locked = False

            self.min_x = 1.8
            self.max_x = 0.0
            self.min_y = 1.8
            self.max_y = 0.0

            self.ema_x = 0.0
            self.ema_y = 0.0

            self.frames_near_center = 0

            self.last_raw_x = 0.0
            self.last_raw_y = 0.0

        def update(self, raw_x, raw_y, SCREEN_WIDTH, SCREEN_HEIGHT):
            self.last_raw_x, self.last_raw_y = raw_x, raw_y

            if self.center_samples == 0:
                self.ema_x = raw_x
                self.ema_y = raw_y

            self.ema_x = EMA_ALPHA * raw_x + (1 - EMA_ALPHA) * self.ema_x
            self.ema_y = EMA_ALPHA * raw_y + (1 - EMA_ALPHA) * self.ema_y

            if not self.center_locked:
                if self.center_x is None:
                    self.center_x = raw_x
                    self.center_y = raw_y
                else:
                    self.center_x += (raw_x - self.center_x) * 0.02
                    self.center_y += (raw_y - self.center_y) * 0.02

                self.center_samples += 1
                if self.center_samples >= CENTER_LOCK_FRAMES:
                    self.center_locked = True
                    print(f"Center locked at X={self.center_x:.4f}V, Y={self.center_y:.4f}V")

            if raw_x < self.min_x:
                self.min_x = self.min_x * 0.2 + raw_x * 0.8
            if raw_x > self.max_x:
                self.max_x = self.max_x * 0.2 + raw_x * 0.8
            if raw_y < self.min_y:
                self.min_y = self.min_y * 0.2 + raw_y * 0.8
            if raw_y > self.max_y:
                self.max_y = self.max_y * 0.2 + raw_y * 0.8

            self.min_x = max(0.0, min(1.8, self.min_x))
            self.max_x = max(0.0, min(1.8, self.max_x))
            self.min_y = max(0.0, min(1.8, self.min_y))
            self.max_y = max(0.0, min(1.8, self.max_y))

            if self.min_x > self.max_x:
                mid = (self.min_x + self.max_x) / 2
                self.min_x = mid - 0.01
                self.max_x = mid + 0.01
            if self.min_y > self.max_y:
                mid = (self.min_y + self.max_y) / 2
                self.min_y = mid - 0.01
                self.max_y = mid + 0.01

            center_x_use = self.center_x if self.center_locked else self.ema_x
            center_y_use = self.center_y if self.center_locked else self.ema_y

            # Asymmetric normalization to pixel
            if self.ema_x >= center_x_use:
                span_right = max(0.01, self.max_x - center_x_use)
                scale_right = ((SCREEN_WIDTH - 1) / 2.0) / span_right
                offset_x = int((self.ema_x - center_x_use) * scale_right)
                norm_pixel_x = (SCREEN_WIDTH - 1) // 2 + offset_x
            else:
                span_left = max(0.01, center_x_use - self.min_x)
                scale_left = ((SCREEN_WIDTH - 1) / 2.0) / span_left
                offset_x = int((center_x_use - self.ema_x) * scale_left)
                norm_pixel_x = (SCREEN_WIDTH - 1) // 2 - offset_x

            if self.ema_y >= center_y_use:
                span_down = max(0.01, self.max_y - center_y_use)
                scale_down = ((SCREEN_HEIGHT - 1) / 2.0) / span_down
                offset_y = int((self.ema_y - center_y_use) * scale_down)
                norm_pixel_y = (SCREEN_HEIGHT - 1) // 2 + offset_y
            else:
                span_up = max(0.01, center_y_use - self.min_y)
                scale_up = ((SCREEN_HEIGHT - 1) / 2.0) / span_up
                offset_y = int((center_y_use - self.ema_y) * scale_up)
                norm_pixel_y = (SCREEN_HEIGHT - 1) // 2 - offset_y

            norm_pixel_x = max(0, min(SCREEN_WIDTH - 1, norm_pixel_x))
            norm_pixel_y = max(0, min(SCREEN_HEIGHT - 1, norm_pixel_y))

            dx = abs(self.ema_x - center_x_use)
            dy = abs(self.ema_y - center_y_use)

            if dx < DEADZONE_THRESHOLD_V and dy < DEADZONE_THRESHOLD_V:
                self.frames_near_center += 1
            else:
                self.frames_near_center = 0

            if self.frames_near_center >= MIN_FRAMES_AT_CENTER:
                norm_pixel_x = (SCREEN_WIDTH - 1) // 2
                norm_pixel_y = (SCREEN_HEIGHT - 1) // 2

            return norm_pixel_x, norm_pixel_y, {
                'center': (self.center_x, self.center_y),
                'bounds': ((self.min_x, self.max_x), (self.min_y, self.max_y)),
                'locked': self.center_locked
            }

    calibrator = JoystickCalibrator()

    last_x, last_y = -1, -1
    last_print_time = 0

    try:
        while True:
            scale = float(read_value(f"{ADC_DIR}/in_voltage_scale"))
            raw_x = float(read_value(f"{ADC_DIR}/in_voltage1_raw")) * scale / 1000.0
            raw_y = float(read_value(f"{ADC_DIR}/in_voltage0_raw")) * scale / 1000.0

            screen_x, screen_y, stats = calibrator.update(raw_x, raw_y, SCREEN_WIDTH, SCREEN_HEIGHT)

            # >>> PARTIAL UPDATE: ONLY ERASE PREVIOUS CURSOR <<<
            if last_x != -1 and last_y != -1:
                draw_rect(fb, last_x, last_y, CURSOR_SIZE, CURSOR_SIZE, COLOR_BLACK,
                         SCREEN_WIDTH, SCREEN_HEIGHT, BPP)

            # >>> PARTIAL UPDATE: ONLY DRAW NEW CURSOR <<<
            draw_rect(fb, screen_x, screen_y, CURSOR_SIZE, CURSOR_SIZE, COLOR_WHITE,
                     SCREEN_WIDTH, SCREEN_HEIGHT, BPP)

            # Flush after both operations
            fb.flush()

            last_x, last_y = screen_x, screen_y

            # Debug print every 2 seconds
            if time.time() - last_print_time > 2.0:
                c = stats['center']
                b = stats['bounds']
                print(f"Center: ({c[0]:.3f}, {c[1]:.3f}) | "
                      f"X Range: [{b[0][0]:.3f}->{b[0][1]:.3f}] → Pixel: {screen_x} | "
                      f"Y Range: [{b[1][0]:.3f}->{b[1][1]:.3f}] → Pixel: {screen_y} | "
                      f"Locked: {stats['locked']}")
                last_print_time = time.time()

            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        fb.close()

if __name__ == "__main__":
    main()
