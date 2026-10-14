/* Plan insights: pure functions over the plan model from PlanICS.toPlan and the JSON files written by
   build.py (data/year/<PREFIX>.json). No DOM access, so node:test covers them.
   Times are "HH:MM" strings in the plan model and minutes after midnight everywhere else. */
(function (root) {
  'use strict';

  var DAY_KEYS = ['PONIEDZIAŁEK', 'WTOREK', 'ŚRODA', 'CZWARTEK', 'PIĄTEK', 'SOBOTA', 'NIEDZIELA'];
  var EXAM_TYPES = ['Zaliczenie', 'Egzamin', 'Kolokwium'];

  function pad2(n) { return String(n).padStart(2, '0'); }
  function toMin(hhmm) { var p = String(hhmm).split(':'); return Number(p[0]) * 60 + Number(p[1]); }
  function hhmm(min) { return pad2(Math.floor(min / 60)) + ':' + pad2(min % 60); }
  function fromIso(iso) { var p = String(iso).split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function isoOf(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
  function addDays(d, n) { var c = new Date(d.getTime()); c.setDate(c.getDate() + n); return c; }
  /* local calendar days between two ISO dates, immune to DST */
  function dayNumber(iso) { var p = String(iso).split('-'); return Math.round(Date.UTC(+p[0], +p[1] - 1, +p[2]) / 864e5); }
  function isoFromDayNumber(n) { var d = new Date(n * 864e5); return d.getUTCFullYear() + '-' + pad2(d.getUTCMonth() + 1) + '-' + pad2(d.getUTCDate()); }

  /* "1 h 35 min", "45 min", "2 h" */
  function fmtDuration(min) {
    var h = Math.floor(min / 60), m = min % 60;
    if (!h) return m + ' min';
    return h + ' h' + (m ? ' ' + m + ' min' : '');
  }
  /* Polish plural: plural(5, 'zajęcia', 'zajęcia', 'zajęć') */
  function plural(n, one, few, many) {
    if (n === 1) return one;
    var m10 = n % 10, m100 = n % 100;
    return m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
  }
  function norm(s) { return String(s || '').toLocaleLowerCase('pl').replace(/\s+/g, ' ').trim(); }

  /* every lesson of the plan in date and time order */
  function lessons(plan) {
    var out = [];
    plan.weeks.forEach(function (w) {
      DAY_KEYS.forEach(function (k) { ((w.days && w.days[k]) || []).forEach(function (l) { out.push(l); }); });
    });
    return out;
  }

  /* breaks of at least minGap minutes between consecutive classes of one day: [{index, from, to, minutes}],
     index being the lesson the break follows; overlapping classes (subgroups) are merged first */
  function gaps(dayLessons, minGap) {
    var out = [], end = -1;
    dayLessons.forEach(function (l, i) {
      var s = toMin(l.start), e = toMin(l.end);
      if (end >= 0 && s - end >= minGap) out.push({ index: i - 1, from: end, to: s, minutes: s - end });
      end = Math.max(end, e);
    });
    return out;
  }

  function isExam(type) { return EXAM_TYPES.indexOf(type) >= 0; }

  /* per subject: how many of its classes are over, by type, and the next one */
  function subjectProgress(plan, todayIso, nowMin) {
    var by = {};
    lessons(plan).forEach(function (l) {
      var s = by[l.subject_full] = by[l.subject_full] || { subject: l.subject_full, total: 0, done: 0, byType: {}, next: null, last: null };
      s.total++;
      s.byType[l.type_full || 'Inne'] = (s.byType[l.type_full || 'Inne'] || 0) + 1;
      var over = l.date < todayIso || (l.date === todayIso && toMin(l.end) <= nowMin);
      if (over) s.done++;
      else if (!s.next) s.next = l;
      s.last = l;
    });
    return Object.keys(by).sort(function (a, b) { return a.localeCompare(b, 'pl'); }).map(function (k) { return by[k]; });
  }

  /* which meeting of its subject and type each class is: lessonKey -> {n, of}, e.g. the 3rd of 15 lectures.
     Counted over the whole term in date order, the same way catchUp numbers the classes of other groups. */
  function ordinals(plan) {
    var all = lessons(plan), seen = {}, totals = {}, out = {};
    var kind = function (l) { return norm(l.subject_full) + '|' + (norm(l.type_full) || 'inne'); };
    all.forEach(function (l) { totals[kind(l)] = (totals[kind(l)] || 0) + 1; });
    all.forEach(function (l) {
      var k = kind(l);
      seen[k] = (seen[k] || 0) + 1;
      out[lessonKey(l)] = { n: seen[k], of: totals[k] };
    });
    return out;
  }

  /* numbers for the statistics sheet */
  function stats(plan) {
    var all = lessons(plan);
    var minutes = 0, byType = {}, byDow = [0, 0, 0, 0, 0, 0, 0], rooms = {}, subjects = {}, days = {};
    var earliest = null, latest = null;
    all.forEach(function (l) {
      var s = toMin(l.start), e = toMin(l.end), len = e - s;
      minutes += len;
      var t = l.type_full || 'Inne';
      byType[t] = byType[t] || { type: t, count: 0, minutes: 0 };
      byType[t].count++;
      byType[t].minutes += len;
      byDow[(fromIso(l.date).getDay() + 6) % 7] += len;
      if (l.room && l.room !== '-') rooms[l.room] = (rooms[l.room] || 0) + 1;
      subjects[l.subject_full] = 1;
      var d = days[l.date] = days[l.date] || { date: l.date, start: s, end: e, minutes: 0, lessons: [] };
      d.start = Math.min(d.start, s);
      d.end = Math.max(d.end, e);
      d.minutes += len;
      d.lessons.push(l);
      if (!earliest || s < earliest.min) earliest = { min: s, date: l.date };
      if (!latest || e > latest.min) latest = { min: e, date: l.date };
    });
    var dayList = Object.keys(days).sort().map(function (k) { return days[k]; });
    var longest = null, gapMinutes = 0, gapCount = 0;
    dayList.forEach(function (d) {
      if (!longest || d.end - d.start > longest.end - longest.start) longest = d;
      gaps(d.lessons, 30).forEach(function (g) { gapMinutes += g.minutes; gapCount++; });
    });
    var weekly = plan.weeks.map(function (w) {
      var m = 0;
      DAY_KEYS.forEach(function (k) { ((w.days && w.days[k]) || []).forEach(function (l) { m += toMin(l.end) - toMin(l.start); }); });
      return { monday: w.monday, label: w.label, minutes: m };
    });
    var active = weekly.filter(function (w) { return w.minutes > 0; });
    var topRoom = Object.keys(rooms).sort(function (a, b) { return rooms[b] - rooms[a] || a.localeCompare(b); })[0] || null;
    return {
      lessons: all.length,
      minutes: minutes,
      subjects: Object.keys(subjects).length,
      days: dayList.length,
      activeWeeks: active.length,
      avgWeekMinutes: active.length ? Math.round(minutes / active.length) : 0,
      byType: Object.keys(byType).map(function (k) { return byType[k]; }).sort(function (a, b) { return b.minutes - a.minutes; }),
      byDow: byDow,
      weekly: weekly,
      earliest: earliest,
      latest: latest,
      longest: longest ? { date: longest.date, start: longest.start, end: longest.end } : null,
      gapCount: gapCount,
      gapMinutes: gapMinutes,
      topRoom: topRoom ? { room: topRoom, count: rooms[topRoom] } : null
    };
  }

  /* ---------- "the plan changed since your last visit" ---------- */
  function lessonKey(l) { return [l.date, l.start, l.end, l.subject_full, l.type_full, l.room].join('|'); }
  function fingerprint(plan) { return lessons(plan).map(lessonKey); }
  function parseKey(k) {
    var p = k.split('|');
    return { date: p[0], start: p[1], end: p[2], subject_full: p[3], type_full: p[4], room: p[5] };
  }
  /* classes added and removed between two fingerprints; a class whose room or time moved shows as both */
  function diff(before, after) {
    var a = {}, b = {};
    before.forEach(function (k) { a[k] = (a[k] || 0) + 1; });
    after.forEach(function (k) { b[k] = (b[k] || 0) + 1; });
    var added = [], removed = [];
    Object.keys(b).forEach(function (k) { for (var i = a[k] || 0; i < b[k]; i++) added.push(parseKey(k)); });
    Object.keys(a).forEach(function (k) { for (var i = b[k] || 0; i < a[k]; i++) removed.push(parseKey(k)); });
    var byWhen = function (x, y) { return lessonKey(x) < lessonKey(y) ? -1 : 1; };
    return { added: added.sort(byWhen), removed: removed.sort(byWhen) };
  }

  /* ---------- comparing groups ---------- */
  /* stretches of at least minLen minutes inside [dayStart, dayEnd] that no list of intervals touches */
  function freeWindows(intervalLists, dayStart, dayEnd, minLen) {
    var busy = [];
    intervalLists.forEach(function (list) { list.forEach(function (iv) { busy.push([iv[0], iv[1]]); }); });
    busy.sort(function (x, y) { return x[0] - y[0]; });
    var out = [], cur = dayStart;
    busy.forEach(function (iv) {
      if (iv[0] - cur >= minLen && iv[0] <= dayEnd) out.push({ from: cur, to: Math.min(iv[0], dayEnd) });
      cur = Math.max(cur, iv[1]);
    });
    if (dayEnd - cur >= minLen) out.push({ from: cur, to: dayEnd });
    return out.filter(function (w) { return w.to - w.from >= minLen; });
  }
  function intervals(dayLessons) { return dayLessons.map(function (l) { return [toMin(l.start), toMin(l.end)]; }); }
  function overlaps(dayLessons, s, e) {
    return dayLessons.some(function (l) { return toMin(l.start) < e && toMin(l.end) > s; });
  }
  /* lessons of one date from a plan, as a map built once */
  function byDate(plan) {
    var m = {};
    lessons(plan).forEach(function (l) { (m[l.date] = m[l.date] || []).push(l); });
    return m;
  }

  /* ---------- "Odrabianie": the same class in another group of the year ---------- */
  function yearOf(group) { var m = /^([A-Za-z]{3}\d{2})/.exec(group || ''); return m ? m[1].toUpperCase() : null; }

  /* peer groups of one major and year: same faculty + year, same leading-letter major of the code
     remainder, same code shape. WCY26KY3S1 pairs with WCY26KY1S1 (the 1st group of the same major),
     but not with WCY26EL2S6 (another major) or WEL26ELTS6 (another code shape). */
  function peerStem(group) {
    var m = /^([A-Za-z]{3}\d{2})([A-Za-z]*)/.exec(group || '');
    if (!m) return null;
    return (m[1] + '|' + m[2] + '|' + String(group).length).toUpperCase();
  }
  function peersOf(myGroup, groups) {
    var stem = peerStem(myGroup);
    if (!stem) return [];
    return groups.filter(function (g) { return g !== myGroup && peerStem(g) === stem; });
  }

  /* a lecture several groups attend together is the same class, not another chance to catch up */
  function shared(dayLessons, s, e, room, subject) {
    return dayLessons.some(function (l) {
      return toMin(l.start) === s && toMin(l.end) === e && l.room === room && norm(l.subject_full) === norm(subject);
    });
  }
  /* year/<PREFIX>.json -> the classes of one subject (and type, when given) in the peer groups of the
     same major and year, from today on, each marked with whether it clashes with my own classes and
     with its ordinal within its group's (subject, type): the Nth class covers the same material as
     my Nth class, so only ordinals my own program also has are offered. Classes my group attends
     together with the peer group are left out. */
  function catchUp(yearData, myGroup, myByDate, subject, type, todayIso) {
    var epoch = dayNumber(yearData.epoch), names = yearData.names, e = yearData.e, out = [];
    var want = norm(subject), wantType = type ? norm(type) : null;
    var today = dayNumber(todayIso);
    var peers = {};
    peersOf(myGroup, yearData.groups).forEach(function (g) { peers[g] = 1; });
    var myTotals = {};
    Object.keys(myByDate).forEach(function (date) {
      (myByDate[date] || []).forEach(function (l) {
        var k = norm(l.subject_full) + '|' + norm(l.type_full || 'Inne');
        myTotals[k] = (myTotals[k] || 0) + 1;
      });
    });
    var ord = {};
    for (var i = 0; i + 6 < e.length; i += 7) {
      var group = yearData.groups[e[i]];
      if (group === myGroup || !peers[group]) continue;
      var sname = names[e[i + 1]], tname = names[e[i + 2]];
      if (norm(sname) !== want) continue;
      var tn = norm(tname), tkey = tn || 'inne';
      if (wantType && tn !== wantType) continue;
      var key = group + '|' + norm(sname) + '|' + tkey;
      var n = (ord[key] || 0) + 1;
      ord[key] = n;
      var day = epoch + e[i + 4];
      if (day < today) continue;
      var date = isoFromDayNumber(day), s = e[i + 5], en = e[i + 6], room = names[e[i + 3]];
      if (n > (myTotals[norm(sname) + '|' + tkey] || 0)) continue;
      if (shared(myByDate[date] || [], s, en, room, sname)) continue;
      out.push({
        group: group, date: date, start: s, end: en, type: tname, room: room, n: n,
        clash: overlaps(myByDate[date] || [], s, en)
      });
    }
    out.sort(function (x, y) { return x.date < y.date ? -1 : x.date > y.date ? 1 : x.start - y.start || (x.group < y.group ? -1 : 1); });
    return out;
  }

  /* ---------- month view ---------- */
  /* the Monday-first weeks covering a month: arrays of 7 ISO dates, null outside the month */
  function monthGrid(year, month) {
    var first = new Date(year, month, 1), weeks = [], week = [];
    var lead = (first.getDay() + 6) % 7;
    for (var i = 0; i < lead; i++) week.push(null);
    for (var d = first; d.getMonth() === month; d = addDays(d, 1)) {
      week.push(isoOf(d));
      if (week.length === 7) { weeks.push(week); week = []; }
    }
    if (week.length) { while (week.length < 7) week.push(null); weeks.push(week); }
    return weeks;
  }

  var PlanInsights = {
    toMin: toMin, hhmm: hhmm, fmtDuration: fmtDuration, plural: plural, norm: norm,
    lessons: lessons, gaps: gaps, isExam: isExam, subjectProgress: subjectProgress, ordinals: ordinals, stats: stats,
    lessonKey: lessonKey, fingerprint: fingerprint, diff: diff,
    freeWindows: freeWindows, intervals: intervals, overlaps: overlaps, byDate: byDate,
    yearOf: yearOf, peersOf: peersOf, catchUp: catchUp,
    monthGrid: monthGrid, dayNumber: dayNumber, isoFromDayNumber: isoFromDayNumber
  };
  if (typeof module === 'object' && module.exports) module.exports = PlanInsights;
  else root.PlanInsights = PlanInsights;
})(this);
