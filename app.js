/* ==========================================================================
   FALCON FITNESS — front-end controller
   All computation that matters happens in the C++ engine via /api/*.
   This file handles state, rendering and interaction only.
   ========================================================================== */
(function () {
  'use strict';

  /* ----------------------------------------------------------------------
     OPENING HOURS.
     Same seven days a week, confirmed by the owner: 6:30 am to 11:00 pm.
     OPEN_AT / CLOSE_AT are decimal hours and drive the live badge:
       before 6:30        -> "Closed · opens in 3h 20m"
       6:30 to 10:00 pm   -> "Open now · until 11:00 pm"
       10:00 pm to 11:00  -> "Closing soon · 42 min left"   (CLOSING_WINDOW)
       after 11:00 pm     -> "Closed · opens in 7h 30m"
     If you ever change the hours, change OPEN_AT and CLOSE_AT. Every piece of
     text on the page (the hours row and the badge) is derived from them.
     ---------------------------------------------------------------------- */
  var CLOSING_WINDOW = 60;  /* show "closing soon" for the final hour */
  var OPEN_AT = 6.5;    /* 6:30 am */
  var CLOSE_AT = 23;    /* 11:00 pm */

  /* ---------- tiny helpers (declared first: no TDZ surprises) ---------- */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var on = function (el, ev, fn, opt) { if (el) el.addEventListener(ev, fn, opt); };
  var clamp = function (n, a, b) { return Math.min(b, Math.max(a, n)); };
  var fmt = function (n, d) { return Number(n).toFixed(d === undefined ? 1 : d).replace(/\.0$/, ''); };

  var state = {
    goal: 'strength',
    days: 4,
    level: 'intermediate',
    sex: 'm',
    age: 29,
    weight: 74,
    height: 174,
    activity: 1.55,
    plan: null,
    lastSession: 0
  };

  var ACTIVITY_LABELS = ['Desk-bound', 'Light', 'Moderate', 'High', 'Athlete'];
  var ACTIVITY_VALUES = [1.2, 1.375, 1.55, 1.725, 1.9];

  /* ======================================================================
     1. TOASTS
     ====================================================================== */
  var toastHost = $('#toasts');
  function toast(msg, kind) {
    if (!toastHost) return;
    var el = document.createElement('div');
    el.className = 'toast' + (kind ? ' toast-' + kind : '');
    el.textContent = msg;
    toastHost.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('is-in'); });
    setTimeout(function () {
      el.classList.remove('is-in');
      setTimeout(function () { el.remove(); }, 400);
    }, 4200);
  }

  /* ======================================================================
     2. NETWORK
     ====================================================================== */
  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw Object.assign(new Error(data.error || 'Request failed'), { data: data });
        return data;
      });
    });
  }

  /* ======================================================================
     3. REVEAL ON SCROLL
     ====================================================================== */
  function initReveal() {
    var items = $$('.reveal');
    if (!items.length) return;

    // Respect the OS "reduce motion" setting — show everything immediately.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      items.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }
    if (!('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-in');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });

    items.forEach(function (el, i) {
      el.style.transitionDelay = (Math.min(i % 6, 4) * 60) + 'ms';
      io.observe(el);
    });

    // SAFETY NET: a fast flick to the bottom skips elements entirely, and an
    // IntersectionObserver that never saw them never fires — leaving sections
    // permanently invisible when the visitor scrolls back up. This sweep marks
    // anything at or above the fold as revealed, however it got there.
    var ticking = false;
    function sweep() {
      ticking = false;
      for (var i = items.length - 1; i >= 0; i--) {
        var el = items[i];
        if (el.classList.contains('is-in')) { items.splice(i, 1); continue; }
        if (el.getBoundingClientRect().top < window.innerHeight * 1.05) {
          el.classList.add('is-in');
          io.unobserve(el);
          items.splice(i, 1);
        }
      }
      if (!items.length) window.removeEventListener('scroll', onScrollSweep);
    }
    function onScrollSweep() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(sweep);
    }
    window.addEventListener('scroll', onScrollSweep, { passive: true });
    window.addEventListener('resize', onScrollSweep, { passive: true });
    setTimeout(sweep, 400);
  }

  /* ======================================================================
     4. NAV / PROGRESS / MENU
     ====================================================================== */
  function initNav() {
    // The home page uses ids (#nav / #burger / #navLinks). Every other page
    // renders shell.html, which uses classes instead -- so fall back to those,
    // otherwise the menu button on account/admin/login pages does nothing and
    // there is no way to sign out on a phone.
    var nav = $('#nav') || $('.nav');
    var burger = $('#burger') || $('.burger');
    var links = $('#navLinks') || $('.nav-links');
    var bar = $('#scrollProgress');
    var sections = $$('main section[id]');

    function onScroll() {
      var y = window.scrollY || window.pageYOffset;
      if (nav) nav.classList.toggle('is-stuck', y > 30);
      if (bar) {
        var h = document.documentElement.scrollHeight - window.innerHeight;
        bar.style.width = (h > 0 ? (y / h) * 100 : 0) + '%';
      }
      var current = '';
      sections.forEach(function (s) {
        if (s.offsetTop - 140 <= y) current = s.id;
      });
      $$('[data-nav]', links || document).forEach(function (a) {
        a.classList.toggle('is-active', a.getAttribute('href') === '#' + current);
      });
    }

    on(window, 'scroll', onScroll, { passive: true });
    onScroll();

    function closeMenu() {
      if (!links) return;
      links.classList.remove('is-open');
      if (burger) {
        burger.classList.remove('is-open');
        burger.setAttribute('aria-expanded', 'false');
      }
      document.body.classList.remove('no-scroll');
    }

    if (burger && links) on(burger, 'click', function () {
      var open = links.classList.toggle('is-open');
      burger.classList.toggle('is-open', open);
      burger.setAttribute('aria-expanded', open ? 'true' : 'false');
      document.body.classList.toggle('no-scroll', open);
    });

    $$('a', links || document.createElement('div')).forEach(function (a) {
      on(a, 'click', closeMenu);
    });
    on(document, 'keydown', function (e) { if (e.key === 'Escape') closeMenu(); });
  }

  /* ======================================================================
     5. CURSOR HALO
     ====================================================================== */
  function initCursor() {
    var halo = $('#cursorHalo');
    if (!halo || window.matchMedia('(pointer: coarse)').matches) return;
    var x = 0, y = 0, cx = 0, cy = 0;
    on(document, 'mousemove', function (e) { x = e.clientX; y = e.clientY; halo.classList.add('is-live'); });
    (function loop() {
      cx += (x - cx) * 0.14;
      cy += (y - cy) * 0.14;
      halo.style.transform = 'translate3d(' + (cx - 180) + 'px,' + (cy - 180) + 'px,0)';
      requestAnimationFrame(loop);
    })();
  }

  /* ======================================================================
     6. HERO: clock, open badge, ticker
     ====================================================================== */

  /* "6:30 am" / "11:00 pm" from decimal hours, so the printed text and the
     badge logic can never drift apart. */
  function hhmm(dec) {
    var h = Math.floor(dec), m = Math.round((dec - h) * 60);
    var ampm = h < 12 ? 'am' : 'pm';
    var h12 = h % 12; if (h12 === 0) h12 = 12;
    return h12 + ':' + String(m).padStart(2, '0') + ' ' + ampm;
  }

  function applyHours() {
    var weekEl = $('#hoursWeek');
    var label = $('#openLabel');
    var dot = $('#openDot');

    if (weekEl) weekEl.textContent = hhmm(OPEN_AT) + ' – ' + hhmm(CLOSE_AT);

    if (!dot || !label) return;
    /* Hours are the same seven days a week, so the day does not enter into it. */
    var now = new Date();
    var mins = now.getHours() * 60 + now.getMinutes();
    var openMins = Math.round(OPEN_AT * 60);
    var closeMins = Math.round(CLOSE_AT * 60);

    var state, text;
    if (mins >= openMins && mins < closeMins) {
      var left = closeMins - mins;
      /* Inside opening hours, but near the end: CLOSING instead of OPEN. */
      if (left <= CLOSING_WINDOW) {
        state = 'is-closing';
        text = 'Closing soon · ' + left + ' min left';
      } else {
        state = 'is-open';
        text = 'Open now · until ' + hhmm(CLOSE_AT);
      }
    } else {
      state = 'is-closed';
      var until = mins < openMins ? openMins - mins : (24 * 60 - mins) + openMins;
      var h = Math.floor(until / 60), m = until % 60;
      text = 'Closed · opens in ' + (h ? h + 'h ' : '') + m + 'm';
    }

    dot.className = 'pulse-dot ' + state;
    label.textContent = text;
  }

  function initClock() {
    var clock = $('#clock');
    if (!clock) return;
    (function tick() {
      var d = new Date();
      clock.textContent = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      applyHours();
      setTimeout(tick, 30000);
    })();
  }

  function initTicker() {
    var track = $('#tickerTrack');
    if (!track) return;
    var words = ['STRONGER EVERYDAY', 'KOLKATA', 'ESTABLISHED 2020', 'AIR CONDITIONED',
      'MULTIGYM CLUB', 'FREE PARKING', 'ASK FOR THE RATE CARD', 'TRAIN. EAT. SLEEP. REPEAT.'];
    var html = '';
    for (var pass = 0; pass < 2; pass++) {
      words.forEach(function (w) { html += '<span>' + w + '</span><i>◆</i>'; });
    }
    track.innerHTML = html;
  }

  /* ======================================================================
     7. PROGRAMME BUILDER
     ====================================================================== */
  function initBuilder() {
    var steps = $$('#steps li');
    var panels = $$('.panel');
    if (!panels.length) return;

    function show(idx) {
      panels.forEach(function (p, i) { p.classList.toggle('is-active', i === idx); });
      steps.forEach(function (s, i) {
        s.classList.toggle('is-active', i === idx);
        s.classList.toggle('is-done', i < idx);
      });
      if (idx === 3) {
        var top = $('.builder');
        if (top) top.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

    $$('[data-next]').forEach(function (b) {
      on(b, 'click', function () {
        var cur = panels.findIndex(function (p) { return p.classList.contains('is-active'); });
        show(clamp(cur + 1, 0, 3));
      });
    });
    $$('[data-back]').forEach(function (b) {
      on(b, 'click', function () {
        var cur = panels.findIndex(function (p) { return p.classList.contains('is-active'); });
        show(clamp(cur - 1, 0, 3));
      });
    });

    function pickGroup(selector, attr, cb) {
      var els = $$(selector);
      els.forEach(function (el) {
        on(el, 'click', function () {
          els.forEach(function (o) {
            o.classList.remove('is-picked');
            o.setAttribute('aria-checked', 'false');
          });
          el.classList.add('is-picked');
          el.setAttribute('aria-checked', 'true');
          cb(el.getAttribute(attr));
        });
      });
    }

    pickGroup('[data-goal]', 'data-goal', function (v) { state.goal = v; });
    pickGroup('[data-days]', 'data-days', function (v) { state.days = parseInt(v, 10); });
    pickGroup('[data-sex]', 'data-sex', function (v) { state.sex = v; });

    function bindSlider(id, key, suffix, transform) {
      var el = $('#' + id);
      var out = $('#' + id + 'Out');
      if (!el) return;
      var update = function () {
        var v = parseFloat(el.value);
        state[key] = transform ? transform(v) : v;
        if (out) out.textContent = suffix ? state[key] + ' ' + suffix : state[key];
        if (key === 'weight') updateWater();
      };
      on(el, 'input', update);
      update();
    }

    bindSlider('age', 'age', '');
    bindSlider('weight', 'weight', 'kg');
    bindSlider('height', 'height', 'cm');
    bindSlider('activity', 'activity', '', function (v) {
      var i = clamp(Math.round(v), 0, 4);
      var out = $('#activityOut');
      if (out) out.textContent = ACTIVITY_LABELS[i];
      return ACTIVITY_VALUES[i];
    });

    on($('#level'), 'change', function (e) { state.level = e.target.value; });

    on($('#generate'), 'click', function () {
      var loading = $('#resultLoading');
      var result = $('#result');
      show(3);
      if (loading) loading.hidden = false;
      if (result) result.hidden = true;
      var msgs = ['compiling engine…', 'periodising 8 weeks…', 'balancing push and pull…', 'calculating macros…'];
      var mi = 0;
      var timer = setInterval(function () {
        var m = $('#loadMsg');
        if (m) m.textContent = msgs[mi++ % msgs.length];
      }, 420);

      post('/api/plan', state).then(function (data) {
        state.plan = data;
        renderPlan(data);
      }).catch(function () {
        toast('Could not reach the training engine. Is the server running?', 'error');
      }).finally(function () {
        clearInterval(timer);
        if (loading) loading.hidden = true;
      });
    });

    on($('#restart'), 'click', function () { show(0); });
    on($('#downloadPlan'), 'click', downloadPlan);
  }

  function renderPlan(p) {
    var result = $('#result');
    if (result) result.hidden = false;

    var title = $('#resTitle');
    if (title) title.textContent = p.goal.charAt(0).toUpperCase() + p.goal.slice(1) +
      ' block · ' + p.days + ' days a week';

    var meta = $('#resMeta');
    if (meta) meta.textContent = p.level + ' · 8 weeks · engine 1.4.0';

    var kpis = $('#resKpis');
    if (kpis) {
      kpis.innerHTML = [
        ['BMR', p.bmr + ' kcal'],
        ['Maintenance', p.tdee + ' kcal'],
        ['Target intake', p.target_kcal + ' kcal'],
        ['Protein', p.macros.protein_g + ' g']
      ].map(function (k) {
        return '<div class="kpi"><span class="mono">' + k[0] + '</span><b>' + k[1] + '</b></div>';
      }).join('');
    }

    var strip = $('#weekStrip');
    if (strip) {
      strip.innerHTML = p.block.map(function (w) {
        return '<div class="week" title="' + w.note + '">' +
          '<span class="mono">W' + w.week + '</span>' +
          '<i style="height:' + clamp(w.vol_pct * 0.7, 10, 100) + '%"></i>' +
          '<em>' + w.phase.slice(0, 3) + '</em></div>';
      }).join('');
    }
    var note = $('#weekNote');
    if (note) note.textContent = p.block[0].note;

    var bars = $('#macroBars');
    if (bars) {
      var tot = p.macros.protein_g + p.macros.carbs_g + p.macros.fat_g;
      bars.innerHTML = [
        ['Protein', p.macros.protein_g, 'p'],
        ['Carbs', p.macros.carbs_g, 'c'],
        ['Fat', p.macros.fat_g, 'f']
      ].map(function (m) {
        return '<div class="macro"><span class="mono">' + m[0] + '</span>' +
          '<div class="macro-track"><i class="' + m[2] + '" style="width:' +
          ((m[1] / tot) * 100).toFixed(1) + '%"></i></div>' +
          '<b>' + m[1] + ' g</b></div>';
      }).join('');
    }
    var mn = $('#macroNote');
    if (mn) mn.textContent = 'Protein target = ' + p.protein_per_kg + ' g per kg bodyweight.';

    var tabs = $('#dayTabs');
    if (tabs) {
      tabs.innerHTML = p.split.map(function (d, i) {
        return '<button data-day="' + i + '"' + (i === 0 ? ' class="is-active"' : '') + '>Day ' + d.day + '</button>';
      }).join('');
      $$('button', tabs).forEach(function (b) {
        on(b, 'click', function () {
          $$('button', tabs).forEach(function (x) { x.classList.remove('is-active'); });
          b.classList.add('is-active');
          renderSession(p.split[parseInt(b.getAttribute('data-day'), 10)]);
        });
      });
    }
    renderSession(p.split[0]);
  }

  function renderSession(day) {
    var host = $('#session');
    if (!host || !day) return;
    host.innerHTML =
      '<div class="sess-head"><h5>' + day.label + '</h5>' +
      '<span class="mono">' + day.working_sets + ' sets · ~' + day.est_minutes + ' min</span></div>' +
      '<ul class="ex-list">' +
      day.exercises.map(function (e) {
        return '<li><b>' + e.name + '</b>' +
          '<span class="mono">' + e.sets + ' × ' + e.reps + ' @RPE ' + e.rpe +
          ' · rest ' + e.rest_s + 's</span></li>';
      }).join('') +
      '</ul>';
  }

  function downloadPlan() {
    var p = state.plan;
    if (!p) { toast('Generate a block first.', 'error'); return; }
    var L = [];
    L.push('FALCON FITNESS — KESTOPUR, KOLKATA');
    L.push('Training block: ' + p.goal.toUpperCase() + ' · ' + p.days + ' days/week · ' + p.level);
    L.push('Generated ' + new Date().toLocaleString('en-IN'));
    L.push('='.repeat(58), '');
    L.push('ENERGY');
    L.push('  BMR ' + p.bmr + ' kcal · maintenance ' + p.tdee + ' kcal · target ' + p.target_kcal + ' kcal');
    L.push('  Protein ' + p.macros.protein_g + ' g · Carbs ' + p.macros.carbs_g +
      ' g · Fat ' + p.macros.fat_g + ' g · Fibre ' + p.macros.fibre_g + ' g');
    L.push('', '8-WEEK PERIODISATION');
    p.block.forEach(function (w) {
      L.push('  Week ' + w.week + ' [' + w.phase + '] load ' + w.load_pct + '% · volume ' + w.vol_pct + '%');
      L.push('      ' + w.note);
    });
    L.push('', 'WEEKLY SPLIT');
    p.split.forEach(function (d) {
      L.push('', '  Day ' + d.day + ' — ' + d.label + '  (' + d.working_sets + ' sets, ~' + d.est_minutes + ' min)');
      d.exercises.forEach(function (e) {
        L.push('    • ' + e.name + ' — ' + e.sets + ' × ' + e.reps + ' @RPE ' + e.rpe + ', rest ' + e.rest_s + 's');
      });
    });
    L.push('', '='.repeat(58));
    L.push('Falcon Fitness, Belabhumi, 1st Floor, AC-204, Prafullakanan (E),');
    L.push('Opp. Mid Amore, Beside Axis Bank, Kestopur, Kolkata 700101');
    L.push('+91 98746 05022 / +91 70037 24906');
    L.push('', 'This is a training template, not medical advice. Stop if something hurts.');

    var blob = new Blob([L.join('\n')], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'falcon-' + p.goal + '-block.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    toast('Plan downloaded.');
  }

  /* ======================================================================
     8. TOOL: PLATE LOADER
     ====================================================================== */
  var PLATE_STYLE = { 25: '#c8374a', 20: '#3f6a9c', 15: '#c9a227', 10: '#4a8a5e',
    5: '#8a8a92', 2.5: '#6b3f7a', 1.25: '#5a4a42' };

  function initPlates() {
    var range = $('#plateRange');
    if (!range) return;
    var out = $('#plateOut');
    var raf = null;

    function draw(data) {
      if (out) out.textContent = data.total + ' kg';
      var side = $('#plateSide');
      if (side) side.textContent = data.per_side + ' kg';
      var total = $('#plateTotal');
      if (total) total.textContent = data.loaded_total + ' kg';
      var detail = $('#plateDetail');
      if (detail) {
        detail.textContent = 'per side · ' + (data.exact ? 'exact load' : 'nearest possible');
      }

      var list = $('#plateList');
      if (list) {
        list.innerHTML = data.plates.length
          ? data.plates.map(function (p) {
            return '<span class="chip"><i style="background:' + (PLATE_STYLE[p.kg] || '#8a8a92') +
              '"></i>' + p.kg + ' kg<em>×' + p.count + '</em></span>';
          }).join('')
          : '<span class="chip chip-empty">Empty bar</span>';
      }

      var group = $('#bbGroup');
      if (group) {
        var plates = group.querySelectorAll('.bb-plate');
        Array.prototype.forEach.call(plates, function (n) { n.remove(); });
        var ns = 'http://www.w3.org/2000/svg';
        var offset = 0;
        data.plates.forEach(function (p) {
          for (var i = 0; i < p.count; i++) {
            var h = 24 + p.kg * 2.6;
            var w = 9 + Math.min(p.kg, 25) * 0.22;
            [1, -1].forEach(function (dir) {
              var r = document.createElementNS(ns, 'rect');
              var x = dir > 0 ? 40 + offset : 580 - offset - w;
              r.setAttribute('x', x);
              r.setAttribute('y', 60 - h / 2);
              r.setAttribute('width', w);
              r.setAttribute('height', h);
              r.setAttribute('rx', 2.5);
              r.setAttribute('fill', PLATE_STYLE[p.kg] || '#8a8a92');
              r.setAttribute('class', 'bb-plate');
              group.appendChild(r);
            });
            offset += w + 2.5;
          }
        });
      }
    }

    function update() {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(function () {
        post('/api/plates', { total: parseFloat(range.value), bar: 20 })
          .then(draw).catch(function () { });
      });
    }
    on(range, 'input', update);
    update();
  }

  /* ======================================================================
     9. TOOL: 1RM
     ====================================================================== */
  function initOneRM() {
    var w = $('#ormWeight');
    var r = $('#ormReps');
    if (!w || !r) return;

    function update() {
      var wo = $('#ormWeightOut');
      var ro = $('#ormRepsOut');
      if (wo) wo.textContent = w.value + ' kg';
      if (ro) ro.textContent = r.value;
      post('/api/e1rm', { weight: parseFloat(w.value), reps: parseFloat(r.value) })
        .then(function (d) {
          var val = $('#ormValue');
          if (val) val.textContent = d.e1rm + ' kg';
          var ring = $('#ormRing');
          if (ring) ring.style.setProperty('--pct', clamp(d.e1rm / 2.5, 5, 100));
          var tbl = $('#pctTable');
          if (tbl) {
            tbl.innerHTML = d.percent_table.slice(0, 6).map(function (row) {
              return '<div><span class="mono">' + row.pct + '%</span><b>' + row.kg +
                ' kg</b><em>×' + row.reps + '</em></div>';
            }).join('');
          }
        }).catch(function () { });
    }
    on(w, 'input', update);
    on(r, 'input', update);
    update();
  }

  /* ======================================================================
     10. TOOL: STANDARDS
     ====================================================================== */
  function initStandards() {
    var lift = $('#stdLift');
    if (!lift) return;
    var w = $('#stdWeight'), bw = $('#stdBw'), sex = $('#stdSex');

    function update() {
      var wo = $('#stdOut');
      var bo = $('#stdBwOut');
      if (wo) wo.textContent = w.value + ' kg';
      if (bo) bo.textContent = bw.value + ' kg';
      post('/api/standards', {
        lift: lift.value, weight: parseFloat(w.value),
        bw: parseFloat(bw.value), sex: sex.value
      }).then(function (d) {
        var lvl = $('#stdLevel');
        if (lvl) lvl.textContent = d.level + ' · ' + d.ratio.toFixed(2) + '× bodyweight';
        var fill = $('#stdFill');
        if (fill) fill.style.width = clamp(d.progress_pct, 0, 100) + '%';
        var next = $('#stdNext');
        if (next) {
          next.textContent = d.to_next_kg > 0
            ? d.to_next_kg + ' kg to the next level'
            : 'Top of the scale — keep it there';
        }
      }).catch(function () { });
    }
    [lift, w, bw, sex].forEach(function (el) { on(el, 'input', update); on(el, 'change', update); });
    update();
  }

  /* ======================================================================
     11. TOOL: ACWR / CHECK-IN
     ====================================================================== */
  function initACWR() {
    var form = $('#checkinForm');
    if (!form) return;

    function history() {
      try { return JSON.parse(localStorage.getItem('falcon_loads') || '[]'); }
      catch (e) { return []; }
    }

    function refresh() {
      var h = history();
      var stats = $('#ciStats');
      if (stats) {
        var total = 0;
        try { total = parseInt(localStorage.getItem('falcon_total') || '0', 10); } catch (e) { }
        stats.textContent = (total || h.length) + ' session' + ((total || h.length) === 1 ? '' : 's') + ' logged';
      }
      if (!h.length) {
        var ratio0 = $('#acwrRatio');
        if (ratio0) ratio0.textContent = '—';
        return;
      }
      post('/api/acwr', { history: h.join(',') }).then(function (d) {
        var ratio = $('#acwrRatio');
        if (ratio) ratio.textContent = d.ratio.toFixed(2);
        var ring = $('#acwrRing');
        if (ring) ring.style.setProperty('--pct', clamp((d.ratio / 2) * 100, 3, 100));
        var band = $('#acwrBand');
        if (band) band.textContent = d.band;
        var adv = $('#acwrAdvice');
        if (adv) adv.textContent = d.advice;
      }).catch(function () { });
    }

    on(form, 'submit', function (e) {
      e.preventDefault();
      var input = $('#ciLoad');
      var load = parseFloat(input.value);
      if (!load || load <= 0) { toast('Enter your session tonnage in kg.', 'error'); return; }

      var h = history();
      h.push(load);
      while (h.length > 28) h.shift();
      try {
        localStorage.setItem('falcon_loads', JSON.stringify(h));
        localStorage.setItem('falcon_total', String(parseInt(localStorage.getItem('falcon_total') || '0', 10) + 1));
      } catch (err) { }

      post('/api/checkin', { load: load, member: 'Web', kind: 'session' })
        .then(function (d) { toast(d.message || 'Logged.'); })
        .catch(function () { toast('Saved on your device.', 'warn'); });

      refresh();
    });

    refresh();
  }

  /* ======================================================================
     12. TOOL: WATER
     ====================================================================== */
  function updateWater() {
    var base = state.weight * 35;       // ml baseline
    var training = 500;                 // one hour of hard training
    var litres = (base + training) / 1000;
    var lit = $('#waterLitres');
    if (lit) lit.textContent = litres.toFixed(1) + ' L';
    var baseEl = $('#waterBase');
    if (baseEl) baseEl.textContent = (base / 1000).toFixed(1) + ' L baseline';
    var fill = $('#waterFill');
    if (fill) fill.style.height = clamp((litres / 4) * 100, 12, 100) + '%';
  }

  /* ======================================================================
     13. LEAD FORM
     ====================================================================== */
  function initLeadForm() {
    var form = $('#leadForm');
    if (!form) return;
    var tsField = $('#formTimestamp');
    if (tsField) tsField.value = new Date().toISOString().slice(0, 19);

    var consent = $('#leadConsent');
    var note = $('#leadNote');

    on(form, 'submit', function (e) {
      e.preventDefault();
      var name = $('#leadName'), phone = $('#leadPhone'), email = $('#leadEmail');
      var goal = $('#leadGoal'), msg = $('#leadMessage');
      var hp = form.querySelector('[name="website"]');

      var phoneDigits = (phone.value || '').replace(/\D/g, '');
      if (phoneDigits.length === 12 && phoneDigits.indexOf('91') === 0) phoneDigits = phoneDigits.slice(2);
      if (phoneDigits.length === 11 && phoneDigits[0] === '0') phoneDigits = phoneDigits.slice(1);

      if (!name.value.trim() || name.value.trim().length < 2) {
        toast('Please enter your name.', 'error'); name.focus(); return;
      }
      if (!/^[6-9]\d{9}$/.test(phoneDigits)) {
        toast('Please enter a valid 10-digit mobile number.', 'error'); phone.focus(); return;
      }
      if (email.value.trim() && !/^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$/.test(email.value.trim())) {
        toast('That email address does not look right.', 'error'); email.focus(); return;
      }
      if (consent && !consent.checked) {
        toast('Please tick the consent box so we can contact you.', 'error'); consent.focus(); return;
      }

      var btn = form.querySelector('button[type="submit"]');
      var original = btn.textContent;
      btn.disabled = true;
      btn.textContent = 'Sending…';

      post('/api/lead', {
        name: name.value.trim(),
        phone: phoneDigits,
        email: email.value.trim(),
        goal: goal ? goal.value : '',
        message: msg ? msg.value.trim() : '',
        website: hp ? hp.value : '',
        consent: consent ? consent.checked : false,
        t: tsField ? tsField.value : '',
        source: 'website'
      }).then(function (d) {
        form.reset();
        if (tsField) tsField.value = new Date().toISOString().slice(0, 19);
        toast(d.message || 'Thanks — we will call you back.');
        if (note) {
          note.textContent = 'Received. We will call you on the number you gave us.';
          note.classList.add('is-ok');
        }
      }).catch(function (err) {
        toast(err.message || 'Something went wrong. Please call us instead.', 'error');
      }).finally(function () {
        btn.disabled = false;
        btn.textContent = original;
      });
    });
  }

  /* ======================================================================
     14. COMMAND PALETTE
     ====================================================================== */
  function initCmdk() {
    var modal = $('#cmdk');
    if (!modal) return;
    var input = $('#cmdkInput');
    var list = $('#cmdkList');
    var index = 0;
    var items = [];

    function build() {
      items = [];
      $$('main section[id]').forEach(function (s) {
        var heading = $('.h2', s) || $('h2', s);
        items.push({
          label: heading ? heading.textContent.trim() : s.id,
          hint: 'Section',
          run: function () { s.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
        });
      });
      items.push({ label: 'Enquire now', hint: 'Form', run: function () { $('#leadForm').scrollIntoView({ behavior: 'smooth' }); setTimeout(function () { $('#leadName').focus(); }, 500); } });
      items.push({ label: 'Call +91 98746 05022', hint: 'Phone', run: function () { window.location.href = 'tel:+919874605022'; } });
      items.push({ label: 'WhatsApp us', hint: 'Message', run: function () { window.open('https://wa.me/919874605022', '_blank', 'noopener'); } });
      items.push({ label: 'Open in Google Maps', hint: 'Directions', run: function () { window.open('https://www.google.com/maps/search/?api=1&query=Falcon+Fitness+Kestopur+Kolkata', '_blank', 'noopener'); } });
      items.push({ label: 'Privacy policy', hint: 'Legal', run: function () { window.location.href = '/privacy'; } });
      items.push({ label: 'Terms & refunds', hint: 'Legal', run: function () { window.location.href = '/terms'; } });
    }

    function render(q) {
      var query = (q || '').toLowerCase().trim();
      var shown = items.filter(function (i) {
        return !query || i.label.toLowerCase().indexOf(query) !== -1 || i.hint.toLowerCase().indexOf(query) !== -1;
      });
      index = 0;
      list.innerHTML = shown.length
        ? shown.map(function (i, n) {
          return '<li data-i="' + n + '"' + (n === 0 ? ' class="is-active"' : '') + '>' +
            '<span>' + i.label + '</span><em class="mono">' + i.hint + '</em></li>';
        }).join('')
        : '<li class="cmdk-empty">Nothing matches that.</li>';
      list._shown = shown;
      $$('li[data-i]', list).forEach(function (li) {
        on(li, 'click', function () {
          var it = shown[parseInt(li.getAttribute('data-i'), 10)];
          close();
          if (it) it.run();
        });
      });
    }

    function move(dir) {
      var lis = $$('li[data-i]', list);
      if (!lis.length) return;
      lis[index].classList.remove('is-active');
      index = (index + dir + lis.length) % lis.length;
      lis[index].classList.add('is-active');
      lis[index].scrollIntoView({ block: 'nearest' });
    }

    function open() {
      modal.classList.add('is-open');
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('no-scroll');
      build();
      render('');
      if (input) { input.value = ''; setTimeout(function () { input.focus(); }, 60); }
    }
    function close() {
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('no-scroll');
    }

    // Both buttons open the same palette: the header one (phones) and the one
    // beside "See memberships" (desktop). Only one is visible at a time.
    on($('#cmdkOpen'), 'click', open);
    on($('#cmdkOpenHero'), 'click', open);
    $$('[data-cmdk-close]').forEach(function (el) { on(el, 'click', close); });
    on(input, 'input', function () { render(input.value); });
    on(input, 'keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        var lis = $$('li[data-i]', list);
        if (lis[index]) lis[index].click();
      }
    });
    on(document, 'keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        modal.classList.contains('is-open') ? close() : open();
      }
      if (e.key === 'Escape' && modal.classList.contains('is-open')) close();
    });
  }

  /* ======================================================================
     14b. IMAGE PROTECTION
     Long-press / right-click on a photo should not offer "Save image".
     This is a deterrent, not real protection — anyone who wants the file can
     still open the URL or take a screenshot. CSS already sets
     -webkit-touch-callout:none and pointer-events:none on images; this stops
     the remaining shortcuts (drag, right-click save, ctrl-click).
     ====================================================================== */
  function initImageGuard() {
    $$('img').forEach(function (img) {
      img.setAttribute('draggable', 'false');
      on(img, 'dragstart', function (e) { e.preventDefault(); });
    });

    on(document, 'contextmenu', function (e) {
      var t = e.target;
      if (t && (t.tagName === 'IMG' || (t.closest && t.closest('.gal, .trainer-photo, .hero-bg')))) {
        e.preventDefault();
        toast('Photos belong to Falcon Fitness. Please don\u2019t copy them.');
      }
    });

    // stop the long-press selection sheet appearing on Android/iOS
    on(document, 'selectstart', function (e) {
      if (e.target && e.target.tagName === 'IMG') e.preventDefault();
    });
  }

  /* ======================================================================
     15. SMOOTH ANCHORS
     ====================================================================== */
  function initAnchors() {
    $$('a[href^="#"]').forEach(function (a) {
      on(a, 'click', function (e) {
        var id = a.getAttribute('href');
        if (id === '#' || id.length < 2) return;
        var target = document.querySelector(id);
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.replaceState(null, '', id);
      });
    });
  }

  /* ======================================================================
     16. ENGINE STATUS
     ====================================================================== */
  function initEngine() {
    fetch('/api/engine/status').then(function (r) { return r.json(); }).then(function (d) {
      var badge = $('#engineBadge');
      if (badge) badge.textContent = d.live ? 'C++ live' : 'python mirror';
      var line = $('#engineLine');
      if (line) {
        line.textContent = 'engine v' + (d.version || '1.4.0') + ' · ' +
          (d.live ? 'C++ compiled' : 'python fallback');
      }
    }).catch(function () {
      var badge = $('#engineBadge');
      if (badge) badge.textContent = 'offline';
    });
  }

  /* ======================================================================
     BOOT
     ====================================================================== */
  function boot() {
    initReveal();
    initNav();
    initCursor();
    initClock();
    initTicker();
    initBuilder();
    initPlates();
    initOneRM();
    initStandards();
    initACWR();
    updateWater();
    initLeadForm();
    initCmdk();
    initImageGuard();
    initAnchors();
    initEngine();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
