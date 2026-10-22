# Stream A: demo click path for the video (sim-7 on the live Worker)

Base URL: `https://chalktalk.inspectmate-logs.workers.dev` (written `$W` below).

The live Worker plays sim-7, built with `--seed 7 --half-minutes 5 --demo`, so it is a 10-minute match.
- The broadcast takes overlays from the hub.
- The producer queue (`queue-sim-7.json`) and the show (`show-sim-7.json`) are both built from the same match, so the times line up.

## Before recording
1. Open two windows side by side:
   - **Producer:** `$W/producer`
   - **Broadcast:** `$W/?lens=analyst&side=away`
2. In the producer, type the hub secret (`OVERLAY_SECRET`, from `~/.config/chalktalk/edge.env`) into **Hub secret**.
   - It stays in page memory only, so type it again after every reload. Keep it off camera.
3. Click **Restart match** in the producer. This starts a new take:
   - It withdraws every approval this console made on the hub, so nothing from the last take airs again.
   - It clears the queue's decisions.
   - It puts the hub clock back to 00:00 and starts it playing.

   The badge then reads `live 00:0x`.
   - If it reads `hub offline`, reload the page.
   - Sockets reconnect on their own after a hub drop, backing off from 2 s up to 30 s.

## The click path

| # | Window | Click | What shows |
|---|---|---|---|
| 1 | Broadcast | (watch) | The live match on the hub clock; badge `live hub`. |
| 2 | Producer | The first `2'` row, which shows **airs in N s** (moment at 01:19). Read the script, the gate table and the claims. | The pitch preview with the strokes. |
| 3 | Producer | **Approve the moment (18)** or key `m`. | 18 approved (3 lenses × 3 sides × 2 languages). Each row shows `N tellings sent to hub`. |
| 4 | Broadcast | (wait for 01:19) | The play holds; the analyst/away telling draws the gap, pitch control and the press on the words that name them. |
| 5 | Broadcast | **Show** (or open `$W/?surface=show&lens=analyst&side=away`) | The studio show with its chapter list. It plays its own recorded fixture, live hub or not. |
| 6 | Show | **2. Where they should have been** | The ghost holds the player's slot; their real run is drawn beside it. |
| 7 | Show | **6. VAR check: offside?** | An amber dashed line and "provisional" until the decision cue, then a solid line and "Goal stands". |
| 8 | Show | **Half-time: the moments that decided it** | The stats panel and the deciding moments. Tap a moment to replay its window. **Back to the show** (or Esc) closes it. |
| 9 | Show | **Catch-up at 10:00: what you missed** | Both goals plus the chance, each replayable. |
| 10 | Show | A number in the caption (for example **11.7**), or a chip under "Tap a number to see its evidence" | The evidence window replays with the tool's geometry, labelled `re-run matches`. Esc goes back. |
| 11 | Show | **Es-ES** in the header | Spanish captions. The ghost and VAR chapter titles are translated (`Dónde debía estar`, `Revisión del VAR: ¿fuera de juego?`), and comma decimals such as `11,7` are tappable. |

The moments in the queue are at 01:19, 01:47, 03:05 and 03:36. The producer's row badges count down to each one.
- Approve a moment **before** it airs. The broadcast airs a moment only within 8 s of its time, so a late approval is skipped. That is by design: the live frames only reach 15 s back.
- To show a second moment, approve the 01:47 row while step 4 is airing.

## Notes
- **Approving one row** airs it only for viewers on that row's lens, side and language. **Approve the moment** covers every viewer, which is why the demo uses it.
- **The show surface** is a recorded programme. Its chapters, ghost, VAR, summaries and evidence come from `show-sim-7.json`, not from the hub.
  - Before this branch, the show surface was blank whenever the hub was live.
- **Fake backends:** the overlays come from the crew caches made with the fake backends, so there is no audio. Captions are timed by the fake speech client.
  - When C runs the crew live, regenerate both fixtures with the commands below.
- **Verified locally only.** I walked every step on a local `wrangler dev` with a local sim-7 package (`--seed 7 --half-minutes 5 --demo`) and a throwaway local secret. I never touched the live Worker. The coordinator should do one dry run on `$W` after deploying.

## Regenerating the fixtures (fake backends)
```
env -u CHALKTALK_CREW_BACKEND uv run python -m chalktalk_crew run --seed 7 --half-minutes 5 --max-moments 4 \
  --lenses casual,analyst,newcomer --sides home,away,neutral --lang en-GB,es-ES --cache <crewcache>
env -u CHALKTALK_CREW_BACKEND uv run python web/scripts/show_fixture.py --cache <crewcache> --half-minutes 5 \
  --out web/public/fixtures/show-sim-7.json --queue web/public/fixtures/queue-sim-7.json
```
`--half-minutes` must match the live package (5). If it doesn't, the queue's moments land at the wrong times on the hub clock.
