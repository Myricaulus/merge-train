// Zeichnungen im Kopf: die Lok (SVG-Text, zug.js hängt sie an den Zug) und die Verladeanlage des Güterbahnhofs
// (Gebäude, Förderband bis über den vordersten Wagen, Gleis – in <svg id="anlage">).
// Braucht von App: –. Stellt bereit: lokSvg, anlageZeichnen.
(() => {
  function lokSvg() {
    // bayerische S 3/6 (Vorbild 3673), Fahrtrichtung rechts; lokale Schiene bei y=70
    const gr = '#2f6b45',
      dk = '#1d4630',
      sw = '#1b1b1b',
      ms = '#d8cfa4';
    const rad = (cx, cy, r) => {
      let t = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${gr}" stroke="#e9e4cf" stroke-width="1.4"/>`;
      for (let k = 0; k < 8; k++) {
        const w = (k * Math.PI) / 4;
        const x2 = (cx + Math.cos(w) * (r - 1.5)).toFixed(1),
          y2 = (cy + Math.sin(w) * (r - 1.5)).toFixed(1);
        t += `<line x1="${cx}" y1="${cy}" x2="${x2}" y2="${y2}" stroke="#e9e4cf" stroke-width=".7"/>`;
      }
      return t + `<circle cx="${cx}" cy="${cy}" r="2.2" fill="${ms}"/>`;
    };
    return `<g class="dampf"><circle cx="150" cy="2" r="4"/><circle cx="138" cy="-3" r="5.5"/>
 <circle cx="123" cy="-6" r="7"/></g>
 <rect x="0" y="27" width="50" height="29" rx="2" fill="${gr}" stroke="${dk}"/>
 <rect x="2" y="21" width="46" height="7" rx="2" fill="${sw}"/>
 <line x1="6" y1="33" x2="44" y2="33" stroke="${ms}" stroke-width=".8"/>
 <line x1="6" y1="51" x2="44" y2="51" stroke="${ms}" stroke-width=".8"/>
 <rect x="50" y="49" width="6" height="3" fill="${sw}"/>
 <rect x="53" y="10" width="30" height="5" rx="2" fill="${dk}"/>
 <rect x="55" y="14" width="26" height="42" fill="${gr}" stroke="${dk}"/>
 <rect x="60" y="19" width="13" height="12" rx="2" fill="#bcd3df" stroke="${sw}" stroke-width=".8"/>
 <rect x="80" y="21" width="92" height="25" rx="12" fill="${gr}" stroke="${dk}"/>
 <rect x="80" y="38" width="22" height="18" fill="${gr}" stroke="${dk}"/>
 <line x1="102" y1="22" x2="102" y2="45" stroke="${ms}"/><line x1="127" y1="22" x2="127" y2="45" stroke="${ms}"/>
 <line x1="152" y1="22" x2="152" y2="45" stroke="${ms}"/>
 <rect x="111" y="14" width="13" height="9" rx="4" fill="${gr}" stroke="${dk}"/>
 <rect x="135" y="15" width="11" height="8" rx="4" fill="${gr}" stroke="${dk}"/>
 <rect x="157" y="9" width="9" height="13" fill="${gr}" stroke="${dk}"/>
 <rect x="155" y="6" width="13" height="4" rx="1" fill="${sw}"/>
 <rect x="168" y="22" width="11" height="24" fill="${sw}"/><polygon points="179,22 192,34 179,46" fill="${sw}"/>
 <circle cx="186" cy="20" r="2.5" fill="${ms}"/><rect x="184" y="21" width="4" height="5" fill="${sw}"/>
 <line x1="78" y1="48" x2="190" y2="48" stroke="${sw}" stroke-width="3"/>
 <rect x="186" y="49" width="6" height="8" fill="#7a1e1e"/><rect x="192" y="51" width="6" height="3" fill="${sw}"/>
 <rect x="192" y="55" width="6" height="0" fill="${sw}"/>
 ${rad(12, 64, 6)}${rad(38, 64, 6)}${rad(88, 63, 7)}${rad(106, 59, 11)}
 ${rad(130, 59, 11)}${rad(154, 59, 11)}${rad(174, 64, 6)}${rad(188, 64, 6)}
 <line x1="106" y1="62" x2="154" y2="62" stroke="#c9c9c9" stroke-width="2.2" stroke-linecap="round"/>
 <line x1="154" y1="62" x2="170" y2="52" stroke="#c9c9c9" stroke-width="1.8"/>`;
  }
  function anlageZeichnen() {
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
    s += `<rect x="112" y="30" width="66" height="50" class="bh-turm"/>
  <rect x="108" y="25" width="74" height="6" class="bh-dach"/>
  <rect x="120" y="38" width="12" height="13" class="bh-fenster"/>
  <rect x="139" y="38" width="12" height="13" class="bh-fenster"/>
  <rect x="158" y="38" width="12" height="13" class="bh-fenster"/>
  <rect x="118" y="58" width="54" height="13" rx="1.5" class="bh-schild"/>
  <text x="145" y="67.5" text-anchor="middle" class="bh-schrift">MERGE-TRAIN</text>
  <rect x="6" y="84" width="172" height="${gl - 84}" class="bh-wand"/>`;
    for (let x = 10; x < 178; x += 5) s += `<line x1="${x}" y1="144" x2="${x}" y2="${gl}" class="bh-welle"/>`;
    s += `<rect x="2" y="78" width="180" height="7" class="bh-dach"/>
  <rect x="12" y="93" width="160" height="46" rx="2" class="bh-glas"/>`;
    for (let x = 52; x < 172; x += 40) s += `<line x1="${x}" y1="94" x2="${x}" y2="138" class="bh-sprosse"/>`;
    s += `<rect x="6" y="139" width="172" height="5" class="bh-dach"/>
  <path d="M28,${gl} V166 Q92,154 156,166 V${gl} Z" class="bh-tor"/>
  <path d="M28,166 Q92,154 156,166" class="bh-torrand"/>
  <rect x="172" y="143" width="10" height="16" class="bh-tor"/>`;
    // Band: aus der Halle schräg hinauf bis zur Mitte, Fachwerkbrücke, Stützen bis zum Boden, Bandkopf mit Schurre über
    // dem Wagen
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
      const unten = gl - 4,
        strebe1 = r(unten - (gl - yb) * 0.3),
        strebe2 = r(unten - (gl - yb) * 0.65);
      s += `<path d="M${r(x - 12)},${unten} L${r(x - 3)},${r(yb)} M${r(x + 12)},${unten} L${r(x + 3)},${r(yb)}
        M${r(x - 9)},${strebe1} H${r(x + 9)} M${r(x - 6)},${strebe2} H${r(x + 6)}" class="bh-stuetze"/>`;
    }
    s += `<path d="M${x1 - 14},${gl - 4} L${x1 - 8},${y1 + T} M${x1 + 14},${gl - 4} L${x1 + 8},${y1 + T}
    M${x1 - 12},${gl - 40} H${x1 + 12} M${x1 - 10},${gl - 70} H${x1 + 10}" class="bh-stuetze"/>
  <g class="bh-band"><line x1="${x0}" y1="${y0 + T}" x2="${x1}" y2="${y1 + T}" class="bh-fachwerk"/>
  <path d="${fw}" class="bh-fachwerk"/>
  <line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" class="bh-gurt"/>
  <line x1="${x0 + 3}" y1="${r(y(x0 + 3) - 3.5)}" x2="${x1 - 5}" y2="${r(y(x1 - 5) - 3.5)}" class="bh-gut"/>
  <circle cx="${x1}" cy="${y1}" r="5" class="bh-trommel"/></g>
  <polygon class="bh-schurre"
    points="${x1 - 2},${y1 + 3} ${x1 + 12},${y1 + 3} ${x1 + 7},${y1 + 24} ${x1 + 1},${y1 + 24}"/>
  <line x1="${x1 + 4}" y1="${y1 + 24}" x2="${x1 + 4}" y2="${y1 + 38}" class="bh-strahl"/>`;
    s += `<line x1="0" y1="${gl}" x2="${B}" y2="${gl}" class="bh-schiene"/>`;
    sv.innerHTML = s;
    return cx + 4;
  }
  App.lokSvg = lokSvg;
  App.anlageZeichnen = anlageZeichnen;
})();
