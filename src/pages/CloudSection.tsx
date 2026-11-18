import { DialogButton, Field, Focusable, Navigation, TextField, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import {
  directSyncNow,
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
  SigninMethod,
  startSignin,
  testCloud,
} from "../backend";
import { BACKEND_LABELS } from "../format";
import { QrCode } from "./QrCode";

const SIGNIN_EVENT = "keepsake_signin";
// OneDrive first: with the built-in client it is pick, sign in on the phone, done (ADR-0032).
const BACKENDS: Backend[] = ["onedrive", "gdrive", "direct", "webdav", "s3", "local"];

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

const GRANT: Partial<Record<Backend, string>> = {
  onedrive: "Microsoft asks you to allow Keepsake access to Apps/Keepsake only.",
  gdrive: "Google asks you to allow Keepsake access to its own app data only.",
};

// Steam's browser re-mounts this page on return and leaves gamepad focus on an invisible
// panel, so the sign-in button is focused again when the page comes back (ADR-0044).
let refocusAfterBrowser = false;

const WHY_PHONE: Record<"onedrive" | "gdrive", string> = {
  onedrive: "Keepsake shows a code to enter on your phone.",
  gdrive: "Google does not allow sign-in inside Steam's browser, so Keepsake shows a code to enter on your phone.",
};

const HELP: Record<Backend, string> = {
  local: "Snapshots stay in a test store on this device. Nothing is shared with your other devices.",
  onedrive: "Sign in with your Microsoft account. Keepsake can read and write only the Apps/Keepsake folder in your OneDrive, never your other files.",
  gdrive: "Sign in with your Google account. Keepsake can use only its own hidden app folder in your Google Drive, never your files.",
  webdav: "Your own WebDAV server, such as Nextcloud. It must refuse to overwrite files (Keepsake checks).",
  s3: "Amazon S3 or an S3-compatible service. It must support conditional writes (Keepsake checks).",
  direct:
    "No account and no cloud: each device keeps its own copy of your saves' history, and paired devices fetch what they lack from each other when they can reach each other. Needs Replication and a paired device. There is no copy away from your devices.",
};

export function CloudSection({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [status, setStatus] = useState<CloudStatus | null>(null);
  // Still on the test store: open on OneDrive, the recommended choice.
  const [view, setView] = useState<Backend>(settings.snapshotStore === "local" ? "onedrive" : settings.snapshotStore);
  const [advanced, setAdvanced] = useState(false);
  const [clientId, setClientId] = useState(settings.onedriveClientId);
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [draft, setDraft] = useState<Record<string, string | boolean>>({});
  const [code, setCode] = useState<SignInCode | null>(null);
  const [browserFailed, setBrowserFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const buttons = useRef<HTMLDivElement>(null);

  const refresh = async () => setStatus(await cloudStatus());

  useEffect(() => {
    if (refocusAfterBrowser) {
      refocusAfterBrowser = false;
      setTimeout(() => buttons.current?.querySelector("button")?.focus(), 100);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const listener = addEventListener<[{ status: string; reason?: string }]>(SIGNIN_EVENT, (result) => {
      setCode((shown) => {
        if (shown?.method === "browser" && result.status !== "signed-in" && result.reason !== "cancelled") setBrowserFailed(true);
        return null;
      });
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
    setAdvanced(false);
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

  const signedIn =
    view === "onedrive"
      ? status?.onedriveSignedIn
      : view === "gdrive"
        ? status?.googleSignedIn
        : view === "direct"
          ? status?.directReady
          : config?.configured;

  const use = () =>
    run(async () => {
      if (view !== "local" && view !== "direct") {
        const checked = await testCloud(view);
        if (!checked.ok) return `${BACKEND_LABELS[view]} did not pass the check: ${checked.error}`;
      }
      onSettings(await setSetting("snapshotStore", view));
      return `Snapshots now go to ${BACKEND_LABELS[view]}.`;
    });

  const locked = settings.readOnly || busy;
  const oauth = view === "onedrive" || view === "gdrive";
  const builtIn = oauth && Boolean(status?.builtInClient?.[view]);
  const own = oauth && Boolean(status?.ownClient?.[view]);
  // With a built-in client the client ID fields are an Advanced option, shown while one is saved.
  const showOwn = !builtIn || advanced || own;
  const form = view === "gdrive" && !showOwn ? [] : (FORMS[view] ?? []);
  const canSignIn = view === "onedrive" ? builtIn || Boolean(settings.onedriveClientId) : builtIn || Boolean(config?.configured);
  const provider = view === "gdrive" ? "gdrive" : "onedrive";
  const preferred: SigninMethod = settings.gamingModeSignin?.[provider] ?? (provider === "gdrive" ? "phone" : "browser");
  const available = status?.methods?.[provider];
  // The preferred method if it has a client, otherwise the other one (ADR-0044).
  const method: SigninMethod = !available || available[preferred] ? preferred : preferred === "browser" ? "phone" : "browser";

  const signIn = (how: SigninMethod) =>
    run(async () => {
      setBrowserFailed(false);
      const shown = await startSignin(provider, how);
      setCode(shown);
      if (shown.method === "browser") {
        refocusAfterBrowser = true;
        Navigation.NavigateToExternalWeb(shown.authUrl);
      }
      return null;
    });

  const setPreferred = (browser: boolean) =>
    void run(async () => {
      const next = { ...(settings.gamingModeSignin ?? { onedrive: "browser", gdrive: "phone" }), [provider]: browser ? "browser" : "phone" };
      onSettings(await setSetting("gamingModeSignin", next));
      return null;
    });

  const useOwnClient = (on: boolean) => {
    setAdvanced(on);
    if (on || !own) return;
    // Back to Keepsake's built-in client. A saved sign-in keeps refreshing with the client it was made with.
    void run(async () => {
      if (view === "onedrive") {
        onSettings(await setSetting("onedriveClientId", ""));
        setClientId("");
      } else {
        setConfig(await setBackendConfig("gdrive", { clientId: "", clientSecret: "" }));
        setDraft({ clientId: "" });
      }
      return "Your own client ID is cleared. Keepsake's built-in sign-in is used from the next sign-in.";
    });
  };

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

      {builtIn && (
        <ToggleField
          label="Advanced: use my own client ID"
          description={
            own
              ? "Your own app registration is in use. Turn this off to use Keepsake's built-in sign-in."
              : "Only if you have your own app registration. Keepsake's built-in sign-in needs none."
          }
          checked={advanced || own}
          disabled={locked}
          onChange={useOwnClient}
        />
      )}

      {view === "onedrive" && showOwn && (
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

      {form.map((f) =>
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
      {form.length > 0 && (
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

      {oauth && !signedIn && available?.browser && available?.phone && (
        <ToggleField
          label="Sign in with this device's browser"
          description={method === "browser" ? "Keepsake opens the sign-in page in Steam's browser." : WHY_PHONE[provider]}
          checked={method === "browser"}
          disabled={locked || Boolean(code)}
          onChange={setPreferred}
        />
      )}

      {code?.method === "browser" && (
        <Field
          label="Finish signing in in the browser"
          description={`Sign in on the ${view === "gdrive" ? "Google" : "Microsoft"} page and allow access for Keepsake. ${
            GRANT[view] ?? ""
          } Then come back here. This waits ${Math.round(code.expiresIn / 60)} minutes.`}
          childrenLayout="below"
        >
          <Focusable style={{ display: "flex", gap: 8 }}>
            <DialogButton style={{ width: "auto" }} onClick={() => Navigation.NavigateToExternalWeb(code.authUrl)}>
              Open the sign-in page again
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => void cancelSignin().then(() => setCode(null))}>
              Cancel sign-in
            </DialogButton>
          </Focusable>
        </Field>
      )}

      {browserFailed && !code && available?.phone && (
        <Field label="The browser sign-in did not finish" description="You can sign in on your phone with a code instead.">
          <DialogButton style={{ width: "auto" }} disabled={locked} onClick={() => void signIn("phone")}>
            Use your phone instead
          </DialogButton>
        </Field>
      )}

      {code && code.method !== "browser" && (
        <Field
          label="Sign in with your phone"
          description={`Open ${code.verificationUri} or scan the code, then enter the code below. Check the page is on ${
            view === "gdrive" ? "google.com" : "microsoft.com"
          } and asks for access for Keepsake. ${GRANT[view] ?? ""} The code expires in ${Math.round(code.expiresIn / 60)} minutes.`}
          childrenLayout="below"
        >
          <div style={{ fontSize: 40, fontWeight: "bold", letterSpacing: 4, margin: "8px 0" }}>{code.userCode}</div>
          <QrCode text={code.verificationUri} size={180} />
          <DialogButton style={{ width: "auto", marginTop: 8 }} onClick={() => void cancelSignin().then(() => setCode(null))}>
            Cancel sign-in
          </DialogButton>
        </Field>
      )}

      <Focusable ref={buttons} style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
        {oauth && !signedIn && !code && (
          <DialogButton style={{ width: "auto" }} disabled={locked || !canSignIn} onClick={() => void signIn(method)}>
            Sign in with {view === "gdrive" ? "Google" : "OneDrive"}
          </DialogButton>
        )}
        {view === "direct" && settings.snapshotStore === "direct" && (
          <DialogButton
            style={{ width: "auto" }}
            disabled={locked}
            onClick={() =>
              void run(async () => {
                const r = await directSyncNow();
                const away = r.unreachable.length ? ` Not reachable: ${r.unreachable.join(", ")}.` : "";
                return `Fetched ${r.copied} new save objects from ${r.peers} device(s).${away}`;
              })
            }
          >
            Sync now
          </DialogButton>
        )}
        {view !== "local" && view !== "direct" && signedIn && (
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
