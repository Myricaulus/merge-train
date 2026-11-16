// Gemeinsamer Rahmen der Seiten-Skripte, auf allen Seiten zuerst geladen. Jede Datei läuft in ihrer eigenen Funktion
// und sieht die anderen nur über App: was sie bereitstellt, trägt sie hier ein (steht oben in der jeweiligen Datei). MR
// kommt vom Server (Seite davor) und heißt hier App.waggon.
const App = {
  waggon: MR,
  kann: MR.kann || {},
  meldung: document.getElementById('meldung'),
  serverWeg: 'merge-train-Server nicht erreichbar – versucht es weiter …',
  /** Meldung im Kopf. toasts.js (Seiten mit Diff) ersetzt das durch Toasts. */
  melden(text) {
    App.meldung.textContent = text || '';
  }
};
/** Element bauen: el('a', {class: 'x', onclick: f}, 'Text', kind, …) */
App.el = (tag, attrs, ...kinder) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v != null) e.setAttribute(k, v);
  }
  for (const k of kinder) {
    if (k == null || k === false) continue;
    e.append(k instanceof Node ? k : String(k));
  }
  return e;
};
/** e sichtbar machen: zugeklappte <details> darum öffnen (Dateibox …; Chromium meldet Rechtecke auch für Zugeklapptes,
 *  scrollIntoView allein zeigt dann nichts) und eine ausgefilterte Datei wieder zeigen (bis zum nächsten Filtern). */
App.aufdecken = e => {
  const d = e.closest('.datei.ausgefiltert');
  if (d) {
    d.classList.remove('ausgefiltert');
    let a = document.querySelector('#liste a[href="#' + d.id + '"]'); // ihr Link und die Ordner-Zeile darüber
    a?.classList.remove('ausgefiltert');
    while (a && a.tagName !== 'DIV') a = a.previousElementSibling;
    a?.classList.remove('ausgefiltert');
  }
  for (let d = e.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
};
/** Uhrzeit (heute) bzw. Datum und Uhrzeit aus einem ISO-Zeitpunkt */
App.uhrzeit = iso => {
  if (!iso) return '';
  const d = new Date(iso),
    hm = d.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
  return d.toDateString() === new Date().toDateString()
    ? hm
    : d.toLocaleDateString('de-DE', {day: '2-digit', month: '2-digit'}) + ' ' + hm;
};
