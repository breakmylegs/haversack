import { Field } from "@decky/ui";
import { useEffect, useState } from "react";
import { sdCards, SdCard } from "../backend";
import { agoText } from "../format";

// Device, Storage: which games are on which SD card or drive, including cards not inserted
// (R29 stage 4, ADR-0096). Read only.
function names(card: SdCard): string {
  const all = [...card.games, ...card.shortcuts.map((s) => `${s} (non-Steam)`)];
  if (!all.length) return "No games on it.";
  const shown = all.slice(0, 12).join(", ");
  return all.length > 12 ? `${shown} and ${all.length - 12} more.` : `${shown}.`;
}

export function SdCardsPanel() {
  const [cards, setCards] = useState<SdCard[] | null>(null);
  useEffect(() => {
    sdCards()
      .then(setCards)
      .catch(() => undefined); // keep what is shown (v0.41.1)
  }, []);
  if (!cards || !cards.length) return null;
  return (
    <>
      <Field label="SD cards and drives" description="The games on each card Steam knows, even when the card is out." />
      {cards.map((card, i) => (
        <Field
          key={`${card.label}-${i}`}
          focusable
          highlightOnFocus={false}
          label={`${card.label}${card.inserted ? ", in this device" : card.lastSeen ? `, last seen ${agoText(card.lastSeen)}` : ", not inserted"}`}
          description={names(card)}
        />
      ))}
    </>
  );
}
