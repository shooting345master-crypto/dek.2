// ============================================================================
//  FALCON FITNESS — Training Engine  (C++17)
//  ---------------------------------------------------------------------------
//  A dependency-free compute core that the Python API shells out to. It owns
//  the "hard" domain logic: energy/macro modelling, periodised program
//  generation, plate loading, 1RM estimation, ACWR injury-risk screening and
//  strength-standard scoring.
//
//  Build:  g++ -O3 -std=c++17 -o bin/falcon-engine main.cpp
//  Usage:  ./falcon-engine plan --goal strength --days 4 --level intermediate \
//                               --age 30 --sex m --weight 78 --height 178 \
//                               --activity 1.55
//          ./falcon-engine plates --total 142.5 --bar 20
//          ./falcon-engine e1rm --weight 120 --reps 3
//          ./falcon-engine standards --lift squat --weight 160 --bw 78 --sex m
//  All commands emit a single JSON object on stdout.
// ============================================================================

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// Tiny helpers
// ---------------------------------------------------------------------------
static std::string jstr(const std::string& s) { return "\"" + s + "\""; }

static double num(const std::string& v, double dflt) {
    try { return std::stod(v); } catch (...) { return dflt; }
}

static std::string fmt(double v, int prec = 1) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.*f", prec, v);
    std::string s(buf);
    // trim trailing zeros for cleanliness
    if (s.find('.') != std::string::npos) {
        while (!s.empty() && s.back() == '0') s.pop_back();
        if (!s.empty() && s.back() == '.') s.pop_back();
    }
    return s;
}

static double round_to(double v, double step) { return std::round(v / step) * step; }

// ---------------------------------------------------------------------------
// Argument parsing:  --key value  ->  map
// ---------------------------------------------------------------------------
static std::map<std::string, std::string> parse_flags(int argc, char** argv, int from) {
    std::map<std::string, std::string> f;
    for (int i = from; i < argc; ++i) {
        std::string k = argv[i];
        if (k.rfind("--", 0) == 0) {
            std::string key = k.substr(2);
            if (i + 1 < argc && std::string(argv[i + 1]).rfind("--", 0) != 0) {
                f[key] = argv[++i];
            } else {
                f[key] = "true";
            }
        }
    }
    return f;
}

static std::string get(const std::map<std::string, std::string>& f,
                       const std::string& k, const std::string& dflt) {
    auto it = f.find(k);
    return it == f.end() ? dflt : it->second;
}

// ===========================================================================
//  1. ENERGY & MACROS  (Mifflin-St Jeor + activity multiplier + goal delta)
// ===========================================================================
struct Macros { double kcal, protein, carbs, fat, fibre; };

static Macros compute_macros(double age, double sex_f, double kg, double cm,
                             double activity, const std::string& goal) {
    // Mifflin-St Jeor
    double bmr = 10.0 * kg + 6.25 * cm - 5.0 * age + (sex_f > 0.5 ? -161.0 : 5.0);
    double tdee = bmr * activity;

    double delta = 0.0;
    double p_per_kg = 1.8, f_per_kg = 0.85;
    if (goal == "strength")      { delta = tdee * 0.08;  p_per_kg = 1.9; f_per_kg = 0.9; }
    else if (goal == "hypertrophy") { delta = tdee * 0.12; p_per_kg = 2.0; f_per_kg = 0.9; }
    else if (goal == "fatloss")  { delta = -tdee * 0.18; p_per_kg = 2.2; f_per_kg = 0.8; }
    else if (goal == "endurance"){ delta = tdee * 0.02;  p_per_kg = 1.7; f_per_kg = 0.8; }
    else                         { delta = 0.0; p_per_kg = 1.8; f_per_kg = 0.85; }

    double kcal = tdee + delta;
    double protein = p_per_kg * kg;
    double fat = f_per_kg * kg;
    double carbs = std::max(50.0, (kcal - protein * 4.0 - fat * 9.0) / 4.0);
    double fibre = std::max(25.0, kcal / 1000.0 * 14.0);

    return {round_to(kcal, 10), round_to(protein, 1), round_to(carbs, 1),
            round_to(fat, 1), round_to(fibre, 1)};
}

