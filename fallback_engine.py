"""
Pure-Python mirror of engine/main.cpp
-------------------------------------
Used only when no C++ toolchain is available so the site never hard-fails.
Same command names, same JSON shapes. The C++ engine is authoritative.
"""

import math

LIB = [
    ("Back Squat", "squat", 1, 1), ("Front Squat", "squat", 1, 2),
    ("Hack Squat", "squat", 2, 1), ("Leg Press", "squat", 2, 0),
    ("Goblet Squat", "squat", 2, 0), ("Bulgarian Split Squat", "squat", 3, 1),
    ("Walking Lunge", "squat", 3, 0),
    ("Deadlift", "hinge", 1, 1), ("Romanian Deadlift", "hinge", 1, 1),
    ("Trap-Bar Deadlift", "hinge", 2, 0), ("Hip Thrust", "hinge", 2, 0),
    ("Kettlebell Swing", "hinge", 3, 0), ("Leg Curl", "hinge", 3, 0),
    ("Back Extension", "hinge", 3, 0),
    ("Bench Press", "push_h", 1, 1), ("Incline Bench Press", "push_h", 2, 1),
    ("Dumbbell Bench Press", "push_h", 2, 0), ("Push-Up", "push_h", 3, 0),
    ("Dip", "push_h", 3, 1), ("Cable Fly", "push_h", 3, 0),
    ("Overhead Press", "push_v", 1, 1), ("Push Press", "push_v", 2, 2),
    ("Seated DB Press", "push_v", 2, 0), ("Landmine Press", "push_v", 3, 0),
    ("Lateral Raise", "push_v", 3, 0),
    ("Barbell Row", "pull_h", 1, 1), ("Pendlay Row", "pull_h", 1, 2),
    ("Chest-Supported Row", "pull_h", 2, 0), ("Seated Cable Row", "pull_h", 2, 0),
    ("Face Pull", "pull_h", 3, 0),
    ("Weighted Pull-Up", "pull_v", 1, 2), ("Lat Pulldown", "pull_v", 2, 0),
    ("Assisted Pull-Up", "pull_v", 2, 0), ("Straight-Arm Pulldown", "pull_v", 3, 0),
    ("Hanging Leg Raise", "core", 3, 1), ("Ab Wheel Rollout", "core", 3, 1),
    ("Cable Crunch", "core", 3, 0), ("Pallof Press", "core", 3, 0),
    ("Plank (weighted)", "core", 3, 0),
    ("Barbell Curl", "arms", 3, 0), ("Hammer Curl", "arms", 3, 0),
    ("Skull Crusher", "arms", 3, 0), ("Cable Pushdown", "arms", 3, 0),
    ("Farmer Carry", "carry", 3, 0), ("Sled Push", "carry", 3, 0),
]

SCHEMES = {
    "strength":    {1: (5, 3, 5, 210, 8), 2: (4, 5, 6, 150, 8), 3: (3, 8, 10, 75, 8)},
    "hypertrophy": {1: (4, 6, 8, 150, 9), 2: (4, 8, 10, 105, 9), 3: (3, 12, 15, 60, 9)},
    "fatloss":     {1: (4, 6, 8, 120, 8), 2: (3, 10, 12, 75, 8), 3: (3, 15, 20, 45, 9)},
    "endurance":   {1: (3, 10, 12, 90, 7), 2: (3, 12, 15, 60, 7), 3: (2, 15, 20, 45, 8)},
    "general":     {1: (4, 8, 12, 90, 8), 2: (4, 8, 12, 90, 8), 3: (3, 12, 15, 60, 8)},
}

SPLITS = {
    1: [("Full Body", ["squat", "push_h", "pull_h", "core"])],
    2: [("Full Body A", ["squat", "push_h", "pull_h", "arms"]),
        ("Full Body B", ["hinge", "push_v", "pull_v", "core"])],
    3: [("Push", ["push_h", "push_v", "arms", "core"]),
        ("Pull", ["pull_v", "pull_h", "arms", "core"]),
        ("Legs", ["squat", "hinge", "core", "carry"])],
    4: [("Upper Strength", ["push_h", "pull_h", "push_v", "pull_v"]),
        ("Lower Strength", ["squat", "hinge", "core", "carry"]),
        ("Upper Volume", ["push_h", "pull_v", "pull_h", "arms"]),
        ("Lower Volume", ["hinge", "squat", "core", "carry"])],
    5: [("Push", ["push_h", "push_v", "arms", "core"]),
        ("Pull", ["pull_v", "pull_h", "arms", "core"]),
        ("Legs", ["squat", "hinge", "core", "carry"]),
        ("Upper", ["push_h", "pull_h", "push_v", "pull_h"]),
        ("Lower", ["squat", "hinge", "core", "carry"])],
    6: [("Push A", ["push_h", "push_v", "arms", "core"]),
        ("Pull A", ["pull_v", "pull_h", "arms", "core"]),
        ("Legs A", ["squat", "hinge", "core", "carry"]),
        ("Push B", ["push_v", "push_h", "arms", "core"]),
        ("Pull B", ["pull_h", "pull_v", "arms", "core"]),
        ("Legs B", ["hinge", "squat", "core", "carry"])],
}

