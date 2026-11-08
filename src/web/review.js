const RV={kommentare:[],hinweise:[],quellen:[],stand:null,zeigVerworfen:false};let wartet=false;
function el(tag,attrs,...kinder){const e=document.createElement(tag);for(const[k,v]of Object.entries(attrs||{})){
 if(k==='class')e.className=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else if(v!=null)e.setAttribute(k,v)}
 for(const k of kinder){if(k==null||k===false)continue;e.append(k instanceof Node?k:String(k))}return e}
// Commit-Ansicht (MR.ansicht = 'commit:<sha>' nur lesen, 'seit:<sha>' rechts = MR-Stand): Server rechnet die Zeilen um
const qs=(mrStand)=>'mr='+encodeURIComponent(MR.id)+'&k='+MR.k+(MR.ansicht&&!mrStand?'&ansicht='+MR.ansicht:'');
const LESEN=!!MR.lesen,SEIT=(MR.ansicht||'').startsWith('seit:');
function post(pfad,d){return fetch(pfad,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({mr:MR.id,k:MR.k,sha:MR.sha,ansicht:MR.ansicht||''},d))})
 .then(r=>r.json()).catch(()=>({ok:false,text:'merge-train-Server nicht erreichbar – merge-train erneut aufrufen'}))}
function antwort(d){if(!d.ok){meld.textContent=d.text||'Fehler';return d}meld.textContent='';if(d.review){Object.assign(RV,d.review);zeichnen()}return d}
function laden(){return fetch('/api/review?'+qs()).then(r=>r.json()).then(d=>{if(!d.ok){meld.textContent=d.text;return}Object.assign(RV,d);zeichnen();autoLaden()})
 .catch(()=>{meld.textContent='merge-train-Server nicht erreichbar'})}
const STATUS={neu:['Entwurf (lokal)','b-neu'],uebertragen:['in GitLab (Entwurf)','b-ok'],geaendert:['geändert – wird aktualisiert','b-geaendert'],
 loeschen:['wird in GitLab gelöscht','b-loeschen'],weg:['in GitLab veröffentlicht oder dort gelöscht','b-ok']};
const ort=x=>x.path?x.path+(x.b?':'+x.b:(x.a?':'+x.a+' (alt)':'')):'allgemein';
function bearbeiten(box,text,speichern,abbruch){
 const ta=el('textarea',{}),alt=[...box.childNodes];ta.value=text||'';
 const zu=()=>{if(abbruch)abbruch();else box.replaceChildren(...alt);nachholen()};
 const ok=()=>{const t=ta.value.trim();if(!t){ta.focus();return}speichern(t).then(d=>{if(!d||!d.ok)return;if(abbruch)abbruch();else box.replaceChildren();zeichnen()})};
 ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();ok()}else if(e.key==='Escape'){e.preventDefault();zu()}});
 box.replaceChildren(ta,el('div',{class:'kk'},el('span',{},'Strg+Enter speichern · Esc abbrechen'),
  el('span',{class:'knoepfe'},el('button',{onclick:zu},'abbrechen'),el('button',{class:'haupt',onclick:ok},'speichern'))));
 ta.focus();ta.setSelectionRange(ta.value.length,ta.value.length)}
function speichernAls(d){return post('/api/kommentar',d).then(r=>{const x=antwort(r);return x})}
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
  zeichnen();return true})}
function blinken(e){e.classList.remove('blink');void e.offsetWidth;e.classList.add('blink');e.addEventListener('animationend',()=>e.classList.remove('blink'),{once:true})}
function aufblitzen(r){r.scrollIntoView({block:'center'});blinken(r)}
function dateiLaden(d){const p=d.querySelector('.spaet');if(!p)return Promise.resolve(true);if(p.dataset.laedt)return p.laedt;
 const b=p.querySelector('button');if(b){b.disabled=true;b.textContent='lädt …'}p.dataset.laedt=1;
 return p.laedt=fetch('/api/datei?'+qs()+'&i='+ds.indexOf(d)).then(r=>r.json()).then(r=>{
  if(!r.ok){meld.textContent=r.text;delete p.dataset.laedt;if(b){b.disabled=false;b.textContent='Diff laden'}return false}
  const t=document.createElement('div');t.innerHTML=r.html;p.replaceWith(...t.childNodes);d.querySelectorAll('tr.lu').forEach(luKnoepfe);
  if(document.body.classList.contains('inline'))inlBauen(d);zeichnen();return true})
  .catch(()=>{meld.textContent='merge-train-Server nicht erreichbar';delete p.dataset.laedt;return false})}
