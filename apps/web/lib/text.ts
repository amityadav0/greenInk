const DEVANAGARI = /[ऀ-ॿ]/;
const UNREADABLE = /[-�]/g;

/**
 * A quote as it should read on screen. GeM PDFs print labels as "Hindi/English", and their
 * Hindi fonts extract as broken glyphs, so a line with Devanagari keeps only its English
 * parts. The verbatim quote is still what the PDF viewer highlights.
 */
export function readableQuote(quote: string): string {
  const lines = quote
    .replace(UNREADABLE, "")
    .split("\n")
    .map((line) => {
      if (!DEVANAGARI.test(line)) return line;
      return line
        .split("/")
        .filter((part) => !DEVANAGARI.test(part))
        .join("/")
        .trim();
    })
    .filter((line) => line.trim().length > 0);
  return lines.length > 0 ? lines.join("\n") : "Hindi text that could not be read from the PDF; open the page to see it.";
}

const FIELD_WORDS: Record<string, string> = {
  business_nature_wording: "business type on your papers",
  business_nature: "business type",
  oem_authorisations: "OEM authorisations",
  company_has: "what you have",
};

/** Model text with any leaked profile field names (e.g. `business_nature_wording`) in plain words. */
export function plainWords(text: string): string {
  // Not inside a URL, path or email address.
  return text.replace(/`?(?<![\w/.@-])([a-z]+(?:_[a-z]+)+)(?![\w/@-]|\.\w)`?/g, (_, name: string) => FIELD_WORDS[name] ?? name.replaceAll("_", " "));
}