BLOCK = [
    (1, "Accumulation", 1.000, 1.00, "Technique first. Leave 2 reps in reserve on every set."),
    (2, "Accumulation", 1.025, 1.10, "Add one set to primary lifts, same loads."),
    (3, "Accumulation", 1.050, 1.20, "Peak volume week. Sleep and protein are non-negotiable."),
    (4, "Deload", 0.850, 0.55, "Deload. Move well, drop all sets to RPE 6."),
    (5, "Intensification", 1.030, 1.00, "Re-enter at week-2 volumes with sharper intent."),
    (6, "Intensification", 1.055, 1.05, "Heavier singles on primary, then back-off sets."),
    (7, "Peak", 1.07, 0.90, "Heaviest week. Cap accessories at 2 sets."),
    (8, "Test / Reset", 0.900, 0.70, "Test top set, then begin the next block."),
]


def _round(v, step):
    return round(v / step) * step


def emulate(cmd, **f):
    g = lambda k, d: f.get(k, d)
    if cmd == "plan":
        return _plan(g)
    if cmd == "plates":
        return _plates(g)
    if cmd == "e1rm":
        return _e1rm(g)
    if cmd == "standards":
        return _standards(g)
    if cmd == "acwr":
        return _acwr(g)
    return {"error": "unknown command", "engine": "python-mirror"}


def _plan(g):
    goal = g("goal", "hypertrophy")
    days = max(1, min(6, int(float(g("days", 4)))))
    level = g("level", "beginner")
    lvl = {"advanced": 2, "intermediate": 1}.get(level, 0)
    age, kg, cm = float(g("age", 30)), float(g("weight", 75)), float(g("height", 175))
    female = g("sex", "m") == "f"
    act = float(g("activity", 1.55))

    bmr = 10 * kg + 6.25 * cm - 5 * age + (-161 if female else 5)
    tdee = bmr * act
    delta = {"strength": 0.08, "hypertrophy": 0.12, "fatloss": -0.18,
             "endurance": 0.02}.get(goal, 0.0)
    pkg = {"strength": 1.9, "hypertrophy": 2.0, "fatloss": 2.2,
           "endurance": 1.7}.get(goal, 1.8)
    fkg = {"strength": .9, "hypertrophy": .9, "fatloss": .8,
           "endurance": .8}.get(goal, .85)
    kcal = tdee * (1 + delta)
    protein, fat = pkg * kg, fkg * kg
    carbs = max(50, (kcal - protein * 4 - fat * 9) / 4)
    schema = SCHEMES.get(goal, SCHEMES["general"])

    split = SPLITS[days]
    out_split, total, seen = [], 0, {}
    for di, (label, slots) in enumerate(split):
        exs, day_sets, chosen = [], 0, set()
        for slot in slots:
            pool_all = [e for e in LIB if e[1] == slot]
            pool = [e for e in pool_all if e[3] <= lvl + 1] or pool_all
            occurrence = seen.get(slot, 0)
            seen[slot] = occurrence + 1
            want = 2 if slot in ("core", "arms") else 1
            for i in range(want):
                pref = 1 if (occurrence == 0 and i == 0) else 2
                group = ([e for e in pool if e[2] == pref]
                         or [e for e in pool if e[2] == 1] or pool)
                usable = [e for e in group if e[0] not in chosen] or pool
                e = usable[(di + occurrence) % len(usable)]
                chosen.add(e[0])
                st, lo, hi, rest, rpe = schema[e[2]]
                if i == 1:
                    st = max(2, st - 1)
                exs.append({"name": e[0], "pattern": e[1], "tier": e[2], "sets": st,
                            "reps": f"{lo}-{hi}", "rest_s": rest, "rpe": rpe})
                day_sets += st
        total += day_sets
        out_split.append({"day": di + 1, "label": label, "exercises": exs,
                          "working_sets": day_sets,
                          "est_minutes": math.ceil(day_sets * 2.6 + 8)})

    verdict = ("Low — good for a first block or a deload." if total < 40 else
               "Productive range for hypertrophy." if total <= 90 else
               "High — monitor sleep, joints and recovery closely.")

    return {
        "goal": goal, "level": level, "days": days,
        "bmr": round(bmr), "tdee": round(tdee), "target_kcal": _round(kcal, 10),
        "macros": {"protein_g": round(protein, 1), "carbs_g": round(carbs, 1),
                   "fat_g": round(fat, 1), "fibre_g": round(max(25, kcal / 1000 * 14), 1)},
        "protein_per_kg": round(protein / kg, 2),
        "block": [{"week": w, "phase": p, "load_pct": round(lf * 100), "vol_pct": round(vf * 100),
                   "note": note} for w, p, lf, vf, note in BLOCK],
        "split": out_split, "weekly_sets": total, "volume_verdict": verdict,
        "acwr_safe_cap": round(total * 1.3), "session_minutes": math.ceil(total * 2.6),
        "water_l": [round(kg * 0.033, 1), round(kg * 0.040, 1)],
        "engine": "python-mirror 1.4.0",
    }


