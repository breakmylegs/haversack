import { toaster } from "@decky/api";
import { DialogButton, Field } from "@decky/ui";
import { useState } from "react";
import { saveNavigationRecord } from "../backend";
import { plainError } from "../format";
import { NavEvent, startRecording, summarise } from "../navlog";

// Diagnostics, Tools: "Record navigation for 60 seconds" (v0.41.1). Move around the full page
// while it runs; the record is saved as one file and goes into the Device checks export.

const SECONDS = 60;

function summaryText(s: Record<string, number>): string {
  return [
    `${s.pageMounts} page openings`,
    `${s.routeMounts} full-page mounts`,
    `${s.focusCalls} focus calls`,
    `${s.unpromptedLeaves} focus jumps out of the sidebar with no button pressed`,
    `${s.navigations} navigations, ${s.redirects} redirects`,
  ].join(", ");
}

export function NavigationRecorder() {
  const [state, setState] = useState<"idle" | "recording" | "saving">("idle");
  const [last, setLast] = useState<string | null>(null);
  const start = () => {
    const done = async (events: NavEvent[]) => {
      setState("saving");
      try {
        const summary = summarise(events);
        const saved = await saveNavigationRecord({ summary, events });
        const text = summaryText(summary);
        setLast(`${text}. Saved: ${saved.where}`);
        toaster.toast({ title: "Navigation recorded", body: text });
      } catch (err) {
        toaster.toast({ title: "Navigation record", body: plainError(err) });
      } finally {
        setState("idle");
      }
    };
    if (startRecording(SECONDS, (events) => void done(events))) setState("recording");
    else toaster.toast({ title: "Navigation record", body: "Open this from Haversack's full page, and only one recording at a time." });
  };
  return (
    <Field
      label="Record navigation for 60 seconds"
      description={
        state === "recording"
          ? "Recording. Move through the sidebar and pages as you normally would; it stops by itself after 60 seconds."
          : (last ?? "Notes page openings, focus moves and focus calls while you move around, to find what makes the sidebar jump. No names or game titles are recorded.")
      }
    >
      {/* Never disabled: a focused button that turns disabled can push the focus elsewhere. */}
      <DialogButton onClick={() => state === "idle" && start()}>
        {state === "recording" ? "Recording" : state === "saving" ? "Saving" : "Record"}
      </DialogButton>
    </Field>
  );
}
