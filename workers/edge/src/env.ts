export interface Env {
  ASSETS: Fetcher;
  MATCH_HUB: DurableObjectNamespace;
  /** Shared secret for crew/producer POSTs. A Worker secret (`wrangler secret put OVERLAY_SECRET`), never committed. */
  OVERLAY_SECRET?: string;
  /** Batch length in ms: the hub sends one frames message per batch (default 1000, i.e. 25 frames at 25 fps). */
  BATCH_MS?: string;
}