def _plates(g):
    total, bar = float(g("total", 100)), float(g("bar", 20))
    per = (total - bar) / 2.0
    rem, used = per, []
    for p in (25, 20, 15, 10, 5, 2.5, 1.25):
        n = int(math.floor((rem + 1e-9) / p))
        if n:
            used.append({"kg": p, "count": n})
            rem -= n * p
    return {"total": total, "bar": bar, "per_side": round(per, 2), "plates": used,
            "loaded_total": round(total - rem * 2, 2), "remainder": round(rem, 3),
            "exact": abs(rem) < 1e-6 and per >= 0}


def _e1rm(g):
    w, r = float(g("weight", 100)), max(1.0, float(g("reps", 5)))
    ep, br, lo = w * (1 + r / 30), w * 36 / (37 - r), w * r ** 0.10
    est = w if r == 1 else (ep * .5 + br * .35 + lo * .15 if r <= 6
                            else ep * .35 + br * .3 + lo * .35)
    table = []
    for pct in (100, 95, 90, 85, 80, 75, 70, 65, 60):
        table.append({"pct": pct, "kg": _round(est * pct / 100, 2.5),
                      "reps": int(max(1, min(20, round(30 * (100 / pct - 1) + 1))))})
    return {"weight": w, "reps": r, "e1rm": _round(est, .5),
            "methods": {"epley": _round(ep, .5), "brzycki": _round(br, .5),
                        "lombardi": _round(lo, .5)},
            "percent_table": table}


def _standards(g):
    lift, w = g("lift", "squat"), float(g("weight", 100))
    bw = max(20.0, float(g("bw", 75)))
    female = g("sex", "m") == "f"
    T = {
        "squat": ((.75, 1, 1.25, 1.6, 1.9) if female else (1, 1.25, 1.6, 2, 2.4)),
        "bench": ((.4, .6, .8, 1, 1.2) if female else (.6, .85, 1.1, 1.4, 1.65)),
        "deadlift": ((.9, 1.2, 1.5, 1.85, 2.2) if female else (1.25, 1.5, 1.9, 2.3, 2.7)),
        "ohp": ((.25, .4, .55, .7, .85) if female else (.4, .55, .7, .9, 1.1)),
    }.get(lift, ((.5, .7, .9, 1.1, 1.3) if female else (.7, .9, 1.15, 1.4, 1.7)))
    ratio = w / bw
    idx = max([i for i in range(5) if ratio >= T[i]], default=0)
    names = ["Untrained", "Novice", "Intermediate", "Advanced", "Elite"]
    nxt = T[idx + 1] * bw if idx < 4 else w
    pct = min(100, (ratio - T[idx]) / (T[idx + 1] - T[idx]) * 100) if idx < 4 else 100
    return {"lift": lift, "weight": w, "bodyweight": bw, "ratio": round(ratio, 2),
            "level": names[idx], "level_index": idx,
            "to_next_kg": max(0, _round(nxt - w, 2.5)), "progress_pct": round(pct)}


def _acwr(g):
    hist = [float(x) for x in str(g("history", "")).split(",") if x.strip()]
    n = len(hist)
    if not n:
        return {"acute": 0, "chronic": 0, "ratio": 0, "band": "No data",
                "advice": "Log a few sessions first.", "samples": 0}
    acute = sum(hist[-7:]) / min(7, n)
    chronic = sum(hist) / n
    ratio = acute / chronic if chronic else 0
    if ratio < .8:
        band, adv = "Undertrained", "You have headroom. Add one set per lift."
    elif ratio <= 1.3:
        band, adv = "Sweet spot", "Load progression is well managed."
    elif ratio <= 1.5:
        band, adv = "Caution", "Spike detected. Hold volume for 5 days."
    else:
        band, adv = "High risk", "Deload now — cut volume ~40% this week."
    return {"acute": round(acute, 1), "chronic": round(chronic, 1), "ratio": round(ratio, 2),
            "band": band, "advice": adv, "samples": n}
