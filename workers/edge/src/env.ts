export interface Env {
  ASSETS: Fetcher;
  MATCH_HUB: DurableObjectNamespace;
  /** Shared secret for crew/producer POSTs. A Worker secret (`wrangler secret put OVERLAY_SECRET`), never committed. */
  OVERLAY_SECRET?: string;
  /** Batch length in ms: the hub sends one frames message per batch (default 1000, i.e. 25 frames at 25 fps). */
  BATCH_MS?: string;
  /** Wait in ms after the final whistle before the match kicks off again for those still watching (default 20000). */
  RESTART_MS?: string;
  /** "Ask the pundit" crew endpoint (POST, streams NDJSON). Unset: /api/ask answers 501 and the web app rehearses. */
  ASK_BACKEND_URL?: string;
  /** Shared secret sent to the crew backend. A Worker secret, never committed. */
  ASK_BACKEND_SECRET?: string;
  /** Kill switch: "false" turns /api/ask off (503) without a deploy of new code. */
  ASK_ENABLED?: string;
  /** Questions per viewer per minute (default 4). */
  ASK_PER_MINUTE?: string;
  /** Questions per UTC day across all viewers (default 300), kept in a Durable Object. */
  ASK_DAILY_QUOTA?: string;
  /** Speech resource key for /api/voice-token. A Worker secret, never committed. Unset: voice is off (501). */
  SPEECH_KEY?: string;
  /** Speech resource region (default koreacentral). */
  SPEECH_REGION?: string;
  /** Voice tokens per viewer per minute (default 6). */
  VOICE_PER_MINUTE?: string;
}