// ===========================================================================
//  2. EXERCISE LIBRARY
//     slot = movement pattern; each entry: name, pattern, tier(1=primary,
//     2=secondary, 3=accessory), and pattern family for balance scoring.
// ===========================================================================
struct Ex {
    const char* name;
    const char* pattern;   // squat / hinge / push_h / push_v / pull_h / pull_v / core / arms / carry
    int tier;              // 1 = barbell primary, 2 = secondary, 3 = accessory/isolation
    int minLevel;          // 0 beginner-friendly, 1 intermediate+, 2 advanced
};

static const std::vector<Ex> LIB = {
    // ---- squat / knee-dominant
    {"Back Squat",            "squat",  1, 1},
    {"Front Squat",           "squat",  1, 2},
    {"Hack Squat",            "squat",  2, 1},
    {"Leg Press",             "squat",  2, 0},
    {"Goblet Squat",          "squat",  2, 0},
    {"Bulgarian Split Squat", "squat",  3, 1},
    {"Walking Lunge",         "squat",  3, 0},
    // ---- hinge / posterior
    {"Deadlift",              "hinge",  1, 1},
    {"Romanian Deadlift",     "hinge",  1, 1},
    {"Trap-Bar Deadlift",     "hinge",  2, 0},
    {"Hip Thrust",            "hinge",  2, 0},
    {"Kettlebell Swing",      "hinge",  3, 0},
    {"Leg Curl",              "hinge",  3, 0},
    {"Back Extension",        "hinge",  3, 0},
    // ---- horizontal push
    {"Bench Press",           "push_h", 1, 1},
    {"Incline Bench Press",   "push_h", 2, 1},
    {"Dumbbell Bench Press",  "push_h", 2, 0},
    {"Push-Up",               "push_h", 3, 0},
    {"Dip",                   "push_h", 3, 1},
    {"Cable Fly",             "push_h", 3, 0},
    // ---- vertical push
    {"Overhead Press",        "push_v", 1, 1},
    {"Push Press",            "push_v", 2, 2},
    {"Seated DB Press",       "push_v", 2, 0},
    {"Landmine Press",        "push_v", 3, 0},
    {"Lateral Raise",         "push_v", 3, 0},
    // ---- horizontal pull
    {"Barbell Row",           "pull_h", 1, 1},
    {"Pendlay Row",           "pull_h", 1, 2},
    {"Chest-Supported Row",   "pull_h", 2, 0},
    {"Seated Cable Row",      "pull_h", 2, 0},
    {"Face Pull",             "pull_h", 3, 0},
    // ---- vertical pull
    {"Weighted Pull-Up",      "pull_v", 1, 2},
    {"Lat Pulldown",          "pull_v", 2, 0},
    {"Assisted Pull-Up",      "pull_v", 2, 0},
    {"Straight-Arm Pulldown", "pull_v", 3, 0},
    // ---- core
    {"Hanging Leg Raise",     "core",   3, 1},
    {"Ab Wheel Rollout",      "core",   3, 1},
    {"Cable Crunch",          "core",   3, 0},
    {"Pallof Press",          "core",   3, 0},
    {"Plank (weighted)",      "core",   3, 0},
    // ---- arms
    {"Barbell Curl",          "arms",   3, 0},
    {"Hammer Curl",           "arms",   3, 0},
    {"Skull Crusher",         "arms",   3, 0},
    {"Cable Pushdown",        "arms",   3, 0},
    // ---- carries / conditioning
    {"Farmer Carry",          "carry",  3, 0},
    {"Sled Push",             "carry",  3, 0},
};

// Programming templates: goal -> strength/hypertrophy rep-zone rules
struct Scheme { int sets; int reps_lo; int reps_hi; int rest; int rpe; };

