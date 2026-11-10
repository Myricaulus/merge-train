const RV={kommentare:[],faeden:[],agenten:[],hinweise:[],quellen:[],stand:null,zeigVerworfen:false};let wartet=false;
function post(pfad,d){return fetch(pfad,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({mr:MR.id,k:MR.k,sha:MR.sha,ansicht:MR.ansicht||''},d))})
 .then(r=>r.json()).catch(()=>({ok:false,text:'merge-train-Server nicht erreichbar – merge-train erneut aufrufen'}))}
function antwort(d){if(!d.ok){meld.textContent=d.text||'Fehler';return d}meld.textContent='';if(d.review){Object.assign(RV,d.review);zeichnen()}return d}
const WEG='merge-train-Server nicht erreichbar – versucht es weiter …';
function laden(){return fetch('/api/review?'+qs()).then(r=>r.json()).then(d=>{if(meld.textContent===WEG)meld.textContent=''; // Server war kurz weg (Neustart nach ./bauen)
 if(!d.ok){meld.textContent=d.text;return}Object.assign(RV,d);zeichnen();autoLaden()})
 .catch(()=>{meld.textContent=WEG})}
const STATUS={neu:['Entwurf (lokal)','b-neu'],uebertragen:['in GitLab (Entwurf)','b-ok'],geaendert:['geändert – wird aktualisiert','b-geaendert'],
 loeschen:['wird in GitLab gelöscht','b-loeschen'],weg:['in GitLab veröffentlicht oder dort gelöscht','b-ok'],
 // Gespräch (lokales Projekt)
 entwurf:['Entwurf – noch nicht gesendet','b-entwurf'],wartet:['wartet auf Claude','b-wartet'],antwort:['Claude hat geantwortet','b-antwort'],erledigt:['erledigt','b-erledigt']};
const FD=()=>RV.faeden||[],GA=()=>RV.g_ausstehend||0,RVW=!!KANN.review; // RVW: Waggon mit Review (Kommentare nach außen)
function gsPost(d){return speichernAls(Object.assign({gespraech:1},d))} // Fragen an den Agenten: Fäden, nie ins Review
const AG=()=>(RV.agenten&&RV.agenten.length?RV.agenten:RVW?[]:['Claude']); // wen man fragen kann (lokal mindestens Claude)
function neuSpeichern(d){ // neuer Kommentar: mit Review als Review-Kommentar, sonst als Frage an den ersten Agenten
 return t=>RVW?speichernAls(Object.assign({},d,{aktion:'neu',text:t})):gsPost(Object.assign({},d,{aktion:'neu',an:AG()[0],text:t}))}
const ort=x=>x.path?x.path+(x.b?':'+x.b:(x.a?':'+x.a+' (alt)':'')):'allgemein';
function bearbeiten(box,text,speichern,abbruch,extra){ // extra: [[beschriftung, speichern(t)|null, titel]] – null = ausgegraut
 const ta=el('textarea',{}),alt=[...box.childNodes];ta.value=text||'';
 const zu=()=>{if(abbruch)abbruch();else box.replaceChildren(...alt);nachholen()};
 const ok=(sp=speichern)=>{const t=ta.value.trim();if(!t){ta.focus();return}sp(t).then(d=>{if(!d||!d.ok)return;if(abbruch)abbruch();else box.replaceChildren();zeichnen()})};
 ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();ok()}else if(e.key==='Escape'){e.preventDefault();zu()}});
 box.replaceChildren(ta,el('div',{class:'kk'},el('span',{},'Strg+Enter speichern · Esc abbrechen'),
  el('span',{class:'knoepfe'},el('button',{onclick:zu},'abbrechen'),
   ...(extra||[]).map(([t,sp,ti])=>el('button',{title:ti||'',disabled:sp?null:'',onclick:()=>ok(sp)},t)),
   el('button',{class:'haupt',onclick:()=>ok()},extra?(RVW?'als Review-Kommentar':'an '+AG()[0]):'speichern'))));
 ta.focus();ta.setSelectionRange(ta.value.length,ta.value.length)}
