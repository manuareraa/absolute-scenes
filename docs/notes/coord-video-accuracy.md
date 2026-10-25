# Demo video accuracy review (coordinator)

We checked the demo video frame by frame (1 fps frames plus speech-to-text of the audio) against the tools.

## What was already right
- **The voice matches the scripts.**
- **Every spoken number matches its tool call:**
  - xG 0.02, 0.01 and 0.04.
  - Gaps 7.36, 13.31 and 8.55 m.
  - Ghost drift 6.27 m.
  - VAR margin 4.93 m.
- **All 22 players and the referee are in every frame.**

## What was wrong, and the fix
1. **The VAR chapter showed the shot, while the voice said "at the moment of the pass".**
   - `var_offside` measures at the pass (the start of its evidence window). Shown at the shot instead, #11 looked level with the line.
   - Fix: the VAR meta now carries `play_t`, and the board holds on the pass (`App.tsx`). The fixture also gets frames for the run-up into the pass.
2. **Gap chapters drew a lone arrow, with no lines.**
   - The crew's `line_gap` wrapper keeps only the arrow. `show_refine.py` re-runs B's tool, checks that the value and arrow match the claim, then adds the tool's two lines on the arrow's cue.
   - `show_fixture.py` now runs this on every build. The evidence panel gets the same lines.
   - Optional root fix, not done: `crew/.../core_tools._line_gap` could keep the lines.
3. **A scored shot was titled "The chance".** Such chapters are now titled "Goal" ("Gol" in Spanish).
4. **The ball covered the carrier's shirt number, and overlapping discs hid numbers.**
   - `layoutDiscs` (`pitch.ts`) is display only:
     - discs that overlap are nudged apart, at most 0.75 m;
     - the ball is drawn just outside the nearest disc.
5. **Recorder issues** (fixed when re-recording):
   - The "Up next" cards covered key moments.
   - The evidence tap landed on the wrong chapter.

Running `show_refine.py` twice gives the same file.
