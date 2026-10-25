// Voice in for "Ask the pundit". The browser never holds a key: the Worker's /api/voice-token
// trades its Speech key for a 10-minute token, and the Speech SDK (loaded only on the first tap)
// recognises one question. Anything missing (no route, no mic, permission denied) leaves typing.

export interface VoiceToken {
  token: string;
  region: string;
  /** Seconds the token lives. */
  expires_in: number;
}

export type VoiceProblem = "unavailable" | "denied" | "failed";

export interface ListenHandlers {
  /** The first sound of speech: the moment to barge in on an answer. */
  onSpeech(): void;
  onPartial(text: string): void;
  onFinal(text: string): void;
  onEnd(problem?: VoiceProblem): void;
}

export interface Listening {
  stop(): void;
}

let cached: { tok: VoiceToken; until: number } | null = null;

/** A fresh token from the Worker, reused until a minute before it expires. */
export async function voiceToken(fetchFn: typeof fetch = fetch, now = Date.now()): Promise<VoiceToken | null> {
  if (cached && cached.until > now) return cached.tok;
  try {
    const res = await fetchFn("/api/voice-token", { headers: { accept: "application/json" } });
    if (!res.ok) return null;
    const tok = (await res.json()) as VoiceToken;
    if (!tok.token || !tok.region) return null;
    cached = { tok, until: now + Math.max(0, (tok.expires_in ?? 600) - 60) * 1000 };
    return tok;
  } catch {
    return null;
  }
}

export function resetVoiceToken() {
  cached = null;
}

/** Can this browser record at all? (The token is checked on the first tap.) */
export const canRecord = () => typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof window !== "undefined" && window.isSecureContext;

/** Listens for one question in `lang`; resolves once the recogniser is running. */
export async function listen(lang: string, h: ListenHandlers): Promise<Listening> {
  const tok = await voiceToken();
  if (!tok || !canRecord()) {
    h.onEnd("unavailable");
    return { stop() {} };
  }
  try {
    // The mic prompt comes first, so a refusal reads as "denied", not as an SDK failure.
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    for (const t of stream.getTracks()) t.stop();
  } catch {
    h.onEnd("denied");
    return { stop() {} };
  }
  const sdk = await import("microsoft-cognitiveservices-speech-sdk");
  const cfg = sdk.SpeechConfig.fromAuthorizationToken(tok.token, tok.region);
  cfg.speechRecognitionLanguage = lang;
  const rec = new sdk.SpeechRecognizer(cfg, sdk.AudioConfig.fromDefaultMicrophoneInput());
  let heard = false;
  let ended = false;
  const end = (p?: VoiceProblem) => {
    if (ended) return;
    ended = true;
    rec.close();
    h.onEnd(p);
  };
  rec.recognizing = (_s, e) => {
    if (!heard) {
      heard = true;
      h.onSpeech();
    }
    h.onPartial(e.result.text);
  };
  rec.recognizeOnceAsync(
    (r) => {
      if (r.reason === sdk.ResultReason.RecognizedSpeech && r.text) h.onFinal(r.text);
      end();
    },
    () => {
      resetVoiceToken();
      end("failed");
    },
  );
  return {
    stop() {
      if (ended) return;
      rec.stopContinuousRecognitionAsync(
        () => end(),
        () => end(),
      );
    },
  };
}
