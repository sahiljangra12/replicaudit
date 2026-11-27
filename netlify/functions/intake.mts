// ReplicAudit intake API. The website (GitHub Pages) calls this so visitors never need GitHub.
// No tokens or secrets are needed anywhere:
//   * files and requests are kept in Netlify Blobs (built in, free);
//   * the GitHub workflows prove who they are with GitHub's own OIDC identity token, which this
//     function checks against GitHub's public keys. Only workflows on the main branch of
//     PUBLIC_REPO are accepted.
//
// Public (called by the website):
//   GET  /api/health
//   POST /api/upload?rid=<id>&name=<file>&part=<n>&parts=<N>   body: raw bytes of one part (≤ 3.6 MB)
//   POST /api/submit                                            body: JSON form → { id }
//   GET  /api/status?id=<id>                                    → { status, issue? }
// Workflows only (Authorization: Bearer <GitHub OIDC token, audience "replicaudit-intake">):
//   GET  /api/pending                    → requests waiting to be picked up
//   POST /api/claim   { id, issue }      → records the GitHub request number
//   GET  /api/files?rid=<id>             → list of stored parts
//   GET  /api/file?key=<rid/name.partNNN> → one part
//   POST /api/done    { rid }            → deletes that request's files
import type { Config, Context } from "@netlify/functions"
import { getStore } from "@netlify/blobs"
import { createRemoteJWKSet, jwtVerify } from "jose"

const PUBLIC_REPO = "sahiljangra12/replicaudit"
const AUDIENCE = "replicaudit-intake"
const ALLOWED_ORIGINS = ["https://sahiljangra12.github.io", "http://localhost:8766"]
const MAX_PART = 3_600_000
const MAX_PARTS = 34 // 34 × 3 MB ≈ 100 MB per file
const OK_EXT = /\.(zip|gz|tgz|pdf|xlsx|xls|csv|docx|txt|json)$/i
const RID = /^[a-f0-9]{16}$/
const JWKS = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"))

const uploads = () => getStore({ name: "uploads", consistency: "strong" })
const queue = () => getStore({ name: "queue", consistency: "strong" })

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
const clean = (s: unknown, max = 2000) => String(s ?? "").replace(/\r/g, "").trim().slice(0, max)
const safeName = (s: string) => s.replace(/[^\w.\- ]+/g, "_").replace(/\s+/g, "_").slice(0, 120)

// ---------- identity of the GitHub workflow ----------
async function isWorkflow(req: Request): Promise<boolean> {
  const m = (req.headers.get("authorization") || "").match(/^Bearer\s+(.+)$/i)
  if (!m) return false
  try {
    const { payload } = await jwtVerify(m[1], JWKS, {
      issuer: "https://token.actions.githubusercontent.com", audience: AUDIENCE,
    })
    const wf = String(payload.job_workflow_ref || "")
    return payload.repository === PUBLIC_REPO && payload.ref === "refs/heads/main" &&
      wf.startsWith(PUBLIC_REPO + "/.github/workflows/") && wf.endsWith("@refs/heads/main")
  } catch {
    return false
  }
}

// ---------- public ----------
async function upload(req: Request, url: URL) {
  const rid = url.searchParams.get("rid") || ""
  const name = safeName(url.searchParams.get("name") || "")
  const part = Number(url.searchParams.get("part")), parts = Number(url.searchParams.get("parts"))
  if (!RID.test(rid)) return reply(req, 400, { error: "bad request id" })
  if (!name || !OK_EXT.test(name)) return reply(req, 400, { error: "file type not accepted" })
  if (!(part >= 1 && part <= parts && parts <= MAX_PARTS)) return reply(req, 400, { error: "file too large (max 100 MB); please use a Zenodo link" })
  const buf = await req.arrayBuffer()
  if (!buf.byteLength || buf.byteLength > MAX_PART) return reply(req, 400, { error: "bad part size" })
  await uploads().set(`${rid}/${name}.part${String(part).padStart(3, "0")}`, buf)
  return reply(req, 200, { ok: true, ref: `upload://${rid}/${encodeURIComponent(name)}` })
}

function section(label: string, value: string) {
  return `### ${label}\n\n${value || "_No response_"}\n\n`
}

