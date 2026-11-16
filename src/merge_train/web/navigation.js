// Diff-Seiten: Dateien des Diffs und ihre Liste – markieren beim Scrollen, Tasten j/k (Datei), i (inline), z (alle
// zu/auf), c (Commits), Inline-Tabellen aus den Tabellen nebeneinander bauen, Filter der Liste (abgehakt, Endungen).
// Braucht von App: el, waggon, zeichnen (review.js, später geladen). Stellt bereit:
// dateien, dateiLinks, kopfhoeheSetzen, inlineBauen, dateiFesthalten, dateienFiltern.
(() => {
  const dateien = [...document.querySelectorAll('.datei')], // die Dateien des Diffs (<details class="datei">)
    dateiLinks = [...document.querySelectorAll('#liste a')], // ihre Links in der Liste links
    kopf = document.getElementById('kopf');
  function kopfHoehe() {
    return kopf.offsetHeight - (parseFloat(getComputedStyle(kopf).getPropertyValue('--himmel')) || 0);
  } // ohne den weggerutschten Himmel
  function kopfhoeheSetzen() {
    document.documentElement.style.setProperty('--kopfh', kopfHoehe() + 'px');
  }
  kopfhoeheSetzen();
  addEventListener('resize', kopfhoeheSetzen);
  document.getElementById('commits').addEventListener('toggle', kopfhoeheSetzen);
  function aktuelleDatei() {
    const g = kopf.getBoundingClientRect().bottom + 20;
    let k = 0;
    dateien.forEach((d, j) => {
      if (!d.closest('#popup') && !d.classList.contains('ausgefiltert') && d.getBoundingClientRect().top <= g) k = j;
    });
    return k;
  }
  let festeDatei = null;
  ['wheel', 'touchmove', 'keydown', 'mousedown'].forEach(t =>
    addEventListener(
      t,
      () => {
        festeDatei = null;
      },
      {passive: true, capture: true}
    )
  );
  const himmel = parseFloat(getComputedStyle(kopf).getPropertyValue('--himmel')) || 0;
  let markiert = null;
  function listeMarkieren() {
    // ganz oben steht der Himmel des Bahnhofs noch über dem Kopf: die Seitenleiste ist um ihn kürzer
    document.documentElement.style.setProperty('--himmel-zu-sehen', Math.max(0, himmel - scrollY) + 'px');
    const k = festeDatei != null && dateien[festeDatei] ? festeDatei : aktuelleDatei();
    if (k === markiert) return; // Liste nur nachziehen, wenn die Datei wechselt: selbst gescrollt bleibt sie stehen
    markiert = k;
    dateiLinks.forEach((a, j) => a.classList.toggle('akt', j === k));
    const a = dateiLinks[k],
      nav = a && a.closest('nav');
    if (nav) {
      const r = a.getBoundingClientRect(),
        p = nav.getBoundingClientRect(),
        h = nav.querySelector('h2'),
        oben = p.top + (h ? h.offsetHeight : 0);
      if (r.top < oben) nav.scrollTop -= oben - r.top + 4;
      else if (r.bottom > p.bottom) nav.scrollTop += r.bottom - p.bottom + 4;
    }
  } // nur die Liste scrollen, nie das Fenster (sonst Rückkopplung mit dem Scroll-Event)
  addEventListener('scroll', listeMarkieren, {passive: true});
  listeMarkieren();
  function zuDatei(k, richtung = 1) {
    if (!dateien.length) return;
    while (dateien[k] && dateien[k].classList.contains('ausgefiltert')) k += richtung; // ausgefilterte überspringen
    if (!dateien[k]) return;
    dateien[k].open = true;
    dateien[k].scrollIntoView({block: 'start'});
  }
  document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.altKey || e.metaKey || /INPUT|TEXTAREA/.test(e.target.tagName)) return;
    const k = aktuelleDatei();
    if (e.key === 'j' || e.key === 'ArrowRight') {
      e.preventDefault();
      zuDatei(dateien[k] && dateien[k].getBoundingClientRect().top > kopfHoehe() + 30 ? k : k + 1);
    } else if (e.key === 'k' || e.key === 'ArrowLeft') {
      e.preventDefault();
      zuDatei(dateien[k] && dateien[k].getBoundingClientRect().top < kopfHoehe() - 5 ? k : k - 1, -1);
    } else if (e.key === 'i') {
      if (!document.body.classList.contains('inline')) inlineBauen();
      document.body.classList.toggle('inline');
      try {
        localStorage.inline = document.body.classList.contains('inline') ? 1 : '';
      } catch (_) {}
      App.zeichnen?.(); // offene Eingabefelder wandern in die sichtbare Tabelle
    } else if (e.key === 'z') {
      const zu = dateien.some(d => d.open);
      dateien.forEach(d => (d.open = !zu));
    } else if (e.key === 'c') {
      const c = document.getElementById('commits');
      c.open = !c.open;
    }
  });
  function inlineBauen(nur) {
    // Inline-Tabelle aus der Tabelle nebeneinander bauen (spart die Hälfte der Seite)
    const neu = [];
    (nur ? [nur] : dateien).forEach(d => {
      const s = d.querySelector('table.sbs');
      if (!s || d.querySelector('table.inl')) return;
      const out = [],
        weg = [],
        dazu = [],
        leeren = () => {
          out.push(...weg, ...dazu);
          weg.length = dazu.length = 0;
        };
      const zeile = (a, b, h, cl, kl) =>
        '<tr' +
        (kl ? ' class="' + kl + '"' : '') +
        (a != null ? ' data-a="' + a + '"' : '') +
        (b != null ? ' data-b="' + b + '"' : '') +
        '><td class="n">' +
        (a == null ? '' : a) +
        '</td><td class="n">' +
        (b == null ? '' : b) +
        '</td><td class="c' +
        (cl ? ' ' + cl : '') +
        '">' +
        h +
        '</td></tr>';
      for (const r of s.rows) {
        const cl = r.classList;
        if (cl.contains('kr')) continue;
        if (cl.contains('hk')) {
          leeren();
          out.push('<tr class="hk"><td></td><td></td><td>' + r.lastElementChild.innerHTML + '</td></tr>');
          continue;
        }
        if (cl.contains('lu')) {
          leeren();
          const x = r.dataset;
          out.push(
            '<tr class="lu" data-von="' +
              x.von +
              '" data-bis="' +
              x.bis +
              '" data-d="' +
              x.d +
              '"><td class="n"></td><td colspan="2"></td></tr>'
          );
          continue;
        }
        const c = r.cells;
        if (c.length < 4) continue;
        const w = c[1].classList.contains('weg'),
          z = c[3].classList.contains('dazu');
        if (!w && !z && !c[1].classList.contains('nix')) {
          leeren();
          out.push(zeile(r.dataset.a, r.dataset.b, c[3].innerHTML, '', r.className));
          continue;
        }
        if (w) weg.push(zeile(r.dataset.a, null, c[1].innerHTML, 'weg'));
        if (z) dazu.push(zeile(null, r.dataset.b, c[3].innerHTML, 'dazu'));
      }
      leeren();
      const t = document.createElement('table');
      t.className = 'inl';
      t.innerHTML = '<colgroup><col class="cn"><col class="cn"><col></colgroup><tbody>' + out.join('') + '</tbody>';
      s.after(t);
      neu.push(t);
    });
    if (neu.length) document.dispatchEvent(new CustomEvent('inl', {detail: neu}));
  }
  try {
    if (localStorage.inline) {
      inlineBauen();
      document.body.classList.add('inline');
    }
  } catch (_) {}

  // ---- Filter der Dateiliste: abgehakte Dateien und Endungen ausblenden (in der Liste und im Diff), je Waggon im
  // Browser gemerkt. Klappmenü „Filter ▾“ im Titel der Liste, je Eintrag ein Häkchen (an = gezeigt).
  const endung = d => {
    const n = d.dataset.pfad.split('/').pop(),
      i = n.lastIndexOf('.');
    return i > 0 ? n.slice(i).toLowerCase() : '(ohne)';
  };
  const FILTER = 'filter:dateien:' + App.waggon.id;
  function dateiFilter(neu) {
    try {
      if (neu) localStorage[FILTER] = JSON.stringify(neu);
      return JSON.parse(localStorage[FILTER] || '[]');
    } catch (_) {
      return neu || [];
    }
  }
  const liste = document.getElementById('liste'),
    titel = liste && liste.querySelector('h2'),
    menue = App.el('div', {class: 'dfilter-menue', hidden: ''}),
    filterKnopf = App.el(
      'button',
      {
        class: 'dfilter',
        title: 'Dateien filtern: abgehakte, Endungen',
        onclick: e => {
          e.stopPropagation();
          menue.hidden = !menue.hidden;
          // fest unter dem Knopf (nicht in der scrollenden Liste), nach links aufgeklappt: bleibt über der Liste, nicht
          // über dem Diff mit seinen klebenden Köpfen
          const r = filterKnopf.getBoundingClientRect();
          menue.style.top = r.bottom + 4 + 'px';
          menue.style.left = Math.max(4, r.right - menue.offsetWidth) + 'px';
        }
      },
      'Filter ▾'
    );
  if (titel) titel.append(filterKnopf, menue);
  document.addEventListener('click', e => {
    if (!menue.hidden && !e.composedPath().includes(menue)) menue.hidden = true; // Häkchen baut das Menü neu: Pfad statt contains
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') menue.hidden = true;
  });
  function filterZeile(schluessel, text, anzahl, aus) {
    const c = App.el('input', {type: 'checkbox', 'data-filter': schluessel});
    c.checked = !aus.includes(schluessel);
    c.addEventListener('change', () => {
      dateiFilter(c.checked ? aus.filter(x => x !== schluessel) : [...aus, schluessel]);
      dateienFiltern();
    });
    return App.el('label', {}, c, ' ' + text, App.el('span', {class: 'sub'}, ' ' + anzahl));
  }
  function dateienFiltern() {
    if (!titel) return;
    const aus = dateiFilter(),
      zahl = {};
    let gezeigt = 0;
    dateien.forEach((d, i) => {
      const e = endung(d),
        weg = aus.includes(e) || (aus.includes('abgehakt') && d.classList.contains('abgehakt'));
      zahl[e] = (zahl[e] || 0) + 1;
      d.classList.toggle('ausgefiltert', weg);
      dateiLinks[i]?.classList.toggle('ausgefiltert', weg);
      if (!weg) gezeigt++;
    });
    // Ordner-Zeilen der Liste ohne gezeigte Datei darunter ausblenden
    let ordner = null;
    [...liste.children].forEach(c => {
      if (c.tagName === 'DIV') {
        ordner = c;
        c.classList.add('ausgefiltert');
      } else if (c.tagName === 'A' && ordner && !c.classList.contains('ausgefiltert')) ordner.classList.remove('ausgefiltert');
    });
    titel.firstChild.textContent =
      'Dateien (' + (gezeigt < dateien.length ? gezeigt + ' von ' + dateien.length : dateien.length) + ')';
    filterKnopf.textContent = aus.length ? 'Filter (' + aus.length + ') ▾' : 'Filter ▾';
    filterKnopf.classList.toggle('an', aus.length > 0);
    const abgehakt = dateien.filter(d => d.classList.contains('abgehakt')).length,
      endungen = Object.keys(zahl).sort((a, b) => zahl[b] - zahl[a] || a.localeCompare(b));
    menue.replaceChildren(
      filterZeile('abgehakt', 'abgehakte', abgehakt, aus),
      App.el('hr'),
      ...endungen.map(e => filterZeile(e, e, zahl[e], aus)),
      aus.length
        ? App.el(
            'button',
            {
              onclick: () => {
                dateiFilter([]);
                dateienFiltern();
              }
            },
            'alle zeigen'
          )
        : null
    );
    markiert = null;
    listeMarkieren();
  }
  dateienFiltern();

  App.dateien = dateien;
  App.dateiLinks = dateiLinks;
  App.kopfhoeheSetzen = kopfhoeheSetzen;
  App.inlineBauen = inlineBauen;
  /** Datei i in der Liste markieren und festhalten, bis der Nutzer selbst scrollt (Sprung aus der Kommentarliste) */
  App.dateienFiltern = dateienFiltern; // nach dem Abhaken (diff.js)
  App.dateiFesthalten = i => {
    festeDatei = i;
    listeMarkieren();
  };
})();
