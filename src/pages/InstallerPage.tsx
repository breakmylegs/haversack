import { ConfirmModal, DialogButton, Field, Focusable, showModal, TextField } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  installerCancel,
  installerCreateShortcut,
  installerFinishedInstalling,
  installerRetarget,
  installerStart,
  installerStatus,
  InstallJob,
  setSetting,
} from "../backend";

// FileSelectionType in @decky/api is a type-only const enum: FILE is 0, FOLDER is 1.
const FILE = 0 as unknown as Parameters<typeof openFilePicker>[0];
const FOLDER = 1 as unknown as Parameters<typeof openFilePicker>[0];

const STEP_TEXT: Record<InstallJob["state"], string> = {
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

export function InstallerPage() {
  const [status, setStatus] = useState<{ running: boolean; udisks: boolean; libraryRoot: string; jobs: InstallJob[] } | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

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
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  const pick = async (kind: "iso" | "folder") => {
    try {
      const picked =
        kind === "iso"
          ? await openFilePicker(FILE, "/home", true, true, undefined, ["iso"])
          : await openFilePicker(FOLDER, "/home", false, true);
      await act(() => installerStart(picked.realpath || picked.path, title), "Ready. Choose the installer program.");
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Nothing chosen: ${err}` });
    }
  };

  const chooseLibrary = async () => {
    try {
      const picked = await openFilePicker(FOLDER, status?.libraryRoot ?? "/home", false, true);
      await act(() => setSetting("libraryRoot", picked.realpath || picked.path), "Games will be installed there.");
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Nothing chosen: ${err}` });
    }
  };

  if (status && !status.running) {
    return <Field label="Installer is off" description="Switch it on in Settings, Modules." />;
  }

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
        <Focusable style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <DialogButton style={{ width: "auto" }} disabled={busy || !title.trim() || !status?.udisks} onClick={() => void pick("iso")}>
            From an ISO file
          </DialogButton>
          <DialogButton style={{ width: "auto" }} disabled={busy || !title.trim()} onClick={() => void pick("folder")}>
            From a folder
          </DialogButton>
        </Focusable>
      </Field>
      {status && !status.udisks && <Field label="ISO files are not available" description="udisksctl is missing on this system. Copy the disc to a folder instead." />}

      {(status?.jobs ?? []).map((job) => (
        <Field key={job.id} label={`${job.title} (${job.kind === "iso" ? "ISO" : "folder"})`} description={`${STEP_TEXT[job.state]}${job.error ? ` ${job.error}` : ""}`} childrenLayout="below">
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
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => installerFinishedInstalling(job.id))}>
                I have finished installing
              </DialogButton>
            </>
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
          {["choose-installer", "creating-shortcut", "run-installer", "choose-game"].includes(job.state) && (
            <DialogButton style={{ width: "auto", marginTop: 4 }} disabled={busy} onClick={() => void act(() => installerCancel(job.id), "Install cancelled.")}>
              Cancel
            </DialogButton>
          )}
        </Field>
      ))}
    </div>
  );
}
