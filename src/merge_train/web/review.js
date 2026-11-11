// Diff-Seiten: Review-Kommentare, Agent-Hinweise (drafts) und Gesprächsfäden an den Zeilen; Eingabefelder, Senden,
// Abschließen; fragt alle 4 s den Stand ab (lädt neu bei neuen Daten oder neuem Server). Braucht von App: waggon, kann,
// el, uhrzeit, melden, meldung, serverWeg, dateien, dateiLinks, kopfhoeheSetzen, aus diff.js waggonAbfrage, nurLesen,
// seitAnsicht, zeileZeigen, zeileFinden, popup, sieheAuch, ortLink, dateiLaden, kommentarListe; später geladen:
// hudZeichnen, serverLed, serverStandSetzen (hud.js), zugHolen (bahnhof.js). Stellt bereit: review (Daten der Seite),
// zeichnen, statusTexte, kommentarAktion, fadenAktion, reviewLaden.
(() => {
  const {
    el,
    waggon,
    uhrzeit,
    dateien,
    dateiLinks,
    kopfhoeheSetzen,
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
  } = App;
  const review = {
    kommentare: [],
    faeden: [],
    agenten: [],
    hinweise: [],
    quellen: [],
    stand: null,
    zeigVerworfen: false
  };
  let zeichnenWartet = false;
  function post(pfad, d) {
    return fetch(pfad, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(
        Object.assign({mr: waggon.id, k: waggon.k, sha: waggon.sha, ansicht: waggon.ansicht || ''}, d)
      )
    })
      .then(r => r.json())
      .catch(() => ({ok: false, text: 'merge-train-Server nicht erreichbar – merge-train erneut aufrufen'}));
  }
  function antwort(d) {
    if (!d.ok) {
      App.melden(d.text || 'Fehler');
      return d;
    }
    App.melden('');
    if (d.review) {
      Object.assign(review, d.review);
      zeichnen();
    }
    return d;
  }
  function laden() {
    return fetch('/api/review?' + waggonAbfrage())
      .then(r => r.json())
      .then(d => {
        if (App.meldung.textContent === App.serverWeg) App.melden(''); // Server war kurz weg (Neustart nach ./bauen)
        if (!d.ok) {
          App.melden(d.text);
          return;
        }
        Object.assign(review, d);
        zeichnen();
        autoLaden();
      })
      .catch(() => {
        App.melden(App.serverWeg);
      });
  }
  const statusTexte = {
    neu: ['Entwurf (lokal)', 'b-neu'],
    uebertragen: ['in GitLab (Entwurf)', 'b-ok'],
    geaendert: ['geändert – wird aktualisiert', 'b-geaendert'],
    loeschen: ['wird in GitLab gelöscht', 'b-loeschen'],
    weg: ['in GitLab veröffentlicht', 'b-ok'],
    // Gespräch (lokales Projekt)
    entwurf: ['Entwurf – noch nicht gesendet', 'b-entwurf'],
    wartet: ['wartet auf Claude', 'b-wartet'],
    antwort: ['Claude hat geantwortet', 'b-antwort'],
    erledigt: ['erledigt', 'b-erledigt']
  };
  const faeden = () => review.faeden || [],
    fragenEntwuerfe = () => review.g_ausstehend || 0,
    mitReview = !!App.kann.review; // Waggon mit Review (Kommentare nach außen)
  function fadenAktion(d) {
    return kommentarAktion(Object.assign({gespraech: 1}, d));
  } // Fragen an den Agenten: Fäden, nie ins Review
  // wen man fragen kann (lokal mindestens Claude)
  const agenten = () => (review.agenten && review.agenten.length ? review.agenten : mitReview ? [] : ['Claude']);
  function neuSpeichern(d) {
    // neuer Kommentar: mit Review als Review-Kommentar, sonst als Frage an den ersten Agenten
    return t =>
      mitReview
        ? kommentarAktion(Object.assign({}, d, {aktion: 'neu', text: t}))
        : fadenAktion(Object.assign({}, d, {aktion: 'neu', an: agenten()[0], text: t})).then(sofortSenden);
  }
  function sofort(w) {
    try {
      if (w !== undefined) localStorage.sofort = w ? 1 : '';
      return !!localStorage.sofort;
    } catch (_) {
      return false;
    }
  } // „sofort senden“, bleibt gespeichert
  function sofortSenden(d) {
    if (d && d.ok && sofort()) senden();
    return d;
  }
  function bearbeiten(box, text, speichern, abbruch, extra, mitSofort) {
    // extra: [[beschriftung, speichern(t)|null, titel]] – null = ausgegraut; mitSofort: Häkchen „sofort senden“
    const ta = el('textarea', {}),
      alt = [...box.childNodes];
    ta.value = text || '';
    const zu = () => {
      if (abbruch) abbruch();
      else box.replaceChildren(...alt);
      nachholen();
    };
    const ok = (sp = speichern) => {
      const t = ta.value.trim();
      if (!t) {
        ta.focus();
        return;
      }
      sp(t).then(d => {
        if (!d || !d.ok) return;
        if (abbruch) abbruch();
        else box.replaceChildren();
        zeichnen();
      });
    };
    ta.addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        ok();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        zu();
      }
    });
    box.replaceChildren(
      ta,
      el(
        'div',
        {class: 'kk'},
        el('span', {}, 'Strg+Enter speichern · Esc abbrechen'),
        el(
          'span',
          {class: 'knoepfe'},
          mitSofort
            ? el(
                'label',
                {
                  class: 'sofort',
                  title:
                    'Fragen an den Agenten gleich abschicken statt erst mit „' +
                    (mitReview ? 'Fragen' : 'Feedback') +
                    ' senden“'
                },
                (() => {
                  const c = el('input', {type: 'checkbox'});
                  c.checked = sofort();
                  c.addEventListener('change', () => sofort(c.checked));
                  return c;
                })(),
                ' sofort senden'
              )
            : null,
          el('button', {onclick: zu}, 'abbrechen'),
          ...(extra || []).map(([t, sp, ti]) =>
            el('button', {title: ti || '', disabled: sp ? null : '', onclick: () => ok(sp)}, t)
          ),
          el(
            'button',
            {class: 'haupt', onclick: () => ok()},
            extra ? (mitReview ? 'als Review-Kommentar' : 'an ' + agenten()[0]) : 'speichern'
          )
        )
      )
    );
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  }
  function kommentarAktion(d) {
    return post('/api/kommentar', d).then(r => {
      const x = antwort(r);
      return x;
    });
  }
  function autoLaden() {
    [...review.kommentare, ...review.hinweise].forEach(x => {
      const d = x.datei != null && dateien[x.datei];
      if (d && d.querySelector('.spaet')) dateiLaden(d);
    });
  }
  /** Gespräch: Verlauf wie im Messenger, eigene Nachrichten rechts. */
  function fadenBox(k, mitOrt) {
    const wer = k.an || 'Claude',
      [st0, cl] = statusTexte[k.status] || ['?', ''],
      neuVomAgenten = k.vom_agenten && k.status === 'antwort' && k.nachrichten.length === 1,
      st = (neuVomAgenten ? 'neu von Claude' : st0).replace('Claude', wer),
      box = el('div', {
        class: 'kbox km gs st-' + k.status + (k.status === 'erledigt' ? ' erledigt' : ''),
        'data-id': k.id
      }),
      kn = el('span', {class: 'knoepfe'}),
      offen = !nurLesen && !k.lesen,
      verlauf = el('div', {class: 'verlauf'});
    const antw = () =>
      el(
        'button',
        {
          onclick: () => {
            const b = el('div', {class: 'msg ich entwurf'});
            verlauf.append(b);
            bearbeiten(
              b,
              '',
              t => fadenAktion({aktion: 'antworten', id: k.id, text: t}).then(sofortSenden),
              () => b.remove(),
              undefined,
              true
            );
          }
        },
        '↩ antworten'
      );
    if (offen) kn.append(antw(), ...fadenKnoepfe(k));
    const er = k.erledigt
      ? el(
          'span',
          {},
          '· erledigt von ' +
            (k.erledigt.von === 'claude' ? k.erledigt.wer || wer : 'dir') +
            ' ' +
            uhrzeit(k.erledigt.zeit)
        )
      : null;
    box.append(el('div', {class: 'kk'}, el('span', {class: 'badge ' + cl}, st), er, mitOrt ? ortLink(k) : null, kn));
    if (k.zeile_text && k.problem)
      box.append(
        el(
          'div',
          {class: 'alt', title: 'die Zeile, als der Kommentar geschrieben wurde'},
          'damals: ' + k.zeile_text.trim()
        )
      );
    k.nachrichten.forEach(m => verlauf.append(nachrichtBox(k, m, wer, offen)));
    box.append(verlauf);
    const sa = sieheAuch(k.see_also);
    if (sa) box.append(sa);
    if (offen && k.nachrichten.length > 1) box.append(el('div', {class: 'unten'}, antw())); // auch unten (lange Fäden)
    return box;
  }
  /** Knöpfe eines offenen Fadens neben „antworten“: erledigt bzw. wieder öffnen, löschen. */
  function fadenKnoepfe(k) {
    return [
      k.status === 'erledigt'
        ? el('button', {onclick: () => fadenAktion({aktion: 'oeffnen', id: k.id})}, 'wieder öffnen')
        : el(
            'button',
            {title: 'Gespräch als erledigt markieren', onclick: () => fadenAktion({aktion: 'erledigt', id: k.id})},
            '✓ erledigt'
          ),
      el(
        'button',
        {
          title: 'ganzes Gespräch löschen',
          onclick: () => {
            if (confirm('Ganzes Gespräch löschen?')) fadenAktion({aktion: 'loeschen', id: k.id});
          }
        },
        '🗑'
      )
    ];
  }
  /** Eine Nachricht im Verlauf: Kopf (wer, wann, ✓/✓✓ bzw. Entwurf mit ✎/🗑) und Text mit Code-Links. */
  function nachrichtBox(k, m, wer, offen) {
    const ich = m.von === 'ich',
      entwurf = ich && !m.gesendet,
      mb = el('div', {class: 'msg ' + (ich ? 'ich' : 'claude') + (entwurf ? ' entwurf' : '')});
    const haken = !ich
      ? null
      : entwurf
        ? el('span', {}, 'Entwurf')
        : el(
            'span',
            {
              class: 'haken' + (m.abgeholt ? ' abgeholt' : ''),
              title: m.abgeholt ? 'von ' + wer + ' abgeholt um ' + uhrzeit(m.abgeholt) : 'gesendet, noch nicht abgeholt'
            },
            m.abgeholt ? '✓✓' : '✓'
          );
    const mk = el(
      'div',
      {class: 'mk'},
      el('b', {}, ich ? 'Du' : '🤖 ' + (m.wer || wer)),
      el('span', {}, uhrzeit(m.gesendet || m.zeit)),
      haken
    );
    if (entwurf && offen)
      mk.append(
        el(
          'button',
          {onclick: () => bearbeiten(mb, m.text, t => fadenAktion({aktion: 'aendern', id: k.id, nid: m.id, text: t}))},
          '✎'
        ),
        el('button', {onclick: () => fadenAktion({aktion: 'loeschen', id: k.id, nid: m.id})}, '🗑')
      );
    mb.append(mk, el('div', {class: 'mt'}, ...verlinkt(m.text, k.links)));
    return mb;
  }
  function verlinkt(text, links) {
    // etwas Markdown (`code`, **fett**) und Code-Verweise (pfad:zeile, Dateiname) als Links aufs Popup
    return text
      .split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/)
      .flatMap((t, i) =>
        i % 2 === 0
          ? codeLinks(t, links)
          : t[0] === '`'
            ? [el('code', {}, ...codeLinks(t.slice(1, -1), links))]
            : [el('b', {}, ...codeLinks(t.slice(2, -2), links))]
      );
  }
  function codeLinks(text, links) {
    if (!links || !links.length || !text) return [text];
    const L = {};
    links.forEach(l => (L[l.t] = l));
    const esc = t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
      rx = new RegExp(
        '(?<![\\w/.-])(' +
          Object.keys(L)
            .sort((a, b) => b.length - a.length)
            .map(esc)
            .join('|') +
          ')(?![\\w/])',
        'g'
      );
    const out = [];
    let i = 0,
      m;
    while ((m = rx.exec(text))) {
      const l = L[m[1]];
      out.push(
        text.slice(i, m.index),
        el(
          'a',
          {
            class: 'codelink',
            title: l.path + (l.zeile ? ':' + l.zeile + (l.bis ? '-' + l.bis : '') : ''),
            onclick: () => popup(l.path, l.zeile, null, l.bis)
          },
          m[1]
        )
      );
      i = m.index + m[1].length;
    }
    out.push(text.slice(i));
    return out;
  }
  function kommentarBox(k, mitOrt) {
    const [st, cl] = statusTexte[k.status] || ['?', ''],
      box = el('div', {class: 'kbox km' + (k.status === 'loeschen' ? ' weg' : ''), 'data-id': k.id}),
      kn = el('span', {class: 'knoepfe'});
    if (nurLesen || k.lesen);
    else if (k.status === 'loeschen')
      kn.append(
        el('button', {onclick: () => kommentarAktion({aktion: 'wiederherstellen', id: k.id})}, 'wiederherstellen')
      );
    else
      kn.append(
        ...(k.status === 'weg'
          ? []
          : [
              el(
                'button',
                {onclick: () => bearbeiten(box, k.text, t => kommentarAktion({aktion: 'aendern', id: k.id, text: t}))},
                '✎ bearbeiten'
              )
            ]),
        el(
          'button',
          {
            onclick: () => {
              if (k.status === 'neu' && !confirm('Kommentar löschen?')) return;
              kommentarAktion({aktion: 'loeschen', id: k.id});
            }
          },
          '🗑 löschen'
        )
      );
    box.append(
      el(
        'div',
        {class: 'kk'},
        el('span', {class: 'badge ' + cl}, st),
        k.finding ? el('span', {class: 'badge b-agent'}, 'aus Agent ' + k.finding) : null,
        mitOrt ? ortLink(k) : null,
        kn
      ),
      el('div', {class: 'kt'}, k.text)
    );
    const h = k.hinweis && review.hinweise.find(x => x.key === k.hinweis),
      sa = h && sieheAuch(h.see_also);
    if (sa) box.append(sa);
    return box;
  }
  function hinweisBox(h, mitOrt) {
    const box = el('div', {class: 'kbox hw' + (h.status === 'verworfen' ? ' weg' : ''), 'data-id': h.key}),
      kn = el('span', {class: 'knoepfe'});
    if (nurLesen || h.lesen);
    else if (h.status === 'verworfen')
      kn.append(
        el(
          'button',
          {onclick: () => post('/api/hinweis', {aktion: 'zurueck', key: h.key}).then(antwort)},
          'zurückholen'
        )
      );
    else
      kn.append(
        el(
          'button',
          {
            class: 'haupt',
            title: 'als Review-Kommentar übernehmen',
            onclick: () => kommentarAktion({aktion: 'neu', hinweis: h.key})
          },
          'übernehmen'
        ),
        el(
          'button',
          {onclick: () => bearbeiten(box, h.text, t => kommentarAktion({aktion: 'neu', hinweis: h.key, text: t}))},
          '✎ anpassen & übernehmen'
        ),
        el(
          'button',
          {onclick: () => post('/api/hinweis', {aktion: 'verwerfen', key: h.key}).then(antwort)},
          'verwerfen'
        )
      );
    const NAMEN = {problem: 'Problem', decision: 'Entscheidung', status: 'Status', placement: 'Platzierung'},
      ex = h.extra || {};
    const det = [
      ['Problem', ex.problem],
      ['Entscheidung', ex.decision],
      ['Begründung', h.rationale],
      ['Behoben, wenn', h.resolved_when],
      ...Object.entries(ex)
        .filter(([k]) => k !== 'problem' && k !== 'decision')
        .map(([k, v]) => [NAMEN[k] || k, v])
    ].filter(x => x[1] != null && x[1] !== '');
    box.append(
      el(
        'div',
        {class: 'kk'},
        el('span', {class: 'badge b-agent'}, '🤖 Agent ' + (h.finding || '')),
        el('span', {}, h.quelle || ''),
        mitOrt ? ortLink(h) : null,
        h.mehrfach ? el('span', {}, '(passt auf ' + h.mehrfach + ' Zeilen)') : null,
        h.problem ? el('span', {class: 'warn'}, h.problem) : null,
        ex.status ? el('span', {class: 'badge'}, 'Status: ' + ex.status) : null,
        kn
      ),
      el('div', {class: 'kt'}, h.text)
    );
    const sa = sieheAuch(h.see_also);
    if (sa) box.append(sa);
    if (det.length) {
      const d = el('details', {}, el('summary', {}, 'Details'));
      det.forEach(([k, v]) =>
        d.append(el('div', {}, el('b', {}, k + ': '), typeof v === 'string' ? v : JSON.stringify(v, null, 1)))
      );
      box.append(d);
    }
    return box;
  }
  function einfuegen(r, inhalt, tab) {
    let z = r;
    while (z.nextElementSibling && z.nextElementSibling.classList.contains('kr')) z = z.nextElementSibling;
    const tr = el('tr', {class: 'kr'}, el('td', {colspan: tab.classList.contains('sbs') ? 4 : 3}, inhalt));
    z.after(tr);
    return tr;
  }
  function nachholen() {
    if (zeichnenWartet) setTimeout(zeichnen, 0);
  }
  function unterDatei(x, box) {
    // Ansicht: Eintrag lässt sich keiner sichtbaren Zeile zuordnen → unter den Dateinamen, mit Grund
    const d = dateien[x.datei];
    let c = d.querySelector(':scope>.kunter');
    if (!c) {
      c = el('div', {class: 'kunter'});
      d.querySelector('summary').after(c);
    }
    const mrOrt = x.mr_b || x.mr_a,
      wo = mrOrt
        ? el(
            'a',
            {class: 'ortlink', title: 'im MR-Stand zeigen', onclick: () => popup(x.path, x.mr_b || null)},
            'MR-Stand: Zeile ' + mrOrt + (x.mr_b ? '' : ' (alt)')
          )
        : null;
    const zur = x.b
      ? el('a', {class: 'ortlink', title: 'Kontext aufklappen', onclick: () => zeileZeigen(x)}, 'aufklappen')
      : null;
    c.append(
      el('div', {class: 'unter'}, el('span', {class: 'warn'}, x.unter), zur ? ' · ' : null, zur, wo ? ' · ' : null, wo),
      box
    );
  }
  function zeichnen() {
    // Kästen mit offenem Eingabefeld bleiben stehen (der Text darin soll nicht verloren gehen), alles andere wird neu
    // gezeichnet. Nach dem Schließen des Felds holt nachholen() den Kasten selbst nach.
    const felder = [...document.querySelectorAll('.kbox textarea')].map(t => t.closest('.kbox')).filter(Boolean);
    const bleibt = new Set(felder.map(b => b.dataset.id).filter(Boolean)),
      haelt = e => felder.some(b => e === b || e.contains(b));
    zeichnenWartet = felder.length > 0;
    document.querySelectorAll('tr.kr').forEach(r => {
      if (!haelt(r)) r.remove();
    });
    document.querySelectorAll('.kunter').forEach(c => {
      if (!haelt(c)) {
        c.remove();
        return;
      }
      [...c.children].forEach(e => {
        if (!haelt(e) && !(e.classList.contains('unter') && e.nextElementSibling && haelt(e.nextElementSibling)))
          e.remove();
      });
    });
    const allg = [],
      zahl = {};
    const platz = (x, mach) => {
      if (x.datei == null || !dateien[x.datei] || !(x.a || x.b)) return false;
      if (bleibt.has(x.id || x.key)) {
        zahl[x.datei] = (zahl[x.datei] || 0) + 1;
        return true;
      }
      let ok = false;
      dateien[x.datei].querySelectorAll('table').forEach(tab => {
        const r = zeileFinden(tab, x.a, x.b);
        if (r) {
          einfuegen(r, mach(), tab);
          ok = true;
        }
      });
      if (ok) zahl[x.datei] = (zahl[x.datei] || 0) + 1;
      return ok;
    };
    const unter = (x, mach) => {
      if (x.unter == null || x.datei == null || !dateien[x.datei]) return false;
      if (!bleibt.has(x.id || x.key)) unterDatei(x, mach());
      zahl[x.datei] = (zahl[x.datei] || 0) + 1;
      return true;
    };
    const allgDazu = (x, mach) => {
      if (!bleibt.has(x.id || x.key)) allg.push(mach);
    };
    review.kommentare.forEach(k => {
      if (!platz(k, () => kommentarBox(k, false)) && !unter(k, () => kommentarBox(k, false)))
        allgDazu(k, () => kommentarBox(k, true));
    });
    faeden().forEach(k => {
      if (!platz(k, () => fadenBox(k, false)) && !unter(k, () => fadenBox(k, false)))
        allgDazu(k, () => fadenBox(k, true));
    });
    review.hinweise
      .filter(h => h.status === 'offen' || (review.zeigVerworfen && h.status === 'verworfen'))
      .forEach(h => {
        if (!platz(h, () => hinweisBox(h, false)) && !unter(h, () => hinweisBox(h, false)))
          allgDazu(h, () => hinweisBox(h, true));
      });
    allgemein(allg);
    kommentarListe();
    dateiLinks.forEach((a, i) => {
      const z = a.querySelector('.kz');
      if (z) z.textContent = zahl[i] ? '💬' + zahl[i] : '';
    });
    const n = review.kommentare.filter(k => k.status !== 'loeschen').length,
      offen = review.hinweise.filter(h => h.status === 'offen').length;
    if (!mitReview) {
      gsStand();
      kopfhoeheSetzen();
      return;
    }
    gsStand(
      n +
        ' Kommentar(e)' +
        (review.ausstehend ? ' · ' + review.ausstehend + ' noch nicht in GitLab' : '') +
        (offen ? ' · ' + offen + ' Agent-Hinweis(e) offen' : '')
    );
    kopfhoeheSetzen();
  }
  const seitenTitel = document.title,
    feedbackKnopf = document.getElementById('feedback'),
    sessionKnopf = document.getElementById('starten');
  function gsStand(vorn) {
    const f = faeden(),
      z = s => f.filter(k => k.status === s).length,
      neu = z('antwort'),
      w = z('wartet'),
      e = fragenEntwuerfe();
    App.hudZeichnen();
    document.getElementById('rvstand').textContent = [
      vorn,
      f.length ? f.length + ' Gespräch(e)' : null,
      e ? e + (mitReview ? ' Fragen-Entw' : ' Entw') + (e > 1 ? 'ürfe' : 'urf') : null,
      w ? w + ' wartet auf Antwort' : null,
      neu ? neu + ' neue Antwort(en)' : null,
      review.horcht ? '🎧 ' + review.horcht + ' hört zu' : null
    ]
      .filter(Boolean)
      .join(' · ');
    if (!feedbackKnopf) return;
    feedbackKnopf.hidden = mitReview && !f.length;
    feedbackKnopf.disabled = !e;
    const fw = mitReview ? 'Fragen senden' : 'Feedback senden';
    feedbackKnopf.textContent = e ? fw + ' (' + e + ')' : fw;
    sessionKnopf.hidden = !review.todo || !!review.horcht;
    document.title = (neu ? '(' + neu + ') ' : '') + seitenTitel;
  }
  function senden() {
    if (!feedbackKnopf) return;
    feedbackKnopf.disabled = true;
    App.melden('sendet …');
    post('/api/gespraech', {aktion: 'senden'}).then(d => {
      App.melden(d.text || '');
      if (d.review) {
        Object.assign(review, d.review);
        zeichnen();
      } else gsStand();
    });
  }
  if (feedbackKnopf) {
    feedbackKnopf.addEventListener('click', senden);
    sessionKnopf.addEventListener('click', () => {
      sessionKnopf.disabled = true;
      post('/api/gespraech', {aktion: 'starten'}).then(d => {
        sessionKnopf.disabled = false;
        App.melden(d.text || '');
      });
    });
  }
  function anKnoepfe(d) {
    // weitere Speichern-Knöpfe „an <Agent>“ (mit Review alle; sonst ist der erste „speichern“)
    const a = mitReview ? agenten() : agenten().slice(1);
    if (!mitReview && !a.length) return undefined;
    return a.length
      ? a.map(n => [
          'an ' + n,
          t => fadenAktion(Object.assign({}, d, {aktion: 'neu', an: n, text: t})).then(sofortSenden),
          'Frage an ' + n + ' – bleibt privat, geht nicht nach GitLab'
        ])
      : [
          [
            'an Agent',
            null,
            'Kein Agent eingerichtet: [agenten] in der Einstellung oder „merge-train agent horchen“ in einer Session'
          ]
        ];
  }
  function allgemein(allg) {
    let s = document.getElementById('allgemein');
    if (!s) {
      s = el('section', {id: 'allgemein'});
      document.querySelector('main').prepend(s);
    }
    const verw = review.hinweise.filter(h => h.status === 'verworfen').length,
      offen = [...s.children].filter(e => e.classList.contains('kbox') && e.querySelector('textarea'));
    s.replaceChildren(
      el(
        'div',
        {class: 'kk'},
        el('b', {}, mitReview ? 'Review' : 'Gespräch mit ' + agenten()[0]),
        el(
          'span',
          {class: 'sub'},
          allg.length ? 'außerhalb des Diffs / allgemein:' : 'Kommentare stehen an den Zeilen'
        ),
        el(
          'span',
          {class: 'knoepfe'},
          verw
            ? el(
                'button',
                {
                  onclick: () => {
                    review.zeigVerworfen = !review.zeigVerworfen;
                    zeichnen();
                  }
                },
                review.zeigVerworfen ? 'verworfene ausblenden' : verw + ' verworfene Hinweise zeigen'
              )
            : null,
          nurLesen
            ? null
            : el(
                'button',
                {
                  onclick: () => {
                    const b = el('div', {class: 'kbox km'});
                    s.append(b);
                    bearbeiten(b, '', neuSpeichern({}), () => b.remove(), anKnoepfe({}), agenten().length > 0);
                  }
                },
                mitReview ? '＋ allgemeiner Kommentar' : '＋ allgemeine Frage'
              )
        )
      ),
      review.ausserhalb
        ? el(
            'div',
            {class: 'sub'},
            review.ausserhalb +
              ' weitere(r) Kommentar(e)/Hinweis(e) in Dateien, die diese Ansicht nicht ändert – siehe ganzer MR'
          )
        : ''
    );
    review.quellen.forEach(q => {
      const d = el(
        'details',
        {class: 'quelle'},
        el(
          'summary',
          {},
          '🤖 ' +
            (q.key || q.datei) +
            (q.reviewed_commit ? ' · geprüft ' + q.reviewed_commit : '') +
            (q.reviewed_at ? ' am ' + q.reviewed_at : '') +
            ' · ' +
            q.anzahl +
            ' Hinweis(e)'
        ),
        q.fehler ? el('div', {class: 'warn'}, q.fehler) : null,
        q.alt
          ? el(
              'div',
              {class: 'warn'},
              'geprüft auf Stand ' +
                q.reviewed_commit +
                ', der MR steht auf ' +
                waggon.sha.slice(0, 8) +
                ' – Hinweise evtl. veraltet'
            )
          : null,
        el('div', {}, q.datei),
        q.notes ? el('div', {class: 'kt'}, q.notes) : null,
        q.failing_tests ? el('div', {}, el('b', {}, 'failing_tests: '), JSON.stringify(q.failing_tests, null, 1)) : null
      );
      if (q.fehler) d.open = true;
      s.append(d);
    });
    allg.forEach(f => s.append(f()));
    offen.forEach(b => s.append(b));
  } // offene Eingabefelder bleiben
  document.addEventListener('click', e => {
    const td = e.target.closest('main td.n,#popup:not(.vergleich) td.n');
    if (!td || !td.textContent.trim()) return; // Seite und Popup (ausgeliehene Datei, nicht der Dateivergleich)
    if (nurLesen) {
      App.melden('Nur-Lese-Ansicht: kommentieren im ganzen MR oder in „seit diesem“');
      return;
    }
    const tr = td.closest('tr');
    if (!tr || !(tr.dataset.a || tr.dataset.b)) return;
    const tab = tr.closest('table'),
      n = dateien.indexOf(tr.closest('.datei'));
    let a = tr.dataset.a ? +tr.dataset.a : null,
      b = tr.dataset.b ? +tr.dataset.b : null;
    if (tab.classList.contains('sbs') && tr.querySelector('.weg,.dazu,.nix')) {
      if (td.cellIndex === 0) b = null;
      else a = null;
    }
    if (seitAnsicht && b == null) {
      App.melden('In dieser Ansicht nur rechts (MR-Stand) kommentierbar');
      return;
    }
    const box = el('div', {class: 'kbox km'}),
      zr = einfuegen(tr, box, tab);
    bearbeiten(
      box,
      '',
      neuSpeichern({datei: n, a, b}),
      () => zr.remove(),
      anKnoepfe({datei: n, a, b}),
      agenten().length > 0
    );
  });
  const abschliessenKnopf = document.getElementById('abschliessen');
  if (abschliessenKnopf)
    abschliessenKnopf.addEventListener('click', () => {
      abschliessenKnopf.disabled = true;
      App.melden('überträgt Entwürfe nach GitLab …');
      post('/api/abschliessen', {}).then(d => {
        abschliessenKnopf.disabled = false;
        App.melden((d.text || '') + (d.web_url ? ' → in GitLab prüfen ↗' : ''));
        if (d.review) {
          Object.assign(review, d.review);
          zeichnen();
        }
        App.zugHolen();
      });
    });
  // auch im Hintergrund: Lebenszeichen der Seite (horchen hört auf, wenn keins mehr kommt). Neuer Server (neu gebaut
  // oder Einstellung geändert): Seite neu laden, sobald kein Eingabefeld offen ist. --beobachten: veraltet = im Repo
  // hat sich etwas geändert → neu laden (beobachten.js rahmt danach das Neue ein)
  function pruefen() {
    fetch('/api/stand?' + waggonAbfrage() + '&sha=' + encodeURIComponent(waggon.sha || ''))
      .then(r => r.json())
      .then(d => {
        if (d.server) App.serverStandSetzen(d.server);
        if (d.version && waggon.version && d.version !== waggon.version) {
          App.serverLed('neu');
          if (!document.querySelector('textarea')) {
            try {
              sessionStorage.meldung = 'merge-train wurde aktualisiert – Seite neu geladen';
            } catch (_) {}
            location.reload();
          }
          return;
        }
        if (d.veraltet) {
          App.serverLed('neu');
          if (!document.querySelector('textarea')) {
            try {
              sessionStorage.meldung = 'Änderung im Repo – Seite neu geladen';
              sessionStorage.beobachtetAlt = waggon.sha || '';
            } catch (_) {}
            location.reload();
          }
          return;
        }
        App.serverLed('an');
        if (d.stand && (d.stand !== review.stand || App.meldung.textContent === App.serverWeg)) laden();
      })
      .catch(() => {
        App.melden(App.serverWeg);
        App.serverLed('weg');
      });
  }
  setInterval(pruefen, 4000);
  setTimeout(pruefen, 300);
  laden();
  Object.assign(App, {review, zeichnen, statusTexte, kommentarAktion, fadenAktion, reviewLaden: laden});
})();
