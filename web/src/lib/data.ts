/**
 * Data loaders for ord-bench.
 * Reads benchmark artefacts from ../data/ at build time.
 *
 * Path layout (relative to the web/ folder):
 *   ../data/landscape/systems/           — clean ORD per system
 *   ../data/landscape/systems_enriched/  — enriched ORD per system
 *   ../data/landscape/logs/              — generation logs
 *   ../data/test_cases/design_time/      — processes, skills, cases
 *   ../data/test_cases/runtime/          — runtime test cases
 *   ../data/certification/               — audit / cert artefacts
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// src/lib/ → web/ → ord-bench/  →  ROOT = ord-bench/
const ROOT = path.resolve(__dirname, "..", "..", "..");

// ─── Landscape (ORD) ────────────────────────────────────────────────────────

export type OrdResource = {
  ordId: string;
  slug: string;
  namespace: string;
  type: "apiResource" | "agent" | "dataProduct" | "entityType" | "event";
  title: string;
  shortDescription: string;
  description: string;
  entityTypes: string[];
  partOfPackage: string;
  packageTitle: string;
  lineOfBusiness: string[];
  tags: string[];
  capabilities: string[];
  useCases: string[];
  partOfGroups: { groupId?: string; groupTypeId?: string }[];
  processNext: string[];
  raw: Record<string, unknown>;
};

export function ordIdToSlug(ordId: string): string {
  return ordId.replace(/[:.]/g, "-");
}

export type IntegrationDependencyAspect = {
  title: string;
  description?: string;
  mandatory?: boolean;
  apiResources?: { ordId: string; minVersion?: string }[];
  eventResources?: { ordId: string }[];
  dataProducts?: { ordId: string }[];
};

export type IntegrationDependency = {
  ordId: string;
  title: string;
  shortDescription: string;
  description: string;
  mandatory: boolean;
  namespace: string;
  aspects: IntegrationDependencyAspect[];
  raw: Record<string, unknown>;
};

export type System = {
  namespace: string;
  resources: OrdResource[];
  integrationDependencies: IntegrationDependency[];
  description: string;
  packages: { ordId: string; title: string; shortDescription: string }[];
};

const SYSTEM_DESCRIPTIONS: Record<string, string> = {
  "sap.s4":      "ERP, Finance, Manufacturing — SAP S/4HANA",
  "sap.sf":      "HR and People — SAP SuccessFactors",
  "sap.ariba":   "Procurement — SAP Ariba",
  "sap.crm":     "Sales and Customer — SAP CRM",
  "sap.ehs":     "Safety and Environment — SAP EHS",
  "corp.itsm":   "IT Service Management — Corporate ITSM",
  "my.mes":      "Manufacturing Execution — Custom MES",
  "workday.hcm": "HR (non-SAP) — Workday HCM",
  "emarsys.cx":  "Marketing and CX — Emarsys",
  "siemens.plm": "Product Lifecycle — Siemens PLM",
};

const SYSTEM_TITLES: Record<string, string> = {
  "sap.s4":      "SAP S/4HANA",
  "sap.sf":      "SAP SuccessFactors",
  "sap.ariba":   "SAP Ariba",
  "sap.crm":     "SAP CRM",
  "sap.ehs":     "SAP EHS",
  "corp.itsm":   "Corporate ITSM",
  "my.mes":      "Custom MES",
  "workday.hcm": "Workday HCM",
  "emarsys.cx":  "Emarsys",
  "siemens.plm": "Siemens PLM",
};

const RESOURCE_KEYS = [
  ["apiResources", "apiResource"],
  ["agents", "agent"],
  ["dataProducts", "dataProduct"],
  ["entityTypes", "entityType"],
  ["eventResources", "event"],
] as const;

function extractEntityTypes(item: any): string[] {
  const out: string[] = [];
  const add = (oid: string) => {
    if (oid && !out.includes(oid)) out.push(oid);
  };
  for (const m of item.entityTypeMappings ?? []) {
    for (const t of m.entityTypeTargets ?? []) {
      if (t?.ordId) add(t.ordId);
    }
  }
  for (const ref of item.exposedEntityTypes ?? []) {
    if (ref?.ordId) add(ref.ordId);
  }
  for (const ref of item.relatedEntityTypes ?? []) {
    if (typeof ref === "string") add(ref);
    else if (ref?.ordId) add(ref.ordId);
  }
  for (const et of item.entityTypes ?? []) {
    if (typeof et === "string") add(et);
  }
  return out;
}

export function loadSystems(state: "enriched" | "clean" = "enriched"): System[] {
  const landscapeDir = path.join(ROOT, "data", "landscape", "systems");
  const enrichedDir = path.join(ROOT, "data", "landscape", "systems_enriched");
  if (!fs.existsSync(landscapeDir)) return [];
  const dirs = fs
    .readdirSync(landscapeDir, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== "sap.odm")
    .map((d) => d.name)
    .sort();

  const systems: System[] = [];
  for (const ns of dirs) {
    const cleanPath = path.join(landscapeDir, ns, "ord.json");
    const enrichedPath = path.join(enrichedDir, ns, "ord_enriched.json");
    const usePath = (state === "enriched" && fs.existsSync(enrichedPath)) ? enrichedPath : cleanPath;
    if (!fs.existsSync(usePath)) continue;
    const doc = JSON.parse(fs.readFileSync(usePath, "utf8"));
    const pkgIdx = new Map<string, any>();
    for (const pkg of doc.packages ?? []) {
      pkgIdx.set(pkg.ordId, pkg);
    }
    const resources: OrdResource[] = [];
    for (const [key, t] of RESOURCE_KEYS) {
      for (const item of doc[key] ?? []) {
        const pkgMeta = pkgIdx.get(item.partOfPackage) ?? {};
        const ordId = item.ordId ?? "";
        resources.push({
          ordId,
          slug: ordIdToSlug(ordId),
          namespace: ns,
          type: t,
          title: item.title ?? "",
          shortDescription: item.shortDescription ?? "",
          description: item.description ?? "",
          entityTypes: extractEntityTypes(item),
          partOfPackage: item.partOfPackage ?? "",
          packageTitle: pkgMeta.title ?? "",
          lineOfBusiness: item.lineOfBusiness ?? pkgMeta.lineOfBusiness ?? [],
          tags: item.tags ?? [],
          capabilities: item.capabilities ?? [],
          useCases: item.useCases ?? [],
          partOfGroups: item.partOfGroups ?? [],
          processNext: item.processNext ?? [],
          raw: item,
        });
      }
    }
    const integrationDependencies: IntegrationDependency[] = (
      doc.integrationDependencies ?? []
    ).map((dep: any) => ({
      ordId: dep.ordId ?? "",
      title: dep.title ?? "",
      shortDescription: dep.shortDescription ?? "",
      description: dep.description ?? "",
      mandatory: dep.mandatory ?? false,
      namespace: ns,
      aspects: (dep.aspects ?? []).map((asp: any) => ({
        title: asp.title ?? "",
        description: asp.description ?? "",
        mandatory: asp.mandatory ?? false,
        apiResources: asp.apiResources ?? [],
        eventResources: asp.eventResources ?? [],
        dataProducts: asp.dataProducts ?? [],
      })),
      raw: dep,
    }));

    systems.push({
      namespace: ns,
      resources,
      integrationDependencies,
      description: SYSTEM_DESCRIPTIONS[ns] ?? doc.description ?? "",
      packages: (doc.packages ?? []).map((p: any) => ({
        ordId: p.ordId,
        title: SYSTEM_TITLES[ns] ?? p.title ?? ns,
        shortDescription: p.shortDescription ?? "",
      })),
    });
  }
  return systems;
}

// ─── Ambiguity scores ────────────────────────────────────────────────────────

export type AmbiguityNeighbor = {
  ordId: string;
  title: string;
  type: string;
  namespace: string;
  sim: number;
  breakdown: {
    useCases: number | null;
    entityTypes: number | null;
    capabilities: number | null;
    tags: number | null;
    lineOfBusiness: number | null;
    cross_namespace: number | null;
    type_penalty_applied: boolean;
  };
  problems: string[];
};

export type AmbiguityEntry = {
  ordId: string;
  ambiguity_score: number;
  difficulty_band: string;
  n_neighbors_above_threshold: number;
  coverage_gap: boolean;
  can_be_ground_truth: boolean;
  ground_truth_eligible: boolean;
  high_neighbors: number;
  medium_neighbors: number;
  low_neighbors: number;
  top_neighbors: AmbiguityNeighbor[];
  all_neighbors?: AmbiguityNeighbor[];
};

let _ambiguityCache: Map<string, AmbiguityEntry> | null = null;

export function loadAmbiguity(): Map<string, AmbiguityEntry> {
  if (_ambiguityCache) return _ambiguityCache;
  const p = path.join(ROOT, "data", "landscape", "ambiguity", "landscape_ambiguity_report.json");
  if (!fs.existsSync(p)) return new Map();
  const report = JSON.parse(fs.readFileSync(p, "utf8"));
  const map = new Map<string, AmbiguityEntry>();
  for (const r of report.resources ?? []) {
    map.set(r.ordId, r as AmbiguityEntry);
  }
  _ambiguityCache = map;
  return map;
}

// ─── Processes (BPMN / CMMN) ────────────────────────────────────────────────

export type ProcessActivity = {
  taskId: string;
  label: string;
  description: string;
  expectedOrdIds: string[];
  capability: string;
  useCase: string;
  isGt: boolean;
};

export type ProcessModel = {
  file: string;
  name: string;
  title: string;
  description: string;
  kind: "bpmn" | "cmmn";
  activities: ProcessActivity[];
};

export function loadProcesses(): ProcessModel[] {
  const procDir = path.join(ROOT, "data", "test_cases", "design_time", "output", "processes");
  if (!fs.existsSync(procDir)) return [];

  const xmlFiles = fs.readdirSync(procDir)
    .filter((f) => f.endsWith(".xml") && !f.includes("enrichment"))
    .sort();

  const out: ProcessModel[] = [];
  for (const f of xmlFiles) {
    const text = fs.readFileSync(path.join(procDir, f), "utf8");
    const processId = f.replace(/\.xml$/, "");

    const enrichPath = path.join(procDir, `${processId}_enrichment.json`);
    const gtIds = new Set<string>(
      fs.existsSync(enrichPath)
        ? JSON.parse(fs.readFileSync(enrichPath, "utf8")).gt_ordIds ?? []
        : []
    );

    const kindMatch = text.match(/type="(bpmn|cmmn)"/);
    const kind = (kindMatch?.[1] ?? "bpmn") as "bpmn" | "cmmn";

    const activities: ProcessActivity[] = [];
    const stepRe = /<step\s([^/]*)\/?>/gs;
    let m: RegExpExecArray | null;
    while ((m = stepRe.exec(text)) !== null) {
      const attrs = m[1];
      const get = (a: string) => attrs.match(new RegExp(`${a}="([^"]*)"`)) ?.[1] ?? "";
      const ordId = get("ordId");
      activities.push({
        taskId: get("id"),
        label: get("label"),
        description: get("description"),
        expectedOrdIds: ordId ? [ordId] : [],
        capability: get("capability"),
        useCase: get("useCase"),
        isGt: gtIds.has(ordId),
      });
    }

    const procIdMatch = text.match(/<process[^>]+id="([^"]+)"/);
    const rawTitle = procIdMatch?.[1] ?? processId;
    const title = rawTitle
      .replace(/^proc_/, "")
      .replace(/_v\d+$/, "")
      .replace(/_/g, " ");

    const skillDir = path.join(ROOT, "data", "test_cases", "design_time", "output", "skills");
    const skillPath = path.join(skillDir, `${processId}.md`);
    let description = "";
    if (fs.existsSync(skillPath)) {
      const skillText = fs.readFileSync(skillPath, "utf8");
      const fm = parseFrontmatter(skillText);
      description = fm["description"] ?? "";
    }

    out.push({ file: f, name: processId, title, description, kind, activities });
  }
  return out;
}

// ─── Skills (SKILL.md) ──────────────────────────────────────────────────────

export type SkillStep = {
  index: number;
  name: string;
  ordConfirmed: string[];
};

export type Skill = {
  file: string;
  skillId: string;
  name: string;
  description: string;
  processType: string;
  sourceFile: string;
  steps: SkillStep[];
};

const FRONTMATTER_RE = /^---\s*\n([\s\S]*?)\n---\s*\n/;
const STEP_RE = /^###\s+(?:\d+\.\s+|Step\s+\d+:\s+)?(.+?)\s*$/gm;
const ORD_CONFIRMED_RE = /<!--\s*ord_confirmed:\s*([^>]+?)-->/g;

function parseFrontmatter(text: string): Record<string, string> {
  const m = text.match(FRONTMATTER_RE);
  if (!m) return {};
  const out: Record<string, string> = {};
  let currentKey: string | null = null;
  for (const line of m[1].split("\n")) {
    const kv = line.match(/^([a-zA-Z][\w-]*):\s*(.*)$/);
    if (kv) {
      out[kv[1]] = kv[2].trim().replace(/^>\s*/, "");
      currentKey = kv[1];
    } else if (currentKey && line.startsWith("  ")) {
      out[currentKey] = (out[currentKey] + " " + line.trim()).trim();
    }
  }
  return out;
}

