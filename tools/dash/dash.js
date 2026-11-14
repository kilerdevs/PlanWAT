// PlanWAT fleet dashboard (tools/dash/dash.py serves this; docs/DASHBOARD.md). Text from runners is data: it only ever
// becomes text nodes, never markup.
(function () {
  'use strict';
  var RUNNERS = ['plebania', 'oracle1', 'oracle2', 'oracle3', 'northflank1', 'northflank2'];
  var ROUTE = { direct: 'własny adres', tor: 'własny Tor', pool: 'wyjścia z puli', hunting: 'poluje', wall: 'ściana',
                error: 'błąd', lost: 'wyjścia padły' };
  var STATUS = { crawling: 'crawl', listing: 'listuje', hunting: 'poluje', idle: 'czeka', done: 'koniec', gone: 'zniknął' };
  var state = null, history = null, tab = 'live';

  function $(id) { return document.getElementById(id); }
  function h(tag, attrs, kids) {
    var el = /^(svg|rect|line|text|g|title|path)$/.test(tag)
      ? document.createElementNS('http://www.w3.org/2000/svg', tag) : document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'text') el.textContent = v;
      else if (k === 'cls') el.setAttribute('class', v);
      else if (k === 'css') Object.keys(v).forEach(function (p) { el.style.setProperty(p, v[p]); });
      else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    });
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined) el.append(c.nodeType ? c : String(c)); });
    return el;
  }
  function fill(el, kids) { el.replaceChildren.apply(el, kids.filter(function (k) { return k !== null && k !== undefined; })); }
  function color(r) { return 'var(--r-' + (RUNNERS.indexOf(r) >= 0 ? r : 'other') + ')'; }
  function who(r) { return h('span', { cls: 'who' }, [h('i', { cls: 'dot', css: { background: color(r) } }), r || '–']); }
  function clock(t) { var d = new Date(t * 1000); return d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  function day(t) { return new Date(t * 1000).toLocaleString('pl-PL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  function mins(s) { return s == null ? '–' : s < 90 ? Math.round(s) + ' s' : (s / 60).toFixed(1) + ' min'; }
  function iso(s) { return s ? Date.parse(s) / 1000 : null; }
  function pct(a, b) { return b ? Math.round(100 * a / b) : 0; }

  // -- theme ------------------------------------------------------------------------------------------------------
  function setTheme(t) {
    if (t === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', t);
    document.querySelectorAll('[data-theme-set]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.themeSet === t)); });
    try { localStorage.setItem('dash-theme', t); } catch (e) { /* private window: the choice lasts this visit */ }
  }
  document.querySelectorAll('[data-theme-set]').forEach(function (b) { b.addEventListener('click', function () { setTheme(b.dataset.themeSet); }); });
  try { setTheme(localStorage.getItem('dash-theme') || 'auto'); } catch (e) { setTheme('auto'); }

  document.querySelectorAll('[data-tab]').forEach(function (b) {
    b.addEventListener('click', function () {
      tab = b.dataset.tab;
      document.querySelectorAll('[data-tab]').forEach(function (x) { x.setAttribute('aria-selected', String(x === b)); });
      $('tab-live').hidden = tab !== 'live';
      $('tab-history').hidden = tab !== 'history';
      if (tab === 'history') loadHistory();
    });
  });

  // -- live -------------------------------------------------------------------------------------------------------
  function current() { return state && (state.live[0] || state.last); }

  function render() {
    var p = current();
    var conn = $('conn');
    conn.classList.toggle('on', !!(state && state.live.length));
    conn.lastChild.textContent = state && state.live.length ? 'przebieg trwa' : 'brak przebiegu';
    var banners = [];
    if (state && !state.key_loaded) banners.push('Brak klucza (~/.config/planwat/dash.key): telemetria runnerów (obciążenie, żądania, Tor, logi) jest zapieczętowana. Widać tylko stos pracy i przebiegi.');
    Object.keys((state && state.errors) || {}).forEach(function (k) { banners.push('Odczyt „' + k + '” nie działa: ' + state.errors[k]); });
    fill($('banners'), banners.map(function (b) { return h('div', { cls: 'banner', text: b }); }));
    if (!p) { $('sub').textContent = 'Nie widać jeszcze żadnego przebiegu.'; return; }
    var run = (state.runs || []).filter(function (r) { return r.id === p.run; })[0];
    $('sub').textContent = (state.live.length ? 'Przebieg ' : 'Ostatni przebieg ') + p.run + ' · zaplanowany ' + day(p.planned)
      + (run ? ' · ' + (run.head_branch || '') + (run.display_title ? ' · ' + run.display_title : '') : '');
    tiles(p, run);
    slots(p);
    runners(p);
    gantt();
    feed();
  }

  function tiles(p, run) {
    var start = run ? iso(run.run_started_at || run.created_at) : p.planned;
    var end = run && run.status === 'completed' ? iso(run.updated_at) : state.now;
    var up = p.runners.filter(function (r) { return r.status !== 'gone' && r.status !== 'done'; }).length;
    var ppm = p.runners.reduce(function (a, r) { return a + (r.ppm || 0); }, 0);
    var walls = p.slots.reduce(function (a, s) { return a + Object.values(s.routes).filter(function (v) { return v === 'wall'; }).length; }, 0);
    fill($('tiles'), [
      tile(run ? h('a', { href: run.html_url, target: '_blank', rel: 'noopener', text: '#' + p.run }) : '#' + p.run,
           run ? (run.status === 'completed' ? (run.conclusion || 'koniec') : run.status) : 'przebieg'),
      tile(mins(end - start), 'czas'),
      tile(p.done + ' / ' + p.total, 'grup sprawdzonych (' + pct(p.done, p.total) + '%)'),
      tile(p.changed, 'kalendarzy zmienionych'),
      tile(p.open + ' / ' + p.slots.length, 'wydziałów otwartych'),
      tile(up + ' / ' + p.runners.length, 'runnerów pracuje'),
      tile(ppm ? ppm.toFixed(0) : '–', 'stron / min (cała flota)'),
      tile(walls, 'ścian (runner × wydział)')
    ]);
  }
  function tile(v, label) { return h('div', { cls: 'tile' }, [h('b', {}, [v]), h('span', { text: label })]); }

  function slots(p) {
    var head = h('tr', {}, ['Wydział', 'Stan', 'Lider', 'Postęp', 'Sprawdzone', 'Zmienione', 'Drogi', 'Na liście', 'Świeże', 'Nie gotowe']
      .map(function (t) { return h('th', { text: t }); }));
    var rows = p.slots.map(function (s) {
      var bar = h('div', { cls: 'bar', title: s.done + ' z ' + s.total + ' sprawdzone' }, s.chunks.map(function (c) {
        var w = s.total ? 100 * c.n / s.total : 0;
        var el = h('i', { cls: c.state, title: c.n + ' grup · ' + (c.state === 'done' ? 'sprawdził ' : c.state === 'held' ? 'sprawdza ' : 'wolne') + (c.by || '') });
        el.style.width = 'calc(' + w + '% - 2px)';
        if (c.state === 'done') el.style.background = color(c.by);
        if (c.state === 'held') el.style.color = color(c.by);
        return el;
      }));
      var routes = Object.keys(s.routes).sort().map(function (r) {
        return h('span', { cls: 'chip ' + s.routes[r], title: r + ': ' + (ROUTE[s.routes[r]] || s.routes[r]) },
                 [h('i', { cls: 'dot', css: { background: color(r) } }), r + ' · ' + (ROUTE[s.routes[r]] || s.routes[r])]);
      });
      return h('tr', {}, [
        h('td', {}, [h('b', { text: s.slot })]),
        h('td', {}, [h('span', { cls: 'state ' + s.state, text: s.state + (s.note ? ' (' + s.note + ')' : '') })]),
        h('td', {}, [s.leader ? who(s.leader) : '–']),
        h('td', {}, [bar]),
        h('td', { text: s.done + ' / ' + s.total + (s.held ? ' (+' + s.held + ')' : '') }),
        h('td', { text: s.changed }),
        h('td', {}, routes.length ? routes : ['–']),
        h('td', { text: s.listed == null ? '–' : s.listed }),
        h('td', { text: s.fresh == null ? '–' : s.fresh }),
        h('td', { text: s.not_ready == null ? '–' : s.not_ready })
      ]);
    });
    fill($('slots'), [h('thead', {}, [head]), h('tbody', {}, rows)]);
    var seen = {};
    p.slots.forEach(function (s) { s.chunks.forEach(function (c) { if (c.by) seen[c.by] = 1; }); });
    fill($('slot-legend'), ['Kolor odcinka: kto go sprawdził; kreskowany: sprawdza teraz; szary: wolne. '].concat(
      Object.keys(seen).sort().map(function (r) { return h('span', { cls: 'chip' }, [who(r)]); })));
  }

  function meter(v, max, hot) {
    var m = h('span', { cls: 'meter' + (hot ? ' hot' : '') }, [h('i', {})]);
    m.firstChild.style.width = Math.min(100, max ? 100 * v / max : 0) + '%';
    return m;
  }

  function runners(p) {
    fill($('runners'), p.runners.map(function (r) {
      var lanes = Object.keys(r.lanes || {}).map(function (g) {
        var l = r.lanes[g];
        return h('div', {}, [h('span', { cls: 'muted', text: g + ': ' }), l.slot ? l.slot + (l.chunk != null ? ' · kawałek ' + l.chunk + ' (' + (l.tick || 0) + ' str.)' : ' · listuje') : '–']);
      });
      var sys = r.sys || {}, t = r.totals || {}, g = r.gauges || {};
      var rows = [['Bicie serca', r.age == null ? '–' : r.age + ' s temu'], ['Pasy', lanes.length ? h('div', {}, lanes) : '–'],
                  ['Prowadzi', r.led.join(', ') || '–'], ['Sprawdził', r.done + ' grup']];
      if (r.tel) {
        rows.push(['Strony/min', r.ppm == null ? '–' : r.ppm]);
        rows.push(['Odpowiedzi', (t.n || 0) + ' · 2xx ' + (t.s2xx || 0) + ' · 304 ' + (t.s304 || 0) + ' · 404 ' + (t.s404 || 0) + ' · inne ' + (t.other || 0) + ' · bez odp. ' + (t.err || 0)]);
        rows.push(['Średnio', t.n ? Math.round(t.ms / t.n) + ' ms · ' + Math.round((t.bytes || 0) / 1024) + ' KiB razem' : '–']);
        var routes = {};
        Object.keys(r.req || {}).forEach(function (host) { Object.keys(r.req[host]).forEach(function (rt) { routes[rt] = (routes[rt] || 0) + r.req[host][rt].n; }); });
        rows.push(['Drogami', Object.keys(routes).map(function (k) { return k + ' ' + routes[k]; }).join(' · ') || '–']);
        rows.push(['CPU', sys.cpu == null ? '–' : h('span', {}, [meter(sys.cpu, 100, sys.cpu > 85), sys.cpu + '%'])]);
        rows.push(['Load', sys.load ? sys.load.join(' / ') : '–']);
        if (sys.mem_mb) rows.push(['Pamięć', h('span', {}, [meter(sys.mem_mb - sys.mem_free_mb, sys.mem_mb, sys.mem_free_mb < sys.mem_mb * 0.1),
                                    (sys.mem_mb - sys.mem_free_mb) + ' / ' + sys.mem_mb + ' MB · crawl ' + (sys.rss_mb || '–') + ' MB'])]);
        if (sys.rx_kbs != null) rows.push(['Sieć', '↓ ' + sys.rx_kbs + ' KB/s · ↑ ' + sys.tx_kbs + ' KB/s']);
        if (g.tor) rows.push(['Tor', g.tor.up ? 'działa · ' + g.tor.circuits + ' obwody · start ' + g.tor.boot_s + ' s' : 'nie wystartował']);
        Object.keys(g).filter(function (k) { return k.indexOf('hunt:') === 0; }).forEach(function (k) {
          var v = g[k];
          rows.push(['Polowanie', k.slice(5).replace('.wat.edu.pl', '') + ': ' + v.found + ' wyjść (' + (v.fresh || 0) + ' świeżych, ' + v.probed + ' prób) · ' + mins(v.secs)]);
        });
      } else {
        rows.push(['Telemetria', r.sealed ? 'zapieczętowana (brak klucza)' : 'brak (runner bez PLANWAT_DASH_KEY)']);
      }
      return h('article', { cls: 'runner' }, [
        h('header', {}, [who(r.runner), h('span', { cls: 'state ' + r.status, text: STATUS[r.status] || r.status })]),
        h('dl', {}, rows.reduce(function (a, kv) { return a.concat([h('dt', { text: kv[0] }), h('dd', {}, [kv[1]])]); }, []))
      ]);
    }));
  }

  function gantt() {
    var tl = state.timeline || [];
    if (!tl.length) { fill($('gantt'), [h('p', { cls: 'sub', text: 'Brak próbek: oś czasu powstaje z obserwacji na żywo (co 10 s).' })]); return; }
    var t0 = tl[0][0], t1 = tl[tl.length - 1][0] + 10;
    var rows = {}, order = [];
    tl.forEach(function (s) {
      var t = s[0], r = s[1], d = s[2];
      var groups = Object.keys(d.lanes || {});
      if (!groups.length) groups = ['–'];
      groups.forEach(function (g) {
        var key = r + '|' + g;
        if (!rows[key]) { rows[key] = []; order.push(key); }
        var lane = (d.lanes || {})[g] || {};
        rows[key].push([t, d.status === 'gone' ? 'gone' : d.status === 'hunting' && !lane.chunk ? 'hunt' : lane.slot ? 'slot' : 'idle', lane.slot || '']);
      });
    });
    order.sort();
    var W = Math.max(720, $('gantt').clientWidth || 720), L = 170, rowH = 22, H = order.length * rowH + 24;
    var x = function (t) { return L + (W - L - 10) * (t - t0) / Math.max(1, t1 - t0); };
    var svg = h('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Oś czasu pasów runnerów' });
    for (var m = 0; m <= (t1 - t0) / 60; m += Math.max(1, Math.round((t1 - t0) / 60 / 10))) {
      svg.append(h('line', { cls: 'grid', x1: x(t0 + m * 60), x2: x(t0 + m * 60), y1: 0, y2: H - 18 }));
      svg.append(h('text', { x: x(t0 + m * 60), y: H - 4, 'text-anchor': 'middle', text: '+' + m + 'm' }));
    }
    order.forEach(function (key, i) {
      var y = i * rowH + 2, parts = key.split('|');
      var label = h('text', { x: 4, y: y + 14, text: parts[0] + ' · ' + parts[1] });
      label.style.fill = color(parts[0]);
      svg.append(label);
      var seg = rows[key], run = null;
      seg.concat([[t1, 'end', '']]).forEach(function (s) {
        if (run && (s[1] !== run[1] || s[2] !== run[2])) {
          var x0 = x(run[0]), x1 = Math.max(x0 + 2, x(s[0]));
          if (run[1] === 'idle') svg.append(h('line', { cls: 'idle', x1: x0, x2: x1, y1: y + 10, y2: y + 10 }));
          else {
            var r = h('rect', { cls: run[1] === 'hunt' ? 'hunt' : run[1] === 'gone' ? 'gone' : 'barfill', x: x0, y: y + 2, width: x1 - x0, height: rowH - 6, rx: 3 },
                      [h('title', { text: parts[0] + ' ' + parts[1] + ': ' + (run[1] === 'hunt' ? 'polowanie' : run[1] === 'gone' ? 'zniknął' : run[2]) + ' · ' + clock(run[0]) + '–' + clock(s[0]) })]);
            svg.append(r);
            if (run[1] === 'slot' && x1 - x0 > 30) svg.append(h('text', { cls: 'lbl', x: x0 + 4, y: y + 14, text: run[2] }));
          }
          run = null;
        }
        if (!run && s[1] !== 'end') run = s;
      });
    });
    fill($('gantt'), [svg]);
  }

  function options(sel, values) {
    var keep = sel.value;
    fill(sel, [sel.options[0]].concat(values.map(function (v) { return h('option', { value: v, text: v }); })));
    sel.value = values.indexOf(keep) >= 0 ? keep : '';
  }

  function feed() {
    var ev = state.events || [];
    options($('f-runner'), Array.from(new Set(ev.map(function (e) { return e.runner; }).filter(Boolean))).sort());
    options($('f-kind'), Array.from(new Set(ev.map(function (e) { return e.kind; }))).sort());
    options($('f-slot'), Array.from(new Set(ev.map(function (e) { return e.slot; }).filter(Boolean))).sort());
    var fr = $('f-runner').value, fk = $('f-kind').value, fs = $('f-slot').value, ft = $('f-text').value.toLowerCase();
    fill($('feed'), ev.filter(function (e) {
      return (!fr || e.runner === fr) && (!fk || e.kind === fk) && (!fs || e.slot === fs) && (!ft || (e.msg || '').toLowerCase().indexOf(ft) >= 0);
    }).slice(0, 300).map(function (e) {
      return h('li', { cls: 'k-' + e.kind }, [h('span', { text: clock(e.t) }), e.runner ? who(e.runner) : h('span', { text: '–' }),
        h('span', { cls: 'fk', text: e.kind + (e.slot ? ' ' + e.slot : '') }), h('span', { text: e.msg })]);
    }));
  }
  ['f-runner', 'f-kind', 'f-slot', 'f-text'].forEach(function (id) { $(id).addEventListener('input', function () { if (state) feed(); }); });

  // -- history ----------------------------------------------------------------------------------------------------
  function loadHistory() {
    fetch('/api/history?days=' + $('h-days').value).then(function (r) { return r.json(); }).then(function (d) { history = d; renderHistory(); })
      .catch(function () { /* the next tab switch tries again */ });
  }
  $('h-days').addEventListener('change', loadHistory);

  function barChart(items, unit) {
    // items: [{label, value, title}]; one series, one axis
    if (!items.length) return h('p', { cls: 'sub', text: 'Brak danych w tym okresie.' });
    var W = Math.max(600, items.length * 26 + 60), H = 180, L = 36, max = Math.max.apply(null, items.map(function (i) { return i.value; })) || 1;
    var bw = (W - L - 8) / items.length;
    var svg = h('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': 'Wykres słupkowy' });
    [0, .5, 1].forEach(function (f) {
      var y = 10 + (H - 40) * (1 - f);
      svg.append(h('line', { cls: 'grid', x1: L, x2: W, y1: y, y2: y }));
      svg.append(h('text', { x: L - 4, y: y + 4, 'text-anchor': 'end', text: Math.round(max * f) }));
    });
    items.forEach(function (it, i) {
      var bh = (H - 40) * it.value / max, x0 = L + i * bw + 3;
      svg.append(h('rect', { cls: 'col', x: x0, y: 10 + (H - 40) - bh, width: Math.max(2, bw - 6), height: Math.max(0, bh), rx: 3 },
        [h('title', { text: it.title || (it.label + ': ' + it.value + ' ' + unit) })]));
      if (i % Math.ceil(items.length / 12) === 0) svg.append(h('text', { x: x0 + bw / 2 - 3, y: H - 12, 'text-anchor': 'middle', text: it.label }));
    });
    return h('div', { cls: 'scroll' }, [svg]);
  }

  function table(head, rows) {
    return h('table', { cls: 'data' }, [h('thead', {}, [h('tr', {}, head.map(function (t) { return h('th', { text: t }); }))]),
      h('tbody', {}, rows.map(function (r) { return h('tr', {}, r.map(function (c) { return h('td', {}, [c]); })); }))]);
  }

  function renderHistory() {
    var passes = history.passes || [], runs = history.runs || [];
    var dur = runs.filter(function (r) { return r.status === 'completed'; }).map(function (r) {
      var m = (iso(r.updated_at) - iso(r.created_at)) / 60;
      return { label: day(iso(r.created_at)).slice(0, 5), value: Math.round(m * 10) / 10, title: '#' + r.id + ' · ' + day(iso(r.created_at)) + ' · ' + m.toFixed(1) + ' min · ' + (r.conclusion || '') };
    });
    fill($('h-duration'), [barChart(dur, 'min')]);

    var st = ['crawling', 'listing', 'hunting', 'idle', 'gone', 'done'];
    var util = [];
    passes.forEach(function (p) {
      Object.keys(p.util || {}).sort().forEach(function (r) {
        var u = p.util[r], n = st.reduce(function (a, s) { return a + (u[s] || 0); }, 0);
        if (n) util.push([day(p.planned), who(r)].concat(st.map(function (s) { return pct(u[s] || 0, n) + '%'; })));
      });
    });
    fill($('h-util'), [util.length ? table(['Przebieg', 'Runner', 'crawl', 'listuje', 'poluje', 'czeka', 'zniknął', 'koniec'], util)
      : h('p', { cls: 'sub', text: 'Brak przebiegów oglądanych na żywo w tym okresie.' })]);

    var names = Array.from(new Set([].concat.apply([], passes.map(function (p) { return p.runners.map(function (r) { return r.runner; }); })))).sort();
    fill($('h-share'), [table(['Przebieg', 'Grup'].concat(names), passes.slice().reverse().map(function (p) {
      return [day(p.planned), String(p.done)].concat(names.map(function (n) {
        var r = p.runners.filter(function (x) { return x.runner === n; })[0];
        return r ? r.done + ' (' + pct(r.done, p.done) + '%)' : '–';
      }));
    }))]);

    var slotsAll = Array.from(new Set([].concat.apply([], passes.map(function (p) { return p.slots.map(function (s) { return s.slot; }); })))).sort();
    var recent = passes.slice(-8);
    fill($('h-routes'), [table(['Wydział'].concat(recent.map(function (p) { return day(p.planned); })), slotsAll.map(function (sl) {
      return [h('b', { text: sl })].concat(recent.map(function (p) {
        var s = p.slots.filter(function (x) { return x.slot === sl; })[0];
        if (!s) return '–';
        return h('div', {}, Object.keys(s.routes).sort().filter(function (r) { return (s.by[r] || 0) > 0 || s.routes[r] !== 'direct'; }).map(function (r) {
          return h('span', { cls: 'chip ' + s.routes[r], title: r + ': ' + (ROUTE[s.routes[r]] || s.routes[r]) + ' · ' + (s.by[r] || 0) + ' grup' },
                   [h('i', { cls: 'dot', css: { background: color(r) } }), (ROUTE[s.routes[r]] || s.routes[r]) + ' ' + (s.by[r] || 0)]);
        }));
      }));
    }))]);

    var per = {};
    runs.forEach(function (r) {
      (r.jobs || []).forEach(function (j) {
        var m = /crawl \((\w+)\)/.exec(j.name || '');
        var k = m ? m[1] : j.name;
        var q = per[k] = per[k] || { n: 0, wait: 0, dur: 0, ok: 0, fail: 0, skip: 0 };
        q.n++;
        if (j.started_at && j.created_at) q.wait += iso(j.started_at) - iso(j.created_at);
        if (j.completed_at && j.started_at) q.dur += iso(j.completed_at) - iso(j.started_at);
        if (j.conclusion === 'success') q.ok++; else if (j.conclusion === 'skipped') q.skip++; else if (j.conclusion) q.fail++;
      });
    });
    fill($('h-jobs'), [table(['Zadanie', 'Liczba', 'Śr. kolejka', 'Śr. czas', 'Udane', 'Nieudane', 'Pominięte'], Object.keys(per).sort().map(function (k) {
      var q = per[k];
      return [RUNNERS.indexOf(k) >= 0 ? who(k) : k, String(q.n), mins(q.wait / q.n), mins(q.dur / q.n), String(q.ok), String(q.fail), String(q.skip)];
    }))]);

    fill($('h-passes'), [h('thead', {}, [h('tr', {}, ['Zaplanowany', 'Przebieg', 'Wynik', 'Czas', 'Grup', 'Zmienione', 'Źródło'].map(function (t) { return h('th', { text: t }); }))]),
      h('tbody', {}, passes.slice().reverse().map(function (p) {
        var r = p.run_info;
        return h('tr', {}, [h('td', { text: day(p.planned) }),
          h('td', {}, [r ? h('a', { href: r.html_url, target: '_blank', rel: 'noopener', text: '#' + p.run }) : '#' + p.run]),
          h('td', { text: r ? (r.conclusion || r.status) : '–' }),
          h('td', { text: r && r.status === 'completed' ? mins(iso(r.updated_at) - iso(r.created_at)) : '–' }),
          h('td', { text: p.done + ' / ' + p.total }), h('td', { text: p.changed }),
          h('td', { text: p.source === 'live' ? 'na żywo' : p.source === 'archive' ? 'archiwum' : 'trwa' })]);
      }))]);
  }

  // -- feed from the server ---------------------------------------------------------------------------------------
  function take(s) { state = s; render(); }
  fetch('/api/state').then(function (r) { return r.json(); }).then(take).catch(function () { /* the stream follows */ });
  var es = new EventSource('/events');
  es.onmessage = function (m) { try { take(JSON.parse(m.data)); } catch (e) { /* a torn message: the next one is whole */ } };
  es.onerror = function () { $('conn').classList.remove('on'); $('conn').lastChild.textContent = 'rozłączony'; };
  window.addEventListener('resize', function () { if (state) gantt(); });
}());
