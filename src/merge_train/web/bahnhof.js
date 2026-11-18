// Güterbahnhof: Leitstand-Knöpfe der eingeschalteten Quellen. Der Zug kommt aus /zug.js (gemischt, ohne
// GitLab-Anfrage); GitLab wird nur auf Knopfdruck gefragt (data-g, auch „⇣ lokal aktualisieren“/„⇡ pushen“ in der Meldung zum
// abweichenden Stand), danach holt zugHolen den Zug neu bzw. lädt bei neu_laden die Seite. Lokal (data-l)
// lädt zug.js neu. Holt der Server dabei die Läufe des Myrlings im Hintergrund (nachladen), fragt die Seite den Zug
// noch einmal, sobald sie da sind. Braucht von App: waggon, melden, zugSetzen, reviewLaden (nur Diff-Seiten). Stellt bereit: zugHolen.
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
  document.querySelectorAll('button[data-g]').forEach(b => {
    if (b.dataset.g === 'mrdaten' && (!waggon.id || /^(projekt|myrling):/.test(waggon.id))) b.hidden = true;
    const bh = document.querySelector('.szene');
    b.addEventListener('click', () => {
      if (b.dataset.frage && !confirm(b.dataset.frage)) return; // z. B. Force-Push
      b.disabled = true;
      App.melden(b.dataset.meldung || 'frage GitLab …');
      bh.classList.add('laedt'); // Schüttgut rieselt, solange GitLab antwortet
      fetch('/api/gitlab', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({aktion: b.dataset.g, mr: waggon.id, k: waggon.k})
      })
        .then(r => r.json())
        .then(d => {
          b.disabled = false;
          bh.classList.remove('laedt');
          if (d.ok && (d.neu_laden || (b.dataset.g === 'mrdaten' && !App.reviewLaden))) {
            try {
              sessionStorage.meldung = d.text || ''; // erst nach dem Neuladen melden – sonst steht sie zweimal in der Glocke
            } catch (_) {}
            location.reload();
            return;
          }
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
