import { ConfirmModal, DialogButton, Field, Focusable, showModal, TextField, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { plainError } from "../format";
import {
  installerNetBrowse,
  installerNetCancel,
  installerNetDownload,
  installerNetFindSmb,
  installerNetForget,
  installerNetLocations,
  installerNetRemember,
  NetAccess,
  NetDownload,
  NetEntry,
  SmbServer,
  NetLocation,
} from "../backend";

const PROGRESS_EVENT = "keepsake_netinstall_progress";
const GIB = 1024 ** 3;
const LOW_SPACE = 8 * GIB;

type Protocol = "http" | "smb" | "webdav" | "nfs";

function gib(bytes: number): string {
  return `${(bytes / GIB).toFixed(1)} GiB`;
}

// Plain string handling: browsers give smb:// addresses no origin, so URL() is not used.
function splitUrl(url: string): { root: string; path: string } {
  const m = /^([a-z]+:\/\/[^/]+)(\/.*)?$/i.exec(url);
  return { root: m?.[1] ?? url, path: m?.[2] ?? "/" };
}

function hostOf(url: string): string {
  return splitUrl(url).root.replace(/^[a-z]+:\/\//i, "");
}

function parent(url: string): string | null {
  const { root, path } = splitUrl(url);
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return null;
  parts.pop();
  return `${root}/${parts.map((p) => `${p}/`).join("")}`;
}

function folderLabel(url: string): string {
  try {
    return decodeURIComponent(splitUrl(url).path);
  } catch {
    return splitUrl(url).path;
  }
}

const HINTS: Record<Exclude<Protocol, "nfs">, { scheme: string; address: string; password: string }> = {
  http: {
    scheme: "https://",
    address: "For example https://nas.local/games/. Plain http:// works only on your local network, without a password.",
    password: "Sent only over https://, only to this server. Kept on this device.",
  },
  smb: {
    scheme: "smb://",
    address:
      "For example smb://nas.local/Games/, or smb://nas.local/ to list its shares. Only servers on your local network, using SMB 2 or 3.",
    password: "Sent only to this server, protected by the sign-in protocol (NTLMv2). Kept on this device.",
  },
  webdav: {
    scheme: "davs://",
    address:
      "For example davs://cloud.example/remote.php/dav/files/me/Games/ (Nextcloud) or davs://nas.local/dav/. dav:// without the s works only on your local network, without a password.",
    password: "Sent only over davs://, only to this server. Kept on this device.",
  },
};

function protocolOf(url: string): Exclude<Protocol, "nfs"> {
  const scheme = url.toLowerCase().split("://", 1)[0];
  return scheme === "smb" ? "smb" : scheme === "dav" || scheme === "davs" ? "webdav" : "http";
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
  const [servers, setServers] = useState<SmbServer[] | null>(null);

  useEffect(() => {
    installerNetLocations()
      .then(setLocations)
      .catch(() => undefined);
    const listener = addEventListener<[NetDownload]>(PROGRESS_EVENT, (status) => {
      setDownload(status);
      if (status.running) return;
      if (status.job) toaster.toast({ title: "Haversack", body: `${status.name} downloaded. Choose the installer program.` });
      else if (status.cancelled) toaster.toast({ title: "Haversack", body: "Download cancelled. The partial file was deleted." });
      else if (status.redirectHost) askRedirect(status.redirectHost);
      else if (status.error) toaster.toast({ title: "Haversack", body: `Download failed: ${status.error}` });
      onChanged();
    });
    return () => removeEventListener(PROGRESS_EVENT, listener);
  }, []);

  // "nas.local/Games" is taken to mean the chosen protocol's scheme.
  const fullUrl = () => {
    const text = url.trim();
    return text && !text.includes("://") && protocol !== "nfs" ? `${HINTS[protocol].scheme}${text}` : text;
  };

  const access = (extra: string[] = allowHosts): NetAccess =>
    chosen ? { locationId: chosen, allowHosts: extra } : { url: fullUrl(), username, password, allowHosts: extra };

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
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };

  const browse = (target: string, override?: NetAccess) =>
    run(async () => {
      if (!chosen && remember) {
        const before = new Set(locations.map((l) => l.id));
        const saved = await installerNetRemember({ url: override?.url ?? fullUrl(), username, password });
        setLocations(saved);
        const made = saved.find((l) => !before.has(l.id));
        if (made) setChosen(made.id);
        setRemember(false);
      }
      const listing = await installerNetBrowse(override ?? access(), target);
      if (listing.redirectHost) {
        askRedirect(listing.redirectHost);
        return;
      }
      setFolder(listing.url);
      setEntries(listing.entries);
      if (!listing.entries.length) toaster.toast({ title: "Haversack", body: "No folders or ISO files here." });
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
  const form = protocol === "nfs" ? null : HINTS[protocol];
  const mine = locations.filter((l) => protocolOf(l.url) === protocol);

  return (
    <div>
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
        {(
          [
            ["http", "Web server (HTTP or HTTPS)"],
            ["smb", "Windows share (SMB)"],
            ["webdav", "WebDAV"],
            ["nfs", "NFS"],
          ] as [Protocol, string][]
        ).map(([p, label]) => (
          <DialogButton
            key={p}
            style={{ width: "auto", opacity: protocol === p ? 1 : 0.6 }}
            onClick={() => {
              setProtocol(p);
              setChosen(null);
              setFolder(null);
              setEntries([]);
            }}
          >
            {label}
          </DialogButton>
        ))}
      </Focusable>
      {protocol === "nfs" && (
        <Field
          label="NFS needs the share mounted"
          description="Haversack cannot mount NFS without root. Mount it once (for example in Desktop Mode or with an fstab entry) and it appears in the places above."
        />
      )}
      {form && (
        <>
          {stagingFree != null && stagingFree < LOW_SPACE && (
            <Field
              label="Low space for downloads"
              description={`Only ${gib(stagingFree)} is free on this device. An ISO is copied here before it is installed.`}
            />
          )}
          {mine.length > 0 && (
            <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
              {mine.map((l) => (
                <DialogButton key={l.id} style={{ width: "auto", opacity: chosen === l.id ? 1 : 0.6 }} onClick={() => setChosen(l.id)}>
                  {hostOf(l.url)}
                  {l.username ? ` (${l.username})` : ""}
                </DialogButton>
              ))}
              <DialogButton style={{ width: "auto", opacity: chosen ? 0.6 : 1 }} onClick={() => setChosen(null)}>
                New location
              </DialogButton>
            </Focusable>
          )}
          {protocol === "smb" && !location && (
            <>
              <Field
                label="Find shares on my network"
                description="Looks for Windows shares, NAS boxes and Macs sharing folders on your local network. Pick one to list its shares, or type an address below."
                childrenLayout="inline"
              >
                <DialogButton
                  style={{ width: "auto" }}
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      const found = await installerNetFindSmb();
                      setServers(found.servers);
                      if (!found.servers.length) {
                        toaster.toast({ title: "Haversack", body: "No shares answered. Check the server is on, or type its address." });
                      }
                    })
                  }
                >
                  {busy && servers === null ? "Looking" : servers ? "Look again" : "Find shares"}
                </DialogButton>
              </Field>
              {servers && servers.length > 0 && (
                <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
                  {servers.map((s) => (
                    <DialogButton
                      key={s.address}
                      style={{ width: "auto" }}
                      disabled={busy}
                      onClick={() => {
                        setUrl(s.url);
                        void browse(s.url, { url: s.url, username, password, allowHosts });
                      }}
                    >
                      {s.name === s.address ? s.address : `${s.name} (${s.address})`}
                    </DialogButton>
                  ))}
                </Focusable>
              )}
            </>
          )}
          {location ? (
            <Field label={location.url} description={location.username ? `User ${location.username}${location.passwordSet ? ", password saved" : ""}.` : "No sign-in."} childrenLayout="inline">
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => forget(location.id)}>
                Forget
              </DialogButton>
            </Field>
          ) : (
            <>
              <Field label="Address" description={form.address} childrenLayout="below">
                <TextField value={url} disabled={busy} onChange={(e) => setUrl(e.target.value)} />
              </Field>
              <Field label="User name (optional)" childrenLayout="below">
                <TextField value={username} disabled={busy} onChange={(e) => setUsername(e.target.value)} />
              </Field>
              <Field label="Password (optional)" description={form.password} childrenLayout="below">
                <TextField value={password} bIsPassword disabled={busy} onChange={(e) => setPassword(e.target.value)} />
              </Field>
              <ToggleField label="Remember this location" checked={remember} disabled={busy} onChange={setRemember} />
            </>
          )}
          <Field label="SHA-256 checksum (optional)" description="If the server lists one, enter it and Haversack checks the download." childrenLayout="below">
            <TextField value={sha256} disabled={busy} onChange={(e) => setSha256(e.target.value)} />
          </Field>
          <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy || (!location && !url.trim())}
              onClick={() => void browse(location?.url ?? fullUrl())}
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
          {folder && <Field label={folderLabel(folder)} description={`${entries.length} folders and ISO files.`} />}
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