static Scheme scheme_for(const std::string& goal, int tier) {
    if (goal == "strength") {
        if (tier == 1) return {5, 3, 5, 210, 8};
        if (tier == 2) return {4, 5, 6, 150, 8};
        return {3, 8, 10, 75, 8};
    }
    if (goal == "hypertrophy") {
        if (tier == 1) return {4, 6, 8, 150, 9};
        if (tier == 2) return {4, 8, 10, 105, 9};
        return {3, 12, 15, 60, 9};
    }
    if (goal == "fatloss") {
        if (tier == 1) return {4, 6, 8, 120, 8};
        if (tier == 2) return {3, 10, 12, 75, 8};
        return {3, 15, 20, 45, 9};
    }
    if (goal == "endurance") {
        if (tier == 1) return {3, 10, 12, 90, 7};
        if (tier == 2) return {3, 12, 15, 60, 7};
        return {2, 15, 20, 45, 8};
    }
    return {4, 8, 12, 90, 8};  // general
}

// ===========================================================================
//  3. SPLIT LIBRARY
// ===========================================================================
struct Day { std::string label; std::vector<std::string> slots; };

static std::vector<Day> split_for(int days, const std::string& goal) {
    std::vector<Day> d;
    switch (days) {
        case 1:
            d = {{"Full Body", {"squat", "push_h", "pull_h", "core"}}};
            break;
        case 2:
            d = {{"Full Body A", {"squat", "push_h", "pull_h", "arms"}},
                 {"Full Body B", {"hinge", "push_v", "pull_v", "core"}}};
            break;
        case 3:
            if (goal == "endurance" || goal == "fatloss")
                d = {{"Full Body A", {"squat", "push_h", "pull_h", "carry"}},
                     {"Conditioning", {"hinge", "carry", "core", "arms"}},
                     {"Full Body B", {"squat", "push_v", "pull_v", "core"}}};
            else
                d = {{"Push", {"push_h", "push_v", "arms", "core"}},
                     {"Pull", {"pull_v", "pull_h", "arms", "core"}},
                     {"Legs", {"squat", "hinge", "core", "carry"}}};
            break;
        case 4:
            d = {{"Upper Strength", {"push_h", "pull_h", "push_v", "pull_v"}},
                 {"Lower Strength", {"squat", "hinge", "core", "carry"}},
                 {"Upper Volume", {"push_h", "pull_v", "pull_h", "arms"}},
                 {"Lower Volume", {"hinge", "squat", "core", "carry"}}};
            break;
        case 5:
            d = {{"Push", {"push_h", "push_v", "arms", "core"}},
                 {"Pull", {"pull_v", "pull_h", "arms", "core"}},
                 {"Legs", {"squat", "hinge", "core", "carry"}},
                 {"Upper", {"push_h", "pull_h", "push_v", "pull_h"}},
                 {"Lower", {"squat", "hinge", "core", "carry"}}};
            break;
        default:
            d = {{"Push A", {"push_h", "push_v", "arms", "core"}},
                 {"Pull A", {"pull_v", "pull_h", "arms", "core"}},
                 {"Legs A", {"squat", "hinge", "core", "carry"}},
                 {"Push B", {"push_v", "push_h", "arms", "core"}},
                 {"Pull B", {"pull_h", "pull_v", "arms", "core"}},
                 {"Legs B", {"hinge", "squat", "core", "carry"}}};
            break;
    }
    return d;
}

// Deterministic-but-varied pick.
//   occurrence = how many times this movement pattern has already appeared in
//   the week. The first exposure gets the barbell primary (tier 1); later
//   exposures get a variant (tier 2) so volume days are not carbon copies.
static std::vector<const Ex*> pick(const std::string& slot, int level, int dayIdx,
                                   int count, int occurrence) {
    std::vector<const Ex*> filtered, all;
    for (const auto& e : LIB) {
        if (slot != e.pattern) continue;
        all.push_back(&e);
        if (e.minLevel <= level + 1) filtered.push_back(&e);
    }
    const std::vector<const Ex*>& base = filtered.empty() ? all : filtered;
    if (base.empty()) return {};

    auto tier_group = [&](int tier) {
        std::vector<const Ex*> g;
        for (auto* e : base) if (e->tier == tier) g.push_back(e);
        return g;
    };

    std::vector<const Ex*> out;
    for (int i = 0; i < count; ++i) {
        int prefTier = (occurrence == 0 && i == 0) ? 1 : 2;
        std::vector<const Ex*> g = tier_group(prefTier);
        if (g.empty()) g = tier_group(1);
        if (g.empty()) g = base;

        // avoid repeating a lift already chosen for this day
        std::vector<const Ex*> usable;
        for (auto* e : g) {
            bool dup = false;
            for (auto* o : out) if (o == e) dup = true;
            if (!dup) usable.push_back(e);
        }
        if (usable.empty()) usable = base;

        size_t idx = (size_t)(dayIdx + occurrence) % usable.size();
        out.push_back(usable[idx]);
    }
    return out;
}