async function submit(req: Request) {
  let f: Record<string, unknown>
  try { f = await req.json() } catch { return reply(req, 400, { error: "invalid form" }) }
  if (clean(f.website)) return reply(req, 200, { ok: true, id: "0000000000000000" }) // honeypot
  const title = clean(f.title, 300), doi = clean(f.doi, 200).replace(/^https?:\/\/(dx\.)?doi\.org\//i, "")
  const pkg = clean(f.package, 2000)
  const missing = [["title", title], ["DOI", doi], ["data and code", pkg]].filter(([, v]) => !v).map(([k]) => k)
  if (missing.length) return reply(req, 400, { error: "missing: " + missing.join(", ") })
  if (!/^10\.\d{4,9}\/\S+$/.test(doi)) return reply(req, 400, { error: "the DOI does not look valid" })
  let id = clean(f.rid, 16)
  if (!RID.test(id)) id = [...crypto.getRandomValues(new Uint8Array(8))].map(b => b.toString(16).padStart(2, "0")).join("")
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
    `<!-- submitted through the ReplicAudit website; request ${id} -->\n`
  await queue().setJSON(id, { id, status: "queued", created: new Date().toISOString(),
                               title: `[Audit] ${title}`.slice(0, 250), body })
  return reply(req, 200, { ok: true, id })
}

async function status(req: Request, url: URL) {
  const id = url.searchParams.get("id") || ""
  if (!RID.test(id)) return reply(req, 400, { error: "bad request id" })
  const q = await queue().get(id, { type: "json" }) as any
  if (!q) return reply(req, 404, { error: "No request with this code." })
  return reply(req, 200, { status: q.status, issue: q.issue || null, title: q.title, created: q.created })
}

// ---------- workflows only ----------
async function pending(req: Request) {
  const { blobs } = await queue().list()
  const out = []
  for (const b of blobs) {
    const q = await queue().get(b.key, { type: "json" }) as any
    if (q && q.status === "queued") out.push({ id: q.id, title: q.title, body: q.body })
  }
  return reply(req, 200, out)
}
async function claim(req: Request) {
  const { id, issue } = await req.json() as any
  if (!RID.test(String(id)) || !(Number(issue) > 0)) return reply(req, 400, { error: "bad claim" })
  const q = await queue().get(id, { type: "json" }) as any
  if (!q) return reply(req, 404, { error: "unknown id" })
  await queue().setJSON(id, { ...q, status: "claimed", issue: Number(issue), body: undefined })
  return reply(req, 200, { ok: true })
}
async function files(req: Request, url: URL) {
  const rid = url.searchParams.get("rid") || ""
  if (!RID.test(rid)) return reply(req, 400, { error: "bad request id" })
  const { blobs } = await uploads().list({ prefix: rid + "/" })
  return reply(req, 200, blobs.map(b => b.key).sort())
}
async function file(req: Request, url: URL) {
  const key = url.searchParams.get("key") || ""
  if (!/^[a-f0-9]{16}\/[\w.\- ]+\.part\d{3}$/.test(key)) return reply(req, 400, { error: "bad key" })
  const data = await uploads().get(key, { type: "arrayBuffer" })
  if (!data) return reply(req, 404, { error: "not found" })
  return new Response(data, { status: 200, headers: { "content-type": "application/octet-stream" } })
}
async function done(req: Request) {
  const { rid } = await req.json() as any
  if (!RID.test(String(rid))) return reply(req, 400, { error: "bad request id" })
  const { blobs } = await uploads().list({ prefix: rid + "/" })
  for (const b of blobs) await uploads().delete(b.key)
  return reply(req, 200, { ok: true, deleted: blobs.length })
}

export default async (req: Request, context: Context) => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(req) })
  const url = new URL(req.url)
  const route = url.pathname.replace(/^\/api\//, "")
  try {
    if (route === "health") return reply(req, 200, { ok: true })
    if (route === "status" && req.method === "GET") return await status(req, url)
    if (route === "upload" && req.method === "POST") return await upload(req, url)
    if (route === "submit" && req.method === "POST") return await submit(req)
    if (["pending", "claim", "files", "file", "done"].includes(route)) {
      if (!(await isWorkflow(req))) return reply(req, 401, { error: "workflow identity required" })
      if (route === "pending") return await pending(req)
      if (route === "claim" && req.method === "POST") return await claim(req)
      if (route === "files") return await files(req, url)
      if (route === "file") return await file(req, url)
      if (route === "done" && req.method === "POST") return await done(req)
    }
    return reply(req, 404, { error: "not found" })
  } catch (e) {
    console.error(e)
    return reply(req, 502, { error: "The request could not be stored. Please try again in a minute." })
  }
}

export const config: Config = {
  path: ["/api/health", "/api/upload", "/api/submit", "/api/status",
         "/api/pending", "/api/claim", "/api/files", "/api/file", "/api/done"],
  method: ["GET", "POST", "OPTIONS"],
  rateLimit: { action: "rate_limit", aggregateBy: ["ip", "domain"], windowSize: 60, windowLimit: 60 },
}
