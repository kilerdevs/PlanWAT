/* iCalendar (RFC 5545) reader/writer for the timetable page.
   decode(bytes) -> text, parse(text) -> { calendar, events }, toPlan(parsed) -> { meta, subjectColors, weeks },
   toIcs(lessons, opts) -> text.
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
      var type = typeOf(ev);
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
  /* the class type (Wykład, Ćwiczenia, …): the first of the event's categories */
  function typeOf(ev) { return ev.CATEGORIES ? (splitList(ev.CATEGORIES[0].value)[0] || '') : ''; }
  /* the usual parts of a subject first, in the order a syllabus lists them; anything else after, by name */
  var TYPE_ORDER = ['Wykład', 'Ćwiczenia', 'Laboratorium', 'Projekt', 'Seminarium'];
  function byTypeOrder(a, b) {
    var i = TYPE_ORDER.indexOf(a), j = TYPE_ORDER.indexOf(b);
    if (i < 0) i = TYPE_ORDER.length;
    if (j < 0) j = TYPE_ORDER.length;
    return i - j || a.localeCompare(b, 'pl');
  }
  /* every subject of the calendar, [{ name, count, color, types: [{ type, count }] }] sorted by name, with the number
     of its calendar entries in all and per class type */
  function subjectsOf(parsed) {
    var by = {};
    (parsed.events || []).forEach(function (ev) {
      var name = text(ev, 'SUMMARY');
      if (!name || name === '-' || name === '–' || text(ev, 'STATUS').toUpperCase() === 'CANCELLED') return;
      var s = by[name] || (by[name] = { name: name, count: 0, color: '', types: {} });
      s.count++;
      var type = typeOf(ev);
      s.types[type] = (s.types[type] || 0) + 1;
      var color = text(ev, 'X-PLAN-COLOR');
      if (!s.color && HEX.test(color)) s.color = color.toLowerCase();
    });
    return Object.keys(by).sort(function (a, b) { return a.localeCompare(b, 'pl'); }).map(function (k) {
      var s = by[k];
      s.types = Object.keys(s.types).sort(byTypeOrder).map(function (t) { return { type: t, count: s.types[t] }; });
      return s;
    });
  }
  /* hidden: a subject's name hides all of it, a [name, type] pair only its classes of that type */
  function hiddenTest(hidden) {
    var whole = {}, part = {};
    hidden.forEach(function (h) {
      if (typeof h === 'string') whole[h] = true;
      else if (Array.isArray(h) && h.length === 2) part[h[0] + '\u0000' + h[1]] = true;
    });
    return function (name, type) { return !!(whole[name] || part[name + '\u0000' + type]); };
  }
  /* per subject, the types the list hides (all of them for a hidden name) */
  function hiddenTypes(hidden, sub) {
    if (hidden.indexOf(sub.name) >= 0) return sub.types.map(function (t) { return t.type; });
    return hidden.filter(function (h) { return Array.isArray(h) && h[0] === sub.name; }).map(function (h) { return h[1]; });
  }
  function hidesAll(hidden, subjects) {
    return subjects.every(function (sub) { return hiddenTypes(hidden, sub).length >= sub.types.length; });
  }
  /* a saved choice, kept to what this calendar still has (subjectsOf); one that would hide everything is dropped */
  function hiddenFor(saved, subjects) {
    if (!Array.isArray(saved)) return [];
    var types = {};
    subjects.forEach(function (sub) { types[sub.name] = sub.types.map(function (t) { return t.type; }); });
    var kept = saved.filter(function (h) {
      if (typeof h === 'string') return !!types[h];
      return Array.isArray(h) && h.length === 2 && !!types[h[0]] && types[h[0]].indexOf(h[1]) >= 0;
    });
    return hidesAll(kept, subjects) ? [] : kept;
  }
  /* the parsed calendar without the hidden classes */
  function withoutSubjects(parsed, hidden) {
    if (!hidden || !hidden.length) return parsed;
    var drop = hiddenTest(hidden);
    return { calendar: parsed.calendar, events: (parsed.events || []).filter(function (ev) { return !drop(text(ev, 'SUMMARY'), typeOf(ev)); }) };
  }
  /* the calendar file's own text without the hidden classes' events: what "Pobierz plan" saves after filtering */
  function filterText(raw, hidden) {
    if (!hidden || !hidden.length) return raw;
    var drop = hiddenTest(hidden);
    return String(raw).replace(/BEGIN:VEVENT[\s\S]*?END:VEVENT(\r?\n)?/g, function (block) {
      var flat = block.replace(/\r?\n[ \t]/g, '');
      var m = /^SUMMARY[^:\r\n]*:(.*)$/m.exec(flat);
      if (!m) return block;
      var c = /^CATEGORIES[^:\r\n]*:(.*)$/m.exec(flat);
      var type = c ? (splitList(c[1].replace(/\r$/, ''))[0] || '') : '';
      return drop(unescapeText(m[1].replace(/\r$/, '')).trim(), type) ? '' : block;
    });
  }

  /* ---------- writer: lessons -> an RFC 5545 calendar with a Warsaw VTIMEZONE ---------- */
  var WARSAW_TZ = [
    'BEGIN:VTIMEZONE',
    'TZID:Europe/Warsaw',
    'BEGIN:STANDARD',
    'DTSTART:19701025T030000',
    'TZOFFSETFROM:+0200',
    'TZOFFSETTO:+0100',
    'TZNAME:CET',
    'RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU',
    'END:STANDARD',
    'BEGIN:DAYLIGHT',
    'DTSTART:19700329T020000',
    'TZOFFSETFROM:+0100',
    'TZOFFSETTO:+0200',
    'TZNAME:CEST',
    'RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU',
    'END:DAYLIGHT',
    'END:VTIMEZONE'
  ];
  var SLUG_MAP = { 'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z' };
  var MAX_MINUTES = 40319;  /* RFC 5545 limits a TRIGGER duration to less than four weeks */

  function escapeText(v) {
    return String(v == null ? '' : v)
      .replace(/\\/g, '\\\\')
      .replace(/;/g, '\\;')
      .replace(/,/g, '\\,')
      .replace(/\r\n|\n\r|\r|\n/g, '\\n');
  }

  function utf8LengthAt(s, i) {
    var c = s.charCodeAt(i);
    if (c < 0x80) return 1;
    if (c < 0x800) return 2;
    if (c >= 0xD800 && c <= 0xDBFF && i + 1 < s.length) {
      var d = s.charCodeAt(i + 1);
      if (d >= 0xDC00 && d <= 0xDFFF) return 4;
    }
    return 3;
  }

  /* fold at 75 octets without splitting a UTF-8 sequence; continuation lines start with one space */
  function foldLine(line) {
    var out = [], cur = '', bytes = 0, max = 75, i = 0;
    while (i < line.length) {
      var size = utf8LengthAt(line, i);
      var step = size === 4 ? 2 : 1;
      var piece = line.slice(i, i + step);
      if (bytes + size > max) {
        out.push(cur);
        cur = piece;
        bytes = size;
        max = 74;
      } else {
        cur += piece;
        bytes += size;
      }
      i += step;
    }
    out.push(cur);
    return out.join('\r\n ');
  }

  function contentLine(name, value) { return foldLine(name + ':' + value); }

  function validIsoDate(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return false;
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
  }
  function validTime(s) { return /^([01]\d|2[0-3]):[0-5]\d$/.test(s); }
  function textOf(v) { return v == null ? '' : String(v).trim(); }

  function lessonOf(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var l = {
      date: textOf(raw.date), start: textOf(raw.start), end: textOf(raw.end),
      subject_full: textOf(raw.subject_full), type_full: textOf(raw.type_full), room: textOf(raw.room)
    };
    if (!validIsoDate(l.date) || !validTime(l.start) || !validTime(l.end)) return null;
    if (l.end <= l.start) return null;
    if (!l.subject_full || l.subject_full === '-' || l.subject_full === '–') return null;
    return l;
  }

  function slugOf(s) {
    var v = String(s).toLowerCase().replace(/[ąćęłńóśźż]/g, function (c) { return SLUG_MAP[c]; });
    return v.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) || 'zajecia';
  }
  function hashOf(s) {
    var h = 5381;
    for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
    return ('00000000' + (h >>> 0).toString(16)).slice(-8);
  }
  function uidOf(l) {
    var key = [l.date, l.start, l.end, l.subject_full, l.type_full, l.room].join('|');
    return wallClock(l.date, l.start) + '-' + slugOf(l.subject_full) + '-' + hashOf(key) + '@planwat';
  }

  function utcStamp(d) {
    return d.getUTCFullYear() + pad2(d.getUTCMonth() + 1) + pad2(d.getUTCDate()) + 'T' +
      pad2(d.getUTCHours()) + pad2(d.getUTCMinutes()) + pad2(d.getUTCSeconds()) + 'Z';
  }
  function wallClock(date, time) { return date.replace(/-/g, '') + 'T' + time.replace(/:/g, '') + '00'; }

  function toIcs(lessons, opts) {
    opts = opts || {};
    var now = opts.now == null ? new Date() : new Date(opts.now);
    if (isNaN(now.getTime())) now = new Date();
    var stamp = utcStamp(now);
    var colors = opts.colors || {};
    var reminders = [];
    if (Array.isArray(opts.reminders)) {
      for (var i = 0; i < opts.reminders.length; i++) {
        var n = opts.reminders[i];
        if (n == null || n === '') continue;
        n = Number(n);
        if (!isFinite(n) || n < 0) continue;
        n = Math.floor(n);
        reminders.push(n > MAX_MINUTES ? MAX_MINUTES : n);
      }
    }

    var lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//PlanWAT//PlanWAT//PL', 'CALSCALE:GREGORIAN',
      contentLine('X-WR-CALNAME', escapeText(opts.name))];
    lines = lines.concat(WARSAW_TZ);

    (Array.isArray(lessons) ? lessons : []).forEach(function (raw) {
      var l = lessonOf(raw);
      if (!l) return;
      var color = Object.prototype.hasOwnProperty.call(colors, l.subject_full) ? colors[l.subject_full] : '';
      lines.push('BEGIN:VEVENT');
      lines.push(contentLine('UID', uidOf(l)));
      lines.push(contentLine('DTSTAMP', stamp));
      lines.push(contentLine('DTSTART;TZID=Europe/Warsaw', wallClock(l.date, l.start)));
      lines.push(contentLine('DTEND;TZID=Europe/Warsaw', wallClock(l.date, l.end)));
      lines.push(contentLine('SUMMARY', escapeText(l.subject_full)));
      if (l.type_full && l.type_full !== '-' && l.type_full !== '–') {
        lines.push(contentLine('CATEGORIES', escapeText(l.type_full)));
      }
      if (l.room && l.room !== '-' && l.room !== '–') {
        lines.push(contentLine('LOCATION', escapeText(l.room)));
      }
      if (HEX.test(color)) lines.push(contentLine('X-PLAN-COLOR', color));
      reminders.forEach(function (m) {
        lines.push('BEGIN:VALARM');
        lines.push('ACTION:DISPLAY');
        lines.push(contentLine('DESCRIPTION', escapeText('Przypomnienie: ' + l.subject_full)));
        lines.push(contentLine('TRIGGER', '-PT' + m + 'M'));
        lines.push('END:VALARM');
      });
      lines.push('END:VEVENT');
    });

    lines.push('END:VCALENDAR');
    return lines.join('\r\n') + '\r\n';
  }

  var PlanICS = { decode: decode, parse: parse, toPlan: toPlan, toIcs: toIcs, initialWeekIndex: initialWeekIndex,
    subjectsOf: subjectsOf, withoutSubjects: withoutSubjects, filterText: filterText,
    hiddenFor: hiddenFor, hiddenTypes: hiddenTypes, hidesAll: hidesAll };
  if (typeof module === 'object' && module.exports) module.exports = PlanICS;
  else root.PlanICS = PlanICS;
})(this);
