import { afterPatch, appDetailsClasses, ErrorBoundary, findInReactTree } from "@decky/ui";
import { routerHook } from "@decky/api";
import { useEffect, useState } from "react";
import { libraryBadge } from "./backend";

// Keepsake's badge on a game's page in Steam's library (R18, ADR-0081): its saves' state, or the
// device a streaming tile streams from. Steam's page is not ours, so the patch is defensive:
// if the page does not look as expected, or anything throws, the page is left exactly as Steam
// drew it. The badge only reads; switching it off is Settings, General, "Badges in Steam's library".

const ROUTE = "/library/app/:appid";

// Steam's render tree has no types; this is the one place Keepsake walks it.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SteamTree = any;

const COLOURS: Record<string, string> = {
  synced: "#3fae5b",
  newer: "#1a9fff",
  conflict: "#d9534f",
  quarantined: "#e0a030",
  pending: "#e0a030",
  streaming: "#8a8fa3",
  off: "#8a8fa3",
  "not-synced": "#8a8fa3",
};

function Badge({ appid }: { appid: number }) {
  const [badge, setBadge] = useState<{ state: string; label: string } | null>(null);
  useEffect(() => {
    libraryBadge(appid)
      .then(setBadge)
      .catch(() => undefined); // no badge
  }, [appid]);
  if (!badge) return null;
  return (
    <div
      style={{
        position: "absolute",
        top: 64,
        right: 24,
        zIndex: 10,
        padding: "4px 10px",
        borderRadius: 12,
        fontSize: 13,
        background: "rgba(14, 20, 27, 0.8)",
        borderLeft: `4px solid ${COLOURS[badge.state] ?? "#8a8fa3"}`,
        color: "#fff",
        pointerEvents: "none",
      }}
    >
      Keepsake · {badge.label}
    </div>
  );
}

export function startLibraryBadges(): () => void {
  const patch = routerHook.addPatch(ROUTE, (route: SteamTree) => {
    try {
      const props = findInReactTree(route, (x: SteamTree) => x?.renderFunc);
      if (!props) return route;
      afterPatch(props, "renderFunc", (_args: SteamTree[], ret: SteamTree) => {
        try {
          const appid = Number(ret?.props?.children?.props?.overview?.appid);
          const container = findInReactTree(
            ret,
            (x: SteamTree) => Array.isArray(x?.props?.children) && String(x?.props?.className ?? "").includes(appDetailsClasses.InnerContainer),
          );
          if (!appid || !container || container.props.children.some((c: SteamTree) => c?.key === "keepsake-badge")) return ret;
          container.props.children.push(
            <ErrorBoundary key="keepsake-badge">
              <Badge appid={appid} />
            </ErrorBoundary>,
          );
        } catch {
          // Steam's page changed shape: leave it as Steam drew it.
        }
        return ret;
      });
    } catch {
      // As above.
    }
    return route;
  });
  return () => routerHook.removePatch(ROUTE, patch);
}
