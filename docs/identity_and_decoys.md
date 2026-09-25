# Identity and Decoys

Primary target must have ≥1 observable property that decoys do not share (Plan §3).

## Primary-target profile (`configs/identity_signatures.yaml`)

```yaml
primary:
  blink_pattern: "10110010"
  modulation_freq_hz: 12.0
  freq_tolerance: 0.05   # ±5%
  shape: square
  size_range_px: [5, 20]
```

## Decoy profiles

- Bright reflection (similar brightness, no valid signature)
- Moving decoy (similar motion, different blink pattern / 8 Hz)
- Noise blob (unstable shape/position)
- False beacon (similar appearance, inconsistent trajectory)

## Distinguishing characteristics

| Characteristic | Primary | Decoy |
|---|---|---|
| Coded blinking | Known pattern `10110010` | Different / incorrect |
| Modulation freq | 12 Hz ±5% | 8 Hz / unstable |
| Shape & size | Compact expected | Irregular / out-of-range |
| Motion | Allowed trajectory, ≤20 px/frame | Jumps / inconsistent |
| Persistence | Stable across frames | Brief / flickers |
| Spectral | Expected band (if supported) | Mismatched |

Baseline: known blink + shape/size + motion consistency + multi-frame persistence. Brightness alone never identifies primary.

## Identity scoring (Plan §6)

```
IdentityScore = 0.20*appearance + 0.20*motion + 0.20*temporal + 0.25*signature + 0.15*estimator_consistency
Confirm when score > 0.85 for 5 consecutive frames (tunable via model_thresholds.yaml).
Incomplete evidence → UNKNOWN (do not force PRIMARY/DECOY).
```
