// Usage: node tools/extract_estimates.js paper.pdf [more.pdf ...]  -> JSON list of suggested estimates on stdout.
// Uses the same finder as the website (site_src/estimates.js).
const fs = require("fs"), path = require("path");
console.log = console.warn = console.info = () => {};  // keep stdout for the JSON only
global.window = {};
window.pdfjsLib = require("pdfjs-dist/legacy/build/pdf.js");
eval(fs.readFileSync(path.join(__dirname, "..", "site_src", "estimates.js"), "utf8"));
(async () => {
  const all = [];
  for (const f of process.argv.slice(2)) {
    const b = fs.readFileSync(f);
    try {
      const s = await window.RAEstimates.fromArrayBuffer(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength), { source: path.basename(f) });
      all.push(...s);
    } catch (e) { console.error("could not read", f, e.message); }
  }
  process.stdout.write(JSON.stringify(all));
})();
