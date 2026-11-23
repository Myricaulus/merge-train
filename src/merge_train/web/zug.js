// Der Zug im Kopf: ein Waggon je Projekt/MR (Klick wechselt), „fertig ✓“ (lokale Waggons), weiter zum nächsten (n,
// Enter), Abfahrt mit Daumen-Regen, wenn der letzte fertig ist. Lokale Waggons klappen mit „▾“ auf (Waggon-Karte):
// Projektinfos und von/bis des Projekts zur Auswahl (api/projekt). Füllung aus den abgehakten Dateien; ist erst ein
// Teil abgehakt, heißt der Knopf „abgeben“ (Teilstand <von>-wip, zählt wie fertig für die Abfahrt).
// Braucht von App: waggon, el, melden, lokSvg, anlageZeichnen, kopfhoeheSetzen (nur Diff-Seiten), review (nur
// Diff-Seiten), serverWeg, neuHolen. Stellt bereit: zugSetzen, wagenFuellen.
// Kopfhörer auf dem Waggondach: wer an dem Waggon zuhört (api/zuhoerer, alle 5 s) und was er gerade tut.
(() => {
  const {waggon, el} = App;
  let zugWagen = (window.MR_ZUG || {wagen: []}).wagen; // die Waggons des Zugs (/zug.js bzw. /api/zug)
  const esc = t =>
    String(t == null ? '' : t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[c]);
  // Kopfhörer: alle .hoerer[data-tut] (Waggons, HUD) wechselt ein Takt. hoert → meist 🎧, ab und zu Freizeit oder
  // Langeweile (auch mal zwei); arbeitet → wechselnde Arbeits-Emojis, die wackeln
  const LANGEWEILE = ['🥱', '😴', '🙄', '😑', '🫠', '🎮', '🎣', '☕', '🧶', '🎲', '🪀', '🏓', '🎸', '📺', '🍿', '🧩', '🎯',
      '🛹', '🪁', '🏖️', '🃏', '🎨'],
    ARBEIT = ['⚙️', '🔧', '🔨', '🛠️', '💻', '⌨️', '🧠', '📝', '🔩', '⛏️', '🧪', '🔍'],
    HOERER_TITEL = {
      hoert: wer => wer + ' hört nur hier zu und langweilt sich',
      arbeitet: wer => wer + ' ist grad beschäftigt'
    };
  const zufall = n => {
    n = Math.imul(n ^ (n >>> 15), 2246822519);
    n = Math.imul(n ^ (n >>> 13), 3266489917);
    return (n ^ (n >>> 16)) >>> 0;
  };
  function hoererZeichen(tut, versatz) {
    const t = Date.now() / 1000 + versatz;
    if (tut === 'arbeitet') return ARBEIT[zufall(Math.floor(t / 1.2)) % ARBEIT.length];
    const runde = Math.floor(t / 9);
    if (t % 9 > 2.7 || zufall(runde) % 2) return '🎧'; // etwa alle 18 s knapp 3 s lang etwas anderes
    const r = zufall(runde * 7 + 1);
    return LANGEWEILE[r % LANGEWEILE.length] + (r % 4 ? '' : LANGEWEILE[(r >>> 8) % LANGEWEILE.length]);
  }
  function hoererTakt() {
    document.querySelectorAll('.hoerer[data-tut]').forEach(e => {
      const z = hoererZeichen(e.dataset.tut, +e.dataset.versatz || 0);
      if (e.textContent !== z) e.textContent = z;
    });
  }
  setInterval(hoererTakt, 300);
  let hoererStand = {}; // Kennung → {wer, tut}
  const kennung = w => (w.quelle && w.quelle !== 'lokal' ? w.p : 'projekt:' + w.p);
  function hoererSetzen() {
    document.querySelectorAll('#zug .hoerer-g').forEach(g => {
      const w = zugWagen[+g.dataset.i],
        z = w && hoererStand[kennung(w)],
        t = g.querySelector('.hoerer');
      if (z) t.dataset.tut = z.tut;
      else {
        delete t.dataset.tut;
        t.textContent = '';
      }
      g.querySelector('title').textContent = z ? HOERER_TITEL[z.tut](z.wer) : '';
      g.classList.toggle('arbeitet', !!z && z.tut === 'arbeitet');
    });
    hoererTakt();
  }
  function hoererHolen() {
    if (!zugWagen.length || document.hidden) return;
    fetch('/api/zuhoerer?ids=' + encodeURIComponent(zugWagen.map(kennung).join(',')))
      .then(r => r.json())
      .then(d => {
        hoererStand = d;
        hoererSetzen();
      })
      .catch(() => {});
  }
  setInterval(hoererHolen, 5000);
  setTimeout(hoererHolen, 200);
  function naechsterWagen() {
    const i = zugWagen.findIndex(w => w.p === waggon.projekt);
    const offen = zugWagen.filter(w => w.status === 'offen' && !w.abgegeben && w.p !== waggon.projekt);
    return offen.find(w => zugWagen.indexOf(w) > i) || offen[0] || null;
  }
  function zugZeichnen() {
    const box = document.getElementById('zug');
    if (!box) return;
    box.innerHTML = '';
    if (!zugWagen.length) {
      App.anlageZeichnen();
      return;
    } // leer: altes Bild weg (sonst zeigen dessen Waggons ins Leere)
    const W = 170,
      H = 56,
      G = 14,
      y = 22,
      LW = 200,
      yr = y + H + 10,
      ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg'),
      breite = 4 + zugWagen.length * (W + G) + LW + 6;
    svg.setAttribute('width', breite);
    svg.setAttribute('height', yr + 4);
    let s = `<line x1="0" y1="${yr}" x2="${breite}" y2="${yr}" class="schiene"/>`;
    zugWagen.forEach((w, i) => {
      const x = 4 + i * (W + G),
        akt = w.p === waggon.projekt,
        f = w.status === 'fertig',
        mr = w.quelle && w.quelle !== 'lokal',
        fehlt = w.status === 'fehlt',
        nmax = mr ? 23 : 20; // lokal: Platz für „▾“
      const nm = w.name || w.p,
        name = esc(nm.length > nmax ? nm.slice(0, nmax - 1) + '…' : nm),
        ges = Math.max(1, w.plus + w.minus),
        bp = Math.round(((W - 20) * w.plus) / ges);
      const todos = w.todos || [],
        marke = esc(
          w.marke ||
            (f
              ? '✓ fertig'
              : w.abgegeben
                ? '✓ abgegeben'
                : w.gs_neu
                ? '💬 ' + w.gs_neu + ' neu'
                : w.gs
                  ? '💬 ' + w.gs
                  : todos.length
                    ? '● todo ' + todos.length
                    : '● offen')
        );
      const titel = esc(
        w.titel ||
          `${w.p}: +${w.plus} −${w.minus}, ${w.dateien} Datei(en), ${w.commits} Commit(s)` +
            (todos.length ? '\ntodos: ' + todos.join(', ') : '')
      );
      const zmax = Math.max(6, 24 - marke.length);
      const z2 =
        w.zeile2 != null
          ? `<tspan class="klein">${esc(w.zeile2.length > zmax ? w.zeile2.slice(0, zmax - 1) + '…' : w.zeile2)}</tspan>`
          : `<tspan class="tp">+${w.plus}</tspan> <tspan class="tm">−${w.minus}</tspan> ` +
            `<tspan class="klein">${w.dateien} Dat.</tspan>`;
      const balken =
        w.plus + w.minus > 0
          ? `<rect x="${x + 10}" y="${y + 43}" width="${bp}" height="4" class="tp"/>` +
            `<rect x="${x + 10 + bp}" y="${y + 43}" width="${W - 20 - bp}" height="4" class="tm"/>`
          : '';
      const klassen =
        `wg ${akt ? 'akt' : ''} ${f ? 'fertig' : ''} ${w.abgegeben ? 'abgegeben' : ''} ${mr ? 'mr' : ''} ` +
        (fehlt ? 'fehlt' : '');
      const auf = mr
        ? ''
        : `<g class="auf"><rect x="${x + W - 26}" y="${y + 2}" width="24" height="22" rx="4"/>` +
          `<text x="${x + W - 14}" y="${y + 18}" text-anchor="middle">▾</text></g>`;
      const fa = w.fuellung && !f ? Math.min(1, w.fuellung.anteil) : 0, // Füllung aus den abgehakten Dateien
        fh = fa ? Math.max(2, Math.round((H - 3) * fa)) : 0,
        fuell = fh
          ? `<rect class="fuell" x="${x + 1.5}" y="${y + H - 1.5 - fh}" width="${W - 3}" height="${fh}" rx="3.5"/>`
          : '';
      s += `<g class="${klassen}" data-i="${i}"><title>${titel}${
        fa ? esc(`\nabgehakt: ${w.fuellung.fertig} von ${w.fuellung.dateien} Dateien (${Math.round(fa * 100)} %)`) : ''
      }</title>
   <rect class="kasten" x="${x}" y="${y}" width="${W}" height="${H}" rx="5"/>${fuell}
   <text x="${x + 10}" y="${y + 17}" font-weight="600">${name}</text>
   <text x="${x + 10}" y="${y + 35}">${z2}</text>
   <text x="${x + W - 10}" y="${y + 35}" text-anchor="end" class="marke ${f || w.abgegeben ? 'mf' : 'mo'}">${marke}</text>
   ${balken}${auf}
   <g class="hoerer-g" data-i="${i}"><title></title><text class="hoerer" data-versatz="${(i * 3.7) % 9}"
     x="${x + W - 16}" y="${y - 5}" text-anchor="middle"></text></g>
   <circle cx="${x + 24}" cy="${y + H + 4}" r="6" class="rad"/>
   <circle cx="${x + W - 24}" cy="${y + H + 4}" r="6" class="rad"/></g>
   <line x1="${x + W}" y1="${y + H - 8}" x2="${x + W + G}" y2="${y + H - 8}" class="rad"
     stroke="currentColor" stroke-width="2"/>`;
    });
    s += `<g transform="translate(${4 + zugWagen.length * (W + G)},${yr - 70})">${App.lokSvg()}</g>`;
    svg.innerHTML = s;
    box.appendChild(svg);
    hoererSetzen();
    svg.querySelectorAll('.wg').forEach(g =>
      g.addEventListener('click', e => {
        const w = zugWagen[+g.dataset.i];
        if (!w) return;
        if (e.target.closest('.auf') || w.status === 'fehlt') return w.quelle && w.quelle !== 'lokal' ? undefined : karteOeffnen(w, g); // Karte nur lokal
        if (w.p !== waggon.projekt && (w.status === 'offen' || (w.quelle && w.quelle !== 'lokal')))
          location.href = w.datei;
      })
    ); // MRs auch nach dem Abschließen anklickbar
    const cx = App.anlageZeichnen(),
      a = svg.querySelector('.akt') || [...svg.querySelectorAll('.wg')].pop();
    if (cx != null) {
      svg.style.marginLeft = cx + 'px';
      svg.style.marginRight = box.clientWidth - cx + 'px';
    }
    if (a) {
      const x = +a.querySelector('.kasten').getAttribute('x');
      box.scrollLeft = Math.max(0, x + W / 2 - (cx != null ? 0 : box.clientWidth / 2));
    }
  }
  // Waggon-Karte (aufgeklappter lokaler Waggon): Projektinfos, von/bis wählen (gespeichert in der Akte des Projekts),
  // „↺ Standard“ = wie in der Einstellung
  let karte = null;
  function karteZu() {
    if (karte) karte.remove();
    karte = null;
  }
  addEventListener('keydown', e => e.key === 'Escape' && karteZu());
  document.addEventListener('mousedown', e => {
    if (karte && !karte.contains(e.target) && !e.target.closest('#zug .auf')) karteZu();
  });
  function zweigWahl(name, wert, d, mitArbeitsstand) {
    const opt = (v, t) => el('option', {value: v, selected: v === wert ? '' : null}, t || v);
    const gruppe = (t, liste) => (liste.length ? el('optgroup', {label: t}, ...liste.map(b => opt(b))) : null);
    const bekannt = [...d.lokal, ...d.remote, d.arbeitsstand].includes(wert);
    return el(
      'label',
      {},
      name + ' ',
      el(
        'select',
        {name},
        bekannt ? null : opt(wert, wert + ' (fehlt)'),
        mitArbeitsstand ? opt(d.arbeitsstand, 'arbeitsstand (Arbeitsverzeichnis, auch nicht Committetes)') : null,
        gruppe('lokal', d.lokal),
        gruppe('remote', d.remote)
      )
    );
  }
  function karteOeffnen(w, g) {
    const offen = karte && karte.dataset.p === w.p;
    karteZu();
    if (offen) return;
    karte = el('div', {id: 'wagenkarte', 'data-p': w.p}, el('div', {class: 'sub'}, w.p + ' …'));
    document.body.append(karte);
    const r = g.querySelector('.kasten').getBoundingClientRect();
    karte.style.top = r.bottom + 14 + 'px';
    karte.style.left = Math.max(8, Math.min(r.left, innerWidth - karte.offsetWidth - 8)) + 'px';
    const k = karte;
    fetch('/api/projekt?p=' + encodeURIComponent(w.p) + '&k=' + encodeURIComponent(waggon.k || ''))
      .then(r => r.json())
      .then(d => {
        if (karte !== k) return;
        if (d.ok === false || d.text) {
          k.replaceChildren(el('div', {class: 'warn'}, d.text || 'Projekt nicht gefunden'));
          return;
        }
        const std = d.standard,
          vonWahl = zweigWahl('von', d.von, d, false),
          bisWahl = zweigWahl('bis', d.bis, d, true);
        const senden = (von, bis) =>
          fetch('/api/projekt', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({p: d.p, von, bis, akt: waggon.id, k: waggon.k})
          })
            .then(r => r.json())
            .then(e => {
              App.melden(e.text);
              if (!e.ok) return;
              karteZu();
              if (d.p === waggon.projekt) App.neuHolen(e.text);
              else zugSetzen(e.wagen || zugWagen);
            })
            .catch(() => App.melden(App.serverWeg));
        const l = d.letzter;
        k.replaceChildren(
          el('button', {class: 'zu', title: 'zuklappen (Esc)', onclick: karteZu}, '✕'),
          el('div', {class: 'kopf'}, el('b', {}, d.p), ' ', el('span', {class: 'sub'}, d.ordner)),
          d.origin ? el('div', {class: 'sub'}, 'origin ' + d.origin) : null,
          el('div', {}, 'ausgecheckt: ', el('code', {}, d.ausgecheckt)),
          l
            ? el(
                'div',
                {class: 'sub'},
                `letzter Commit ${d.bis === d.arbeitsstand ? '(HEAD)' : 'von ' + d.bis}: ${l.sha} · ${l.zeit} · ${l.betreff}`
              )
            : null,
          d.fehlt.length
            ? el('div', {class: 'warn'}, '⚠ fehlt im Klon: ' + d.fehlt.join(', '))
            : d.ohne_basis
              ? el('div', {class: 'warn'}, `⚠ ${d.bis} und ${d.von} haben keinen gemeinsamen Vorgänger (Rebase?)`)
              : el(
                'div',
                {},
                el('span', {class: 'p'}, '+' + d.plus),
                ' ',
                el('span', {class: 'm'}, '−' + d.minus),
                ` · ${d.dateien} Datei(en) · ${d.commits} Commit(s)`
              ),
          el('div', {class: 'wahl'}, bisWahl, ' → ', vonWahl),
          el(
            'div',
            {class: 'knoepfe'},
            el(
              'button',
              {
                onclick: () => senden(vonWahl.querySelector('select').value, bisWahl.querySelector('select').value)
              },
              'übernehmen'
            ),
            el(
              'button',
              {
                disabled: d.gewaehlt ? null : '',
                title: 'wie in der Einstellung: ' + std.bis + ' → ' + std.von,
                onclick: () => senden('', '')
              },
              '↺ Standard'
            )
          ),
          el(
            'div',
            {class: 'sub'},
            (d.gewaehlt ? 'auf der Seite gewählt · ' : 'aus der Einstellung · ') +
              (d.fertig ? '„fertig ✓“ setzt ' + d.von : '„fertig ✓“ nur mit lokalen Branches (nicht origin/…, arbeitsstand)')
          )
        );
        k.style.left = Math.max(8, Math.min(r.left, innerWidth - k.offsetWidth - 8)) + 'px';
      })
      .catch(() => App.melden(App.serverWeg));
  }
  zugZeichnen();
  App.kopfhoeheSetzen?.();
  addEventListener('resize', () => {
    karteZu();
    zugZeichnen();
  });
  /** Neue Waggons (vom Server) zeigen */
  function zugSetzen(wagen) {
    zugWagen = wagen;
    zugZeichnen();
    App.kopfhoeheSetzen?.();
  }
  App.zugSetzen = zugSetzen;
  /** Füllung des eigenen Waggons nach dem Abhaken (ohne den Zug neu zu laden). */
  App.wagenFuellen = fuellung => {
    const w = zugWagen.find(w => w.p === waggon.projekt);
    if (!w || JSON.stringify(w.fuellung) === JSON.stringify(fuellung)) return;
    w.fuellung = fuellung;
    zugZeichnen();
    knopfAnpassen();
  };
  if (location.hash === '#laden') {
    const z = document.querySelector('.szene');
    if (z) z.classList.add('laedt');
  } // Vorschau: Band läuft dauerhaft
  document
    .querySelectorAll('#bahnhof button[data-l]')
    .forEach(b => b.addEventListener('click', () => App.neuHolen())); // lokal: neue Änderungen
  const fertigKnopf = document.getElementById('fertig');
  const dieserWagen = zugWagen.find(w => w.p === waggon.projekt);
  /** Teil abgehakt → „abgeben“ (nur die abgehakten Dateien), sonst „fertig ✓“. */
  function teilAbgabe() {
    const w = zugWagen.find(w => w.p === waggon.projekt),
      fu = w && w.fuellung;
    return !!(fu && fu.fertig > 0 && fu.fertig < fu.dateien);
  }
  function knopfAnpassen() {
    if (!fertigKnopf || fertigKnopf.classList.contains('erledigt')) return;
    const teil = teilAbgabe();
    fertigKnopf.textContent = teil ? 'abgeben ⇢' : 'fertig ✓';
    if (!fertigKnopf.dataset.titel) fertigKnopf.dataset.titel = fertigKnopf.title;
    fertigKnopf.title = teil
      ? 'Die abgehakten Dateien als Teilstand abgeben (<von>-wip), der Rest bleibt offen'
      : fertigKnopf.dataset.titel;
  }
  function abfahrtFeiern() {
    // letzter Waggon fertig: Zug fährt ab, Daumen-Regen, großer Daumen
    const box = document.getElementById('zug'),
      svg = box && box.querySelector('svg');
    if (svg) {
      box.style.overflow = 'hidden';
      const w = svg.getBoundingClientRect().width;
      svg.animate([{transform: 'translateX(0)'}, {transform: `translateX(${innerWidth + w}px)`}], {
        duration: 2200,
        easing: 'cubic-bezier(.55,0,.85,.5)',
        fill: 'forwards'
      });
    }
    const o = document.createElement('div');
    o.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:99;overflow:hidden';
    document.body.appendChild(o);
    const W = innerWidth,
      H = innerHeight,
      zf = Math.random;
    for (let i = 0; i < 110; i++) {
      const e = document.createElement('span');
      e.textContent = '👍';
      e.style.cssText =
        `position:absolute;left:0;top:0;font-size:${16 + zf() * 30}px;line-height:1;will-change:transform`;
      o.appendChild(e);
      const seite = i % 4,
        x0 = seite === 1 ? W + 60 : seite === 3 ? -60 : zf() * W,
        y0 = seite === 0 ? -60 : seite === 2 ? H + 60 : zf() * H;
      const x1 = W - x0 + (zf() - 0.5) * W * 0.7,
        y1 = H - y0 + (zf() - 0.5) * H * 0.7;
      e.animate(
        [
          {transform: `translate(${x0}px,${y0}px) rotate(0deg)`},
          {transform: `translate(${x1}px,${y1}px) rotate(${(zf() - 0.5) * 1080}deg)`}
        ],
        {duration: 1000 + zf() * 700, delay: zf() * 1300, fill: 'both'}
      );
    }
    const b = document.createElement('div');
    b.textContent = '👍';
    b.style.cssText = 'position:absolute;left:50%;top:50%;font-size:80vmin;line-height:1;will-change:transform,filter';
    o.appendChild(b);
    const t = (sk, r) => `translate(-50%,-50%) scale(${sk}) rotate(${r}deg)`,
      glanz = (px, a) => `drop-shadow(0 0 ${px}px rgba(255,200,40,${a}))`;
    b.animate(
      [
        {transform: t(0.02, -1440), filter: glanz(0, 0), opacity: 1, easing: 'cubic-bezier(.2,.6,.3,1)'},
        {transform: t(1, 0), filter: glanz(0, 0), opacity: 1, offset: 0.62, easing: 'ease-out'},
        {transform: t(1.14, 0), filter: glanz(60, 0.95), opacity: 1, offset: 0.74, easing: 'ease-in-out'},
        {transform: t(1, 0), filter: glanz(20, 0.4), opacity: 1, offset: 0.86, easing: 'ease-in'},
        {transform: t(1, 0), filter: glanz(0, 0), opacity: 0}
      ],
      {duration: 3400, fill: 'forwards'}
    ).onfinish = () => o.remove();
  }
  if (location.hash === '#feier') setTimeout(abfahrtFeiern, 300); // Vorschau: Seite mit #feier aufrufen
  function weiterZumNaechsten() {
    const n = naechsterWagen();
    if (n) {
      App.melden('→ weiter zu ' + n.p);
      setTimeout(() => (location.href = n.datei), 600);
    } else App.melden('Alles durch – kein offener Waggon mehr 🎉');
  }
  if (fertigKnopf) {
    // „fertig ✓“ gibt es nur bei Waggons, deren Quelle das kann (lokal)
    if (dieserWagen && dieserWagen.status === 'fertig') {
      fertigKnopf.textContent = '✓ fertig';
      fertigKnopf.classList.add('erledigt');
      fertigKnopf.disabled = true;
      weiterZumNaechsten();
    } else if (!waggon.dateien) {
      fertigKnopf.style.display = 'none';
    }
    knopfAnpassen();
    fertigKnopf.addEventListener('click', () => {
      const teil = teilAbgabe();
      fertigKnopf.disabled = true;
      App.melden('wird übernommen …');
      const review = App.review; // offene Gespräche und ungesendete Fragen: erst nachfragen
      if (review) {
        const o = (review.faeden || []).filter(k => k.status === 'wartet' || k.status === 'antwort').length,
          e = review.g_ausstehend || 0;
        if (
          (o || e) &&
          !confirm(
            (o ? o + ' Gespräch(e) noch offen' : '') +
              (o && e ? ', ' : '') +
              (e ? e + (e > 1 ? ' Entwürfe' : ' Entwurf') + ' nicht gesendet' : '') +
              (teil ? ' – trotzdem abgeben?' : ' – trotzdem fertig?')
          )
        ) {
          fertigKnopf.disabled = false;
          App.melden('');
          return;
        }
      }
      if (location.protocol.startsWith('http')) {
        // „fertig“ setzt von per git push . – ein pre-push-Hook des Repos (merge-train selbst: ./testen) kann dauern
        const warten = teil
          ? 0
          : setTimeout(() => {
              fertigKnopf.textContent = '⏳ prüft …';
              App.melden('fertig: git push . – der pre-push-Hook des Repos läuft (merge-train: Tests, bis ~20 s) …');
            }, 1500);
        fetch('/fertig', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({mr: waggon.id, projekt: waggon.projekt, sha: waggon.sha, seite: waggon.seite, k: waggon.k, teil})
        })
          .then(r => r.json())
          .then(d => {
            clearTimeout(warten);
            if (!d.ok) {
              fertigKnopf.disabled = false;
              knopfAnpassen();
              App.melden(d.text);
              return;
            }
            zugSetzen(d.wagen);
            const rest = d.wagen.find(w => w.p === waggon.projekt && w.abgegeben);
            if (rest) {
              // Teilabgabe: weiter zum nächsten Waggon, sonst fährt der Zug ab und die Seite zeigt den Rest
              fertigKnopf.textContent = '✓ abgegeben';
              fertigKnopf.classList.add('erledigt');
              App.melden(d.text);
              if (naechsterWagen()) weiterZumNaechsten();
              else {
                abfahrtFeiern();
                setTimeout(() => App.neuHolen(), 3600);
              }
              return;
            }
            fertigKnopf.textContent = '✓ fertig';
            fertigKnopf.classList.add('erledigt');
            weiterZumNaechsten();
            if (!naechsterWagen()) abfahrtFeiern();
          })
          .catch(() => {
            clearTimeout(warten);
            fertigKnopf.disabled = false;
            knopfAnpassen();
            App.melden('merge-train-Server nicht erreichbar – merge-train erneut aufrufen');
          });
        return;
      }
      fertigKnopf.disabled = false;
      App.melden('Seite bitte über merge-train öffnen, dann klappt „fertig“.');
    });
  }
  document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey || /INPUT|TEXTAREA|BUTTON/.test(e.target.tagName)) return;
    if (e.key === 'n') {
      const n = naechsterWagen();
      if (n) location.href = n.datei;
    } else if (e.key === 'Enter' && fertigKnopf && !fertigKnopf.disabled && fertigKnopf.style.display !== 'none') {
      e.preventDefault();
      fertigKnopf.click();
    }
  });
})();
