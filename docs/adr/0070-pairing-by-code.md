# ADR-0070: Pairing by code: request, accept, type the code

- Status: accepted (Peter's request of 21 November 2026, decided under ADR-0037). Supersedes ADR-0054 points 4.5 (both users confirm) and 4.6 and 4.7 (the pairing window, and comparing instead of typing), and the comparison step in ADR-0056. Changes the frozen pairing messages (an escalation item, decided here).
- Date: 21 November 2026
- Deciders: Peter (owner)

## Context

Today one device opens a 120-second pairing window, the other connects, both screens show the same 6-digit code, and the user presses "The codes match" on both. Peter wants instead:
- no window to open first: "Let other devices reach this one" being on is enough;
- the requester (say the Go 2) sends a request;
- the receiver (the Go) shows "Legion Go 2 wants to pair" with **Accept** and **Decline**, and declining or no answer in 120 seconds pairs nothing;
- the receiver shows a 6-digit code, which the user types on the requester with a controller-friendly number pad;
- a right code pairs both devices and a wrong one ends the attempt on both.

Security must keep ADR-0054's protection:
- the code is not a password or a key, and a device in the middle gets one chance in a million per attempt and nothing to try offline;
- limits: one code entry per attempt, at most 3 requests per 2 minutes on the receiver, and 5 failed attempts lock an address or device ID out for 10 minutes;
- unpaired devices get only the pairing handshake;
- the Accept screen shows the requester's name and address;
- no request is shown while a game runs.

## The derivation Peter asked for, and why it changes

Peter asked for the code to be derived exactly as today: from `tls-unique`, the committed nonces and both device IDs. The requester would compare it with what is typed, and only then send the link key.

That keeps the **requester** safe, but not the **receiver**:
- A device in the middle holds two TLS sessions, one with each device. The code on the receiver comes from the session between the middle device and the receiver, so **the middle device can compute it too**.
- When the user types that code on the real requester, the requester's own code differs, and it refuses.
- But nothing stops the middle device from sending the receiver its own link key straight away. The receiver, which only showed a code and checks nothing, would store it and say "Paired". The user would see "wrong code" on the Go 2 and "Paired" on the Go, with a stranger's key on the Go.

With a code both ends can compute, only a check by the user on both screens closes that gap, and that is today's comparison step, which Peter is replacing. So the code has to be something the middle device cannot know: **random, shown only on the receiver's screen**.

A random 6-digit code sent as a plain proof (for example an HMAC of the code) could be brute-forced offline by the middle device, which is ADR-0054's point 4.7. So the devices prove the code **one bit at a time with commitments**. This is the passkey entry method of Bluetooth Secure Simple Pairing (Core Specification, Volume 3, Part H, section 2.3.5.6.3).

## Decision

1. **Requests while the listener is on.** There is no pairing window. The receiver takes pairing handshakes whenever its listener is on, with these limits:
   - at most 3 in 2 minutes; more are refused in the TLS handshake;
   - an address, or a device ID once named, with 5 failed attempts in 10 minutes is locked out for 10 minutes. A failed attempt is any attempt not ending in "paired": decline, no answer, wrong code, dropped connection or broken protocol.
2. **The messages** (pairing protocol 2, identity `keepsake-pair/2` with a new public key, so devices with the old pairing refuse it cleanly in the handshake). Data connections stay on protocol 1:
   1. requester: `pair-request` with `v`, `deviceId`, `name`;
   2. receiver: the user sees "*name* wants to pair", with the address, and **Accept** or **Decline**. No answer in 120 seconds declines. Then `pair-accepted` (`deviceId`, `name`), or `pair-declined` (`reason`: declined, timed out);
   3. the receiver shows a random code, `secrets.randbelow(10**6)`, until it is typed. The requester's user types it, once, within 120 seconds;
   4. **twenty rounds, one per bit** of the code (10^6 < 2^20). In round *i*, each side commits to bit *i* as `HMAC-SHA256(nonce, "keepsake passkey v1" ‖ tls-unique ‖ requester ID ‖ receiver ID ‖ role ‖ i ‖ bit)`, with every part length-prefixed and a fresh 16-byte nonce:
      - the requester sends `pair-c`, then the receiver sends `pair-c`;
      - the requester sends `pair-n` (its nonce), and the receiver checks the requester's commitment against **its own** bit, in constant time, before sending its own `pair-n`;
      - the requester checks the receiver's commitment the same way;
      - any mismatch sends `error` ("the code was wrong") and ends the attempt on both;
   5. the requester sends `pair-key` (the new 256-bit link key); the receiver stores it and answers `pair-done`. Both show "Paired".
3. **Why a device in the middle fails:**
   - Its two sessions have different `tls-unique` values and the commitments name the sender's role, so it cannot pass one device's commitment to the other.
   - In each round it must commit to a bit on one session before it can learn that bit on the other, because each side reveals only after both commitments are in.
   - So each round is a coin toss for it: about one chance in a million per attempt over 20 rounds, and every attempt costs a request against the limits.
   - The nonces are 128-bit and the code is new each attempt, so there is nothing to try offline.
   - Both devices check every round, so the receiver is protected as well as the requester.
4. **Interface.**
   - **Requester:** Find devices (or Pair by address), then **Pair**, then "Waiting for *name* to accept". Then "*name* accepted. Enter the code shown on it.", with a number pad (digits, Delete, OK) that works with the controller. Then "Checking the code", then Paired, or the plain reason.
   - **Receiver:** a modal "*name* wants to pair" with the address and **Accept** and **Decline**. While a game runs there is only a notification ("answer it in Keepsake, Devices, after your game"), and the request waits on the Devices page. Then the code, large, with Cancel.
   - The desktop interface follows the same steps, with a text field for the code.
5. **Device check "The other handheld can be seen":** any Keepsake device answering Find devices, paired or not (the existing "Finding the other handheld" check needs them paired).

## Consequences

- Both devices need this version to pair. Devices already paired keep their keys and connect as before.
- `docs/protocol.md` is updated, and `tests/test_replication_protocol.py` pins the new identity, key, limits and commitment.
- T129 in `docs/threat-model.md` (T112 described the old pairing).
