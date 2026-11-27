// ReplicAudit intake API. The website (GitHub Pages) calls this so visitors never need GitHub.
//   POST /api/upload?rid=<id>&name=<file>&part=<n>&parts=<N>   body: raw bytes (one part, ≤ 3.5 MB)
//        → stores the part in the PRIVATE uploads repository as <id>/<file>.part001 …
//   POST /api/submit                                            body: JSON with the form fields
//        → opens the audit request (an issue in the public repository), which starts the free audit.
// Environment (set in Netlify, scope: Functions):  GH_INTAKE_TOKEN — fine-grained GitHub token with
//   Issues: read & write on PUBLIC_REPO, and Contents: read & write on UPLOADS_REPO.
import type { Config, Context } from "@netlify/functions"

const PUBLIC_REPO = "sahiljangra12/replicaudit"
const UPLOADS_REPO = "sahiljangra12/replicaudit-uploads"
const ALLOWED_ORIGINS = ["https://sahiljangra12.github.io", "http://localhost:8766"]
const MAX_PART = 3_600_000
const MAX_PARTS = 34 // 34 × 3 MB ≈ 100 MB per file
const OK_EXT = /\.(zip|gz|tgz|pdf|xlsx|xls|csv|docx|txt|json)$/i

function cors(req: Request): Record<string, string> {
  const o = req.headers.get("origin") || ""
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGINS.includes(o) ? o : ALLOWED_ORIGINS[0],
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Vary": "Origin",
  }
}
function reply(req: Request, status: number, body: unknown) {
  return Response.json(body, { status, headers: cors(req) })
}
async function gh(path: string, init: RequestInit = {}) {
  const token = Netlify.env.get("GH_INTAKE_TOKEN")
  if (!token) throw new Error("server not configured (GH_INTAKE_TOKEN missing)")
  const r = await fetch("https://api.github.com" + path, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "replicaudit-intake", ...(init.headers || {}) },
  })
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 200)}`)
  return r.json()
}
const clean = (s: unknown, max = 2000) => String(s ?? "").replace(/\r/g, "").trim().slice(0, max)
const safeName = (s: string) => s.replace(/[^\w.\- ]+/g, "_").replace(/\s+/g, "_").slice(0, 120)

async function upload(req: Request, url: URL) {
  const rid = url.searchParams.get("rid") || ""
  const name = safeName(url.searchParams.get("name") || "")
  const part = Number(url.searchParams.get("part")), parts = Number(url.searchParams.get("parts"))
  if (!/^[a-f0-9]{16}$/.test(rid)) return reply(req, 400, { error: "bad request id" })
  if (!name || !OK_EXT.test(name)) return reply(req, 400, { error: "file type not accepted" })
  if (!(part >= 1 && part <= parts && parts <= MAX_PARTS)) return reply(req, 400, { error: "file too large (max 100 MB); please use a Zenodo link" })
  const buf = new Uint8Array(await req.arrayBuffer())
  if (!buf.length || buf.length > MAX_PART) return reply(req, 400, { error: "bad part size" })
  let bin = ""
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000))
  const path = `${rid}/${name}.part${String(part).padStart(3, "0")}`
  await gh(`/repos/${UPLOADS_REPO}/contents/${encodeURIComponent(rid)}/${encodeURIComponent(name + ".part" + String(part).padStart(3, "0"))}`, {
    method: "PUT",
    body: JSON.stringify({ message: `upload ${path}`, content: btoa(bin) }),
  })
  return reply(req, 200, { ok: true, ref: `upload://${rid}/${encodeURIComponent(name)}` })
}

function section(label: string, value: string) {
  return `### ${label}\n\n${value || "_No response_"}\n\n`
}

async function submit(req: Request) {
  let f: Record<string, unknown>
  try { f = await req.json() } catch { return reply(req, 400, { error: "invalid form" }) }
  if (clean(f.website)) return reply(req, 200, { ok: true, number: 0 }) // honeypot: bots fill hidden fields
  const title = clean(f.title, 300), doi = clean(f.doi, 200).replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
  const pkg = clean(f.package, 2000)
  const missing = [["title", title], ["DOI", doi], ["data and code", pkg]].filter(([, v]) => !v).map(([k]) => k)
  if (missing.length) return reply(req, 400, { error: "missing: " + missing.join(", ") })
  if (!/^10\.\d{4,9}\/\S+$/.test(doi)) return reply(req, 400, { error: "the DOI does not look valid" })
  const claims = clean(f.claims, 20000)
  const body =
    section("Paper title", title) +
    section("Authors", clean(f.authors, 1000)) +
    section("Journal and year", clean(f.journal, 300)) +
    section("Paper DOI", doi) +
    section("Paper PDF (open-access link or attachment)", clean(f.paper, 2000)) +
    section("Replication package", pkg) +
    section("Supplementary materials", clean(f.supplement, 6000)) +
    section("Claims to check (optional)", claims ? "```csv\n" + claims + "\n```" : "") +
    section("Field", clean(f.field, 100) || "Not stated") +
    section("Your relationship to the paper", clean(f.relationship, 100) || "Not stated") +
    section("Notes for the auditors", clean(f.notes, 4000)) +
    "### Confirmation\n\n- [X] The replication materials are publicly available and I am allowed to point to them.\n" +
    "- [X] I understand the results are shown openly on the website.\n\n" +
    "<!-- submitted through the ReplicAudit website -->\n"
  const issue = await gh(`/repos/${PUBLIC_REPO}/issues`, {
    method: "POST",
    body: JSON.stringify({ title: `[Audit] ${title}`.slice(0, 250), body, labels: ["audit-request"] }),
  })
  return reply(req, 200, { ok: true, number: issue.number })
}

export default async (req: Request, context: Context) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) })
  const url = new URL(req.url)
  if (url.pathname.endsWith("/health")) {
    const ready = Boolean(Netlify.env.get("GH_INTAKE_TOKEN"))
    return reply(req, ready ? 200 : 503, { ok: ready })
  }
  if (req.method !== "POST") return reply(req, 405, { error: "POST only" })
  try {
    if (url.pathname.endsWith("/upload")) return await upload(req, url)
    if (url.pathname.endsWith("/submit")) return await submit(req)
    return reply(req, 404, { error: "not found" })
  } catch (e) {
    console.error(e)
    return reply(req, 502, { error: "The request could not be stored. Please try again in a minute." })
  }
}

export const config: Config = {
  path: ["/api/upload", "/api/submit", "/api/health"],
  method: ["GET", "POST", "OPTIONS"],
  rateLimit: { action: "rate_limit", aggregateBy: ["ip", "domain"], windowSize: 60, windowLimit: 40 },
}
