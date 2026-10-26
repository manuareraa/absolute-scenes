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
    lede: "ChalkTalk turns tracking data into a studio breakdown. An AI crew picks the moment, measures it with analytics tools, writes and voices a short script, and draws each line on the pitch at the exact word that names it. Every number links back to the tool call that measured it. Ask it about any moment, by typing or out loud, and it answers by drawing.",
    honest: "The match is simulated and shown as a tactics board, as the hackathon rules require: no real footage, clubs or players.",
    start: "Start here",
    featuresTitle: "What to look for",
    showMe: "Show me",
    features: [
      { key: "strokes", title: "Lines land on the word", body: "Arrows, zones and gaps appear on the word in the voice that names them, not before or after." },
      { key: "ask", title: "Ask the pundit", body: "Type or say a question about the moment. A live crew on Azure measures it, a Verifier checks every number, and the answer is drawn on the pitch as it is spoken." },
      { key: "whatif", title: "What should they have done?", body: "A Tactician proposes a change, the simulation re-runs it, and a Critic rejects it unless the numbers improve. You see both." },
      { key: "ghost", title: "Ghost runs", body: "The pundit draws the run a player should have made, next to the one they did." },
      { key: "var", title: "VAR offside line", body: "A provisional call, then the line drawn from the frame of the pass, then the decision." },
      { key: "evidence", title: "Tap any number", body: "Each figure opens the tool call behind it and replays the seconds it was measured from." },
      { key: "audiences", title: "One moment, many viewers", body: "Casual, analyst or newcomer; home, away or neutral; English or Spanish. Same facts, different script." },
      { key: "summary", title: "Half-time and catch-up", body: "What decided the half so far, with each deciding moment one tap from its replay." },
      { key: "live", title: "Live, with a producer", body: "Moments air at their minute on the live match; a producer approves or rejects each one before it airs." },
    ],
    measuredTitle: "Measured, not claimed",
    measured: [
      { value: "10 ms", label: "median gap between a stroke and the word that names it (33 strokes)" },
      { value: "4.62 / 5", label: "groundedness of 77 live answers, judged by a Foundry evaluator" },
      { value: "8 of 156", label: "first-round claims the Verifier rejected and sent back for a rewrite" },
      { value: "6 of 34", label: "what-if proposals the Critic kept; the rest did not improve the numbers" },
      { value: "6 of 6", label: "attack questions that ended safely (Prompt Shields or the Pundit declined)" },
      { value: "12.5 s", label: "median time to a drawn, spoken answer, at about $0.002 each" },
    ],
    measuredNote: "From the live ask eval of 25 October 2026: 78 football questions in English and Spanish, plus 6 attacks. Method and raw results are in the repository.",
    builtTitle: "How it is built",
    built: [
      { name: "Director", body: "Microsoft Foundry agent that picks the moments worth a breakdown from match events." },
      { name: "Analyst", body: "Calls MCP analytics tools: xG, line gaps, pressing, pitch control, pass options, offside lines." },
      { name: "Pundit", body: "Writes the script around tool slots. The model never types a number or a coordinate." },
      { name: "Verifier", body: "Re-runs the tools and checks every claim before anything airs." },
      { name: "Azure AI Speech", body: "Voices the script and returns word timings, which cue each stroke." },
      { name: "Tactician and Critic", body: "For “what should they have done?”: one agent proposes a change, the simulation re-runs it, the other keeps it only if the numbers improve." },
      { name: "Azure Container Apps", body: "Runs the live ask crew, scales to zero, and reaches Foundry with a managed identity, no keys in code." },
      { name: "Azure AI Content Safety", body: "Prompt Shields screen every typed or spoken question before an agent sees it." },
      { name: "Cloudflare", body: "One Worker and a Durable Object run the shared live clock, rate-limit questions and push moments to every viewer." },
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
  tour: {
    button: "Tour",
    count: (n: number, of: number) => `Step ${n} of ${of}`,
    next: "Next",
    back: "Back",
    skip: "Skip tour",
    done: "Done",
    steps: [
      {
        at: [".screen"],
        title: "The pundit's board",
        body: "Every chalk line lands on the word that names it, and the caption follows the voice. The shapes come from the tracking tools, not from the AI.",
      },
      {
        at: [".chapters"],
        title: "Chapters and evidence",
        body: "Jump to any moment of the match. Tap an underlined number, here or in the caption, to replay the tracking evidence behind it.",
      },
      {
        at: [".viewer-bar"],
        title: "Catch me up and My player",
        body: "Missed a bit? Catch me up opens the latest summary of the match so far. Tap a player, or pick one in Settings, to follow them: a ring and their name on the pitch, a stats line here, and a dot on every chapter they feature in.",
      },
      {
        at: [".settings-toggle", "#controls"],
        title: "Make it yours",
        body: "Pick the surface, the audience (newcomer, casual or analyst), the side the pundit supports, the language, and a flat or 3D view. The script is written for each pick.",
      },
      {
        at: [".transport"],
        title: "Play and scrub",
        body: "Pause the show, or drag through all of its chapters.",
      },
      {
        at: [".settings-toggle", "#controls > :first-child"],
        title: "Live match and producer",
        body: "Pick Live to follow the match on its shared clock. In the producer console, approve or reject each moment before it airs.",
        link: { href: "/producer", label: "Open the producer console" },
      },
    ] as TourStep[],
  },
  groups: { surface: "Surface", lens: "Audience", side: "Support", lang: "Language", view: "View", player: "My player" },
  groupHints: {
    surface: "Pick what to watch",
    lens: "Who the commentary is written for",
    side: "Which team the pundit supports",
    lang: "Caption and interface language",
    view: "Flat tactics board or 3D broadcast camera",
    player: "Follow one player: a ring and name on the pitch, and a stats line under it",
  },
  options: {
    broadcast: "Live",
    show: "Studio show",
    player: "Player",
    casual: "Casual",
    analyst: "Analyst",
    newcomer: "Newcomer",
    home: "Northbridge",
    away: "Saltmere",
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
    home: "Pundit supports Northbridge Rovers (blue)",
    away: "Pundit supports Saltmere Athletic (red)",
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
  onAirAuto: "On air · auto-pilot: fact-checked, no producer on shift",
  noMoreMoments: "No more pundit moments this match",
  tryShow: "Watch the studio show",
  chapters: "Chapters",
  decided: "The moments that decided it",
  tapNumber: "Tap a number to see its evidence",
  halfTime: "Half-time: the moments that decided it",
  catchUp: (t: string) => `Catch-up at ${t}: what you missed`,
  catchMeUp: "Catch me up",
  catchMeUpHint: "Open the latest summary of what you missed (key C)",
  catchUpNotYet: (t: string) => `Nothing to catch up on yet: the first summary is at ${t}.`,
  catchUpNone: "This match has no summary to catch up on.",
  me: {
    nobody: "Nobody",
    follow: "Tap a player on the board, or pick one in Settings, to follow them.",
    stop: "Stop following",
    km: (v: string) => `${v} km`,
    m: (v: string) => `${v} m`,
    sprints: (n: number) => (n === 1 ? "1 sprint" : `${n} sprints`),
    top: (v: string) => `top ${v} km/h`,
    touches: (n: number) => (n === 1 ? "1 touch" : `${n} touches`),
    last: (what: string, t: string) => `last: ${what} ${t}`,
    seen: (t: string) => `from ${t} of tracking seen`,
    noTouches: "touches: needs the full event list, which this recording does not carry",
    noLast: "last action: no events in this data",
    notHere: "not in this match's data",
    hint: "Distance and sprints are counted from the tracking frames this screen has received. A sprint is 25.2 km/h or faster held for at least a second. The recorded show carries only the seconds around each moment; live counts from when you joined.",
    inChapter: "Your player is in this breakdown",
  },
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
    match: "Checked when the show was built: re-running the tool gave the same number.",
    matchHash: "Checked when the show was built: re-running the tool gave the same number and the same data hash.",
    differs: (v: string) => `Checked when the show was built: re-running the tool gave ${v}.`,
    window: "This replays the window the number was measured in.",
  },
  claimSentence: (label: string, value: string) => `${cap(label)}: ${value}.`,
  pause: "Pause",
  play: "Play",
  scrub: "Seek through the show",
  soundOn: "Sound on",
  /** The sim's fictional clubs (sim/teams.py); names stay the same in every language. */
  teams: { home: "Northbridge", away: "Saltmere" } as Record<string, string>,
  /** Three-letter codes for the score bug. */
  teamCodes: { home: "NBR", away: "SAL" },
  momentum: {
    xg: "Chances (xG)",
    shots: "Shots",
    hint: (metric: "xg" | "shots"): string =>
      metric === "xg"
        ? "Each bar is one minute: the expected goals (xG) of a side's shots. Northbridge above the line, Saltmere below. Only shots with a recorded time are shown."
        : "Each bar is one minute: a side's shots. Northbridge above the line, Saltmere below.",
  },
  referee: "Referee",
  ball: "Ball",
  goal: "Goal",
  loading: "Loading…",
  upNext: "Up next",
  replayAt: (t: string) => `Replay ${t}`,
  pitch: "Synthetic pitch view",
  broadcast3d: "Synthetic broadcast view; drag to orbit, scroll to zoom",
  slots: { gap: "gap", control: "control", press: "pressing", "pass options": "pass options", "pitch control": "pitch control", block: "block", margin: "margin", xg: "chance" } as Record<string, string>,
  units: { points: "points" } as Record<string, string>,
  crewTitles: {} as Record<string, string>,
  var: { check: "VAR check · provisional", checking: "Checking", checkingFor: (r: string) => `Checking: ${r}`, onside: "Onside", offside: "Offside", decisions: { goal_stands: "Goal stands", goal_disallowed: "No goal" } as Record<string, string> },
  outcomes: {} as Record<string, string>,
  events: {} as Record<string, string>,
  ask: {
    title: "Ask the pundit",
    placeholder: "Ask about this moment…",
    send: "Ask",
    pauses: "Asking pauses the show",
    suggestions: {
      counterfactual: "What should they have done?",
      space: "Why was there so much space?",
      chance: "Was that a good chance?",
      offside: "Was it really offside?",
      press: "Was the press working?",
      key_player: "Who made the difference here?",
    } as Record<string, string>,
    mic: "Ask out loud",
    listening: "Listening…",
    micOff: "Voice isn't available here, so type your question",
    micDenied: "The microphone is blocked, so type your question",
    stop: "Stop",
    back: "Back to the show",
    youAsked: "You asked",
    controlRoom: "Control room",
    live: "Live crew",
    rehearsal: "Rehearsal",
    rehearsalHint: "The live crew isn't connected, so a recorded run plays: same events, same checks.",
    standby: "Standing by",
    onAir: "On air",
    working: (who: string) => `${who} working`,
    agents: { director: "Director", analyst: "Analyst", tactician: "Tactician", critic: "Critic", pundit: "Pundit", verifier: "Fact check", safety: "Safety" } as Record<string, string>,
    ran: "ran",
    rejected: "Rejected",
    approved: "Checked",
    round: (n: number) => `Round ${n}`,
    handoff: {
      label: (from: string, to: string) => `${from} → ${to}`,
      measured: (n: number) => (n === 1 ? "1 measurement" : `${n} measurements`),
      checked: (n: number) => (n === 1 ? "1 claim checked" : `${n} claims checked`),
      sentBack: (n: number) => (n === 1 ? "1 claim sent back" : `${n} claims sent back`),
      proposal: "a proposal to test",
      draft: "a draft",
      kept: "proposal kept",
      dropped: "proposal dropped",
    },
    tried: "Tried",
    helps: "Tools say it helps",
    noHelp: "Tools say it doesn't help",
    before: "before",
    after: "after",
    cached: "From the cache",
    trace: "Trace",
    traceTitle: "OpenTelemetry trace id in Application Insights and Foundry tracing",
    refusals: {
      rehearsal: "Rehearsal answers exist only for the suggested questions. The live crew answers anything about the match.",
      default: "The pundit only answers questions about this match.",
    } as Record<string, string>,
    errors: {
      busy: "The studio is busy. Try again in a minute.",
      off: "Live questions are switched off right now.",
      default: "The answer didn't come through. Try again.",
    } as Record<string, string>,
    metrics: { gap_m: "gap to slot", pc_pts: "pitch control", line_gap_m: "line gap", xg: "chance (xG)", pitch_control_box: "box control" } as Record<string, string>,
  },
};

