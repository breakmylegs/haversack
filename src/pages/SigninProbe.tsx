import { DialogButton, Field, Focusable, Navigation } from "@decky/ui";
import { useState } from "react";
import { recordProbeEvent, signinProbe } from "../backend";
import { JsonBlock } from "./JsonBlock";

// The Gaming Mode sign-in probe (ADR-0044): which providers allow sign-in in Steam's browser,
// and whether that browser can reach Keepsake's loopback redirect. Outcomes go to the
// diagnostics export, so the next change can set the Gaming Mode defaults from them.

const PAGES = [
  { id: "microsoft", label: "Microsoft", url: "https://login.live.com/" },
  { id: "google", label: "Google", url: "https://accounts.google.com/" },
] as const;

export function SigninProbe() {
  const [loopback, setLoopback] = useState<unknown>(null);
  const [opened, setOpened] = useState(false);
  const [reported, setReported] = useState<Record<string, string>>({});

  const report = (provider: string, outcome: string) => {
    setReported((prev) => ({ ...prev, [provider]: outcome }));
    recordProbeEvent("signin-browser", { provider, outcome }).catch(() => undefined);
  };

  return (
    <div>
      <Field
        label="Sign-in browser test"
        description="Checks which sign-ins work in Steam's browser on this device. Nothing is signed in to Keepsake. Run the three steps, then export diagnostics."
      />
      <Field label="1. Loopback" description="Opens a test page that Keepsake serves on this device. When it says you're signed in, come back and check." childrenLayout="below">
        <Focusable style={{ display: "flex", gap: 8 }}>
          <DialogButton
            style={{ width: "auto" }}
            onClick={async () => {
              const started = await signinProbe("start");
              if (started.url) {
                setOpened(true);
                Navigation.NavigateToExternalWeb(started.url);
              } else setLoopback(started);
            }}
          >
            Open the test page
          </DialogButton>
          <DialogButton style={{ width: "auto" }} disabled={!opened} onClick={async () => setLoopback(await signinProbe("result"))}>
            Check
          </DialogButton>
        </Focusable>
        {loopback !== null && <JsonBlock value={loopback} />}
      </Field>
      {PAGES.map((page, index) => (
        <Field
          key={page.id}
          label={`${index + 2}. ${page.label}`}
          description={`Opens ${page.url}. Sign in with your ${page.label} account, then come back and say what happened.`}
          childrenLayout="below"
        >
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <DialogButton style={{ width: "auto" }} onClick={() => Navigation.NavigateToExternalWeb(page.url)}>
              Open {page.label} sign-in
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => report(page.id, "worked")}>
              It worked
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => report(page.id, "blocked")}>
              Blocked ("not secure")
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => report(page.id, "looped")}>
              It kept looping
            </DialogButton>
            <DialogButton style={{ width: "auto" }} onClick={() => report(page.id, "other")}>
              Something else
            </DialogButton>
          </Focusable>
          {reported[page.id] && <Field description={`Recorded: ${reported[page.id]}.`} />}
        </Field>
      ))}
    </div>
  );
}
