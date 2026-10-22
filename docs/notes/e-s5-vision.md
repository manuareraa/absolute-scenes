# S5: vision spike (stream E)

**Verdict: go.** On the RTX 3050 Laptop (4 GB), off-the-shelf RF-DETR-S (COCO weights, no fine-tuning) with ByteTrack runs faster than real time (46.5 fps detector, 37.4 fps end to end against a 25 fps clip). It finds 95% of the people and 84% of the ball frames. The line-based homography puts people within 0.35 m of truth on the pitch.

Identity is the weak spot. AssA is 0.38 in image space and 0.57 on the pitch, with 26 ID switches across 22 people in 30 s. Identity only matters for M9's actor attribution.

## Setup
- **Clip:** the stream-E renderer, `sim` seed 7, a 30 s window (225.0 s to 255.0 s, 750 frames at 1280x720 and 25 fps). It shows broadcast camera pan and zoom, motion blur and occlusions.
- **Ground truth:** exact, from the renderer: boxes, visibility, pitch positions, ball 3D position and per-frame homography.
- **Licences:** everything is Apache-2.0 or MIT/BSD. There is no Ultralytics and no real footage.
- **GPU stage (`vision/gpu/run_s5.py`, separate venv, never installed in CI):**
  - Pinned packages: `rfdetr==1.11.2`, `trackers==2.6.1`, `supervision==0.31.1`, `torch==2.14.1+cu130`.
  - Weights: `rf-detr-small.pth`, Roboflow's official release, MD5-checked by `rfdetr` on download and kept outside the repo.
  - Detector settings: input 768 px square, FP16, batch 4.
  - Classes: COCO person (score ≥ 0.15, fed to ByteTrack with a high-confidence split at 0.5) and sports ball (top 3 at ≥ 0.1).
- **CPU stage (`python -m chalktalk_vision.s5`, in the workspace and tested in CI):**
  - Calibration: a per-frame line-based PTZ fit from known camera position and pitch markings (a distance transform plus Nelder-Mead) gives the homography.
  - People: foot point to pitch metres, then kit colour in Lab space (5 kits), voted per track, which also gives player, goalkeeper or referee.
  - Ball: lowest box point to the ground.
- **Scoring:**
  - HOTA by the TrackEval method, CLEAR MOTA and IDF1, at IoU 0.5 in image space.
  - On the pitch, HOTA uses the GS-HOTA distance similarity. MOTA and IDF1 use a 1 m threshold.
  - Ground-truth people under 30% visible are "don't care".

## Results

### Throughput (RTX 3050 Laptop, 4 GB)

| stage | fps | notes |
|---|---|---|
| RF-DETR-S detector, 768 px FP16, batch 4 | **46.5** | peak GPU memory 322 MB |
| GPU stage end to end (decode + detect + ByteTrack + write) | **37.4** | |
| CPU stage (calibration + kits + projection) | 27.1 | single thread, about 215 MB RSS |

Running the two stages one after the other covers a 30 s clip in about 48 s. The CPU calibration is now the bottleneck. It could run every 5th frame, with interpolation in between, if needed.

### Tracking and pitch accuracy: detector against the oracle

The oracle row feeds ground-truth boxes into the same CPU stage. It isolates the error from calibration and projection.

| metric | RF-DETR-S + ByteTrack | oracle boxes |
|---|---|---|
| **image HOTA** (DetA / AssA) | **0.487** (0.630 / 0.379) | 1.0 |
| image MOTA / IDF1 / IDSW | **0.915 / 0.673** / 26 | 1.0 / 1.0 / 0 |
| image recall / precision | 0.953 / 0.965 | 1.0 / 1.0 |
| track IDs for 22 ground-truth IDs | 41 | 22 |
| **pitch HOTA** (DetA / AssA) | **0.738** (0.947 / 0.575) | 1.0 |
| pitch MOTA@1m / IDF1@1m | 0.902 / 0.673 | 1.0 / 1.0 |
| player position error, mean / p95 | 0.35 m / 0.50 m | 0.09 m / 0.15 m |
| calibration error, mean / p95 | 0.034 m / 0.058 m | 0.033 m / 0.058 m |
| kit / role accuracy | 0.949 | 1.0 |
| ball recall / precision (8 px) | **0.844 / 0.888** | 1.0 / 1.0 |
| ball ground error, median (ball on the ground) | 0.27 m | 0.02 m |

### Reading the numbers
- **Detection is good enough as-is.** Pitch DetA is 0.95, so nearly every visible person is found and placed within about 1 m. A football-specific fine-tune is not needed for the demo.
- **Image HOTA is held back by localisation (LocA 0.68) and association.**
  - COCO "person" boxes are looser than the renderer's tight boxes.
  - That looseness also explains the 0.35 m pitch error: the foot point sits a few pixels low or high.
- **Calibration is not the problem.** The homography error is the same with and without the detector (0.034 m).
- **ID switches come from occlusions in crowded moments and from camera pans.** ByteTrack works in image space and is not told about camera motion. Two likely fixes, neither tried yet:
  1. Track in pitch space, since the homography is already known.
  2. Use the camera-motion compensation in `trackers` (BoT-SORT with CMC).
- **The ball works off COCO weights at 768 px.** Most misses are when the ball is airborne against the crowd or inside a player's box.

## Reproduce
```bash
uv venv -p 3.12 ~/.cache/chalktalk/vision-gpu
VIRTUAL_ENV=~/.cache/chalktalk/vision-gpu uv pip install -r vision/gpu/requirements.txt
uv run python scripts/render/render_clip.py --out scripts/render/out/demo   # see PR #24
~/.cache/chalktalk/vision-gpu/bin/python vision/gpu/run_s5.py \
    --video scripts/render/out/demo/clip.mp4 --out scripts/render/out/demo/tracks.jsonl
uv run python -m chalktalk_vision.s5 --clip scripts/render/out/demo --tracks scripts/render/out/demo/tracks.jsonl
uv run python -m chalktalk_vision.s5 --clip scripts/render/out/demo --oracle
```
Outputs go to `scripts/render/out/`, which is git-ignored. No weights or videos are committed.

## Next (M9)
Turn the pitch tracks into `event` contracts with `source: "video"` and score them against the sim's events. That work is in a follow-up PR.
