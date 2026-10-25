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

## Second review (frame by frame at 1 fps, plus speech-to-text of both voice tracks)
Every number spoken was checked against the tool output: xG 0.02 and a 7.4 m gap (chapter 1), ghost 6.3 m, VAR 4.9 m, Spanish 0.01 xG and a 13.3 m gap, 0.04 xG and 8.6 m (chapter 5). The producer's 44% pitch control and 44% pressing are two separate tool results that happen to match; both re-run to the same hash.

6. **The VAR chapter's score bug read 1-0 at 02:50**, during the replay of the goal it was checking. The bug now holds at the check (its time, goal counted), and the board shows a "Replay 02:50" tag (`App.tsx`, `i18n.ts`).
7. **The producer queue drew gap arrows with no lines.** `refine_queue` (`show_refine.py`) adds the same two lines to the queue. Overlays the crew rejected keep their arrow as it is when the re-run differs. Tested in `producer.test.ts`.
8. **A 1 s Spanish blip played while switching language.** The video cut now drops audio stretches of 2 s or less.

Known and accepted: the VAR chapter list says 02:55 (the moment), while the bug shows the check at 02:59.
