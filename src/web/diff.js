// Diff-Ansicht (GitLab-MR und lokales Projekt): Kontext nachladen, große Dateien laden, Zeile zeigen, Popup
function el(tag,attrs,...kinder){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs||{})){
 if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!=null)e.setAttribute(k,v)}
 for(const k of kinder){if(k==null||k===false)continue;e.append(k instanceof Node?k:String(k))}return e}
// Commit-Ansicht (MR.ansicht = 'commit:<sha>' nur lesen, 'seit:<sha>' rechts = MR-Stand): Server rechnet die Zeilen um
const qs=(mrStand)=>'mr='+encodeURIComponent(MR.id)+'&k='+MR.k+(MR.ansicht&&!mrStand?'&ansicht='+MR.ansicht:'');
const LESEN=!!MR.lesen,SEIT=(MR.ansicht||'').startsWith('seit:');
function neuZeichnen(){if(typeof zeichnen==='function')zeichnen()}
// ---- Kontext nachladen, Zeile zeigen, Popup
const PROJ=(MR.web_url||'').split('/-/merge_requests/')[0];
function zeilenHolen(pfad,von,bis,mrStand){return fetch('/api/zeilen?'+qs(mrStand)+'&pfad='+encodeURIComponent(pfad)+'&von='+von+'&bis='+bis)
 .then(r=>r.json()).catch(()=>({ok:false,text:'merge-train-Server nicht erreichbar'}))}
function trAus(h){const t=document.createElement('tbody');t.innerHTML=h;return t.firstElementChild}
function luKnoepfe(tr){const v=+tr.dataset.von,b=+tr.dataset.bis,n=b-v+1,kn=[el('span',{},'⋯ '+n+' Zeile(n) ausgeblendet')];
 if(n>30){if(v>1)kn.push(el('button',{title:'20 Zeilen unter dem sichtbaren Teil darüber',onclick:()=>aufklappen(tr,v,v+19)},'▼ 20'));
  if(tr.nextElementSibling)kn.push(el('button',{title:'20 Zeilen über dem sichtbaren Teil darunter',onclick:()=>aufklappen(tr,b-19,b)},'▲ 20'))}
 kn.push(el('button',{onclick:()=>aufklappen(tr,v,b)},n>30?'alle '+n:'aufklappen'));tr.lastElementChild.replaceChildren(...kn)}
function luTeil(lu,v,b){const t=lu.cloneNode(true);t.dataset.von=v;t.dataset.bis=b;return t}
function aufklappen(tr,x,y){const d=tr.closest('.datei'),v=tr.dataset.von,b=tr.dataset.bis,delta=+tr.dataset.d;x=Math.max(x,+v);y=Math.min(y,+b);
 return zeilenHolen(d.dataset.pfad,x,y).then(r=>{if(!r.ok){meld.textContent=r.text;return false}
  d.querySelectorAll('tr.lu[data-von="'+v+'"][data-bis="'+b+'"]').forEach(lu=>{const sbs=lu.closest('table').classList.contains('sbs'),neu=[];
   if(x>+v)neu.push(luTeil(lu,+v,x-1));
   r.zeilen.forEach((h,i)=>{const nb=x+i,na=nb+delta;neu.push(trAus(sbs
    ?`<tr class="kx" data-a="${na}" data-b="${nb}"><td class="n">${na}</td><td class="c">${h}</td><td class="n">${nb}</td><td class="c">${h}</td></tr>`
    :`<tr class="kx" data-a="${na}" data-b="${nb}"><td class="n">${na}</td><td class="n">${nb}</td><td class="c">${h}</td></tr>`))});
   if(y<+b)neu.push(luTeil(lu,y+1,+b));
   lu.replaceWith(...neu);neu.forEach(t=>{if(t.classList.contains('lu'))luKnoepfe(t)})});
  neuZeichnen();return true})}
