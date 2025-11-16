#!/usr/bin/env python3
"""
LED Daemon - Autonomous LED control with PWM pulsing
Reads button press events and stop signals from audio daemon via named pipe
- GPIO 18 (configurable) controls the LED switch
- Idle state: Smooth PWM pulsing (off -> bright -> off in 5 seconds)
- Button pressed: Rapid flashing (on/off at 100ms intervals)
- Button interrupt: Restart flash sequence from beginning
- Stop signal (button ID 0): Return to idle pulsing
"""
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from enum import Enum

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO = None
    GPIO_AVAILABLE = False

# Event FIFO (named pipe) from audio daemon
EVENT_FIFO = Path("/tmp/sound_led_events")

# LED GPIO pin - single pin controls the LED switch
LED_GPIO_PIN = int(os.environ.get("LED_GPIO", "13"))

# Pulsing configuration
PULSE_CYCLE_SECONDS = 5.0  # Full cycle: off -> bright -> off
FLASH_ON_MS = 100  # Flash timing: 100ms on
FLASH_OFF_MS = 100  # Flash timing: 100ms off
IDLE_MIN_PWM = 20  # Minimum PWM duty cycle (20%) for idle pulsing
IDLE_MAX_PWM = 100  # Maximum PWM duty cycle (100%) for idle pulsing


class LEDState(Enum):
    """LED control states"""
    IDLE = "idle"  # Pulsing, waiting for interaction
    FLASHING = "flashing"  # Rapid on/off from button press


class LEDController:
    """Controls LED with PWM pulsing and flashing"""
    
    def __init__(self):
        global GPIO_AVAILABLE
        self.state = LEDState.IDLE
        self.pwm_instance = None
        self.control_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.initialized = False
        self.current_frequency = 1000  # PWM frequency in Hz
        
        if not GPIO_AVAILABLE:
            print("LED: GPIO not available - simulation mode")
            return
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(LED_GPIO_PIN, GPIO.OUT)
            GPIO.output(LED_GPIO_PIN, GPIO.LOW)
            self.pwm_instance = GPIO.PWM(LED_GPIO_PIN, self.current_frequency)
            self.pwm_instance.start(0)  # Start with 0% duty cycle (off)
            self.initialized = True
            print(f"LED: Initialized on GPIO {LED_GPIO_PIN}")
        except Exception as e:
            print(f"LED: GPIO init failed: {e}")
            GPIO_AVAILABLE = False
    
    def set_pwm_duty(self, duty_cycle: float) -> None:
        """Set PWM duty cycle (0-100)"""
        if not self.initialized or not GPIO_AVAILABLE or not self.pwm_instance:
            return
        try:
            duty_cycle = max(0, min(100, duty_cycle))  # Clamp to 0-100
            self.pwm_instance.ChangeDutyCycle(duty_cycle)
        except Exception:
            pass
    
    def _idle_pulsing_loop(self) -> None:
        """Smooth pulsing: off -> bright -> off in 5 seconds"""
        start_time = time.time()
        while self.state == LEDState.IDLE and not self.stop_event.is_set():
            elapsed = time.time() - start_time
            cycle_position = (elapsed % PULSE_CYCLE_SECONDS) / PULSE_CYCLE_SECONDS
            
            # Triangular wave: 0 -> 1 -> 0
            if cycle_position < 0.5:
                # First half: ramp up from IDLE_MIN_PWM to IDLE_MAX_PWM
                normalized = cycle_position * 2  # 0 to 1
                pwm_value = IDLE_MIN_PWM + (IDLE_MAX_PWM - IDLE_MIN_PWM) * normalized
            else:
                # Second half: ramp down from IDLE_MAX_PWM to IDLE_MIN_PWM
                normalized = (cycle_position - 0.5) * 2  # 0 to 1
                pwm_value = IDLE_MAX_PWM - (IDLE_MAX_PWM - IDLE_MIN_PWM) * normalized
            
            self.set_pwm_duty(pwm_value)
            time.sleep(0.05)  # Update PWM 20 times per second
    
    def _flashing_loop(self) -> None:
        """Rapid flashing: on/off at 100ms intervals"""
        while self.state == LEDState.FLASHING and not self.stop_event.is_set():
            # Flash ON
            self.set_pwm_duty(100)
            time.sleep(FLASH_ON_MS / 1000.0)
            
            # Flash OFF
            self.set_pwm_duty(0)
            time.sleep(FLASH_OFF_MS / 1000.0)
    
    def start_control_loop(self) -> None:
        """Start the main LED control loop"""
        if self.control_thread and self.control_thread.is_alive():
            return  # Already running
        
        self.stop_event.clear()
        self.control_thread = threading.Thread(target=self._run_control_loop, daemon=True)
        self.control_thread.start()
    
    def _run_control_loop(self) -> None:
        """Main control loop that switches between idle and flashing states"""
        while not self.stop_event.is_set():
            try:
                if self.state == LEDState.IDLE:
                    self._idle_pulsing_loop()
                elif self.state == LEDState.FLASHING:
                    self._flashing_loop()
                time.sleep(0.01)  # Prevent busy loop
            except Exception as e:
                print(f"LED: Control loop error: {e}")
                time.sleep(0.1)
    
    def button_pressed(self, button_id: int) -> None:
        """Handle button press - restart flashing"""
        with self.lock:
            self.state = LEDState.FLASHING
            print(f"LED: Button {button_id} pressed - starting flash")
    
    def stop_flashing(self) -> None:
        """Stop flashing and return to idle pulsing"""
        with self.lock:
            if self.state == LEDState.FLASHING:
                self.state = LEDState.IDLE
                print("LED: Audio finished - returning to idle pulsing")
    
    def cleanup(self) -> None:
        """Cleanup GPIO resources"""
        self.stop_event.set()
        if self.control_thread:
            self.control_thread.join(timeout=1.0)
        if self.pwm_instance:
            try:
                self.pwm_instance.stop()
            except Exception:
                pass
        if self.initialized:
            try:
                GPIO.output(LED_GPIO_PIN, GPIO.LOW)
            except Exception:
                pass


