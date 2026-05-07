/* Anomaly detection. The hero alert is reserved for actionable institutional
   concerns — concentrations on school-related topics (complaints, frustrations,
   facilities, professors, etc.) and the explicit crisis pattern. Everything else
   (generic intensity spikes, sarcasm in non-school topics) becomes amber chips
   in the signal-strip rather than a giant red banner. */
window.InstAlerts = (function () {
  /* Topic labels are matched against this pattern to decide whether the
     concentration is "institutional" (admin can act on) vs personal/social. */
  const SCHOOL_PATTERN = /complain|frustrat|issue|problem|concern|noise|dorm|residence|facility|infrastructure|toxic|abus|profess|faculty|staff|department|college|univers|campus|ground|rule|policy|food|canteen|cafeteria|service|wifi|internet|exam|grad|adminis|tuition|fee|enrol|enroll/i;

  function isSchoolTopic(label) {
    return !!label && SCHOOL_PATTERN.test(label);
  }

  function compute(univ) {
    const posts = univ.posts || [];
    const alerts = [];
    const now = posts.reduce((m, p) => p.ts && p.ts > m ? p.ts : m, 0);
    if (!now) return alerts;
    const since24h = now - 24 * 3600;
    const recent = posts.filter(p => p.ts && p.ts >= since24h);
    const recentScored = recent.filter(p => p.A != null);

    /* Intensity spike — never hero-grade because intensity alone isn't actionable;
       caps out at warn level. */
    if (recentScored.length >= 5) {
      const meanA = recentScored.reduce((s, p) => s + p.A, 0) / recentScored.length;
      if (meanA > 6.2) {
        alerts.push({
          level: "warn", kind: "intensity",
          title: `Energy is up — last 24 h average intensity = ${meanA.toFixed(1)} / 9`,
          meta: `${recentScored.length} scored posts.`,
          targetId: "scatter-card",
          ctaLabel: `Inspect ${recentScored.length} posts`,
          schoolConcern: false,
        });
      }
    }

    /* Topic concentration — hero-grade ONLY when the dominant topic looks
       institutional (complaints, facilities, professors). Otherwise it's a
       neutral "trending topic" warn. */
    if (recent.length >= 10) {
      const buckets = new Map();
      for (const p of recent) buckets.set(p.topic_id, (buckets.get(p.topic_id) || 0) + 1);
      for (const [tid, c] of buckets) {
        const share = c / recent.length;
        if (share >= 0.30 && tid !== -1) {
          const t = univ.topics.find(t => t.id === tid);
          const label = (t && t.label) || `Topic ${tid}`;
          const school = isSchoolTopic(label);
          alerts.push({
            level: school && share >= 0.45 ? "crit"
                 : school                  ? "warn-strong"
                 :                            "warn",
            kind: "concentration", topicId: tid,
            title: school
              ? `Concentration — “${label}” is ${(share * 100).toFixed(0)}% of last 24 h`
              : `Trending — “${label}” is ${(share * 100).toFixed(0)}% of last 24 h`,
            meta: `${c} of ${recent.length} recent posts cluster on this topic.`,
            targetId: "topic-card",
            ctaLabel: `Filter to ${c} posts`,
            schoolConcern: school,
          });
        }
      }
    }

    /* Sarcasm on a school-related topic gets warn-strong; on personal topics
       it stays a soft amber chip. Crit only if the rate is extreme on a
       school-related topic. */
    for (const t of univ.topics || []) {
      if (t.sarcasm_rate != null && t.sarcasm_rate > 0.15 && t.scored >= 30) {
        const sarcCount = Math.round(t.sarcasm_rate * t.scored);
        const school = isSchoolTopic(t.label);
        alerts.push({
          level: school && t.sarcasm_rate > 0.25 ? "crit"
               : school                          ? "warn-strong"
               :                                   "warn",
          kind: "sarcasm", topicId: t.id,
          title: `Sarcasm — “${t.label}” at ${(t.sarcasm_rate * 100).toFixed(0)}%`,
          meta: `${sarcCount} of ${t.scored} scored posts. Hidden frustration likely.`,
          targetId: "feed-card-emotions",
          ctaLabel: `Read ${sarcCount} sarcastic posts`,
          schoolConcern: school,
        });
      }
    }

    /* Crisis pattern: low positivity + high intensity combined. Always hero
       because the human signal supersedes the topic — distress posts deserve
       the loudest treatment regardless of whether the topic looks institutional. */
    const crisis = recentScored.filter(p => p.V <= 3 && p.A >= 7);
    if (crisis.length >= 5) {
      alerts.push({
        level: "crit", kind: "crisis",
        title: `Distress signal — ${crisis.length} posts with low positivity and high intensity in 24 h`,
        meta: `Negative-and-stressed combination. Recommend guidance-office review.`,
        targetId: "feed-card-emotions",
        ctaLabel: `Open ${crisis.length} posts`,
        schoolConcern: true,
      });
    } else if (crisis.length >= 2) {
      alerts.push({
        level: "warn-strong", kind: "crisis",
        title: `${crisis.length} negative-and-stressed posts in 24 h`,
        meta: `Below crisis threshold but worth monitoring.`,
        targetId: "feed-card-emotions",
        ctaLabel: `Open ${crisis.length} posts`,
        schoolConcern: true,
      });
    }

    /* Stable order — crits first, then severity, then warn chips */
    const rank = { "crit": 0, "warn-strong": 1, "warn": 2 };
    alerts.sort((a, b) => (rank[a.level] ?? 9) - (rank[b.level] ?? 9));
    return alerts;
  }

  /* Hero zone: ONLY shows crit-level alerts where the underlying signal is
     institutionally actionable. Crisis is always crit. Concentration is crit
     only on school-related topics. */
  function renderHero(host, alerts, univ, ctx) {
    host.innerHTML = "";
    const heroAlert = alerts.find(a => a.level === "crit" && a.schoolConcern);
    if (heroAlert) {
      const el = document.createElement("section");
      el.className = "hero-alert";
      el.innerHTML = `
        <div class="ico">!</div>
        <div>
          <div class="title">${heroAlert.title}</div>
          <div class="body">${heroAlert.meta}</div>
        </div>
        <button class="review">${heroAlert.ctaLabel} →</button>`;
      el.querySelector(".review").addEventListener("click", () => handleCta(heroAlert, ctx));
      host.appendChild(el);
      return heroAlert;
    }
    if (alerts.length === 0) {
      const el = document.createElement("section");
      el.className = "calm-state";
      const lastTs = univ.posts.reduce((m, p) => p.ts > m ? p.ts : m, 0);
      const recent = univ.posts.filter(p => p.ts && p.ts >= lastTs - 24 * 3600).length;
      el.innerHTML = `
        <div class="ok-dot">✓</div>
        <div>
          <div class="copy"><b>All clear.</b> No anomalous emotional signals in the most recent 24-hour window.</div>
          <div class="meta">${recent} posts scanned · ${univ.posts.filter(p => p.V != null).length} with emotion scores.</div>
        </div>`;
      host.appendChild(el);
    }
    return null;
  }

  /* Strip of small chips: anything that isn't the hero. Cheap to scan. */
  function renderStrip(host, alerts, suppressed, ctx) {
    host.innerHTML = "";
    const remaining = alerts.filter(a => a !== suppressed);
    if (!remaining.length) return;
    for (const a of remaining) {
      const levelClass = a.level === "crit" ? "crit" : "";
      const kindClass  = a.kind === "sarcasm" ? "sarc" : "";
      const glyph = a.kind === "sarcasm" ? "S" : a.kind === "intensity" ? "↑" : a.kind === "concentration" ? "T" : "!";
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = `chip ${levelClass} ${kindClass}`.trim();
      chip.innerHTML = `<span class="glyph">${glyph}</span><span>${a.title}</span>`;
      chip.addEventListener("click", () => handleCta(a, ctx));
      host.appendChild(chip);
    }
  }

  function handleCta(a, ctx) {
    if (!ctx) return;
    if (a.kind === "concentration" && a.topicId != null) ctx.applyTopicFilter(a.topicId);
    if (a.kind === "sarcasm")  ctx.applyFeedSort("sarcasm");
    if (a.kind === "crisis")   ctx.applyFeedSort("negative");
    if (a.kind === "intensity") ctx.applyFeedSort("arousal");
    ctx.gotoPageForAlert(a);
  }

  return { compute, renderHero, renderStrip, isSchoolTopic };
})();
