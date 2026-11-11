// merge-train --beobachten (nur Diff-Seiten, waggon.beobachten): Tab zu → Server beendet sich (Beacon); nach dem
// Neuladen wegen einer Änderung im Repo (review.js merkt sich den alten Stand) die neuen Zeilen einrahmen und sanft
// dorthin scrollen. Der Rahmen bleibt bis zur nächsten Änderung.
// Braucht von App: waggon, dateien, waggonAbfrage. Stellt bereit: nichts.
(() => {
  const {waggon, dateien} = App;
  if (!waggon.beobachten) return;
  addEventListener('pagehide', () => navigator.sendBeacon('/tschuess', JSON.stringify({mr: waggon.id, k: waggon.k})));
  let alt = '';
  try {
    alt = sessionStorage.beobachtetAlt || '';
    sessionStorage.removeItem('beobachtetAlt');
  } catch (_) {}
  if (!alt || alt === waggon.sha) return;
  function einrahmen(zeilen) {
    let erste = null;
    for (const d of dateien) {
      const bereiche = zeilen[d.dataset.pfad];
      if (!bereiche) continue;
      for (const tab of d.querySelectorAll('table')) {
        let vorige = null;
        for (const r of tab.querySelectorAll('tr[data-b]')) {
          const b = +r.dataset.b,
            drin = bereiche.some(([von, bis]) => von <= b && b <= bis);
          if (!drin) {
            if (vorige) vorige.classList.add('neu-ende');
            vorige = null;
            continue;
          }
          r.classList.add('neu-rahmen');
          if (!vorige) r.classList.add('neu-anfang');
          vorige = r;
          if (!erste && tab.offsetParent) erste = r;
        }
        if (vorige) vorige.classList.add('neu-ende');
      }
    }
    if (erste) setTimeout(() => erste.scrollIntoView({block: 'center', behavior: 'smooth'}), 150);
  }
  const abfrage = App.waggonAbfrage() + '&alt=' + encodeURIComponent(alt) + '&sha=' + encodeURIComponent(waggon.sha);
  fetch('/api/neu?' + abfrage)
    .then(r => r.json())
    .then(d => d.ok && einrahmen(d.zeilen || {}))
    .catch(() => {});
})();
