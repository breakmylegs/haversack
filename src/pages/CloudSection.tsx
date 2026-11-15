import { DialogButton, Field, Focusable, TextField, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  Backend,
  backendConfig,
  BackendConfig,
  cancelSignin,
  cloudStatus,
  CloudStatus,
  setBackendConfig,
  setSetting,
  Settings,
  signOut,
  SignInCode,
  startSignin,
  testCloud,
} from "../backend";
import { BACKEND_LABELS } from "../format";
import { QrCode } from "./QrCode";

const SIGNIN_EVENT = "keepsake_signin";
const BACKENDS: Backend[] = ["local", "onedrive", "gdrive", "webdav", "s3"];

type FieldSpec = { name: string; label: string; secret?: boolean; bool?: boolean; hint?: string };

const FORMS: Partial<Record<Backend, FieldSpec[]>> = {
  gdrive: [
    { name: "clientId", label: "Google client ID", hint: "From your Google Cloud project. See docs/setup-google.md." },
    { name: "clientSecret", label: "Google client secret", secret: true },
  ],
  webdav: [
    { name: "url", label: "WebDAV folder address", hint: "https:// only, for example https://cloud.example/remote.php/dav/files/me/Keepsake/" },
    { name: "username", label: "User name" },
    { name: "password", label: "Password or app password", secret: true },
  ],
  s3: [
    { name: "endpoint", label: "Endpoint", hint: "https:// only, for example https://s3.eu-west-2.amazonaws.com" },
    { name: "region", label: "Region" },
    { name: "bucket", label: "Bucket" },
    { name: "prefix", label: "Folder inside the bucket" },
    { name: "accessKey", label: "Access key ID" },
    { name: "secretKey", label: "Secret access key", secret: true },
    { name: "pathStyle", label: "Path-style addresses", bool: true, hint: "On for most S3-compatible services." },
  ],
};

const HELP: Record<Backend, string> = {
  local: "Snapshots stay in a test store on this device. Nothing is shared with your other devices.",
  onedrive: "Keepsake can see only its own folder, Apps/Keepsake, in your OneDrive.",
  gdrive: "Keepsake can see only its own hidden app folder in your Google Drive, never your files.",
  webdav: "Your own WebDAV server, such as Nextcloud. It must refuse to overwrite files (Keepsake checks).",
  s3: "Amazon S3 or an S3-compatible service. It must support conditional writes (Keepsake checks).",
};

