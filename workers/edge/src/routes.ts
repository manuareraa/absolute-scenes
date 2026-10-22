// Pure routing, kept apart from the Workers runtime so it unit-tests in plain Node.
export type Route =
  | { kind: "health" }
  | { kind: "match_ws"; matchId: string }
  | { kind: "match_manifest"; matchId: string }
  | { kind: "match_control"; matchId: string }
  | { kind: "overlay" }
  | { kind: "not_found" };

const MATCH_ID = /^[A-Za-z0-9_-]{1,64}$/;

export function isMatchId(id: unknown): id is string {
  return typeof id === "string" && MATCH_ID.test(id);
}

export function route(pathname: string): Route {
  if (pathname === "/api/health") return { kind: "health" };
  if (pathname === "/api/overlay") return { kind: "overlay" };
  let m = pathname.match(/^\/ws\/match\/([^/]+)$/);
  if (m && isMatchId(m[1])) return { kind: "match_ws", matchId: m[1] };
  m = pathname.match(/^\/api\/match\/([^/]+?)(\/control)?$/);
  if (m && isMatchId(m[1])) {
    return m[2] ? { kind: "match_control", matchId: m[1] } : { kind: "match_manifest", matchId: m[1] };
  }
  return { kind: "not_found" };
}

/** Where a match package sits in the static assets (written by `chalktalk_sim`, copied by scripts/assemble.mjs). */
export function packageBase(matchId: string): string {
  return `/matches/${matchId}/`;
}

/** A real package file, not the single-page-app fallback (index.html) that assets serve for misses. */
export function isPackageFile(res: { ok: boolean; headers: Headers }): boolean {
  return res.ok && !(res.headers.get("content-type") ?? "").startsWith("text/html");
}