function blinken(e){e.classList.remove('blink');void e.offsetWidth;e.classList.add('blink');e.addEventListener('animationend',()=>e.classList.remove('blink'),{once:true})}
function aufblitzen(r){r.scrollIntoView({block:'center'});blinken(r)}
function dateiLaden(d){const p=d.querySelector('.spaet');if(!p)return Promise.resolve(true);if(p.dataset.laedt)return p.laedt;
 const b=p.querySelector('button');if(b){b.disabled=true;b.textContent='lädt …'}p.dataset.laedt=1;
 return p.laedt=fetch('/api/datei?'+qs()+'&i='+ds.indexOf(d)).then(r=>r.json()).then(r=>{
  if(!r.ok){meld.textContent=r.text;delete p.dataset.laedt;if(b){b.disabled=false;b.textContent='Diff laden'}return false}
  const t=document.createElement('div');t.innerHTML=r.html;p.replaceWith(...t.childNodes);d.querySelectorAll('tr.lu').forEach(luKnoepfe);
  if(document.body.classList.contains('inline'))inlBauen(d);neuZeichnen();return true})
  .catch(()=>{meld.textContent='merge-train-Server nicht erreichbar';delete p.dataset.laedt;return false})}
document.querySelector('main').addEventListener('click',e=>{const b=e.target.closest('button.laden');if(b)dateiLaden(b.closest('.datei'))});
document.addEventListener('inl',e=>{e.detail.forEach(t=>t.querySelectorAll('tr.lu').forEach(luKnoepfe));neuZeichnen()});
function zeigen(x,ohnePopup){ // Zeile im Diff zeigen (Kontext/Datei dafür nachladen), sonst Popup. Promise: true = Zeile im Diff
 const z=x.b||x.a,sonst=()=>{if(x.path&&!ohnePopup)popup(x.path,z);return false};
 if(x.datei!=null&&ds[x.datei]&&z){const d=ds[x.datei];d.open=true;
  if(d.querySelector('.spaet'))return dateiLaden(d).then(ok=>ok?zeigen(x,ohnePopup):sonst());
  const tab=d.querySelector(document.body.classList.contains('inline')?'table.inl':'table.sbs'),r=tab&&zeileFinden(tab,x.a,x.b);
  if(!tab)return Promise.resolve(sonst());
  if(r){aufblitzen(r);return Promise.resolve(true)}
  const lu=x.b&&[...tab.querySelectorAll('tr.lu')].find(t=>+t.dataset.von<=x.b&&x.b<=+t.dataset.bis);
  if(lu)return aufklappen(lu,x.b-6,x.b+6).then(ok=>{const r2=ok&&zeileFinden(tab,x.a,x.b);if(r2)aufblitzen(r2);return !!r2})}
 return Promise.resolve(sonst())}
function sichtbar(sel){return [...document.querySelectorAll(sel)].find(e=>e.getClientRects().length)}
function springen(i){ // aus der Kommentarliste: zum Kasten (bei Bedarf Kontext/Datei nachladen)
 const hin=()=>{const b=sichtbar('.kbox[data-id="'+i.id+'"]');if(!b)return false;const d=b.closest('.datei');FEST=d?ds.indexOf(d):null;
  b.scrollIntoView({block:'center'});markiere();blinken(b);return true};
 if(hin())return;
 (i.x.datei!=null?zeigen(i.x,true):Promise.resolve(false)).then(()=>{if(!hin())zeigen(i.x)})}
var SORT=false; // Sortiermodus der Box „GitLab-Kommentare“
function kliste(){ // links: GitLab-Kommentare (Entwürfe, Agent-Hinweise) und KI-Threads (privat) getrennt
 const nach=(p,q)=>((p.x.datei??-1)-(q.x.datei??-1))||((p.x.b||p.x.a||0)-(q.x.b||q.x.a||0));
 const pos={};(RV.reihenfolge||[]).forEach((id,n)=>pos[id]=n); // vom Server: Sende-Reihenfolge bei „Review abschließen“
 kasten('kliste','GitLab-Kommentare',[...RV.kommentare.filter(x=>x.status!=='loeschen').map(x=>({art:'km',id:x.id,x,f:x.finding,st:x.status})),
  ...RV.hinweise.filter(h=>h.status==='offen').map(h=>({art:'hw',id:h.key,x:h,f:h.finding}))].sort((p,q)=>((pos[p.id]??1e9)-(pos[q.id]??1e9))||nach(p,q)),
  RVW&&!LESEN&&!MR.ansicht);
 kasten('kliste-ki','KI-Threads',(RV.faeden||[]).map(x=>({art:'km',id:x.id,x,st:x.status})).sort(nach))}
