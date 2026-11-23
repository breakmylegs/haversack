import { DialogButton, Dropdown, Field, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  AnimationKind,
  looksResetAnimation,
  looksSend,
  looksSetAnimation,
  looksStatus,
  LooksPart,
  LooksStatus,
  PairedDevice,
  replicationStatus,
} from "../backend";
import { plainError } from "../format";

// Device, Looks (R29 stage 1, ADR-0091): Steam's boot and suspend videos from the user's own WebM files,
// and what CSS Loader and Audio Loader have installed (read only). Nothing takes focus by itself.

const KINDS: { kind: AnimationKind; label: string }[] = [
  { kind: "boot", label: "Boot" },
  { kind: "suspend", label: "Sleep" },
  { kind: "throbber", label: "Sleep from the loading screen" },
];

function current(v: LooksStatus["animations"]["videos"][AnimationKind]): string {
  if (v.who === "haversack") return `Now: ${v.name ?? "your video"}.`;
  if (v.who === "other") return "Now: a video put there by hand or by another tool. Choosing one keeps it, so Use Steam's own brings it back.";
  return "Now: Steam's own.";
}

export function LooksPage() {
  const [status, setStatus] = useState<LooksStatus | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState<AnimationKind | null>(null);

  const load = () =>
    looksStatus()
      .then((s) => {
        setStatus(s);
        setProblem("");
      })
      .catch((err) => setProblem(plainError(err)));
  useEffect(() => {
    void load();
  }, []);

  const act = async (kind: AnimationKind, run: () => Promise<unknown>) => {
    setBusy(kind);
    setProblem("");
    try {
      await run();
      await load();
    } catch (err) {
      setProblem(plainError(err));
    } finally {
      setBusy(null);
    }
  };

  if (!status) return <Field label="Looks" description={problem || "Loading"} />;
  const anims = status.animations;
  return (
    <div>
      <Field
        label="Boot and sleep animations"
        description={
          anims.blockedBy
            ? `${anims.blockedBy} manages the animations on this device, so Haversack only shows them.`
            : "Steam plays these when the device starts and when it goes to sleep. Choose one of your own WebM videos; the change shows the next time the device starts or sleeps."
        }
      />
      {KINDS.map(({ kind, label }) => {
        const v = anims.videos[kind];
        return (
          <Field key={kind} label={label} description={current(v)} childrenLayout="below">
            {!anims.blockedBy && (
              <div style={{ display: "flex", gap: 8 }}>
                <div style={{ flexGrow: 1 }}>
                  <Dropdown
                    disabled={busy !== null || status.choices.length === 0}
                    strDefaultLabel={status.choices.length ? "Choose a video" : "No WebM videos found"}
                    rgOptions={status.choices.map((c) => ({ data: c.id, label: `${c.name} (${c.from})` }))}
                    selectedOption={null}
                    onChange={(o) => void act(kind, () => looksSetAnimation(kind, String(o.data)))}
                  />
                </div>
                {v.who === "haversack" && (
                  <DialogButton style={{ width: "auto" }} disabled={busy !== null} onClick={() => void act(kind, () => looksResetAnimation(kind))}>
                    Use Steam's own
                  </DialogButton>
                )}
              </div>
            )}
          </Field>
        );
      })}
      {status.choices.length === 0 && !anims.blockedBy && (
        <Field description="Put WebM videos in your Videos or Downloads folder (or in Animation Changer's sets), then open this page again." />
      )}
      {!anims.steamFound && <Field description="Steam's config folder was not found on this device." />}
      <Field
        label="Themes"
        description={
          status.plugins.css
            ? status.themes.length
              ? `CSS Loader has ${status.themes.length} theme${status.themes.length === 1 ? "" : "s"}: ${status.themes.map((t) => t.name).join(", ")}.`
              : "CSS Loader is installed, with no themes yet. Add them from its own page."
            : "Themes for Steam's interface come from CSS Loader, in Decky's store. Haversack does not change themes itself."
        }
      />
      <Field
        label="Sounds"
        description={
          status.plugins.audio
            ? status.sounds.length
              ? `Audio Loader has ${status.sounds.length} sound pack${status.sounds.length === 1 ? "" : "s"}: ${status.sounds.map((p) => p.name).join(", ")}.`
              : "Audio Loader is installed, with no sound packs yet."
            : "Sound packs and menu music come from Audio Loader, in Decky's store."
        }
      />
      <SendLooks sendable={status.sendable} />
      {problem && <Field description={problem} />}
    </div>
  );
}

const PARTS: { part: LooksPart; label: string; none: string }[] = [
  { part: "themes", label: "CSS Loader themes", none: "no themes here" },
  { part: "sounds", label: "Audio Loader sound packs", none: "no sound packs here" },
  { part: "animations", label: "The animations chosen above", none: "none chosen here" },
];

// Sending looks to a paired handheld (R29 stage 1b, ADR-0092). The other handheld keeps what it has:
// only themes, packs and videos it lacks are added, and its own screen changes only when someone picks.
function SendLooks({ sendable }: { sendable: LooksStatus["sendable"] }) {
  const [peers, setPeers] = useState<PairedDevice[] | null>(null);
  const [peer, setPeer] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Record<LooksPart, boolean>>({ themes: true, sounds: true, animations: true });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    replicationStatus()
      .then((r) => {
        setPeers(r.peers);
        if (r.peers.length) setPeer(r.peers[0].id);
      })
      .catch(() => setPeers([]));
  }, []);
  if (peers === null) return null;
  if (!peers.length)
    return <Field label="Send to your other handheld" description="Pair your other handheld first (Games and devices, Other devices, with Replication on)." />;
  const target = peers.find((p) => p.id === peer);
  const parts = PARTS.filter((p) => chosen[p.part] && sendable[p.part] > 0).map((p) => p.part);
  const send = async () => {
    if (busy || !peer || !parts.length) return; // never disable a focused button: ignore a second press
    setBusy(true);
    try {
      const r = await looksSend(peer, parts);
      toaster.toast({ title: "Looks", body: `Getting ${r.sending} ready to send.` });
    } catch (err) {
      toaster.toast({ title: "Looks", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Field
        label="Send to your other handheld"
        description="It keeps everything it already has: only what it lacks is added. Videos arrive as choices on its own Looks page."
      />
      {peers.length > 1 && (
        <Field label="To">
          <Dropdown rgOptions={peers.map((p) => ({ data: p.id, label: p.name }))} selectedOption={peer} onChange={(o) => setPeer(String(o.data))} />
        </Field>
      )}
      {PARTS.map(({ part, label, none }) => (
        <ToggleField
          key={part}
          label={label}
          description={sendable[part] ? `${sendable[part]} on this device` : none}
          checked={chosen[part] && sendable[part] > 0}
          disabled={!sendable[part]}
          onChange={(on) => setChosen({ ...chosen, [part]: on })}
        />
      ))}
      <Field>
        <DialogButton onClick={() => void send()}>{busy ? "Working" : `Send to ${target?.name ?? "the other handheld"}`}</DialogButton>
      </Field>
    </>
  );
}