function parseSteps(body: string): SkillStep[] {
  const headers: { start: number; name: string }[] = [];
  let match: RegExpExecArray | null;
  STEP_RE.lastIndex = 0;
  while ((match = STEP_RE.exec(body)) !== null) {
    headers.push({ start: match.index, name: match[1].trim() });
  }
  if (headers.length === 0) return [];
  headers.push({ start: body.length, name: "" });
  const steps: SkillStep[] = [];
  for (let i = 0; i < headers.length - 1; i++) {
    const block = body.slice(headers[i].start, headers[i + 1].start);
    const confirmed: string[] = [];
    ORD_CONFIRMED_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = ORD_CONFIRMED_RE.exec(block)) !== null) {
      for (const oid of m[1].split(",")) {
        const x = oid.trim();
        if (x) confirmed.push(x);
      }
    }
    steps.push({ index: i + 1, name: headers[i].name, ordConfirmed: confirmed });
  }
  return steps;
}

export function loadSkills(): Skill[] {
  const dir = path.join(ROOT, "data", "test_cases", "design_time", "output", "skills");
  if (!fs.existsSync(dir)) return [];
  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".md")).sort();
  return files.map((f) => {
    const text = fs.readFileSync(path.join(dir, f), "utf8");
    const fm = parseFrontmatter(text);
    const m = text.match(FRONTMATTER_RE);
    const body = m ? text.slice(m[0].length) : text;
    return {
      file: f,
      skillId: fm["process-id"] ?? f.replace(/\.md$/, ""),
      name: fm["name"] ?? f.replace(/\.md$/, ""),
      description: fm["description"] ?? "",
      processType: fm["process-type"] ?? "bpmn",
      sourceFile: fm["source-file"] ?? "",
      steps: parseSteps(body),
    };
  });
}

