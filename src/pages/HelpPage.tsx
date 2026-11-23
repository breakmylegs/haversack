import { Dropdown, Field } from "@decky/ui";
import { Fragment, ReactNode, useState } from "react";
import { HELP, HelpBlock } from "../help";

// Settings, Help (R28, ADR-0090): the user guide, word for word, built from docs/user by scripts/help.py.
// Each heading starts a section that the controller can move to; the right stick scrolls a long one.
// Nothing here takes focus by itself (v0.41.1).

/** "**bold**" marks as bold text; everything else as it is. */
export function rich(text: string): ReactNode[] {
  return text.split("**").map((part, i) => (i % 2 ? <b key={i}>{part}</b> : <Fragment key={i}>{part}</Fragment>));
}

interface Section {
  title: string;
  level: number;
  blocks: HelpBlock[];
}

/** The topic's blocks, grouped under their headings (text before the first heading has no title). */
export function sections(blocks: HelpBlock[]): Section[] {
  const out: Section[] = [];
  for (const block of blocks) {
    if (block.k === "h") out.push({ title: block.t, level: block.l, blocks: [] });
    else if (out.length) out[out.length - 1].blocks.push(block);
    else out.push({ title: "", level: 2, blocks: [block] });
  }
  return out;
}

function Block({ block }: { block: HelpBlock }) {
  switch (block.k) {
    case "li":
      return <div style={{ paddingLeft: 12 + block.d * 16, textIndent: block.t.match(/^\d+\./) ? 0 : -10 }}>{block.t.match(/^\d+\./) ? rich(block.t) : <>{"• "}{rich(block.t)}</>}</div>;
    case "row":
      return <div style={{ fontSize: 13, opacity: 0.9 }}>{rich(block.t)}</div>;
    case "code":
      return <div style={{ fontFamily: "monospace", fontSize: 13, wordBreak: "break-all" }}>{block.t}</div>;
    default:
      return <div style={{ margin: "4px 0" }}>{rich(block.t)}</div>;
  }
}

export function HelpPage() {
  const [topicId, setTopicId] = useState(HELP[0]?.id ?? "");
  const topic = HELP.find((t) => t.id === topicId) ?? HELP[0];
  if (!topic) return <Field label="Help" description="The guide is not included in this build." />;
  return (
    <div>
      <Field label="Topic" description="The user guide, also at github.com/breakmylegs/haversack." childrenContainerWidth="max">
        <Dropdown
          rgOptions={HELP.map((t) => ({ data: t.id, label: t.title }))}
          selectedOption={topic.id}
          onChange={(option) => setTopicId(String(option.data))}
        />
      </Field>
      {sections(topic.blocks).map((section, i) => (
        <Field
          key={`${topic.id}-${i}`}
          focusable
          highlightOnFocus={false}
          label={section.title ? <span style={{ fontSize: section.level <= 1 ? 22 : 18 }}>{rich(section.title)}</span> : undefined}
          description={
            <div style={{ whiteSpace: "normal", lineHeight: 1.45 }}>
              {section.blocks.map((block, j) => (
                <Block key={j} block={block} />
              ))}
            </div>
          }
        />
      ))}
    </div>
  );
}
