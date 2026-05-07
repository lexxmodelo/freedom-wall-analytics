/* VAD color scales using OKLCH so they tint correctly in light/dark.
   V (valence) — coral→amber→teal continuum (negative→neutral→positive)
   A (arousal) — calm→agitated continuum
   D (dominance) — submissive→commanding continuum */
(function () {
  // Score 1..9 → OKLCH stops
  const V_HUE = (s) => {
    // s=1 (negative) red-orange, s=5 amber, s=9 (positive) teal-green
    const stops = [22, 30, 40, 60, 85, 130, 150, 160, 165];
    return stops[Math.max(0, Math.min(8, Math.round(s) - 1))];
  };
  const A_HUE = (s) => {
    // s=1 (calm) blue, s=9 (excited) red-orange
    const stops = [240, 220, 200, 60, 50, 40, 30, 22, 18];
    return stops[Math.max(0, Math.min(8, Math.round(s) - 1))];
  };
  const D_HUE = (s) => {
    // s=1 (helpless) purple, s=9 (commanding) gold
    const stops = [290, 280, 270, 260, 60, 70, 80, 90, 95];
    return stops[Math.max(0, Math.min(8, Math.round(s) - 1))];
  };

  function pick(score, hueFn) {
    if (score == null) return "oklch(80% 0.005 280)";
    const hue = hueFn(score);
    const L = 56 + (Math.round(score) - 1) * 1.2;
    return `oklch(${L}% 0.16 ${hue})`;
  }

  function valenceCalendar(score) {
    if (score == null) return "var(--bg-subtle)";
    if (score <= 3) return "oklch(60% 0.20 22)";   // negative
    if (score <= 6) return "oklch(78% 0.13 70)";   // mixed amber
    return "oklch(65% 0.14 155)";                  // positive
  }

  function valenceWord(score) {
    if (score == null) return "var(--text-muted)";
    return valenceCalendar(score);
  }

  window.VADColors = {
    V: (s) => pick(s, V_HUE),
    A: (s) => pick(s, A_HUE),
    D: (s) => pick(s, D_HUE),
    valenceCalendar,
    valenceWord,
  };
})();
