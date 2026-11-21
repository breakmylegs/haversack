import { ConfirmModal, DialogButton, Field, Focusable, showModal, TextField } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  installerAddCdDrive,
  installerArtworkApply,
  installerArtworkSearch,
  installerCancel,
  installerCreateShortcut,
  installerFinishedInstalling,
  installerHandoff,
  installerRemoveShortcut,
  installerRetarget,
  installerStart,
  installerSwapDisc,
  installerStatus,
  InstallerStatus,
  InstallJob,
  saveSteamGridDbKey,
  setSetting,
  updateGameConfig,
} from "../backend";
import { openSection } from "../routes";
import { NetworkSource } from "./NetworkSource";
import { plainError } from "../format";

// FileSelectionType in @decky/api is a type-only const enum: FILE is 0, FOLDER is 1.
const FILE = 0 as unknown as Parameters<typeof openFilePicker>[0];
const FOLDER = 1 as unknown as Parameters<typeof openFilePicker>[0];

const STEP_TEXT: Record<InstallJob["state"], string> = {
  queued: "Waiting in the queue. It starts by itself when the install before it ends.",
  "choose-installer": "Choose the installer program.",
  "creating-shortcut": "Creating the installer shortcut in Steam.",
  "run-installer": "Open your library, start the installer shortcut and install. Then quit it and come back here.",
  "choose-game": "Choose the game's program. The same shortcut will start the game and keep its Proton prefix.",
  retargeting: "Pointing the shortcut at the game.",
  done: "Done. The shortcut now starts the game.",
  failed: "Stopped.",
  cancelled: "Cancelled.",
};

