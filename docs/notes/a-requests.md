# Stream A requests and API notes

## Ghost players in the 3D view (for studio-ui's counterfactual ghosts)
`web/src/figures/Broadcast3D.tsx` takes an optional `ghosts` prop:

```ts
import type { Ghost3D } from "./figures/Broadcast3D";
// { id: string; x: number; y: number;            // pitch metres, same axes as Frame
//   team: "home" | "away"; heading?: number;     // degrees CCW from +x
//   label?: string }                              // a short standing tag, e.g. "#4 should be here"
<Broadcast3D ghosts={ghosts} ... />
```

Each ghost is a see-through lavender figure (the `--stroke-ghost` colour) with a ground ring; it walks with the same gait as real players if you move it frame to frame. `ghost_path` strokes already get a standing ghost automatically, so pass only extra counterfactual players. Keep the array reference stable when nothing changes (it is cheap either way).

## i18n (not my path, request only)
The view toggle reads "2D Board" / "3D". The brief calls the 2D view the **Analyst** view; please consider relabelling the toggle in `web/src/i18n.ts` (e.g. `"Analyst"` / `"Broadcast"`), since I may not edit `i18n.ts` in this stream.

## App.tsx (small wiring change, coordinate with studio-ui)
Three lines in `App.tsx`: `START_VIEW` defaults to 3D when WebGL2 exists, `show3d` no longer drops to 2D during an overlay, and `Broadcast3D` gets `overlay`, `audioMs`, `nameOf`, `onPick`. If studio-ui's PR lands first, the merge is these lines only.
