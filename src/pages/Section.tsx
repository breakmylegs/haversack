import { DialogButton, Focusable } from "@decky/ui";
import { ReactElement, useEffect, useState } from "react";
import { SectionId, takeRequestedTab } from "../routes";

// A section's tabs (layout v3, ADR-0073): a row of buttons the D-pad moves along, then the
// chosen tab. The tab is remembered while Keepsake is open, and a link can choose it.

export interface SectionTab {
  id: string;
  title: string;
  content: ReactElement;
}

const last: Partial<Record<SectionId, string>> = {};

export function SectionPage({ section, tabs, initial }: { section: SectionId; tabs: SectionTab[]; initial?: string }) {
  const pick = (wanted: string | undefined) => (wanted && tabs.some((t) => t.id === wanted) ? wanted : undefined);
  const [active, setActive] = useState<string>(
    () => pick(takeRequestedTab(section)) ?? pick(initial) ?? pick(last[section]) ?? tabs[0]?.id,
  );

  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ section: SectionId; tab?: string }>).detail;
      if (detail.section !== section) return;
      const tab = pick(takeRequestedTab(section) ?? detail.tab);
      if (tab) setActive(tab);
    };
    window.addEventListener("keepsake-tab", listener);
    return () => window.removeEventListener("keepsake-tab", listener);
  }, [section, tabs.map((t) => t.id).join(",")]);

  const shown = tabs.find((t) => t.id === active) ?? tabs[0];
  if (!shown) return null;
  last[section] = shown.id;
  return (
    <div>
      {tabs.length > 1 && (
        // A horizontal row the D-pad moves along; Down goes into the tab, and B is left to the
        // sidebar (no onCancel here), so focus always gets back to it (v0.39.1).
        <Focusable flow-children="horizontal" style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
          {tabs.map((t) => (
            <DialogButton
              key={t.id}
              style={{
                width: "auto",
                minWidth: 0,
                padding: "4px 14px",
                opacity: t.id === shown.id ? 1 : 0.65,
                borderBottom: t.id === shown.id ? "2px solid #1a9fff" : "2px solid transparent",
              }}
              onClick={() => setActive(t.id)}
            >
              {t.title}
            </DialogButton>
          ))}
        </Focusable>
      )}
      <div key={shown.id}>{shown.content}</div>
    </div>
  );
}
