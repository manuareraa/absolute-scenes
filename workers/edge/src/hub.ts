import { DurableObject } from "cloudflare:workers";

/**
 * One instance per match. Holds viewers' WebSockets with hibernation (idle sockets cost
 * nothing), and fans out messages. M0 skeleton: relay only. Stream D adds the match
 * clock, approvals and the D1 audit trail.
 */
export class MatchHub extends DurableObject {
  async fetch(_request: Request): Promise<Response> {
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    this.ctx.acceptWebSocket(server);
    server.send(JSON.stringify({ type: "hello", viewers: this.ctx.getWebSockets().length }));
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(sender: WebSocket, message: string | ArrayBuffer): Promise<void> {
    for (const ws of this.ctx.getWebSockets()) {
      if (ws !== sender) ws.send(message);
    }
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    ws.close(code, reason);
  }
}
