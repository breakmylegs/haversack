# R21 stage 4 report: the battery charge limit (v0.35.0)

Stage 4 of Peter's Legion Go controls, which folds in R17. The decisions are in ADR-0077. Stage 3 (fans) needs root, so it waits for Peter's decision on ADR-0075 tier 1, and this stage came first.

## What changed

- **`keepsake/device/battery.py`:**
  - reads the kernel's `charge_types` or threshold from the system battery, and never from a controller's battery;
  - turns the 80 percent limit on (80) or off (-1) through steamos-manager's `BatteryChargeLimit1`, read back;
  - where that interface is not offered, shows the state, says where to change it, and writes nothing.
- **steamos-manager:** a new `set_charge_limit`.
- **New calls:** `device_battery` and `device_set_charge_limit`. The change refuses while the Device module is off.
- **Where it shows:**
  - Device, Battery;
  - a "Stop charging at 80%" toggle in the quick access menu, shown only where Keepsake can change it;
  - the desktop app's Battery page.
- **The Device check "Battery charge limit".**

## Not done, and why

- **Writing `charge_types` directly needs root.** It is tier 1, waiting for Peter.
- **Valve's Legion device file has not enabled `BatteryChargeLimit1`.** On the devices, Keepsake may only show the state until Valve does. The device run's check records which case applies.

## Tests

- **New:** `tests/test_device_battery.py`, 9 tests:
  - the kernel state from the system battery, with a controller's battery listed first and ignored;
  - a threshold counts too;
  - steamos-manager sets the limit and reads it back;
  - without steamos-manager it only shows the state and says where to change it;
  - a read-back that differs is an error;
  - the device check in three states;
  - the app sets the limit, and refuses while the module is off.
- **Regression:** `tests/test_device_performance.py`.
- **Mutation tests:** 7 mutations. One survived (the controller-battery rule), which led to a new test case. Now all 7 are caught.

## Threat model

T142.

## On-device checklist

`docs/device-run.md` part 4, step 25.