// ─── Test cases ─────────────────────────────────────────────────────────────

export type RuntimeCase = {
  case_id: string;
  mode: "skill_guided" | "skill_adjusted" | "dynamic" | "out_of_scope";
  query_class: string;
  user_prompt: string;
  expected_skill_id?: string;
  expected_ordIds?: string[];
  expected_steps?: { step_name: string; expected_ordIds: string[] }[];
  expected_gap_ordIds?: string[];
  problems_exercised?: string[];
  distractor_ordId?: string | null;
  topic?: string;
  skill_id?: string;
};

export function loadRuntimeCases(): RuntimeCase[] {
  const modes = ["skill_guided", "skill_adjusted", "dynamic", "out_of_scope"];
  const all: RuntimeCase[] = [];
  for (const m of modes) {
    const p = path.join(ROOT, "data", "test_cases", "runtime", "output", `${m}.json`);
    if (fs.existsSync(p)) all.push(...JSON.parse(fs.readFileSync(p, "utf8")));
  }
  return all;
}

export function groupByMode(cases: RuntimeCase[]) {
  const out: Record<string, RuntimeCase[]> = {
    skill_guided: [], skill_adjusted: [], dynamic: [], out_of_scope: [],
  };
  for (const c of cases) {
    out[c.mode]?.push(c);
  }
  return out;
}

