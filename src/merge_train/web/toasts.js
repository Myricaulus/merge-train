// Diff-Seiten: Toasts statt Meldungszeile (10 s, wegklickbar) und 🔔 mit den letzten 50 Meldungen (im Browser gemerkt).
// Braucht von App: el, uhrzeit, meldung, serverWeg. Ersetzt: melden.
(() => {
  const {el} = App;
  // Toasts: Meldungen des Servers (alles, was in #meldung landet, außer Fortschritt „… “ und „Server weg“) 10 s gut
  // sichtbar, wegklickbar; die letzten 50 merkt sich der Browser für den Knopf „Nachrichten“.
  const toastBox = el('div', {id: 'toasts'}),
    nachrichtenKnopf = el('button', {id: 'nachrichten', title: 'letzte Meldungen von merge-train'}, '🔔');
  document.body.append(toastBox, nachrichtenKnopf);
  function meldungsVerlauf(neu) {
    let v = [];
    try {
      v = JSON.parse(localStorage.meldungen || '[]');
    } catch (_) {}
    if (neu) {
      v.unshift(neu);
      v = v.slice(0, 50);
      try {
        localStorage.meldungen = JSON.stringify(v);
      } catch (_) {}
    }
    return v;
  }
  let ungelesen = 0;
  function zahlZeigen() {
    nachrichtenKnopf.dataset.n = ungelesen || '';
    nachrichtenKnopf.classList.toggle('neu', ungelesen > 0);
  }
  function toast(text) {
    const t = el(
      'div',
      {
        class:
          'toast' +
          (/fehler|abgelehnt|ungültig|nicht (erreichbar|abrufbar|gefunden|möglich)|startet nicht|gibt es nicht/i.test(
            text
          )
            ? ' warn'
            : '')
      },
      el('span', {}, text),
      el('button', {title: 'schließen', onclick: () => t.remove()}, '✕')
    );
    toastBox.prepend(t);
    setTimeout(() => {
      t.classList.add('weg');
      setTimeout(() => t.remove(), 400);
    }, 10000);
    meldungsVerlauf({zeit: new Date().toISOString(), text, seite: document.title.replace(/^\(\d+\) /, '')});
    ungelesen++;
    zahlZeigen();
  }
  // Meldungen werden Toasts – außer leeren, Fortschritt („… “) und „Server weg“: die bleiben im Kopf stehen
  App.melden = text => {
    const t = String(text || '').trim();
    if (!t || t === App.serverWeg || /…$|\.\.\.$/.test(t)) {
      App.meldung.textContent = text || '';
      return;
    }
    App.meldung.textContent = '';
    toast(t);
  };
  nachrichtenKnopf.addEventListener('click', e => {
    e.stopPropagation();
    let p = document.getElementById('nachrichten-liste');
    if (p) {
      p.remove();
      return;
    }
    ungelesen = 0;
    zahlZeigen();
    const v = meldungsVerlauf();
    p = el(
      'div',
      {id: 'nachrichten-liste'},
      el(
        'div',
        {class: 'nl-kopf'},
        el('b', {}, 'Letzte Meldungen'),
        v.length
          ? el(
              'button',
              {
                onclick: () => {
                  try {
                    localStorage.removeItem('meldungen');
                  } catch (_) {}
                  p.remove();
                }
              },
              'leeren'
            )
          : null
      ),
      ...(v.length
        ? v.map(m =>
            el(
              'div',
              {class: 'nl-e'},
              el('span', {class: 'sub'}, App.uhrzeit(m.zeit) + (m.seite ? ' · ' + m.seite : '')),
              el('div', {}, m.text)
            )
          )
        : [el('div', {class: 'sub'}, 'noch keine Meldungen')])
    );
    document.body.append(p);
  });
  document.addEventListener('click', e => {
    const p = document.getElementById('nachrichten-liste');
    if (p && !p.contains(e.target)) p.remove();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      const p = document.getElementById('nachrichten-liste');
      if (p) p.remove();
    }
  });
})();
