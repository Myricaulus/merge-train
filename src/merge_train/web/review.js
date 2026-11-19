// Diff-Seiten: Review-Kommentare, Agent-Hinweise (drafts) und Gesprächsfäden an den Zeilen; Eingabefelder, Senden,
// Abschließen; fragt alle 4 s den Stand ab (lädt neu bei neuen Daten oder neuem Server). Braucht von App: waggon, kann,
// el, uhrzeit, melden, meldung, serverWeg, dateien, dateiLinks, kopfhoeheSetzen, aus diff.js waggonAbfrage, nurLesen,
// seitAnsicht, zeileZeigen, zeileFinden, popup, sieheAuch, ortLink, dateiLaden, kommentarListe; später geladen:
// hudZeichnen, serverLed, serverStandSetzen (hud.js), zugHolen (bahnhof.js). Stellt bereit: review (Daten der Seite),
// zeichnen, STAENDE, werZeichen, direkt, fadenErledigen, kommentarAktion, reviewLaden.
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
    diskussionen: [],
    faeden: [],
    agenten: [],
    hinweise: [],
    quellen: [],
    stand: null,
    zeigVerworfen: false,
    zeigFremde: zeigFremde()
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
    App.zugHolen(); // Marke und fertig des Waggons hängen an Kommentaren, Fäden und Diskussionen
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
    weg: ['in GitLab veröffentlicht', 'b-ok']
  };
  /** Stände der Listen und Threads (Konzept: docs/funktionen.md, „Stände der Listen“), vom Server je Eintrag als
   *  stand (wer jetzt dran ist: [Zeichen, Text], Farbe über die Klasse s-<stand>) und wer (wer zuletzt gehandelt hat). */
  const STAENDE = {
    entwurf: ['○', 'Entwurf – noch nicht gesendet'],
    dran: ['●', 'du bist dran'],
    gitlab_entwurf: ['➜', 'Entwurf in GitLab – dort abschicken'],
    wartet: ['○', 'wartet auf die anderen'],
    erledigt: ['✓', 'erledigt']
  };
  const extern = waggon.extern || {titel: 'extern'},
    WER = {du: 'dir', agent: 'einem Agenten', extern: extern.titel};
  /** Symbol für wer: du = eigenes Emoji (Einstellung ich_symbol), agent = 🤖, extern = Logo der Quelle. */
  function werZeichen(wer) {
    const title = 'zuletzt von ' + (WER[wer] || '?');
    if (wer === 'extern' && extern.logo) return el('img', {class: 'wer', src: extern.logo, alt: extern.titel, title});
    return el('span', {class: 'wer', title}, wer === 'agent' ? '🤖' : wer === 'du' ? waggon.ich || '🤓' : '?');
  }
  /** Text des Stands eines Threads (Badge der Box). */
  function standText(k) {
    const an = k.an || 'Claude';
    if (k.stand === 'dran')
      return k.ziel === 'gitlab'
        ? 'neue Nachricht – du bist dran'
        : (k.vom_agenten && k.nachrichten.length === 1 ? 'neu von ' + an : an + ' hat geantwortet') + ' – du bist dran';
    if (k.stand === 'wartet') return k.ziel === 'gitlab' ? 'wartet auf die anderen' : 'wartet auf ' + an;
    if (k.stand === 'erledigt' && k.ziel === 'gitlab') return 'in GitLab erledigt';
    return (STAENDE[k.stand] || ['', '?'])[1];
  }
  const faeden = () => review.faeden || [],
    fragenEntwuerfe = () => review.g_ausstehend || 0,
    mitReview = !!App.kann.review; // Waggon mit Review (Kommentare nach außen)
  function fadenAktion(d) {
    return kommentarAktion(Object.assign({gespraech: 1}, d));
  } // Fragen an den Agenten: Fäden, nie ins Review
  // Ein Thread, zwei Ziele: Fragen an den Agenten (Fäden) oder eine GitLab-Diskussion. ziel(k)(d) führt die Aktion d
  // (antworten, erledigt, oeffnen, aendern/loeschen mit nid, loeschen ohne nid = ganzer Faden) am richtigen Ziel aus.
  const GITLAB_AKTIONEN = {
    antworten: (k, d) => ({aktion: 'antworten', diskussion: k.diskussion, text: d.text, sofort: sofort() ? 1 : ''}),
    erledigt: k => ({aktion: 'erledigen', diskussion: k.diskussion}),
    oeffnen: k => ({aktion: 'wiedereroeffnen', diskussion: k.diskussion}),
    abhaken: k => ({aktion: 'abhaken', diskussion: k.diskussion}), // lokal erledigt, GitLab bleibt offen
    aufhaken: k => ({aktion: 'aufhaken', diskussion: k.diskussion}),
    aendern: (_k, d) => ({aktion: 'aendern', id: d.nid, text: d.text}), // Antwort-Entwurf = Review-Kommentar
    loeschen: (_k, d) => ({aktion: 'loeschen', id: d.nid})
  };
  function ziel(k) {
    if (k.ziel === 'gitlab') return d => kommentarAktion(GITLAB_AKTIONEN[d.aktion](k, d));
    return d => {
      const p = fadenAktion(Object.assign({id: k.id}, d));
      return d.aktion === 'antworten' ? p.then(sofortSenden) : p;
    };
  }
  // wen man fragen kann (mindestens Claude, auch ohne Zuhörer: abholen mit „agent feedback“)
  const agenten = () => (review.agenten && review.agenten.length ? review.agenten : ['Claude']);
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
  function direkt(w) {
    try {
      if (w !== undefined) localStorage.direkt = w ? 1 : 0;
      return localStorage.direkt !== '0';
    } catch (_) {
      return true;
    }
  } // „direkt veröffentlichen“ (Standard an), bleibt gespeichert
  const DIREKT_TITEL =
    '„Review abschließen“ veröffentlicht die Kommentare gleich in GitLab (eine Benachrichtigung wie „Submit review“, ' +
    'auch für deine übrigen Entwürfe in diesem MR); aus: nur als Entwürfe übertragen, abschicken in GitLab';
  function zeigFremde(w) {
    try {
      if (w !== undefined) localStorage.fremdeFaeden = w ? 1 : '';
      return !!localStorage.fremdeFaeden;
    } catch (_) {
      return false;
    }
  } // „Fäden anderer Branches zeigen“, bleibt gespeichert
  const SOFORT_TITEL =
    'gleich abschicken: Fragen an den Agenten ohne „' +
    (mitReview ? 'Fragen' : 'Feedback') +
    ' senden“' +
    (mitReview ? ', Antworten auf GitLab-Diskussionen ohne Entwurf (gleich veröffentlicht)' : '');
  function sofortHaken() {
    const c = el('input', {type: 'checkbox', class: 'sofort-haken'});
    c.checked = sofort();
    c.addEventListener('change', () => {
      sofort(c.checked);
      document.querySelectorAll('.sofort-haken').forEach(x => (x.checked = c.checked)); // alle Häkchen gleich
    });
    return c;
  }
  function sofortSenden(d) {
    if (d && d.ok && sofort()) senden();
    return d;
  }
  function bearbeiten(box, text, speichern, abbruch, extra, mitSofort, haupt) {
    // extra: [[beschriftung, speichern(t)|null, titel]] – null = ausgegraut; mitSofort: Häkchen „sofort senden“;
    // haupt: Beschriftung des Hauptknopfs
    const ta = el('textarea', {}),
      alt = [...box.childNodes];
    ta.value = text || '';
    const zu = () => {
      if (abbruch) abbruch();
      else box.replaceChildren(...alt);
      nachholen();
      App.hudZeichnen(); // ✎ im HUD weg
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
    // neues, leeres Feld: ein Klick außerhalb des Rahmens schließt es, innerhalb (Häkchen, Beschriftung …) nicht
    const draussen = e => {
      if (!ta.isConnected) return document.removeEventListener('pointerdown', draussen, true);
      if (!text && !ta.value.trim() && !box.contains(e.target)) {
        document.removeEventListener('pointerdown', draussen, true);
        zu();
      }
    };
    document.addEventListener('pointerdown', draussen, true);
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
                {class: 'sofort', title: SOFORT_TITEL},
                sofortHaken(),
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
            haupt || (extra ? (mitReview ? 'als Review-Kommentar' : 'an ' + agenten()[0]) : 'speichern')
          )
        )
      )
    );
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    App.hudZeichnen(); // ✎ im HUD
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
  /** Ein Thread – Gesprächsfaden mit dem Agenten oder GitLab-Diskussion (k.ziel), Aktionen über ziel(k). */
  function fadenBox(k, mitOrt) {
    const wer = k.an || 'Claude',
      senden = ziel(k),
      box = el('div', {class: 'kbox km gs gs-' + k.stand + (k.ziel === 'gitlab' ? ' gl' : ''), 'data-id': k.id}),
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
              t => senden({aktion: 'antworten', text: t}),
              () => b.remove(),
              undefined,
              true
            );
          }
        },
        '↩ antworten'
      );
    if (offen) kn.append(antw(), ...fadenKnoepfe(k, senden));
    const er = k.erledigt
      ? el(
          'span',
          {},
          '· erledigt von ' +
            (k.erledigt.von === 'ich' ? 'dir' : k.erledigt.wer || wer) +
            ' ' +
            uhrzeit(k.erledigt.zeit)
        )
      : k.abgehakt
        ? el('span', {}, '· abgewartet ' + uhrzeit(k.abgehakt))
        : null;
    const gitlab = k.url
      ? el(
          'a',
          {class: 'ortlink', href: k.url, target: '_blank', rel: 'noopener', title: 'in GitLab öffnen'},
          'GitLab ↗'
        )
      : null;
    const agent = k.finding ? el('span', {class: 'badge b-agent'}, 'aus ' + (k.agent || 'Agent') + ' ' + k.finding) : null;
    const zu = k.zu
      ? el('span', {class: 'badge', title: ZU_TITEL}, '✎ zum GitLab-Kommentar')
      : null;
    const ort = !mitOrt
      ? null
      : k.fremd
        ? el('code', {title: 'Zeile im Stand von ' + k.fremd}, k.path ? k.path + (k.b ? ':' + k.b : '') : 'allgemein')
        : ortLink(k);
    const branch = k.fremd
      ? el('span', {class: 'badge b-fremd', title: 'Gespräch aus einem anderen Branch'}, k.fremd)
      : null;
    const badge = el('span', {class: 'badge s-' + k.stand}, werZeichen(k.wer), ' ' + standText(k));
    box.append(el('div', {class: 'kk'}, badge, branch, agent, zu, er, ort, gitlab, kn));
    if (k.zeile_text && k.problem)
      box.append(
        el(
          'div',
          {class: 'alt', title: 'die Zeile, als der Kommentar geschrieben wurde'},
          'damals: ' + k.zeile_text.trim()
        )
      );
    k.nachrichten.forEach(m => verlauf.append(nachrichtBox(k, m, wer, offen, senden)));
    box.append(verlauf);
    const sa = sieheAuch(k.see_also);
    if (sa) box.append(sa);
    if (offen && k.nachrichten.length > 1) box.append(el('div', {class: 'unten'}, antw())); // auch unten (lange Fäden)
    if (k.ziel === 'gitlab' && k.kommentar) angehaengt(box, ['k:' + k.kommentar], kn); // eigener, veröffentlicht
    return box;
  }
  const ZU_TITEL =
    'Wunsch an den Agenten zu diesem GitLab-Kommentar: er ändert den Kommentartext (als neuen Agent-Hinweis zum ' +
    'Übernehmen) und antwortet nur, wenn du nach einer Erklärung fragst – geht nicht nach GitLab';
  /** Schlüssel, unter denen Fäden an einem GitLab-Kommentar hängen (Faden.zu): Review-Kommentar k:<id>, Hinweis
   *  h:<key> – ein übernommener Hinweis gehört zu seinem Kommentar. */
  const zuSchluessel = {
    kommentar: k => ['k:' + k.id].concat(k.hinweis ? ['h:' + k.hinweis] : []),
    hinweis: h => ['h:' + h.key],
    diskussion: k => (k.kommentar ? ['k:' + k.kommentar] : [])
  };
  /** Fäden zu diesem GitLab-Kommentar unter die Box, dazu der Knopf „💬 an Agent“ in kn (neuer Faden mit zu). */
  function angehaengt(box, schluessel, kn) {
    const fs = faeden().filter(f => schluessel.includes(f.zu));
    if (fs.length) box.append(el('div', {class: 'anhang'}, ...fs.map(f => fadenBox(f, false))));
    if (!kn || nurLesen) return;
    const ag = agenten(),
      neu = an => t =>
        fadenAktion({aktion: 'neu', zu: schluessel[0], an, text: t}).then(sofortSenden);
    kn.append(
      el(
        'button',
        {
          title: ag.length ? ZU_TITEL : KEIN_AGENT,
          disabled: ag.length ? null : '',
          onclick: () => {
            const b = el('div', {class: 'kbox km'});
            let a = box.querySelector(':scope>.anhang');
            if (!a) box.append((a = el('div', {class: 'anhang'})));
            a.append(b);
            bearbeiten(
              b,
              '',
              neu(ag[0]),
              () => b.remove(),
              ag.slice(1).map(n => ['an ' + n, neu(n), ZU_TITEL]),
              true,
              'an ' + ag[0]
            );
          }
        },
        '💬 an Agent'
      )
    );
  }
  /** Knöpfe eines offenen Threads neben „antworten“: erledigt bzw. wieder öffnen (GitLab: nur lösbare), löschen
   *  (nur Fäden – eine GitLab-Diskussion löscht man in GitLab). */
  function fadenKnoepfe(k, senden) {
    const knopf = (aktion, text, title) => el('button', {title, onclick: () => senden({aktion})}, text);
    if (k.ziel !== 'gitlab')
      return [
        k.erledigt
          ? knopf('oeffnen', 'wieder öffnen')
          : knopf('erledigt', '✓ erledigt', 'Gespräch als erledigt markieren'),
        el(
          'button',
          {
            title: 'ganzes Gespräch löschen',
            onclick: e => {
              if (!confirm('Ganzes Gespräch löschen?')) return;
              const box = e.target.closest('.kbox');
              senden({aktion: 'loeschen'}).then(d => {
                if (!d || !d.ok) return;
                box.querySelectorAll('textarea').forEach(t => t.remove()); // offenes Feld hält den Faden nicht mehr
                zeichnen();
              });
            }
          },
          '🗑'
        )
      ];
    // GitLab: „☑ abwarten“ gibt den Ball ohne Antwort ab (nur lokal), erledigt wird in GitLab
    if (k.erledigt) return k.loesbar ? [knopf('oeffnen', 'wieder öffnen', 'in GitLab wieder öffnen')] : [];
    return [
      k.abgehakt
        ? knopf('aufhaken', '↺ doch dran', 'Abwarten zurücknehmen')
        : k.stand === 'dran'
          ? knopf('abhaken', '☑ abwarten', ABWARTEN_TITEL)
          : null,
      k.loesbar ? knopf('erledigt', '✓ in GitLab erledigt', 'in GitLab als erledigt markieren') : null
    ].filter(Boolean); // append() schriebe null als Text
  }
  const ABWARTEN_TITEL =
    'nichts zu tun: Ball abgeben, ohne zu antworten – schreibt danach jemand, bist du wieder dran; ' +
    'in GitLab bleibt die Diskussion offen';
  /** Klick auf das Zeichen in der Liste links: erledigen wie beim KI-Thread, eine GitLab-Diskussion gleich in GitLab
   *  (nur lösbare; nicht lösbare in „dran“ abwarten). Rückgabe null: in diesem Stand kein Klick. */
  function fadenErledigen(k, nurPruefen) {
    const gl = k.ziel === 'gitlab',
      aktion =
        (!gl || k.loesbar) && k.stand !== 'erledigt' ? 'erledigt' : gl && k.stand === 'dran' ? 'abhaken' : null;
    if (!aktion || nurPruefen)
      return aktion && TITEL_ERLEDIGEN[aktion === 'abhaken' ? 'abhaken' : gl ? 'gitlab' : 'faden'];
    return ziel(k)({aktion});
  }
  const TITEL_ERLEDIGEN = {faden: 'als erledigt markieren', gitlab: 'in GitLab erledigen', abhaken: '☑ abwarten'};
  /** Eine Nachricht im Verlauf: Kopf (wer, wann, ✓/✓✓ bzw. Entwurf mit ✎/🗑) und Text mit Code-Links. */
  function nachrichtBox(k, m, wer, offen, senden) {
    const ich = m.von === 'ich',
      entwurf = ich && !m.gesendet,
      mb = el('div', {class: 'msg ' + m.von + (entwurf ? ' entwurf' : '')});
    const haken = !ich
      ? null
      : entwurf
        ? el('span', {}, m.stufe ? statusTexte[m.stufe][0] : 'Entwurf')
        : k.ziel === 'gitlab'
          ? null
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
      el('b', {}, ich ? 'Du' : (m.von === 'claude' ? '🤖 ' : '') + (m.wer || wer)),
      el('span', {}, uhrzeit(m.gesendet || m.zeit)),
      haken
    );
    if (entwurf && offen)
      mk.append(
        el(
          'button',
          {onclick: () => bearbeiten(mb, m.text, t => senden({aktion: 'aendern', nid: m.id, text: t}))},
          '✎'
        ),
        el('button', {onclick: () => senden({aktion: 'loeschen', nid: m.id})}, '🗑')
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
        k.finding ? el('span', {class: 'badge b-agent'}, 'aus ' + (k.agent || 'Agent') + ' ' + k.finding) : null,
        mitOrt ? ortLink(k) : null,
        kn
      ),
      el('div', {class: 'kt'}, k.text)
    );
    const h = k.hinweis && review.hinweise.find(x => x.key === k.hinweis),
      sa = h && sieheAuch(h.see_also);
    if (sa) box.append(sa);
    angehaengt(box, zuSchluessel.kommentar(k), nurLesen || k.lesen || k.status === 'loeschen' ? null : kn);
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
        el('span', {class: 'badge b-agent'}, '🤖 ' + (h.agent || 'Agent') + ' ' + (h.finding || '')),
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
    angehaengt(box, zuSchluessel.hinweis(h), nurLesen || h.lesen || h.status === 'verworfen' ? null : kn);
    return box;
  }
  /** Box unter Zeile r (hinter schon eingefügten Boxen): inline über die ganze Breite, nebeneinander nur auf der Seite
   *  ihres Orts (b → rechts, nur a → links). ort {a, b} steht an der Zeile (data-ka/-kb) fürs Verschieben. */
  function einfuegen(r, inhalt, tab, ort) {
    let z = r;
    while (z.nextElementSibling && z.nextElementSibling.classList.contains('kr')) z = z.nextElementSibling;
    const sbs = tab.classList.contains('sbs'),
      td = el('td', {colspan: sbs ? 2 : 3}, inhalt),
      leer = () => el('td', {colspan: 2, class: 'kleer'}),
      links = ort.b == null && ort.a != null;
    const tr = el('tr', {class: 'kr'}, ...(!sbs ? [td] : links ? [td, leer()] : [leer(), td]));
    if (ort.a != null) tr.dataset.ka = ort.a;
    if (ort.b != null) tr.dataset.kb = ort.b;
    z.after(tr);
    return tr;
  }
  const sichtbar = tab => tab.classList.contains('inl') === document.body.classList.contains('inline');
  /** Zeile mit offenem Eingabefeld in der versteckten Tabelle (i schaltet nebeneinander/inline um): samt Feld und
   *  Text in die sichtbare Tabelle derselben Datei verschieben. */
  function feldMitnehmen(tr) {
    const tab = tr.closest('table'),
      d = tr.closest('.datei');
    if (!tab || !d || sichtbar(tab)) return;
    const ziel = [...d.querySelectorAll('table')].find(t => t !== tab && sichtbar(t)),
      ort = {a: tr.dataset.ka != null ? +tr.dataset.ka : null, b: tr.dataset.kb != null ? +tr.dataset.kb : null},
      r = ziel && zeileFinden(ziel, ort.a, ort.b),
      box = tr.querySelector('td:not(.kleer)');
    if (!r || !box) return;
    const neu = einfuegen(r, box.firstElementChild, ziel, ort); // Zeile selbst bleibt (Abbrechen entfernt sie)
    tr.replaceChildren(...neu.childNodes);
    neu.replaceWith(tr);
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
  /** Zeilen ab–b (neue Seite) einer Tabelle mit cls markieren: Faden an einem Bereich bzw. Bereich im Entwurf. */
  function bereichMarkieren(tab, ab, b, cls) {
    tab.querySelectorAll('tr[data-b]').forEach(r => {
      if (ab <= +r.dataset.b && +r.dataset.b <= b) r.classList.add(cls);
    });
  }
  function zeichnen() {
    // Kästen mit offenem Eingabefeld bleiben stehen (der Text darin soll nicht verloren gehen), alles andere wird neu
    // gezeichnet. Nach dem Schließen des Felds holt nachholen() den Kasten selbst nach.
    const aussen = e => {
      // äußerste Box: ein Feld in einem angehängten Faden hält die Box des Kommentars
      let b = e && e.closest('.kbox');
      while (b && b.parentElement && b.parentElement.closest('.kbox')) b = b.parentElement.closest('.kbox');
      return b;
    };
    const felder = [...document.querySelectorAll('.kbox textarea')].map(aussen).filter(Boolean);
    const bleibt = new Set(felder.map(b => b.dataset.id).filter(Boolean)),
      haelt = e => felder.some(b => e === b || e.contains(b));
    zeichnenWartet = felder.length > 0;
    document.querySelectorAll('tr.bereich').forEach(r => r.classList.remove('bereich'));
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
          einfuegen(r, mach(), tab, x);
          if (x.ab) bereichMarkieren(tab, x.ab, x.b, 'bereich');
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
    review.kommentare
      .filter(k => !k.antwort_auf)
      .forEach(k => {
        if (!platz(k, () => kommentarBox(k, false)) && !unter(k, () => kommentarBox(k, false)))
        allgDazu(k, () => kommentarBox(k, true));
    });
    const gezeigt = new Set(
      [
        ...review.kommentare.filter(k => !k.antwort_auf).flatMap(zuSchluessel.kommentar),
        ...(review.diskussionen || []).flatMap(zuSchluessel.diskussion),
        ...review.hinweise
          .filter(h => h.status === 'offen' || (review.zeigVerworfen && h.status === 'verworfen'))
          .flatMap(zuSchluessel.hinweis)
      ]
    ); // Fäden an diesen Kommentaren stehen in deren Box (angehaengt)
    faeden().filter(k => !gezeigt.has(k.zu)).forEach(k => {
      if (!platz(k, () => fadenBox(k, false)) && !unter(k, () => fadenBox(k, false)))
        allgDazu(k, () => fadenBox(k, true));
    });
    if (review.zeigFremde) (review.faeden_fremd || []).forEach(k => allgDazu(k, () => fadenBox(k, true)));
    (review.diskussionen || []).forEach(k => {
      if (!platz(k, () => fadenBox(k, false)) && !unter(k, () => fadenBox(k, false)))
        allgDazu(k, () => fadenBox(k, true));
    });
    review.hinweise
      .filter(h => h.status === 'offen' || (review.zeigVerworfen && h.status === 'verworfen'))
      .forEach(h => {
        if (!platz(h, () => hinweisBox(h, false)) && !unter(h, () => hinweisBox(h, false)))
          allgDazu(h, () => hinweisBox(h, true));
      });
    felder.forEach(b => b.closest('tr.kr') && feldMitnehmen(b.closest('tr.kr')));
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
    abschliessenStand();
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
    sessionKnopf = document.getElementById('starten'),
    promptKnopf = document.getElementById('prompt'),
    abmeldenKnopf = document.getElementById('abmelden');
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
    promptKnopf.hidden = feedbackKnopf.hidden;
    feedbackKnopf.disabled = !e;
    const fw = 'An Agent senden';
    feedbackKnopf.textContent = e ? fw + ' (' + e + ')' : fw;
    sessionKnopf.hidden = !review.todo || !!review.horcht;
    abmeldenKnopf.hidden = !review.horcht;
    document.title = (neu ? '(' + neu + ') ' : '') + seitenTitel;
  }
  function vorher(w) {
    try {
      if (w !== undefined) localStorage.promptVorher = w ? 1 : '';
      return !!localStorage.promptVorher;
    } catch (_) {
      return false;
    }
  } // „Prompt vor dem Senden zeigen“, bleibt gespeichert
  const WEGE = {
    abholen: () => 'beim Abholen (agent feedback bzw. horchen)',
    wartet: () => 'gesendet, noch nicht abgeholt – so bekommt es der Agent beim Abholen',
    horchen: p => 'über „agent horchen“ an ' + (p.wer || 'die Session'),
    feedback: () => 'über „agent feedback“',
    start: p => 'als Startprompt für ' + (p.wer || 'den Agenten'),
    todo: () => 'als Prompt im todo-Eintrag'
  };
  function promptDialog(prompts, titel, weiter) {
    // prompts: [{zeit, weg, wer, text}]; weiter: „senden“ (Vorschau), sonst nur schließen
    const d = el('dialog', {class: 'prompt-dialog'}),
      haken = el('input', {type: 'checkbox'});
    haken.checked = vorher();
    haken.addEventListener('change', () => vorher(haken.checked));
    const zu = () => d.close();
    d.addEventListener('close', () => d.remove());
    d.append(
      el('div', {class: 'pd-kopf'}, titel),
      ...prompts.map((p, i) =>
        el(
          'details',
          {class: 'pd-eintrag', open: i === 0 ? '' : null},
          el('summary', {}, (p.zeit ? App.uhrzeit(p.zeit) + ' · ' : '') + (WEGE[p.weg] || (() => p.weg))(p)),
          el('pre', {}, p.text)
        )
      ),
      el(
        'div',
        {class: 'pd-unten'},
        el('label', {class: 'sofort', title: '„An Agent senden“ zeigt erst, was der Agent bekommt'}, haken, ' vor dem Senden zeigen'),
        el('button', {onclick: zu}, weiter ? 'abbrechen' : 'schließen'),
        weiter
          ? el('button', {class: 'pd-senden', onclick: () => {
              zu();
              weiter();
            }}, 'senden')
          : null
      )
    );
    document.body.append(d);
    d.showModal();
  }
  function senden(geprueft) {
    if (!feedbackKnopf) return;
    if (geprueft !== true && vorher()) {
      post('/api/gespraech', {aktion: 'vorschau'}).then(d => {
        if (!d.ok) return senden(true); // kein Agent erreichbar: senden meldet, wie es weitergeht
        App.melden('');
        promptDialog(d.prompts, 'Vorschau – das bekommt der Agent (Stand jetzt)', () => senden(true));
      });
      return;
    }
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
    if (!mitReview)
      feedbackKnopf.before(el('label', {class: 'sofort', title: SOFORT_TITEL}, sofortHaken(), ' sofort senden'));
    feedbackKnopf.addEventListener('click', senden);
    promptKnopf.addEventListener('click', () =>
      post('/api/gespraech', {aktion: 'prompt'}).then(d =>
        d.ok ? promptDialog(d.prompts, 'Zuletzt an den Agenten zugestellt (neueste zuerst)') : App.melden(d.text || '')
      )
    );
    abmeldenKnopf.addEventListener('click', () =>
      post('/api/gespraech', {aktion: 'abmelden'}).then(d => {
        App.melden(d.text || '');
        if (d.review) {
          Object.assign(review, d.review);
          zeichnen();
        } else gsStand();
      })
    );
    sessionKnopf.addEventListener('click', () => {
      sessionKnopf.disabled = true;
      post('/api/gespraech', {aktion: 'starten'}).then(d => {
        sessionKnopf.disabled = false;
        App.melden(d.text || '');
      });
    });
  }
  const KEIN_AGENT =
    'Kein Agent eingerichtet: [agenten] in der Einstellung oder „merge-train agent horchen“ in einer Session';
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
            KEIN_AGENT
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
      fremde = (review.faeden_fremd || []).length,
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
          fremde
            ? el(
                'button',
                {
                  title:
                    'Gespräche, die zu einem anderen Branch als ' + (review.branch || '?') + ' gehören (nur lesen)',
                  onclick: () => {
                    review.zeigFremde = zeigFremde(!review.zeigFremde);
                    zeichnen();
                  }
                },
                review.zeigFremde ? 'Fäden anderer Branches ausblenden' : fremde + ' Fäden aus anderen Branches zeigen'
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
  // Neuer Entwurf an einer Zeile; Umschalt-Klick auf eine zweite Zeile derselben Tabelle macht daraus einen Bereich.
  let entwurf = null;
  function bereichAufziehen(tab, tr, b) {
    if (!entwurf || !entwurf.zr.isConnected || entwurf.tab !== tab || entwurf.erste == null || b == null) return false;
    if (mitReview) {
      App.melden('Bereiche gehen bisher nur bei Fragen an Agenten (lokal), nicht bei Review-Kommentaren');
      return true;
    }
    const ort = entwurf.ort,
      ab = Math.min(entwurf.erste, b);
    ort.b = Math.max(entwurf.erste, b);
    if (ab < ort.b) ort.ab = ab;
    else delete ort.ab;
    ort.a = null;
    tab.querySelectorAll('tr.bereich-neu').forEach(r => r.classList.remove('bereich-neu'));
    bereichMarkieren(tab, ab, ort.b, 'bereich-neu');
    let z = zeileFinden(tab, null, ort.b) || tr;
    while (z.nextElementSibling && z.nextElementSibling.classList.contains('kr') && z.nextElementSibling !== entwurf.zr)
      z = z.nextElementSibling;
    z.after(entwurf.zr);
    return true;
  }
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
    if (e.shiftKey && bereichAufziehen(tab, tr, b)) return;
    const box = el('div', {class: 'kbox km'}),
      zr = einfuegen(tr, box, tab, {a, b}),
      ort = {datei: n, a, b},
      weg = () => document.querySelectorAll('tr.bereich-neu').forEach(r => r.classList.remove('bereich-neu'));
    weg();
    entwurf = {tab, zr, ort, erste: b};
    bearbeiten(
      box,
      '',
      neuSpeichern(ort),
      () => {
        weg();
        zr.remove();
      },
      anKnoepfe(ort),
      agenten().length > 0
    );
  });
  const abschliessenKnopf = document.getElementById('abschliessen');
  // Urteil des Reviews (Split-Knopf „▾“ rechts): kommentieren ist der Standard, genehmigen und ändern lassen gelten nur
  // für das nächste Abschließen (nicht gespeichert – ein versehentliches Genehmigen soll nicht hängen bleiben)
  const URTEILE = {
    kommentieren: ['Review abschließen → GitLab', 'Kommentieren', 'nur die Kommentare senden (Standard)'],
    genehmigen: ['Genehmigen → GitLab', 'Genehmigen', 'Kommentare senden und den MR genehmigen (Approve) – auch ohne Kommentar'],
    aendern: ['Ändern lassen → GitLab', 'Ändern lassen', 'Kommentare senden und Änderungen anfordern (Request changes)']
  };
  let urteil = 'kommentieren';
  function urteilSetzen(u) {
    urteil = u;
    abschliessenKnopf.textContent = URTEILE[u][0];
    abschliessenKnopf.parentNode.classList.toggle('u-aendern', u === 'aendern');
    abschliessenStand();
  }
  if (abschliessenKnopf) {
    const menue = el('div', {class: 'urteilmenue', hidden: true}),
      auf = el('button', {class: 'urteilauf', title: 'Urteil wählen: kommentieren, genehmigen, ändern lassen'}, '▾'),
      split = el('span', {class: 'split'});
    for (const [u, [, name, titel]] of Object.entries(URTEILE)) {
      const b = el('button', {title: titel}, name);
      b.dataset.u = u;
      b.addEventListener('click', () => {
        menue.hidden = true;
        urteilSetzen(u);
      });
      menue.append(b);
    }
    auf.addEventListener('click', e => {
      e.stopPropagation();
      menue.hidden = !menue.hidden;
      menue.querySelectorAll('button').forEach(b => b.classList.toggle('akt', b.dataset.u === urteil));
    });
    document.addEventListener('click', e => {
      if (!menue.hidden && !split.contains(e.target)) menue.hidden = true;
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') menue.hidden = true;
    });
    abschliessenKnopf.replaceWith(split);
    split.append(abschliessenKnopf, auf, menue);
    if (abschliessenKnopf.hidden) split.hidden = true;
    const d = el('input', {type: 'checkbox'});
    d.checked = direkt();
    d.addEventListener('change', () => {
      direkt(d.checked);
      abschliessenStand();
      kommentarListe(); // Filter „Entwurf in GitLab“ nur ohne direkt
    });
    split.after(
      el('label', {class: 'sofort', title: DIREKT_TITEL}, d, ' direkt veröffentlichen'),
      el('label', {class: 'sofort', title: SOFORT_TITEL}, sofortHaken(), ' sofort senden')
    );
  }
  /** „Review abschließen“ nur, wenn es lokale Entwürfe (staged) gibt – mit Urteil (genehmigen …) immer. */
  function abschliessenStand() {
    if (!abschliessenKnopf || abschliessenKnopf.dataset.laeuft) return;
    const inGitlab = direkt() ? review.in_gitlab || 0 : 0;
    abschliessenKnopf.disabled = !review.ausstehend && !inGitlab && urteil === 'kommentieren';
    abschliessenKnopf.title =
      urteil !== 'kommentieren'
        ? URTEILE[urteil][2] +
          (review.ausstehend ? ' (' + review.ausstehend + ' lokale Entwürfe' + (direkt() ? ', veröffentlicht)' : ' als Entwürfe)') : '')
        : review.ausstehend || inGitlab
        ? (review.ausstehend ? review.ausstehend + ' lokale Entwürfe ' : '') +
          (inGitlab ? (review.ausstehend ? 'und ' : '') + inGitlab + ' Entwürfe in GitLab ' : '') +
          (direkt()
            ? 'in GitLab veröffentlichen (eine Benachrichtigung)'
            : 'als Entwürfe („Review starten“) in den MR übertragen – veröffentlicht wird erst in GitLab')
        : 'keine lokalen Entwürfe – nichts zu übertragen';
  }
  if (abschliessenKnopf)
    abschliessenKnopf.addEventListener('click', () => {
      abschliessenKnopf.dataset.laeuft = 1;
      abschliessenKnopf.disabled = true;
      App.melden(
        urteil !== 'kommentieren'
          ? URTEILE[urteil][1] + ' in GitLab …'
          : direkt()
            ? 'veröffentlicht in GitLab …'
            : 'überträgt Entwürfe nach GitLab …'
      );
      post('/api/abschliessen', {direkt: direkt() ? 1 : '', urteil}).then(d => {
        delete abschliessenKnopf.dataset.laeuft;
        abschliessenKnopf.disabled = false;
        if (d.ok) urteilSetzen('kommentieren');
        else abschliessenStand();
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
  // hat sich etwas geändert → neu laden (beobachten.js rahmt danach das Neue ein). Seite im Hintergrund neu gebaut
  // (z. B. MR-Daten über den Zug) → ebenfalls neu laden
  // Seite neu laden (mit Meldung danach), sobald kein Eingabefeld offen ist
  function neuLaden(meldung, alt) {
    App.serverLed('neu');
    if (document.querySelector('textarea')) return;
    try {
      sessionStorage.meldung = meldung;
      if (alt !== undefined) sessionStorage.beobachtetAlt = alt;
    } catch (_) {}
    location.reload();
  }
  let seite; // zuletzt gebaute Seite des Waggons (beim ersten Abfragen gemerkt)
  function pruefen() {
    fetch('/api/stand?' + waggonAbfrage() + '&sha=' + encodeURIComponent(waggon.sha || ''))
      .then(r => r.json())
      .then(d => {
        if (d.server) App.serverStandSetzen(d.server);
        if (d.meldung) App.melden(d.meldung);
        if (d.version && waggon.version && d.version !== waggon.version)
          return neuLaden('merge-train wurde aktualisiert – Seite neu geladen');
        if (d.veraltet) return neuLaden('Änderung im Repo – Seite neu geladen', waggon.sha || '');
        if (seite === undefined) seite = d.seite;
        else if (d.seite && d.seite !== seite) return neuLaden('Seite im Hintergrund neu gebaut (MR-Daten) – neu geladen');
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
  Object.assign(App, {
    review,
    zeichnen,
    STAENDE,
    werZeichen,
    direkt,
    fadenErledigen,
    kommentarAktion,
    reviewLaden: laden
  });
})();
