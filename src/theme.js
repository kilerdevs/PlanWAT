(function () {
  var root = document.documentElement;
  function stored() {
    try { var t = window.localStorage.getItem('planwat:theme'); return t === 'light' || t === 'dark' ? t : 'auto'; } catch (e) { return 'auto'; }
  }
  function isDark(t) {
    return t === 'dark' || (t === 'auto' && !(window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches));
  }
  function apply(t) {
    if (t === 'auto') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', t);
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i++) {
      var m = metas[i];
      if (!m.hasAttribute('data-content')) { m.setAttribute('data-content', m.getAttribute('content')); m.setAttribute('data-media', m.getAttribute('media') || ''); }
      if (t === 'auto') {
        m.setAttribute('content', m.getAttribute('data-content'));
        if (m.getAttribute('data-media')) m.setAttribute('media', m.getAttribute('data-media'));
      } else {
        m.setAttribute('content', isDark(t) ? '#000000' : '#f2f2f7');
        m.removeAttribute('media');
      }
    }
  }
  /* a chosen theme fades in over a moment; the first paint and reduced motion stay instant */
  var fadeTimer;
  function fade() {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    root.classList.add('theme-fade');
    clearTimeout(fadeTimer);
    fadeTimer = setTimeout(function () { root.classList.remove('theme-fade'); }, 340);
  }
  apply(stored());
  document.addEventListener('DOMContentLoaded', function () {
    var buttons = document.querySelectorAll('[data-theme-set]');
    function mark() {
      var t = stored();
      for (var i = 0; i < buttons.length; i++) buttons[i].setAttribute('aria-pressed', String(buttons[i].getAttribute('data-theme-set') === t));
    }
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', function (e) {
        var t = e.currentTarget.getAttribute('data-theme-set');
        try { if (t === 'auto') window.localStorage.removeItem('planwat:theme'); else window.localStorage.setItem('planwat:theme', t); } catch (err) { /* private mode: the choice lasts until the page closes */ }
        fade();
        apply(t);
        mark();
      });
    }
    mark();
    /* the footer's Motyw: swaps the row of tools for the three choices, shows the one in force, swaps back once picked */
    var btn = document.getElementById('themeBtn'), row = document.getElementById('themeRow'), tools = document.getElementById('footTools');
    if (!btn || !row || !tools) return;
    var NAMES = { auto: 'automatyczny', dark: 'ciemny', light: 'jasny' };
    function show(t) { btn.setAttribute('data-mode', t); btn.setAttribute('aria-label', 'Motyw: ' + NAMES[t]); }
    function open(on) {
      row.hidden = !on;
      tools.hidden = on;
      tools.classList.toggle('again', !on);
      btn.setAttribute('aria-expanded', String(on));
    }
    show(stored());
    btn.addEventListener('click', function () { open(true); (row.querySelector('[aria-pressed="true"]') || row.querySelector('button')).focus(); });
    row.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-theme-set]');
      if (!b) return;
      show(b.getAttribute('data-theme-set'));
      setTimeout(function () { open(false); btn.focus(); }, 220);
    });
    row.addEventListener('keydown', function (e) { if (e.key === 'Escape') { e.stopPropagation(); open(false); btn.focus(); } });
    document.addEventListener('click', function (e) { if (!row.hidden && !row.contains(e.target) && !btn.contains(e.target)) open(false); });
  });
})();
