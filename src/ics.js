/* iCalendar (RFC 5545) reader for the timetable page.
   decode(bytes) -> text, parse(text) -> { calendar, events }, toPlan(parsed) -> { meta, subjectColors, weeks }.
   Runs in the browser (window.PlanICS) and in Node (module.exports) for tests. */
(function (root) {
  'use strict';

  /* index = Date#getDay() */
  var DAY_KEYS = ['NIEDZIELA', 'PONIEDZIAŁEK', 'WTOREK', 'ŚRODA', 'CZWARTEK', 'PIĄTEK', 'SOBOTA'];
  var BYDAY = { SU: 0, MO: 1, TU: 2, WE: 3, TH: 4, FR: 5, SA: 6 };
  var HEX = /^#[0-9a-fA-F]{6}$/;
  var PALETTE = ['#2563a8', '#1d8a7a', '#5b52c9', '#c8862a', '#c14953', '#3f9142', '#8a4fae',
                 '#c65a91', '#6f5ed1', '#d16b3f', '#b5651d', '#2aa7ad', '#7a8a3a', '#6b7280'];
  var SPORTS_CENTRE = 'SWF';  /* Studium Wychowania Fizycznego */
  var MAX_OCCURRENCES = 2000;
  var DAY_MS = 86400000;

  function pad2(n) { return String(n).padStart(2, '0'); }
  function isoOf(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
  function hhmm(d) { return pad2(d.getHours()) + ':' + pad2(d.getMinutes()); }
  function addDays(d, n) { var c = new Date(d.getTime()); c.setDate(c.getDate() + n); return c; }
  function fromIso(iso) { var p = iso.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function mondayOf(d) { var c = new Date(d.getFullYear(), d.getMonth(), d.getDate()); return addDays(c, -((c.getDay() + 6) % 7)); }
  function fmtShort(d) { return pad2(d.getDate()) + '.' + pad2(d.getMonth() + 1); }

  /* ---------- bytes -> text: unfold at byte level so a fold inside a UTF-8 sequence survives ---------- */
  function decode(buffer) {
    var b = new Uint8Array(buffer);
    var out = new Uint8Array(b.length);
    var j = 0;
    for (var i = 0; i < b.length; i++) {
      if (b[i] === 13 && b[i + 1] === 10 && (b[i + 2] === 32 || b[i + 2] === 9)) { i += 2; continue; }
      if (b[i] === 10 && (b[i + 1] === 32 || b[i + 1] === 9)) { i += 1; continue; }
      out[j++] = b[i];
    }
    return new TextDecoder('utf-8').decode(out.subarray(0, j));
  }

  /* ---------- content lines ---------- */
  function splitUnquoted(s, sep) {
    var parts = [], cur = '', quoted = false;
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (c === '"') quoted = !quoted;
      if (c === sep && !quoted) { parts.push(cur); cur = ''; } else cur += c;
    }
    parts.push(cur);
    return parts;
  }

  function parseLine(line) {
    var quoted = false, colon = -1;
    for (var i = 0; i < line.length; i++) {
      if (line[i] === '"') quoted = !quoted;
      else if (line[i] === ':' && !quoted) { colon = i; break; }
    }
    if (colon < 1) return null;
    var head = splitUnquoted(line.slice(0, colon), ';');
    var params = {};
    for (var k = 1; k < head.length; k++) {
      var eq = head[k].indexOf('=');
      if (eq > 0) params[head[k].slice(0, eq).toUpperCase()] = head[k].slice(eq + 1).replace(/^"|"$/g, '');
    }
    return { name: head[0].toUpperCase(), params: params, value: line.slice(colon + 1) };
  }

  function parse(text) {
    var lines = String(text).replace(/^﻿/, '').replace(/\r\n?/g, '\n').replace(/\n[ \t]/g, '').split('\n');
    var stack = [], calendar = null, events = [], cur = null;
    function add(obj, p) { (obj[p.name] = obj[p.name] || []).push(p); }
    for (var i = 0; i < lines.length; i++) {
      if (!lines[i]) continue;
      var p = parseLine(lines[i]);
      if (!p) continue;
      var kind = p.value.trim().toUpperCase();
      if (p.name === 'BEGIN') {
        stack.push(kind);
        if (kind === 'VCALENDAR' && !calendar) calendar = {};
        else if (kind === 'VEVENT' && stack[stack.length - 2] === 'VCALENDAR') cur = {};
      } else if (p.name === 'END') {
        if (kind === 'VEVENT' && cur && stack[stack.length - 1] === 'VEVENT') { events.push(cur); cur = null; }
        stack.pop();
      } else if (cur && stack[stack.length - 1] === 'VEVENT') {
        add(cur, p);
      } else if (calendar && stack[stack.length - 1] === 'VCALENDAR') {
        add(calendar, p);
      }
    }
    if (!calendar) throw new Error('To nie jest plik iCalendar (brak BEGIN:VCALENDAR)');
    return { calendar: calendar, events: events };
  }

  /* ---------- values ---------- */
  function unescapeText(v) {
    return v.replace(/\\([\\;,nN])/g, function (m, c) { return c === 'n' || c === 'N' ? '\n' : c; });
  }
  function splitList(v) {
    var out = [], cur = '';
    for (var i = 0; i < v.length; i++) {
      if (v[i] === '\\' && i + 1 < v.length) { cur += v[i] + v[++i]; }
      else if (v[i] === ',') { out.push(cur); cur = ''; }
      else cur += v[i];
    }
    out.push(cur);
    return out.map(function (s) { return unescapeText(s).trim(); }).filter(Boolean);
  }
  function text(obj, name) { return obj[name] ? unescapeText(obj[name][0].value).trim() : ''; }

  /* DATE or DATE-TIME -> { date: local Date, allDay }; TZID times are read as wall-clock times */
  function parseDateValue(value, params) {
    var m = /^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?$/.exec(String(value).trim());
    if (!m) return null;
    if (!m[4] || (params && String(params.VALUE).toUpperCase() === 'DATE')) {
      return { date: new Date(+m[1], +m[2] - 1, +m[3]), allDay: true };
    }
    var date = m[7]
      ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)))
      : new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0));
    return isNaN(date.getTime()) ? null : { date: date, allDay: false };
  }
  function dateProp(obj, name) {
    if (!obj[name]) return '';
    var d = parseDateValue(obj[name][0].value, obj[name][0].params);
    return d ? isoOf(d.date) : '';
  }
  function parseDuration(v) {
    var m = /^P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/.exec(String(v).trim());
    if (!m) return 0;
    return (((+(m[1] || 0) * 7 + +(m[2] || 0)) * 24 + +(m[3] || 0)) * 60 + +(m[4] || 0)) * 60000 + +(m[5] || 0) * 1000;
  }

  /* ---------- recurrence: FREQ=WEEKLY / DAILY with INTERVAL, COUNT, UNTIL, BYDAY; EXDATE ---------- */
  function expand(start, rule, limit) {
    var r = {};
    rule.split(';').forEach(function (kv) {
      var i = kv.indexOf('=');
      if (i > 0) r[kv.slice(0, i).toUpperCase()] = kv.slice(i + 1).toUpperCase();
    });
    if (r.FREQ !== 'WEEKLY' && r.FREQ !== 'DAILY') return [start];
    var interval = Math.max(1, parseInt(r.INTERVAL, 10) || 1);
    var count = r.COUNT ? Math.max(0, parseInt(r.COUNT, 10) || 0) : Infinity;
    var until = r.UNTIL ? parseDateValue(r.UNTIL) : null;
    var untilMs = until ? (until.allDay ? until.date.getTime() + DAY_MS - 1 : until.date.getTime()) : Infinity;
    var limitMs = limit ? limit.getTime() : start.getTime() + 366 * DAY_MS;
    var endMs = Math.min(untilMs, limitMs);
    var out = [];
    function at(day) {
      return new Date(day.getFullYear(), day.getMonth(), day.getDate(), start.getHours(), start.getMinutes(), start.getSeconds());
    }
    if (r.FREQ === 'DAILY') {
      for (var d = at(start); d.getTime() <= endMs && out.length < count && out.length < MAX_OCCURRENCES; d = at(addDays(d, interval))) out.push(d);
      return out;
    }
    var days = r.BYDAY
      ? r.BYDAY.split(',').map(function (s) { return BYDAY[s.replace(/^[+-]?\d+/, '')]; }).filter(function (n) { return n != null; })
      : [start.getDay()];
    days.sort(function (a, b) { return (a + 6) % 7 - (b + 6) % 7; });
    var week = mondayOf(start);
    for (var guard = 0; guard < MAX_OCCURRENCES; guard++, week = addDays(week, 7 * interval)) {
      if (week.getTime() > endMs) break;
      for (var k = 0; k < days.length; k++) {
        var occ = at(addDays(week, (days[k] + 6) % 7));
        if (occ < start) continue;
        if (occ.getTime() > endMs || out.length >= count) return out;
        out.push(occ);
      }
    }
    return out;
  }

  function occurrences(ev, limit) {
    if (!ev.DTSTART) return [];
    var s = parseDateValue(ev.DTSTART[0].value, ev.DTSTART[0].params);
    if (!s || s.allDay) return [];
    var durMs = 0;
    if (ev.DTEND) {
      var e = parseDateValue(ev.DTEND[0].value, ev.DTEND[0].params);
      if (e && !e.allDay) durMs = e.date - s.date;
    } else if (ev.DURATION) {
      durMs = parseDuration(ev.DURATION[0].value);
    }
    if (!(durMs > 0) || durMs > DAY_MS) return [];
    var starts = ev.RRULE ? expand(s.date, ev.RRULE[0].value, limit) : [s.date];
    var skip = {};
    (ev.EXDATE || []).forEach(function (p) {
      p.value.split(',').forEach(function (v) {
        var x = parseDateValue(v, p.params);
        if (x) skip[x.allDay ? isoOf(x.date) : isoOf(x.date) + 'T' + hhmm(x.date)] = true;
      });
    });
    return starts.filter(function (d) {
      return !skip[isoOf(d)] && !skip[isoOf(d) + 'T' + hhmm(d)];
    }).map(function (d) { return { start: d, end: new Date(d.getTime() + durMs) }; });
  }

  function paletteColor(name) {
    var h = 0;
    for (var i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return PALETTE[h % PALETTE.length];
  }

  /* ---------- calendar -> the page's plan model ---------- */
  function toPlan(parsed) {
    var c = parsed.calendar || {};
    var meta = {
      group: text(c, 'X-PLAN-GROUP') || text(c, 'X-WR-CALNAME').replace(/^plan zajęć\s*/i, ''),
      faculty: text(c, 'X-PLAN-FACULTY'),
      term: text(c, 'X-PLAN-TERM'),
      semesterStart: dateProp(c, 'X-PLAN-SEMESTER-START'),
      semesterEnd: dateProp(c, 'X-PLAN-SEMESTER-END'),
      generated: dateProp(c, 'X-PLAN-GENERATED')
    };
    var limit = meta.semesterEnd ? addDays(mondayOf(fromIso(meta.semesterEnd)), 7) : null;

    var lessons = [], colors = {};
    (parsed.events || []).forEach(function (ev) {
      if (text(ev, 'STATUS').toUpperCase() === 'CANCELLED') return;
      var subject = text(ev, 'SUMMARY');
      if (!subject) return;
      var type = ev.CATEGORIES ? (splitList(ev.CATEGORIES[0].value)[0] || '') : '';
      var room = text(ev, 'LOCATION');
      /* the faculties write "54/ 62" and "29/ 54 30/ 54": the space after the slash is noise in a room code */
      if (room) room = room.replace(/\s*\/\s*/g, '/').replace(/\s+/g, ' ').trim();
      /* physical education (WF) is held at the sports centre, but the faculties list no room for it */
      if (!room && /wychowanie fizyczne/i.test(subject)) room = SPORTS_CENTRE;
      var color = text(ev, 'X-PLAN-COLOR');
      var found = occurrences(ev, limit);
      if (!found.length) return;
      if (HEX.test(color) && !colors[subject]) colors[subject] = color.toLowerCase();
      found.forEach(function (o) {
        lessons.push({
          date: isoOf(o.start), start: hhmm(o.start), end: hhmm(o.end),
          subject_full: subject, type_full: type, room: room
        });
      });
    });
    /* the faculties sometimes list one class twice (same time, subject, type and room): show it once */
    var seen = {};
    lessons = lessons.filter(function (l) {
      var k = [l.date, l.start, l.end, l.subject_full, l.type_full, l.room].join('|');
      return seen[k] ? false : (seen[k] = true);
    });
    lessons.forEach(function (l) { if (!colors[l.subject_full]) colors[l.subject_full] = paletteColor(l.subject_full); });
    lessons.sort(function (a, b) {
      return a.date < b.date ? -1 : a.date > b.date ? 1 : a.start < b.start ? -1 : a.start > b.start ? 1 : 0;
    });

    var first = meta.semesterStart, last = meta.semesterEnd;
    if (lessons.length) {
      if (!first || lessons[0].date < first) first = lessons[0].date;
      if (!last || lessons[lessons.length - 1].date > last) last = lessons[lessons.length - 1].date;
    }
    var weeks = [], byMonday = {};
    if (first && last) {
      for (var d = mondayOf(fromIso(first)), end = mondayOf(fromIso(last)); d <= end; d = addDays(d, 7)) {
        var w = { monday: isoOf(d), label: fmtShort(d) + '–' + fmtShort(addDays(d, 5)), days: {} };
        weeks.push(w);
        byMonday[w.monday] = w;
      }
    }
    lessons.forEach(function (l) {
      var day = fromIso(l.date);
      var w = byMonday[isoOf(mondayOf(day))];
      var key = DAY_KEYS[day.getDay()];
      (w.days[key] = w.days[key] || []).push(l);
    });
    return { meta: meta, subjectColors: colors, weeks: weeks };
  }

  /* Which week to show first: the week holding today (or the next one when today
     falls between/after them), except that on a Saturday/Sunday whose own week
     has no weekend lessons the following week is shown straight away. */
  function initialWeekIndex(weeks, today, dayOfWeek) {
    var cur = weeks.length - 1, inside = false;
    for (var i = 0; i < weeks.length; i++) {
      var monday = weeks[i].monday;
      var sunday = isoOf(addDays(fromIso(monday), 6));
      if (today >= monday && today <= sunday) { cur = i; inside = true; break; }
      if (today < monday) { cur = i; break; }
    }
    if (inside && cur < weeks.length - 1 && (dayOfWeek === 0 || dayOfWeek === 6)) {
      var days = weeks[cur].days || {};
      if (!((days.SOBOTA || []).length || (days.NIEDZIELA || []).length)) return cur + 1;
    }
    return cur;
  }

  /* ---------- "my subjects": a personal filter, applied in the browser only ---------- */
  /* every subject of the calendar, [{ name, count, color }] sorted by name, with the number of its calendar entries */
  function subjectsOf(parsed) {
    var by = {};
    (parsed.events || []).forEach(function (ev) {
      var name = text(ev, 'SUMMARY');
      if (!name || name === '-' || name === '–' || text(ev, 'STATUS').toUpperCase() === 'CANCELLED') return;
      var s = by[name] || (by[name] = { name: name, count: 0, color: '' });
      s.count++;
      var color = text(ev, 'X-PLAN-COLOR');
      if (!s.color && HEX.test(color)) s.color = color.toLowerCase();
    });
    return Object.keys(by).sort(function (a, b) { return a.localeCompare(b, 'pl'); }).map(function (k) { return by[k]; });
  }
  /* the parsed calendar without the classes of the hidden subjects (an array of names) */
  function withoutSubjects(parsed, hidden) {
    if (!hidden || !hidden.length) return parsed;
    var drop = {};
    hidden.forEach(function (n) { drop[n] = true; });
    return { calendar: parsed.calendar, events: (parsed.events || []).filter(function (ev) { return !drop[text(ev, 'SUMMARY')]; }) };
  }
  /* the calendar file's own text without the hidden subjects' events: what "Pobierz plan" saves after filtering */
  function filterText(raw, hidden) {
    if (!hidden || !hidden.length) return raw;
    var drop = {};
    hidden.forEach(function (n) { drop[n] = true; });
    return String(raw).replace(/BEGIN:VEVENT[\s\S]*?END:VEVENT(\r?\n)?/g, function (block) {
      var m = /^SUMMARY[^:\r\n]*:(.*)$/m.exec(block.replace(/\r?\n[ \t]/g, ''));
      return m && drop[unescapeText(m[1].replace(/\r$/, '')).trim()] ? '' : block;
    });
  }

  var PlanICS = { decode: decode, parse: parse, toPlan: toPlan, initialWeekIndex: initialWeekIndex,
    subjectsOf: subjectsOf, withoutSubjects: withoutSubjects, filterText: filterText };
  if (typeof module === 'object' && module.exports) module.exports = PlanICS;
  else root.PlanICS = PlanICS;
})(this);
