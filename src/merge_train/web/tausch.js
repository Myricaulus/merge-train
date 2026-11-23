// Diff-Seiten: neuer Stand ohne Neuladen (Issue #6). Holt api/diff und tauscht je Datei: gleicher Schlüssel
// (data-schluessel) bleibt im DOM samt aufgeklapptem Kontext, Feldern und Haken, geänderte und neue Dateien kommen
// dazu, weggefallene gehen. Eine geänderte oder weggefallene Datei mit offenem Eingabefeld wartet (Marke im Kopf), bis
// das Feld zu ist. Danach: Einrichtung der neuen Dateien, Haken, Boxen, Rahmen um das Neue; die oberste sichtbare Zeile
// bleibt, wo sie war. Ganz neu geladen wird nur bei neuer Version (oder wenn der Waggon jetzt anderes kann).
// Braucht von App: waggon, el, melden, dateien, dateiEinrichten, dateienNeu, kopfhoeheSetzen, reviewLaden, hakenLaden,
// einrahmen, zugHolen, waggonAbfrage. Ersetzt: neuHolen.
(() => {
  const {el, waggon, dateien} = App;
  const wartend = new Map(), // Schlüssel der neuen Fassung → ihre Datei, solange die alte ein offenes Feld hat
    verwaist = new Set(); // weggefallene Dateien, in denen noch ein Feld offen ist
  let laeuft = null; // Anfrage in Arbeit: ein zweiter Anstoß hängt sich an
  const offen = d => !!d.querySelector('textarea');
  const sichtbareTabelle = d => d.querySelector(document.body.classList.contains('inline') ? 'table.inl' : 'table.sbs');
  function ausHtml(h) {
    const t = document.createElement('template');
    t.innerHTML = h;
    return t.content;
  }
  /** Oberste sichtbare Zeile unter dem Kopf (Datei + data-b) und ihr Abstand zum Fensterrand. */
  function anker() {
    const oben = document.getElementById('kopf').getBoundingClientRect().bottom;
    for (const d of dateien) {
      if (d.classList.contains('ausgefiltert') || d.getBoundingClientRect().bottom <= oben) continue;
      const tab = d.open && sichtbareTabelle(d),
        z = tab && [...tab.querySelectorAll('tr[data-b]')].find(r => r.getBoundingClientRect().bottom > oben);
      return {d, pfad: d.dataset.pfad, b: z ? z.dataset.b : null, top: (z || d).getBoundingClientRect().top};
    }
    return null;
  }
  function ankerHalten(a) {
    if (!a) return;
    const d = a.d.isConnected ? a.d : dateien.find(x => x.dataset.pfad === a.pfad);
    if (!d) return;
    const tab = d.open && sichtbareTabelle(d),
      z = a.b && tab && tab.querySelector('tr[data-b="' + a.b + '"]');
    scrollBy(0, (z || d).getBoundingClientRect().top - a.top);
  }
  function warteMarke(d, an) {
    d.classList.toggle('wartet', an);
    const s = d.querySelector('summary');
    let m = s.querySelector('.wartet-marke');
    if (an && !m)
      s.append(
        (m = el(
          'span',
          {class: 'badge wartet-marke', title: 'Diese Datei hat sich geändert. Sie wird getauscht, sobald das Feld zu ist.'},
          'geändert'
        ))
      );
    if (!an) m?.remove();
  }
  /** Seite ganz neu laden (neue Version), erst ohne offenes Feld */
  function neuLaden(meldung) {
    if (document.querySelector('textarea')) return false;
    try {
      sessionStorage.meldung = meldung || '';
    } catch (_) {}
    location.reload();
    return true;
  }
  function tauschen(r, meldung) {
    if (r.mr.version !== waggon.version || JSON.stringify(r.mr.kann) !== JSON.stringify(waggon.kann))
      return neuLaden(meldung || 'merge-train wurde aktualisiert – Seite neu geladen');
    const a = anker(),
      main = document.querySelector('main'),
      vorhanden = new Map(dateien.map(d => [d.dataset.schluessel, d])),
      neuePfade = new Set(),
      soll = [],
      einrichten = [];
    let geaendert = 0,
      dazu = 0;
    for (const f of r.dateien) {
      let d = vorhanden.get(f.schluessel);
      if (d) {
        vorhanden.delete(f.schluessel);
        warteMarke(d, false);
        soll.push(d);
        neuePfade.add(d.dataset.pfad);
        continue;
      }
      d = wartend.get(f.schluessel) || (f.html ? ausHtml(f.html).firstElementChild : null);
      if (!d) return neuLaden(meldung); // der Server rechnete mit einer Fassung, die die Seite nicht mehr hat
      wartend.delete(f.schluessel);
      neuePfade.add(d.dataset.pfad);
      const alt = [...vorhanden.values()].find(x => x.dataset.pfad === d.dataset.pfad);
      if (alt && offen(alt)) {
        vorhanden.delete(alt.dataset.schluessel);
        wartend.set(f.schluessel, d);
        warteMarke(alt, true);
        soll.push(alt);
        continue;
      }
      if (alt) geaendert++;
      else dazu++;
      soll.push(d);
      einrichten.push(d);
    }
    let weg = 0;
    for (const d of vorhanden.values()) {
      if (neuePfade.has(d.dataset.pfad)) continue; // getauscht
      if (offen(d)) {
        warteMarke(d, true); // weggefallen, aber man schreibt noch darin
        verwaist.add(d);
        soll.push(d);
      } else weg++;
    }
    const leer = ausHtml(r.leer).firstElementChild;
    if (leer) soll.unshift(leer);
    let vor = main.firstElementChild;
    for (const e of soll) {
      if (e === vor) vor = vor.nextElementSibling;
      else main.insertBefore(e, vor); // nur verschieben, was nicht schon an seinem Platz steht (Fokus, Felder)
    }
    while (vor) {
      const n = vor.nextElementSibling;
      vor.remove();
      vor = n;
    }
    soll.filter(e => e.classList.contains('datei')).forEach((d, i) => (d.id = 'd' + i));
    document.getElementById('titel').replaceChildren(ausHtml(r.titel));
    const commits = document.getElementById('commits');
    commits.replaceChildren(commits.querySelector('summary'), ausHtml(r.commits));
    document.getElementById('nachcommits').replaceChildren(ausHtml(r.nach_commits));
    const liste = document.getElementById('liste');
    liste.replaceChildren(liste.querySelector('h2'), ausHtml(r.liste));
    Object.assign(waggon, r.mr);
    App.dateienNeu();
    einrichten.forEach(App.dateiEinrichten);
    App.hakenLaden(einrichten);
    App.kopfhoeheSetzen();
    ankerHalten(a);
    const springt = App.einrahmen(r.zeilen || {});
    App.reviewLaden().then(() => springt || ankerHalten(a));
    App.zugHolen();
    const was = [geaendert && geaendert + ' geändert', dazu && dazu + ' neu', weg && weg + ' weg'].filter(Boolean);
    App.melden((meldung ? meldung + ' · ' : '') + 'neuer Stand' + (was.length ? ': ' + was.join(', ') : ''));
    return true;
  }
  /** Neuen Stand zeigen: api/diff holen und je Datei tauschen. meldung: was davor geschah (z. B. „MR-Daten geholt“). */
  function diffNeu(meldung) {
    if (laeuft) return laeuft;
    if (document.getElementById('popup')) {
      // die Datei im Popup ist geliehen (diff.js): erst nach dem Schließen tauschen
      return new Promise(r => setTimeout(() => r(diffNeu(meldung)), 1000));
    }
    laeuft = fetch('/api/diff?' + App.waggonAbfrage())
      .then(r => r.json())
      .then(r => {
        if (!r.ok) App.melden(r.text);
        else if (r.gleich) App.melden(meldung || 'keine neuen Änderungen');
        else tauschen(r, meldung);
      })
      .catch(() => App.melden('merge-train-Server nicht erreichbar'))
      .finally(() => {
        laeuft = null;
      });
    return laeuft;
  }
  // wartende Dateien: sobald das Feld zu ist, die neue Fassung einsetzen bzw. die weggefallene entfernen
  setInterval(() => {
    if ((!wartend.size && !verwaist.size) || laeuft) return;
    const a = anker(),
      getauscht = [];
    let geaendert = false;
    for (const [s, neu] of wartend) {
      const alt = dateien.find(d => d.classList.contains('wartet') && d.dataset.pfad === neu.dataset.pfad);
      if (alt && offen(alt)) continue;
      wartend.delete(s);
      if (!alt) continue;
      neu.id = alt.id;
      alt.replaceWith(neu);
      getauscht.push(neu);
      geaendert = true;
    }
    for (const d of verwaist) {
      if (offen(d)) continue;
      verwaist.delete(d);
      d.remove();
      geaendert = true;
    }
    if (!geaendert) return;
    App.dateienNeu();
    getauscht.forEach(App.dateiEinrichten);
    App.hakenLaden(getauscht);
    ankerHalten(a);
    App.reviewLaden().then(() => ankerHalten(a));
  }, 1000);
  App.neuHolen = diffNeu;
})();
