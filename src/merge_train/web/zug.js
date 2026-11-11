// Der Zug im Kopf: ein Waggon je Projekt/MR (Klick wechselt), „fertig ✓“ (lokale Waggons), weiter zum nächsten (n,
// Enter), Abfahrt mit Daumen-Regen, wenn der letzte fertig ist.
// Braucht von App: waggon, melden, lokSvg, anlageZeichnen, kopfhoeheSetzen (nur Diff-Seiten), review (nur Diff-Seiten).
// Stellt bereit: zugSetzen.
(() => {
  const {waggon} = App;
  let zugWagen = (window.MR_ZUG || {wagen: []}).wagen; // die Waggons des Zugs (/zug.js bzw. /api/zug)
  const esc = t =>
    String(t == null ? '' : t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[c]);
  function naechsterWagen() {
    const i = zugWagen.findIndex(w => w.p === waggon.projekt);
    const offen = zugWagen.filter(w => w.status === 'offen' && w.p !== waggon.projekt);
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
        mr = w.quelle && w.quelle !== 'lokal';
      const nm = w.name || w.p,
        name = esc(nm.length > 23 ? nm.slice(0, 22) + '…' : nm),
        ges = Math.max(1, w.plus + w.minus),
        bp = Math.round(((W - 20) * w.plus) / ges);
      const todos = w.todos || [],
        marke = esc(
          w.marke ||
            (f
              ? '✓ fertig'
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
      const klassen = `wg ${akt ? 'akt' : ''} ${f ? 'fertig' : ''} ${mr ? 'mr' : ''}`;
      s += `<g class="${klassen}" data-i="${i}"><title>${titel}</title>
   <rect class="kasten" x="${x}" y="${y}" width="${W}" height="${H}" rx="5"/>
   <text x="${x + 10}" y="${y + 17}" font-weight="600">${name}</text>
   <text x="${x + 10}" y="${y + 35}">${z2}</text>
   <text x="${x + W - 10}" y="${y + 35}" text-anchor="end" class="marke ${f ? 'mf' : 'mo'}">${marke}</text>
   ${balken}
   <circle cx="${x + 24}" cy="${y + H + 4}" r="6" class="rad"/>
   <circle cx="${x + W - 24}" cy="${y + H + 4}" r="6" class="rad"/></g>
   <line x1="${x + W}" y1="${y + H - 8}" x2="${x + W + G}" y2="${y + H - 8}" class="rad"
     stroke="currentColor" stroke-width="2"/>`;
    });
    s += `<g transform="translate(${4 + zugWagen.length * (W + G)},${yr - 70})">${App.lokSvg()}</g>`;
    svg.innerHTML = s;
    box.appendChild(svg);
    svg.querySelectorAll('.wg').forEach(g =>
      g.addEventListener('click', () => {
        const w = zugWagen[+g.dataset.i];
        if (w && w.p !== waggon.projekt && (w.status === 'offen' || (w.quelle && w.quelle !== 'lokal')))
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
  zugZeichnen();
  App.kopfhoeheSetzen?.();
  addEventListener('resize', zugZeichnen);
  /** Neue Waggons (vom Server) zeigen */
  function zugSetzen(wagen) {
    zugWagen = wagen;
    zugZeichnen();
    App.kopfhoeheSetzen?.();
  }
  App.zugSetzen = zugSetzen;
  if (location.hash === '#laden') {
    const z = document.querySelector('.szene');
    if (z) z.classList.add('laedt');
  } // Vorschau: Band läuft dauerhaft
  document
    .querySelectorAll('#bahnhof button[data-l]')
    .forEach(b => b.addEventListener('click', () => location.reload())); // lokal: neue Änderungen
  const fertigKnopf = document.getElementById('fertig');
  const dieserWagen = zugWagen.find(w => w.p === waggon.projekt);
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
    fertigKnopf.addEventListener('click', () => {
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
              ' – trotzdem fertig?'
          )
        ) {
          fertigKnopf.disabled = false;
          App.melden('');
          return;
        }
      }
      if (location.protocol.startsWith('http')) {
        fetch('/fertig', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({mr: waggon.id, projekt: waggon.projekt, sha: waggon.sha, k: waggon.k})
        })
          .then(r => r.json())
          .then(d => {
            if (!d.ok) {
              fertigKnopf.disabled = false;
              App.melden(d.text);
              return;
            }
            zugSetzen(d.wagen);
            fertigKnopf.textContent = '✓ fertig';
            fertigKnopf.classList.add('erledigt');
            weiterZumNaechsten();
            if (!naechsterWagen()) abfahrtFeiern();
          })
          .catch(() => {
            fertigKnopf.disabled = false;
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
