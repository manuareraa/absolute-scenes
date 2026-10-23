// A short guided tour of the show screen: one group of the interface at a time, spotlit, with a
// card that says what it is for. It opens once per visitor, after the first moment has aired,
// and again from the header's "Tour" button.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Strings } from "./i18n";

export const TOUR_KEY = "chalktalk.tour";

export function tourSeen(): boolean {
  try {
    return localStorage.getItem(TOUR_KEY) !== null;
  } catch {
    return false;
  }
}

function markSeen() {
  try {
    localStorage.setItem(TOUR_KEY, "seen");
  } catch {
    // Private windows may refuse storage; the tour then just opens again next visit.
  }
}

export interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const GAP = 12;
const PAD = 6;

/** Where the card goes: under the target if it fits, else above, else over its lower edge; always inside the viewport. */
export function placeCard(target: Box, card: { width: number; height: number }, view: { width: number; height: number }): { top: number; left: number } {
  const below = target.top + target.height + PAD + GAP;
  const above = target.top - PAD - GAP - card.height;
  const top =
    below + card.height <= view.height - GAP ? below : above >= GAP ? above : Math.max(GAP, Math.min(target.top + target.height - card.height - GAP, view.height - card.height - GAP));
  const left = Math.max(GAP, Math.min(target.left + target.width / 2 - card.width / 2, view.width - card.width - GAP));
  return { top, left };
}

/** An element's box; a `display: contents` group (the header pickers) spans its children. */
function boxOf(el: Element): Box | null {
  const r = el.getBoundingClientRect();
  if (r.width > 0) return { top: r.top, left: r.left, width: r.width, height: r.height };
  const kids = [...el.children].map((k) => k.getBoundingClientRect()).filter((k) => k.width > 0);
  if (!kids.length) return null;
  const top = Math.min(...kids.map((k) => k.top));
  const left = Math.min(...kids.map((k) => k.left));
  return { top, left, width: Math.max(...kids.map((k) => k.right)) - left, height: Math.max(...kids.map((k) => k.bottom)) - top };
}

/** The first of `selectors` that is on screen with a size. */
function find(selectors: string[]): Element | null {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && boxOf(el)) return el;
  }
  return null;
}

export function Tour({ s, onClose }: { s: Strings; onClose(): void }) {
  const steps = s.tour.steps.filter((st) => find(st.at));
  const [i, setI] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const card = useRef<HTMLElement>(null);
  const step = steps[Math.min(i, steps.length - 1)];

  const close = () => {
    markSeen();
    onClose();
  };

  // Follow the target while the page lays out, scrolls or resizes.
  useLayoutEffect(() => {
    if (!step) return;
    find(step.at)?.scrollIntoView({ block: "nearest" });
    let raf = 0;
    const track = () => {
      // Look again each frame: a resize can swap the phone settings button for the pickers.
      const el = find(step.at);
      const b = el ? boxOf(el) : null;
      setBox((p) => (p && b && p.top === b.top && p.left === b.left && p.width === b.width && p.height === b.height ? p : b));
      const c = card.current?.getBoundingClientRect();
      if (b && c) {
        const next = placeCard(b, c, { width: innerWidth, height: innerHeight });
        setPos((p) => (p && p.top === next.top && p.left === next.left ? p : next));
      }
      raf = requestAnimationFrame(track);
    };
    track();
    return () => cancelAnimationFrame(raf);
  }, [step]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") setI((n) => Math.min(n + 1, steps.length - 1));
      else if (e.key === "ArrowLeft") setI((n) => Math.max(n - 1, 0));
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  if (!step) return null;
  const last = i >= steps.length - 1;
  return (
    <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-body">
      {box && (
        <div className="tour-spot" style={{ top: box.top - PAD, left: box.left - PAD, width: box.width + 2 * PAD, height: box.height + 2 * PAD }} />
      )}
      <section ref={card} className="tour-card" style={pos ?? { visibility: "hidden" }}>
        <p className="tour-count">{s.tour.count(i + 1, steps.length)}</p>
        <h2 id="tour-title">{step.title}</h2>
        <p id="tour-body">{step.body}</p>
        {step.link && (
          <a className="tour-link" href={step.link.href} target="_blank" rel="noopener">
            {step.link.label} ↗
          </a>
        )}
        <div className="tour-nav">
          <button className="tour-skip" onClick={close}>
            {last ? s.close : s.tour.skip}
          </button>
          <span className="tour-dots" aria-hidden>
            {steps.map((st, n) => (
              <i key={st.title} className={n === i ? "on" : ""} />
            ))}
          </span>
          {i > 0 && <button onClick={() => setI(i - 1)}>{s.tour.back}</button>}
          <button className="primary" onClick={() => (last ? close() : setI(i + 1))} autoFocus>
            {last ? s.tour.done : s.tour.next}
          </button>
        </div>
      </section>
    </div>
  );
}