function reihenfolge(ids){RV.reihenfolge=ids;kliste();speichernAls({aktion:'reihenfolge',ids})}
function verschieben(id,ziel,unten){const ids=(RV.reihenfolge||[]).filter(x=>x!==id); // ziel: id, 'oben' oder 'unten'
 if(ziel==='oben')ids.unshift(id);else if(ziel==='unten')ids.push(id);else{const i=ids.indexOf(ziel);if(i<0)return;ids.splice(i+(unten?1:0),0,id)}
 reihenfolge(ids)}
function kasten(id,name,items,sortierbar){const k=document.getElementById(id);if(!k)return;
 k.hidden=!items.length;const sm=k.querySelector('summary'),s=sortierbar&&SORT&&items.length>1;sm.replaceChildren(name+' ('+items.length+')');
 if(sortierbar&&items.length>1)sm.append(el('button',{class:'sortknopf',title:SORT?'Sortieren beenden':'Reihenfolge ändern – in dieser Reihenfolge gehen die Kommentare an GitLab',
  onclick:e=>{e.preventDefault();SORT=!SORT;k.open=true;kliste()}},SORT?'✓ fertig':'⇅ sortieren'));
 const titel=x=>x.title||(x.hinweis&&(RV.hinweise.find(h=>h.key===x.hinweis)||{}).title)||null;
 k.querySelector('div').replaceChildren(...items.map(i=>{const t=String(i.x.text||(i.x.nachrichten&&i.x.nachrichten[0]||{}).text||''),f=titel(i.x)||(i.f&&t.startsWith(i.f)?t.slice(i.f.length).trim():t);
  const e=el('div',{class:'ke '+i.art+(s?' sort':''),title:f,onclick:s?null:()=>springen(i)},
   s?el('span',{class:'griff',title:'ziehen zum Umsortieren'},'⠿'):null,
   el('span',{class:'ki '+((STATUS[i.st]||[])[1]||''),title:i.st?(STATUS[i.st]||[''])[0]:'Agent-Hinweis'},i.art==='hw'?'🤖':'💬'),
   i.f?el('b',{},i.f):null,el('span',{class:'kt2'},f),
   s?el('span',{class:'pfeile'},el('button',{title:'ganz nach oben',onclick:()=>verschieben(i.id,'oben')},'⤒'),
     el('button',{title:'ganz nach unten',onclick:()=>verschieben(i.id,'unten')},'⤓')):null);
  if(s){e.draggable=true;const weg=()=>e.classList.remove('drop-oben','drop-unten');
   e.addEventListener('dragstart',ev=>{ev.dataTransfer.setData('text/plain',i.id);ev.dataTransfer.effectAllowed='move';e.classList.add('zieht')});
   e.addEventListener('dragend',()=>e.classList.remove('zieht'));
   e.addEventListener('dragover',ev=>{ev.preventDefault();const r=e.getBoundingClientRect(),u=ev.clientY>=r.top+r.height/2;e.classList.toggle('drop-oben',!u);e.classList.toggle('drop-unten',u)});
   e.addEventListener('dragleave',weg);
   e.addEventListener('drop',ev=>{ev.preventDefault();const von=ev.dataTransfer.getData('text/plain'),u=e.classList.contains('drop-unten');weg();if(von&&von!==i.id)verschieben(von,i.id,u)})}
  return e}))}
function ortLink(x){return x.path?el('a',{class:'ortlink',title:'im Code zeigen',onclick:()=>zeigen(x)},ort(x)):el('code',{},ort(x))}
function siehe(sa){if(!sa||!sa.length)return null;
 return el('div',{class:'sa'},el('span',{},'Siehe auch:'),...sa.map(s=>{const wo=s.path+(s.zeile?':'+s.zeile+(s.bis?'-'+s.bis:''):'');
  if(s.problem)return el('span',{class:'warn',title:s.problem},(s.label?s.label+' · ':'')+wo+' ('+s.problem+')');
  const name=s.label||(s.path.split('/').pop()+(s.zeile?':'+s.zeile+(s.bis?'-'+s.bis:''):''));
  return s.vergleich?el('a',{class:'vgl',title:'Vergleich nebeneinander: '+s.vergleich+' ⇄ '+s.path,onclick:()=>vergleich(s.vergleich,s.path,s.label)},'⇄ '+name)
   :el('a',{title:wo,onclick:()=>popup(s.path,s.zeile,s.label,s.bis)},name)}))}