function autoLaden(){[...RV.kommentare,...RV.hinweise].forEach(x=>{const d=x.datei!=null&&ds[x.datei];if(d&&d.querySelector('.spaet'))dateiLaden(d)})}
document.querySelector('main').addEventListener('click',e=>{const b=e.target.closest('button.laden');if(b)dateiLaden(b.closest('.datei'))});
document.addEventListener('inl',e=>{e.detail.forEach(t=>t.querySelectorAll('tr.lu').forEach(luKnoepfe));zeichnen()});
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
function kliste(){const k=document.getElementById('kliste');if(!k)return;
 const items=[...RV.kommentare.filter(x=>x.status!=='loeschen').map(x=>({art:'km',id:x.id,x,f:x.finding,st:x.status})),
  ...RV.hinweise.filter(h=>h.status==='offen').map(h=>({art:'hw',id:h.key,x:h,f:h.finding}))]
  .sort((p,q)=>((p.x.datei??-1)-(q.x.datei??-1))||((p.x.b||p.x.a||0)-(q.x.b||q.x.a||0)));
 k.querySelector('summary').textContent='Kommentare ('+items.length+')';
 const titel=x=>x.title||(x.hinweis&&(RV.hinweise.find(h=>h.key===x.hinweis)||{}).title)||null;
 k.querySelector('div').replaceChildren(...items.map(i=>{const t=String(i.x.text||''),f=titel(i.x)||(i.f&&t.startsWith(i.f)?t.slice(i.f.length).trim():t);
  return el('div',{class:'ke '+i.art,title:f,onclick:()=>springen(i)},
   el('span',{class:'ki '+((STATUS[i.st]||[])[1]||''),title:i.st?(STATUS[i.st]||[''])[0]:'Agent-Hinweis'},i.art==='hw'?'🤖':'💬'),
   i.f?el('b',{},i.f):null,el('span',{class:'kt2'},f))}))}
function ortLink(x){return x.path?el('a',{class:'ortlink',title:'im Code zeigen',onclick:()=>zeigen(x)},ort(x)):el('code',{},ort(x))}
function siehe(sa){if(!sa||!sa.length)return null;
 return el('div',{class:'sa'},el('span',{},'Siehe auch:'),...sa.map(s=>{const wo=s.path+(s.zeile?':'+s.zeile:'');
  return s.problem?el('span',{class:'warn',title:s.problem},(s.label?s.label+' · ':'')+wo+' ('+s.problem+')')
   :el('a',{title:wo,onclick:()=>popup(s.path,s.zeile,s.label)},s.label||(s.path.split('/').pop()+(s.zeile?':'+s.zeile:'')))}))}
function schliessen(){['popup','schleier'].forEach(i=>{const e=document.getElementById(i);if(e)e.remove()})}
function popup(pfad,zeile,label){schliessen();
 const st={von:Math.max(1,(zeile||1)-12),bis:(zeile||1)+12},tb=el('tbody'),info=el('span',{class:'sub'}),pb=el('div',{class:'pb'});
 const hoch=el('button',{onclick:()=>{st.von=Math.max(1,st.von-30);lade('oben')}},'▲ mehr'),runter=el('button',{onclick:()=>{st.bis+=30;lade('unten')}},'▼ mehr');
 const di=ds.findIndex(d=>d.dataset.pfad===pfad);
 const gl=PROJ?el('a',{class:'gl-link',target:'_blank',rel:'noopener',href:PROJ+'/-/blob/'+MR.sha+'/'+pfad.split('/').map(encodeURIComponent).join('/')+(zeile?'#L'+zeile:'')},'GitLab ↗'):null;
 pb.append(el('table',{},el('colgroup',{},el('col',{class:'cn'}),el('col',{})),tb));
 document.body.append(el('div',{id:'schleier',onclick:schliessen}),el('div',{id:'popup'},el('div',{class:'pk'},
  el('b',{},(label?label+' – ':'')+pfad+(zeile?':'+zeile:'')),info,el('span',{class:'knoepfe'},hoch,runter,
   di>=0&&zeile&&!LESEN?el('button',{onclick:()=>{schliessen();zeigen({datei:di,a:null,b:zeile,path:pfad})}},'im Diff zeigen'):null,gl,
   el('button',{title:'schließen (Esc)',onclick:schliessen},'✕'))),pb));
 function lade(wie){const rest=pb.scrollHeight-pb.scrollTop;
  zeilenHolen(pfad,st.von,st.bis,true).then(r=>{if(!r.ok){tb.replaceChildren(el('tr',{},el('td',{},''),el('td',{class:'warn'},r.text)));return}
   Object.assign(st,{von:r.von,bis:r.bis});
   tb.replaceChildren(...r.zeilen.map((h,i)=>{const nr=r.von+i;return trAus(`<tr${nr===zeile?' class="ziel"':''}><td class="n">${nr}</td><td class="c">${h}</td></tr>`)}));
   hoch.disabled=st.von<=1;runter.disabled=st.bis>=r.n;info.textContent=r.n+' Zeilen · Stand '+r.sha.slice(0,8);
   if(wie==='erst'){const z=tb.querySelector('tr.ziel');if(z)pb.scrollTop=z.offsetTop-pb.clientHeight/2}
   else if(wie==='oben')pb.scrollTop=pb.scrollHeight-rest})}
 lade('erst')}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('popup')){e.preventDefault();schliessen()}});
