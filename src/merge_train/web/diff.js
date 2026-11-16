// Diff-Seiten (GitLab-MR und lokales Projekt): Kontext und große Dateien nachladen, Zeile zeigen, Popup mit Code bzw.
// Dateivergleich, Kommentarliste links (sortierbar), Datei abhaken. Braucht von App: waggon, kann, el, aufdecken, melden, dateien, inlineBauen,
// dateiFesthalten, dateiLinks, wagenFuellen; aus review.js (später geladen, daher erst beim Aufruf): review, zeichnen, STAENDE, werZeichen,
// direkt, fadenErledigen, kommentarAktion. Stellt bereit: waggonAbfrage, nurLesen, seitAnsicht, zeileZeigen,
// zeileFinden, popup, sieheAuch, ortLink, dateiLaden, kommentarListe.
(() => {
  const {el, waggon, dateien} = App;
  // Commit-Ansicht (waggon.ansicht = 'commit:<sha>' nur lesen, 'seit:<sha>' rechts = MR-Stand): Server rechnet die
  // Zeilen um
  const waggonAbfrage = mrStand =>
    'mr=' +
    encodeURIComponent(waggon.id) +
    '&k=' +
    waggon.k +
    (waggon.ansicht && !mrStand ? '&ansicht=' + waggon.ansicht : '');
  const mitReview = !!App.kann.review,
    nurLesen = !!waggon.lesen,
    seitAnsicht = (waggon.ansicht || '').startsWith('seit:');
  function neuZeichnen() {
    App.zeichnen?.();
  }
  // ---- Kontext nachladen, Zeile zeigen, Popup
  const projektUrl = (waggon.web_url || '').split('/-/merge_requests/')[0];
  function zeilenHolen(pfad, von, bis, mrStand) {
    return fetch(
      '/api/zeilen?' + waggonAbfrage(mrStand) + '&pfad=' + encodeURIComponent(pfad) + '&von=' + von + '&bis=' + bis
    )
      .then(r => r.json())
      .catch(() => ({ok: false, text: 'merge-train-Server nicht erreichbar'}));
  }
  function trAus(h) {
    const t = document.createElement('tbody');
    t.innerHTML = h;
    return t.firstElementChild;
  }
  function luKnoepfe(tr) {
    const v = +tr.dataset.von,
      b = +tr.dataset.bis,
      n = b - v + 1,
      kn = [el('span', {}, '⋯ ' + n + ' Zeile(n) ausgeblendet')];
    if (n > 30) {
      if (v > 1)
        kn.push(
          el(
            'button',
            {title: '20 Zeilen unter dem sichtbaren Teil darüber', onclick: () => aufklappen(tr, v, v + 19)},
            '▼ 20'
          )
        );
      if (tr.nextElementSibling)
        kn.push(
          el(
            'button',
            {title: '20 Zeilen über dem sichtbaren Teil darunter', onclick: () => aufklappen(tr, b - 19, b)},
            '▲ 20'
          )
        );
    }
    kn.push(el('button', {onclick: () => aufklappen(tr, v, b)}, n > 30 ? 'alle ' + n : 'aufklappen'));
    tr.lastElementChild.replaceChildren(...kn);
  }
  function luTeil(lu, v, b) {
    const t = lu.cloneNode(true);
    t.dataset.von = v;
    t.dataset.bis = b;
    return t;
  }
  function aufklappen(tr, x, y) {
    const d = tr.closest('.datei'),
      v = tr.dataset.von,
      b = tr.dataset.bis,
      delta = +tr.dataset.d;
    x = Math.max(x, +v);
    y = Math.min(y, +b);
    return zeilenHolen(d.dataset.pfad, x, y).then(r => {
      if (!r.ok) {
        App.melden(r.text);
        return false;
      }
      d.querySelectorAll('tr.lu[data-von="' + v + '"][data-bis="' + b + '"]').forEach(lu => {
        const sbs = lu.closest('table').classList.contains('sbs'),
          neu = [];
        if (x > +v) neu.push(luTeil(lu, +v, x - 1));
        r.zeilen.forEach((h, i) => {
          const nb = x + i,
            na = nb + delta;
          neu.push(
            trAus(
              sbs
                ? `<tr class="kx" data-a="${na}" data-b="${nb}"><td class="n">${na}</td><td class="c">${h}</td>` +
                    `<td class="n">${nb}</td><td class="c">${h}</td></tr>`
                : `<tr class="kx" data-a="${na}" data-b="${nb}">` +
                    `<td class="n">${na}</td><td class="n">${nb}</td><td class="c">${h}</td></tr>`
            )
          );
        });
        if (y < +b) neu.push(luTeil(lu, y + 1, +b));
        lu.replaceWith(...neu);
        neu.forEach(t => {
          if (t.classList.contains('lu')) luKnoepfe(t);
        });
      });
      neuZeichnen();
      return true;
    });
  }
  function blinken(e) {
    e.classList.remove('blink');
    void e.offsetWidth;
    e.classList.add('blink');
    e.addEventListener('animationend', () => e.classList.remove('blink'), {once: true});
  }
  function aufblitzen(r) {
    r.scrollIntoView({block: 'center'});
    blinken(r);
  }
  function dateiLaden(d) {
    const p = d.querySelector('.spaet');
    if (!p) return Promise.resolve(true);
    if (p.dataset.laedt) return p.laedt;
    const b = p.querySelector('button');
    if (b) {
      b.disabled = true;
      b.textContent = 'lädt …';
    }
    p.dataset.laedt = 1;
    return (p.laedt = fetch('/api/datei?' + waggonAbfrage() + '&i=' + dateien.indexOf(d))
      .then(r => r.json())
      .then(r => {
        if (!r.ok) {
          App.melden(r.text);
          delete p.dataset.laedt;
          if (b) {
            b.disabled = false;
            b.textContent = 'Diff laden';
          }
          return false;
        }
        const t = document.createElement('div');
        t.innerHTML = r.html;
        p.replaceWith(...t.childNodes);
        d.querySelectorAll('tr.lu').forEach(luKnoepfe);
        if (document.body.classList.contains('inline')) App.inlineBauen(d);
        neuZeichnen();
        return true;
      })
      .catch(() => {
        App.melden('merge-train-Server nicht erreichbar');
        delete p.dataset.laedt;
        return false;
      }));
  }
  document.querySelector('main').addEventListener('click', e => {
    const b = e.target.closest('button.laden');
    if (b) dateiLaden(b.closest('.datei'));
  });
  document.addEventListener('inl', e => {
    e.detail.forEach(t => t.querySelectorAll('tr.lu').forEach(luKnoepfe));
    neuZeichnen();
  });
  function zeileZeigen(x, ohnePopup) {
    // Zeile im Diff zeigen (Kontext/Datei dafür nachladen), sonst Popup. Promise: true = Zeile im Diff
    const z = x.b || x.a,
      sonst = () => {
        if (x.path && !ohnePopup) popup(x.path, z);
        return false;
      };
    if (x.datei != null && dateien[x.datei] && z) {
      const d = dateien[x.datei];
      d.open = true;
      if (d.querySelector('.spaet')) return dateiLaden(d).then(ok => (ok ? zeileZeigen(x, ohnePopup) : sonst()));
      const tab = d.querySelector(document.body.classList.contains('inline') ? 'table.inl' : 'table.sbs'),
        r = tab && zeileFinden(tab, x.a, x.b);
      if (!tab) return Promise.resolve(sonst());
      if (r) {
        aufblitzen(r);
        return Promise.resolve(true);
      }
      const lu = x.b && [...tab.querySelectorAll('tr.lu')].find(t => +t.dataset.von <= x.b && x.b <= +t.dataset.bis);
      if (lu)
        return aufklappen(lu, x.b - 6, x.b + 6).then(ok => {
          const r2 = ok && zeileFinden(tab, x.a, x.b);
          if (r2) aufblitzen(r2);
          return !!r2;
        });
    }
    return Promise.resolve(sonst());
  }
  function sichtbar(sel) {
    return [...document.querySelectorAll(sel)].find(e => e.getClientRects().length);
  }
  function springen(i) {
    // aus der Kommentarliste: zum Kasten (bei Bedarf Kontext/Datei nachladen)
    const hin = () => {
      const b = sichtbar('.kbox[data-id="' + i.id + '"]');
      if (!b) return false;
      const d = b.closest('.datei');
      App.aufdecken(b);
      b.scrollIntoView({block: 'center'});
      App.dateiFesthalten(d ? dateien.indexOf(d) : null);
      blinken(b);
      return true;
    };
    if (hin()) return;
    (i.x.datei != null ? zeileZeigen(i.x, true) : Promise.resolve(false)).then(() => {
      if (!hin()) zeileZeigen(i.x);
    });
  }
  var sortieren = false; // Sortiermodus der Box „GitLab-Kommentare“
  function kommentarListe() {
    // links: GitLab-Kommentare (Entwürfe, Agent-Hinweise) und KI-Threads (privat) getrennt
    const nach = (p, q) => (p.x.datei ?? -1) - (q.x.datei ?? -1) || (p.x.b || p.x.a || 0) - (q.x.b || q.x.a || 0);
    const pos = {};
    // vom Server: Sende-Reihenfolge bei „Review abschließen“
    (App.review.reihenfolge || []).forEach((id, n) => (pos[id] = n));
    kasten(
      'kliste',
      'GitLab-Kommentare',
      [
        ...App.review.kommentare
          .filter(x => x.status !== 'loeschen')
          .map(x => ({art: 'km', id: x.id, x, f: x.finding, st: x.stand})),
        ...App.review.hinweise
          .filter(h => h.status === 'offen')
          .map(h => ({art: 'hw', id: h.key, x: h, f: h.finding, st: h.stand}))
      ].sort((p, q) => (pos[p.id] ?? 1e9) - (pos[q.id] ?? 1e9) || nach(p, q)),
      mitReview && !nurLesen && !waggon.ansicht
    );
    kasten(
      'kliste-gl',
      'GitLab-Diskussionen',
      (App.review.diskussionen || []).map(x => ({art: 'km gl', id: x.id, x, st: x.stand})).sort(nach),
      false
    );
    kasten(
      'kliste-ki',
      'KI-Threads',
      [...(App.review.faeden || []), ...(App.review.zeigFremde ? App.review.faeden_fremd || [] : [])]
        .map(x => ({art: 'km', id: x.id, x, st: x.stand}))
        .sort(nach)
    );
  }
  function reihenfolge(ids) {
    App.review.reihenfolge = ids;
    kommentarListe();
    App.kommentarAktion({aktion: 'reihenfolge', ids});
  }
  function verschieben(id, ziel, unten) {
    const ids = (App.review.reihenfolge || []).filter(x => x !== id); // ziel: id, 'oben' oder 'unten'
    if (ziel === 'oben') ids.unshift(id);
    else if (ziel === 'unten') ids.push(id);
    else {
      const i = ids.indexOf(ziel);
      if (i < 0) return;
      ids.splice(i + (unten ? 1 : 0), 0, id);
    }
    reihenfolge(ids);
  }
  /** Gemeinsame Basis der drei Listen: die Stände, die dort vorkommen können, in Anzeige-Reihenfolge (je ein
   *  Filterknopf, auch bei 0). Bedeutung und Zeichen: App.STAENDE (Konzept: docs/funktionen.md, „Stände der Listen“).
   *  „Entwurf in GitLab“ gibt es nur ohne „direkt veröffentlichen“ (oder wenn noch einer da ist). */
  const LISTEN_STATI = {
    kliste: ['entwurf', 'dran', 'gitlab_entwurf', 'wartet'],
    'kliste-gl': ['entwurf', 'dran', 'gitlab_entwurf', 'wartet', 'erledigt'],
    'kliste-ki': ['entwurf', 'dran', 'wartet', 'erledigt']
  };
  const listenStati = (id, items) =>
    LISTEN_STATI[id].filter(st => st !== 'gitlab_entwurf' || !App.direkt() || items.some(i => i.st === st));
  /** [Zeichen, Klasse, Titel] eines Stands – in der Liste und an den Filterknöpfen gleich. */
  function standZeichen(st) {
    const [zeichen, titel] = App.STAENDE[st] || ['?', st];
    return [zeichen, 'zu s-' + st, titel];
  }
  function ausgeblendet(id, neu) {
    const schl = 'filter:' + id + ':' + waggon.id;
    try {
      if (neu) localStorage[schl] = JSON.stringify(neu);
      return JSON.parse(localStorage[schl] || '[]');
    } catch (_) {
      return neu || [];
    }
  }
  function filterKnoepfe(id, items, aus) {
    return listenStati(id, items).map(st => {
      const [zeichen, klasse, titel] = standZeichen(st);
      return el(
        'button',
        {
          class: aus.includes(st) ? 'aus' : '',
          title: titel + (aus.includes(st) ? ' – ausgeblendet, Klick: zeigen' : ' – Klick: ausblenden'),
          onclick: e => {
            e.preventDefault();
            ausgeblendet(id, aus.includes(st) ? aus.filter(x => x !== st) : [...aus, st]);
            kommentarListe();
          }
        },
        el('span', {class: klasse}, zeichen),
        items.filter(i => i.st === st).length
      );
    });
  }
  /** Eine der drei Listen (id: Schlüssel in LISTEN_STATI) füllen: Titel, Filterknöpfe je Stand (die Zahlen stehen an
   *  den Knöpfen), Einträge; sortierbar: Knopf „⇅“ vor den Filterknöpfen (Sende-Reihenfolge, nur „GitLab-Kommentare“). */
  function kasten(id, name, alle, sortierbar) {
    const k = document.getElementById(id);
    if (!k) return;
    k.hidden = !alle.length;
    const aus = ausgeblendet(id),
      items = alle.filter(i => !aus.includes(i.st)),
      s = sortierbar && sortieren && items.length > 1;
    k.querySelector('summary').replaceChildren(
      name,
      el('span', {class: 'stfilter'}, sortierbar && items.length > 1 ? sortKnopf(k) : '', ...filterKnoepfe(id, alle, aus))
    );
    k.querySelector('div').replaceChildren(
      ...items.map(i => {
        const e = listenEintrag(id, i, s);
        if (s) ziehbarMachen(e, i);
        return e;
      })
    );
  }
  function sortKnopf(k) {
    return el(
      'button',
      {
        class: 'sortknopf' + (sortieren ? ' an' : ''),
        title: sortieren
          ? 'Sortieren beenden'
          : 'Reihenfolge ändern – in dieser Reihenfolge gehen die Kommentare an GitLab',
        onclick: e => {
          e.preventDefault();
          sortieren = !sortieren;
          k.open = true;
          kommentarListe();
        }
      },
      sortieren ? '⇅ fertig' : '⇅'
    );
  }
  const eintragTitel = x =>
    x.title || (x.hinweis && (App.review.hinweise.find(h => h.key === x.hinweis) || {}).title) || null;
  /** Zeile der Liste: wer zuletzt gehandelt hat, Stand (standKnopf), Ort, Text; beim Sortieren Griff und Pfeile. */
  function listenEintrag(id, i, s) {
    const t = String(i.x.text || ((i.x.nachrichten && i.x.nachrichten[0]) || {}).text || '').replace(/\*\*|`/g, ''),
      f = eintragTitel(i.x) || (i.f && t.startsWith(i.f) ? t.slice(i.f.length).trim() : t);
    return el(
      'div',
      {class: 'ke ' + i.art + (s ? ' sort' : ''), title: f, onclick: s ? null : () => springen(i)},
      s ? el('span', {class: 'griff', title: 'ziehen zum Umsortieren'}, '⠿') : null,
      App.werZeichen(i.x.wer),
      standKnopf(id, i),
      i.f ? el('b', {}, i.f) : null,
      el('span', {class: 'kt2'}, f),
      s
        ? el(
            'span',
            {class: 'pfeile'},
            el('button', {title: 'ganz nach oben', onclick: () => verschieben(i.id, 'oben')}, '⤒'),
            el('button', {title: 'ganz nach unten', onclick: () => verschieben(i.id, 'unten')}, '⤓')
          )
        : null
    );
  }
  /** Stand eines Eintrags; Klick, wo App.fadenErledigen es erlaubt (erledigen, GitLab-Diskussion in GitLab). */
  function standKnopf(id, i) {
    const [zeichen, klasse, titel] = standZeichen(i.st),
      klick = id !== 'kliste' && App.fadenErledigen(i.x, true);
    if (!klick) return el('span', {class: klasse + ' fest', title: titel}, zeichen);
    return el(
      'span',
      {
        class: klasse,
        title: titel + ' – Klick: ' + klick,
        onclick: e => {
          e.stopPropagation();
          App.fadenErledigen(i.x);
        }
      },
      zeichen
    );
  }
  /** Drag & Drop in der Liste: oben/unten von der Mitte des Ziels abhängig. */
  function ziehbarMachen(e, i) {
    e.draggable = true;
    const weg = () => e.classList.remove('drop-oben', 'drop-unten');
    e.addEventListener('dragstart', ev => {
      ev.dataTransfer.setData('text/plain', i.id);
      ev.dataTransfer.effectAllowed = 'move';
      e.classList.add('zieht');
    });
    e.addEventListener('dragend', () => e.classList.remove('zieht'));
    e.addEventListener('dragover', ev => {
      ev.preventDefault();
      const r = e.getBoundingClientRect(),
        u = ev.clientY >= r.top + r.height / 2;
      e.classList.toggle('drop-oben', !u);
      e.classList.toggle('drop-unten', u);
    });
    e.addEventListener('dragleave', weg);
    e.addEventListener('drop', ev => {
      ev.preventDefault();
      const von = ev.dataTransfer.getData('text/plain'),
        u = e.classList.contains('drop-unten');
      weg();
      if (von && von !== i.id) verschieben(von, i.id, u);
    });
  }
  const ort = x =>
    x.path ? x.path + (x.b ? ':' + (x.ab ? x.ab + '-' : '') + x.b : x.a ? ':' + x.a + ' (alt)' : '') : 'allgemein';
  function ortLink(x) {
    return x.path
      ? el('a', {class: 'ortlink', title: 'im Code zeigen', onclick: () => zeileZeigen(x)}, ort(x))
      : el('code', {}, ort(x));
  }
  function sieheAuch(sa) {
    if (!sa || !sa.length) return null;
    return el(
      'div',
      {class: 'sa'},
      el('span', {}, 'Siehe auch:'),
      ...sa.map(s => {
        const wo = s.path + (s.zeile ? ':' + s.zeile + (s.bis ? '-' + s.bis : '') : '');
        if (s.problem)
          return el(
            'span',
            {class: 'warn', title: s.problem},
            (s.label ? s.label + ' · ' : '') + wo + ' (' + s.problem + ')'
          );
        const name = s.label || s.path.split('/').pop() + (s.zeile ? ':' + s.zeile + (s.bis ? '-' + s.bis : '') : '');
        // Vergleich: je Seite nur ihr Bereich, wenn einer angegeben ist (B: zeile–bis des Eintrags, A: vzeile–vbis)
        const va = s.vergleich && [s.vergleich, s.vzeile, s.vbis],
          vb = s.vergleich && [s.path, s.bis ? s.zeile : null, s.bis],
          link = s.vergleich
            ? el(
                'a',
                {
                  class: 'vgl',
                  title: 'Vergleich nebeneinander: ' + bereichText(va) + ' ⇄ ' + bereichText(vb),
                  onclick: () => vergleich(va, vb, s.label)
                },
                '⇄ ' + name
              )
            : el('a', {title: wo, onclick: () => popup(s.path, s.zeile, s.label, s.bis)}, name);
        return s.warnung ? el('span', {}, link, el('span', {class: 'warn', title: s.warnung}, ' ⚠')) : link;
      })
    );
  }
  /** [pfad, von, bis] → „pfad“ bzw. „pfad:von-bis“ */
  function bereichText(x) {
    return x[0] + (x[1] ? ':' + x[1] + (x[2] ? '-' + x[2] : '') : '');
  }
  function vergleich(va, vb, label) {
    schliessen(); // see_also mit "diff": zwei Dateien (bzw. Bereiche) des MR-Stands nebeneinander
    const a = va[0],
      b = vb[0],
      kurz = x => bereichText([x[0].split('/').pop(), x[1], x[2]]),
      bereich = (seite, x) =>
        x[1] ? '&' + seite + '_von=' + x[1] + '&' + seite + '_bis=' + (x[2] || x[1]) : '',
      info = el('span', {class: 'sub'}, 'lädt …'),
      pb = el('div', {class: 'pb'}),
      kn = el('span', {class: 'knoepfe'});
    document.body.append(
      el('div', {id: 'schleier', onclick: schliessen}),
      el(
        'div',
        {id: 'popup', class: 'vergleich'},
        el(
          'div',
          {class: 'pk'},
          el('b', {title: bereichText(va) + ' ⇄ ' + bereichText(vb)}, (label ? label + ' – ' : '') + kurz(va) + ' ⇄ ' + kurz(vb)),
          info,
          kn
        ),
        pb
      )
    );
    kn.append(el('button', {title: 'schließen (Esc)', onclick: schliessen}, '✕'));
    fetch(
      '/api/vergleich?' + waggonAbfrage(true) + '&a=' + encodeURIComponent(a) + '&b=' + encodeURIComponent(b) +
        bereich('a', va) + bereich('b', vb)
    )
      .then(r => r.json())
      .catch(() => ({ok: false, text: 'merge-train-Server nicht erreichbar'}))
      .then(r => {
        if (!pb.isConnected) return;
        if (!r.ok) {
          info.textContent = '';
          pb.append(el('div', {class: 'warn'}, r.text));
          return;
        }
        const ka = bereichText([a, ...(r.a || [])]),
          kb = bereichText([b, ...(r.b || [])]);
        pb.append(el('div', {class: 'vkopf'}, el('span', {title: ka}, ka), el('span', {title: kb}, kb)));
        const t = document.createElement('div');
        t.innerHTML = r.html;
        pb.append(...t.childNodes);
        const rows = [...pb.querySelectorAll('tr')],
          anf = rows.filter(
            (tr, i) =>
              tr.querySelector('.weg,.dazu,.nix') && !(rows[i - 1] && rows[i - 1].querySelector('.weg,.dazu,.nix'))
          );
        info.textContent = anf.length
          ? anf.length + ' Unterschied(e) · +' + r.plus + ' −' + r.minus + ' · Stand ' + r.sha.slice(0, 8)
          : 'keine Unterschiede';
        let i = -1;
        const geh = d => {
          if (!anf.length) return;
          i = (i + d + anf.length) % anf.length;
          const z = anf[i];
          pb.scrollTop += z.getBoundingClientRect().top - pb.getBoundingClientRect().top - pb.clientHeight / 3;
          blinken(z);
        };
        if (anf.length)
          kn.prepend(
            el('button', {title: 'voriger Unterschied', onclick: () => geh(-1)}, '↑'),
            el('button', {title: 'nächster Unterschied', onclick: () => geh(1)}, '↓')
          );
        geh(1);
      });
  }
  var geliehen = null; // Datei, die gerade im Popup steht: {d, platz}
  function zurueckgeben() {
    if (!geliehen) return;
    const {d, platz} = geliehen;
    geliehen = null;
    d.querySelectorAll('tr.ziel').forEach(t => t.classList.remove('ziel'));
    platz.replaceWith(d);
  }
  function schliessen() {
    zurueckgeben();
    ['popup', 'schleier'].forEach(i => {
      const e = document.getElementById(i);
      if (e) e.remove();
    });
  }
  function gitlabLink(pfad, zeile, bisZ) {
    if (!projektUrl) return null;
    const href =
      projektUrl +
      '/-/blob/' +
      waggon.sha +
      '/' +
      pfad.split('/').map(encodeURIComponent).join('/') +
      (zeile ? '#L' + zeile + (bisZ ? '-' + bisZ : '') : '');
    return el('a', {class: 'gl-link', target: '_blank', rel: 'noopener', href}, 'GitLab ↗');
  }
  /** Popup mit Code im MR-Stand; liegt die Datei im Diff: deren Diff (aufklappbar). */
  function popup(pfad, zeile, label, bisZ) {
    schliessen();
    const di = dateien.findIndex(d => d.dataset.pfad === pfad),
      p = {
        pfad,
        zeile,
        ende: bisZ || zeile,
        info: el('span', {class: 'sub'}),
        pb: el('div', {class: 'pb'}),
        knoepfe: el('span', {class: 'knoepfe'}),
        gitlab: gitlabLink(pfad, zeile, bisZ),
        zu: el('button', {title: 'schließen (Esc)', onclick: schliessen}, '✕')
      },
      wo = pfad + (zeile ? ':' + zeile + (bisZ ? '-' + bisZ : '') : '');
    document.body.append(
      el('div', {id: 'schleier', onclick: schliessen}),
      el(
        'div',
        {id: 'popup'},
        el('div', {class: 'pk'}, el('b', {}, (label ? label + ' – ' : '') + wo), p.info, p.knoepfe),
        p.pb
      )
    );
    if (di >= 0 && !nurLesen) popupMitDiff(p, di);
    else popupMitCode(p);
  }
  /** Popup: die Datei des Diffs selbst (geliehen, nicht kopiert), Zeilen markiert. */
  function popupMitDiff(p, di) {
    const {pfad, zeile, ende, info, pb} = p,
      d = dateien[di];
    info.textContent = 'Diff im MR';
    p.knoepfe.append(
      el(
        'button',
        {title: 'alle ausgeblendeten Zeilen dieser Datei laden', onclick: () => alleAuf(pb)},
        'alles aufklappen'
      ),
      zeile
        ? el(
            'button',
            {
              onclick: () => {
                schliessen();
                zeileZeigen({datei: di, a: null, b: zeile, path: pfad});
              }
            },
            'im Diff zeigen'
          )
        : '',
      p.gitlab || '',
      p.zu
    );
    dateiLaden(d).then(ok => {
      if (!pb.isConnected) return; // Popup inzwischen zu
      if (!ok) {
        pb.textContent = 'Diff nicht verfügbar';
        return;
      }
      // dieselbe Datei wie auf der Seite (nicht kopiert): Kommentare, Hinweise, Kontext und Klicks gelten hier wie
      // dort
      const platz = el('div', {class: 'leihplatz', style: 'height:' + d.offsetHeight + 'px'});
      d.replaceWith(platz);
      d.open = true;
      pb.append(d);
      geliehen = {d, platz};
      if (!zeile) return;
      const markieren = () => {
        let erst = null;
        d.querySelectorAll('tr[data-b]').forEach(t => {
          const b = +t.dataset.b,
            an = b >= zeile && b <= ende;
          t.classList.toggle('ziel', an);
          if (an && !erst && t.getClientRects().length) erst = t;
        });
        if (erst)
          pb.scrollTop += erst.getBoundingClientRect().top - pb.getBoundingClientRect().top - pb.clientHeight / 2;
        return !!erst;
      };
      if (markieren()) return;
      const lu = [...d.querySelectorAll('tr.lu')].find(t => +t.dataset.von <= ende && zeile <= +t.dataset.bis);
      if (lu) aufklappen(lu, zeile - 12, ende + 12).then(markieren);
    });
  }
  /** Popup: Zeilen um die Stelle aus dem MR-Stand, nach oben/unten oder ganz nachladbar. */
  function popupMitCode(p) {
    const {pfad, zeile, ende, info, pb} = p,
      bereich = {von: Math.max(1, (zeile || 1) - 12), bis: (ende || 1) + 12},
      tb = el('tbody');
    const knopf = (text, titel, aendern, wie) =>
      el(
        'button',
        {
          title: titel,
          onclick: () => {
            aendern();
            lade(wie);
          }
        },
        text
      );
    const hoch = knopf('▲ mehr', null, () => (bereich.von = Math.max(1, bereich.von - 30)), 'oben'),
      runter = knopf('▼ mehr', null, () => (bereich.bis += 30), 'unten'),
      ganz = knopf('ganze Datei', 'ganze Datei laden', () => Object.assign(bereich, {von: 1, bis: 1e6}), 'erst');
    p.knoepfe.append(hoch, runter, ganz, p.gitlab || '', p.zu);
    pb.append(el('table', {}, el('colgroup', {}, el('col', {class: 'cn'}), el('col', {})), tb));
    function lade(wie) {
      const rest = pb.scrollHeight - pb.scrollTop;
      zeilenHolen(pfad, bereich.von, bereich.bis, true).then(r => {
        if (!r.ok) {
          tb.replaceChildren(el('tr', {}, el('td', {}, ''), el('td', {class: 'warn'}, r.text)));
          return;
        }
        Object.assign(bereich, {von: r.von, bis: r.bis});
        tb.replaceChildren(
          ...r.zeilen.map((h, i) => {
            const nr = r.von + i;
            return trAus(
              `<tr${zeile && nr >= zeile && nr <= ende ? ' class="ziel"' : ''}>` +
                `<td class="n">${nr}</td><td class="c">${h}</td></tr>`
            );
          })
        );
        hoch.disabled = bereich.von <= 1;
        runter.disabled = ganz.disabled = bereich.bis >= r.n;
        info.textContent = r.n + ' Zeilen · Stand ' + r.sha.slice(0, 8);
        if (wie === 'erst') {
          const z = tb.querySelector('tr.ziel');
          if (z) pb.scrollTop = z.offsetTop - pb.clientHeight / 2;
        } else if (wie === 'oben') pb.scrollTop = pb.scrollHeight - rest;
      });
    }
    lade('erst');
  }
  function alleAuf(box) {
    const lu = box.querySelector('tr.lu');
    if (!lu) return Promise.resolve(true); // nacheinander, bis keine Lücke mehr da ist
    return aufklappen(lu, +lu.dataset.von, +lu.dataset.bis).then(ok => ok && alleAuf(box));
  }
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.getElementById('popup')) {
      e.preventDefault();
      schliessen();
    }
  });
  document.querySelectorAll('tr.lu').forEach(luKnoepfe);
  function zeileFinden(tab, a, b) {
    for (const r of tab.querySelectorAll('tr[data-a],tr[data-b]')) {
      if (
        b != null
          ? r.dataset.b === String(b)
          : (r.dataset.a === String(a) && r.dataset.b == null) ||
            (tab.classList.contains('sbs') && r.dataset.a === String(a))
      )
        return r;
    }
    return null;
  }

  // ---- Datei abhaken (☐ im Dateikopf, gilt für den ganzen Waggon): klappt zu, füllt den Waggon (api/abgehakt)
  function hakenSetzen(r) {
    if (!r || !r.ok) return r && App.melden(r.text);
    const ab = new Set(r.abgehakt);
    dateien.forEach((d, i) => {
      const c = d.querySelector('summary .haken');
      if (c) c.checked = ab.has(d.dataset.pfad);
      d.classList.toggle('abgehakt', ab.has(d.dataset.pfad));
      App.dateiLinks[i]?.classList.toggle('abgehakt', ab.has(d.dataset.pfad));
    });
    App.wagenFuellen(r.fuellung);
  }
  if (location.protocol.startsWith('http') && !nurLesen) {
    dateien.forEach(d => {
      const c = el('input', {type: 'checkbox', class: 'haken', title: 'Datei abhaken (fertig angesehen): klappt sie zu und füllt den Waggon'});
      c.addEventListener('click', e => e.stopPropagation());
      c.addEventListener('change', () => {
        setTimeout(() => (d.open = !c.checked));
        fetch('/api/abgehakt', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({mr: waggon.id, k: waggon.k, pfad: d.dataset.pfad, an: c.checked})
        })
          .then(r => r.json())
          .then(hakenSetzen)
          .catch(() => App.melden('Haken nicht gespeichert – Server weg?'));
      });
      d.querySelector('summary').prepend(c);
    });
    fetch('/api/abgehakt?' + waggonAbfrage(true))
      .then(r => r.json())
      .then(r => {
        hakenSetzen(r);
        dateien.forEach(d => d.classList.contains('abgehakt') && (d.open = false));
      })
      .catch(() => {});
  }

  Object.assign(App, {
    waggonAbfrage,
    nurLesen,
    seitAnsicht,
    zeileZeigen,
    zeileFinden,
    popup,
    sieheAuch,
    ortLink,
    dateiLaden,
    kommentarListe
  });
})();