// ===========================================================================
//  4. PERIODISATION (8-week block, accumulation -> deload -> intensification)
// ===========================================================================
struct WeekSpec { int week; std::string phase; double loadFactor; double volFactor; std::string note; };

static std::vector<WeekSpec> periodise(const std::string& goal) {
    std::vector<WeekSpec> w;
    double peak = (goal == "strength") ? 1.075 : (goal == "fatloss" ? 1.03 : 1.06);
    w.push_back({1, "Accumulation",   1.000, 1.00, "Technique first. Leave 2 reps in reserve on every set."});
    w.push_back({2, "Accumulation",   1.025, 1.10, "Add one set to primary lifts, same loads."});
    w.push_back({3, "Accumulation",   1.050, 1.20, "Peak volume week. Sleep and protein are non-negotiable."});
    w.push_back({4, "Deload",         0.850, 0.55, "Deload. Move well, drop all sets to RPE 6."});
    w.push_back({5, "Intensification",1.030, 1.00, "Re-enter at week-2 volumes with sharper intent."});
    w.push_back({6, "Intensification",1.055, 1.05, "Heavier singles on primary, then back-off sets."});
    w.push_back({7, "Peak",           peak,  0.90, "Heaviest week. Cap accessories at 2 sets."});
    w.push_back({8, "Test / Reset",   0.900, 0.70, "Test top set, then begin the next block."});
    return w;
}

