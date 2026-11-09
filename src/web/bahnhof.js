// Güterbahnhof: GitLab nur auf Knopfdruck. Der Zug kommt aus dem Cache des Servers (/api/mrzug), keine GitLab-Anfrage.
function zugHolen(){return fetch('/api/mrzug?akt='+encodeURIComponent(MR.id)).then(r=>r.json()).then(z=>{ZUG=z.wagen||[];zug();kh();
 const t=document.getElementById('bhzeit');if(t)t.textContent=z.zeit?'MRs vom '+z.zeit:'MRs noch nicht geholt';
 try{localStorage.mrzug=JSON.stringify(ZUG)}catch(_){}}).catch(()=>{})}
try{if(!ZUG.length){ZUG=JSON.parse(localStorage.mrzug||'[]');zug();kh()}}catch(_){}
zugHolen();
document.querySelectorAll('#bahnhof button').forEach(b=>{if(b.dataset.g==='mrdaten'&&!MR.id)b.hidden=true;
 const bh=document.getElementById('bahnhof');
 b.addEventListener('click',()=>{b.disabled=true;meld.textContent='frage GitLab …';bh.classList.add('laedt'); // Schüttgut rieselt, solange GitLab antwortet
  fetch('/api/gitlab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aktion:b.dataset.g,mr:MR.id,k:MR.k})})
   .then(r=>r.json()).then(d=>{b.disabled=false;bh.classList.remove('laedt');meld.textContent=d.text||'';if(!d.ok)return;
    if(b.dataset.g==='mrdaten')location.reload();else zugHolen()})
   .catch(()=>{b.disabled=false;bh.classList.remove('laedt');meld.textContent='merge-train-Server nicht erreichbar'})})});