function sizeText(bytes: number): string {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(0)} MB` : `${(bytes / 1024).toFixed(0)} KB`;
}

function lastPart(path: string): string {
  return path.split("/").filter(Boolean).pop() ?? path;
}

export function InstallerPage() {
  const [status, setStatus] = useState<InstallerStatus | null>(null);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [network, setNetwork] = useState(false);
  const [matches, setMatches] = useState<Record<number, { id: number; name: string; verified: boolean }[]>>({});

  const refresh = () =>
    installerStatus()
      .then(setStatus)
      .catch(() => undefined);

  useEffect(() => {
    void refresh();
  }, []);

  const act = async (work: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      await work();
      if (done) toaster.toast({ title: "Keepsake", body: done });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  const from = start ?? status?.sources.home ?? "/home";

  const pick = async (kind: "iso" | "folder") => {
    try {
      const picked =
        kind === "iso"
          ? await openFilePicker(FILE, from, true, true, undefined, ["iso"])
          : await openFilePicker(FOLDER, from, false, true);
      const busyInstall = (status?.jobs ?? []).some((j) =>
        ["choose-installer", "creating-shortcut", "run-installer", "choose-game", "retargeting"].includes(j.state),
      );
      // While another install is under way, a new one joins the queue (ADR-0053).
      await act(
        () => installerStart(picked.realpath || picked.path, title, busyInstall),
        busyInstall ? "Added to the queue. It starts when the current install ends." : "Ready. Choose the installer program.",
      );
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Nothing chosen: ${plainError(err)}` });
    }
  };

  const chooseLibrary = async () => {
    try {
      const picked = await openFilePicker(FOLDER, status?.libraryRoot ?? "/home", false, true);
      await act(() => setSetting("libraryRoot", picked.realpath || picked.path), "Games will be installed there.");
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Nothing chosen: ${plainError(err)}` });
    }
  };

  const syncSaves = (job: InstallJob) =>
    act(async () => {
      const { key } = await installerHandoff(job.id);
      await updateGameConfig(key, { enabled: true });
      openSection("saves", "games");
    }, `Save sync switched on for ${job.title}. Check its match in Games.`);

  const findArtwork = (job: InstallJob) =>
    act(async () => {
      const found = await installerArtworkSearch(job.id);
      setMatches((m) => ({ ...m, [job.id]: found }));
      if (!found.length) toaster.toast({ title: "Keepsake", body: "SteamGridDB has no game by that name." });
    });

  if (status && !status.running) {
    return <Field label="Installer is off" description="Switch it on in Settings, Modules." />;
  }

  const places = [
    ...(status ? [{ label: "Home", path: status.sources.home }] : []),
    ...(status?.sources.removable ?? []).map((p) => ({ label: lastPart(p), path: p })),
    ...(status?.sources.network ?? []).map((p) => ({ label: `Network: ${lastPart(p)}`, path: p })),
  ];

  return (
    <div>
      <Field
        label="Install a game"
        description={`Installs into its own Steam shortcut and Proton prefix. Games go to ${status?.libraryRoot ?? "~/Games"}. An installer is a Windows program run in a Proton prefix, which is not a sandbox: only install software you trust.`}
        childrenLayout="inline"
      >
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void chooseLibrary()}>
          Change folder
        </DialogButton>
      </Field>
      <Field label="Game title" description="Used for the shortcut and the install folder." childrenLayout="below">
        <TextField value={title} disabled={busy} onChange={(e) => setTitle(e.target.value)} />
        {places.length > 1 && (
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            {places.map((p) => (
              <DialogButton
                key={p.path}
                style={{ width: "auto", opacity: from === p.path ? 1 : 0.6 }}
                disabled={busy}
                onClick={() => setStart(p.path)}
              >
                {p.label}
              </DialogButton>
            ))}
          </Focusable>
        )}
        <div style={{ fontSize: 12, marginTop: 4 }}>
          Browse from {from}. Network shares appear here once they are mounted, for example from Desktop Mode, or use From a network location.
        </div>
        <Focusable style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <DialogButton style={{ width: "auto" }} disabled={busy || !title.trim() || !status?.udisks} onClick={() => void pick("iso")}>
            From an ISO file
          </DialogButton>
          <DialogButton style={{ width: "auto" }} disabled={busy || !title.trim()} onClick={() => void pick("folder")}>
            From a folder
          </DialogButton>
          <DialogButton style={{ width: "auto", opacity: network ? 1 : 0.8 }} disabled={busy || !status?.udisks} onClick={() => setNetwork(!network)}>
            From a network location
          </DialogButton>
        </Focusable>
      </Field>
      {network && status && (
        <NetworkSource title={title} stagingFree={status.stagingFree} initial={status.download} onChanged={() => void refresh()} />
      )}
      {status && !status.udisks && <Field label="ISO files are not available" description="udisksctl is missing on this system. Copy the disc to a folder instead." />}
      {status?.artwork && !status.artworkKey && (
        <Field label="SteamGridDB API key" description="Optional. Lets Keepsake add artwork to games you install. Get a key from your SteamGridDB profile, API." childrenLayout="below">
          <TextField value={apiKey} disabled={busy} bIsPassword onChange={(e) => setApiKey(e.target.value)} />
          <DialogButton
            style={{ width: "auto", marginTop: 8 }}
            disabled={busy || !apiKey.trim()}
            onClick={() => void act(() => saveSteamGridDbKey("steamgriddb", { apiKey: apiKey.trim() }).then(() => setApiKey("")), "Key saved.")}
          >
            Save key
          </DialogButton>
        </Field>
      )}

      {(status?.jobs ?? []).map((job) => (
        <Field key={job.id} label={`${job.title} (${job.state === "queued" ? "queued" : job.kind === "iso" ? "ISO" : "folder"})`} description={`${STEP_TEXT[job.state]}${job.error ? ` ${job.error}` : ""}`} childrenLayout="below">
          {job.state === "choose-installer" && (
            <>
              <div style={{ fontSize: 12, marginBottom: 4 }}>When the installer asks where to install, enter: {job.windowsTarget}</div>
              {job.installers.length === 0 && <div style={{ fontSize: 12 }}>No installer program found.</div>}
              {job.installers.slice(0, 6).map((exe) => (
                <DialogButton
                  key={exe}
                  style={{ width: "auto", marginBottom: 4 }}
                  disabled={busy}
                  onClick={() => void act(() => installerCreateShortcut(job.id, exe), `Adding "Install: ${job.title}" to Steam.`)}
                >
                  Use {exe}
                </DialogButton>
              ))}
            </>
          )}
          {job.state === "run-installer" && (
            <>
              <div style={{ fontSize: 12, marginBottom: 4 }}>Install to: {job.windowsTarget}</div>
              {job.kind === "iso" &&
                (job.cdDrive ? (
                  <>
                    <div style={{ fontSize: 12, marginBottom: 4 }}>The disc is drive {job.cdDrive.letter.toUpperCase()}: in the installer.</div>
                    {(job.otherDiscs ?? []).map((disc) => (
                      <DialogButton
                        key={disc}
                        style={{ width: "auto", marginBottom: 4 }}
                        disabled={busy}
                        onClick={() =>
                          void act(() => installerSwapDisc(job.id, disc), `${disc} is now in the drive. Continue in the installer.`)
                        }
                      >
                        Swap to {disc}
                      </DialogButton>
                    ))}
                  </>
                ) : (
                  <DialogButton
                    style={{ width: "auto", marginBottom: 4 }}
                    disabled={busy}
                    onClick={() => void act(() => installerAddCdDrive(job.id), "The disc is now a CD drive. Start the installer shortcut again.")}
                  >
                    Installer wants a disc drive
                  </DialogButton>
                ))}
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => installerFinishedInstalling(job.id))}>
                I have finished installing
              </DialogButton>
            </>
          )}
          {job.state === "choose-game" && (job.runtimes ?? []).length > 0 && (
            <div style={{ fontSize: 12, marginBottom: 4 }}>
              The game also ships {Array.from(new Set((job.runtimes ?? []).map((r) => r.runtime))).join(", ")}. Proton already
              provides most of these. Only if the game will not start, run the one it needs once, through this shortcut:{" "}
              {(job.runtimes ?? []).slice(0, 3).map((r) => lastPart(r.path)).join(", ")}.
            </div>
          )}
          {job.state === "choose-game" &&
            (job.candidates ?? []).map((c) => (
              <DialogButton
                key={c.path}
                style={{ width: "auto", marginBottom: 4 }}
                disabled={busy}
                onClick={() =>
                  showModal(
                    <ConfirmModal
                      strTitle={`Start ${job.title} with this program?`}
                      strDescription={`${c.path} (${sizeText(c.size)}). The installer shortcut becomes the game's shortcut and keeps its prefix.`}
                      strOKButtonText="Use it"
                      strCancelButtonText="Cancel"
                      onOK={() => void act(() => installerRetarget(job.id, c.path), "Pointing the shortcut at the game.")}
                    />,
                  )
                }
              >
                {c.path.split("/").slice(-2).join("/")} ({sizeText(c.size)})
              </DialogButton>
            ))}
          {job.state === "done" && (
            <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void syncSaves(job)}>
                Sync this game's saves
              </DialogButton>
              {status?.artwork && status.artworkKey && !job.artwork && (
                <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void findArtwork(job)}>
                  Add artwork from SteamGridDB
                </DialogButton>
              )}
            </Focusable>
          )}
          {job.state === "done" &&
            (matches[job.id] ?? []).map((m) => (
              <DialogButton
                key={m.id}
                style={{ width: "auto", marginTop: 4 }}
                disabled={busy}
                onClick={() => void act(() => installerArtworkApply(job.id, m.id).then(() => setMatches((x) => ({ ...x, [job.id]: [] }))), "Adding artwork.")}
              >
                Use artwork for {m.name}
                {m.verified ? " (verified)" : ""}
              </DialogButton>
            ))}
          {(job.state === "failed" || job.state === "cancelled") && job.appid && !job.gameExe && !job.shortcutRemoved && (
            <DialogButton
              style={{ width: "auto", marginTop: 4 }}
              disabled={busy}
              onClick={() => void act(() => installerRemoveShortcut(job.id), `Removing "Install: ${job.title}" from Steam.`)}
            >
              Remove the installer shortcut
            </DialogButton>
          )}
          {["queued", "choose-installer", "creating-shortcut", "run-installer", "choose-game"].includes(job.state) && (
            <DialogButton style={{ width: "auto", marginTop: 4 }} disabled={busy} onClick={() => void act(() => installerCancel(job.id), "Install cancelled.")}>
              Cancel
            </DialogButton>
          )}
        </Field>
      ))}
    </div>
  );
}
