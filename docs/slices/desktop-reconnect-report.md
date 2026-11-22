# Reconnect help in the desktop app (R24 first part, v0.42.0)

## What changed

- **A new desktop page,** Device, Reconnect help (`desktop/src/main.ts` `reconnectPage`, types in `desktop/src/types.ts`). It uses the same backend calls as Gaming Mode:
  - the device list with help switches;
  - Pair and commit;
  - Reconnect, Diagnose, Read stored host over USB, Export report bundle;
  - with the helper: cable pairing and Restore backup, each asking twice, the reversed key order, and the SSP gate behind its warning and a typed "I understand";
  - dry run and the recent actions.
- **Helper install stays in Gaming Mode.** Installing the helper needs Decky's installer, so the page points there.
- **Wording.** The Controllers page no longer says the root helper is "waiting for a decision".
- **Docs:** CHANGELOG, ADR-0082 consequences, the user guide, device run step 40 and the plan.

## Tests

- `tests/test_desktop_calls.py`: every call in the desktop app exists in the host's call list, and the page is registered. 2 passed.
- Mutation tests: 2 mutations (an unknown call name, the page removed), both caught.
- Threat model: no change, because the page adds no new capability, only another surface for T147 to T153's gated calls.

## On-device checklist

Device run step 40.
