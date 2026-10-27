// Copies pdf.js's worker (a dependency of react-pdf) to public/ so the viewer loads it
// same-origin, at exactly the version react-pdf was built against.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const fromReactPdf = createRequire(require.resolve("react-pdf"));
const worker = fromReactPdf.resolve("pdfjs-dist/build/pdf.worker.min.mjs");
mkdirSync("public", { recursive: true });
copyFileSync(worker, "public/pdf.worker.min.mjs");
console.log(`copied ${worker} -> public/pdf.worker.min.mjs`);
