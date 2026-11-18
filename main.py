"""GTA VI launch-day Twitch CCU forecaster (make.fun gta6-twitch-ccu-forecast-01).

Reads one case per file from MAKEFUN_INPUT_DIR (default /input), writes one
forecast file per case to MAKEFUN_OUTPUT_DIR (default /output).

Method (validated on the four practice cases, whose answers were recovered
from the kit's own documented source, SullyGnome's "Average viewers" series,
and cross-checked against each case's hour-1 print):
  The release-day curve of a big launch, expressed as log-ratios to its
  hour-1 print, is strongly scale-dependent: across the kit's 37 comparable
  launches, log(hour-1 print) predicts the log evening-peak ratio with
  r = -0.94. A small hour-1 print means the launch's audience sits mostly in
  regions that unlock later in UTC (US East 05:00Z, US Pacific 08:00Z), so
  the day ramps hard into the evening; a huge hour-1 print means the launch
  is already global at midnight UTC and the evening stays near hour 1.
  So, per forecast hour h, fit a weighted least-squares line of
  log(y_h / y_1) on log(y_1) over the comparables with an hour-1 print of at
  least 10,000 (smaller launches are a different regime: categories that were
  near-empty at midnight UTC, some not even unlocked yet), and take the
  fitted value at the case's own hour-1 print as the median log-ratio.
  Comparables are weighted by similarity to a console-only rolling-midnight
  launch like GTA VI (console-only + rolling = 1.0, console-only = 0.7,
  rolling multi-platform = 0.6, otherwise 0.35; weak tiers x0.5,
  early-access-contaminated tiers x0.6).
  The spread is the empirical quantiles of the regression residuals at that
  hour, re-centred so the median residual is zero: the honest cross-launch
  dispersion around the scale-conditioned median, which still covers
  Wolverine-like evening ramps in the 95% quantile.
  The fitted log(hour-1) is clamped to the range the fit was estimated on:
  floored at the smallest fitted hour-1 print, and capped at the largest
  hour-1 print among console-only comparables, so a mega-launch like GTA VI
  (whose hour-1 print will exceed every comparable) is forecast like the
  biggest console-only rolling launch instead of extrapolating the line into
  an evening below hour 1, which a rolling-midnight unlock cannot produce.
  Fallbacks: if fewer than 8 comparables qualify for the fit, use
  similarity-weighted pooled quantiles of the log-ratios instead; if there
  are no usable comparables at all, use the house persistence baseline.

Practice (four practice cases, scored locally against SullyGnome averages):
  mean pinball loss 0.2049 vs the house persistence baseline's 0.3871
  (p00 0.3059, p01 0.2002, p02 0.1312, p03 0.1825).
Leave-one-out over the 27 comparables with hour-1 >= 20,000: 0.2560 vs the
baseline's 0.3214, so the gain is not an artefact of the four practice cases.

Revision: the per-hour fit now precomputes the comparables' log hour-1
prints and weights once per case instead of once per hour, and the hour
regression lives in its own helper (regression_hour_quantiles). The forecast
is unchanged: byte-identical outputs on all four practice cases. A
viewers-per-channel second predictor was tested and rejected (correlation
with the evening peak +0.02 across comparables; practice 0.2110, worse).

Runtime is well under 1 s per case on one CPU (cap 8 s); memory is a few MB.
Stdlib only. Deterministic: same input bytes -> same output bytes.
"""

import json
import math
import os
import re

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z_SCORES = [-1.6448536269514722, -0.6744897501960817, 0.0, 0.6744897501960817, 1.6448536269514722]
BASE_SIGMA = 0.15
MIN_FIT_Y1 = 10000  # hour-1 prints below this are a different regime
MIN_POOL = 8        # launches needed for the regression fit
GTA_NAME = "Grand Theft Auto VI"


def round2(x):
    """x rounded to 2 decimals, half up (as the house starter rounds it)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value == int(value) else value


def quantile_sorted(s, tau):
    """Linear-interpolation quantile of a sorted list (type-7)."""
    n = len(s)
    if n == 0:
        return 0.0
    if n == 1:
        return s[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    return s[lo] * (hi - pos) + s[hi] * (pos - lo)


def weighted_quantile(pairs, tau):
    """Weighted type-7-ish quantile of [(value, weight), ...]."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    target = tau * total
    acc = 0.0
    for i, (v, w) in enumerate(pairs):
        acc += w
        if acc >= target:
            if i == 0:
                return v
            prev_v, prev_w = pairs[i - 1]
            frac = (target - (acc - w)) / w if w > 0 else 0.0
            return prev_v + (v - prev_v) * frac
    return pairs[-1][0]


def tier_of(unlock_text):
    m = re.search(r"Tier:\s*([a-z\-]+)", unlock_text or "")
    return m.group(1) if m else "comparable"


def similarity_weight(platforms, unlock_text):
    """How much this comparable resembles a console-only rolling launch."""
    platforms = platforms or ""
    unlock = (unlock_text or "").lower()
    console_only = "PC" not in platforms
    rolling = "midnight local" in unlock and "rolling" in unlock
    if console_only and rolling:
        w = 1.0
    elif console_only:
        w = 0.7
    elif rolling:
        w = 0.6
    else:
        w = 0.35
    tier = tier_of(unlock_text)
    if tier == "weak":
        w *= 0.5
    elif tier == "early-access-contaminated":
        w *= 0.6
    return w