function vergleich(a,b,label){schliessen(); // see_also mit "diff": zwei Dateien des MR-Stands nebeneinander
 const kurz=p=>p.split('/').pop(),info=el('span',{class:'sub'},'lädt …'),pb=el('div',{class:'pb'}),kn=el('span',{class:'knoepfe'});
 document.body.append(el('div',{id:'schleier',onclick:schliessen}),el('div',{id:'popup',class:'vergleich'},el('div',{class:'pk'},
  el('b',{title:a+' ⇄ '+b},(label?label+' – ':'')+kurz(a)+' ⇄ '+kurz(b)),info,kn),pb));
 kn.append(el('button',{title:'schließen (Esc)',onclick:schliessen},'✕'));
 fetch('/api/vergleich?'+qs(true)+'&a='+encodeURIComponent(a)+'&b='+encodeURIComponent(b)).then(r=>r.json())
  .catch(()=>({ok:false,text:'merge-train-Server nicht erreichbar'})).then(r=>{if(!pb.isConnected)return;
  if(!r.ok){info.textContent='';pb.append(el('div',{class:'warn'},r.text));return}
  pb.append(el('div',{class:'vkopf'},el('span',{title:a},a),el('span',{title:b},b)));
  const t=document.createElement('div');t.innerHTML=r.html;pb.append(...t.childNodes);
  const rows=[...pb.querySelectorAll('tr')],anf=rows.filter((tr,i)=>tr.querySelector('.weg,.dazu,.nix')&&!(rows[i-1]&&rows[i-1].querySelector('.weg,.dazu,.nix')));
  info.textContent=anf.length?anf.length+' Unterschied(e) · +'+r.plus+' −'+r.minus+' · Stand '+r.sha.slice(0,8):'keine Unterschiede';
  let i=-1;const geh=d=>{if(!anf.length)return;i=(i+d+anf.length)%anf.length;const z=anf[i];
   pb.scrollTop+=z.getBoundingClientRect().top-pb.getBoundingClientRect().top-pb.clientHeight/3;blinken(z)};
  if(anf.length)kn.prepend(el('button',{title:'voriger Unterschied',onclick:()=>geh(-1)},'↑'),el('button',{title:'nächster Unterschied',onclick:()=>geh(1)},'↓'));
  geh(1)})}
