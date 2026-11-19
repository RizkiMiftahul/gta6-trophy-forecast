"""Forecast GTA VI trophy earn rates from the case's observed history."""
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
RELEASE = datetime(2026, 11, 19, tzinfo=timezone.utc).timestamp()


def clamp(x):
    return min(99.99, max(0.01, x))


def logit(pct):
    p = clamp(pct)
    return math.log(p / (100 - p))


def round4(x):
    """Round to four decimals, half up, as JavaScript's Math.round(x * 10000) / 10000 does."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value.is_integer() else value


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def weighted_fit(xs, ys, weights):
    sw = sum(weights)
    if sw <= 0:
        return None
    xm = sum(w * x for x, w in zip(xs, weights)) / sw
    ym = sum(w * y for y, w in zip(ys, weights)) / sw
    sxx = sum(w * (x - xm) ** 2 for x, w in zip(xs, weights))
    if sxx <= 1e-15:
        return None
    slope = sum(w * (x - xm) * (y - ym) for x, y, w in zip(xs, ys, weights)) / sxx
    intercept = ym - slope * xm
    resid = math.sqrt(max(0.0, sum(w * (y - (intercept + slope*x))**2 for x, y, w in zip(xs, ys, weights)) / sw))
    return intercept, slope, resid


def median(values):
    vals = sorted(values)
    n = len(vals)
    return vals[n//2] if n % 2 else (vals[n//2-1] + vals[n//2]) / 2


def forecast_case(case):
    if case.get("levels") != LEVELS:
        raise ValueError("unexpected quantile levels")
    history = case["history"]
    if not history:
        raise ValueError("case has no history")
    ts = [parse_time(row["at"]) for row in history]
    first = ts[0]
    hours = [(t-first)/3600 for t in ts]
    players = [float(row["players_tracked"]) for row in history]
    target_ts = parse_time(case["target"])
    horizon = max(0.0, (target_ts-ts[-1])/3600)
    if len(set(players)) >= 2:
        pfit = weighted_fit(hours, [math.log(p) for p in players], [1.0]*len(players))
        slope = max(0.0, pfit[1])
        log_p_target = math.log(players[-1]) + slope * horizon * 0.5
    else:
        log_p_target = math.log(players[-1])
    tier_slopes = {tier: [] for tier in ("platinum", "gold", "silver", "bronze")}
    fits = []
    for i, trophy in enumerate(case["trophies"]):
        points = [(t, rate) for t, row in zip(ts, history) if (rate := row["rates"][i]) is not None]
        xs = [math.log1p(max(0.0, (t-RELEASE)/3600)) for t, _ in points]
        ys = [logit(rate) for _, rate in points]
        ages = [(target_ts-t)/3600 for t, _ in points]
        weights = [2 ** (-max(0.0, age)/12) for age in ages]
        trend_fit = weighted_fit(xs, ys, weights) if len(points) >= 3 and len(set(xs)) >= 2 else None
        lx = [math.log(float(row["players_tracked"])) for row in history if row["rates"][i] is not None]
        dilution_fit = weighted_fit(lx, ys, weights) if len(points) >= 3 and len(set(lx)) >= 2 else None
        if dilution_fit is not None and trophy["tier"] in tier_slopes:
            tier_slopes[trophy["tier"]].append(dilution_fit[1])
        fits.append((points, trend_fit, dilution_fit, xs, ys, weights))
    pooled = {tier: median(vals) for tier, vals in tier_slopes.items() if vals}
    rows = []
    for i, (trophy, fit) in enumerate(zip(case["trophies"], fits)):
        points, trend_fit, dilution_fit, xs, ys, weights = fit
        trend_value = trend_fit[0] + trend_fit[1] * math.log1p(max(0.0, (target_ts-RELEASE)/3600)) if trend_fit else None
        dilution_value = None
        if dilution_fit:
            slope = dilution_fit[1]
            tier = trophy["tier"]
            if tier in pooled:
                slope = 0.5*slope + 0.5*pooled[tier]
            dilution_value = dilution_fit[0] + slope*log_p_target
        available = [v for v in (trend_value, dilution_value) if v is not None]
        last_rate = points[-1][1] if points else 0.0
        center = sum(available)/len(available) if available else logit(last_rate)
        resid = trend_fit[2] if trend_fit else 0.0
        growth = max(0.0, log_p_target - math.log(players[-1]))
        floor_var = 0.04 + 0.25 * growth**2
        sigma = min(1.6, math.sqrt((0.5*math.sqrt(horizon/24))**2 + resid**2 + floor_var))
        qs = []
        for z in Z:
            value = round4(clamp(100/(1+math.exp(-(center+z*sigma)))))
            if qs:
                value = max(qs[-1], value)
            qs.append(value)
        rows.append({"id": trophy["id"], "q": qs})
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        result = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(json.dumps(result, separators=(",", ":"))+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
