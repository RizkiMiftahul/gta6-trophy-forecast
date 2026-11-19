"""Refresh-aware forecast of GTA VI trophy earn rates."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]
TIERS = ("platinum", "gold", "silver", "bronze")


def clamp(x):
    return min(99.99, max(0.01, x))


def logit(pct):
    p = clamp(pct)
    return math.log(p / (100 - p))


def round4(x):
    """Round to four decimals, half up, as JavaScript Math.round does."""
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

    # A state marks a distinct Exophase snapshot; repeated reads add no evidence.
    states = []
    for row in history:
        signature = (row["players_tracked"], tuple(row["rates"]))
        if not states or signature != states[-1]["signature"]:
            states.append({"signature": signature, "time": parse_time(row["at"]),
                           "players": float(row["players_tracked"]), "rates": row["rates"]})

    ts = [s["time"] for s in states]
    first = ts[0]
    hours = [(t-first)/3600 for t in ts]
    horizon = max(0.0, (parse_time(case["target"])-ts[-1])/3600)
    weights = [2 ** (-(ts[-1]-t)/3600/24) for t in ts]
    players = [s["players"] for s in states]
    pfit = weighted_fit(hours, [math.log(p) for p in players], weights) if len(states) >= 2 else None
    p_slope = pfit[1] if pfit else 0.0
    log_p_target = math.log(players[-1]) + 0.5*p_slope*horizon
    player_target = max(players[-1], math.exp(log_p_target))
    log_p_target = math.log(player_target)

    fits = []
    eta_pool = {tier: [] for tier in TIERS}
    growth_pool = {tier: [] for tier in TIERS}
    for i, trophy in enumerate(case["trophies"]):
        points = [(j, s["time"], s["players"], float(s["rates"][i]) / 100 * s["players"])
                  for j, s in enumerate(states) if s["rates"][i] is not None
                  and float(s["rates"][i]) > 0]
        efit = None
        eta = None
        if len(points) >= 2:
            px = [math.log(p) for _, _, p, _ in points]
            ey = [math.log(e) for _, _, _, e in points]
            pw = [weights[j] for j, _, _, _ in points]
            eta_fit = weighted_fit(px, ey, pw) if len(set(px)) >= 2 else None
            if eta_fit:
                eta = eta_fit[1]
                eta_pool.get(trophy["tier"], []).append(eta)
            tx = [hours[j] for j, _, _, _ in points]
            efit = weighted_fit(tx, ey, pw) if len(set(tx)) >= 2 else None
            if efit:
                growth_pool.get(trophy["tier"], []).append(efit[1])
        fits.append((points, eta, efit))

    eta_medians = {tier: median(v) for tier, v in eta_pool.items() if v}
    growth_medians = {tier: median(v) for tier, v in growth_pool.items() if v}
    stale = len(states) == 1 and horizon >= 0.5
    stale_shift = min(0.35, 0.10 * math.sqrt(horizon / 1.5)) if stale else 0.0
    rows = []
    for index, (trophy, (points, eta, efit)) in enumerate(zip(case["trophies"], fits)):
        tier = trophy["tier"]
        eta = (0.5*eta + 0.5*eta_medians[tier]) if eta is not None and tier in eta_medians else (eta if eta is not None else eta_medians.get(tier, 1.0))
        growth = efit[1] if efit else None
        growth = (0.5*growth + 0.5*growth_medians[tier]) if growth is not None and tier in growth_medians else (growth if growth is not None else growth_medians.get(tier, 0.0))
        if points:
            last_e = points[-1][3]
            log_e_target = math.log(last_e) + eta*(log_p_target-math.log(players[-1])) + growth*horizon*0.5
            earners_target = math.exp(log_e_target)
            center_rate = clamp(100*earners_target/player_target)
        else:
            # Keep null and zero-rate trophies at the last observed rate.
            last_rate = states[-1]["rates"][len(rows)]
            center_rate = clamp(float(last_rate)) if last_rate is not None else 0.01
        resid = efit[2] if efit else 0.0
        sigma = math.sqrt((0.35*math.sqrt(horizon/24))**2 + resid**2 + 0.03)
        if stale:
            sigma += 0.30
        sigma = min(1.6, sigma)
        center = logit(center_rate) - stale_shift
        qs = []
        for z in Z:
            value = round4(clamp(100/(1+math.exp(-(center+z*sigma)))))
            if qs:
                value = max(qs[-1], value)
            qs.append(value)
        last_rate = states[-1]["rates"][index]
        if last_rate is not None and float(last_rate) >= 99.99 and eta >= 0.9:
            qs[0] = max(90.0, qs[0])
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