var LEIHE=null; // Datei, die gerade im Popup steht: {d, platz}
function zurueckgeben(){if(!LEIHE)return;const {d,platz}=LEIHE;LEIHE=null;d.querySelectorAll('tr.ziel').forEach(t=>t.classList.remove('ziel'));platz.replaceWith(d)}
function schliessen(){zurueckgeben();['popup','schleier'].forEach(i=>{const e=document.getElementById(i);if(e)e.remove()})}
function popup(pfad,zeile,label,bisZ){schliessen(); // Code im MR-Stand; liegt die Datei im Diff: deren Diff (aufklappbar)
 const di=ds.findIndex(d=>d.dataset.pfad===pfad),mitDiff=di>=0&&!LESEN,ende=bisZ||zeile,info=el('span',{class:'sub'}),pb=el('div',{class:'pb'});
 const gl=PROJ?el('a',{class:'gl-link',target:'_blank',rel:'noopener',href:PROJ+'/-/blob/'+MR.sha+'/'+pfad.split('/').map(encodeURIComponent).join('/')+(zeile?'#L'+zeile+(bisZ?'-'+bisZ:''):'')},'GitLab ↗'):null;
 const kn=el('span',{class:'knoepfe'}),wo=pfad+(zeile?':'+zeile+(bisZ?'-'+bisZ:''):'');
 document.body.append(el('div',{id:'schleier',onclick:schliessen}),el('div',{id:'popup'},el('div',{class:'pk'},
  el('b',{},(label?label+' – ':'')+wo),info,kn),pb));
 const zu=el('button',{title:'schließen (Esc)',onclick:schliessen},'✕');
 if(mitDiff){const d=ds[di];info.textContent='Diff im MR';
  kn.append(el('button',{title:'alle ausgeblendeten Zeilen dieser Datei laden',onclick:()=>alleAuf(pb)},'alles aufklappen'),
   zeile?el('button',{onclick:()=>{schliessen();zeigen({datei:di,a:null,b:zeile,path:pfad})}},'im Diff zeigen'):null,gl,zu);
  dateiLaden(d).then(ok=>{if(!pb.isConnected)return; // Popup inzwischen zu
   if(!ok){pb.textContent='Diff nicht verfügbar';return}
   // dieselbe Datei wie auf der Seite (nicht kopiert): Kommentare, Hinweise, Kontext und Klicks gelten hier wie dort
   const platz=el('div',{class:'leihplatz',style:'height:'+d.offsetHeight+'px'});d.replaceWith(platz);d.open=true;pb.append(d);LEIHE={d,platz};
   if(!zeile)return;
   const markieren=()=>{let erst=null;d.querySelectorAll('tr[data-b]').forEach(t=>{const b=+t.dataset.b,an=b>=zeile&&b<=ende;t.classList.toggle('ziel',an);if(an&&!erst&&t.getClientRects().length)erst=t});
    if(erst)pb.scrollTop+=erst.getBoundingClientRect().top-pb.getBoundingClientRect().top-pb.clientHeight/2;return !!erst};
   if(markieren())return;
   const lu=[...d.querySelectorAll('tr.lu')].find(t=>+t.dataset.von<=ende&&zeile<=+t.dataset.bis);
   if(lu)aufklappen(lu,zeile-12,ende+12).then(markieren)});
  return}
 const st={von:Math.max(1,(zeile||1)-12),bis:(ende||1)+12},tb=el('tbody');
 const hoch=el('button',{onclick:()=>{st.von=Math.max(1,st.von-30);lade('oben')}},'▲ mehr'),runter=el('button',{onclick:()=>{st.bis+=30;lade('unten')}},'▼ mehr');
 const ganz=el('button',{title:'ganze Datei laden',onclick:()=>{st.von=1;st.bis=1e6;lade('erst')}},'ganze Datei');
 kn.append(hoch,runter,ganz,gl,zu);
 pb.append(el('table',{},el('colgroup',{},el('col',{class:'cn'}),el('col',{})),tb));
 function lade(wie){const rest=pb.scrollHeight-pb.scrollTop;
  zeilenHolen(pfad,st.von,st.bis,true).then(r=>{if(!r.ok){tb.replaceChildren(el('tr',{},el('td',{},''),el('td',{class:'warn'},r.text)));return}
   Object.assign(st,{von:r.von,bis:r.bis});
   tb.replaceChildren(...r.zeilen.map((h,i)=>{const nr=r.von+i;return trAus(`<tr${zeile&&nr>=zeile&&nr<=ende?' class="ziel"':''}><td class="n">${nr}</td><td class="c">${h}</td></tr>`)}));
   hoch.disabled=st.von<=1;runter.disabled=ganz.disabled=st.bis>=r.n;info.textContent=r.n+' Zeilen · Stand '+r.sha.slice(0,8);
   if(wie==='erst'){const z=tb.querySelector('tr.ziel');if(z)pb.scrollTop=z.offsetTop-pb.clientHeight/2}
   else if(wie==='oben')pb.scrollTop=pb.scrollHeight-rest})}
 lade('erst')}
function alleAuf(box){const lu=box.querySelector('tr.lu');if(!lu)return Promise.resolve(true); // nacheinander, bis keine Lücke mehr da ist
 return aufklappen(lu,+lu.dataset.von,+lu.dataset.bis).then(ok=>ok&&alleAuf(box))}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('popup')){e.preventDefault();schliessen()}});
document.querySelectorAll('tr.lu').forEach(luKnoepfe);
function zeileFinden(tab,a,b){for(const r of tab.querySelectorAll('tr[data-a],tr[data-b]')){if(b!=null?r.dataset.b==String(b):(r.dataset.a==String(a)&&r.dataset.b==null||tab.classList.contains('sbs')&&r.dataset.a==String(a)))return r}return null}