document.querySelectorAll('tr.lu').forEach(luKnoepfe);
function kommentarBox(k,mitOrt){
 const [st,cl]=STATUS[k.status]||['?',''],box=el('div',{class:'kbox km'+(k.status==='loeschen'?' weg':''),'data-id':k.id}),kn=el('span',{class:'knoepfe'});
 if(LESEN||k.lesen);
 else if(k.status==='loeschen')kn.append(el('button',{onclick:()=>speichernAls({aktion:'wiederherstellen',id:k.id})},'wiederherstellen'));
 else kn.append(k.status==='weg'?null:el('button',{onclick:()=>bearbeiten(box,k.text,t=>speichernAls({aktion:'aendern',id:k.id,text:t}))},'✎ bearbeiten'),
  el('button',{onclick:()=>{if(k.status==='neu'&&!confirm('Kommentar löschen?'))return;speichernAls({aktion:'loeschen',id:k.id})}},'🗑 löschen'));
 box.append(el('div',{class:'kk'},el('span',{class:'badge '+cl},st),k.finding?el('span',{class:'badge b-agent'},'aus Agent '+k.finding):null,
  mitOrt?ortLink(k):null,kn),el('div',{class:'kt'},k.text));
 const h=k.hinweis&&RV.hinweise.find(x=>x.key===k.hinweis),sa=h&&siehe(h.see_also);if(sa)box.append(sa);
 return box}
function hinweisBox(h,mitOrt){
 const box=el('div',{class:'kbox hw'+(h.status==='verworfen'?' weg':''),'data-id':h.key}),kn=el('span',{class:'knoepfe'});
 if(LESEN||h.lesen);
 else if(h.status==='verworfen')kn.append(el('button',{onclick:()=>post('/api/hinweis',{aktion:'zurueck',key:h.key}).then(antwort)},'zurückholen'));
 else kn.append(el('button',{class:'haupt',title:'als Review-Kommentar übernehmen',onclick:()=>speichernAls({aktion:'neu',hinweis:h.key})},'übernehmen'),
  el('button',{onclick:()=>bearbeiten(box,h.text,t=>speichernAls({aktion:'neu',hinweis:h.key,text:t}))},'✎ anpassen & übernehmen'),
  el('button',{onclick:()=>post('/api/hinweis',{aktion:'verwerfen',key:h.key}).then(antwort)},'verwerfen'));
 const NAMEN={problem:'Problem',decision:'Entscheidung',status:'Status',placement:'Platzierung'},ex=h.extra||{};
 const det=[['Problem',ex.problem],['Entscheidung',ex.decision],['Begründung',h.rationale],['Behoben, wenn',h.resolved_when],
  ...Object.entries(ex).filter(([k])=>k!=='problem'&&k!=='decision').map(([k,v])=>[NAMEN[k]||k,v])].filter(x=>x[1]!=null&&x[1]!=='');
 box.append(el('div',{class:'kk'},el('span',{class:'badge b-agent'},'🤖 Agent '+(h.finding||'')),el('span',{},h.quelle||''),
  mitOrt?ortLink(h):null,h.mehrfach?el('span',{},'(passt auf '+h.mehrfach+' Zeilen)'):null,h.problem?el('span',{class:'warn'},h.problem):null,ex.status?el('span',{class:'badge'},'Status: '+ex.status):null,kn),
  el('div',{class:'kt'},h.text));
 const sa=siehe(h.see_also);if(sa)box.append(sa);
 if(det.length){const d=el('details',{},el('summary',{},'Details'));det.forEach(([k,v])=>d.append(el('div',{},el('b',{},k+': '),typeof v==='string'?v:JSON.stringify(v,null,1))));box.append(d)}
 return box}
