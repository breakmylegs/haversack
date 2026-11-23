// How the game ran on this device (ADR-0069): the Last session card, the Recent sessions trend, and the advice
// measured here, shown above community reports. Works for any game, running or not.
import { Field } from "@decky/ui";
import { AdvisorSession, AdvisorSessions } from "../backend";

function n(value: number | null | undefined, unit = "", digits = 0): string | null {
  return value === null || value === undefined ? null : `${value.toFixed(digits)}${unit}`;
}

function fpsText(s: AdvisorSession): string {
  const fps = s.fps ?? { source: null };
  if (!fps.source || fps.avg === undefined) return "frame rate not available";
  const low = fps.low1 !== undefined ? `, 1% low ${fps.low1.toFixed(0)}` : fps.min5s ? `, lowest 5 s ${fps.min5s.toFixed(0)}` : "";
  return `${fps.avg.toFixed(0)} fps${low}`;
}

function line(s: AdvisorSession): string {
  const parts = [
    fpsText(s),
    n(s.watts?.socketAvg, " W"),
    s.battery?.lifeHours ? `${s.battery.lifeHours.toFixed(1)} h battery` : null,
    n(s.gpu?.tempPeak, " °C GPU peak"),
    s.settings?.tdp ? `TDP ${s.settings.tdp} W` : null,
    s.throttle?.seen ? `throttled after ${s.throttle.afterMinutes?.toFixed(0)} min` : null,
  ];
  return parts.filter(Boolean).join(", ");
}

function when(s: AdvisorSession): string {
  return `${new Date(s.start * 1000).toISOString().slice(0, 16).replace("T", " ")}, ${Math.round(s.seconds / 60)} min, ${s.power}`;
}

export function SessionCards({ sessions }: { sessions?: AdvisorSessions }) {
  if (!sessions) return null;
  const last = sessions.last;
  if (!last) {
    return <Field label="Last session" description="Play this game for a few minutes and quit: Haversack measures how it ran on this device." />;
  }
  const details = [
    `CPU ${n(last.cpu?.busyAvg, "%") ?? "?"} at ${n(last.cpu?.mhzAvg, " MHz") ?? "?"}, GPU ${n(last.gpu?.busyAvg, "%") ?? "?"} at ${n(last.gpu?.mhzAvg, " MHz") ?? "?"}`,
    last.watts?.cpuAvg !== null && last.watts?.cpuAvg !== undefined ? `CPU ${last.watts.cpuAvg.toFixed(1)} W, GPU ${last.watts.gpuAvg?.toFixed(1) ?? "?"} W` : null,
    last.battery?.drainW ? `battery drain ${last.battery.drainW.toFixed(1)} W, ${last.battery.percentPerHour?.toFixed(0) ?? "?"}% an hour` : null,
    last.memory?.ramPeakMiB ? `RAM ${(last.memory.ramPeakMiB / 1024).toFixed(1)} GB, VRAM ${((last.memory.vramPeakMiB ?? 0) / 1024).toFixed(1)} GB` : null,
    last.settings?.protonVersion ? `Proton ${last.settings.protonVersion}` : null,
    last.settings?.frameGen ? `frame generation ${last.settings.frameGen}` : null,
  ].filter(Boolean);
  return (
    <>
      <Field label={`Last session: ${line(last)}`} description={`${when(last)}. ${details.join("; ")}.`} />
      {sessions.recent.length > 1 && (
        <Field
          label={`Recent sessions (${sessions.total?.sessions ?? sessions.recent.length} measured here)`}
          description={sessions.recent.map((s) => `${when(s)}: ${line(s)}`).join("\n")}
        />
      )}
      {sessions.advice.map((a) => (
        <Field key={a.id} label={a.text} description={a.source} />
      ))}
    </>
  );
}
