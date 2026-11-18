"""Replication: game installs and prefixes go device to device (slices 16 to 20).

Hard rules (ADR-0045), enforced by ``tests/test_replication_rules.py``:

- nothing here reaches a cloud store, the sync engine or cloud sign-in;
- nothing here compresses, at any layer.
"""
