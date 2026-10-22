# Spike S1: SSML bookmarks vs WordBoundary on Azure Speech

**Result: pass.** Cue offsets can come straight from Azure Speech. Each bookmark fires a fixed
~12 ms before the word it marks, except after a pause, where it fires at the start of the
silence. Snapping each bookmark to the start of its word removes both effects.

## Method
- Script: `crew/spikes/s1_word_timing.py`. It is live and manual only (Speech F0, free tier),
  and never runs in tests or CI.
- Input: 10 synthetic pundit lines in the crew's template style, with 20 cues
  (`<bookmark mark='kN'/>` right before the word that names the stroke). Each line ran on
  2 voices (`en-GB-RyanNeural`, `en-US-AndrewNeural`), so 40 cues in total. Output is
  MP3 24 kHz 48 kbit/s.
- For each cue:
  - the raw bookmark offset comes from `bookmark_reached`;
  - the "true" word is the first `WordBoundary` (Word type) whose `text_offset` into the SSML
    comes after the bookmark tag;
  - delta = word start − bookmark offset, in ms on the audio clock.
- Both runs (Oct 22) gave identical numbers, so synthesis timing is deterministic for a fixed
  SSML and voice.

## Numbers (40 cues)
| | median abs | p95 abs | max abs | min signed |
|---|---|---|---|---|
| en-GB-RyanNeural (20) | 12.5 ms | 13 ms | 175 ms | +12 ms |
| en-US-AndrewNeural (20) | 12.0 ms | 13 ms | 275 ms | +12 ms |
| **all (40)** | **12.0 ms** | **13 ms** | **275 ms** | **+12 ms** |

- The bookmark never fires after its word starts (min signed +12 ms).
- The outliers both come from `k14` ("…behind him, [[k14]]space opens…"). The bookmark fires at
  the start of the comma pause, 175 to 275 ms before the word. Unsnapped, the stroke would start
  that much early.

## Snapping (which word does a time-based snap pick?)
| Rule | correct |
|---|---|
| first word starting ≥ bookmark − 0 ms | 40/40 |
| first word starting ≥ bookmark − 20 ms | 40/40 |
| first word starting ≥ bookmark − 100 ms | 14/40 (picks the previous short word) |

## Decisions
- The crew's `AzureSpeechClient` snaps each bookmark to its word by SSML text position
  (`text_offset`), which is exact, and falls back to the first word starting at or after the
  bookmark. The 100 ms slack from the first version of PR #8 is gone; that fix is pushed to
  that PR.
- Cue offset = snapped word start. Stroke start = cue offset − `lead_ms` (150 ms default), as
  the evals assume. After snapping, cue-to-word alignment is 0 ms by construction, well inside
  the 50 ms eval bar. The remaining sync error is the player's job (audio clock vs render).
- The character-rate fake stays only for tests and CI.
