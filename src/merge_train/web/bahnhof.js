// Güterbahnhof: Leitstand-Knöpfe der eingeschalteten Quellen. Der Zug kommt aus /zug.js (gemischt, ohne GitLab-Anfrage);
// GitLab wird nur auf Knopfdruck gefragt (data-g), danach holt zugHolen den Zug neu. Lokal (data-l) lädt zug.js neu.
// Braucht von App: waggon, melden, zugSetzen, reviewLaden (nur Diff-Seiten). Stellt bereit: zugHolen.
(() => {
  const {waggon} = App;
  const mitGitlab = !!document.querySelector('#bahnhof button[data-g]');
  function mrZeitZeigen(z) {
    const t = document.getElementById('bhzeit');
    if (t && mitGitlab) t.textContent = z ? 'MRs vom ' + z : 'MRs noch nicht geholt';
  }
  function zugHolen() {
    return fetch('/api/zug?akt=' + encodeURIComponent(waggon.id))
      .then(r => r.json())
      .then(z => {
        App.zugSetzen(z.wagen || []);
        mrZeitZeigen(z.zeit);
      })
      .catch(() => {});
  }
  mrZeitZeigen((window.MR_ZUG || {}).zeit);
  try {
    if (sessionStorage.meldung) {
      App.melden(sessionStorage.meldung);
      sessionStorage.removeItem('meldung');
    }
  } catch (_) {} // Meldung von „↻ MR-Daten“ über das Neuladen
  document.querySelectorAll('#bahnhof button[data-g]').forEach(b => {
    if (b.dataset.g === 'mrdaten' && (!waggon.id || waggon.id.startsWith('projekt:'))) b.hidden = true;
    const bh = document.querySelector('.szene');
    b.addEventListener('click', () => {
      b.disabled = true;
      App.melden('frage GitLab …');
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
          App.melden(d.text || '');
          if (!d.ok) return;
          if (b.dataset.g === 'mrdaten' && (d.neu_laden || !App.reviewLaden)) {
            try {
              sessionStorage.meldung = d.text || '';
            } catch (_) {}
            location.reload();
            return;
          }
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
  // Himmel rutscht weg (#kopf klebt bei top:-96px): Kulisse um bis zu 36 px nach unten schieben, Horizont landet am Unterrand
  {
    const k = document.getElementById('kopf'),
      sz = document.querySelector('.szene');
    if (k && sz) {
      const f = () => {
        const s = Math.min(96, Math.max(0, -k.getBoundingClientRect().top));
        sz.style.setProperty('--hub', ((s * 36) / 96).toFixed(1) + 'px');
      };
      addEventListener('scroll', f, {passive: true});
      f();
    }
  }
  App.zugHolen = zugHolen;
})();
