import { Fragment, type ReactNode } from "react";

/** **bold**, *italic* / _italic_ and `code`; anything else stays text. */
function inline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|\b_[^_]+_\b)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>;
    if (/^(\*[^*].*\*|_.+_)$/.test(part)) return <em key={i}>{part.slice(1, -1)}</em>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

type Block = { kind: "p" | "h" | "ul" | "ol"; lines: string[] };

function blocks(source: string): Block[] {
  const out: Block[] = [];
  for (const raw of source.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const number = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const heading = line.match(/^#{1,6}\s+(.*)$/);
    const last = out[out.length - 1];
    if (!line.trim()) out.push({ kind: "p", lines: [] });
    else if (heading) out.push({ kind: "h", lines: [heading[1]] });
    else if (bullet) last?.kind === "ul" ? last.lines.push(bullet[1]) : out.push({ kind: "ul", lines: [bullet[1]] });
    else if (number) last?.kind === "ol" ? last.lines.push(number[1]) : out.push({ kind: "ol", lines: [number[1]] });
    else if (last?.kind === "p") last.lines.push(line);
    else out.push({ kind: "p", lines: [line] });
  }
  return out.filter((b) => b.lines.length > 0);
}

/** The small Markdown subset the fix drafter writes: paragraphs, headings, lists, emphasis. */
export function Markdown({ source, className }: { source: string; className?: string }) {
  return (
    <div className={className}>
      {blocks(source).map((b, i) => {
        if (b.kind === "h") return <p key={i} className="mt-3 font-semibold first:mt-0">{inline(b.lines[0])}</p>;
        if (b.kind === "ul" || b.kind === "ol") {
          const List = b.kind;
          return (
            <List key={i} className={`mt-2 space-y-1 pl-5 first:mt-0 ${b.kind === "ul" ? "list-disc" : "list-decimal"}`}>
              {b.lines.map((line, j) => (
                <li key={j}>{inline(line)}</li>
              ))}
            </List>
          );
        }
        return (
          <p key={i} className="mt-2 whitespace-pre-line first:mt-0">
            {inline(b.lines.join("\n"))}
          </p>
        );
      })}
    </div>
  );
}

/** The same text without Markdown marks, for pasting into a letter or email. */
export function plainText(source: string): string {
  return source
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/(^|[^*\w])\*([^*\s][^*]*)\*/g, "$1$2")
    .replace(/\b_([^_]+)_\b/g, "$1");
}
