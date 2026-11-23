// Diff-Seiten: Rahmen um das Neue nach einem Tausch (tausch.js) – die Zeilen, die seit dem vorher gezeigten Stand neu
// sind (api/diff). Der Rahmen bleibt bis zur nächsten Änderung. --beobachten (waggon.beobachten): sanft zum ersten
// Neuen scrollen, und Tab zu → Server beendet sich (Beacon).
// Braucht von App: waggon, dateien. Stellt bereit: einrahmen.
(() => {
  const {waggon, dateien} = App;
  if (waggon.beobachten)
    addEventListener('pagehide', () => navigator.sendBeacon('/tschuess', JSON.stringify({mr: waggon.id, k: waggon.k})));
  /** zeilen {pfad: [[von, bis], …]} einrahmen (alte Rahmen weg). true, wenn die Seite dorthin scrollt. */
  function einrahmen(zeilen) {
    document
      .querySelectorAll('tr.neu-rahmen')
      .forEach(r => r.classList.remove('neu-rahmen', 'neu-anfang', 'neu-ende'));
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
    if (!erste || !waggon.beobachten) return false;
    setTimeout(() => erste.scrollIntoView({block: 'center', behavior: 'smooth'}), 150);
    return true;
  }
  App.einrahmen = einrahmen;
})();