function zeileFinden(tab,a,b){for(const r of tab.querySelectorAll('tr[data-a],tr[data-b]')){if(b!=null?r.dataset.b==String(b):(r.dataset.a==String(a)&&r.dataset.b==null||tab.classList.contains('sbs')&&r.dataset.a==String(a)))return r}return null}
function einfuegen(r,inhalt,tab){let z=r;while(z.nextElementSibling&&z.nextElementSibling.classList.contains('kr'))z=z.nextElementSibling;
 const tr=el('tr',{class:'kr'},el('td',{colspan:tab.classList.contains('sbs')?4:3},inhalt));z.after(tr);return tr}
function nachholen(){if(wartet)setTimeout(zeichnen,0)}
function unterDatei(x,box){ // Ansicht: Eintrag lässt sich keiner sichtbaren Zeile zuordnen → unter den Dateinamen, mit Grund
 const d=ds[x.datei];let c=d.querySelector(':scope>.kunter');
 if(!c){c=el('div',{class:'kunter'});d.querySelector('summary').after(c)}
 const mrOrt=x.mr_b||x.mr_a,wo=mrOrt?el('a',{class:'ortlink',title:'im MR-Stand zeigen',onclick:()=>popup(x.path,x.mr_b||null)},'MR-Stand: Zeile '+mrOrt+(x.mr_b?'':' (alt)')):null;
 const zur=x.b?el('a',{class:'ortlink',title:'Kontext aufklappen',onclick:()=>zeigen(x)},'aufklappen'):null;
 c.append(el('div',{class:'unter'},el('span',{class:'warn'},x.unter),zur?' · ':null,zur,wo?' · ':null,wo),box)}
function zeichnen(){
 if(document.querySelector('.kbox textarea')){wartet=true;return}wartet=false;
 document.querySelectorAll('tr.kr,.kunter').forEach(r=>r.remove());
 const allg=[],zahl={};
 const platz=(x,mach)=>{if(x.datei==null||!ds[x.datei]||!(x.a||x.b))return false;let ok=false;
  ds[x.datei].querySelectorAll('table').forEach(tab=>{const r=zeileFinden(tab,x.a,x.b);if(r){einfuegen(r,mach(),tab);ok=true}});
  if(ok)zahl[x.datei]=(zahl[x.datei]||0)+1;return ok};
 const unter=(x,mach)=>{if(x.unter==null||x.datei==null||!ds[x.datei])return false;unterDatei(x,mach());zahl[x.datei]=(zahl[x.datei]||0)+1;return true};
 RV.kommentare.forEach(k=>{if(!platz(k,()=>kommentarBox(k,false))&&!unter(k,()=>kommentarBox(k,false)))allg.push(()=>kommentarBox(k,true))});
 RV.hinweise.filter(h=>h.status==='offen'||(RV.zeigVerworfen&&h.status==='verworfen'))
  .forEach(h=>{if(!platz(h,()=>hinweisBox(h,false))&&!unter(h,()=>hinweisBox(h,false)))allg.push(()=>hinweisBox(h,true))});
 allgemein(allg);kliste();ls.forEach((a,i)=>{const z=a.querySelector('.kz');if(z)z.textContent=zahl[i]?'💬'+zahl[i]:''});
 const n=RV.kommentare.filter(k=>k.status!=='loeschen').length,offen=RV.hinweise.filter(h=>h.status==='offen').length;
 document.getElementById('rvstand').textContent=n+' Kommentar(e)'+(RV.ausstehend?' · '+RV.ausstehend+' noch nicht in GitLab':'')+(offen?' · '+offen+' Agent-Hinweis(e) offen':'');kh()}