export type DtCase = {
  caseId: string;
  slug: string;
  process: string;
  processName: string;
  taskId: string;
  label: string;
  expectedOrdIds: string[];
  isGt: boolean;
  capability: string;
};

export function dtCaseSlug(caseId: string): string {
  return caseId.replace(/[^a-zA-Z0-9_-]/g, "-");
}

export function loadDtAnnotations(): DtCase[] {
  const p = path.join(
    ROOT, "data", "test_cases", "design_time", "output", "activity_cases.json"
  );
  if (!fs.existsSync(p)) return [];
  const raw: any[] = JSON.parse(fs.readFileSync(p, "utf8"));
  return raw.map((c) => ({
    caseId: c.case_id,
    slug: dtCaseSlug(c.case_id),
    process: c.process_id + ".xml",
    processName: c.process_id,
    taskId: c.step_id ?? c.step_index?.toString() ?? "",
    label: c.input,
    expectedOrdIds: c.expected_ordId ? [c.expected_ordId] : [],
    isGt: c.is_gt ?? false,
    capability: c.capability ?? "",
  })).sort((a, b) => a.caseId.localeCompare(b.caseId));
}

// ─── Entity types ─────────────────────────────────────────────────────────

export type EntityType = {
  ordId: string;
  slug: string;
  namespace: string;
  localId: string;
  level: string;
  title: string;
  shortDescription: string;
  description: string;
  packageTitle: string;
  releaseStatus: string;
  relatedEntityTypeIds: string[];
  raw: Record<string, unknown>;
};

