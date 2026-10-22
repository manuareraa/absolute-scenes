// Pure routing, kept apart from the Workers runtime so it unit-tests in plain Node.
export type Route =
  | { kind: "health" }
  | { kind: "match_ws"; matchId: string }
  | { kind: "not_found" };

const MATCH_ID = /^[A-Za-z0-9_-]{1,64}$/;

export function route(pathname: string): Route {
  if (pathname === "/api/health") return { kind: "health" };
  const m = pathname.match(/^\/ws\/match\/([^/]+)$/);
  if (m && MATCH_ID.test(m[1])) return { kind: "match_ws", matchId: m[1] };
  return { kind: "not_found" };
}