function speichernAls(d){return post('/api/kommentar',d).then(r=>{const x=antwort(r);return x})}
function autoLaden(){[...RV.kommentare,...RV.hinweise].forEach(x=>{const d=x.datei!=null&&ds[x.datei];if(d&&d.querySelector('.spaet'))dateiLaden(d)})}
function uhr(iso){if(!iso)return'';const d=new Date(iso),hm=d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
 return d.toDateString()===new Date().toDateString()?hm:d.toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit'})+' '+hm}
function fadenBox(k,mitOrt){ // Gespräch: Verlauf wie im Messenger, eigene Nachrichten rechts
 const wer=k.an||'Claude',[st0,cl]=STATUS[k.status]||['?',''],st=st0.replace('Claude',wer),box=el('div',{class:'kbox km gs st-'+k.status+(k.status==='erledigt'?' erledigt':''),'data-id':k.id}),kn=el('span',{class:'knoepfe'});
 const offen=!LESEN&&!k.lesen;
 if(offen)kn.append(el('button',{onclick:()=>{const b=el('div',{class:'msg ich entwurf'});v.append(b);bearbeiten(b,'',t=>gsPost({aktion:'antworten',id:k.id,text:t}),()=>b.remove())}},'↩ antworten'),
  k.status==='erledigt'?el('button',{onclick:()=>gsPost({aktion:'oeffnen',id:k.id})},'wieder öffnen')
   :el('button',{title:'Gespräch als erledigt markieren',onclick:()=>gsPost({aktion:'erledigt',id:k.id})},'✓ erledigt'),
  el('button',{title:'ganzes Gespräch löschen',onclick:()=>{if(confirm('Ganzes Gespräch löschen?'))gsPost({aktion:'loeschen',id:k.id})}},'🗑'));
 const er=k.erledigt?el('span',{},'· erledigt von '+(k.erledigt.von==='claude'?(k.erledigt.wer||wer):'dir')+' '+uhr(k.erledigt.zeit)):null;
 box.append(el('div',{class:'kk'},el('span',{class:'badge '+cl},st),er,mitOrt?ortLink(k):null,kn));
 if(k.zeile_text&&k.problem)box.append(el('div',{class:'alt',title:'die Zeile, als der Kommentar geschrieben wurde'},'damals: '+k.zeile_text.trim()));
 const v=el('div',{class:'verlauf'});
 k.nachrichten.forEach(m=>{const ich=m.von==='ich',ent=ich&&!m.gesendet,mb=el('div',{class:'msg '+(ich?'ich':'claude')+(ent?' entwurf':'')});
  const haken=!ich?null:ent?el('span',{},'Entwurf'):el('span',{class:'haken'+(m.abgeholt?' abgeholt':''),
   title:m.abgeholt?'von '+wer+' abgeholt um '+uhr(m.abgeholt):'gesendet, noch nicht abgeholt'},m.abgeholt?'✓✓':'✓');
  const mk=el('div',{class:'mk'},el('b',{},ich?'Du':'🤖 '+(m.wer||wer)),el('span',{},uhr(m.gesendet||m.zeit)),haken);
  if(ent&&offen)mk.append(el('button',{onclick:()=>bearbeiten(mb,m.text,t=>gsPost({aktion:'aendern',id:k.id,nid:m.id,text:t}))},'✎'),
   el('button',{onclick:()=>gsPost({aktion:'loeschen',id:k.id,nid:m.id})},'🗑'));
  mb.append(mk,el('div',{class:'mt'},m.text));v.append(mb)});
 box.append(v);return box}
function kommentarBox(k,mitOrt){
 const [st,cl]=STATUS[k.status]||['?',''],box=el('div',{class:'kbox km'+(k.status==='loeschen'?' weg':''),'data-id':k.id}),kn=el('span',{class:'knoepfe'});
 if(LESEN||k.lesen);
 else if(k.status==='loeschen')kn.append(el('button',{onclick:()=>speichernAls({aktion:'wiederherstellen',id:k.id})},'wiederherstellen'));
 else kn.append(...(k.status==='weg'?[]:[el('button',{onclick:()=>bearbeiten(box,k.text,t=>speichernAls({aktion:'aendern',id:k.id,text:t}))},'✎ bearbeiten')]),
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
 FD().forEach(k=>{if(!platz(k,()=>fadenBox(k,false))&&!unter(k,()=>fadenBox(k,false)))allg.push(()=>fadenBox(k,true))});
 RV.hinweise.filter(h=>h.status==='offen'||(RV.zeigVerworfen&&h.status==='verworfen'))
  .forEach(h=>{if(!platz(h,()=>hinweisBox(h,false))&&!unter(h,()=>hinweisBox(h,false)))allg.push(()=>hinweisBox(h,true))});
 allgemein(allg);kliste();ls.forEach((a,i)=>{const z=a.querySelector('.kz');if(z)z.textContent=zahl[i]?'💬'+zahl[i]:''});
 const n=RV.kommentare.filter(k=>k.status!=='loeschen').length,offen=RV.hinweise.filter(h=>h.status==='offen').length;
 if(!RVW){gsStand();kh();return}
 gsStand(n+' Kommentar(e)'+(RV.ausstehend?' · '+RV.ausstehend+' noch nicht in GitLab':'')+(offen?' · '+offen+' Agent-Hinweis(e) offen':''));kh()}
const TITEL=document.title,fb=document.getElementById('feedback'),sst=document.getElementById('starten');
function gsStand(vorn){const f=FD(),z=s=>f.filter(k=>k.status===s).length,neu=z('antwort'),w=z('wartet'),e=GA();
 document.getElementById('rvstand').textContent=[vorn,f.length?f.length+' Gespräch(e)':null,e?e+(RVW?' Fragen-Entw':' Entw')+(e>1?'ürfe':'urf'):null,w?w+' wartet auf Antwort':null,
  neu?neu+' neue Antwort(en)':null,RV.horcht?'🎧 '+RV.horcht+' hört zu':null].filter(Boolean).join(' · ');
 if(!fb)return;fb.hidden=RVW&&!f.length;fb.disabled=!e;const fw=RVW?'Fragen senden':'Feedback senden';fb.textContent=e?fw+' ('+e+')':fw;sst.hidden=!RV.todo||!!RV.horcht;
 document.title=(neu?'('+neu+') ':'')+TITEL}
if(fb){
 fb.addEventListener('click',()=>{fb.disabled=true;meld.textContent='sendet …';post('/api/gespraech',{aktion:'senden'}).then(d=>{meld.textContent=d.text||'';
  if(d.review){Object.assign(RV,d.review);zeichnen()}else gsStand()})});
 sst.addEventListener('click',()=>{sst.disabled=true;post('/api/gespraech',{aktion:'starten'}).then(d=>{sst.disabled=false;meld.textContent=d.text||''})})}
function anKnoepfe(d){ // weitere Speichern-Knöpfe „an <Agent>“ (mit Review alle; sonst ist der erste „speichern“)
 const a=RVW?AG():AG().slice(1);if(!RVW&&!a.length)return undefined;
 return a.length?a.map(n=>['an '+n,t=>gsPost(Object.assign({},d,{aktion:'neu',an:n,text:t})),'Frage an '+n+' – bleibt privat, geht nicht nach GitLab'])
  :[['an Agent',null,'Kein Agent eingerichtet: [agenten] in der Einstellung oder „merge-train agent horchen“ in einer Session']]}
function allgemein(allg){
 let s=document.getElementById('allgemein');if(!s){s=el('section',{id:'allgemein'});document.querySelector('main').prepend(s)}
 const verw=RV.hinweise.filter(h=>h.status==='verworfen').length;
 s.replaceChildren(el('div',{class:'kk'},el('b',{},RVW?'Review':'Gespräch mit '+AG()[0]),el('span',{class:'sub'},allg.length?'außerhalb des Diffs / allgemein:':'Kommentare stehen an den Zeilen'),
  el('span',{class:'knoepfe'},verw?el('button',{onclick:()=>{RV.zeigVerworfen=!RV.zeigVerworfen;zeichnen()}},RV.zeigVerworfen?'verworfene ausblenden':verw+' verworfene Hinweise zeigen'):null,
   LESEN?null:el('button',{onclick:()=>{const b=el('div',{class:'kbox km'});s.append(b);bearbeiten(b,'',neuSpeichern({}),()=>b.remove(),anKnoepfe({}))}},RVW?'＋ allgemeiner Kommentar':'＋ allgemeine Frage'))),
  RV.ausserhalb?el('div',{class:'sub'},RV.ausserhalb+' weitere(r) Kommentar(e)/Hinweis(e) in Dateien, die diese Ansicht nicht ändert – siehe ganzer MR'):'');
 RV.quellen.forEach(q=>{const d=el('details',{class:'quelle'},el('summary',{},'🤖 '+(q.key||q.datei)+(q.reviewed_commit?' · geprüft '+q.reviewed_commit:'')+(q.reviewed_at?' am '+q.reviewed_at:'')+' · '+q.anzahl+' Hinweis(e)'),
  q.fehler?el('div',{class:'warn'},q.fehler):null,q.alt?el('div',{class:'warn'},'geprüft auf Stand '+q.reviewed_commit+', der MR steht auf '+MR.sha.slice(0,8)+' – Hinweise evtl. veraltet'):null,el('div',{},q.datei),q.notes?el('div',{class:'kt'},q.notes):null,
  q.failing_tests?el('div',{},el('b',{},'failing_tests: '),JSON.stringify(q.failing_tests,null,1)):null);
  if(q.fehler)d.open=true;s.append(d)});
 allg.forEach(f=>s.append(f()))}
document.addEventListener('click',e=>{const td=e.target.closest('main td.n,#popup td.n');if(!td||!td.textContent.trim())return; // Seite und Popup (ausgeliehene Datei)
 if(LESEN){meld.textContent='Nur-Lese-Ansicht: kommentieren im ganzen MR oder in „seit diesem“';return}
 const tr=td.closest('tr');if(!tr||!(tr.dataset.a||tr.dataset.b))return;
 const tab=tr.closest('table'),n=ds.indexOf(tr.closest('.datei'));let a=tr.dataset.a?+tr.dataset.a:null,b=tr.dataset.b?+tr.dataset.b:null;
 if(tab.classList.contains('sbs')&&tr.querySelector('.weg,.dazu,.nix')){if(td.cellIndex===0)b=null;else a=null}
 if(SEIT&&b==null){meld.textContent='In dieser Ansicht nur rechts (MR-Stand) kommentierbar';return}
 const box=el('div',{class:'kbox km'}),zr=einfuegen(tr,box,tab);
 bearbeiten(box,'',neuSpeichern({datei:n,a,b}),()=>zr.remove(),anKnoepfe({datei:n,a,b}))});
const abk=document.getElementById('abschliessen');
if(abk)abk.addEventListener('click',()=>{abk.disabled=true;meld.textContent='überträgt Entwürfe nach GitLab …';
 post('/api/abschliessen',{}).then(d=>{abk.disabled=false;
  meld.replaceChildren(d.text||'',d.web_url?el('a',{href:d.web_url,target:'_blank',rel:'noopener'},' → in GitLab prüfen ↗'):'');
  if(d.review){Object.assign(RV,d.review);zeichnen()}
  zugHolen()})});
setInterval(()=>{if(document.hidden)return;fetch('/api/stand?'+qs()).then(r=>r.json()).then(d=>{if(d.stand&&(d.stand!==RV.stand||meld.textContent===WEG))laden()})
 .catch(()=>{meld.textContent=WEG})},4000);
laden();