const ENTITY_CATALOGUES = ["sap.odm"] as const;

export function loadEntityTypes(): EntityType[] {
  const out: EntityType[] = [];
  for (const ns of ENTITY_CATALOGUES) {
    const p = path.join(ROOT, "data", "landscape", "systems", ns, "ord.json");
    if (!fs.existsSync(p)) continue;
    const doc = JSON.parse(fs.readFileSync(p, "utf8"));
    const pkgIdx = new Map<string, any>();
    for (const pkg of doc.packages ?? []) {
      pkgIdx.set(pkg.ordId, pkg);
    }
    for (const et of doc.entityTypes ?? []) {
      const ordId: string = et.ordId ?? "";
      const pkg = pkgIdx.get(et.partOfPackage) ?? {};
      const related = (et.relatedEntityTypes ?? [])
        .map((r: any) => (typeof r === "string" ? r : r?.ordId))
        .filter(Boolean);
      out.push({
        ordId,
        slug: ordIdToSlug(ordId),
        namespace: ns,
        localId: et.localId ?? "",
        level: et.level ?? "",
        title: et.title ?? "",
        shortDescription: et.shortDescription ?? "",
        description: et.description ?? "",
        packageTitle: pkg.title ?? "",
        releaseStatus: et.releaseStatus ?? "",
        relatedEntityTypeIds: related,
        raw: et,
      });
    }
  }
  return out;
}

export type EntityUsage = {
  ordId: string;
  slug: string;
  namespace: string;
  title: string;
  kind: "agent" | "apiResource" | "dataProduct" | "entityType" | "event";
};

export function loadEntityUsages(): Map<string, EntityUsage[]> {
  const usages = new Map<string, EntityUsage[]>();
  for (const sys of loadSystems("enriched")) {
    if (sys.namespace === "sap.odm") continue;
    for (const r of sys.resources) {
      if (r.type === "entityType") continue;
      for (const et of r.entityTypes) {
        const list = usages.get(et) ?? [];
        list.push({
          ordId: r.ordId,
          slug: ordIdToSlug(r.ordId),
          namespace: sys.namespace,
          title: r.title,
          kind: r.type as EntityUsage["kind"],
        });
        usages.set(et, list);
      }
    }
  }
  return usages;
}

export function loadAgentCalls(): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const sys of loadSystems("enriched")) {
    if (sys.namespace === "sap.odm") continue;
    const agentByLocal = new Map<string, string>();
    for (const r of sys.resources) {
      if (r.type !== "agent") continue;
      const local = r.ordId.split(":")[2]?.toLowerCase();
      if (local) agentByLocal.set(local, r.ordId);
    }
    for (const dep of sys.integrationDependencies) {
      const m = dep.ordId.match(/:integrationDependency:([^:]+)-to-/);
      if (!m) continue;
      const sourceLocal = m[1].toLowerCase();
      const agentOrdId = agentByLocal.get(sourceLocal);
      if (!agentOrdId) continue;
      const targets: string[] = [];
      for (const asp of dep.aspects) {
        for (const a of asp.apiResources || []) targets.push(a.ordId);
        for (const e of asp.eventResources || []) targets.push(e.ordId);
        for (const d of asp.dataProducts || []) targets.push(d.ordId);
      }
      const list = out.get(agentOrdId) ?? [];
      for (const t of targets) if (!list.includes(t)) list.push(t);
      out.set(agentOrdId, list);
    }
  }
  return out;
}