// ===========================================================================
//  5. COMMAND: plan
// ===========================================================================
static int cmd_plan(const std::map<std::string, std::string>& f) {
    std::string goal = get(f, "goal", "hypertrophy");
    int days = (int)std::max(1.0, std::min(6.0, num(get(f, "days", "4"), 4)));
    std::string level = get(f, "level", "beginner");
    int lvl = level == "advanced" ? 2 : (level == "intermediate" ? 1 : 0);
    double age = num(get(f, "age", "30"), 30);
    double sex_f = get(f, "sex", "m") == "f" ? 1 : 0;
    double kg = std::max(30.0, num(get(f, "weight", "75"), 75));
    double cm = std::max(120.0, num(get(f, "height", "175"), 175));
    double activity = std::max(1.2, std::min(1.9, num(get(f, "activity", "1.55"), 1.55)));

    Macros m = compute_macros(age, sex_f, kg, cm, activity, goal);
    std::vector<Day> split = split_for(days, goal);

    double bmr = 10 * kg + 6.25 * cm - 5 * age + (sex_f > 0.5 ? -161.0 : 5.0);
    std::ostringstream j;
    j << "{";
    j << "\"goal\":" << jstr(goal) << ",";
    j << "\"level\":" << jstr(level) << ",";
    j << "\"days\":" << days << ",";
    j << "\"bmr\":" << fmt(bmr, 0) << ",";
    j << "\"tdee\":" << fmt(bmr * activity, 0) << ",";
    j << "\"target_kcal\":" << fmt(m.kcal, 0) << ",";
    j << "\"macros\":{\"protein_g\":" << fmt(m.protein, 0)
      << ",\"carbs_g\":" << fmt(m.carbs, 0)
      << ",\"fat_g\":" << fmt(m.fat, 0)
      << ",\"fibre_g\":" << fmt(m.fibre, 0) << "},";
    j << "\"protein_per_kg\":" << fmt(m.protein / kg, 2) << ",";

    // ---- weeks
    j << "\"block\":[";
    auto weeks = periodise(goal);
    for (size_t i = 0; i < weeks.size(); ++i) {
        if (i) j << ",";
        j << "{\"week\":" << weeks[i].week << ",\"phase\":" << jstr(weeks[i].phase)
          << ",\"load_pct\":" << fmt(weeks[i].loadFactor * 100, 0)
          << ",\"vol_pct\":" << fmt(weeks[i].volFactor * 100, 0)
          << ",\"note\":" << jstr(weeks[i].note) << "}";
    }
    j << "],";

    // ---- split with exercises
    int totalSets = 0;
    std::map<std::string, int> seen;   // movement pattern -> exposures so far
    j << "\"split\":[";
    for (size_t d = 0; d < split.size(); ++d) {
        if (d) j << ",";
        j << "{\"day\":" << (int)d + 1 << ",\"label\":" << jstr(split[d].label) << ",\"exercises\":[";
        bool first = true;
        int daySets = 0;
        for (const auto& slot : split[d].slots) {
            // One lift per primary pattern keeps weekly volume inside a
            // productive band; accessory patterns get a second movement.
            int want = (slot == "core" || slot == "arms") ? 2 : 1;
            auto picks = pick(slot, lvl, (int)d, want, seen[slot]++);
            int k = 0;
            for (auto* e : picks) {
                Scheme s = scheme_for(goal, e->tier);
                if (k == 1) s.sets = std::max(2, s.sets - 1);   // second movement = back-off
                ++k;
                if (!first) j << ",";
                first = false;
                j << "{\"name\":" << jstr(e->name)
                  << ",\"pattern\":" << jstr(e->pattern)
                  << ",\"tier\":" << e->tier
                  << ",\"sets\":" << s.sets
                  << ",\"reps\":" << jstr(std::to_string(s.reps_lo) + "-" + std::to_string(s.reps_hi))
                  << ",\"rest_s\":" << s.rest
                  << ",\"rpe\":" << s.rpe << "}";
                daySets += s.sets;
            }
        }
        totalSets += daySets;
        j << "],\"working_sets\":" << daySets << ",\"est_minutes\":" << (int)std::ceil(daySets * 2.6 + 8) << "}";
    }
    j << "],";

    // ---- weekly volume landmarks (sets per muscle group, MEV/MAV heuristic)
    int weeklySets = totalSets;
    std::string verdict;
    if (weeklySets < 40) verdict = "Low — good for a first block or a deload.";
    else if (weeklySets <= 90) verdict = "Productive range for hypertrophy.";
    else verdict = "High — monitor sleep, joints and recovery closely.";

    j << "\"weekly_sets\":" << weeklySets << ",";
    j << "\"volume_verdict\":" << jstr(verdict) << ",";
    j << "\"acwr_safe_cap\":" << fmt(weeklySets * 1.3, 0) << ",";
    j << "\"session_minutes\":" << (int)std::ceil(totalSets * 2.6) << ",";
    j << "\"water_l\":[" << fmt(kg * 0.033, 1) << "," << fmt(kg * 0.040, 1) << "],";
    j << "\"engine\":\"falcon-engine 1.4.0 (c++17)\"";
    j << "}";

    std::cout << j.str() << "\n";
    return 0;
}

// ===========================================================================
//  6. COMMAND: plates  (greedy per-side loading, IPF plate colours)
// ===========================================================================
static int cmd_plates(const std::map<std::string, std::string>& f) {
    double total = num(get(f, "total", "100"), 100);
    double bar = num(get(f, "bar", "20"), 20);
    std::vector<double> avail = {25, 20, 15, 10, 5, 2.5, 1.25};

    double perSide = (total - bar) / 2.0;
    std::ostringstream j;
    j << "{\"total\":" << fmt(total, 2) << ",\"bar\":" << fmt(bar, 1) << ",";
    j << "\"per_side\":" << fmt(perSide, 2) << ",";
    j << "\"plates\":[";
    std::vector<std::pair<double,int>> used;
    double rem = perSide;
    bool ok = perSide >= 0;
    for (double p : avail) {
        int n = (int)std::floor((rem + 1e-9) / p);
        if (n > 0) { used.push_back({p, n}); rem -= n * p; }
    }
    for (size_t i = 0; i < used.size(); ++i) {
        if (i) j << ",";
        j << "{\"kg\":" << fmt(used[i].first, 2) << ",\"count\":" << used[i].second << "}";
    }
    j << "],";
    j << "\"loaded_total\":" << fmt(total - rem * 2, 2) << ",";
    j << "\"remainder\":" << fmt(rem, 3) << ",";
    j << "\"exact\":" << ((std::fabs(rem) < 1e-6 && ok) ? "true" : "false");
    j << "}";
    std::cout << j.str() << "\n";
    return 0;
}

