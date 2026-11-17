# ADR-0037: Standing delegation of decisions

- Status: accepted (Peter's owner decision, 17 November 2026)
- Date: 17 November 2026
- Deciders: Peter (owner)
- Amends: the escalation rules in `CLAUDE.md` section 4 and the stop at each slice end in section 5

## Decision (Peter's words, condensed)

"Always make the best decision for the app yourself, and record it in an ADR with your reasoning and sources. Only stop for things you genuinely can't do: physical device runs, signing in to my accounts, or anything that needs my credentials. When you stop, say exactly what you need from me, as step-by-step commands I run and report back on."

## How it is applied

1. **Escalation items become recorded decisions.** For each item listed in `CLAUDE.md` section 4, Claude:
   - decides, choosing what is best for users' saves, devices and privacy;
   - records the decision in an ADR, with the options, the reasoning and primary sources;
   - carries on without waiting.

   The principles themselves are not loosened by this ADR. Changing one still needs its own ADR that says why, so the record stays honest.
2. **The only stops** are what Claude cannot do:
   - physical device runs (SteamOS and Bazzite devices, a NAS);
   - signing in to Peter's accounts or registering apps under them (Microsoft Entra, Google Cloud, GitHub settings that need his login);
   - anything needing his credentials or secrets;
   - anything this laptop's own security policy blocks Claude from doing. One example is handling a key file (ADR-0036). Claude does not try to get around such a guardrail.
3. **Every stop** ends with exact step-by-step commands for Peter to run, and what to report back.
4. **Pull requests** merge once the gate passes and the change's tests (with their mutation checks) pass. This follows Peter's earlier permission to merge without device testing. Device checks are listed in each report for Peter's next run.
5. **Releases** go out with whatever is ready. A feature that still needs Peter, such as the built-in sign-in client IDs, ships switched off rather than holding the release back.
6. **The queue** continues past slice ends. A slice whose acceptance needs a device is built as far as possible, its device steps are handed to Peter, and work moves on to the next item that does not need a device.

## Consequences

- Fewer stops. The ADRs carry the reasoning Peter would otherwise have been asked for.
- Peter's attention goes only to device runs and account steps, each given as commands.
