# Stream A: broadcast look (branch stream/a-broadcast-look)

## Decision: a stylised, premium 3D look, not a push for realism
I looked at the live site (2D board, studio show) and rendered the current 3D view locally against wrangler dev (`before-3d.png`; the Claude browser pane has no WebGL, so 3D shots come from headless Chromium with SwiftShader).

The current 3D reads as a toy: 23 stick figures a few pixels tall on a flat green slab floating in a black void, no shadows, no names, and the view cuts back to the 2D board the moment the pundit starts drawing.

I chose the **clean, flat-shaded style of top analysis tools** (virtual-replay and tracking-data graphics) over trying to make the current figures more realistic, because:
1. **Our data is synthetic.** Realistic figures invite the uncanny valley (gait glitches, faceless heads, sliding feet). A stylised figure makes no promise the sim can't keep, so it reads as deliberate.
2. **Analysis broadcasts already look like this.** When TV cuts to tactical analysis it shows clean figures, crisp lines and glowing telestrator strokes, not game-engine players. That is the register a pundit product should sit in.
3. **Performance.** Flat shading, baked textures and blob shadows keep 60 fps on a mid laptop with no shadow maps.
4. **One visual family with the 2D Analyst board.** Same kit colours, same numbers, same stroke colours.

## What it means in practice
- A high main-stand camera (TV angle) that follows the ball with easing; drag to orbit, wheel to zoom, double-click to return.
- Pitch: mowing stripes, a soft lighting falloff, crisp markings, goals with nets, a dark stadium bowl so the pitch never floats in a void.
- Players: rounded, flat-shaded figures in kit, soft blob shadows, a shirt number above each one, and a name tag on the player on the ball (and on "my player").
- Telestrator: the existing SVG overlay is projected onto the grass with a CSS `matrix3d` homography, so the stroke timing code is untouched; strokes get a glow.
- The 2D board stays as the Analyst view toggle.
