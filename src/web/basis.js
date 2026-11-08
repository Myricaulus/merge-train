const ds=[...document.querySelectorAll('.datei')],ls=[...document.querySelectorAll('#liste a')],kopf=document.getElementById('kopf');
function kh(){document.documentElement.style.setProperty('--kopfh',kopf.offsetHeight+'px')}
kh();addEventListener('resize',kh);document.getElementById('commits').addEventListener('toggle',kh);
function aktuell(){const g=kopf.offsetHeight+20;let k=0;ds.forEach((d,j)=>{if(d.getBoundingClientRect().top<=g)k=j});return k}
let FEST=null;['wheel','touchmove','keydown','mousedown'].forEach(t=>addEventListener(t,()=>{FEST=null},{passive:true,capture:true}));
function markiere(){const k=FEST!=null&&ds[FEST]?FEST:aktuell();ls.forEach((a,j)=>a.classList.toggle('akt',j===k));const a=ls[k],nav=a&&a.closest('nav');
 if(nav){const r=a.getBoundingClientRect(),p=nav.getBoundingClientRect(),h=nav.querySelector('h2'),oben=p.top+(h?h.offsetHeight:0);
  if(r.top<oben)nav.scrollTop-=oben-r.top+4;else if(r.bottom>p.bottom)nav.scrollTop+=r.bottom-p.bottom+4}} // nur die Liste scrollen, nie das Fenster (sonst Rückkopplung mit dem Scroll-Event)
addEventListener('scroll',markiere,{passive:true});markiere();
function geh(k){if(!ds.length)return;k=Math.max(0,Math.min(ds.length-1,k));ds[k].open=true;ds[k].scrollIntoView({block:'start'})}
document.addEventListener('keydown',e=>{if(e.ctrlKey||e.altKey||e.metaKey||/INPUT|TEXTAREA/.test(e.target.tagName))return;
 const k=aktuell();
 if(e.key==='j'||e.key==='ArrowRight'){e.preventDefault();geh(ds[k]&&ds[k].getBoundingClientRect().top>kopf.offsetHeight+30?k:k+1)}
 else if(e.key==='k'||e.key==='ArrowLeft'){e.preventDefault();geh(ds[k]&&ds[k].getBoundingClientRect().top<kopf.offsetHeight-5?k:k-1)}
 else if(e.key==='i'){if(!document.body.classList.contains('inline'))inlBauen();document.body.classList.toggle('inline');try{localStorage.inline=document.body.classList.contains('inline')?1:''}catch(_){}}
 else if(e.key==='z'){const zu=ds.some(d=>d.open);ds.forEach(d=>d.open=!zu)}
 else if(e.key==='c'){const c=document.getElementById('commits');c.open=!c.open}});
function inlBauen(nur){ // Inline-Tabelle aus der Tabelle nebeneinander bauen (spart die Hälfte der Seite)
 const neu=[];
 (nur?[nur]:ds).forEach(d=>{const s=d.querySelector('table.sbs');if(!s||d.querySelector('table.inl'))return;
  const out=[],weg=[],dazu=[],leeren=()=>{out.push(...weg,...dazu);weg.length=dazu.length=0};
  const zeile=(a,b,h,cl,kl)=>'<tr'+(kl?' class="'+kl+'"':'')+(a!=null?' data-a="'+a+'"':'')+(b!=null?' data-b="'+b+'"':'')+'><td class="n">'+(a==null?'':a)
   +'</td><td class="n">'+(b==null?'':b)+'</td><td class="c'+(cl?' '+cl:'')+'">'+h+'</td></tr>';
  for(const r of s.rows){const cl=r.classList;
   if(cl.contains('kr'))continue;
   if(cl.contains('hk')){leeren();out.push('<tr class="hk"><td></td><td></td><td>'+r.lastElementChild.innerHTML+'</td></tr>');continue}
   if(cl.contains('lu')){leeren();const x=r.dataset;out.push('<tr class="lu" data-von="'+x.von+'" data-bis="'+x.bis+'" data-d="'+x.d+'"><td class="n"></td><td colspan="2"></td></tr>');continue}
   const c=r.cells;if(c.length<4)continue;
   const w=c[1].classList.contains('weg'),z=c[3].classList.contains('dazu');
   if(!w&&!z&&!c[1].classList.contains('nix')){leeren();out.push(zeile(r.dataset.a,r.dataset.b,c[3].innerHTML,'',r.className));continue}
   if(w)weg.push(zeile(r.dataset.a,null,c[1].innerHTML,'weg'));
   if(z)dazu.push(zeile(null,r.dataset.b,c[3].innerHTML,'dazu'))}
  leeren();const t=document.createElement('table');t.className='inl';
  t.innerHTML='<colgroup><col class="cn"><col class="cn"><col></colgroup><tbody>'+out.join('')+'</tbody>';s.after(t);neu.push(t)});
 if(neu.length)document.dispatchEvent(new CustomEvent('inl',{detail:neu}))}
try{if(localStorage.inline){inlBauen();document.body.classList.add('inline')}}catch(_){}