// ===========================================================================
//  7. COMMAND: e1rm  (Epley + Brzycki ensemble, rounded to nearest 0.5)
// ===========================================================================
static int cmd_e1rm(const std::map<std::string, std::string>& f) {
    double w = num(get(f, "weight", "100"), 100);
    double r = std::max(1.0, num(get(f, "reps", "5"), 5));

    double epley = w * (1.0 + r / 30.0);
    double brzycki = w * 36.0 / (37.0 - r);
    double lombardi = w * std::pow(r, 0.10);
    std::vector<double> ens = {epley, brzycki, lombardi};
    // Epley weighted highest for r<=6, Lombardi for high reps
    double est = r <= 6 ? (epley * 0.5 + brzycki * 0.35 + lombardi * 0.15)
                        : (epley * 0.35 + brzycki * 0.3 + lombardi * 0.35);
    if (r == 1) est = w;

    std::ostringstream j;
    j << "{\"weight\":" << fmt(w, 1) << ",\"reps\":" << fmt(r, 0) << ",";
    j << "\"e1rm\":" << fmt(round_to(est, 0.5), 1) << ",";
    j << "\"methods\":{\"epley\":" << fmt(round_to(epley, 0.5), 1)
      << ",\"brzycki\":" << fmt(round_to(brzycki, 0.5), 1)
      << ",\"lombardi\":" << fmt(round_to(lombardi, 0.5), 1) << "},";
    j << "\"percent_table\":[";
    double pcts[] = {100, 95, 90, 85, 80, 75, 70, 65, 60};
    for (int i = 0; i < 9; ++i) {
        if (i) j << ",";
        double target = round_to(est * pcts[i] / 100.0, 2.5);
        double reps = 30.0 * (100.0 / pcts[i] - 1.0) + 1.0;
        reps = std::max(1.0, std::min(20.0, std::round(reps)));
        j << "{\"pct\":" << pcts[i] << ",\"kg\":" << fmt(target, 1)
          << ",\"reps\":" << (int)std::min(20.0, std::round(reps)) << "}";
    }
    j << "]}";
    std::cout << j.str() << "\n";
    return 0;
}

// ===========================================================================
//  8. COMMAND: standards  (strength level vs bodyweight)
// ===========================================================================
static int cmd_standards(const std::map<std::string, std::string>& f) {
    std::string lift = get(f, "lift", "squat");
    double w = num(get(f, "weight", "100"), 100);
    double bw = std::max(20.0, num(get(f, "bw", "75"), 75));
    bool female = get(f, "sex", "m") == "f";

    // ratio thresholds (untrained / novice / intermediate / advanced / elite)
    double t[5];
    if (lift == "squat")  female ? (t[0]=0.75,t[1]=1.0,t[2]=1.25,t[3]=1.6,t[4]=1.9)
                                 : (t[0]=1.0,t[1]=1.25,t[2]=1.6,t[3]=2.0,t[4]=2.4);
    else if (lift == "bench") female ? (t[0]=0.4,t[1]=0.6,t[2]=0.8,t[3]=1.0,t[4]=1.2)
                                     : (t[0]=0.6,t[1]=0.85,t[2]=1.1,t[3]=1.4,t[4]=1.65);
    else if (lift == "deadlift") female ? (t[0]=0.9,t[1]=1.2,t[2]=1.5,t[3]=1.85,t[4]=2.2)
                                        : (t[0]=1.25,t[1]=1.5,t[2]=1.9,t[3]=2.3,t[4]=2.7);
    else if (lift == "ohp") female ? (t[0]=0.25,t[1]=0.4,t[2]=0.55,t[3]=0.7,t[4]=0.85)
                                   : (t[0]=0.4,t[1]=0.55,t[2]=0.7,t[3]=0.9,t[4]=1.1);
    else  female ? (t[0]=0.5,t[1]=0.7,t[2]=0.9,t[3]=1.1,t[4]=1.3)
                 : (t[0]=0.7,t[1]=0.9,t[2]=1.15,t[3]=1.4,t[4]=1.7);

    double ratio = w / bw;
    const char* names[5] = {"Untrained", "Novice", "Intermediate", "Advanced", "Elite"};
    int idx = 0;
    for (int i = 0; i < 5; ++i) if (ratio >= t[i]) idx = i;
    double next = idx < 4 ? t[idx + 1] * bw : w;
    double pct = idx < 4 ? std::min(100.0, (ratio - t[idx]) / (t[idx + 1] - t[idx]) * 100.0) : 100.0;

    std::ostringstream j;
    j << "{\"lift\":" << jstr(lift) << ",\"weight\":" << fmt(w, 1) << ",\"bodyweight\":" << fmt(bw, 1)
      << ",\"ratio\":" << fmt(ratio, 2)
      << ",\"level\":" << jstr(names[idx])
      << ",\"level_index\":" << idx
      << ",\"to_next_kg\":" << fmt(std::max(0.0, round_to(next - w, 2.5)), 1)
      << ",\"progress_pct\":" << fmt(pct, 0) << "}";
    std::cout << j.str() << "\n";
    return 0;
}

