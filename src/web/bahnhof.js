// Güterbahnhof: Leitstand-Knöpfe der eingeschalteten Quellen. Der Zug kommt aus /zug.js (gemischt, ohne GitLab-Anfrage);
// GitLab wird nur auf Knopfdruck gefragt (data-g), danach holt zugHolen den Zug neu. Lokal (data-l) lädt zug.js neu.
const GLK=!!document.querySelector('#bahnhof button[data-g]');
function bhZeit(z){const t=document.getElementById('bhzeit');if(t&&GLK)t.textContent=z?'MRs vom '+z:'MRs noch nicht geholt'}
function zugHolen(){return fetch('/api/zug?akt='+encodeURIComponent(MR.id)).then(r=>r.json()).then(z=>{ZUG=z.wagen||[];zug();kh();bhZeit(z.zeit)}).catch(()=>{})}
bhZeit((window.MR_ZUG||{}).zeit);
try{if(sessionStorage.meldung){meld.textContent=sessionStorage.meldung;sessionStorage.removeItem('meldung')}}catch(_){} // Meldung von „↻ MR-Daten“ über das Neuladen
document.querySelectorAll('#bahnhof button[data-g]').forEach(b=>{if(b.dataset.g==='mrdaten'&&(!MR.id||MR.id.startsWith('projekt:')))b.hidden=true;
 const bh=document.querySelector('.szene');
 b.addEventListener('click',()=>{b.disabled=true;meld.textContent='frage GitLab …';bh.classList.add('laedt'); // Schüttgut rieselt, solange GitLab antwortet
  fetch('/api/gitlab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aktion:b.dataset.g,mr:MR.id,k:MR.k})})
   .then(r=>r.json()).then(d=>{b.disabled=false;bh.classList.remove('laedt');meld.textContent=d.text||'';if(!d.ok)return;
    if(b.dataset.g==='mrdaten'){try{sessionStorage.meldung=d.text||''}catch(_){}location.reload()}else zugHolen()})
   .catch(()=>{b.disabled=false;bh.classList.remove('laedt');meld.textContent='merge-train-Server nicht erreichbar'})})});
// Himmel rutscht weg (#kopf klebt bei top:-96px): Kulisse um bis zu 36 px nach unten schieben, Horizont landet am Unterrand
{const k=document.getElementById('kopf'),sz=document.querySelector('.szene');
 if(k&&sz){const f=()=>{const s=Math.min(96,Math.max(0,-k.getBoundingClientRect().top));sz.style.setProperty('--hub',(s*36/96).toFixed(1)+'px')};
  addEventListener('scroll',f,{passive:true});f()}}