// ─── Graph view ─────────────────────────────────────────────────────────────

export type GraphNode = {
  id: string;
  label: string;
  kind: "system" | "agent" | "apiResource" | "dataProduct" | "entityType" | "process";
  namespace?: string;
  ordId?: string;
  slug?: string;
  degree?: number;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  kind: "hosts" | "entities" | "calls" | "processNext" | "partOfGroups";
};

export type LandscapeGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export function buildLandscapeGraph(): LandscapeGraph {
  const systems = loadSystems("enriched");
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];

  function addNode(n: GraphNode) {
    if (!nodes.has(n.id)) nodes.set(n.id, n);
  }
  function addEdge(e: GraphEdge) {
    edges.push(e);
  }

  for (const sys of systems) {
    if (sys.namespace === "sap.odm") continue;
    const sysId = `sys:${sys.namespace}`;
    addNode({ id: sysId, label: sys.packages?.[0]?.title || sys.namespace, kind: "system", namespace: sys.namespace });

    for (const r of sys.resources) {
      const kind = r.type as GraphNode["kind"];
      if (kind === "entityType") continue;
      const rid = `res:${r.ordId}`;
      addNode({ id: rid, label: r.title, kind, namespace: sys.namespace, ordId: r.ordId, slug: ordIdToSlug(r.ordId) });
      addEdge({ id: `e:hosts:${sysId}->${rid}`, source: sysId, target: rid, kind: "hosts" });
      for (const et of r.entityTypes) {
        const eid = `et:${et}`;
        const local = et.split(":")[2] ?? et;
        addNode({ id: eid, label: local, kind: "entityType", ordId: et, slug: ordIdToSlug(et) });
        addEdge({ id: `e:entities:${rid}->${eid}`, source: rid, target: eid, kind: "entities" });
      }
      for (const nx of r.processNext || []) {
        if (typeof nx !== "string") continue;
        addEdge({ id: `e:next:${rid}->res:${nx}`, source: rid, target: `res:${nx}`, kind: "processNext" });
      }
    }
  }

  const procDir = path.join(ROOT, "data", "test_cases", "design_time", "output", "processes");
  if (fs.existsSync(procDir)) {
    const xmlFiles = fs.readdirSync(procDir).filter((f) => f.endsWith(".xml") && !f.includes("enrichment"));
    for (const f of xmlFiles) {
      const xml = fs.readFileSync(path.join(procDir, f), "utf8");
      const processIdMatch = xml.match(/<process[^>]+id="([^"]+)"/);
      if (!processIdMatch) continue;
      const processXmlId = processIdMatch[1];
      const fileId = f.replace(/\.xml$/, "");
      const gnid = `group:${fileId}`;
      const label = processXmlId.replace(/^proc_/, "").replace(/_v\d+$/, "").replace(/_/g, " ");
      addNode({ id: gnid, label, kind: "process", ordId: fileId, slug: fileId });
      const stepOrdIds = xml.matchAll(/ordId="([^"]+)"/g);
      for (const m of stepOrdIds) {
        const rid = `res:${m[1]}`;
        if (nodes.has(rid)) {
          addEdge({ id: `e:proc:${rid}->${gnid}`, source: rid, target: gnid, kind: "partOfGroups" });
        }
      }
    }
  }

  const calls = loadAgentCalls();
  for (const [agentOrdId, targets] of calls) {
    const src = `res:${agentOrdId}`;
    for (const t of targets) {
      addEdge({ id: `e:calls:${src}->res:${t}`, source: src, target: `res:${t}`, kind: "calls" });
    }
  }

  const nodeIds = new Set(nodes.keys());
  const cleanEdges = edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));

  const degree = new Map<string, number>();
  for (const e of cleanEdges) {
    degree.set(e.source, (degree.get(e.source) || 0) + 1);
    degree.set(e.target, (degree.get(e.target) || 0) + 1);
  }
  for (const [id, n] of nodes) {
    n.degree = degree.get(id) || 0;
  }

  return { nodes: [...nodes.values()], edges: cleanEdges };
}
