/* Campus map data and helpers: WAT buildings, room → building, search and the day's stops.
   Pure (no DOM), so node:test covers it; inlined into the group page and the map page.
   Building coordinates: © OpenStreetMap contributors, ODbL 1.0 (see THIRD-PARTY-NOTICES.md). */
(function (root) {
  'use strict';

  /* faculty code → label and marker colour; '' is everything else */
  var FACULTIES = [
    { code: 'WIM', label: 'Inżynieria Mechaniczna (WIM)', color: '#68ab40' },
    { code: 'WML', label: 'Mechatronika i Lotnictwo (WML)', color: '#0aa5aa' },
    { code: 'WEL', label: 'Elektronika (WEL)', color: '#9e3a7a' },
    { code: 'WIG', label: 'Inżynieria Lądowa i Geodezja (WIG)', color: '#e14459' },
    { code: 'WCY', label: 'Cybernetyka (WCY)', color: '#ec9e34' },
    { code: 'IOE', label: 'Optoelektronika (IOE)', color: '#e57766' },
    { code: 'WLO', label: 'Bezpieczeństwo i Zarządzanie (WLO)', color: '#8a5a36' },
    { code: 'WTC', label: 'Nowe Technologie i Chemia (WTC)', color: '#3b6b98' },
    { code: '', label: 'Inne', color: '#78909c' }
  ];

  /* [code, name, description, faculty, lat, lng]; code is what rooms refer to (null: not a teaching building) */
  var ROWS = [
    ['100', 'Budynek główny WAT (Sztab 100)', 'Rektorat, sale „bud. S”', '', 52.253203, 20.900203],
    [null, 'Wejście główne', 'Wejście A do budynku głównego', '', 52.253155, 20.899481],
    [null, 'Brama nr 2', 'Brama nr 2, na południe od budynku głównego', '', 52.252213, 20.900425],
    [null, 'Brama nr 4', 'Brama nr 4, od ul. Radiowej', '', 52.25533, 20.904666],
    [null, 'Plac apelowy', 'Plac apelowy', '', 52.25538, 20.900848],
    ['K', 'Klub WAT / Kino', 'Studium Języków Obcych, Kaliskiego 25A', '', 52.255191, 20.895263],
    ['BIBL', 'Biblioteka Główna WAT', 'Biblioteka Główna', '', 52.252979, 20.895584],
    ['121', 'WCBKT (Budynek 121)', 'Wojskowe Centralne Biuro Konstrukcyjno-Technologiczne', '', 52.255793, 20.903],
    ['28', 'PTW (Budynek 28)', 'PTW', '', 52.249537, 20.903713],
    ['1', 'Budynek 1', 'Budynek 1', '', 52.248871, 20.901531],
    ['10', 'Budynek 10', 'Budynek 10', '', 52.250782, 20.904347],
    ['13', 'Budynek 13', 'Budynek 13', '', 52.253732, 20.901981],
    ['35', 'Budynek 35', 'Budynek 35', '', 52.252744, 20.901987],
    ['38', 'Budynek 38', 'Budynek 38', '', 52.251605, 20.903238],
    ['39', 'Budynek 39', 'Budynek 39', '', 52.251753, 20.904036],
    ['40', 'Budynek 40', 'Budynek 40', '', 52.252482, 20.904157],
    ['43', 'Budynek 43', 'Budynek 43', '', 52.251319, 20.904193],
    ['131', 'Budynek 131', 'Budynek 131', '', 52.251699, 20.904391],
    ['64', 'Budynek 64', 'Budynek 64', '', 52.254956, 20.904569],
    ['50', 'Budynek 50', 'Budynek 50', '', 52.251868, 20.908177],
    ['52', 'Budynek 52', 'Budynek 52', '', 52.252898, 20.908124],
    ['60', 'Budynek 60', 'Budynek 60', '', 52.252047, 20.907052],
    ['125', 'Budynek 125', 'Budynek 125', '', 52.252895, 20.908772],
    ['126', 'Budynek 126', 'Budynek 126', '', 52.252645, 20.909319],
    ['127', 'Budynek 127', 'Budynek 127', '', 52.252236, 20.910066],
    ['15', 'Budynek 15', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.249929, 20.902781],
    ['17', 'Budynek 17', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.250599, 20.900918],
    ['19', 'Budynek 19', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.251494, 20.899437],
    ['20', 'Budynek 20', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.250597, 20.89999],
    ['21', 'Budynek 21', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.250174, 20.899994],
    ['23', 'Budynek 23', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.250095, 20.902329],
    ['23A', 'Budynek 23A', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.2501, 20.90178],
    ['34A', 'Budynek 34A', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.251822, 20.901901],
    ['54', 'Budynek 54', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.253287, 20.90678],
    ['157', 'Budynek 157', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.25255, 20.906703],
    ['62', 'Budynek 62', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.254333, 20.900558],
    ['68', 'Budynek 68', 'Wydział Inżynierii Mechanicznej', 'WIM', 52.256336, 20.899852],
    ['25', 'Budynek 25', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.249167, 20.900383],
    ['26', 'Budynek 26', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.249018, 20.900807],
    ['36', 'Budynek 36', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.25265, 20.902807],
    ['63', 'Budynek 63', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.255046, 20.902107],
    ['63A', 'Budynek 63A', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.255197, 20.902472],
    ['66', 'Budynek 66', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.256325, 20.901953],
    ['67', 'Budynek 67', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.256939, 20.900563],
    ['69', 'Budynek 69', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.255598, 20.899451],
    ['72', 'Budynek 72', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.257372, 20.899095],
    ['74', 'Budynek 74', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'WML', 52.257035, 20.901069],
    [null, 'Hangar lotniczy', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa - Radiowa 9', 'WML', 52.255458, 20.908116],
    ['29', 'Budynek 29', 'Wydział Elektroniki', 'WEL', 52.24867, 20.903613],
    ['42', 'Budynek 42', 'Wydział Elektroniki', 'WEL', 52.252776, 20.905235],
    ['45', 'Budynek 45', 'Wydział Elektroniki', 'WEL', 52.252119, 20.905163],
    ['47', 'Budynek 47', 'Wydział Elektroniki', 'WEL', 52.252553, 20.905484],
    ['61', 'Budynek 61', 'Wydział Elektroniki', 'WEL', 52.254134, 20.902439],
    ['75', 'Budynek 75', 'Wydział Elektroniki', 'WEL', 52.251263, 20.905989],
    ['80', 'Budynek 80', 'Wydział Elektroniki', 'WEL', 52.249465, 20.904749],
    ['114', 'Budynek 114', 'Wydział Elektroniki - stacja radarowa', 'WEL', 52.24936, 20.905276],
    [null, 'Nowy budynek WEL', 'Wydział Elektroniki - przy budynku 61', 'WEL', 52.254513, 20.902517],
    ['53', 'Budynek 53', 'Wydział Inżynierii Lądowej i Geodezji', 'WIG', 52.253951, 20.904793],
    ['56', 'Budynek 56', 'Wydział Inżynierii Lądowej i Geodezji (część budynku)', 'WIG', 52.25445, 20.905554],
    ['57', 'Budynek 57', 'Wydział Inżynierii Lądowej i Geodezji', 'WIG', 52.253536, 20.904892],
    ['58', 'Budynek 58', 'Wydział Inżynierii Lądowej i Geodezji', 'WIG', 52.253963, 20.904012],
    ['59', 'Budynek 59', 'Wydział Inżynierii Lądowej i Geodezji', 'WIG', 52.254261, 20.903722],
    ['98', 'Mikropoligon (Budynek 98)', 'Wydział Inżynierii Lądowej i Geodezji - laboratorium fortyfikacyjne', 'WIG', 52.248721, 20.900178],
    [null, 'Nowy budynek WIG', 'Wydział Inżynierii Lądowej i Geodezji - przy budynku 65', 'WIG', 52.254994, 20.903455],
    ['65', 'Budynek 65', 'Wydział Cybernetyki', 'WCY', 52.255348, 20.903758],
    [null, 'Centrum Innowacji i Cyberbezpieczeństwa', 'Wydział Cybernetyki - nowy budynek', 'WCY', 52.25335, 20.9027],
    ['41', 'Budynek 41', 'Instytut Optoelektroniki', 'IOE', 52.251, 20.903524],
    ['46', 'Budynek 46', 'Instytut Optoelektroniki', 'IOE', 52.251358, 20.906693],
    ['49', 'Budynek 49', 'Instytut Optoelektroniki', 'IOE', 52.251283, 20.90748],
    ['136', 'Budynek 136', 'Instytut Optoelektroniki', 'IOE', 52.25057, 20.905147],
    ['70', 'Budynek 70', 'Centrum Inżynierii Biomedycznej (CIB), Instytut Optoelektroniki', 'IOE', 52.25598, 20.898646],
    ['71', 'Budynek 71', 'Centrum Inżynierii Biomedycznej (CIB), Instytut Optoelektroniki', 'IOE', 52.256469, 20.89925],
    ['144', 'Budynek 144 (Przedszkole)', 'Instytut Optoelektroniki', 'IOE', 52.253606, 20.895186],
    ['135', 'Budynek 135', 'Wydział Bezpieczeństwa, Logistyki i Zarządzania, Szkoła Doktorska (SDR), Centrum Certyfikacji Jakości (CCJ)', 'WLO', 52.251307, 20.899266],
    ['158', 'Budynek 158', 'Wydział Bezpieczeństwa, Logistyki i Zarządzania', 'WLO', 52.252641, 20.903831],
    ['16', 'Budynek 16', 'Wydział Bezpieczeństwa, Logistyki i Zarządzania', 'WLO', 52.250352, 20.903443],
    ['22', 'Budynek 22 (BHP)', 'Wydział Bezpieczeństwa, Logistyki i Zarządzania, BHP', 'WLO', 52.250926, 20.901707],
    ['5', 'Budynek 5', 'Wydział Nowych Technologii i Chemii', 'WTC', 52.250667, 20.902422],
    ['14', 'Budynek 14', 'Wydział Nowych Technologii i Chemii', 'WTC', 52.249608, 20.902136],
    ['24', 'Budynek 24', 'Wydział Nowych Technologii i Chemii', 'WTC', 52.249292, 20.902199],
    ['34', 'Budynek 34', 'Wydział Nowych Technologii i Chemii', 'WTC', 52.252101, 20.901352],
    ['55', 'Budynek 55', 'Wydział Nowych Technologii i Chemii', 'WTC', 52.253639, 20.90712],
    [null, 'Stołówka Wojskowa 1', 'Stołówka Wojskowa 1', '', 52.254504, 20.894475],
    [null, 'Stołówka Wojskowa 2', 'Stołówka Wojskowa 2', '', 52.251564, 20.895983],
    [null, 'Stołówka Wojskowa 3', 'Stołówka Wojskowa 3', '', 52.252061, 20.895222],
    [null, 'Dom Studencki nr 3', 'Dom Studencki nr 3', '', 52.250078, 20.89583],
    [null, 'Dom Asystenta', 'Dom Asystenta', '', 52.249933, 20.897583],
    [null, 'Stadion WAT', 'Stadion WAT', '', 52.25282, 20.892992],
    [null, 'Ośrodek Szkoleniowo-Sportowy WAT', 'Studium Wychowania Fizycznego (SWF), Kartezjusza 1', '', 52.251174, 20.893344],
    [null, 'Przychodnia Zdrowia', 'Przychodnia Zdrowia', '', 52.250627, 20.895219],
    [null, 'Modułowy Budynek Dydaktyczny nr 2', 'Modułowy Budynek Dydaktyczny nr 2', '', 52.250748, 20.896476],
    [null, 'AW 1', 'Akademik Wojskowy nr 1', '', 52.252126, 20.897305],
    [null, 'AW 2', 'Akademik Wojskowy nr 2', '', 52.256541, 20.896868],
    [null, 'AW 3', 'Akademik Wojskowy nr 3', '', 52.250453, 20.891482],
    [null, 'AW 4', 'Akademik Wojskowy nr 4', '', 52.250817, 20.897452],
    [null, 'AW 5', 'Akademik Wojskowy nr 5', '', 52.254024, 20.897166],
    [null, 'AW 6', 'Akademik Wojskowy nr 6', '', 52.249912, 20.896602],
    [null, 'AW 7', 'Akademik Wojskowy nr 7', '', 52.248791, 20.90588]
  ];

  var BOUNDS = [[20.855, 52.232], [20.95, 52.272]];  // [[west, south], [east, north]]

  var byFaculty = {};
  FACULTIES.forEach(function (f) { byFaculty[f.code] = f; });
  var BUILDINGS = ROWS.map(function (r, i) {
    return { id: i, code: r[0], name: r[1], desc: r[2], faculty: byFaculty[r[3]] || byFaculty[''], lat: r[4], lng: r[5] };
  });

  var CODE_RE = /^\d{1,3}[A-Z]?$/;

  /* a building by its code; "55A" falls back to "55" */
  function findBuilding(code) {
    if (!code) return null;
    var c = String(code).trim().toUpperCase();
    var hit = function (k) { for (var i = 0; i < BUILDINGS.length; i++) if (BUILDINGS[i].code === k) return BUILDINGS[i]; return null; };
    return hit(c) || hit(c.replace(/[A-Z]+$/, '')) || null;
  }

  /* The building a LOCATION points at, or null. Rooms read "<room> <building>" or "<room>/ <building>"
     ("314 S", "aula/ 135", "106 65 120 65", "1.9/ 16;1.10/ 16"); S is the main building (100),
     K the Klub, Bibl. the library. Only the first room counts. */
  function roomBuilding(room) {
    var seg = String(room || '').split(';')[0].trim();
    var tokens = seg.split(/\s+/);
    var token;
    var slash = tokens[0].indexOf('/');
    if (slash >= 0 && slash < tokens[0].length - 1) token = tokens[0].slice(slash + 1);
    else token = tokens[1];
    if (!token) return null;
    token = token.replace(/^\/+|[/.]+$/g, '').toUpperCase();
    if (token === 'S') token = '100';
    else if (token === 'BIBL') return 'BIBL';
    else if (token === 'K') return 'K';
    if (!CODE_RE.test(token)) return null;
    var b = findBuilding(token);
    return b ? b.code : null;
  }

  function fold(s) {
    return String(s).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ł/g, 'l');
  }

  /* buildings matching a query: exact code first, then name, then description */
  function search(query, max) {
    var q = fold(query).trim();
    if (!q) return [];
    var exact = [], named = [], described = [];
    BUILDINGS.forEach(function (b) {
      if (b.code && fold(b.code) === q) exact.push(b);
      else if (fold(b.name).indexOf(q) >= 0) named.push(b);
      else if (fold(b.desc).indexOf(q) >= 0 || fold(b.faculty.label).indexOf(q) >= 0) described.push(b);
    });
    return exact.concat(named, described).slice(0, max || 15);
  }

  /* one day's classes from a PlanICS.toPlan result, in time order, each with its building (or null) */
  function dayStops(plan, iso) {
    var stops = [];
    (plan.weeks || []).forEach(function (w) {
      Object.keys(w.days || {}).forEach(function (k) {
        w.days[k].forEach(function (l) {
          if (l.date !== iso) return;
          var code = roomBuilding(l.room);
          stops.push({ start: l.start, end: l.end, subject: l.subject_full, type: l.type_full, room: l.room,
            building: code ? findBuilding(code) : null });
        });
      });
    });
    return stops.sort(function (a, b) { return a.start < b.start ? -1 : a.start > b.start ? 1 : a.end < b.end ? -1 : a.end > b.end ? 1 : 0; });
  }

  function directionsUrl(b) {
    return 'https://www.google.com/maps/dir/?api=1&destination=' + b.lat + ',' + b.lng + '&travelmode=walking';
  }

  /* "#111" or "#fff", whichever reads on the given #rrggbb (WCAG relative luminance) */
  function inkOn(hex) {
    var lin = function (v) { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    var r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b) > 0.179 ? '#111' : '#fff';
  }

  var Campus = {
    FACULTIES: FACULTIES, BUILDINGS: BUILDINGS, BOUNDS: BOUNDS,
    findBuilding: findBuilding, roomBuilding: roomBuilding, search: search, dayStops: dayStops,
    directionsUrl: directionsUrl, inkOn: inkOn
  };
  if (typeof module === 'object' && module.exports) module.exports = Campus;
  else root.Campus = Campus;
})(this);