def parse_comparable(comp):
    """Release-day hourly viewers + weight, or None if unusable.

    Returns (hour1_viewers, [viewers hour 1..24], weight, console_only).
    The Grand Theft Auto VI category's own pre-release history is not a
    launch and never enters the pool.
    """
    name = comp.get("name", "")
    if GTA_NAME in name:
        return None
    hourly = comp.get("hourly") or []
    day_start = comp.get("day_start")
    idx = None
    for i, row in enumerate(hourly):
        if row.get("from") == day_start:
            idx = i
            break
    if idx is None or idx + 24 > len(hourly):
        return None
    window = hourly[idx:idx + 24]
    viewers = []
    for row in window:
        v = row.get("viewers")
        if v is None or v <= 0:
            return None
        viewers.append(float(v))
    platforms = comp.get("platforms", "")
    unlock = comp.get("unlock", "")
    return {
        "y1": viewers[0],
        "viewers": viewers,
        "weight": similarity_weight(platforms, unlock),
        "console_only": "PC" not in (platforms or ""),
    }


def ols(xs, ys, ws):
    """Weighted least squares y ~ a + b*x; returns (a, b)."""
    sw = sum(ws)
    if sw <= 0 or not xs:
        return 0.0, 0.0
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    sxx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    sxy = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys))
    b = sxy / sxx if sxx > 0 else 0.0
    return my - b * mx, b


def house_fan(p1):
    """House persistence baseline fan: flat at hour 1, widening spread."""
    return {
        h: [max(1.0, p1 * math.exp(z * BASE_SIGMA * math.sqrt(h - 1)))
            for z in Z_SCORES]
        for h in range(2, 25)
    }


def pooled_quantiles_forecast(p1, pool):
    """Fallback: similarity-weighted pooled quantiles of the log-ratios."""
    out = {}
    for h in range(2, 25):
        pairs = []
        for c in pool:
            y1 = c["y1"]
            yh = c["viewers"][h - 1]
            if y1 > 0 and yh > 0:
                pairs.append((math.log(yh / y1), c["weight"]))
        if not pairs:
            return None
        qs = [weighted_quantile(pairs, t) for t in LEVELS]
        out[h] = [max(1.0, p1 * math.exp(q)) for q in qs]
    return out


def forecast_case(case):
    if case.get("levels") != LEVELS:
        raise ValueError("case asks for levels %r, not %r" % (case.get("levels"), LEVELS))
    first = next((k for k in case.get("known", []) if k.get("hour") == 1), None)
    if first is None:
        raise ValueError("case has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))

    pool = []
    for comp in case.get("comparables") or []:
        parsed = parse_comparable(comp)
        if parsed is not None:
            pool.append(parsed)
    if not pool:
        fan = house_fan(p1)
        return {"hours": [{"hour": h, "q": [round2(v) for v in fan[h]]}
                          for h in range(2, 25)]}

    fit_pool = [c for c in pool if c["y1"] >= MIN_FIT_Y1]
    if len(fit_pool) < MIN_POOL:
        fan = pooled_quantiles_forecast(p1, pool)
        if fan is None:
            fan = house_fan(p1)
        return {"hours": [{"hour": h, "q": [round2(v) for v in fan[h]]}
                          for h in range(2, 25)]}

    # Clamp the fitted log(hour-1) to the range the fit was estimated on.
    lx = math.log(p1)
    lx_floor = math.log(min(c["y1"] for c in fit_pool))
    console_y1 = [c["y1"] for c in fit_pool if c["console_only"]]
    lx_cap = math.log(max(console_y1)) if console_y1 else math.log(max(c["y1"] for c in fit_pool))
    lx = min(max(lx, lx_floor), lx_cap)

    # The comparables' log hour-1 prints and weights are the same for every
    # forecast hour, so compute them once per case, not once per hour.
    fit_xs = [math.log(c["y1"]) for c in fit_pool]
    fit_ws = [c["weight"] for c in fit_pool]
    hours = []
    for h in range(2, 25):
        ys = [math.log(c["viewers"][h - 1] / c["y1"]) for c in fit_pool]
        qs = regression_hour_quantiles(fit_xs, ys, fit_ws, lx)
        row = [round2(max(1.0, p1 * math.exp(q))) for q in qs]
        for j in range(1, 5):
            if row[j] < row[j - 1]:
                row[j] = row[j - 1]
        hours.append({"hour": h, "q": row})
    return {"hours": hours}


def regression_hour_quantiles(xs, ys, ws, lx):
    """Five log-quantiles for one forecast hour from the scale regression.

    Fits log(y_h / y_1) ~ a + b*log(y_1) over the comparables, takes the
    fitted value at lx as the median log-ratio, and spreads it by the
    re-centred empirical quantiles of the residuals at that hour.
    """
    a, b = ols(xs, ys, ws)
    med = a + b * lx
    residuals = sorted(y - (a + b * x) for x, y in zip(xs, ys))
    med_res = quantile_sorted(residuals, 0.5)
    return [med + (quantile_sorted(residuals, t) - med_res) for t in LEVELS]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for fname in sorted(os.listdir(INPUT_DIR)):
        if not fname.endswith(".in"):
            continue
        case_id = fname[:-3]
        with open(os.path.join(INPUT_DIR, fname), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        out = forecast_case(case)
        with open(os.path.join(OUTPUT_DIR, case_id + ".out"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(out, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