export function CloudSection({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [status, setStatus] = useState<CloudStatus | null>(null);
  const [view, setView] = useState<Backend>(settings.snapshotStore);
  const [clientId, setClientId] = useState(settings.onedriveClientId);
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [draft, setDraft] = useState<Record<string, string | boolean>>({});
  const [code, setCode] = useState<SignInCode | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => setStatus(await cloudStatus());

  useEffect(() => {
    void refresh();
    const listener = addEventListener<[{ status: string; reason?: string }]>(SIGNIN_EVENT, (result) => {
      setCode(null);
      toaster.toast({
        title: "Keepsake",
        body: result.status === "signed-in" ? "Signed in." : `Sign-in did not complete: ${result.reason}`,
      });
      void refresh();
    });
    return () => removeEventListener(SIGNIN_EVENT, listener);
  }, []);

  useEffect(() => {
    setConfig(null);
    setDraft({});
    if (FORMS[view]) {
      backendConfig(view)
        .then((c) => {
          setConfig(c);
          setDraft(Object.fromEntries(Object.entries(c).filter(([k]) => k !== "configured" && !k.endsWith("Set"))));
        })
        .catch(() => undefined);
    }
  }, [view]);

  const run = async (work: () => Promise<string | null>) => {
    setBusy(true);
    try {
      const message = await work();
      if (message) toaster.toast({ title: "Keepsake", body: message });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  const signedIn = view === "onedrive" ? status?.onedriveSignedIn : view === "gdrive" ? status?.googleSignedIn : config?.configured;

  const use = () =>
    run(async () => {
      if (view !== "local") {
        const checked = await testCloud(view);
        if (!checked.ok) return `${BACKEND_LABELS[view]} did not pass the check: ${checked.error}`;
      }
      onSettings(await setSetting("snapshotStore", view));
      return `Snapshots now go to ${BACKEND_LABELS[view]}.`;
    });

  const locked = settings.readOnly || busy;

  return (
    <div>
      <Field
        label={`Cloud: ${BACKEND_LABELS[settings.snapshotStore]}`}
        description={status?.problem ? `Needs attention: ${status.problem}` : "Choose where snapshots are kept."}
      />
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
        {BACKENDS.map((b) => (
          <DialogButton key={b} style={{ width: "auto", opacity: b === view ? 1 : 0.6 }} onClick={() => setView(b)}>
            {BACKEND_LABELS[b]}
            {b === settings.snapshotStore ? " (in use)" : ""}
          </DialogButton>
        ))}
      </Focusable>
      <Field description={HELP[view]} />

      {view === "onedrive" && (
        <Field label="OneDrive client ID" description="From your app registration. See docs/setup-entra.md." childrenLayout="below">
          <TextField value={clientId} disabled={locked} onChange={(e) => setClientId(e.target.value)} />
          <DialogButton
            style={{ width: "auto", marginTop: 8 }}
            disabled={locked}
            onClick={() => void run(async () => (onSettings(await setSetting("onedriveClientId", clientId)), "Client ID saved."))}
          >
            Save client ID
          </DialogButton>
        </Field>
      )}

      {(FORMS[view] ?? []).map((f) =>
        f.bool ? (
          <ToggleField
            key={f.name}
            label={f.label}
            description={f.hint}
            checked={Boolean(draft[f.name])}
            disabled={locked}
            onChange={(on) => setDraft({ ...draft, [f.name]: on })}
          />
        ) : (
          <Field
            key={f.name}
            label={f.label}
            description={f.secret && config?.[`${f.name}Set`] ? "Saved. Leave empty to keep it." : f.hint}
            childrenLayout="below"
          >
            <TextField
              value={String(draft[f.name] ?? "")}
              bIsPassword={f.secret}
              disabled={locked}
              onChange={(e) => setDraft({ ...draft, [f.name]: e.target.value })}
            />
          </Field>
        ),
      )}
      {FORMS[view] && (
        <DialogButton
          style={{ width: "auto", margin: "8px 0" }}
          disabled={locked}
          onClick={() =>
            void run(async () => {
              setConfig(await setBackendConfig(view, draft));
              return `${BACKEND_LABELS[view]} settings saved.`;
            })
          }
        >
          Save settings
        </DialogButton>
      )}

      {code && (
        <Field
          label="Sign in with your phone"
          description={`Open ${code.verificationUri} or scan the code, then enter the code below. Check the page is on ${
            view === "gdrive" ? "google.com" : "microsoft.com"
          } and asks for access for Keepsake. The code expires in ${Math.round(code.expiresIn / 60)} minutes.`}
          childrenLayout="below"
        >
          <div style={{ fontSize: 40, fontWeight: "bold", letterSpacing: 4, margin: "8px 0" }}>{code.userCode}</div>
          <QrCode text={code.verificationUri} size={180} />
          <DialogButton style={{ width: "auto", marginTop: 8 }} onClick={() => void cancelSignin().then(() => setCode(null))}>
            Cancel sign-in
          </DialogButton>
        </Field>
      )}

      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
        {(view === "onedrive" || view === "gdrive") && !signedIn && !code && (
          <DialogButton
            style={{ width: "auto" }}
            disabled={locked || (view === "onedrive" ? !clientId : !config?.configured)}
            onClick={() => void run(async () => (setCode(await startSignin(view)), null))}
          >
            Sign in
          </DialogButton>
        )}
        {view !== "local" && signedIn && (
          <DialogButton
            style={{ width: "auto" }}
            disabled={locked}
            onClick={() =>
              void run(async () => {
                const r = await testCloud(view);
                return r.ok ? `${BACKEND_LABELS[view]} works.` : `Not working: ${r.error}`;
              })
            }
          >
            Test connection
          </DialogButton>
        )}
        {(view === "onedrive" || view === "gdrive") && signedIn && (
          <DialogButton style={{ width: "auto" }} disabled={locked} onClick={() => void run(async () => (await signOut(view), "Signed out."))}>
            Sign out
          </DialogButton>
        )}
        {view !== settings.snapshotStore && (
          <DialogButton style={{ width: "auto" }} disabled={locked || (view !== "local" && !signedIn)} onClick={() => void use()}>
            Use {BACKEND_LABELS[view]} for snapshots
          </DialogButton>
        )}
      </Focusable>
    </div>
  );
}
