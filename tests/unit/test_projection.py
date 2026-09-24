"""
Unit tests for virtual camera projection and coordinate conversion.
Tests FOV-to-pixel conversion and pan/tilt sign convention.
"""
import numpy as np
from fsoc_tracker.simulation.virtual_camera import VirtualCamera

def test_fov_to_pixel():
    cam = VirtualCamera(world_size=(2000,2000), resolution=(640,480), fov_deg=(4.0,3.0))
    # Centre should map to image centre
    pos = cam.world_to_image((1000, 1000))
    assert pos is not None
    # With camera at centre (1000,1000), world centre should be at image centre
    # Due to camera at (1000,1000) with 640x480 viewport, world (1000,1000) is centre
    assert abs(pos[0] - 320) < 1e-6
    assert abs(pos[1] - 240) < 1e-6

def test_angle_conversion():
    cam = VirtualCamera(world_size=(2000,2000), resolution=(640,480), fov_deg=(4.0,3.0))
    # Image centre error should be zero angle
    err = cam.image_to_angle_error((320, 240))
    assert err == (0.0, 0.0)
    # 10px right should be positive pan
    err = cam.image_to_angle_error((330, 240))
    assert err[0] > 0
    # 10px down should be negative tilt (image y increases down, tilt up is negative)
    err = cam.image_to_angle_error((320, 250))
    assert err[1] < 0

def test_pan_tilt_saturation():
    cam = VirtualCamera(world_size=(2000,2000), resolution=(640,480), fov_deg=(4.0,3.0), max_pan_speed=5.0, max_tilt_speed=5.0)
    # Command beyond limit should be clamped
    pan, tilt = cam.apply_command(100, 100, dt=1.0)
    assert abs(pan) <= 5.0 + 1e-6
    assert abs(tilt) <= 5.0 + 1e-6

def test_world_bounds_clamping():
    cam = VirtualCamera(world_size=(2000,2000), resolution=(640,480), fov_deg=(4.0,3.0))
    # Try to pan far beyond world
    cam.pan = 100  # far
    cam.tilt = 100
    cam._update_center()
    l, t, r, b = cam.get_viewport_bounds()
    assert 0 <= l < r <= 2000
    assert 0 <= t < b <= 2000