// ===========================================================================
//  9. COMMAND: acwr  (acute:chronic workload ratio — injury risk screen)
// ===========================================================================
static int cmd_acwr(const std::map<std::string, std::string>& f) {
    // --history 1,2,3,... (last N daily loads, most recent last)
    std::string hist = get(f, "history", "");
    std::vector<double> v;
    std::stringstream ss(hist);
    std::string tok;
    while (std::getline(ss, tok, ',')) if (!tok.empty()) v.push_back(num(tok, 0));

    size_t n = v.size();
    double chronic = 0, acute = 0;
    for (size_t i = 0; i < n; ++i) {
        chronic += v[i];
        if (i + 7 >= n) acute += v[i];   // trailing 7-day window
    }
    double window = (double)std::min<size_t>(7, n);
    double a = n ? acute / window : 0;
    double c = n ? chronic / (double)n : 0;
    double ratio = c > 0 ? a / c : 0;

    std::string band, advice;
    if (ratio < 0.8)        { band = "Undertrained";  advice = "You have headroom. Add one set per lift."; }
    else if (ratio <= 1.3)  { band = "Sweet spot";    advice = "Load progression is well managed."; }
    else if (ratio <= 1.5)  { band = "Caution";       advice = "Spike detected. Hold volume for 5 days."; }
    else                    { band = "High risk";     advice = "Deload now — cut volume ~40% this week."; }

    std::ostringstream j;
    j << "{\"acute\":" << fmt(a, 1) << ",\"chronic\":" << fmt(c, 1)
      << ",\"ratio\":" << fmt(ratio, 2) << ",\"band\":" << jstr(band)
      << ",\"advice\":" << jstr(advice) << ",\"samples\":" << (int)n << "}";
    std::cout << j.str() << "\n";
    return 0;
}

// ===========================================================================
int main(int argc, char** argv) {
    if (argc < 2) {
        std::cout << "{\"error\":\"usage: falcon-engine <plan|plates|e1rm|standards|acwr> [flags]\"}\n";
        return 2;
    }
    std::string cmd = argv[1];
    auto f = parse_flags(argc, argv, 2);
    try {
        if (cmd == "plan")      return cmd_plan(f);
        if (cmd == "plates")    return cmd_plates(f);
        if (cmd == "e1rm")      return cmd_e1rm(f);
        if (cmd == "standards") return cmd_standards(f);
        if (cmd == "acwr")      return cmd_acwr(f);
        if (cmd == "--version" || cmd == "version")
            { std::cout << "{\"engine\":\"falcon-engine\",\"version\":\"1.4.0\",\"cxx\":\"17\"}\n"; return 0; }
    } catch (const std::exception& e) {
        std::cout << "{\"error\":" << jstr(e.what()) << "}\n";
        return 1;
    }
    std::cout << "{\"error\":\"unknown command\"}\n";
    return 2;
}
