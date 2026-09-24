"""Tests for PID controller and saturation handling."""
from fsoc_tracker.control.pid import PIDController

def test_pid_deadzone():
    pid = PIDController(kp=1.2, ki=0.05, kd=0.15, deadzone=2.0, integral_limit=8.0)
    # Small error within deadzone should give zero command
    cmd = pid.step(0.01, dt=1/30)  # ~0.01 deg ~ 0.7px, within 2px deadzone
    assert abs(cmd) < 1e-6

def test_pid_saturation_and_anti_windup():
    pid = PIDController(kp=5.0, ki=1.0, kd=0.0, deadzone=0.5, integral_limit=2.0)
    # Large error should produce large command but integral should be clamped
    for _ in range(100):
        pid.step(5.0, dt=1/30)
    assert abs(pid.integral) <= pid.integral_limit + 1e-6

def test_pid_derivative_damping():
    pid = PIDController(kp=1.0, ki=0.0, kd=0.3, deadzone=0.5)
    # Step error then small change should have damped derivative
    c1 = pid.step(2.0, dt=1/30)
    c2 = pid.step(2.1, dt=1/30)
    # Derivative should not cause huge jump
    assert abs(c2 - c1) < 2.0
