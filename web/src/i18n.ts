// UI chrome in the caption language. The captions themselves come from the crew per language;
// everything around them (labels, panels, fixture titles the crew left in English) is here.
import type { Moment } from "./summary";

const EN = {
  tagline:
    "ChalkTalk is an AI pundit that draws on a synthetic pitch: every line lands on the word that names it, and every number links back to the tracking tool that produced it.",
  welcomeTitle: "Welcome to ChalkTalk",
  watchShow: "Watch the studio show",
  watchShowHint: "A recorded analyst breakdown, from the away side",
  watchLive: "Watch live",
  watchLiveHint: "The live match, with pundit moments at their minute",
  howItWorks: "How it works",
  close: "Close",
  landing: {
    kicker: "AI football analysis for broadcast",
    backHome: "ChalkTalk home",
    title: "The pundit that draws as it talks.",
    lede: "ChalkTalk turns tracking data into a studio breakdown. An AI crew picks the moment, measures it with analytics tools, writes and voices a short script, and draws each line on the pitch at the exact word that names it. Every number links back to the tool call that measured it.",
    honest: "The match is simulated and shown as a tactics board, as the hackathon rules require: no real footage, clubs or players.",
    start: "Start here",
    featuresTitle: "What to look for",
    showMe: "Show me",
    features: [
      { key: "strokes", title: "Lines land on the word", body: "Arrows, zones and gaps appear on the word in the voice that names them, not before or after." },
      { key: "ghost", title: "Ghost runs", body: "The pundit draws the run a player should have made, next to the one they did." },
      { key: "var", title: "VAR offside line", body: "A provisional call, then the line drawn from the frame of the pass, then the decision." },
      { key: "evidence", title: "Tap any number", body: "Each figure opens the tool call behind it and replays the seconds it was measured from." },
      { key: "audiences", title: "One moment, many viewers", body: "Casual, analyst or newcomer; home, away or neutral; English or Spanish. Same facts, different script." },
      { key: "summary", title: "Half-time and catch-up", body: "What decided the half so far, with each deciding moment one tap from its replay." },
      { key: "live", title: "Live, with a producer", body: "Moments air at their minute on the live match; a producer approves or rejects each one before it airs." },
    ],
    builtTitle: "How it is built",
    built: [
      { name: "Director", body: "Microsoft Foundry agent that picks the moments worth a breakdown from match events." },
      { name: "Analyst", body: "Calls MCP analytics tools: xG, line gaps, pressing, pitch control, pass options, offside lines." },
      { name: "Pundit", body: "Writes the script around tool slots. The model never types a number or a coordinate." },
      { name: "Verifier", body: "Re-runs the tools and checks every claim before anything airs." },
      { name: "Azure AI Speech", body: "Voices the script and returns word timings, which cue each stroke." },
      { name: "Cloudflare", body: "One Worker and a Durable Object run the shared live clock and push moments to every viewer." },
    ],
    footer: "Built for the Microsoft \u201cInside the Game\u201d hackathon.",
  },
  how: [
    "A synthetic match runs on a shared live clock. All players, teams and data are generated.",
    "Tracking tools measure each moment: gaps, pressure, pitch control and offside lines.",
    "An AI crew writes a short script per audience, side and language. Every number in it comes from a tool call, and every drawing comes from tool geometry.",
    "A fact-check gate re-runs the tools; a producer approves what airs. Without a producer, the demo airs the checked moments on its own.",
    "On the studio show, tap any underlined number to replay the evidence it came from.",
  ],
  groups: { surface: "Surface", lens: "Audience", side: "Support", lang: "Language", view: "View" },
  groupHints: {
    surface: "Pick what to watch",
    lens: "Who the commentary is written for",
    side: "Which team the pundit supports",
    lang: "Caption and interface language",
    view: "Flat tactics board or 3D broadcast camera",
  },
  options: {
    broadcast: "Live",
    show: "Studio show",
    player: "Player",
    casual: "Casual",
    analyst: "Analyst",
    newcomer: "Newcomer",
    home: "Reds",
    away: "Blues",
    neutral: "Neutral",
    "2d": "2D board",
    "3d": "3D",
    "en-GB": "English",
    "es-ES": "Español",
  } as Record<string, string>,
  optionHints: {
    broadcast: "The live match on the shared clock",
    show: "The recorded post-match studio show, in chapters",
    player: "Player view",
    casual: "Plain words for a casual fan",
    analyst: "Numbers and shape for an analyst",
    newcomer: "Explains the basics for someone new to football",
    home: "Pundit supports the Reds",
    away: "Pundit supports the Blues",
    neutral: "Neutral pundit",
    "2d": "Top-down tactics board",
    "3d": "Broadcast camera; drag to orbit",
    "en-GB": "Captions in English",
    "es-ES": "Subtítulos en español",
  } as Record<string, string>,
  settings: "Settings",
  live: "● Live",
  liveHint: "Connected to the live match",
  fullTime: "Full time",
  recorded: "Recorded match",
  recordedHint: "The live match is unavailable; playing a recorded match",
  connecting: "Connecting…",
  nextMoment: (t: string) => `Next pundit moment at ${t}`,
  onAir: "On air",
  noMoreMoments: "No more pundit moments this match",
  tryShow: "Watch the studio show",
  chapters: "Chapters",
  decided: "The moments that decided it",
  tapNumber: "Tap a number to see its evidence",
  halfTime: "Half-time: the moments that decided it",
  catchUp: (t: string) => `Catch-up at ${t}: what you missed`,
  kinds: { goal: "goal", chance: "chance", card: "card", offside: "offside" } as Record<string, string>,
  stats: { shots: "Shots", onTarget: "On target", xg: "xG", possession: "Possession", passAccuracy: "Pass accuracy" },
  backToShow: "Back to the show",
  backToMoments: "Back to the moments",
  tapMoment: "Tap a moment to replay it.",
  replayMoment: "Replay this moment",
  replayEvidence: "Replay the evidence",
  showToolCall: "Show the tool call",
  replaying: (a: string, b: string) => `Replaying ${a}–${b}`,
  checks: {
    match: "We re-ran the tool and got the same number.",
    matchHash: "We re-ran the tool and got the same number and the same data hash.",
    differs: (v: string) => `We re-ran the tool and got ${v}.`,
    window: "This replays the window the number was measured in.",
  },
  claimSentence: (label: string, value: string) => `${cap(label)}: ${value}.`,
  pause: "Pause",
  play: "Play",
  scrub: "Seek through the show",
  soundOn: "Sound on",
  teams: { home: "Reds", away: "Blues" } as Record<string, string>,
  referee: "Referee",
  ball: "Ball",
  goal: "Goal",
  loading: "Loading…",
  upNext: "Up next",
  pitch: "Synthetic pitch view",
  broadcast3d: "Synthetic broadcast view; drag to orbit, scroll to zoom",
  slots: { gap: "gap", control: "control", press: "pressing", "pass options": "pass options", "pitch control": "pitch control", block: "block", margin: "margin" } as Record<string, string>,
  crewTitles: {} as Record<string, string>,
  var: { check: "VAR check · provisional", checking: "Checking", checkingFor: (r: string) => `Checking: ${r}`, onside: "Onside", offside: "Offside", decisions: { goal_stands: "Goal stands", goal_disallowed: "No goal" } as Record<string, string> },
  outcomes: {} as Record<string, string>,
  events: {} as Record<string, string>,
};