export type Strings = typeof EN;

/** A tour step spotlights the first of `at` (CSS selectors) that is on screen; the phone-only settings button comes first. */
export interface TourStep {
  at: string[];
  title: string;
  body: string;
  link?: { href: string; label: string };
}

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
    lede: "ChalkTalk convierte datos de seguimiento en un análisis de estudio. Un equipo de IA elige la jugada, la mide con herramientas de análisis, escribe y pone voz a un guion breve, y dibuja cada línea en el campo justo en la palabra que la nombra. Cada número enlaza con la llamada a la herramienta que lo midió. Pregúntale por cualquier jugada, escribiendo o en voz alta, y responde dibujando.",
    honest: "El partido es simulado y se muestra como una pizarra táctica, como exigen las reglas del hackathon: sin imágenes, clubes ni jugadores reales.",
    start: "Empieza aquí",
    featuresTitle: "Qué mirar",
    showMe: "Muéstramelo",
    features: [
      { key: "strokes", title: "Las líneas caen en la palabra", body: "Flechas, zonas y huecos aparecen en la palabra de la voz que los nombra, ni antes ni después." },
      { key: "ask", title: "Pregunta al comentarista", body: "Escribe o di una pregunta sobre la jugada. Un equipo en directo en Azure la mide, un Verificador comprueba cada número y la respuesta se dibuja en el campo mientras se dice." },
      { key: "whatif", title: "¿Qué debieron hacer?", body: "Un Táctico propone un cambio, la simulación lo vuelve a jugar y un Crítico lo rechaza salvo que mejoren los números. Ves las dos cosas." },
      { key: "ghost", title: "Carreras fantasma", body: "El comentarista dibuja la carrera que debió hacer un jugador, junto a la que hizo." },
      { key: "var", title: "Línea de fuera de juego del VAR", body: "Una decisión provisional, la línea trazada en el fotograma del pase y luego la decisión." },
      { key: "evidence", title: "Toca cualquier número", body: "Cada cifra abre la llamada a la herramienta que la midió y repite los segundos de los que sale." },
      { key: "audiences", title: "Una jugada, muchos públicos", body: "Casual, analista o principiante; local, visitante o neutral; inglés o español. Los mismos datos, otro guion." },
      { key: "summary", title: "Descanso y resumen", body: "Lo que ha decidido la parte hasta ahora, con cada jugada clave a un toque de su repetición." },
      { key: "live", title: "En directo, con productor", body: "Las jugadas se emiten en su minuto del partido en directo; un productor aprueba o rechaza cada una antes de emitirla." },
    ],
    measuredTitle: "Medido, no prometido",
    measured: [
      { value: "10 ms", label: "diferencia mediana entre un trazo y la palabra que lo nombra (33 trazos)" },
      { value: "4,62 / 5", label: "fundamentación de 77 respuestas en directo, según un evaluador de Foundry" },
      { value: "8 de 156", label: "datos de la primera ronda que el Verificador rechazó y mandó reescribir" },
      { value: "6 de 34", label: "propuestas que el Crítico aceptó; las demás no mejoraban los números" },
      { value: "6 de 6", label: "preguntas de ataque que acabaron sin daño (Prompt Shields o el Comentarista se negó)" },
      { value: "12,5 s", label: "tiempo mediano hasta una respuesta dibujada y hablada, por unos 0,002 $ cada una" },
    ],
    measuredNote: "De la evaluación en directo del 25 de octubre de 2026: 78 preguntas de fútbol en inglés y español, más 6 ataques. El método y los resultados están en el repositorio.",
    builtTitle: "Cómo está hecho",
    built: [
      { name: "Director", body: "Agente de Microsoft Foundry que elige las jugadas que merecen un análisis a partir de los eventos del partido." },
      { name: "Analista", body: "Llama a herramientas de análisis MCP: xG, huecos entre líneas, presión, control del campo, opciones de pase, fuera de juego." },
      { name: "Comentarista", body: "Escribe el guion alrededor de huecos para las herramientas. El modelo nunca escribe un número ni una coordenada." },
      { name: "Verificador", body: "Vuelve a ejecutar las herramientas y comprueba cada dato antes de emitir." },
      { name: "Azure AI Speech", body: "Pone voz al guion y devuelve los tiempos de cada palabra, que marcan cada trazo." },
      { name: "Táctico y Crítico", body: "Para “¿qué debieron hacer?”: un agente propone un cambio, la simulación lo vuelve a jugar y el otro solo lo acepta si mejoran los números." },
      { name: "Azure Container Apps", body: "Ejecuta el equipo de preguntas en directo, escala a cero y llega a Foundry con una identidad administrada, sin claves en el código." },
      { name: "Azure AI Content Safety", body: "Prompt Shields revisa cada pregunta escrita o hablada antes de que la vea un agente." },
      { name: "Cloudflare", body: "Un Worker y un Durable Object llevan el reloj en directo compartido, limitan las preguntas y envían las jugadas a cada espectador." },
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
  tour: {
    button: "Guía",
    count: (n: number, of: number) => `Paso ${n} de ${of}`,
    next: "Siguiente",
    back: "Atrás",
    skip: "Saltar guía",
    done: "Hecho",
    steps: [
      {
        at: [".screen"],
        title: "La pizarra del comentarista",
        body: "Cada trazo cae en la palabra que lo nombra, y el subtítulo sigue a la voz. Las formas salen de las herramientas de seguimiento, no de la IA.",
      },
      {
        at: [".chapters"],
        title: "Capítulos y pruebas",
        body: "Salta a cualquier momento del partido. Toca un número subrayado, aquí o en el subtítulo, para ver de nuevo la jugada de la que sale.",
      },
      {
        at: [".viewer-bar"],
        title: "Ponme al día y Mi jugador",
        body: "¿Te perdiste algo? «Ponme al día» abre el último resumen del partido hasta ahora. Toca a un jugador, o elígelo en Ajustes, para seguirlo: un aro y su nombre en el campo, una línea de datos aquí y un punto en cada capítulo en el que aparece.",
      },
      {
        at: [".settings-toggle", "#controls"],
        title: "A tu medida",
        body: "Elige la pantalla, el público (principiante, aficionado o analista), el equipo que apoya el comentarista, el idioma y la vista plana o en 3D. El guion se escribe para cada opción.",
      },
      {
        at: [".transport"],
        title: "Reproducir y avanzar",
        body: "Pausa el programa o arrastra para recorrer todos sus capítulos.",
      },
      {
        at: [".settings-toggle", "#controls > :first-child"],
        title: "Partido en directo y productor",
        body: "Elige Directo para seguir el partido con su reloj compartido. En la consola del productor, aprueba o rechaza cada momento antes de que se emita.",
        link: { href: "/producer", label: "Abrir la consola del productor" },
      },
    ],
  },
  groups: { surface: "Pantalla", lens: "Público", side: "Afición", lang: "Idioma", view: "Vista", player: "Mi jugador" },
  groupHints: {
    surface: "Elige qué ver",
    lens: "Para quién se escribe el comentario",
    side: "Qué equipo apoya el comentarista",
    lang: "Idioma de subtítulos e interfaz",
    view: "Pizarra táctica plana o cámara de televisión en 3D",
    player: "Sigue a un jugador: un aro y su nombre en el campo, y una línea de datos debajo",
  },
  options: {
    broadcast: "Directo",
    show: "Programa",
    player: "Reproductor",
    casual: "Aficionado",
    analyst: "Analista",
    newcomer: "Principiante",
    home: "Northbridge",
    away: "Saltmere",
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
    home: "El comentarista apoya al Northbridge Rovers (azul)",
    away: "El comentarista apoya al Saltmere Athletic (rojo)",
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
  onAirAuto: "En antena · piloto automático: verificado, sin productor de turno",
  noMoreMoments: "No hay más momentos del comentarista en este partido",
  tryShow: "Ver el programa de estudio",
  chapters: "Capítulos",
  decided: "Los momentos que lo decidieron",
  tapNumber: "Toca un número para ver de dónde sale",
  halfTime: "Descanso: los momentos que lo decidieron",
  catchUp: (t) => `Resumen al ${t}: lo que te perdiste`,
  catchMeUp: "Ponme al día",
  catchMeUpHint: "Abre el último resumen de lo que te perdiste (tecla C)",
  catchUpNotYet: (t) => `Aún no hay nada que resumir: el primer resumen llega al ${t}.`,
  catchUpNone: "Este partido no tiene resumen para ponerte al día.",
  me: {
    nobody: "Nadie",
    follow: "Toca a un jugador en la pizarra, o elígelo en Ajustes, para seguirlo.",
    stop: "Dejar de seguir",
    km: (v) => `${v} km`,
    m: (v) => `${v} m`,
    sprints: (n) => (n === 1 ? "1 sprint" : `${n} sprints`),
    top: (v) => `máx. ${v} km/h`,
    touches: (n) => (n === 1 ? "1 toque" : `${n} toques`),
    last: (what, t) => `última: ${what} ${t}`,
    seen: (t) => `con ${t} de seguimiento visto`,
    noTouches: "toques: hace falta la lista completa de eventos, que esta grabación no trae",
    noLast: "última acción: no hay eventos en estos datos",
    notHere: "no está en los datos de este partido",
    hint: "La distancia y los sprints se cuentan con los fotogramas de seguimiento que ha recibido esta pantalla. Un sprint es ir a 25,2 km/h o más durante al menos un segundo. El programa grabado solo trae los segundos alrededor de cada momento; el directo cuenta desde que entraste.",
    inChapter: "Tu jugador está en este análisis",
  },
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
    match: "Comprobado al crear el programa: al volver a ejecutar la herramienta dio el mismo número.",
    matchHash: "Comprobado al crear el programa: al volver a ejecutar la herramienta, mismo número y mismo hash de datos.",
    differs: (v) => `Comprobado al crear el programa: al volver a ejecutar la herramienta dio ${v}.`,
    window: "Esto repite el intervalo en el que se midió el número.",
  },
  claimSentence: (label, value) => `${cap(label)}: ${value}.`,
  pause: "Pausa",
  play: "Reproducir",
  scrub: "Avanzar o retroceder en el programa",
  soundOn: "Activar sonido",
  teams: { home: "Northbridge", away: "Saltmere" },
  teamCodes: { home: "NBR", away: "SAL" },
  momentum: {
    xg: "Ocasiones (xG)",
    shots: "Tiros",
    hint: (metric) =>
      metric === "xg"
        ? "Cada barra es un minuto: los goles esperados (xG) de los tiros de un equipo. Northbridge arriba de la línea, Saltmere abajo. Solo se muestran los tiros con hora registrada."
        : "Cada barra es un minuto: los tiros de un equipo. Northbridge arriba de la línea, Saltmere abajo.",
  },
  referee: "Árbitro",
  ball: "Balón",
  goal: "Gol",
  loading: "Cargando…",
  upNext: "A continuación",
  replayAt: (t) => `Repetición ${t}`,
  pitch: "Vista del campo sintético",
  broadcast3d: "Vista de televisión sintética; arrastra para girar, rueda para acercar",
  slots: { gap: "hueco", control: "control", press: "presión", "pass options": "opciones de pase", "pitch control": "control del campo", block: "bloque", margin: "margen", xg: "ocasión" },
  units: { points: "puntos" },
  crewTitles: { "The chance": "La ocasión", Goal: "Gol", "The gap between the lines": "El hueco entre líneas", "Where they should have been": "Dónde debía estar", "VAR check: offside?": "Revisión del VAR: ¿fuera de juego?" },
  var: { check: "Revisión del VAR · provisional", checking: "Revisando", checkingFor: (r) => `Revisando: ${r}`, onside: "En posición legal", offside: "Fuera de juego", decisions: { goal_stands: "Gol válido", goal_disallowed: "Gol anulado" } },
  outcomes: { saved: "parada", blocked: "bloqueado", wide: "fuera", post: "al palo", goal: "gol" },
  events: { pass: "pase", carry: "conducción", dribble: "regate", save: "parada", clearance: "despeje", goal: "gol", free_kick: "tiro libre", shot: "tiro", tackle: "entrada", press: "presión", foul: "falta", interception: "intercepción", offside: "fuera de juego", card: "tarjeta" },
  ask: {
    title: "Pregunta al comentarista",
    placeholder: "Pregunta sobre esta jugada…",
    send: "Preguntar",
    pauses: "Preguntar pausa el programa",
    suggestions: {
      counterfactual: "¿Qué debieron hacer?",
      space: "¿Por qué había tanto espacio?",
      chance: "¿Era una buena ocasión?",
      offside: "¿De verdad era fuera de juego?",
      press: "¿Funcionaba la presión?",
      key_player: "¿Quién marcó la diferencia aquí?",
    },
    mic: "Preguntar en voz alta",
    listening: "Escuchando…",
    micOff: "La voz no está disponible aquí: escribe tu pregunta",
    micDenied: "El micrófono está bloqueado: escribe tu pregunta",
    stop: "Parar",
    back: "Volver al programa",
    youAsked: "Has preguntado",
    controlRoom: "Sala de control",
    live: "Equipo en directo",
    rehearsal: "Ensayo",
    rehearsalHint: "El equipo en directo no está conectado, así que se reproduce una sesión grabada: mismos pasos, mismas comprobaciones.",
    standby: "En espera",
    onAir: "En el aire",
    working: (who) => `${who} trabajando`,
    agents: { director: "Realizador", analyst: "Analista", tactician: "Táctico", critic: "Crítico", pundit: "Comentarista", verifier: "Verificación", safety: "Seguridad" },
    ran: "ejecutó",
    rejected: "Rechazado",
    approved: "Comprobado",
    round: (n) => `Ronda ${n}`,
    handoff: {
      label: (from, to) => `${from} → ${to}`,
      measured: (n) => (n === 1 ? "1 medición" : `${n} mediciones`),
      checked: (n) => (n === 1 ? "1 afirmación comprobada" : `${n} afirmaciones comprobadas`),
      sentBack: (n) => (n === 1 ? "1 afirmación devuelta" : `${n} afirmaciones devueltas`),
      proposal: "una propuesta para probar",
      draft: "un borrador",
      kept: "propuesta aceptada",
      dropped: "propuesta descartada",
    },
    tried: "Probado",
    helps: "Las herramientas dicen que ayuda",
    noHelp: "Las herramientas dicen que no ayuda",
    before: "antes",
    after: "después",
    cached: "Desde la caché",
    trace: "Traza",
    traceTitle: "Id de la traza OpenTelemetry en Application Insights y el seguimiento de Foundry",
    refusals: {
      rehearsal: "En el ensayo solo hay respuestas para las preguntas sugeridas. El equipo en directo responde cualquier cosa sobre el partido.",
      default: "El comentarista solo responde preguntas sobre este partido.",
    },
    errors: {
      busy: "El estudio está ocupado. Inténtalo dentro de un minuto.",
      off: "Las preguntas en directo están desactivadas ahora mismo.",
      default: "La respuesta no ha llegado. Inténtalo de nuevo.",
    },
    metrics: { gap_m: "distancia a su sitio", pc_pts: "control del campo", line_gap_m: "hueco entre líneas", xg: "ocasión (xG)", pitch_control_box: "control del área" },
  },
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
    const extra = repeated && first ? `: ${num(first.value, lang)}${first.unit ? ` ${s.units[first.unit] ?? first.unit}` : ""}` : "";
    return `${clockOf(c.overlay.match_tc)} · ${bases[i]}${extra}`;
  });
}

/** The crew's slot as words in the UI language: `pc_pts` -> "pitch control". */
export function slotWords(label: string, lang: string): string {
  return tr(lang).slots[label] ?? label;
}

/** A claim's unit in the UI language: "points" is a word; m, %, xG stay as they are. */
export function unitWord(unit: string | null | undefined, lang: string): string {
  return unit ? (tr(lang).units[unit] ?? unit) : "";
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
