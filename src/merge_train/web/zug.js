let ZUG = (window.MR_ZUG || {wagen: []}).wagen;
const KANN = MR.kann || {},
  esc = t =>
    String(t == null ? '' : t).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[c]);
function naechster() {
  const i = ZUG.findIndex(w => w.p === MR.projekt);
  const offen = ZUG.filter(w => w.status === 'offen' && w.p !== MR.projekt);
  return offen.find(w => ZUG.indexOf(w) > i) || offen[0] || null;
}
function lok() {
  // bayerische S 3/6 (Vorbild 3673), Fahrtrichtung rechts; lokale Schiene bei y=70
  const gr = '#2f6b45',
    dk = '#1d4630',
    sw = '#1b1b1b',
    ms = '#d8cfa4';
  const rad = (cx, cy, r) => {
    let t = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${gr}" stroke="#e9e4cf" stroke-width="1.4"/>`;
    for (let k = 0; k < 8; k++) {
      const w = (k * Math.PI) / 4;
      t += `<line x1="${cx}" y1="${cy}" x2="${(cx + Math.cos(w) * (r - 1.5)).toFixed(1)}" y2="${(cy + Math.sin(w) * (r - 1.5)).toFixed(1)}" stroke="#e9e4cf" stroke-width=".7"/>`;
    }
    return t + `<circle cx="${cx}" cy="${cy}" r="2.2" fill="${ms}"/>`;
  };
  return `<g class="dampf"><circle cx="150" cy="2" r="4"/><circle cx="138" cy="-3" r="5.5"/><circle cx="123" cy="-6" r="7"/></g>
 <rect x="0" y="27" width="50" height="29" rx="2" fill="${gr}" stroke="${dk}"/><rect x="2" y="21" width="46" height="7" rx="2" fill="${sw}"/>
 <line x1="6" y1="33" x2="44" y2="33" stroke="${ms}" stroke-width=".8"/><line x1="6" y1="51" x2="44" y2="51" stroke="${ms}" stroke-width=".8"/>
 <rect x="50" y="49" width="6" height="3" fill="${sw}"/>
 <rect x="53" y="10" width="30" height="5" rx="2" fill="${dk}"/><rect x="55" y="14" width="26" height="42" fill="${gr}" stroke="${dk}"/>
 <rect x="60" y="19" width="13" height="12" rx="2" fill="#bcd3df" stroke="${sw}" stroke-width=".8"/>
 <rect x="80" y="21" width="92" height="25" rx="12" fill="${gr}" stroke="${dk}"/>
 <rect x="80" y="38" width="22" height="18" fill="${gr}" stroke="${dk}"/>
 <line x1="102" y1="22" x2="102" y2="45" stroke="${ms}"/><line x1="127" y1="22" x2="127" y2="45" stroke="${ms}"/><line x1="152" y1="22" x2="152" y2="45" stroke="${ms}"/>
 <rect x="111" y="14" width="13" height="9" rx="4" fill="${gr}" stroke="${dk}"/><rect x="135" y="15" width="11" height="8" rx="4" fill="${gr}" stroke="${dk}"/>
 <rect x="157" y="9" width="9" height="13" fill="${gr}" stroke="${dk}"/><rect x="155" y="6" width="13" height="4" rx="1" fill="${sw}"/>
 <rect x="168" y="22" width="11" height="24" fill="${sw}"/><polygon points="179,22 192,34 179,46" fill="${sw}"/>
 <circle cx="186" cy="20" r="2.5" fill="${ms}"/><rect x="184" y="21" width="4" height="5" fill="${sw}"/>
 <line x1="78" y1="48" x2="190" y2="48" stroke="${sw}" stroke-width="3"/>
 <rect x="186" y="49" width="6" height="8" fill="#7a1e1e"/><rect x="192" y="51" width="6" height="3" fill="${sw}"/><rect x="192" y="55" width="6" height="0" fill="${sw}"/>
 ${rad(12, 64, 6)}${rad(38, 64, 6)}${rad(88, 63, 7)}${rad(106, 59, 11)}${rad(130, 59, 11)}${rad(154, 59, 11)}${rad(174, 64, 6)}${rad(188, 64, 6)}
 <line x1="106" y1="62" x2="154" y2="62" stroke="#c9c9c9" stroke-width="2.2" stroke-linecap="round"/>
 <line x1="154" y1="62" x2="170" y2="52" stroke="#c9c9c9" stroke-width="1.8"/>`;
}
function zug() {
  const box = document.getElementById('zug');
  if (!box) return;
  box.innerHTML = '';
  if (!ZUG.length) {
    anlage();
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
    breite = 4 + ZUG.length * (W + G) + LW + 6;
  svg.setAttribute('width', breite);
  svg.setAttribute('height', yr + 4);
  let s = `<line x1="0" y1="${yr}" x2="${breite}" y2="${yr}" class="schiene"/>`;
  ZUG.forEach((w, i) => {
    const x = 4 + i * (W + G),
      akt = w.p === MR.projekt,
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
        `${w.p}: +${w.plus} −${w.minus}, ${w.dateien} Datei(en), ${w.commits} Commit(s)${todos.length ? '\ntodos: ' + todos.join(', ') : ''}`
    );
    const zmax = Math.max(6, 24 - marke.length);
    const z2 =
      w.zeile2 != null
        ? `<tspan class="klein">${esc(w.zeile2.length > zmax ? w.zeile2.slice(0, zmax - 1) + '…' : w.zeile2)}</tspan>`
        : `<tspan class="tp">+${w.plus}</tspan> <tspan class="tm">−${w.minus}</tspan> <tspan class="klein">${w.dateien} Dat.</tspan>`;
    const balken =
      w.plus + w.minus > 0
        ? `<rect x="${x + 10}" y="${y + 43}" width="${bp}" height="4" class="tp"/><rect x="${x + 10 + bp}" y="${y + 43}" width="${W - 20 - bp}" height="4" class="tm"/>`
        : '';
    s += `<g class="wg ${akt ? 'akt' : ''} ${f ? 'fertig' : ''} ${mr ? 'mr' : ''}" data-i="${i}"><title>${titel}</title>
   <rect class="kasten" x="${x}" y="${y}" width="${W}" height="${H}" rx="5"/>
   <text x="${x + 10}" y="${y + 17}" font-weight="600">${name}</text>
   <text x="${x + 10}" y="${y + 35}">${z2}</text>
   <text x="${x + W - 10}" y="${y + 35}" text-anchor="end" class="marke ${f ? 'mf' : 'mo'}">${marke}</text>
   ${balken}
   <circle cx="${x + 24}" cy="${y + H + 4}" r="6" class="rad"/><circle cx="${x + W - 24}" cy="${y + H + 4}" r="6" class="rad"/></g>
   <line x1="${x + W}" y1="${y + H - 8}" x2="${x + W + G}" y2="${y + H - 8}" class="rad" stroke="currentColor" stroke-width="2"/>`;
  });
  s += `<g transform="translate(${4 + ZUG.length * (W + G)},${yr - 70})">${lok()}</g>`;
  svg.innerHTML = s;
  box.appendChild(svg);
  svg.querySelectorAll('.wg').forEach(g =>
    g.addEventListener('click', () => {
      const w = ZUG[+g.dataset.i];
      if (w && w.p !== MR.projekt && (w.status === 'offen' || (w.quelle && w.quelle !== 'lokal')))
        location.href = w.datei;
    })
  ); // MRs auch nach dem Abschließen anklickbar
  const cx = anlage(),
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
function anlage() {
  // Verladegebäude links, Förderband bis zur Mitte über dem vordersten Wagen, Gleis; liefert die Bandmitte
  const sv = document.getElementById('anlage');
  if (!sv) return null;
  const B = sv.clientWidth,
    H = sv.clientHeight,
    gl = H - 4,
    cx = Math.round(Math.max(B / 2, 330)),
    r = n => n.toFixed(1);
  let s = `<rect x="0" y="${gl - 4}" width="${B}" height="8" class="bh-schotter"/>`;
  for (let x = 3; x < B; x += 11) s += `<rect x="${x}" y="${gl - 1}" width="7" height="3" class="bh-schwelle"/>`;
  // Gebäude: Bandturm, Halle mit Leitstand (Knöpfe als HTML darüber), Schild, Tor fürs Gleis
  s += `<rect x="112" y="30" width="66" height="50" class="bh-turm"/><rect x="108" y="25" width="74" height="6" class="bh-dach"/>
  <rect x="120" y="38" width="12" height="13" class="bh-fenster"/><rect x="139" y="38" width="12" height="13" class="bh-fenster"/><rect x="158" y="38" width="12" height="13" class="bh-fenster"/>
  <rect x="118" y="58" width="54" height="13" rx="1.5" class="bh-schild"/><text x="145" y="67.5" text-anchor="middle" class="bh-schrift">MERGE-TRAIN</text>
  <rect x="6" y="84" width="172" height="${gl - 84}" class="bh-wand"/>`;
  for (let x = 10; x < 178; x += 5) s += `<line x1="${x}" y1="144" x2="${x}" y2="${gl}" class="bh-welle"/>`;
  s += `<rect x="2" y="78" width="180" height="7" class="bh-dach"/><rect x="12" y="93" width="160" height="46" rx="2" class="bh-glas"/>`;
  for (let x = 52; x < 172; x += 40) s += `<line x1="${x}" y1="94" x2="${x}" y2="138" class="bh-sprosse"/>`;
  s += `<rect x="6" y="139" width="172" height="5" class="bh-dach"/>
  <path d="M28,${gl} V166 Q92,154 156,166 V${gl} Z" class="bh-tor"/><path d="M28,166 Q92,154 156,166" class="bh-torrand"/>
  <rect x="172" y="143" width="10" height="16" class="bh-tor"/>`;
  // Band: aus der Halle schräg hinauf bis zur Mitte, Fachwerkbrücke, Stützen bis zum Boden, Bandkopf mit Schurre über dem Wagen
  const x0 = 180,
    y0 = 150,
    x1 = cx,
    y1 = 106,
    dy = (y1 - y0) / (x1 - x0),
    y = x => y0 + (x - x0) * dy,
    T = 10;
  let fw = `M${x0},${y0}`;
  for (let x = x0, k = 0; x < x1; x += 16, k++) {
    const xn = Math.min(x + 16, x1);
    fw += ` L${r(xn)},${r(y(xn) + (k % 2 ? 0 : T))}`;
  }
  for (let x = x0 + 110; x < x1 - 60; x += 160) {
    const yb = y(x) + T;
    s += `<path d="M${r(x - 12)},${gl - 4} L${r(x - 3)},${r(yb)} M${r(x + 12)},${gl - 4} L${r(x + 3)},${r(yb)} M${r(x - 9)},${r(gl - 4 - (gl - yb) * 0.3)} H${r(x + 9)} M${r(x - 6)},${r(gl - 4 - (gl - yb) * 0.65)} H${r(x + 6)}" class="bh-stuetze"/>`;
  }
  s += `<path d="M${x1 - 14},${gl - 4} L${x1 - 8},${y1 + T} M${x1 + 14},${gl - 4} L${x1 + 8},${y1 + T} M${x1 - 12},${gl - 40} H${x1 + 12} M${x1 - 10},${gl - 70} H${x1 + 10}" class="bh-stuetze"/>
  <g class="bh-band"><line x1="${x0}" y1="${y0 + T}" x2="${x1}" y2="${y1 + T}" class="bh-fachwerk"/><path d="${fw}" class="bh-fachwerk"/>
  <line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" class="bh-gurt"/>
  <line x1="${x0 + 3}" y1="${r(y(x0 + 3) - 3.5)}" x2="${x1 - 5}" y2="${r(y(x1 - 5) - 3.5)}" class="bh-gut"/>
  <circle cx="${x1}" cy="${y1}" r="5" class="bh-trommel"/></g>
  <polygon points="${x1 - 2},${y1 + 3} ${x1 + 12},${y1 + 3} ${x1 + 7},${y1 + 24} ${x1 + 1},${y1 + 24}" class="bh-schurre"/>
  <line x1="${x1 + 4}" y1="${y1 + 24}" x2="${x1 + 4}" y2="${y1 + 38}" class="bh-strahl"/>`;
  s += `<line x1="0" y1="${gl}" x2="${B}" y2="${gl}" class="bh-schiene"/>`;
  sv.innerHTML = s;
  return cx + 4;
}
zug();
kh();
addEventListener('resize', zug);
if (location.hash === '#laden') {
  const z = document.querySelector('.szene');
  if (z) z.classList.add('laedt');
} // Vorschau: Band läuft dauerhaft
document.querySelectorAll('#bahnhof button[data-l]').forEach(b => b.addEventListener('click', () => location.reload())); // lokal: neue Änderungen
const knopf = document.getElementById('fertig'),
  meld = document.getElementById('meldung');
const ich = ZUG.find(w => w.p === MR.projekt);
function feier() {
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
    e.style.cssText = `position:absolute;left:0;top:0;font-size:${16 + zf() * 30}px;line-height:1;will-change:transform`;
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
if (location.hash === '#feier') setTimeout(feier, 300); // Vorschau: Seite mit #feier aufrufen
function weiter() {
  const n = naechster();
  if (n) {
    meld.textContent = '→ weiter zu ' + n.p;
    setTimeout(() => (location.href = n.datei), 600);
  } else meld.textContent = 'Alles durch – kein offener Waggon mehr 🎉';
}
if (knopf) {
  // „fertig ✓“ gibt es nur bei Waggons, deren Quelle das kann (lokal)
  if (ich && ich.status === 'fertig') {
    knopf.textContent = '✓ fertig';
    knopf.classList.add('erledigt');
    knopf.disabled = true;
    weiter();
  } else if (!MR.dateien) {
    knopf.style.display = 'none';
  }
  knopf.addEventListener('click', () => {
    knopf.disabled = true;
    meld.textContent = 'wird übernommen …';
    if (typeof RV !== 'undefined') {
      const o = (RV.faeden || []).filter(k => k.status === 'wartet' || k.status === 'antwort').length,
        e = RV.g_ausstehend || 0;
      if (
        (o || e) &&
        !confirm(
          (o ? o + ' Gespräch(e) noch offen' : '') +
            (o && e ? ', ' : '') +
            (e ? e + (e > 1 ? ' Entwürfe' : ' Entwurf') + ' nicht gesendet' : '') +
            ' – trotzdem fertig?'
        )
      ) {
        knopf.disabled = false;
        meld.textContent = '';
        return;
      }
    }
    if (location.protocol.startsWith('http')) {
      fetch('/fertig', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mr: MR.id, projekt: MR.projekt, sha: MR.sha, k: MR.k})
      })
        .then(r => r.json())
        .then(d => {
          if (!d.ok) {
            knopf.disabled = false;
            meld.textContent = d.text;
            return;
          }
          ZUG = d.wagen;
          zug();
          kh();
          knopf.textContent = '✓ fertig';
          knopf.classList.add('erledigt');
          weiter();
          if (!naechster()) feier();
        })
        .catch(e => {
          knopf.disabled = false;
          meld.textContent = 'merge-train-Server nicht erreichbar – merge-train erneut aufrufen';
        });
      return;
    }
    knopf.disabled = false;
    meld.textContent = 'Seite bitte über merge-train öffnen, dann klappt „fertig“.';
  });
}
document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey || /INPUT|TEXTAREA|BUTTON/.test(e.target.tagName)) return;
  if (e.key === 'n') {
    const n = naechster();
    if (n) location.href = n.datei;
  } else if (e.key === 'Enter' && knopf && !knopf.disabled && knopf.style.display !== 'none') {
    e.preventDefault();
    knopf.click();
  }
});
