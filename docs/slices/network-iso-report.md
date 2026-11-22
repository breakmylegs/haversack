# Network ISOs in place (R24, v0.45.0)

## What changed

- **The gate is open.** Peter approved `fusermount3` for the System Binary Register on 22 November 2026, so `netfuse.FUSERMOUNT_APPROVED` is now True. The in-place install from shares that are not mounted (ADR-0067) is on.
  - Keepsake mounts its own read-only one-file FUSE file system with `ro,nosuid,nodev,noexec,auto_unmount`.
  - It falls back to copying if anything fails: the mount, a server without ranges, a refused loop setup, or no `/dev/fuse`.
- **The register.** ADR-0018's row is marked approved, and the v2 build prompt's register table gains `fusermount3`.
- **Docs:** ADR-0067 status, CHANGELOG, device run step 45 and the plan.

## Tests

- `tests/test_netfuse.py` and `tests/test_installer_smb.py` pass. The gate test now checks the approval and the refusal when the gate is off.
- Mutation test: setting the gate back to off is caught.
- Threat model: no change. T-entries for the FUSE mount were written with ADR-0067; only the gate changed.

## On-device checklist

Device run step 45.