function allgemein(allg){
 let s=document.getElementById('allgemein');if(!s){s=el('section',{id:'allgemein'});document.querySelector('main').prepend(s)}
 const verw=RV.hinweise.filter(h=>h.status==='verworfen').length;
 s.replaceChildren(el('div',{class:'kk'},el('b',{},'Review'),el('span',{class:'sub'},allg.length?'außerhalb des Diffs / allgemein:':'Kommentare stehen an den Zeilen'),
  el('span',{class:'knoepfe'},verw?el('button',{onclick:()=>{RV.zeigVerworfen=!RV.zeigVerworfen;zeichnen()}},RV.zeigVerworfen?'verworfene ausblenden':verw+' verworfene Hinweise zeigen'):null,
   LESEN?null:el('button',{onclick:()=>{const b=el('div',{class:'kbox km'});s.append(b);bearbeiten(b,'',t=>speichernAls({aktion:'neu',text:t}),()=>b.remove())}},'＋ allgemeiner Kommentar'))),
  RV.ausserhalb?el('div',{class:'sub'},RV.ausserhalb+' weitere(r) Kommentar(e)/Hinweis(e) in Dateien, die diese Ansicht nicht ändert – siehe ganzer MR'):null);
 RV.quellen.forEach(q=>{const d=el('details',{class:'quelle'},el('summary',{},'🤖 '+(q.key||q.datei)+(q.reviewed_commit?' · geprüft '+q.reviewed_commit:'')+(q.reviewed_at?' am '+q.reviewed_at:'')+' · '+q.anzahl+' Hinweis(e)'),
  q.fehler?el('div',{class:'warn'},q.fehler):null,q.alt?el('div',{class:'warn'},'geprüft auf Stand '+q.reviewed_commit+', der MR steht auf '+MR.sha.slice(0,8)+' – Hinweise evtl. veraltet'):null,el('div',{},q.datei),q.notes?el('div',{class:'kt'},q.notes):null,
  q.failing_tests?el('div',{},el('b',{},'failing_tests: '),JSON.stringify(q.failing_tests,null,1)):null);
  if(q.fehler)d.open=true;s.append(d)});
 allg.forEach(f=>s.append(f()))}
document.querySelector('main').addEventListener('click',e=>{const td=e.target.closest('td.n');if(!td||!td.textContent.trim())return;
 if(LESEN){meld.textContent='Nur-Lese-Ansicht: kommentieren im ganzen MR oder in „seit diesem“';return}
 const tr=td.closest('tr');if(!tr||!(tr.dataset.a||tr.dataset.b))return;
 const tab=tr.closest('table'),n=ds.indexOf(tr.closest('.datei'));let a=tr.dataset.a?+tr.dataset.a:null,b=tr.dataset.b?+tr.dataset.b:null;
 if(tab.classList.contains('sbs')&&tr.querySelector('.weg,.dazu,.nix')){if(td.cellIndex===0)b=null;else a=null}
 if(SEIT&&b==null){meld.textContent='In dieser Ansicht nur rechts (MR-Stand) kommentierbar';return}
 const box=el('div',{class:'kbox km'}),zr=einfuegen(tr,box,tab);
 bearbeiten(box,'',t=>speichernAls({aktion:'neu',datei:n,a,b,text:t}),()=>zr.remove())});
knopf.addEventListener('click',()=>{knopf.disabled=true;meld.textContent='überträgt Entwürfe nach GitLab …';
 post('/api/abschliessen',{}).then(d=>{knopf.disabled=false;
  meld.replaceChildren(d.text||'',d.web_url?el('a',{href:d.web_url,target:'_blank',rel:'noopener'},' → in GitLab prüfen ↗'):'');
  if(d.review){Object.assign(RV,d.review);zeichnen()}
  fetch('/api/mrzug?akt='+encodeURIComponent(MR.id)).then(r=>r.json()).then(z=>{ZUG=z.wagen||[];zug();kh()}).catch(()=>{})})});
setInterval(()=>{if(document.hidden)return;fetch('/api/stand?'+qs()).then(r=>r.json()).then(d=>{if(d.stand&&d.stand!==RV.stand)laden()}).catch(()=>{})},4000);
laden();
// MR-Zug nebenbei holen (braucht GitLab-Abfragen – soll den Seitenaufbau nicht blockieren)
// Bis die Antwort da ist: der zuletzt gesehene Zug aus dem Browser (sonst hält #zug nur den Platz frei, nichts springt)
try{if(!ZUG.length){ZUG=JSON.parse(localStorage.mrzug||'[]');zug();kh()}}catch(_){}
fetch('/api/mrzug?akt='+encodeURIComponent(MR.id)).then(r=>r.json()).then(z=>{ZUG=z.wagen||[];zug();kh();
 try{localStorage.mrzug=JSON.stringify(ZUG)}catch(_){}}).catch(()=>{});
