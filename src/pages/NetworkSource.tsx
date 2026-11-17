import { ConfirmModal, DialogButton, Field, Focusable, showModal, TextField, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  installerNetBrowse,
  installerNetCancel,
  installerNetDownload,
  installerNetForget,
  installerNetLocations,
  installerNetRemember,
  NetAccess,
  NetDownload,
  NetEntry,
  NetLocation,
} from "../backend";

const PROGRESS_EVENT = "keepsake_netinstall_progress";
const GIB = 1024 ** 3;
const LOW_SPACE = 8 * GIB;

type Protocol = "http" | "smb" | "nfs";

function gib(bytes: number): string {
  return `${(bytes / GIB).toFixed(1)} GiB`;
}

function parent(url: string): string | null {
  const u = new URL(url);
  const parts = u.pathname.split("/").filter(Boolean);
  if (!parts.length) return null;
  parts.pop();
  return `${u.origin}/${parts.map((p) => `${p}/`).join("")}`;
}

/** Install → "From a network location": browse an HTTP or HTTPS server and download one ISO (ADR-0033). */
export function NetworkSource({
  title,
  stagingFree,
  initial,
  onChanged,
}: {
  title: string;
  stagingFree: number | null;
  initial: NetDownload;
  onChanged: () => void;
}) {
  const [protocol, setProtocol] = useState<Protocol>("http");
  const [locations, setLocations] = useState<NetLocation[]>([]);
  const [chosen, setChosen] = useState<string | null>(null); // a remembered location's id, or null for a new one
  const [url, setUrl] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [folder, setFolder] = useState<string | null>(null);
  const [entries, setEntries] = useState<NetEntry[]>([]);
  const [sha256, setSha256] = useState("");
  const [allowHosts, setAllowHosts] = useState<string[]>([]);
  const [download, setDownload] = useState<NetDownload>(initial);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    installerNetLocations()
      .then(setLocations)
      .catch(() => undefined);
    const listener = addEventListener<[NetDownload]>(PROGRESS_EVENT, (status) => {
      setDownload(status);
      if (status.running) return;
      if (status.job) toaster.toast({ title: "Keepsake", body: `${status.name} downloaded. Choose the installer program.` });
      else if (status.cancelled) toaster.toast({ title: "Keepsake", body: "Download cancelled. The partial file was deleted." });
      else if (status.redirectHost) askRedirect(status.redirectHost);
      else if (status.error) toaster.toast({ title: "Keepsake", body: `Download failed: ${status.error}` });
      onChanged();
    });
    return () => removeEventListener(PROGRESS_EVENT, listener);
  }, []);

  const access = (extra: string[] = allowHosts): NetAccess =>
    chosen ? { locationId: chosen, allowHosts: extra } : { url, username, password, allowHosts: extra };

  const askRedirect = (host: string) =>
    showModal(
      <ConfirmModal
        strTitle="The server sent you to another host"
        strDescription={`It points to ${host}. Allow ${host} for this download? Your user name and password are never sent to it. Then choose it again.`}
        strOKButtonText="Allow it"
        strCancelButtonText="Cancel"
        onOK={() => setAllowHosts((h) => [...new Set([...h, host])])}
      />,
    );

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    try {
      await work();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const browse = (target: string) =>
    run(async () => {
      if (!chosen && remember) {
        const saved = await installerNetRemember({ url, username, password });
        setLocations(saved);
        const made = saved.find((l) => l.url === url.trim() && l.username === username.trim());
        if (made) setChosen(made.id);
        setRemember(false);
      }
      const listing = await installerNetBrowse(access(), target);
      if (listing.redirectHost) {
        askRedirect(listing.redirectHost);
        return;
      }
      setFolder(listing.url);
      setEntries(listing.entries);
      if (!listing.entries.length) toaster.toast({ title: "Keepsake", body: "No folders or ISO files here." });
    });

  const start = (entry: NetEntry) =>
    showModal(
      <ConfirmModal
        strTitle={`Download ${entry.name}?`}
        strDescription={`It is copied to this device first (${stagingFree != null ? `${gib(stagingFree)} free` : "free space unknown"}), then installed as "${title}" like any ISO. The copy is deleted when the install ends.${sha256.trim() ? " It must match the SHA-256 you entered." : ""}`}
        strOKButtonText="Download"
        strCancelButtonText="Cancel"
        onOK={() =>
          void run(async () => {
            setDownload(await installerNetDownload(access(), entry.url, title, sha256.trim()));
          })
        }
      />,
    );

  const forget = (id: string) =>
    run(async () => {
      setLocations(await installerNetForget(id));
      setChosen(null);
      setFolder(null);
      setEntries([]);
    });

  if (download.running) {
    const total = download.total ?? 0;
    return (
      <Field
        label={`Downloading ${download.name}`}
        description={`${gib(download.done ?? 0)}${total ? ` of ${gib(total)}` : ""}, ${((download.rate ?? 0) / 1024 / 1024).toFixed(1)} MB/s. The install starts when it finishes.`}
        childrenLayout="inline"
      >
        <DialogButton style={{ width: "auto" }} onClick={() => void installerNetCancel().then(setDownload)}>
          Cancel download
        </DialogButton>
      </Field>
    );
  }

  const location = locations.find((l) => l.id === chosen);

  return (
    <div>
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
        {(
          [
            ["http", "Web server (HTTP or HTTPS)"],
            ["smb", "Windows share (SMB)"],
            ["nfs", "NFS"],
          ] as [Protocol, string][]
        ).map(([p, label]) => (
          <DialogButton key={p} style={{ width: "auto", opacity: protocol === p ? 1 : 0.6 }} onClick={() => setProtocol(p)}>
            {label}
          </DialogButton>
        ))}
      </Focusable>
      {protocol === "smb" && (
        <Field
          label="Windows shares are coming"
          description="Until then, open the share once in Desktop Mode (Dolphin); it then appears in the places above. Or turn on your NAS's web server and choose Web server."
        />
      )}
      {protocol === "nfs" && (
        <Field
          label="NFS needs the share mounted"
          description="Keepsake cannot mount NFS without root. Mount it once (for example in Desktop Mode or with an fstab entry) and it appears in the places above."
        />
      )}
      {protocol === "http" && (
        <>
          {stagingFree != null && stagingFree < LOW_SPACE && (
            <Field
              label="Low space for downloads"
              description={`Only ${gib(stagingFree)} is free on this device. An ISO is copied here before it is installed.`}
            />
          )}
          {locations.length > 0 && (
            <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
              {locations.map((l) => (
                <DialogButton key={l.id} style={{ width: "auto", opacity: chosen === l.id ? 1 : 0.6 }} onClick={() => setChosen(l.id)}>
                  {new URL(l.url).host}
                  {l.username ? ` (${l.username})` : ""}
                </DialogButton>
              ))}
              <DialogButton style={{ width: "auto", opacity: chosen ? 0.6 : 1 }} onClick={() => setChosen(null)}>
                New location
              </DialogButton>
            </Focusable>
          )}
          {location ? (
            <Field label={location.url} description={location.username ? `User ${location.username}${location.passwordSet ? ", password saved" : ""}.` : "No sign-in."} childrenLayout="inline">
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => forget(location.id)}>
                Forget
              </DialogButton>
            </Field>
          ) : (
            <>
              <Field label="Address" description="For example https://nas.local/games/. Plain http:// works only on your local network, without a password." childrenLayout="below">
                <TextField value={url} disabled={busy} onChange={(e) => setUrl(e.target.value)} />
              </Field>
              <Field label="User name (optional)" childrenLayout="below">
                <TextField value={username} disabled={busy} onChange={(e) => setUsername(e.target.value)} />
              </Field>
              <Field label="Password (optional)" description="Sent only over https://, only to this server. Kept on this device." childrenLayout="below">
                <TextField value={password} bIsPassword disabled={busy} onChange={(e) => setPassword(e.target.value)} />
              </Field>
              <ToggleField label="Remember this location" checked={remember} disabled={busy} onChange={setRemember} />
            </>
          )}
          <Field label="SHA-256 checksum (optional)" description="If the server lists one, enter it and Keepsake checks the download." childrenLayout="below">
            <TextField value={sha256} disabled={busy} onChange={(e) => setSha256(e.target.value)} />
          </Field>
          <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy || (!location && !url.trim())}
              onClick={() => void browse(location?.url ?? url.trim())}
            >
              {busy ? "Working" : "Browse"}
            </DialogButton>
            {folder && parent(folder) && (
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void browse(parent(folder) as string)}>
                Up one folder
              </DialogButton>
            )}
          </Focusable>
          {download.error && !download.running && <Field label="Last download" description={download.error} />}
          {folder && <Field label={decodeURIComponent(new URL(folder).pathname)} description={`${entries.length} folders and ISO files.`} />}
          {entries.map((e) => (
            <DialogButton
              key={e.url}
              style={{ width: "auto", marginBottom: 4 }}
              disabled={busy || (e.kind === "iso" && !title.trim())}
              onClick={() => (e.kind === "folder" ? void browse(e.url) : start(e))}
            >
              {e.kind === "folder" ? `${e.name}/` : `Install ${e.name}`}
            </DialogButton>
          ))}
          {entries.some((e) => e.kind === "iso") && !title.trim() && <Field description="Enter the game title above first." />}
        </>
      )}
    </div>
  );
}