export type Strings = typeof EN;

const ES: Strings = {
  tagline:
    "ChalkTalk es un comentarista con IA que dibuja sobre un campo sintético: cada trazo cae en la palabra que lo nombra, y cada número enlaza con la herramienta de seguimiento que lo calculó.",
  welcomeTitle: "Bienvenido a ChalkTalk",
  watchShow: "Ver el programa de estudio",
  watchShowHint: "Un análisis grabado, desde el lado visitante",
  watchLive: "Ver en directo",
  watchLiveHint: "El partido en directo, con los momentos del comentarista en su minuto",
  howItWorks: "Cómo funciona",
  close: "Cerrar",
  landing: {
    kicker: "Análisis de fútbol con IA para televisión",
    backHome: "Inicio de ChalkTalk",
    title: "El comentarista que dibuja mientras habla.",
    lede: "ChalkTalk convierte datos de seguimiento en un análisis de estudio. Un equipo de IA elige la jugada, la mide con herramientas de análisis, escribe y pone voz a un guion breve, y dibuja cada línea en el campo justo en la palabra que la nombra. Cada número enlaza con la llamada a la herramienta que lo midió.",
    honest: "El partido es simulado y se muestra como una pizarra táctica, como exigen las reglas del hackathon: sin imágenes, clubes ni jugadores reales.",
    start: "Empieza aquí",
    featuresTitle: "Qué mirar",
    showMe: "Muéstramelo",
    features: [
      { key: "strokes", title: "Las líneas caen en la palabra", body: "Flechas, zonas y huecos aparecen en la palabra de la voz que los nombra, ni antes ni después." },
      { key: "ghost", title: "Carreras fantasma", body: "El comentarista dibuja la carrera que debió hacer un jugador, junto a la que hizo." },
      { key: "var", title: "Línea de fuera de juego del VAR", body: "Una decisión provisional, la línea trazada en el fotograma del pase y luego la decisión." },
      { key: "evidence", title: "Toca cualquier número", body: "Cada cifra abre la llamada a la herramienta que la midió y repite los segundos de los que sale." },
      { key: "audiences", title: "Una jugada, muchos públicos", body: "Casual, analista o principiante; local, visitante o neutral; inglés o español. Los mismos datos, otro guion." },
      { key: "summary", title: "Descanso y resumen", body: "Lo que ha decidido la parte hasta ahora, con cada jugada clave a un toque de su repetición." },
      { key: "live", title: "En directo, con productor", body: "Las jugadas se emiten en su minuto del partido en directo; un productor aprueba o rechaza cada una antes de emitirla." },
    ],
    builtTitle: "Cómo está hecho",
    built: [
      { name: "Director", body: "Agente de Microsoft Foundry que elige las jugadas que merecen un análisis a partir de los eventos del partido." },
      { name: "Analista", body: "Llama a herramientas de análisis MCP: xG, huecos entre líneas, presión, control del campo, opciones de pase, fuera de juego." },
      { name: "Comentarista", body: "Escribe el guion alrededor de huecos para las herramientas. El modelo nunca escribe un número ni una coordenada." },
      { name: "Verificador", body: "Vuelve a ejecutar las herramientas y comprueba cada dato antes de emitir." },
      { name: "Azure AI Speech", body: "Pone voz al guion y devuelve los tiempos de cada palabra, que marcan cada trazo." },
      { name: "Cloudflare", body: "Un Worker y un Durable Object llevan el reloj en directo compartido y envían las jugadas a cada espectador." },
    ],
    footer: "Hecho para el hackathon \u201cInside the Game\u201d de Microsoft.",
  },
  how: [
    "Un partido sintético se juega con un reloj en directo compartido. Jugadores, equipos y datos son generados.",
    "Las herramientas de seguimiento miden cada momento: huecos, presión, control del campo y líneas de fuera de juego.",
    "Un equipo de IA escribe un guion breve por público, equipo e idioma. Cada número sale de una llamada a una herramienta, y cada dibujo, de su geometría.",
    "Un control de datos vuelve a ejecutar las herramientas; un productor aprueba lo que se emite. Sin productor, la demo emite sola los momentos verificados.",
    "En el programa de estudio, toca un número subrayado para ver de nuevo la jugada de la que sale.",
  ],
  groups: { surface: "Pantalla", lens: "Público", side: "Afición", lang: "Idioma", view: "Vista" },
  groupHints: {
    surface: "Elige qué ver",
    lens: "Para quién se escribe el comentario",
    side: "Qué equipo apoya el comentarista",
    lang: "Idioma de subtítulos e interfaz",
    view: "Pizarra táctica plana o cámara de televisión en 3D",
  },
  options: {
    broadcast: "Directo",
    show: "Programa",
    player: "Reproductor",
    casual: "Aficionado",
    analyst: "Analista",
    newcomer: "Principiante",
    home: "Rojos",
    away: "Azules",
    neutral: "Neutral",
    "2d": "Pizarra 2D",
    "3d": "3D",
    "en-GB": "English",
    "es-ES": "Español",
  },
  optionHints: {
    broadcast: "El partido en directo con el reloj compartido",
    show: "El programa de estudio grabado, por capítulos",
    player: "Vista de reproductor",
    casual: "Palabras sencillas para el aficionado",
    analyst: "Números y estructura para el analista",
    newcomer: "Explica lo básico a quien empieza con el fútbol",
    home: "El comentarista apoya a los Rojos",
    away: "El comentarista apoya a los Azules",
    neutral: "Comentarista neutral",
    "2d": "Pizarra táctica vista desde arriba",
    "3d": "Cámara de televisión; arrastra para girar",
    "en-GB": "Captions in English",
    "es-ES": "Subtítulos en español",
  },
  settings: "Ajustes",
  live: "● Directo",
  liveHint: "Conectado al partido en directo",
  fullTime: "Final del partido",
  recorded: "Partido grabado",
  recordedHint: "El directo no está disponible; se reproduce un partido grabado",
  connecting: "Conectando…",
  nextMoment: (t) => `Próximo momento del comentarista: ${t}`,
  onAir: "En antena",
  noMoreMoments: "No hay más momentos del comentarista en este partido",
  tryShow: "Ver el programa de estudio",
  chapters: "Capítulos",
  decided: "Los momentos que lo decidieron",
  tapNumber: "Toca un número para ver de dónde sale",
  halfTime: "Descanso: los momentos que lo decidieron",
  catchUp: (t) => `Resumen al ${t}: lo que te perdiste`,
  kinds: { goal: "gol", chance: "ocasión", card: "tarjeta", offside: "fuera de juego" },
  stats: { shots: "Tiros", onTarget: "A puerta", xg: "xG", possession: "Posesión", passAccuracy: "Precisión de pase" },
  backToShow: "Volver al programa",
  backToMoments: "Volver a los momentos",
  tapMoment: "Toca un momento para verlo de nuevo.",
  replayMoment: "Ver de nuevo este momento",
  replayEvidence: "Ver de dónde sale",
  showToolCall: "Ver la llamada a la herramienta",
  replaying: (a, b) => `Repetición ${a}–${b}`,
  checks: {
    match: "Volvimos a ejecutar la herramienta y dio el mismo número.",
    matchHash: "Volvimos a ejecutar la herramienta: mismo número y mismo hash de datos.",
    differs: (v) => `Volvimos a ejecutar la herramienta y dio ${v}.`,
    window: "Esto repite el intervalo en el que se midió el número.",
  },
  claimSentence: (label, value) => `${cap(label)}: ${value}.`,
  pause: "Pausa",
  play: "Reproducir",
  scrub: "Avanzar o retroceder en el programa",
  soundOn: "Activar sonido",
  teams: { home: "Rojos", away: "Azules" },
  referee: "Árbitro",
  ball: "Balón",
  goal: "Gol",
  loading: "Cargando…",
  upNext: "A continuación",
  pitch: "Vista del campo sintético",
  broadcast3d: "Vista de televisión sintética; arrastra para girar, rueda para acercar",
  slots: { gap: "hueco", control: "control", press: "presión", "pass options": "opciones de pase", "pitch control": "control del campo", block: "bloque", margin: "margen" },
  crewTitles: { "The chance": "La ocasión", "The gap between the lines": "El hueco entre líneas", "Where they should have been": "Dónde debía estar", "VAR check: offside?": "Revisión del VAR: ¿fuera de juego?" },
  var: { check: "Revisión del VAR · provisional", checking: "Revisando", checkingFor: (r) => `Revisando: ${r}`, onside: "En posición legal", offside: "Fuera de juego", decisions: { goal_stands: "Gol válido", goal_disallowed: "Gol anulado" } },
  outcomes: { saved: "parada", blocked: "bloqueado", wide: "fuera", post: "al palo", goal: "gol" },
  events: { pass: "pase", carry: "conducción", goal: "gol", free_kick: "tiro libre", shot: "tiro", tackle: "entrada", press: "presión", foul: "falta", interception: "intercepción", offside: "fuera de juego", card: "tarjeta" },
};

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const tr = (lang: string): Strings => (lang === "es-ES" ? ES : EN);

