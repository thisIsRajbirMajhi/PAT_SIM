TUNABLE PARAMETERS FOR OPTUNA (locked 2026-10-14)
Defaults: src/pat_common/config/sections/*.py | Limits: template.py:42-76 | Floors: docs/Hardware_Constraints.md
Fixed and OUT (never tuned): fps=30, max_pan/tilt_speed, fov_deg, resolution,
all test conditions (target, noise, atmosphere, platform, environment/stars, world, seed).

A. CAMERA START (applied post-far-start so tuned starts survive enforce_far_start)
1.  Initial Camera Position .... initial_position ..... centre | user-defined
2.  Initial Pan Angle ........... initial_pan ........... 0.0 deg | ±8 deg
3.  Initial Tilt Angle .......... initial_tilt .......... 0.0 deg | ±8 deg
4.  Update Interval ............. update_interval_hz .... 30 Hz | 20-60 (floor >= 20)

B. DETECTOR
5.  Threshold K ................. threshold_k ........... 3.0 | 2.0-5.0
6.  Min Area .................... min_area .............. 8 | 4-16
7.  Max Area .................... max_area .............. 900 | 400-1500

C. TRACKER / EKF
8.  Process Noise ............... process_noise ......... 0.8 | 0.1-5.0
9.  Meas Noise .................. meas_noise ............ 4.0 | 0.5-10.0
10. Gate Sigma .................. gate_sigma ............ 5.0 | 3.0-8.0
11. Lost Timeout ................ lost_timeout_frames ... 15 | 5-30
12. Reacq Timeout ............... reacq_timeout_frames .. 30 | 10-60

D. CONTROLLER PID
13. KP Pan ...................... kp_pan ................ 1.2 | 0.1-5.0
14. KP Tilt ..................... kp_tilt ............... 1.2 | 0.1-5.0
15. KI .......................... ki .................... 0.05 | 0-1.0
16. KD .......................... kd .................... 0.15 | 0-2.0
17. Deadzone PX ................. deadzone_px ........... 2.0 | 0-6.0
18. Integral Limit .............. integral_limit ........ 8.0 | 2-20
19. Feedforward Gain ............ feedforward_gain ..... 0.0 | 0-2.0

E. SEARCH & INTERCEPT POLICY
20. Search Angle Step ........... search_angle_step ..... 0.45 | 0.05-1.0
21. Search Radius Step .......... search_radius_step .... 0.09 | 0.01-0.5
22. Search Radius Max ........... search_radius_max ..... 4.5 | 2.0-8.0
23. Search Rate Scale ........... search_rate_scale ..... 0.85 | 0.3-1.5
24. Spiral Phase S .............. spiral_phase_s ........ 3.0 | 1-8
25. Raster Pan Scale ............ raster_pan_scale ...... 0.9 | 0.3-1.0
26. Raster Tilt Scale ........... raster_tilt_scale ..... 0.35 | 0.3-1.0
27. Stare Scale ................. stare_rate_scale ...... 0.3 | 0.1-0.8
28. Intercept Gain .............. intercept_gain ........ 2.0 | 0.5-5.0
29. Intercept Lead S ............ intercept_lead_s ...... 0.3 | 0-0.8
30. Uncertainty Scale ........... unc_scale ............. 0.6 | 0-2.0
31. Uncertainty Max Boost ....... unc_max_boost ......... 2.5 | 1-4
32. Fast Velocity ............... fast_vel_deg_s ........ 1.0 | 0.2-5.0
33. Give Up Frames .............. give_up_frames ........ 600 | 120-1800

TUNING ORDER (staged, ~33 dims too many flat):
Stage 1 core .... B + C(8,9) + D(13-17)
Stage 2 policy .. E + C(11,12)
Stage 3 polish .. joint re-tune of winners' region (all groups)