def main():
    # Create named pipe if it doesn't exist
    try:
        if EVENT_FIFO.exists():
            import stat
            if not stat.S_ISFIFO(EVENT_FIFO.stat().st_mode):
                print(f"ERROR: {EVENT_FIFO} exists but is not a named pipe", file=sys.stderr)
                sys.exit(1)
        else:
            os.mkfifo(str(EVENT_FIFO), 0o666)
            print(f"LED Daemon: Created FIFO at {EVENT_FIFO}")
    except FileExistsError:
        # Another process created it
        pass
    except Exception as e:
        print(f"ERROR: Failed to create FIFO: {e}", file=sys.stderr)
        sys.exit(1)
    
    controller = LEDController()
    controller.start_control_loop()
    
    print(f"LED Daemon: Monitoring {EVENT_FIFO}")
    print(f"LED Daemon: Using GPIO {LED_GPIO_PIN}")
    print(f"LED Daemon: Idle pulsing 5-second cycle, flash on button press")
    
    try:
        while True:
            try:
                # Open FIFO for reading (blocks until audio daemon opens it for writing)
                print("LED Daemon: Waiting for events from audio daemon...", file=sys.stderr)
                with open(str(EVENT_FIFO), 'r') as fifo:
                    while True:
                        line = fifo.readline()
                        if not line:
                            # EOF - audio daemon closed the pipe, reconnect
                            print("LED Daemon: Audio daemon disconnected, waiting for reconnection...", file=sys.stderr)
                            break
                        
                        try:
                            button_id = int(line.strip())
                            
                            # Special signal 0 = stop flashing, return to idle
                            if button_id == 0:
                                controller.stop_flashing()
                            else:
                                # Any other button ID = start/restart flashing
                                controller.button_pressed(button_id)
                                
                        except (ValueError, KeyError):
                            pass
                        
            except FileNotFoundError:
                print("LED Daemon: FIFO not found, waiting...", file=sys.stderr)
                time.sleep(1.0)
            except Exception as e:
                print(f"LED Daemon error: {e}", file=sys.stderr)
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        controller.cleanup()
        # Clean up FIFO
        try:
            if EVENT_FIFO.exists():
                EVENT_FIFO.unlink()
        except Exception:
            pass
        print("LED Daemon: Exiting")


if __name__ == "__main__":
    main()
