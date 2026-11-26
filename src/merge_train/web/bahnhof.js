// Güterbahnhof: Leitstand-Knöpfe der eingeschalteten Quellen. Der Zug kommt aus /zug.js (gemischt, ohne
// GitLab-Anfrage); GitLab wird nur auf Knopfdruck gefragt (data-g, auch „⇣ lokal aktualisieren“/„⇡ pushen“ in der Meldung zum
// abweichenden Stand), danach holt zugHolen den Zug neu bzw. bei neu_laden den neuen Stand (neuHolen). Lokal (data-l):
// zug.js. Holt der Server dabei die Läufe des Myrlings im Hintergrund (nachladen), fragt die Seite den Zug
// noch einmal, sobald sie da sind. „MR erstellen“ (lokale Waggons): Rückfrage im Dialog, dann zum MR.
// Braucht von App: waggon, el, serverWeg, melden, zugSetzen, neuHolen, reviewLaden (nur Diff-Seiten). Stellt bereit: zugHolen.
(() => {
  const {waggon} = App;
  const mitGitlab = !!document.querySelector('#bahnhof button[data-g]');
  function mrZeitZeigen(z) {
    const t = document.getElementById('bhzeit');
    if (t && mitGitlab) t.textContent = z ? 'MRs vom ' + z : 'MRs noch nicht geholt';
  }
  function zugHolen(warten) {
    return fetch('/api/zug?akt=' + encodeURIComponent(waggon.id) + (warten ? '&warten=1' : ''))
      .then(r => r.json())
      .then(z => {
        App.zugSetzen(z.wagen || []);
        mrZeitZeigen(z.zeit);
      })
      .catch(() => {});
  }
  mrZeitZeigen((window.MR_ZUG || {}).zeit);
  if ((window.MR_ZUG || {}).nachladen) zugHolen(true);
  try {
    if (sessionStorage.meldung) {
      App.melden(sessionStorage.meldung);
      sessionStorage.removeItem('meldung');
    }
  } catch (_) {} // Meldung von „↻ MR-Daten“ über das Neuladen
  document.querySelectorAll('button[data-g="mrdaten"]').forEach(b => {
    if (!waggon.id || /^(projekt|myrling):/.test(waggon.id)) b.hidden = true;
  });
  function gitlabPost(daten) {
    return fetch('/api/gitlab', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...daten, mr: waggon.id, k: waggon.k})
    }).then(r => r.json());
  }
  // ein Handler für alle data-g-Knöpfe, auch die in der Meldung über den Diffs (kommt beim Tausch neu)
  document.addEventListener('click', e => {
    const b = e.target.closest('button[data-g]');
    if (!b || b.disabled) return;
    const bh = document.querySelector('.szene');
    if (b.dataset.frage && !confirm(b.dataset.frage)) return; // z. B. Force-Push
    b.disabled = true;
    App.melden(b.dataset.meldung || 'frage GitLab …');
    bh.classList.add('laedt'); // Schüttgut rieselt, solange GitLab antwortet
    gitlabPost({aktion: b.dataset.g})
      .then(d => {
        b.disabled = false;
        bh.classList.remove('laedt');
        if (d.ok && (d.neu_laden || (b.dataset.g === 'mrdaten' && !App.reviewLaden))) return App.neuHolen(d.text);
        App.melden(d.text || '');
        if (!d.ok) return;
        if (b.dataset.g === 'mrdaten') App.reviewLaden(); // Seite unverändert: nur Kommentare/Entwürfe auffrischen
        zugHolen();
      })
      .catch(() => {
        b.disabled = false;
        bh.classList.remove('laedt');
        App.melden('merge-train-Server nicht erreichbar');
      });
  });
  // „MR erstellen“ (lokaler Waggon, docs/ein-waggon.md Schritt 2): erst fragt der Server GitLab nach einem MR zum Branch
  // (gibt es einen, übernimmt er ihn), sonst Rückfrage mit Ziel-Branch, Titel, Beschreibung und was gepusht wird
  const mrKnopf = document.getElementById('mrerstellen');
  function mrFertig(d) {
    if (!d.ok) return App.melden(d.text || 'MR nicht erstellt');
    try {
      sessionStorage.meldung = d.text || '';
    } catch (_) {}
    location.href = d.url; // zum MR: ist der Branch ausgecheckt, ist es jetzt derselbe Waggon
  }
  function mrDialog(v) {
    const {el} = App,
      ziel = el('select', {class: 'md-ziel'}, ...v.ziele.map(z => el('option', {value: z, selected: z === v.ziel ? '' : null}, z))),
      titel = el('input', {type: 'text', class: 'md-titel', value: v.titel}),
      text = el('textarea', {class: 'md-text', rows: 6}, v.beschreibung),
      entwurf = el('input', {type: 'checkbox', class: 'md-entwurf'}),
      erstellen = el('button', {class: 'pd-senden md-erstellen', disabled: v.hindernisse.length ? '' : null}, 'erstellen'),
      fehler = el('li', {class: 'warn', hidden: ''}),
      d = el(
        'dialog',
        {class: 'prompt-dialog mr-dialog'},
        el('div', {class: 'pd-kopf'}, 'Merge-Request erstellen'),
        el('label', {}, 'Branch ', el('code', {}, v.quelle), ' → ', ziel, ` · ${v.commits} Commit(s)`),
        el('label', {}, 'Titel', titel),
        el('label', {}, 'Beschreibung', text),
        el('label', {class: 'md-haken'}, entwurf, ' als Entwurf (Draft)'),
        el(
          'ul',
          {class: 'md-hinweise'},
          v.push_text ? el('li', {}, v.push_text) : null,
          ...v.warnungen.map(w => el('li', {class: 'warn'}, '⚠ ' + w)),
          ...v.hindernisse.map(h => el('li', {class: 'warn'}, '✗ ' + h)),
          fehler
        ),
        el('div', {class: 'pd-unten'}, el('button', {onclick: () => zu()}, 'abbrechen'), erstellen)
      ),
      zu = () => {
        d.close();
        d.remove();
      };
    erstellen.addEventListener('click', () => {
      erstellen.disabled = true;
      App.melden('erstellt den MR …');
      gitlabPost({aktion: 'mrerstellen', ziel: ziel.value, titel: titel.value, beschreibung: text.value, entwurf: entwurf.checked})
        .then(r => {
          erstellen.disabled = false;
          if (!r.ok) {
            fehler.hidden = false;
            fehler.textContent = '✗ ' + (r.text || 'MR nicht erstellt');
            return;
          }
          zu();
          mrFertig(r);
        })
        .catch(() => {
          erstellen.disabled = false;
          App.melden(App.serverWeg);
        });
    });
    document.body.append(d);
    d.showModal();
    titel.focus();
  }
  if (mrKnopf)
    mrKnopf.addEventListener('click', () => {
      mrKnopf.disabled = true;
      App.melden('frage GitLab nach einem MR zum Branch …');
      gitlabPost({aktion: 'mrplanen'})
        .then(d => {
          mrKnopf.disabled = false;
          if (d.ok && d.vorschlag) {
            App.melden('');
            mrDialog(d.vorschlag);
          } else mrFertig(d);
        })
        .catch(() => {
          mrKnopf.disabled = false;
          App.melden(App.serverWeg);
        });
    });
  // Himmel rutscht weg (#kopf klebt bei top:-96px): Kulisse um bis zu 36 px nach unten schieben, Horizont landet am
  // Unterrand
  {
    const k = document.getElementById('kopf'),
      sz = document.querySelector('.szene');
    if (k && sz) {
      let hub = null;
      const f = () => {
        const s = Math.min(96, Math.max(0, -k.getBoundingClientRect().top)),
          h = ((s * 36) / 96).toFixed(1);
        if (h !== hub) sz.style.setProperty('--hub', (hub = h) + 'px'); // nur bei Änderung: weiter unten steht sie fest
      };
      addEventListener('scroll', f, {passive: true});
      f();
    }
  }
  App.zugHolen = zugHolen;
})();
