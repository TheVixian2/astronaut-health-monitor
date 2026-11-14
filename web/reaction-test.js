// Written with AI assistance (Claude Code, Anthropic) and reviewed by the team. See README "Use of AI".
// NASA's 3-minute Reaction Self Test (PVT-B; Basner et al. 2011) as an optional check-in step.
// Tap the pad (or press Space) as soon as the counter appears. Random waits of 1-4 s, for 3 minutes.
// A lapse is a reaction slower than 355 ms; a false start is a tap with no counter showing, or one
// faster than 100 ms. The result goes into the check-in as `reaction_test`
// {mean_rt_ms, lapses, false_starts, duration_s}, which the backend compares with the astronaut's own
// days 7-14. For a live demo, add ?rt_s=30 to the page URL to run a 30-second version.
(() => {
  const ISI_MS = [1000, 4000], LAPSE_MS = 355, FALSE_START_MS = 100, FEEDBACK_MS = 900, NO_RESPONSE_MS = 30000;
  const asked = Number(new URLSearchParams(location.search).get("rt_s"));
  const DURATION_MS = (asked >= 10 && asked <= 180 ? asked : 180) * 1000;
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const CSS = `
.rt-pad{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:170px;margin:10px 0;border-radius:14px;background:rgba(127,127,127,.12);border:1px solid rgba(127,127,127,.3);cursor:pointer;user-select:none;-webkit-user-select:none;touch-action:manipulation;outline:none}
.rt-pad:focus-visible{box-shadow:0 0 0 3px #3987e5}
.rt-pad.rt-on{background:rgba(232,163,61,.16);border-color:#e8a33d}
.rt-ctr{font:700 clamp(40px,9vw,60px)/1 ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums;color:#e8a33d;min-height:1em}
.rt-msg{font-size:15px;text-align:center;padding:0 12px}
.rt-bar{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px}
.rt-bar button{min-height:44px}
.rt-out{min-height:1.4em}`;

  function injectCss() {
    if (document.getElementById("rt-css")) return;
    const s = document.createElement("style");
    s.id = "rt-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function step(spec) {
    injectCss();
    const el = document.createElement("div");
    el.className = "ci-step";
    el.dataset.step = "reaction_test";
    el.hidden = true;
    const mins = DURATION_MS >= 60000 ? `${DURATION_MS / 60000} minutes` : `${DURATION_MS / 1000} seconds`;
    el.innerHTML = `
      <p class="ci-q">${esc(spec.name || "Reaction test")} <span class="muted small">(optional)</span></p>
      <p class="ci-hint muted">Tap the pad, or press Space, as soon as the counter appears. It takes ${mins}: find a quiet moment.</p>
      <div class="rt-pad" tabindex="0" role="button" aria-label="Reaction test pad">
        <span class="rt-ctr" aria-hidden="true"></span>
        <span class="rt-msg">Press Start, then watch this pad.</span>
      </div>
      <div class="rt-bar">
        <button type="button" class="rt-start">Start the test</button>
        <span class="rt-left small muted"></span>
      </div>
      <p class="rt-out small" aria-live="polite"></p>
      <input type="hidden" name="reaction_test" value="">
      <p class="ci-source muted small">${esc(spec.source || "")}</p>`;

    const pad = el.querySelector(".rt-pad"), ctr = el.querySelector(".rt-ctr"), msg = el.querySelector(".rt-msg");
    const startBtn = el.querySelector(".rt-start"), left = el.querySelector(".rt-left");
    const out = el.querySelector(".rt-out"), field = el.querySelector('input[name="reaction_test"]');
    let st = null;   // the running test, or null

    const clearTimers = () => {
      if (!st) return;
      clearTimeout(st.wait); clearTimeout(st.noResp); clearTimeout(st.next);
      cancelAnimationFrame(st.raf); clearInterval(st.clock);
    };
    const tickClock = () => {
      if (!st) return;
      if (el.hidden) return stop("Stopped because you left this step. Start again when you're ready.");
      const s = Math.max(0, Math.ceil((DURATION_MS - (performance.now() - st.t0)) / 1000));
      left.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} left`;
    };
    const showCounter = () => {
      if (performance.now() - st.t0 >= DURATION_MS) return finish();   // no new counter once time is up
      st.on = true; st.at = performance.now();
      pad.classList.add("rt-on"); msg.textContent = "";
      const draw = () => { if (!st || !st.on) return; ctr.textContent = String(Math.round(performance.now() - st.at)); st.raf = requestAnimationFrame(draw); };
      draw();
      st.noResp = setTimeout(() => respond(true), NO_RESPONSE_MS);
    };
    const schedule = () => {
      if (!st) return;
      if (performance.now() - st.t0 >= DURATION_MS) return finish();
      ctr.textContent = ""; msg.textContent = "Wait for the counter…"; pad.classList.remove("rt-on");
      st.wait = setTimeout(showCounter, ISI_MS[0] + Math.random() * (ISI_MS[1] - ISI_MS[0]));
    };
    const respond = timedOut => {
      if (!st) return;
      if (!st.on) {                          // tapped with no counter: a false start, and the wait starts over
        st.falseStarts += 1; clearTimeout(st.wait); clearTimeout(st.next);
        ctr.textContent = ""; msg.textContent = "Too early: wait for the counter.";
        st.next = setTimeout(schedule, FEEDBACK_MS);
        return;
      }
      const rt = performance.now() - st.at;
      st.on = false; cancelAnimationFrame(st.raf); clearTimeout(st.noResp); pad.classList.remove("rt-on");
      if (timedOut) { st.lapses += 1; ctr.textContent = ""; msg.textContent = "Missed: tap as soon as it appears."; }
      else if (rt < FALSE_START_MS) { st.falseStarts += 1; ctr.textContent = ""; msg.textContent = "Too early: wait for the counter."; }
      else { st.rts.push(rt); if (rt > LAPSE_MS) st.lapses += 1; ctr.textContent = String(Math.round(rt)); msg.textContent = "ms"; }
      st.next = setTimeout(schedule, FEEDBACK_MS);
    };
    const stop = text => {
      clearTimers(); st = null;
      pad.classList.remove("rt-on"); ctr.textContent = ""; msg.textContent = "Press Start, then watch this pad.";
      left.textContent = ""; startBtn.textContent = "Start the test"; startBtn.hidden = false;
      if (text) out.textContent = text;
    };
    const finish = () => {
      const r = st;
      const secs = Math.round((performance.now() - r.t0) / 1000);
      stop("");
      if (!r.rts.length) { out.textContent = "No reactions were recorded. Try again when you're ready."; return; }
      const mean = r.rts.reduce((a, b) => a + b, 0) / r.rts.length;
      field.value = JSON.stringify({ mean_rt_ms: Math.round(mean), lapses: r.lapses, false_starts: r.falseStarts, duration_s: secs });
      field.dispatchEvent(new Event("input", { bubbles: true }));   // the wizard's Next button updates
      out.textContent = `Average ${Math.round(mean)} ms, ${r.lapses} lapse${r.lapses === 1 ? "" : "s"} (slower than ${LAPSE_MS} ms), `
        + `${r.falseStarts} false start${r.falseStarts === 1 ? "" : "s"}. Saved with this check-in.`;
      startBtn.textContent = "Run it again";
    };

    startBtn.addEventListener("click", () => {
      field.value = ""; out.textContent = "";
      field.dispatchEvent(new Event("input", { bubbles: true }));
      st = { t0: performance.now(), on: false, at: 0, rts: [], lapses: 0, falseStarts: 0 };
      startBtn.hidden = true;
      st.clock = setInterval(tickClock, 250); tickClock();
      pad.focus({ preventScroll: true });
      schedule();
    });
    pad.addEventListener("pointerdown", e => { if (st) { e.preventDefault(); respond(false); } });
    pad.addEventListener("keydown", e => {
      if (st && (e.key === " " || e.key === "Enter")) { e.preventDefault(); e.stopPropagation(); if (!e.repeat) respond(false); }
    });
    queueMicrotask(() => el.closest("form")?.addEventListener("reset", () => { stop(""); out.textContent = ""; }));
    return el;
  }

  window.ReactionTest = { step };
})();
