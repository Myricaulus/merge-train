// Diff-Seiten: Stellwerk-HUD im Kopf (rechts neben der Schurre): Server-LED, Stand von merge-train, Zähler, wer zuhört,
// Kontext-Füllstand der Agenten-Session. Auch auf der Startseite (Güterbahnhof, auch mit Fehler wie „kein lokaler
// Klon“): ohne review.js fragt es selbst alle 4 s api/hud (Server, wer zuhört) und zeigt keine Zähler.
// Braucht von App: el, kann, waggon, melden, serverWeg, review (nur Diff-Seiten). Stellt bereit: hudZeichnen, serverLed, serverStandSetzen.
(() => {
  const {el} = App;
  const ohneReview = {kommentare: [], hinweise: [], faeden: [], horcht: null, zuhoerer: null, kontext: null};
  const R = () => App.review || ohneReview;
  // HUD: Stellwerk auf Stelzen rechts neben der Schurre (Zug fährt drunter durch): Server-LED, Stand, Zähler, wer
  // zuhört.
  let ledZustand = 'an',
    serverStand = null; // SERVER: Stand von merge-train (Commit, Zeit, ungespeicherte Änderungen) aus /api/stand
  function serverLed(z) {
    if (ledZustand === z) return;
    ledZustand = z;
    hudZeichnen();
  }
  const hudTeile = (() => {
    const sz = document.querySelector('.szene');
    if (!sz) return null;
    const bau = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    bau.id = 'hud-bau';
    const h = el('div', {id: 'hud'});
    sz.append(bau, h);
    addEventListener('resize', () => hudLage());
    return {sz, bau, h};
  })();
  function hudLage() {
    if (!hudTeile) return;
    const B = hudTeile.sz.clientWidth,
      H = hudTeile.sz.clientHeight,
      cx = Math.round(Math.max(B / 2, 330)),
      gl = H - 4;
    const W = Math.min(372, B - cx - 58),
      x = B - W - 10,
      y = 98,
      h = 42;
    /* ganz rechts, aber nie über der Schurre */ hudTeile.h.hidden = hudTeile.bau.hidden = W < 230;
    document.body.classList.toggle('mit-hud', W >= 230);
    if (W < 230) return;
    Object.assign(hudTeile.h.style, {left: x + 'px', top: y + 'px', width: W + 'px', height: h + 'px'});
    const turm = xl => {
      // schlanke Gittertürme, Zug fährt dazwischen
      let s = `<path d="M${xl},${y + h + 3} V${gl - 4} M${xl + 9},${y + h + 3} V${gl - 4}" class="hud-stelze"/>`;
      for (let yy = y + h + 3; yy < gl - 12; yy += 13)
        s += `<path d="M${xl},${yy} L${xl + 9},${yy + 13} M${xl + 9},${yy} L${xl},${yy + 13}" class="hud-strebe"/>`;
      return s;
    };
    hudTeile.bau.setAttribute('viewBox', `0 0 ${B} ${H}`);
    hudTeile.bau.innerHTML =
      turm(Math.max(x + 14, cx + 96)) +
      turm(x + W - 23) + // links erst hinter dem Wagen unter dem Band
      `<rect x="${x - 4}" y="${y + h}" width="${W + 8}" height="4" class="hud-boden"/>` +
      `<rect x="${x}" y="${y}" width="${W}" height="${h}" rx="2" class="hud-kabine"/>` +
      `<rect x="${x - 6}" y="${y - 5}" width="${W + 12}" height="6" rx="1" class="hud-dach"/>` +
      `<path d="M${x + W - 30},${y - 5} V${y - 18} M${x + W - 36},${y - 14} H${x + W - 24}" class="hud-antenne"/>` +
      `<circle cx="${x + W - 30}" cy="${y - 19}" r="1.8" class="hud-funk"/>`;
  }
  const tokenKurz = n => (n >= 1e6 ? (n / 1e6).toFixed(n % 1e6 ? 1 : 0) + 'M' : Math.round(n / 1e3) + 'k');
  function hudZeichnen() {
    if (!hudTeile) return;
    hudLage();
    const ledTitel = {
      an: 'Server läuft',
      weg: 'Server nicht erreichbar',
      neu: 'neuer Server – Seite lädt neu, sobald kein Eingabefeld offen ist'
    }[ledZustand];
    const zaehler = hudZaehler().concat(hudFeld() || []); // ✎ gehört zu den Nachrichten
    const zeilen = [
      el('div', {class: 'hud-z'}, el('span', {class: 'hud-led ' + ledZustand, title: ledTitel}), hudStand()),
      App.review &&
      el(
        'div',
        {class: 'hud-z'},
        ...(zaehler.length
          ? zaehler.flatMap((e, i) => (i ? [el('span', {class: 'hud-trenn'}, '·'), e] : [e]))
          : [el('span', {}, 'keine Kommentare')])
      )
    ];
    hudTeile.h.replaceChildren(el('div', {class: 'hud-links'}, ...zeilen.filter(Boolean)), hudAgent(R().kontext));
  }
  /** ✎, solange ein Eingabefeld offen ist (es hält Neuladen und Neuzeichnen seiner Box auf): Klick springt hin. */
  function hudFeld() {
    const ta = document.querySelector('textarea');
    if (!ta) return null;
    const hin = () => {
      for (let d = ta.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
      ta.scrollIntoView({block: 'center'});
      ta.focus({preventScroll: true});
    };
    return el(
      'button',
      {
        class: 'hud-feld',
        title:
          'offenes Eingabefeld' +
          (ledZustand === 'neu' ? ' – die Seite lädt neu, sobald es zu ist' : '') +
          ' · Klick springt hin',
        onmousedown: e => e.preventDefault(), // Fokus bleibt im Feld (ein leeres ginge sonst zu)
        onclick: hin
      },
      '✎'
    );
  }
  /** Stand von merge-train selbst: Commit, Zeit, * bei nicht committeten Änderungen in src/. */
  function hudStand() {
    return el(
      'span',
      {
        class: 'hud-stand',
        title: serverStand
          ? 'merge-train: letzter Commit ' +
            serverStand.commit +
            ' vom ' +
            serverStand.zeit +
            (serverStand.geaendert ? ' – dazu Änderungen in src/, die noch nicht committet sind' : '')
          : 'Stand von merge-train'
      },
      serverStand
        ? 'merge-train ' + serverStand.commit + (serverStand.geaendert ? '*' : '') + ' · ' + serverStand.zeit
        : 'merge-train'
    );
  }
  /** Zähler: GitLab-Kommentare (davon lokal), offene Agent-Hinweise, KI-Threads (davon offen). */
  function hudZaehler() {
    const faeden = R().faeden || [],
      offen = faeden.filter(k => k.status !== 'erledigt').length,
      kommentare = R().kommentare.filter(k => k.status !== 'loeschen'),
      lokal = R().ausstehend || 0,
      hinweise = R().hinweise.filter(h => h.status === 'offen').length;
    return [
      mitReview
        ? el(
            'span',
            {title: kommentare.length + ' GitLab-Kommentar(e), davon ' + lokal + ' noch nicht in GitLab'},
            '💬 ' + kommentare.length + (lokal ? ' (' + lokal + ' lokal)' : '')
          )
        : null,
      mitReview && hinweise ? el('span', {title: hinweise + ' Agent-Hinweis(e) offen'}, '🤖 ' + hinweise) : null,
      faeden.length
        ? el(
            'span',
            {
              title:
                faeden.length +
                ' KI-Thread(s)' +
                (offen ? ', davon ' + offen + ' noch offen (nicht erledigt)' : ', alle erledigt')
            },
            '🧵 ' + faeden.length + (offen ? ' (' + offen + ' offen)' : '')
          )
        : null
    ].filter(Boolean);
  }
  /** Rechts: wer zuhört, darunter der Kontext-Füllstand der Agenten-Session (KX aus kontext, sonst ohne Balken). */
  function hudAgent(KX) {
    const SW = (KX && KX.schwellen) || [15, 20, 25, 35],
      ag = el(
        'div',
        {class: 'hud-agent' + (KX && KX.prozent >= SW[3] ? ' gift' : '')},
        App.hoererSpan(R().zuhoerer)
      );
    if (!KX) return ag;
    const p = Math.min(100, KX.prozent),
      c = ctxFarbe(KX.prozent, SW);
    ag.append(
      el(
        'span',
        {
          class: 'hud-ctx',
          style: `background:linear-gradient(to right,${c} ${p}%,rgba(255,255,255,.07) ${p}%)`,
          title:
            'Kontext von ' +
            KX.name +
            ': ' +
            tokenKurz(KX.tokens) +
            ' von ' +
            tokenKurz(KX.fenster) +
            ' Tokens' +
            (R().horcht ? '' : ' (arbeitet gerade, hört nicht zu)') +
            (KX.prozent >= SW[2] ? ' – im Terminal /compact, wenn ein Thema abgeschlossen ist' : '')
        },
        KX.prozent + ' % ctx'
      )
    );
    return ag;
  }
  // Balkenfarbe Kontext, Schwellen [a,b,c,d] aus kontext_schwellen: bis a grün, bis b nach orange, bis c nach rot, dann
  // rot, ab d giftlila (Klasse gift, ohne Übergang)
  function ctxFarbe(p, [a, b, c, d]) {
    const G = [63, 185, 80],
      O = [240, 136, 62],
      R = [248, 81, 73],
      mix = (a, b, t) => 'rgb(' + a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',') + ')';
    return p >= d
      ? '#a100ff'
      : p <= a
        ? mix(G, G, 0)
        : p <= b
          ? mix(G, O, (p - a) / (b - a || 1))
          : p <= c
            ? mix(O, R, (p - b) / (c - b || 1))
            : mix(R, R, 0);
  }
  const mitReview = !!App.kann.review;
  /** Stand von merge-trains Server (aus /api/stand) – nur neu zeichnen, wenn er sich geändert hat */
  function serverStandSetzen(s) {
    if (JSON.stringify(s) === JSON.stringify(serverStand)) return;
    serverStand = s;
    hudZeichnen();
  }
  Object.assign(App, {hudZeichnen, serverLed, serverStandSetzen});
  hudZeichnen();
  if (App.review) return; // Diff-Seiten: review.js fragt api/stand und meldet Server und Zuhörer
  let version;
  function pruefen() {
    fetch('/api/hud?mr=' + encodeURIComponent(App.waggon.id || ''))
      .then(r => r.json())
      .then(d => {
        if (version && d.version !== version) return location.reload(); // neuer Server
        version = d.version;
        if (d.meldung) App.melden(d.meldung);
        ohneReview.horcht = d.horcht;
        ohneReview.zuhoerer = d.zuhoerer;
        ohneReview.kontext = d.kontext;
        ledZustand = 'an';
        serverStand = d.server;
        hudZeichnen();
      })
      .catch(() => {
        App.melden(App.serverWeg);
        serverLed('weg');
      });
  }
  setInterval(pruefen, 4000);
  pruefen();
})();
