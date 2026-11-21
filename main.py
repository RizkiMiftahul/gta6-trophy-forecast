"""Refresh-aware forecast of GTA VI trophy earn rates."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import variance

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


def weighted_median(entries):
    ordered = sorted(entries)
    half = sum(weight for _, weight in ordered) / 2
    cumulative = 0.0
    for i, (value, weight) in enumerate(ordered):
        cumulative += weight
        if cumulative > half:
            return value
        if cumulative == half and i + 1 < len(ordered):
            return (value + ordered[i + 1][0]) / 2
    return ordered[-1][0]


def integer_earners(rate, players):
    """Recover the integer earner count represented by a printed page rate."""
    if rate is None:
        return None
    return max(0, int(math.floor(float(rate) * float(players) / 100.0 + 0.5)))


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
    log_players = [math.log(p) for p in players]
    earner_states = [
        [integer_earners(rate, s["players"]) for rate in s["rates"]]
        for s in states
    ]
    interval_gaps = [(ts[j] - ts[j - 1]) / 60 for j in range(1, len(states))
                     if ts[j] > ts[j - 1]]
    cadence_minutes = median(interval_gaps) if interval_gaps else None
    jump_flags = [players[j] > players[j - 1] * 1.2 for j in range(1, len(states))]
    state_ends = ts[1:] + [parse_time(history[-1]["at"])]
    for j in range(1, len(states)):
        duration = max(0.0, (state_ends[j] - ts[j]) / 3600)
        # Large downward revisions can make the square root undefined.
        movement = math.sqrt(max(0.0, 1 + log_players[j] - log_players[j - 1]))
        weights[j] *= movement * (1 + math.log1p(duration))

    pfit = weighted_fit(hours, log_players, weights)
    log_hours = [math.log1p(h) for h in hours]
    saturating_fit = weighted_fit(log_hours, log_players, weights)
    player_span = horizon
    if saturating_fit and (pfit is None or saturating_fit[2] < pfit[2]):
        pfit = saturating_fit
        player_span = math.log1p(hours[-1] + horizon) - log_hours[-1]
    log_p_change = max(0.0, 0.5 * pfit[1] * player_span) if pfit else 0.0
    log_p_target = log_players[-1] + log_p_change

    fits = []
    eta_pool = {tier: [] for tier in TIERS}
    growth_pool = {tier: [] for tier in TIERS}
    jump_pool = {tier: [] for tier in TIERS}
    refreshes = [j for j in range(1, len(states)) if jump_flags[j - 1]]
    lag_by_trophy = []
    for i, trophy in enumerate(case["trophies"]):
        points = [(j, s["time"], s["players"], earner_states[j][i])
                  for j, s in enumerate(states) if s["rates"][i] is not None
                  and earner_states[j][i] is not None and earner_states[j][i] > 0]
        efit = None
        eta = None
        nonjump_growth = []
        jump_growth = []
        jump_fractions = []
        for j in range(1, len(states)):
            before, after = earner_states[j - 1][i], earner_states[j][i]
            dt = (ts[j] - ts[j - 1]) / 3600
            if before is None or after is None or before <= 0 or after <= 0 or dt <= 0:
                continue
            growth = math.log(after / before) / dt
            entry_weight = (weights[j] + weights[j - 1]) / 2
            if jump_flags[j - 1]:
                jump_growth.append((growth, entry_weight, dt))
            else:
                nonjump_growth.append((growth, entry_weight))
        steady_growth = weighted_median(nonjump_growth) if nonjump_growth else None
        if steady_growth is not None:
            for jump_rate, jump_weight, dt in jump_growth:
                expected = max(0.0, steady_growth * dt)
                observed = max(0.0, jump_rate * dt)
                if expected > 1e-9:
                    jump_fractions.append((min(1.0, observed / expected), jump_weight))
        lag_fraction = (weighted_median(jump_fractions) if jump_fractions else 0.25)
        lag_fraction = min(1.0, max(0.0, lag_fraction))
        lag_by_trophy.append(lag_fraction)
        if len(points) >= 2:
            px = [math.log(p) for _, _, p, _ in points]
            ey = [math.log(e) for _, _, _, e in points]
            # A refresh interval can hide ordinary earner progress. Keep it in
            # the fit, but give its endpoint only the learned lag weight.
            pw = [weights[j] * (lag_fraction if j > 0 and jump_flags[j - 1] else 1.0)
                  for j, _, _, _ in points]
            eta_fit = weighted_fit(px, ey, pw) if len(set(px)) >= 2 else None
            if eta_fit:
                eta = eta_fit[1]
                eta_pool.get(trophy["tier"], []).append((eta, sum(pw)))
            tx = [hours[j] for j, _, _, _ in points]
            growth_weights = [weights[j] * (4.0 if j == 0 or not jump_flags[j - 1]
                                                else max(0.05, lag_fraction))
                              for j, _, _, _ in points]
            efit = weighted_fit(tx, ey, growth_weights) if len(set(tx)) >= 2 else None
            if efit:
                growth_pool.get(trophy["tier"], []).append((efit[1], sum(growth_weights)))
        jumps = []
        elapsed_days = 0.0
        for j in refreshes:
            before, after = states[j - 1]["rates"][i], states[j]["rates"][i]
            if before is not None and after is not None:
                jumps.append(logit(float(after)) - logit(float(before)))
                elapsed_days += (hours[j] - hours[j - 1]) / 24
        jumpvar = None
        if len(jumps) >= 2 and elapsed_days > 0:
            jumpvar = variance(jumps) * len(jumps) / elapsed_days
            jump_pool.get(trophy["tier"], []).append(jumpvar)
        fits.append((points, eta, efit, jumpvar))

    eta_medians = {tier: weighted_median(v) for tier, v in eta_pool.items() if v}
    growth_medians = {tier: weighted_median(v) for tier, v in growth_pool.items() if v}
    jump_medians = {tier: median(v) for tier, v in jump_pool.items() if v}
    pooled = []
    for trophy, (_, eta, efit, _) in zip(case["trophies"], fits):
        tier = trophy["tier"]
        eta = (0.5*eta + 0.5*eta_medians[tier]) if eta is not None and tier in eta_medians else (eta if eta is not None else eta_medians.get(tier, 1.0))
        growth = efit[1] if efit else None
        growth = (0.5*growth + 0.5*growth_medians[tier]) if growth is not None and tier in growth_medians else (growth if growth is not None else growth_medians.get(tier, 0.0))
        pooled.append((eta, growth))

    last_rates = states[-1]["rates"]
    # Use the last rate to break elasticity ties at the tercile boundaries.
    ranked = sorted(range(len(pooled)), key=lambda i: (pooled[i][0], float(last_rates[i] or 0)))
    maturity = [0.0] * len(pooled)
    damped_horizon = 0.5 * horizon
    for group in range(3):
        members = ranked[group * len(ranked) // 3:(group + 1) * len(ranked) // 3]
        if members:
            group_growth = median([pooled[i][1] for i in members])
            for i in members:
                maturity[i] = (group_growth - pooled[i][1]) * 0.25 * damped_horizon

    stale = len(states) == 1 and horizon >= 0.5
    stale_shift = min(0.35, 0.10 * math.sqrt(horizon / 1.5)) if stale else 0.0
    horizon_days = horizon / 24

    # A flat/near-empty history gives no evidence about the first page refresh.
    # Launch night is the one well-supported case where a large jump is likely.
    case_horizon_minutes = float(case.get("horizon_minutes", horizon * 60))
    total_player_growth = players[-1] / players[0] - 1.0
    degenerate = (case_horizon_minutes >= 30 and
                  (len(states) <= 2 or total_player_growth < 0.05))
    if degenerate:
        release = case.get("game", {}).get("release_date")
        near_release = False
        if release:
            release_time = parse_time(release)
            case_time = parse_time(case.get("at", history[-1]["at"]))
            release_age_hours = (case_time - release_time) / 3600
            near_release = -24 <= release_age_hours <= 36
        base_growth = 6.0 if near_release else 1.6
        horizon_hours = case_horizon_minutes / 60
        player_multiplier = min(12.0, max(1.5, base_growth ** (case_horizon_minutes / 90.0)))
        target_players = players[-1] * player_multiplier
        earner_growth = min(0.10, 0.02 * horizon_hours)

    rows = []
    for index, (trophy, (points, _, efit, jumpvar)) in enumerate(zip(case["trophies"], fits)):
        eta, growth = pooled[index]
        last_rate = last_rates[index]
        if degenerate:
            last_e = earner_states[-1][index] or 0
            if last_rate is not None and float(last_rate) >= 99.99:
                center_rate = 99.99
            else:
                center_rate = 100.0 * last_e * (1.0 + earner_growth) / target_players
                center_rate = min(99.99, max(0.01, center_rate))
        elif points:
            last_e = points[-1][3]
            forecast_lag = 1.0
            if cadence_minutes and cadence_minutes > 0:
                cadence_ratio = horizon * 60 / cadence_minutes
                if 0.5 <= cadence_ratio <= 1.5:
                    forecast_lag = lag_by_trophy[index]
            log_e_target = math.log(last_e) + forecast_lag * (eta * log_p_change) \
                           + forecast_lag * growth * damped_horizon + maturity[index]
            log_rate = math.log(100) + log_e_target - log_p_target
            center_rate = math.exp(min(math.log(99.99), max(math.log(0.01), log_rate)))
        else:
            # Keep null and zero-rate trophies at the last observed rate.
            center_rate = clamp(float(last_rate)) if last_rate is not None else 0.01
        resid = efit[2] if efit else 0.0
        if jumpvar is None:
            jumpvar = jump_medians.get(trophy["tier"], 0.0)
        if degenerate:
            sigma = 0.18 + min(0.50, 0.50 / math.sqrt(max(1, earner_states[-1][index] or 0)))
        else:
            sigma = math.sqrt((0.35 * math.sqrt(horizon_days))**2 + resid**2
                              + jumpvar * min(1, horizon_days / 4.52) + 0.03)
            if stale:
                sigma += 0.30
            sigma = min(1.6, sigma)
            if cadence_minutes and cadence_minutes > 0:
                cadence_ratio = horizon * 60 / cadence_minutes
                if 0.5 <= cadence_ratio <= 1.5:
                    sigma = min(sigma, 0.18 + min(0.50, 0.50 / math.sqrt(max(1, earner_states[-1][index] or 0))))
        center = logit(center_rate) - (0.0 if degenerate else stale_shift)
        qs = []
        for z in Z:
            value = round4(clamp(100/(1+math.exp(-(center+z*sigma)))))
            if qs:
                value = max(qs[-1], value)
            qs.append(value)
        if last_rate is not None and float(last_rate) >= 99.99 and (degenerate or eta >= 0.9):
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
