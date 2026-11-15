import { DialogButton, Field, Focusable, TextField, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  cancelSignin,
  cloudStatus,
  CloudStatus,
  setSetting,
  Settings,
  signOut,
  SignInCode,
  startSignin,
  testCloud,
} from "../backend";
import { QrCode } from "./QrCode";

const SIGNIN_EVENT = "keepsake_signin";

export function CloudSection({ settings, onSettings }: { settings: Settings; onSettings: (s: Settings) => void }) {
  const [status, setStatus] = useState<CloudStatus | null>(null);
  const [clientId, setClientId] = useState(settings.onedriveClientId);
  const [code, setCode] = useState<SignInCode | null>(null);

  const refresh = async () => setStatus(await cloudStatus());

  useEffect(() => {
    void refresh();
    const listener = addEventListener<[{ status: string; reason?: string }]>(SIGNIN_EVENT, (result) => {
      setCode(null);
      toaster.toast({
        title: "Keepsake",
        body: result.status === "signed-in" ? "Signed in to OneDrive." : `Sign-in did not complete: ${result.reason}`,
      });
      void refresh();
    });
    return () => removeEventListener(SIGNIN_EVENT, listener);
  }, []);

  const save = async (key: string, value: unknown, done: string) => {
    try {
      onSettings(await setSetting(key, value));
      toaster.toast({ title: "Keepsake", body: done });
      await refresh();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Not saved: ${err}` });
    }
  };

  const begin = async () => {
    try {
      setCode(await startSignin());
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not start sign-in: ${err}` });
    }
  };

  return (
    <div>
      <Field label="Cloud: OneDrive" description={statusText(status)} />
      <Field
        label="OneDrive client ID"
        description="From your app registration. See docs/setup-entra.md in the Keepsake repository."
        childrenLayout="below"
      >
        <TextField value={clientId} disabled={settings.readOnly} onChange={(e) => setClientId(e.target.value)} />
        <DialogButton
          style={{ width: "auto", marginTop: 8 }}
          disabled={settings.readOnly}
          onClick={() => void save("onedriveClientId", clientId, "Client ID saved.")}
        >
          Save client ID
        </DialogButton>
      </Field>

      {code && (
        <Field
          label="Sign in with your phone"
          description={`Open ${code.verificationUri} or scan the code, then enter the code below. Check the page is on microsoft.com and asks for access for Keepsake. The code expires in ${Math.round(code.expiresIn / 60)} minutes.`}
          childrenLayout="below"
        >
          <div style={{ fontSize: 40, fontWeight: "bold", letterSpacing: 4, margin: "8px 0" }}>{code.userCode}</div>
          <QrCode text={code.verificationUri} size={180} />
          <DialogButton
            style={{ width: "auto", marginTop: 8 }}
            onClick={() => void cancelSignin().then(() => setCode(null))}
          >
            Cancel sign-in
          </DialogButton>
        </Field>
      )}

      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
        {!status?.signedIn && !code && (
          <DialogButton style={{ width: "auto" }} disabled={!status?.clientIdSet} onClick={() => void begin()}>
            Sign in
          </DialogButton>
        )}
        {status?.signedIn && (
          <>
            <DialogButton
              style={{ width: "auto" }}
              onClick={() =>
                void testCloud().then((r) =>
                  toaster.toast({
                    title: "Keepsake",
                    body: r.ok ? `OneDrive app folder "${r.folder}" is reachable.` : `Not reachable: ${r.error}`,
                  }),
                )
              }
            >
              Test connection
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => void signOut().then(refresh)}>
              Sign out
            </DialogButton>
          </>
        )}
      </Focusable>

      <ToggleField
        label="Use OneDrive for snapshots"
        description="Off: the local test store on this device. On: your OneDrive app folder."
        checked={settings.snapshotStore === "onedrive"}
        disabled={settings.readOnly || !status?.signedIn}
        onChange={(on) =>
          void save("snapshotStore", on ? "onedrive" : "local", on ? "Snapshots go to OneDrive." : "Snapshots stay local.")
        }
      />
    </div>
  );
}

function statusText(status: CloudStatus | null): string {
  if (!status) return "Checking";
  if (status.problem === "sign-in-needed") return "Sign-in needed again.";
  if (status.signedIn) return `Signed in. Snapshots are stored ${status.store === "onedrive" ? "in OneDrive" : "locally"}.`;
  if (!status.clientIdSet) return "Enter the client ID first.";
  return "Not signed in.";
}