/** Number in the locale's own format: 11.66 -> "11.7" / "11,7". */
// Small values keep two decimals, so 0.03 xG does not read as "0 xG".
export const num = (v: unknown, lang: string) =>
  typeof v === "number" ? v.toLocaleString(lang, { maximumFractionDigits: Math.abs(v) < 1 ? 2 : 1 }) : String(v);

const clockOf = (ms: number) => {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

/**
 * A chapter's title: its match time as mm:ss, then the crew title without its "2' · " minute
 * prefix, translated. Titles that repeat in a show get their first measured number added, so
 * four "The gap between the lines" chapters read apart.
 */
export function chapterTitles(chapters: { title: string; overlay: { match_tc: number; claims: { value: unknown; unit?: string | null }[] } }[], lang: string): string[] {
  const s = tr(lang);
  const bases = chapters.map((c) => {
    const base = c.title.replace(/^\d+'\s*·\s*/, "").trim();
    return s.crewTitles[base] ?? base;
  });
  return chapters.map((c, i) => {
    const repeated = bases.filter((b) => b === bases[i]).length > 1;
    const first = c.overlay.claims.find((k) => typeof k.value === "number");
    const extra = repeated && first ? `: ${num(first.value, lang)}${first.unit ? ` ${first.unit}` : ""}` : "";
    return `${clockOf(c.overlay.match_tc)} · ${bases[i]}${extra}`;
  });
}

/** The crew's slot as words in the UI language: `pc_pts` -> "pitch control". */
export function slotWords(label: string, lang: string): string {
  return tr(lang).slots[label] ?? label;
}

/**
 * A summary moment's headline. The fixture's are English ("Goal, home: 1-0 (VAR: goal stands)");
 * they are rebuilt from the moment's fields so team names and language match the UI.
 */
export function momentHeadline(m: Moment, lang: string): string {
  const s = tr(lang);
  const team = s.teams[m.team] ?? m.team;
  const kind = s.kinds[m.kind] ?? m.kind;
  const head = `${cap(kind)}, ${team}`;
  if (m.kind === "goal" && m.score_after) {
    const v = m.var ? ` (VAR: ${(s.var.decisions[m.var.decision] ?? m.var.decision.replaceAll("_", " ")).toLowerCase()})` : "";
    return `${head}: ${m.score_after.home}-${m.score_after.away}${v}`;
  }
  if (m.kind === "chance" && typeof m.xg === "number") {
    const out = /,\s*([a-z ]+)$/.exec(m.headline)?.[1];
    return `${head}: xG ${m.xg.toLocaleString(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${out ? `, ${s.outcomes[out] ?? out}` : ""}`;
  }
  return lang === "es-ES" ? head : m.headline.replace(/\bhome\b/, s.teams.home).replace(/\baway\b/, s.teams.away);
}
