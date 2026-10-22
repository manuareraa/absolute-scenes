import { route } from "./routes";

export { MatchHub } from "./hub";

export interface Env {
  ASSETS: Fetcher;
  MATCH_HUB: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const r = route(new URL(request.url).pathname);
    switch (r.kind) {
      case "health":
        return Response.json({ ok: true, service: "chalktalk-edge" });
      case "match_ws": {
        if (request.headers.get("Upgrade") !== "websocket") {
          return new Response("expected websocket", { status: 426 });
        }
        const stub = env.MATCH_HUB.get(env.MATCH_HUB.idFromName(r.matchId));
        return stub.fetch(request);
      }
      default:
        return new Response("not found", { status: 404 });
    }
  },
} satisfies ExportedHandler<Env>;
