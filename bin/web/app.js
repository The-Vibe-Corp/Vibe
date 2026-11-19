
const OC_URL=(document.querySelector('meta[name="vibe-opencode-url"]')||{}).content||'';
/* AP13: Der Token kommt nur aus dem #t=-Hash und wird ausschließlich im
   Speicher gehalten. Beim ersten Laden tauscht boot() ihn gegen einen
   Session-Cookie ein (POST /api/login), damit ein Neuladen ohne Hash
   angemeldet bleibt. Der frühere Weg über sessionStorage entfällt bewusst:
   Er hielt das Geheimnis dauerhaft im Browser-Speicher. */
const T=(()=>{const m=location.hash.match(/t=([^&]+)/);if(m)history.replaceState(null,'',location.pathname);return m?m[1]:''})();
function errText(j,status){const e=j&&j.error;return (e&&(e.message||e))||(j&&j.message)||('HTTP '+status)}
async function api(p,body){const o=body?{method:'POST',headers:{'X-Token':T,'Content-Type':'application/json'},body:JSON.stringify(body)}:{headers:{'X-Token':T}};
 const r=await fetch(p,o);const j=await r.json().catch(()=>({}));if(!r.ok&&!body)throw new Error(errText(j,r.status));return j}
function el(t,a={},...c){const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='on')for(const[ev,f]of Object.entries(v))e.addEventListener(ev,f);else if(k==='class')e.className=v;else if(k==='value')e.value=v;else e.setAttribute(k,v)}
 for(const x of c.flat())if(x!==null&&x!==undefined&&x!==false)e.append(x.nodeType?x:document.createTextNode(String(x)));return e}
const main=document.getElementById('main'),nav=document.getElementById('nav'),srvbox=document.getElementById('srv');let tab='projects',es=null,timer=null,LOG=null;
function showErr(e){main.replaceChildren(el('div',{class:'card err'},el('b',{class:'bad'},'Fehler: '),String(e&&e.message||e)),el('button',{class:'b',on:{click:()=>setTab('projects')}},'← zur Projektliste'))}
function setTab(t){exitLogFull();LOG=null;DTAB='arbeit';tab=t;if(es){es.close();es=null}clearInterval(timer);[...nav.children].forEach(b=>b.classList.toggle('on',b.dataset.t===t));Promise.resolve(({projects,agents,mcp,env,costs,security}[t])()).catch(showErr);header()}
[['projects','Projekte'],['agents','Agenten & Modelle'],['mcp','MCP-Tools'],['env','Umgebung'],['costs','Kosten'],['security','Zugriffssicherheit']].forEach(([k,l])=>nav.append(el('button',{'data-t':k,on:{click:()=>setTab(k)}},l)));
const toastBox=el('div',{id:'toasts',class:'toasts',role:'status','aria-live':'polite','aria-atomic':'false'});
document.body.append(toastBox);
function toast(m){const t=el('div',{class:'toast'},el('span',{class:'toasttext'},String(m)),el('button',{class:'b x',type:'button','aria-label':'Meldung schließen',title:'Meldung schließen',on:{click:()=>t.remove()}},'×'));
 toastBox.prepend(t);while(toastBox.children.length>4)toastBox.lastElementChild.remove();setTimeout(()=>t.remove(),8000)}
/* Rückfragen (F16): Der Agent stellt eine Frage, das Dashboard zeigt sie mit
   den angebotenen Möglichkeiten und schreibt die Antwort zurück. */
const qbox=document.getElementById('questions'),qBaseTitle=document.title;
let qSeen=new Set(),qSig=null;
function questionCard(q){
 const send=body=>answerQuestion(q.id,body);
 const opts=(q.options||[]).map((text,i)=>el('button',{class:'b'+(i===0?' p':''),type:'button','data-option':String(i),on:{click:()=>send({option:i})}},text));
 let free=null;
 if(q.free_text!==false){
  const inp=el('input',{type:'text','aria-label':'Eigene Antwort zu '+q.id,placeholder:'Eigene Antwort …',maxlength:'4000'});
  const go=()=>{const text=inp.value.trim();if(!text){inp.focus();return}send({text})};
  inp.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();go()}});
  free=el('div',{class:'qfree'},inp,el('button',{class:'b p',type:'button',on:{click:go}},'Antwort senden'));
 }
 const auto=q.project?el('button',{class:'b',type:'button',title:'Der Agent entscheidet ohne Antwort selbst und dokumentiert die Entscheidung',on:{click:()=>setAutonomous(q.project)}},'Autonom entscheiden'):null;
 return el('section',{class:'qcard','data-question':q.id,'data-id':q.id},el('div',{class:'qhead'},el('span',{class:'pill warn'},'Rückfrage'),q.project?el('span',{class:'mut'},q.project):null,q.agent?el('span',{class:'mut'},'Agent: '+q.agent):null),el('p',{class:'qtext'},q.text),opts.length?el('div',{class:'qopts'},...opts):null,free,auto?el('div',{class:'qopts'},auto):null);
}
function showQuestions(list){
 const fresh=list.filter(q=>!qSeen.has(q.id));qSeen=new Set(list.map(q=>q.id));
 const sig=JSON.stringify(list.map(q=>[q.id,q.project,q.agent,q.text,q.options,q.free_text]));
 if(sig!==qSig){qSig=sig;qbox.replaceChildren(...list.map(questionCard));qbox.hidden=!list.length}
 document.title=list.length?'('+list.length+') '+qBaseTitle:qBaseTitle;
 if(fresh.length)toast('Neue Rückfrage'+(fresh[0].project?' ('+fresh[0].project+')':'')+': '+fresh[0].text);
}
async function answerQuestion(id,body){
 try{const r=await api('/api/questions',Object.assign({action:'answer',id},body));
  if(r.ok){toast(r.message);showQuestions(r.questions||[])}else toast(r.message||'Antwort abgelehnt')}catch(e){toast('Antwort nicht gesendet: '+String(e&&e.message||e))}
}
async function setAutonomous(name){
 try{const r=await api('/api/autonomous',{name,action:'on'});toast(r.message);
  if(r.ok)showQuestions((await api('/api/questions')).questions||[])}catch(e){toast('Autonomer Modus nicht geändert: '+String(e&&e.message||e))}
}
async function pollQuestions(){try{showQuestions((await api('/api/questions')).questions||[])}catch(e){}}
pollQuestions();setInterval(pollQuestions,3000);
function askInline(btn,q,okLabel,run){if(!btn.isConnected)return;
 const bar=btn.parentNode;if(bar&&bar.querySelector('.confirm'))return;
 const back=()=>{group.remove();btn.hidden=false;if(btn.isConnected)btn.focus()};
 const yes=el('button',{class:'b '+(btn.classList.contains('d')?'d':'p'),type:'button',on:{click:async()=>{yes.disabled=true;no.disabled=true;try{await run()}catch(e){showErr(e)}finally{back()}}}},okLabel);
 const no=el('button',{class:'b',type:'button',on:{click:back}},'Abbrechen');
 const group=el('span',{class:'confirm',role:'group','aria-label':q},el('span',{class:'mut'},q),yes,no);
 group.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();back()}});
 btn.hidden=true;btn.after(group);yes.focus()}
function setLogFull(on){if(!LOG)return;LOG.card.classList.toggle('full',on);document.body.classList.toggle('logfull',on);LOG.button.textContent=on?'Verkleinern':'Vergrößern';if(on)LOG.pre.style.height='auto';else LOG.fit()}
function exitLogFull(){if(LOG&&LOG.card.classList.contains('full'))setLogFull(false)}
window.addEventListener('keydown',e=>{if(e.key==='Escape')exitLogFull()});
window.addEventListener('resize',()=>{if(LOG)LOG.fit()});
const GOOD=['sehr schnell','schnell','gering','geeignet','gut','ja'],MID=['mittel','bedingt','unklar'],BAD=['langsam','hoch','eingeschränkt','nicht empfohlen','nein'];
function badge(v){v=v||'?';return el('span',{class:'pill '+(GOOD.includes(v)?'ok':MID.includes(v)?'warn':BAD.includes(v)?'bad':'mut')},v)}
async function header(){try{const s=await api('/api/server');
 const isPi=(s.harness||'opencode')==='pi';
 const quit=el('button',{class:'b quit',title:isPi?'Beendet diese App (das Dashboard), nicht laufende Agentenläufe in tmux':'Beendet diese App (das Dashboard), nicht opencode',on:{click:()=>askInline(quit,'Dashboard (diese App) beenden? Laufende Agentenläufe in tmux laufen weiter.','Ja, beenden',async()=>{await api('/api/shutdown',{});
   main.replaceChildren(el('div',{class:'card'},'Dashboard beendet. Neu starten im Terminal: vibe ui'));srvbox.replaceChildren()})}},'Dashboard beenden');
 srvbox.replaceChildren(el('span',{class:'ok'},'Harness: '+(s.harness||'?')),el('span',{class:'sep'}),
  ...((isPi?[el('span',{class:'mut'},'Pi: Agentenläufe laufen ohne opencode-Server'),el('span',{class:'sep'})
      ]:[el('span',{class:s.up?'ok':'mut'},'opencode-Server: '+(s.up?'an':'aus')),
      el('button',{class:'b',title:'Startet/stoppt nur den gemeinsamen opencode-Server (Weboberfläche), nicht dieses Dashboard',on:{click:async()=>{toast((await api('/api/server',{action:s.up?'stop':'start'})).message);header()}}},s.up?'opencode stoppen':'opencode starten'),el('span',{class:'sep'})])),
  quit)}catch(e){}}
/* F20: Welche Alternative gilt? Die Karten richten ihre Hinweise und
   steuerbaren Elemente nach der aktiv gewählten Harness-Auswahl aus. */
const harnessSelected=async()=>{try{const s=await api('/api/server');return (s&&s.harness)||'opencode'}catch(e){return 'opencode'}};
async function rootsCard(){const rs=await api('/api/roots');const inp=el('input',{placeholder:'/var/mnt/data/.../mein-entwicklungsordner'});
 const rows=rs.map(r=>el('div',{class:'bar'},el('b',{},r.path),el('span',{class:'mut'},r.projects.length+' Projekt(e)'+(r.projects.length?': '+r.projects.join(', '):'')),
  r.fixed?el('span',{class:'pill'},'Standard'):el('button',{class:'b d',on:{click:async()=>{await api('/api/roots',{action:'remove',path:r.path});setTab('projects')}}},'entfernen')));
 return el('div',{class:'card'},el('b',{},'Entwicklungsordner'),...rows,el('label',{},'Ordner hinzufügen und Projekte darin einlesen (jeder Unterordner mit .git)'),
  el('div',{class:'bar'},inp,el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/roots',{action:'add',path:inp.value});toast(r.message);setTab('projects')}}},'Einlesen'),
   el('button',{class:'b',on:{click:async()=>{await api('/api/roots',{action:'scan'});setTab('projects')}}},'Neu einlesen')))}
async function projects(){
 // AP13: Kein clientseitiger Token-Zwang mehr. Die Berechtigung prüft der
 // Server (Session-Cookie oder Token); ohne Berechtigung entscheidet boot()
 // über die Anmeldekarte, und die Anfrage scheitert strukturiert.
 const render=async()=>{const ps=await api('/api/projects');
  const tb=el('table',{},el('tr',{},...['Projekt','Typ','Branch','Offen','Änd.','Lauf','Letzter Commit'].map(h=>el('th',{},h))));
  ps.forEach(p=>tb.append(el('tr',{class:'row',on:{click:()=>detail(p.name).catch(showErr)}},el('td',{},p.name,p.init?null:el('span',{class:'warn'},' ●')),el('td',{},p.type),el('td',{},p.branch),
   el('td',{class:p.open?'warn':'ok'},p.open),el('td',{},p.dirty),el('td',{},el('span',{class:'pill '+(p.running?'run':'')},p.running?'läuft':'-'),p.pause_after?el('span',{class:'pill warn',title:'Nach dem aktuellen Arbeitspaket wird kein neues gestartet'},' Pause'):null),el('td',{class:'mut'},p.last))));
  const rc=await rootsCard();
  main.replaceChildren(el('div',{class:'card'},ps.length?tb:el('span',{class:'mut'},'Keine Projekte gefunden. Entwicklungsordner unten hinzufügen.'),ps.some(p=>!p.init)?el('div',{class:'warn',style:'margin-top:8px'},'● = noch nicht für vibe vorbereitet (Projekt öffnen → „Für vibe vorbereiten“)'):null),rc,newForm())};
 await render();timer=setInterval(()=>{if(tab==='projects'&&!document.activeElement.matches('input,textarea,select'))render().catch(()=>{})},5000)}
function newForm(){const types=el('select',{});api('/api/types').then(t=>t.forEach(x=>types.append(el('option',{},x))));
 const nm=el('input',{placeholder:'projektname (a-z, 0-9, -)'}),tp=el('input',{placeholder:'nur Android: Vorlage aus "android create --list"'});
 const gu=el('input',{placeholder:'https://github.com/owner/name.git','aria-label':'GitHub-Adresse zum Auschecken'});
 return el('div',{class:'card',id:'nf'},el('b',{},'Neues Projekt (im Standardordner)'),el('div',{class:'grid'},el('div',{},el('label',{},'Name'),nm),el('div',{},el('label',{},'Typ'),types)),el('label',{},'Android-Vorlage'),tp,
  el('label',{},'Oder aus GitHub auschecken'),gu,
  el('div',{class:'mut'},'Nach dem Anlegen öffnet der Projektassistent die fachlichen Schritte und legt SPEC.md sowie fehlende Grundlagen an. Beim Auschecken gilt die lokale vibe-Konfiguration dieses Rechners; aktive Agenten werden auf die lokal konfigurierten Agenten angepasst.'),
  el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/new',{name:nm.value,type:types.value,tpl:tp.value});toast(r.message);if(r.ok){DTAB='assistent';detail(nm.value).catch(showErr)}else setTab('projects')}}},'Anlegen und Assistent öffnen'),
   el('button',{class:'b',type:'button',on:{click:async()=>{const r=await api('/api/clone',{url:gu.value,name:nm.value});toast(r.message||'');if(r.ok&&r.project){await projects();setTimeout(()=>detail(r.project).catch(showErr),800)}else setTab('projects')}}},'Aus GitHub auschecken')))}
let DTAB='arbeit';
const DTABS=[['arbeit','Arbeit'],['ausgabe','Ausgabe'],['assistent','Assistent'],['einstellungen','Einstellungen']];
function tile(k,v,tone){return el('div',{class:'tile'},el('div',{class:'k'},k),el('div',{class:'v'+(tone?' '+tone:'')},String(v)))}
function tabPanel(key,...c){return el('section',{class:'tabpanel',role:'tabpanel',id:'panel-'+key,'data-panel':key,'aria-labelledby':'tab-'+key,hidden:''},...c)}
function showDetailTab(key,panels,btns,focus){DTAB=key;
 DTABS.forEach(([k])=>{const on=k===key;btns[k].setAttribute('aria-selected',on?'true':'false');btns[k].tabIndex=on?0:-1;panels[k].hidden=!on});
 if(key!=='ausgabe')exitLogFull();if(key==='ausgabe'&&LOG&&LOG.card.isConnected)LOG.fit();if(focus&&btns[key])btns[key].focus()}
function detailTabs(panels){const btns={},list=el('div',{class:'tabs',role:'tablist','aria-label':'Projektbereiche'});
 DTABS.forEach(([k,label])=>{const b=el('button',{type:'button',role:'tab',id:'tab-'+k,'aria-controls':'panel-'+k},label);
  b.addEventListener('click',()=>showDetailTab(k,panels,btns));btns[k]=b;list.append(b)});
 list.addEventListener('keydown',e=>{const keys=DTABS.map(d=>d[0]);const i=Math.max(0,keys.indexOf(DTAB));let n=null;
  if(e.key==='ArrowRight')n=(i+1)%keys.length;else if(e.key==='ArrowLeft')n=(i-1+keys.length)%keys.length;
  else if(e.key==='Home')n=0;else if(e.key==='End')n=keys.length-1;else return;
  e.preventDefault();showDetailTab(keys[n],panels,btns,true)});
 showDetailTab(DTAB in panels?DTAB:'arbeit',panels,btns);
 return {list,btns}}
async function detail(name){
 clearInterval(timer);if(es){es.close();es=null}exitLogFull();LOG=null;window.scrollTo(0,0);
 const d=await api('/api/project?name='+encodeURIComponent(name));
 const isPi=(await harnessSelected())==='pi';
 const runPill=el('span',{id:'runstate',class:'pill '+(d.running?'run':''),title:d.running?'Der Paket-Läufer ist aktiv.':'Der Agentenlauf ist beendet.'},d.running?'läuft':'gestoppt');
 const refreshRun=async()=>{const s=await api('/api/run-state?name='+encodeURIComponent(name));
  runPill.textContent=s.running?'läuft':'gestoppt';runPill.className='pill '+(s.running?'run':'');
  runPill.title=s.running?'Der Paket-Läufer ist aktiv.':'Der Agentenlauf ist beendet.';return s};
 const act=(p,b)=>async()=>{const r=await api(p,b);toast(r.message);detail(name).catch(showErr)};
 let openTab=()=>{};
 const itemsCard=openPackagesCard(d,name);
 const fact=(k,v)=>el('div',{class:'factrow'},el('span',{class:'mut'},k),el('span',{},String(v)));
 const factsCard=el('div',{class:'card'},el('b',{},'Projekt'),fact('Pfad',d.path),fact('Typ',d.type),fact('Branch',d.branch),fact('Letzter Commit',d.last||'—'),fact('Vorbereitet',d.init?'ja':'nein'));
 const startVerify=mode=>async()=>{openTab('ausgabe');const r=await api('/api/verify',{name,mode});toast(r.message);if(r.ok)stream('verify')};
 const checksCard=el('div',{class:'card'},el('b',{},'Prüfungen'),
  el('div',{class:'mut'},'quick prüft Struktur und Sicherheit, package führt die Paketprüfung aus (VERIFY_PACKAGE), full zusätzlich Unit- und Browsertests. Die Ausgabe erscheint im Bereich „Ausgabe“.'),
  el('div',{class:'bar'},el('button',{class:'b',type:'button',on:{click:startVerify('quick')}},'Prüfung quick'),
   el('button',{class:'b',type:'button',on:{click:startVerify('package')}},'Prüfung package'),
   el('button',{class:'b',type:'button',on:{click:startVerify('full')}},'Prüfung full'),
   isPi?null:el('a',{href:OC_URL,target:'_blank'},'opencode-Weboberfläche')));
 const tsel=el('select',{});api('/api/types').then(t=>t.forEach(x=>{const o=el('option',{},x);if(x===d.type)o.selected=true;tsel.append(o)}));
 const initCard=d.init?null:el('div',{class:'card warnbox'},el('b',{class:'warn'},'Noch nicht für vibe vorbereitet'),el('div',{class:'mut'},'Ergänzt fehlende Dateien (FEEDBACK.md, TICKETS.md, AGENTS.md, .vibe/project.env). Vorhandenes wird nie überschrieben, es wird nichts committet.'),
  el('div',{class:'bar'},tsel,el('button',{class:'b p',type:'button',on:{click:act('/api/init',{name,type:tsel.value})}},'Für vibe vorbereiten')));
 const head=el('div',{class:'bar detailbar'},
  el('button',{class:'b',type:'button',on:{click:()=>setTab('projects')}},'← zurück'),
  el('div',{class:'dhead'},el('h2',{},name),runPill,el('span',{class:'mut dmeta',title:d.path},d.type+' · '+d.branch+' · '+d.dirty+' Änderungen · '+d.path)),
  el('div',{class:'bar dactions'},
   d.dirty?el('button',{class:'b',type:'button',on:{click:function(){askInline(this,'Nicht committete Änderungen bleiben unverändert. Lauf trotzdem starten?','Trotz Änderungen starten',async()=>{const r=await api('/api/run',{name,keep_changes:true});toast(r.message);detail(name).catch(showErr)})}}},'Trotz Änderungen starten'):null,
   el('button',{class:'b p',type:'button',on:{click:act('/api/run',{name})}},'Agentenlauf starten'),el('button',{class:'b',type:'button',on:{click:act('/api/stop',{name})}},'Stoppen')));
 const tiles=el('div',{class:'tiles'},tile('Offene Arbeitspakete',d.items.length,d.items.length?'warn':'ok'),tile('Änderungen',d.dirty,d.dirty?'warn':'ok'),tile('Branch',d.branch,'small'),tile('Letzter Commit',d.last||'—','small'));
 const L=logView(d,()=>stream('run'));
 /* B11: Die Ausgabeansicht wird von Grund auf neu aufgebaut. Sie zeigt den
    Hauptagenten und jeden laufenden Subagenten gleichzeitig; beendete
    Subagenten verschwinden. Die frühere Protokollkarte bleibt nur als
    Rückfall für Projekte ohne Agentenlauf (und für Prüfungsläufe) bestehen. */
 const O=outputView(name,d,isPi);
 const sessionsCardView=await sessionsCard(name);
 const ausgabePanel=tabPanel('ausgabe');
 let outputMode='';
 let outputPinned='';
 function setOutputMode(mode){
  if(mode===outputMode)return;
  outputMode=mode;
  ausgabePanel.classList.toggle('bv-agent',mode==='agent');
  if(mode==='agent')ausgabePanel.replaceChildren(O.card);else ausgabePanel.replaceChildren(L.card);
  if(mode==='legacy')L.fit();else O.fit()}
 const panels={arbeit:tabPanel('arbeit',tiles,el('div',{class:'grid'},
   el('div',{},itemsCard,ticketCard(d,name),ticketFormCard(d,name),feedbackCard(d,name),bugFormCard(d,name),feedbackFormCard(d,name)),
   el('div',{},pauseCard(d,name),sessionsCardView,autonomousCard(d,name),checksCard,factsCard))),
  ausgabe:ausgabePanel,
  assistent:tabPanel('assistent',guideCard(name)),
  einstellungen:tabPanel('einstellungen',settingsPanel(d,name,isPi))};
 const tabs=detailTabs(panels);
 openTab=k=>showDetailTab(k,panels,tabs.btns);
 main.replaceChildren(...[head,initCard,tabs.list,panels.arbeit,panels.ausgabe,panels.assistent,panels.einstellungen].filter(Boolean));
 setOutputMode('legacy');
 let streamKind='run';
 function stream(kind){if(es)es.close();streamKind=kind;L.clear();O.clearMain();
  if(kind==='verify'){outputPinned='verify';setOutputMode('legacy')}else{outputPinned='';}
  es=new EventSource('/api/stream?name='+encodeURIComponent(name)+'&kind='+kind+'&t='+encodeURIComponent(T));
  es.onmessage=ev=>{const text=JSON.parse(ev.data).join('\n')+'\n';L.feed(text);O.feedMain(text)}}
 function applyAgents(data){
  if(outputPinned==='verify'){setOutputMode('legacy');return}
  const running=!!(data&&data.running),session=String((data&&data.session)||'');
  setOutputMode(running||session?'agent':'legacy');
  O.sync(data)}
 async function pollAgents(){try{applyAgents(await api('/api/subagents?name='+encodeURIComponent(name)))}catch(e){}}
 stream('run');refreshRun().catch(()=>{});pollAgents();
 timer=setInterval(()=>{refreshRun().catch(()=>{});pollAgents()},2000)}
function pauseCard(d,name){
 const active=!!d.pause_after;
 const btn=el('button',{class:'b'+(active?' p':''),on:{click:async()=>{const r=await api('/api/pause',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Pause aufheben':'Nach aktuellem Paket anhalten');
 return el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Arbeitspaket-Pause'),el('span',{class:'pill '+(active?'warn':'mut')},active?'Pause angefordert':'keine Pause'),btn),
  el('div',{class:'mut'},'Der laufende Agent wird nicht unterbrochen. Nach dem aktuellen Arbeitspaket startet der Läufer kein neues Paket; die Anforderung gilt einmalig und wird beim Anhalten verbraucht.'))}
function autonomousCard(d,name){
 const active=!!d.autonomous;
 const btn=el('button',{class:'b'+(active?'':' p'),type:'button',on:{click:async()=>{const r=await api('/api/autonomous',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Autonomen Modus ausschalten':'Autonomen Modus einschalten');
 return el('div',{class:'card',id:'autonomous'},el('div',{class:'bar'},el('b',{},'Autonomer Modus'),el('span',{class:'pill '+(active?'warn':'mut')},active?'aktiv':'aus'),btn),
  el('div',{class:'mut'},'Ist der Modus aktiv, entscheidet der Agent ohne Antwort des Nutzers selbst und dokumentiert die Entscheidung als Antwort auf seine Rückfrage. Die Einstellung lässt sich auch während eines Laufs ändern und gilt nur für dieses Projekt.'))}
/* AP19: Erfasste Sessions im Projektpanel. Die Karte lädt die Liste einmalig
   beim Öffnen (kein Polling) und zeigt Zustand, Agent und lesbare Zeit. */
function sessionTone(state){
  return state==='running'?'run':state==='finished'?'ok':state==='aborted'?'warn':state==='failed'?'bad':'mut'}
function sessionTime(value){
  const n=Number(value);if(!Number.isFinite(n)||n<=0)return '—';
  const d=new Date(n*1000),p=x=>String(x).padStart(2,'0');
  return p(d.getDate())+'.'+p(d.getMonth()+1)+'.'+d.getFullYear()+' '+p(d.getHours())+':'+p(d.getMinutes())}
async function sessionsCard(name){
  const card=el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Sessions')));
  let data;
  try{data=await api('/api/sessions?name='+encodeURIComponent(name))}
  catch(e){card.append(el('div',{class:'mut'},'Sessions konnten nicht geladen werden: '+String(e&&e.message||e)));return card}
  const list=Array.isArray(data&&data.sessions)?data.sessions:[];
  const canResume=!!(data&&data.resume_supported)&&!(data&&data.running);
  if(!list.length)card.append(el('div',{class:'mut'},'Noch keine erfassten Sessions.'));
  for(const s of list){
    const btn=canResume?el('button',{class:'b',type:'button','aria-label':'Session '+s.session+' fortsetzen',on:{click:async()=>{
      try{const r=await api('/api/sessions',{name,session:s.session,action:'continue'});
        toast(r&&r.ok?((r.message)||'Fortsetzen gestartet.'):'Fortsetzen abgelehnt: '+((r&&r.message)||'Unbekannter Grund.'))}
      catch(e){toast('Fortsetzen nicht gestartet: '+String(e&&e.message||e))}
    }}},'Fortsetzen'):null;
    card.append(el('div',{class:'bar','data-session':String(s.session)},
      el('span',{class:'pill '+sessionTone(s.state)},s.state_label||s.state||'?'),
      el('span',{},' '+s.session),
      el('span',{class:'mut'},s.agent||'?'),
      el('span',{class:'mut'},sessionTime(s.last_seen)),btn));
  }
  if(list.length&&data&&data.resume_supported===false)
    card.append(el('div',{class:'mut'},'Fortsetzen ist bei Pi nicht möglich (--no-session): Pi läuft ohne fortsetzbare Session.'));
  return card}
/* AP7: Einstellungs-Tab neu gegliedert. Wichtiges (Agenten) steht offen oben,
   optionale Bereiche sind als sichtbare Aufklapunkte eingeklappt. Die
   Abschnittsleiste zeigt den Zustand je Bereich und springt bei Klick dorthin,
   sodass der Standardzustand ohne Scrollen bedienbar bleibt. */
function settingsSection(id,title,open,body){
 return el('details',{class:'card seccard',id,...(open?{open:'open'}:{})},
  el('summary',{},el('span',{},title)),el('div',{class:'secbody'},body))}
function sandboxStatus(s){
 const active=!!(s&&s.enabled),missing=(s&&s.missing_tools)||[];
 const state=!active?'aus':(s.error?'Fehler':(!s.bwrap?'bubblewrap fehlt':(missing.length?'Werkzeuge fehlen':'bereit')));
 const tone=!active?'mut':(s.error||!s.bwrap||missing.length?'bad':'ok');
 return {state,tone}}
function settingsPanel(d,name,isPi){
 const g=d.github||{enabled:false};
 const sandbox=sandboxStatus(d.sandbox);
 const zustand={agenten:'…',
  rechte:d.write_dirs_error?'Fehler':(d.write_dirs_custom?(d.write_dirs.length+' Verzeichnisse'):'Standardliste'),
  sandbox:sandbox.state,github:g.enabled?'aktiv':'aus'};
 const tone=key=>{
  if(key==='agenten')return 'mut';
  if(key==='rechte')return zustand.rechte==='Fehler'?'bad':'mut';
  if(key==='sandbox')return sandbox.tone;
  return g.enabled?'ok':'mut'};
 /* F29: Die Priorisierung ist in der Maske „Arbeit" zu Hause (Karte
    „Offene Arbeitspakete") und hat keinen Abschnitt mehr in Einstellungen. */
 const chips={},sections={};
 for(const[key,label] of [['agenten','Agenten'],['rechte','Schreibrechte'],['sandbox','Sandbox'],['github','Git & GitHub']]){
  chips[key]=el('button',{class:'b settingschip',type:'button','data-goto':key,
   on:{click:()=>to(key)},
   title:'Öffnet den Abschnitt „'+label+'“'},el('span',{},label),
   el('span',{class:'pill '+tone(key)},zustand[key]))}
 const to=key=>{const sec=sections[key];if(!sec)return;
  if(sec.tagName==='DETAILS')sec.open=true;sec.scrollIntoView({block:'start'})}
 const agentPill=chips.agenten.querySelector('.pill');
 const agentsSec=projectAgentsCard(name,(text,t)=>{agentPill.textContent=text;
  if(t)agentPill.className='pill '+t});
 const rechteSec=settingsSection('settings-rechte','Schreibrechte (Agenten)',false,rightsBody(d,name));
 const sandboxSec=settingsSection('sandbox','Sandbox (optional)',false,sandboxBody(d,name,isPi));
 const githubSec=settingsSection('github','Git & GitHub (optional)',false,githubBody(d,name));
 sections.agenten=agentsSec;sections.rechte=rechteSec;sections.sandbox=sandboxSec;sections.github=githubSec;
 return el('div',{class:'settingsstack'},
  el('div',{class:'settings-nav','aria-label':'Einstellungsbereiche'},...Object.values(chips)),
  agentsSec,rechteSec,sandboxSec,githubSec)}
function projectAgentsCard(name,onPill){
 const body=el('div',{},el('span',{class:'mut'},'Lade Agenten …'));
 let showUnconfigured=false;
 const rowFor=(data,a)=>{
  const cb=el('input',{type:'checkbox','data-configure':a.name,'aria-label':'Agent '+a.name+' konfigurieren'});
  cb.checked=!!a.configured;
  if(a.is_vibe){cb.checked=true;cb.disabled=true}
  cb.addEventListener('change',async()=>{const r=await api('/api/project-agents',{name,agent:a.name,selected:cb.checked});
   toast(r.message);if(r.ok)load().catch(showErr);else cb.checked=!!a.configured});
  const mo=modelSelect(data.models,data.info,a.override,'— Standard aus Agentendatei —');
  mo.setAttribute('data-model-override',a.name);mo.setAttribute('aria-label','Modell für '+a.name);
  mo.addEventListener('change',async()=>{const r=await api('/api/project-agents',{name,agent:a.name,model:mo.value});
   toast(r.message);if(r.ok)load().catch(showErr)});
  return el('tr',{'data-project-agent':a.name,'data-configured':a.configured?'ja':'nein'},
   el('td',{},cb),
   el('td',{},a.name,a.is_vibe?el('span',{class:'pill ok'},' vibe'):null),
   el('td',{'data-aufgabe':a.name},a.description||'—'),
   el('td',{class:'mut','data-ergebnis':a.name},a.result||'—'),
   el('td',{'data-erlaubt':a.name},allowedLabel(a)),
   el('td',{class:'mut','data-wirksam':a.name},a.effective_model||a.model||'—'),
   el('td',{},mo))};
 const rowsCard=(data)=>{
  const visible=data.agents.filter(a=>showUnconfigured||a.configured||a.is_vibe).map(a=>rowFor(data,a));
  const hidden=data.agents.filter(a=>!a.configured&&!a.is_vibe).length;
  const toggle=el('input',{type:'checkbox','data-toggle':'unconfigured','aria-label':'Nicht konfigurierte Agenten anzeigen'});
  toggle.checked=showUnconfigured;
  toggle.addEventListener('change',()=>{showUnconfigured=toggle.checked;rowsCard(data)});
  const parts=[
   el('div',{class:'mut'},'Projekte verwenden ausschließlich systemweite Agenten. Standardmäßig ist nur der Vibe-Agent konfiguriert; weitere Agenten lassen sich einblenden und auswählen. Das Modell gilt nur für dieses Projekt und ändert die Agentendatei nicht.'),
   el('label',{style:'margin:6px 0'},toggle,' Nicht konfigurierte Agenten anzeigen ('+hidden+')'),
   el('div',{class:'tablewrap'},el('table',{},el('tr',{},...['Aktiv','Agent','Aufgabe','Ergebnis','Subagenten','Wirksames Modell','Modell für dieses Projekt'].map(h=>el('th',{},h))),...visible))];
  if(!visible.length)parts.push(el('span',{class:'mut'},'Keine Agenten sichtbar.'));
  if(data.error)parts.push(el('div',{class:'bad'},data.error));
  body.replaceChildren(...parts)};
 const load=async()=>{const data=await api('/api/project-agents?name='+encodeURIComponent(name));rowsCard(data);
  if(onPill)onPill(String(data.agents.filter(a=>a.configured||a.is_vibe).length)+' aktiv')};
 load().catch(e=>{body.replaceChildren(el('div',{class:'bad'},'Agentenauswahl nicht verfügbar: '+String(e&&e.message||e)));
  if(onPill)onPill('Fehler','bad')});
 return el('section',{class:'card',id:'project-agents'},el('b',{},'Agenten in diesem Projekt'),body)}
function guideCard(name){
 const body=el('div',{},el('span',{class:'mut'},'Lade Projektassistent …'));
 const load=async()=>{const g=await api('/api/guide?name='+encodeURIComponent(name));body.replaceChildren(...drawGuide(g,name))};
 load().catch(e=>body.replaceChildren(el('div',{class:'bad'},'Projektassistent nicht verfügbar: '+String(e&&e.message||e))));
 return el('div',{class:'card',id:'guide'},body)}
function drawGuide(g,name){
 const out=[],ask={};
 const tone=s=>s==='gefüllt'?'ok':(s==='offen'?'warn':'mut');
 const status=g.complete?el('span',{class:'pill ok'},'vollständig'):el('span',{class:'pill warn'},g.filled+'/'+g.total+' Pflichtschritte');
 out.push(el('div',{class:'bar'},el('b',{},'Projektassistent'),el('span',{class:'mut'},'Fachliche Grundlagen'),status));
 out.push(el('div',{class:'mut'},'Der Assistent schreibt SPEC.md und legt fehlende Grundlagen an. Vorhandene Dateien und gefüllte Abschnitte bleiben unverändert, außer du änderst sie hier ausdrücklich.'));
 out.push(el('div',{class:'mut'},'Dateien: '+g.files.map(f=>(f.exists?'✓ ':'✗ ')+f.path).join(' · ')));
 if(g.missing_files.length)out.push(el('div',{class:'warn'},'Fehlende Pflichtdateien: '+g.missing_files.join(', ')));
 g.steps.forEach(s=>{const ta=el('textarea',{rows:4,value:s.value||''});ask[s.id]=ta;
  const note=el('input',{placeholder:'Hinweis für den Agenten (optional)','aria-label':'Hinweis für '+s.title});
  const block=el('div',{class:'gstep','data-step':s.id},
   el('div',{class:'bar'},el('b',{},s.title),el('span',{class:'pill '+tone(s.status)},s.status),el('span',{class:'mut'},s.required?'Pflicht':'optional')),
   el('label',{},s.question),ta,el('div',{class:'mut'},s.help),
   el('div',{class:'bar'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/guide',{name,action:'agent',step:s.id,note:note.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Mit Agent entwerfen'),note));
  if(s.draft)block.append(el('div',{class:'mut'},el('b',{},'Entwurf des Agenten'),el('pre',{},g.drafts[s.id]||''),
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/guide',{name,action:'draft_apply',step:s.id});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Entwurf übernehmen'),
    el('button',{class:'b',on:{click:async()=>{const r=await api('/api/guide',{name,action:'draft_discard',step:s.id});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Entwurf verwerfen'))));
  out.push(block)});
 if(g.agent&&(g.agent.running||g.agent.log))out.push(el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Agentenauftrag'),el('span',{class:'pill '+(g.agent.running?'run':'mut')},g.agent.running?'läuft':'beendet')),
  el('div',{class:'mut'},'Sitzung '+g.agent.session+' · Agent '+(g.agent.agent||'?')+(g.agent.log?' · Log '+g.agent.log:'')),
  el('pre',{},(g.agent.log_tail||[]).join('\n')||'(noch keine Ausgabe)')));
 out.push(el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{
   const answers={},replace=[];
   g.steps.forEach(s=>{const v=(ask[s.id].value||'').trim();if(!v)return;answers[s.id]=v;if(s.value&&v!==s.value.trim())replace.push(s.id)});
   if(!Object.keys(answers).length){toast('Noch keine Antworten eingetragen.');return}
   const r=await api('/api/guide',{name,action:'save',answers,replace});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Antworten speichern und Dateien anlegen')));
 out.push(agentsFileCard(name));
 return out}
/* F31: AGENTS.md ansehen und in den freien Teilen bearbeiten. Der von vibe
   verwaltete Block wird schreibgeschützt dargestellt; die Karte lädt nach
   dem Speichern bzw. Anlegen ihren Inhalt neu. */
function agentsFileCard(name){
 const body=el('div',{},el('span',{class:'mut'},'Lade AGENTS.md …'));
 const load=async()=>{const v=await api('/api/agents_file?name='+encodeURIComponent(name));body.replaceChildren(...drawAgentsFile(v,name,load))};
 load().catch(e=>body.replaceChildren(el('div',{class:'bad'},'AGENTS.md nicht verfügbar: '+String(e&&e.message||e))));
 return el('div',{class:'card'},body)}
function drawAgentsFile(v,name,reload){
 const before=el('textarea',{rows:5,'aria-label':'AGENTS.md: freier Teil vor dem verwalteten Block',placeholder:'Freier Text vor dem verwalteten Block'});
 before.value=v.before||'';
 if(v.managed===null){before.disabled=true;before.placeholder='Kein verwalteter Block vorhanden; dieser Teil bleibt leer.'}
 const after=el('textarea',{rows:5,'aria-label':'AGENTS.md: freier Teil nach dem verwalteten Block',placeholder:'Freier Text nach dem verwalteten Block'});
 after.value=v.after||'';
 const save=el('button',{class:'b p',type:'button',on:{click:async()=>{
  try{const r=await api('/api/agents_file',{name,action:'save',before:before.value,after:after.value,digest:v.digest});toast(r.message);if(r.ok)await reload()}
  catch(e){toast('AGENTS.md nicht gespeichert: '+String(e&&e.message||e))}}}},'Speichern');
 const create=el('button',{class:'b',type:'button',on:{click:async()=>{
  try{const r=await api('/api/agents_file',{name,action:'create'});toast(r.message);if(r.ok)await reload()}
  catch(e){toast('AGENTS.md nicht angelegt: '+String(e&&e.message||e))}}}},'Aus Vorlage anlegen');
 const out=[el('b',{},'AGENTS.md — Regeln für Agenten'),
  el('div',{class:'mut'},'Die Datei entsteht aus der Vorlage des Projekttyps. Den folgenden verwalteten Block aktualisiert vibe bei jedem Agentenlauf; er wird dabei auf den aktuellen Stand gebracht und ist in der Bearbeitung geschützt. Nicht committete Änderungen bleiben beim Aktualisieren erhalten.'),
  el('div',{class:'mut'},v.exists?'Freier Teil vor dem verwalteten Block:':'Die Datei fehlt noch. „Aus Vorlage anlegen“ erzeugt sie aus der Typvorlage.'),
  before,
  v.managed!==null?el('pre',{},v.managed):el('div',{class:'mut'},'Kein verwalteter Block vorhanden.'),
  el('div',{class:'mut'},'Freier Teil nach dem verwalteten Block:'),
  after,
  el('div',{class:'bar'},v.exists?save:null,v.exists?null:create)];
 return out}
function feedbackCard(d,name){const list=el('div',{});const cls=s=>s==='erledigt'?'ok':s==='BLOCKIERT'?'bad':'warn';
 const done=d.feedback.filter(i=>i.completed),pending=d.feedback.filter(i=>!i.completed);let showDone=false;
 const toggle=el('button',{class:'b'});
 const delBtn=i=>{const b=el('button',{class:'b d',on:{click:()=>askInline(b,'Feedback '+i.id+' wirklich löschen?','Ja, löschen',async()=>{const r=await api('/api/feedback',{name,action:'delete',id:i.id});toast(r.message);if(r.ok)detail(name).catch(showErr)})}},'Löschen');return b};
 const rowFor=i=>{const row=el('div',{class:'fbentry','data-id':i.id});
  row.append(el('div',{},el('span',{class:'pill '+cls(i.state)},i.state),i.kind==='bug'?el('span',{class:'pill bad'},' Bug'):null,el('b',{},' '+i.id+' '+i.title)),
   ...(i.description?[el('div',{class:'mut fbdesc'},i.description)]:[]),
   el('div',{class:'bar'},
    ...(i.completed?[el('span',{class:'mut'},'abgeschlossen – nicht bearbeitbar')]:[el('button',{class:'b',on:{click:()=>edit(i,row)}},'Bearbeiten')]),
    delBtn(i)));
  return row};
 const draw=()=>{const shown=showDone?d.feedback:pending;
  list.replaceChildren(...(shown.length?shown.map(rowFor):[el('span',{class:'mut'},showDone?'Noch kein Feedback vorhanden.':'Keine offenen Feedback-Punkte.')]));
  toggle.textContent=showDone?'Abgeschlossene ausblenden':'Abgeschlossene anzeigen ('+done.length+')';
  toggle.classList.toggle('p',showDone);toggle.setAttribute('aria-expanded',showDone?'true':'false');
  toggle.style.display=done.length?'':'none'};
 const edit=(i,row)=>{const t=el('input',{value:i.title}),b=el('textarea',{rows:4,value:i.description||''});
  const ed=el('div',{class:'fbentry','data-id':i.id},el('label',{},'Titel'),t,el('label',{},'Beschreibung'),b,
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/feedback',{name,action:'update',id:i.id,title:t.value,description:b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:()=>ed.replaceWith(row)}},'Abbrechen')));
  row.replaceWith(ed)};
 toggle.addEventListener('click',()=>{showDone=!showDone;draw()});
 draw();
 return el('div',{class:'card',id:'feedback'},el('div',{class:'bar'},el('b',{},'Feedback ('+d.feedback.length+')'),toggle),list)}
function ticketCard(d,name){const list=el('div',{});const cls=s=>s==='erledigt'?'ok':s==='BLOCKIERT'?'bad':'warn';
 const done=d.tickets.filter(i=>i.completed),pending=d.tickets.filter(i=>!i.completed);let showDone=false;
 const toggle=el('button',{class:'b'});
 const delBtn=i=>{const b=el('button',{class:'b d',on:{click:()=>askInline(b,'Arbeitspaket '+i.id+' wirklich löschen?','Ja, löschen',async()=>{const r=await api('/api/ticket',{name,action:'delete',id:i.id});toast(r.message);if(r.ok)detail(name).catch(showErr)})}},'Löschen');return b};
 const rowFor=i=>{const row=el('div',{class:'fbentry','data-id':i.id});
  row.append(el('div',{},el('span',{class:'pill '+cls(i.state)},i.state),el('b',{},' '+i.id+' '+i.title)),
   ...(i.description?[el('div',{class:'mut fbdesc'},i.description)]:[]),
   el('div',{class:'bar'},
    ...(i.completed?[el('span',{class:'mut'},'abgeschlossen – nicht bearbeitbar')]:[el('button',{class:'b',on:{click:()=>edit(i,row)}},'Bearbeiten')]),
    delBtn(i)));
  return row};
 const draw=()=>{const shown=showDone?d.tickets:pending;
  list.replaceChildren(...(shown.length?shown.map(rowFor):[el('span',{class:'mut'},showDone?'Noch keine Arbeitspakete vorhanden.':'Keine offenen Arbeitspakete.')]));
  toggle.textContent=showDone?'Abgeschlossene ausblenden':'Abgeschlossene anzeigen ('+done.length+')';
  toggle.classList.toggle('p',showDone);toggle.setAttribute('aria-expanded',showDone?'true':'false');
  toggle.style.display=done.length?'':'none'};
 const edit=(i,row)=>{const t=el('input',{value:i.title}),b=el('textarea',{rows:4,value:i.description||''});
  const ed=el('div',{class:'fbentry','data-id':i.id},el('label',{},'Titel'),t,el('label',{},'Beschreibung'),b,
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/ticket',{name,action:'update',id:i.id,title:t.value,description:b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:()=>ed.replaceWith(row)}},'Abbrechen')));
  row.replaceWith(ed)};
 toggle.addEventListener('click',()=>{showDone=!showDone;draw()});
 draw();
 return el('div',{class:'card',id:'tickets'},el('div',{class:'bar'},el('b',{},'Arbeitspakete ('+d.tickets.length+')'),toggle),list)}
function ticketFormCard(d,name){
 const f={id:el('input',{placeholder:'leer lassen: automatisch vergebene ID','aria-label':'ID des Arbeitspakets'}),t:el('input',{}),b:el('textarea',{rows:3,placeholder:'Was soll umgesetzt werden?'})};
 return el('div',{class:'card',id:'ticket-new'},el('b',{},'Neues Arbeitspaket'),el('label',{},'ID (automatisch vergeben, wenn leer)'),f.id,el('label',{},'Titel'),f.t,el('label',{},'Beschreibung'),f.b,
  el('div',{class:'bar'},el('button',{class:'b p',type:'button',on:{click:async()=>{const r=await api('/api/ticket',{name,action:'add',id:f.id.value,title:f.t.value,description:f.b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Arbeitspaket anlegen')))}
function bugFormCard(d,name){
 const f={t:el('input',{}),b:el('textarea',{rows:3,placeholder:'Was funktioniert nicht?'})};
 return el('div',{class:'card',id:'bug-new'},el('b',{},'Bug melden'),el('label',{},'Titel'),f.t,el('label',{},'Beschreibung'),f.b,
  el('div',{class:'bar'},el('button',{class:'b p',type:'button',on:{click:async()=>{const r=await api('/api/feedback',{name,kind:'bug',title:f.t.value,description:f.b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Bug melden')))}
function feedbackFormCard(d,name){
 const f={t:el('input',{}),b:el('textarea',{rows:3,placeholder:'Was soll geändert oder ergänzt werden?'})};
 return el('div',{class:'card',id:'feedback-new'},el('b',{},'Feedback eintragen'),el('label',{},'Titel'),f.t,el('label',{},'Beschreibung'),f.b,
  el('div',{class:'bar'},el('button',{class:'b p',type:'button',on:{click:async()=>{const r=await api('/api/feedback',{name,title:f.t.value,description:f.b.value});toast(r.message);detail(name).catch(showErr)}}},'Eintragen')))}
/* F19: Syntaxhervorhebung der Live-Ausgabe. Es werden ausschließlich
   DOM-Knoten erzeugt (kein innerHTML), damit Protokollinhalt nie als HTML
   interpretiert wird. Die Hervorhebung ist eine Darstellungshilfe und ändert
   den Text nicht. */
const HL_INLINE=/(`[^`\n]+`|"[^"\n]+"|\b[0-9a-f]{7,40}\b|(?:[A-Za-z0-9_.\/-]+\/)*[A-Za-z0-9_.-]+\.(?:py|js|css|html|sh|md|json|ya?ml|toml|env|png|txt|log|cfg|ini)\b|\b\d+(?:[.,]\d+)?\b)/g;
function hlLineClass(line){
 if(/^===.*===\s*$/.test(line)||/^diff --git |^@@ /.test(line))return 'hl-head';
 if(/^\[Fehler\]/.test(line))return 'hl-err';
 if(/^\[Subagent\]/.test(line))return 'hl-sub';
 if(/^\[Werkzeug\]/.test(line))return 'hl-tool';
 if(/^\[Denken\]/.test(line))return 'hl-think';
 if(/^\s*(?:\$|>)\s/.test(line))return 'hl-cmd';
 if(/^\+[^ ]/.test(line))return 'hl-add';
 if(/^-[^ ]/.test(line))return 'hl-del';
 return ''}
function hlLine(line){
 const cls=hlLineClass(line),span=cls?el('span',{class:cls}):el('span');
 /* AP16/AK4: Zeilen mit Markup-Zeichen bleiben als ein Textknoten
    unangetastet. So ist der Protokolltext wörtlich und unteilbar sichtbar
    und eine HTML-Interpretation bleibt ausgeschlossen. */
 if(/[<>]/.test(line)){span.append(document.createTextNode(line));return span}
 let last=0,m;HL_INLINE.lastIndex=0;
 while((m=HL_INLINE.exec(line))){
  if(m.index>last)span.append(document.createTextNode(line.slice(last,m.index)));
  const tok=m[0];
  let c='hl-num';
  if(tok[0]==='`')c='hl-code';else if(tok[0]==='"')c='hl-str';
  else if(/^[0-9a-f]{7,40}$/.test(tok))c='hl-sha';
  else if(/\.[A-Za-z0-9]+$/.test(tok))c='hl-path';
  span.append(el('span',{class:c},tok));last=HL_INLINE.lastIndex}
 if(last<line.length)span.append(document.createTextNode(line.slice(last)));
 return span}
function renderLogChunk(text){
 const frag=document.createDocumentFragment();
 String(text).split('\n').forEach((line,i)=>{
  if(i)frag.append(document.createTextNode('\n'));
  if(line)frag.append(hlLine(line))});
 return frag}
function logView(d,onRun){
 const pre=el('pre',{id:'log'});
 let logPaused=false,logBuf='',totalChars=0;
 function append(text){if(!text)return;const near=pre.scrollHeight-pre.scrollTop-pre.clientHeight<60;
  pre.append(renderLogChunk(text));totalChars+=String(text).length;
  if(totalChars>80000){while(totalChars>60000&&pre.firstChild){const n=pre.firstChild;totalChars-=(n.textContent||'').length;pre.removeChild(n)}}
  if(near)pre.scrollTop=pre.scrollHeight}
 function reset(text){pre.replaceChildren();totalChars=0;append(text);pre.scrollTop=pre.scrollHeight}
 reset((d.tail||[]).join('\n')||'(noch keine Ausgabe)');
 const pauseBtn=el('button',{class:'b',type:'button'},'Pause'),fullBtn=el('button',{class:'b',type:'button'},'Vergrößern');
 const runBtn=el('button',{class:'b',type:'button',title:'Verbindet die Ausgabe wieder mit dem Agentenlauf',on:{click:onRun}},'Lauf-Log');
 const card=el('div',{class:'card logcard'});
 const fit=()=>{if(card.classList.contains('full'))return;
  pre.style.height=Math.max(240,window.innerHeight-pre.getBoundingClientRect().top-18)+'px'};
 pauseBtn.addEventListener('click',()=>{logPaused=!logPaused;pauseBtn.textContent=logPaused?'Fortsetzen':'Pause';pauseBtn.classList.toggle('p',logPaused);
  if(!logPaused&&logBuf){append(logBuf);logBuf='';pre.scrollTop=pre.scrollHeight}});
 fullBtn.addEventListener('click',()=>setLogFull(!card.classList.contains('full')));
 card.append(el('div',{class:'bar'},el('b',{},'Live-Ausgabe'),el('span',{class:'mut'},'Lauf-Ausgabe des aktuellen Projekts'),runBtn,pauseBtn,fullBtn),pre);
 LOG={card,pre,button:fullBtn,fit};
 return {card,pre,fit,
  clear:()=>{pre.replaceChildren();totalChars=0;logBuf=''},
  feed:text=>{if(logPaused){logBuf=(logBuf+text).slice(-80000);return}append(text)}}
}
/* B11/AP20: Die Ausgabeansicht zeigt Hauptagent und jeden laufenden
   Subagenten gleichzeitig. AP20 ergänzt eine kompakte Übersicht, einen
   einzigen panelweiten Scrollbereich, ein umbrechendes Kartenraster und
   einen geteilten Fokus-Modus. Der B11/F30-Vertrag bleibt unverändert:
   Zielauswahl, Anweisung, Senden/Fortsetzen, DOM-only-Highlighter und
   Vergrößerung. */
function outputView(name,d,isPi){
 const mainPre=el('pre',{class:'bv-log','aria-label':'Ausgabe des Hauptagenten'});
 const mainState=el('span',{class:'pill mut'},'gestoppt');
 /* AP20: Der Fokus-Knopf des Hauptagenten teilt denselben Zustand wie die
    Übersichts- und Karten-Knöpfe. Er bleibt dauerhaft „fokussieren“ benannt;
    der Zustand steht in aria-expanded. */
 const mainToggle=el('button',{class:'b bv-focus-btn',type:'button','data-focus-session':'','aria-label':'Hauptagent fokussieren','aria-expanded':'false'},'Fokus');
 const mainView=el('section',{class:'bv-view bv-main','data-agent-view':'','data-role':'main','data-session':'',role:'log','aria-label':'Hauptagent'},
  el('div',{class:'bv-head'},el('b',{},'Hauptagent'),el('div',{class:'bv-head-actions'},mainState,mainToggle)),mainPre);
 /* AP20: Kompakte Statusübersicht über alle aktiven Agenten (Hauptagent
    eingeschlossen). Keine Tabliste, kein Modal — nur Zeilen mit Name,
    gekürzter Beschreibung, Status-Pille und Fokus-Knopf. */
 const overview=el('section',{class:'bv-overview','aria-label':'Aktive Agenten','data-active-agents':'0'});
 const overviewCount=el('span',{class:'pill mut'},'0 Subagenten');
 const overviewList=el('div',{class:'bv-overview-list'});
 const overviewEmpty=el('div',{class:'bv-overview-empty'},'Keine laufenden Subagenten.');
 overview.append(el('div',{class:'bv-overview-head'},el('b',{},'Aktive Agenten'),overviewCount),overviewList,overviewEmpty);
 const subsBox=el('div',{class:'bv-subs','aria-label':'Laufende Subagenten'});
 const select=el('select',{'aria-label':'Ziel'});
 const ta=el('textarea',{rows:'2',maxlength:'4000','aria-label':'Zusatzanweisung für den gewählten Agenten',placeholder:'Zusatzanweisung …'});
 const send=el('button',{class:'b p',type:'button'},'Anweisung senden');
 const cont=el('button',{class:'b p',type:'button',hidden:''},'Fortsetzen');
 const hint=el('span',{class:'mut'},isPi
  ?'Bei Pi ist das Steuern nicht möglich: Pi läuft im Print-Modus (--no-session) ohne fortsetzbare Session.'
  :'Die Anweisung geht an das in „Ziel“ gewählte Ziel und ist nur während eines Laufs möglich.');
 const controls=el('section',{class:'card bv-controls'},
  el('div',{class:'bv-bar'},el('span',{class:'bv-label'},'Ziel'),select),
  el('div',{class:'bv-bar'},ta),
  el('div',{class:'bv-bar'},send,cont,hint));
 const card=el('div',{class:'bv-root'},overview,controls,mainView,subsBox);
 let mainText=(d.tail||[]).join('\n')||'(noch keine Ausgabe)';
 let lastRunning=false,optionKey='',rowKey='',focusedSession=null;
 const children=new Map(),rows=new Map();
 /* AP16: Die Ausgabeansicht nutzt denselben F19-Highlighter wie das
    Lauf-Log (renderLogChunk, DOM-only). Der Text bleibt unverändert; die
    Hervorhebung ist reine Darstellung. */
 function renderMain(){mainPre.replaceChildren(renderLogChunk(mainText))}
 renderMain();
 function nameOf(entry){return String(entry.agent||'Subagent')+(entry.description?' — '+entry.description:'')}
 function setText(node,text){
  if(node.text===text)return;
  node.text=text;
  const near=node.pre.scrollHeight-node.pre.scrollTop-node.pre.clientHeight<70;
  node.pre.replaceChildren(renderLogChunk(text||'(noch keine Ausgabe)'));
  if(near)node.pre.scrollTop=node.pre.scrollHeight}
 /* AP20: Ein einziger Fokus-Zustand für Karten-, Haupt- und
    Übersichts-Knöpfe. Klick auf denselben Knopf oder Escape hebt ihn auf. */
 function toggleFocus(session){focusedSession=focusedSession===session?null:session;applyFocus()}
 /* AP20: Der Fokus-Knopf des Hauptagenten schaltet exakt denselben
    geteilten Zustand wie Karten- und Übersichts-Knöpfe (Session des
    Hauptagenten zum Zeitpunkt des Klicks). */
 mainToggle.addEventListener('click',()=>toggleFocus(mainView.getAttribute('data-session')||''));
 function applyFocus(){
  card.classList.toggle('bv-focusing',!!focusedSession);
  const mainOn=!!focusedSession&&focusedSession===mainView.getAttribute('data-session');
  mainView.classList.toggle('enlarged',mainOn);
  mainToggle.textContent=mainOn?'Fokus beenden':'Fokus';
  mainToggle.setAttribute('aria-label','Hauptagent fokussieren');
  mainToggle.setAttribute('aria-expanded',mainOn?'true':'false');
  for(const[id,node]of children){const on=focusedSession===id;
   node.view.classList.toggle('enlarged',on);
   node.toggle.textContent=on?'Verkleinern':'Vergrößern';
   node.toggle.setAttribute('aria-label',on?'Subagent verkleinern':'Subagent vergrößern');
   node.toggle.setAttribute('aria-expanded',on?'true':'false')}
  for(const[id,row]of rows)row.focus.setAttribute('aria-expanded',focusedSession===id?'true':'false')}
 function makeChild(entry){
  const pre=el('pre',{class:'bv-log'});
  const state=el('span',{class:'pill run'},'läuft');
  /* F30/AP20: Der Knopf im Kartenkopf und der Übersichts-Knopf schalten
     denselben Zustand. Beim Entfernen des Subagenten verschwindet er mit. */
  const toggle=el('button',{class:'b',type:'button','aria-label':'Subagent vergrößern','aria-expanded':'false'},'Vergrößern');
  const view=el('section',{class:'bv-view bv-sub','data-agent-view':'','data-role':'subagent','data-session':String(entry.session||''),role:'log','aria-label':nameOf(entry)},
   el('div',{class:'bv-head'},el('b',{},nameOf(entry)),el('div',{class:'bv-head-actions'},state,toggle)),pre);
  toggle.addEventListener('click',()=>toggleFocus(String(entry.session||'')));
  const node={view,pre,state,toggle,text:'',loading:false};
  setText(node,String(entry.output||''));
  return node}
 function makeRow(){
  const focus=el('button',{class:'b bv-focus-btn',type:'button','data-focus-session':'','aria-label':'fokussieren','aria-expanded':'false'},'Fokus');
  const label=el('span',{class:'bv-ov-name'});
  const desc=el('span',{class:'bv-ov-desc'});
  const state=el('span',{class:'pill mut'});
  const row=el('div',{class:'bv-overview-row','data-overview-session':''},label,desc,state,focus);
  focus.addEventListener('click',()=>toggleFocus(String(row.getAttribute('data-overview-session')||'')));
  return {row,label,desc,state,focus}}
 async function loadChild(node,entry){
  if(node.loading)return;
  node.loading=true;
  try{const r=await api('/api/subagent-output?name='+encodeURIComponent(name)+'&session='+encodeURIComponent(entry.session||''));
   if(r&&r.ok)setText(node,String(r.text||''));
   else if(!node.text&&entry.output)setText(node,String(entry.output))}
  catch(e){}
  finally{node.loading=false}}
 function sync(data){
  const running=!!(data&&data.running),session=String((data&&data.session)||'');
  lastRunning=running;
  mainView.setAttribute('data-session',session);
  mainView.setAttribute('aria-label','Hauptagent'+(session?' '+session:''));
  mainToggle.setAttribute('data-focus-session',session);
  mainState.textContent=running?'läuft':'gestoppt';
  mainState.className='pill '+(running?'run':'mut');
  const subs=((data&&data.subagents)||[]).filter(s=>s&&s.session&&s.status==='running');
  const entries=[{session,label:'Hauptagent',agent:'Hauptagent',description:'Live-Ausgabe des Hauptagenten'}]
   .concat(subs.map(s=>({session:String(s.session),label:nameOf(s),agent:String(s.agent||'Subagent'),description:String(s.description||'')})))
   .filter(e=>e.session);
  /* Ein Sessionwechsel des Hauptagenten darf keinen verwaisten Fokus lassen. */
  if(focusedSession&&focusedSession!==session&&!children.has(focusedSession))focusedSession=null;
  const key=entries.map(e=>e.session).join('|');
  if(key!==optionKey){optionKey=key;select.replaceChildren(...entries.map(e=>el('option',{value:e.session},e.label)))}
  const values=new Set([...select.options].map(o=>o.value));
  select.value=values.has(select.value)?select.value:(values.has(session)?session:(entries[0]?entries[0].session:''));
  /* Übersicht: genau eine Zeile je laufendem Agenten, bei Sessionwechsel
     mitgezogen und ohne Duplikate. */
  for(const[id,row]of [...rows]){if(!entries.some(e=>e.session===id)){row.row.remove();rows.delete(id)}}
  entries.forEach(entry=>{
   const id=entry.session;let row=rows.get(id);
   if(!row){row=makeRow();rows.set(id,row)}
   row.row.setAttribute('data-overview-session',id);
   /* AP20: Die Zeile kürzt die Beschreibung per Ellipsis; der volle Text
      bleibt als Tooltip (Hover/Tastatur) ohne innerHTML verfügbar. */
   row.row.setAttribute('title',entry.agent+(entry.description?' — '+entry.description:''));
   row.label.textContent=entry.agent;
   row.desc.textContent=entry.description||'—';
   row.state.textContent=entry.session===session&&!running?'gestoppt':'läuft';
   row.state.className='pill '+(entry.session===session&&!running?'mut':'run');
   row.focus.setAttribute('data-focus-session',id);
   row.focus.setAttribute('aria-label',entry.agent+' fokussieren')});
  if(key!==rowKey){rowKey=key;overviewList.replaceChildren(...entries.map(e=>rows.get(e.session).row))}
  overviewCount.textContent=subs.length+' Subagenten';
  overview.setAttribute('data-active-agents',String(subs.length));
  /* Der Leerzustand bezieht sich auf Subagenten: Der Hauptagent bleibt auch
     ohne Subagenten als Zeile sichtbar. */
  overviewEmpty.hidden=subs.length>0;
  const wanted=new Set(subs.map(s=>String(s.session)));
  for(const[id,node]of [...children]){if(!wanted.has(id)){if(focusedSession===id)focusedSession=null;node.view.remove();children.delete(id)}}
  subs.forEach(s=>{const id=String(s.session);let node=children.get(id);
   if(!node){node=makeChild(s);children.set(id,node)}
   node.view.setAttribute('data-session',id);
   node.view.setAttribute('aria-label',nameOf(s));
   node.state.textContent=s.status||'läuft';
   if(!node.text&&s.output)setText(node,String(s.output));
   if(node.view.parentNode!==subsBox)subsBox.append(node.view);
   loadChild(node,s)});
  subsBox.hidden=!subs.length;
  cont.hidden=!(session&&!running);
  send.disabled=isPi||!running;
  ta.disabled=isPi||!running;
  applyFocus()}
 card.addEventListener('keydown',e=>{if(e.key==='Escape'&&focusedSession){e.preventDefault();toggleFocus(focusedSession)}});
 async function sendNow(){
  if(isPi){toast('Bei Pi ist das Steuern nicht möglich: Pi läuft im Print-Modus (--no-session) ohne fortsetzbare Session.');return}
  const text=ta.value.trim();
  if(!text){ta.focus();toast('Bitte eine Zusatzanweisung eingeben.');return}
  /* Sofort leeren: Eine zweite Anweisung darf nicht durch die verspätete
     Antwort der ersten gelöscht werden. */
  ta.value='';
  try{const body={name,text};const session=select.value;if(session)body.session=session;
   const r=await api('/api/steer',body);
   toast(r.message||(r.ok?'Zusatzanweisung übermittelt.':'Zusatzanweisung abgelehnt.'))}
  catch(e){toast('Zusatzanweisung nicht gesendet: '+String(e&&e.message||e));if(!ta.value)ta.value=text}
  finally{send.disabled=isPi||!lastRunning}}
 function feedMain(text){
  if(!text)return;
  const near=mainPre.scrollHeight-mainPre.scrollTop-mainPre.clientHeight<70;
  mainText=(mainText+text).slice(-120000);
  renderMain();
  if(near)mainPre.scrollTop=mainPre.scrollHeight}
 function clearMain(){mainText='';renderMain()}
 function fit(){mainPre.scrollTop=mainPre.scrollHeight}
 cont.addEventListener('click',async()=>{
  cont.disabled=true;
  try{const r=await api('/api/continue',{name});
   toast(r.message||(r.ok?'Der Lauf wird fortgesetzt.':'Fortsetzen abgelehnt.'));
   if(r.ok)detail(name).catch(showErr)}
  catch(e){toast('Fortsetzen nicht gesendet: '+String(e&&e.message||e))}
  finally{cont.disabled=false}});
 send.addEventListener('click',sendNow);
 ta.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();sendNow()}});
 return {card,sync,feedMain,clearMain,fit}
}
function rightsBody(d,name){const inp=el('input',{placeholder:'/absoluter/pfad','aria-label':'Schreibverzeichnis'});
 const reset=el('button',{class:'b',on:{click:()=>askInline(reset,'Standardverzeichnisse wiederherstellen?','Ja, zurücksetzen',async()=>{const r=await api('/api/rights',{name,action:'reset'});toast(r.message);if(r.ok)detail(name).catch(showErr)})}},'Standard wiederherstellen');
 const rows=el('div',{},...(d.write_dirs.length?d.write_dirs.map(p=>el('div',{class:'bar'},el('span',{class:'mut'},p),
   el('button',{class:'b d',on:{click:async()=>{const r=await api('/api/rights',{name,action:'remove',path:p});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Entfernen'))):[el('span',{class:'mut'},'Keine Verzeichnisse – Schreiben ist gesperrt.')]));
 const sandboxOn=!!(d.sandbox&&d.sandbox.enabled);
 return el('div',{},
  el('div',{class:'mut'},sandboxOn
   ? 'Sandbox aktiv: Schreibwerkzeug (edit) und Shell-Befehle (bash) können nur in diesen Verzeichnissen, den Caches der Build-Werkzeuge und /tmp/opencode schreiben. MCP und Netzwerk bleiben erlaubt; Lesezugriffe werden nicht eingeschränkt.'
   : 'Verzeichnisse für das Schreibwerkzeug (edit) der Projektagenten. Voreingestellt sind /tmp/opencode und das Projektverzeichnis. Agenten ohne Schreibrecht bleiben unverändert. Shell-Befehle (bash) bleiben erlaubt und können Dateien außerhalb dieser Liste ändern – die Liste ist keine Sandbox.'),
  d.write_dirs_error?el('div',{class:'bad'},'Liste nicht lesbar: '+d.write_dirs_error):null,
  rows,
  el('div',{class:'bar'},inp,el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/rights',{name,action:'add',path:inp.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Hinzufügen')),
  el('div',{class:'bar'},reset,
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/rights',{name,action:'apply'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Auf Projektagenten anwenden')),
  el('div',{class:'mut'},d.write_dirs_custom?'Eigene Liste aktiv.':'Standardliste aktiv.'))}
function sandboxBody(d,name,isPi){const s=d.sandbox||{enabled:false,tools:[],write_dirs:[],missing_tools:[],error:null,bwrap:''};
 const active=!!s.enabled,missing=s.missing_tools||[],dirs=s.write_dirs||[],tools=s.tools||[];
 const st=sandboxStatus(s),state=st.state,tone=st.tone;
 const inp=el('input',{value:tools.join(' '),placeholder:'git node npm','aria-label':'Build-Werkzeuge'});
 return el('div',{},el('div',{class:'bar'},el('span',{class:'pill '+tone},state),
   el('button',{class:'b'+(active?'':' p'),on:{click:async()=>{const r=await api('/api/sandbox',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Sandbox ausschalten':'Sandbox einschalten'),
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/sandbox',{name,action:'check'});toast(r.message)}}},'Prüfen')),
  el('div',{class:'mut'},isPi
   ? 'Aktiv läuft der Agent mit Pi im Print-Modus (ohne opencode-Server) in bubblewrap. Schreiben ist nur in den Verzeichnissen unten, in den Caches der Build-Werkzeuge und in einem privaten Temporärordner möglich; /tmp ist sonst schreibgeschützt. MCP und Netzwerk bleiben verfügbar; Lesezugriffe werden nicht eingeschränkt.'
   : 'Aktiv läuft der Agent mit eigenem opencode-Server in bubblewrap. Schreiben ist nur in den Verzeichnissen unten, in den Caches der Build-Werkzeuge und in einem privaten Temporärordner möglich; /tmp ist sonst schreibgeschützt. MCP und Netzwerk bleiben verfügbar; Lesezugriffe werden nicht eingeschränkt.'),
  el('div',{class:'mut'},'Die Sandbox-Konfiguration (.vibe/project.env, .vibe/permissions.json) ist im Lauf schreibgeschützt.'),
  s.error?el('div',{class:'bad'},'Fehler: '+s.error):null,
  missing.length?el('div',{class:'bad'},'Fehlende Werkzeuge: '+missing.join(', ')):null,
  !active?el('div',{class:'mut'},'Ohne Sandbox bleiben Shell-Befehle (bash) außerhalb der Liste möglich.'):null,
  el('label',{},'Build-Werkzeuge (Leerzeichen oder Komma)'),inp,
  el('div',{class:'bar'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/sandbox',{name,action:'tools',tools:inp.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Werkzeuge speichern')),
  el('b',{},'Erlaubte Schreibverzeichnisse ('+dirs.length+')'),el('div',{},...dirs.map(p=>el('div',{class:'mut'},p))))}

/* ---------- Git & GitHub (AP6: optional je Projekt; AP7: Aktionen erscheinen
   nur bei aktiver Verknüpfung, damit der aus-Zustand übersichtlich bleibt;
   B7: GitHub-Zugang (Token) direkt in der Karte hinterlegen und entfernen;
   fehlgeschlagene Aktionen bleiben dauerhaft in der Fehlerbox stehen;
   AP9: Token je Projekt verschlüsselt, Branch-Kontrolle, Verbindungsprüfung,
   Basis-Branch; der Läufer zieht bei GITHUB_ENABLED vor jedem Arbeitspaket
   den Haupt-Branch und pusht nach jedem abgeschlossenen Paket automatisch
   den Paket-Branch samt Merge-Request — das Zusammenführen bleibt manuell) ---------- */
function githubBody(d,name){
 const g=d.github||{enabled:false,repo:'',label:'vibe',api:'',base:'',branch:'-',remotes:[],branches:[],ahead:0,behind:0,unpushed:false};
 const active=!!g.enabled;
 const fact=(k,v)=>el('div',{class:'factrow'},el('span',{class:'mut'},k),el('span',{},String(v)));
 const errBox=el('div',{class:''});
 const issuesBox=el('div',{class:'mut'});
 const setErr=message=>{errBox.className=String(message||'').length?'bad':'';errBox.textContent=String(message||'')};
 const refresh=()=>detail(name).catch(showErr);
 const post=async body=>{const r=await api('/api/github',body);toast(r.message||'');if(r.ok)setErr('');else setErr(r.message);return r};
 const enabled=el('input',{type:'checkbox','aria-label':'GitHub-Verknüpfung aktiv'});enabled.checked=active;
 const repo=el('input',{value:g.repo||'',placeholder:'owner/name','aria-label':'GitHub-Repository (owner/name)'});
 const label=el('input',{value:g.label||'vibe',placeholder:'vibe','aria-label':'GitHub-Label für vibe-Aufgaben'});
 const apiIn=el('input',{value:(g.api&&g.api!=='https://api.github.com')?g.api:'',placeholder:'https://api.github.com (Standard)','aria-label':'GitHub-API-Basis'});
 /* AP9: Basis-Branch für Merge-Requests (GITHUB_BASE); Leerwert = Standard-Branch der origin (meist main). */
 const baseIn=el('input',{value:g.base||'',placeholder:'z. B. main (leer = Standard-Branch der origin)','aria-label':'Basis-Branch für Merge-Requests'});
 /* B7/AP9: GitHub-Zugang (Token) direkt in der Karte, ohne CLI oder Umgebungsvariable.
    Seit AP9 gilt der Token je Projekt und wird verschlüsselt im Zustandsordner
    abgelegt. Der Zustand spiegelt g.auth (set/source ohne Geheimnis) und wird
    nach speichern/entfernen unverzüglich in der Zeile aktualisiert (kein
    Refresh, damit der aufgeklappte Abschnitt geöffnet bleibt). */
 const authLine=el('div',{class:'mut','data-auth':''});
 const setAuth=source=>{
  const text=source==='umgebung'?'Zugang über die Umgebung (GITHUB_TOKEN/GH_TOKEN).'
    :source==='projekt'?'GitHub-Token für dieses Projekt gespeichert (verschlüsselt).'
    :source==='gespeichert'?'Zugang über den früher global gespeicherten Token (Rückfall, nicht projektbezogen).'
    :'';
  authLine.textContent='GitHub-Zugang: '+(text
    ||'Kein Token hinterlegt — für Push, private Repositories und Merge-Requests ist ein Token nötig. GitHub empfiehlt einen Personal Access Token.');
 };
 setAuth(g.auth&&g.auth.set?g.auth.source:'');
 const tokenIn=el('input',{type:'password',placeholder:'GitHub-Token einfügen (Personal Access Token)','aria-label':'GitHub-Token einfügen'});
 const tokenSave=el('button',{class:'b p',on:{click:async()=>{
   const value=tokenIn.value.trim();
   if(!value){setErr('Kein Token angegeben: GitHub-Token einfügen, dann speichern.');return}
   const r=await api('/api/github',{name,action:'token.save',token:value});
   setErr(r.ok?'':r.message);toast(r.message||'');
   if(r.ok){tokenIn.value='';setAuth(r.auth&&r.auth.set?r.auth.source:'')}}}},'Token hinterlegen');
 const tokenClear=el('button',{class:'b',on:{click:async()=>{
   const r=await api('/api/github',{name,action:'token.clear'});
   setErr(r.ok?'':r.message);toast(r.message||'');
   if(r.ok){tokenIn.value='';setAuth(r.auth&&r.auth.set?r.auth.source:'')}}}},'Token entfernen');
 const save=el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/github',{name,action:'settings',enabled:enabled.checked,repo:repo.value.trim(),label:label.value.trim(),api:apiIn.value.trim(),base:baseIn.value.trim()});
   if(!r.ok)setErr(r.message);toast(r.message);if(r.ok){setErr('');refresh()}}}},'Speichern');
 const linkBtn=el('button',{class:'b',on:{click:async()=>{
   const value=repo.value.trim();
   if(!value||!value.includes('/')){setErr('Repository in der Form owner/name angeben');return}
   const r=await api('/api/github',{name,action:'link',url:'https://github.com/'+value+'.git'});
   if(!r.ok)setErr(r.message);toast(r.message);if(r.ok){setErr('');refresh()}}}},'Mit GitHub verknüpfen');
 const unlinkBtn=el('button',{class:'b',on:{click:async()=>{const r=await api('/api/github',{name,action:'unlink'});
   if(!r.ok)setErr(r.message);toast(r.message);if(r.ok){setErr('');refresh()}}}},'Verknüpfung lösen');
 const fetchBtn=el('button',{class:'b',on:{click:async()=>{const r=await post({name,action:'fetch'});if(r.ok)refresh()}}},'Abrufen (fetch, kein Merge)');
 const pushTarget=el('input',{placeholder:'Ziel-Branch (leer = gleicher Name)','aria-label':'Ziel-Branch für Push (optional)'});
 const pushBtn=el('button',{class:'b',on:{click:async()=>{const r=await post({name,action:'push',target:pushTarget.value.trim()});if(r.ok)refresh()}}},'Push (aktueller Branch)');
 const pullBtn=el('button',{class:'b',on:{click:async()=>{const r=await post({name,action:'pull'});if(r.ok)refresh()}}},'Pull (aufholen, --ff-only)');
 /* AP9: Verbindungsprüfung in der Karte — Fernseite (origin) und GitHub-REST
    werden geprüft; das Ergebnis bleibt als Zeile mit ok/fehler-Kennung stehen. */
 const connLine=el('div',{class:'mut','data-connection':''});
 const testBtn=el('button',{class:'b',on:{click:async()=>{
   const r=await api('/api/github',{name,action:'connection'});
   const c=r.connection||{};
   connLine.className=c.ok?'ok':'bad';
   connLine.textContent='Verbindung: '+(c.ok?'OK':'FEHLER')+' — '+String(r.message||c.message||'');
   toast(r.message||'')}}},'Verbindung testen');
 const issueFilter=el('input',{value:g.label||'vibe',placeholder:'Label (leer = alle)','aria-label':'Issues nach Label filtern'});
 const loadBtn=el('button',{class:'b',on:{click:async()=>{const r=await api('/api/github',{name,action:'issues',label:issueFilter.value.trim()});
   if(!r.ok){setErr(r.message);toast(r.message);return}
   const rows=(r.issues||[]).map(i=>el('div',{class:'mut'},el('b',{},'GH-'+i.number+' '),i.title,
     i.labels&&i.labels.length?el('span',{class:'mut'},' ['+i.labels.join(', ')+']'):null));
   issuesBox.replaceChildren(...(rows.length?rows:[el('span',{class:'mut'},'Keine offenen Issues für dieses Label.')]))}}},'Issues laden');
 const importBtn=el('button',{class:'b',on:{click:async()=>{const r=await api('/api/github',{name,action:'import',label:issueFilter.value.trim()});
   if(!r.ok)setErr(r.message);else setErr('');toast(r.message);if(r.ok)refresh()}}},'Import');
 const prBtn=el('button',{class:'b p',on:{click:()=>{askInline(prBtn,'Merge-Request stellen: Erst den aktuellen Branch nach origin pushen, dann den Merge-Request über GitHub anlegen. Fortfahren?','Ja, stellen',async()=>{
   const r=await api('/api/github',{name,action:'pr',confirm:true});
   if(!r.ok)setErr(r.message);toast(r.message||'Fehler beim Merge-Request');if(r.ok)refresh()})}}},'Merge-Request stellen');
 const facts=[fact('Zustand',active?'aktiv':'aus'),fact('Repository',g.repo||'—'),fact('Branch',g.branch||'-'),
   fact('Ahead/Behind',(g.ahead||0)+' / '+(g.behind||0)+(g.unpushed?' (ungesendete Commits)':''))];
 if(g.error)facts.push(fact('Hinweis',String(g.error)));
 const remoteRows=(g.remotes||[]).map(r=>el('div',{class:'mut'},'Remote '+r.name+': '+r.url));
 /* AP9: Branch-Kontrolle je Zeile — „Wechseln“ checkt den Branch aus
    (erzeugt ihn bei Bedarf aus origin/<branch>), „Push“ überträgt ihn
    nach origin. Meldungen landen im Toast, Fehler in der Fehlerbox. */
 const branchRows=(g.branches||[]).map(b=>el('div',{class:'mut'},
  (b.current?'* ':'  ')+b.name+' (Ahead/Behind '+b.ahead+'/'+b.behind+')',
  el('div',{class:'bar'},
   el('button',{class:'b',on:{click:async()=>{const r=await post({name,action:'checkout',branch:b.name});if(r.ok)refresh()}}},'Wechseln'),
   el('button',{class:'b',on:{click:async()=>{const r=await post({name,action:'push',branch:b.name});if(r.ok)refresh()}}},'Push'))));
 const conn=el('div',{},
   el('div',{class:'mut'},'GitHub ist optional je Projekt. Die Einstellungen gelten nur für dieses Projekt; die Knöpfe bleiben bewusste Aktionen. Bei aktiver Verknüpfung zieht der Läufer vor jedem Arbeitspaket den Haupt-Branch (pull) und überträgt nach jedem abgeschlossenen Paket den Paket-Branch automatisch nach origin und stellt einen Merge-Request — das Zusammenführen bleibt manuell.'),
   authLine,
   el('div',{class:'bar'},tokenIn,tokenSave,tokenClear),
   el('label',{class:'inline'},enabled,' GitHub-Verknüpfung aktiv'),
   el('label',{},'Repository (owner/name)'),repo,
   el('label',{},'Label für vibe-Aufgaben'),label,
   el('label',{},'API-Basis (optional)'),apiIn,
   /* AP9: Basis-Branch für Merge-Requests (GITHUB_BASE); leer = Standard-Branch der origin. */
   el('label',{},'Basis-Branch für Merge-Requests (optional)'),baseIn,
   el('div',{class:'bar'},save,linkBtn,unlinkBtn));
 const actions=active?el('div',{class:'gh-actions'},
   ...facts,
   remoteRows.length?el('div',{'data-remotes':''},...remoteRows):null,
   el('div',{class:'bar'},fetchBtn,pushBtn,pullBtn),
   branchRows.length?el('details',{},el('summary',{},'Branches ('+branchRows.length+')'),el('div',{},...branchRows))
                    :el('div',{class:'mut'},'Keine lokalen Branches erkannt.'),
   /* AP9: Verbindungsprüfung mit dauerhafter Ergebniszeile in der Karte. */
   el('div',{class:'bar'},testBtn),
   connLine,
   el('div',{class:'bar'},prBtn),
   el('hr'),
   el('b',{},'Issues als Arbeitspakete'),
   el('div',{class:'mut'},'Offene GitHub-Issues nach Label filtern und als Arbeitspakete (GH-Nummer) in TICKETS.md übernehmen.'),
   el('label',{},'Label-Filter'),issueFilter,
   el('div',{class:'bar'},loadBtn,importBtn),
   issuesBox):null;
 return el('div',{},conn,actions,errBox)}

/* ---------- Offene Arbeitspakete (F29: Die Reihenfolge der Arbeitspakete
   wird direkt hier per Drag&Drop am Handle je Paket geändert und als
   PACKAGE_ORDER gespeichert — statt versteckt im Einstellungs-Tab, wo sie
   beim Speichern wegen eines nicht gesetzten ok den UnboundLocalError
   auslöste. Der Läufer wählt den ersten geeigneten Eintrag dieser Liste vor
   der Standardordnung; erledigte oder gesperrte Einträge halten ihn nicht
   auf.) ---------- */
function openPackagesCard(d,name){
 const stateOf={};(d.items||[]).forEach(i=>{stateOf[i.id]=i.state});
 const list=el('div',{class:'itemlist','data-open-packages':''},el('span',{class:'mut'},'Lade Reihenfolge …'));
 const errBox=el('div',{});
 const hintBox=el('div',{class:'mut'});
 const setErr=message=>{errBox.className=String(message||'').length?'bad':'';errBox.textContent=String(message||'')};
 let rows=[],dragId=null;
 const rowFor=r=>{
  const handle=el('span',{class:'draghandle','data-drag-handle':r.id,role:'button',tabindex:'0',
   'aria-label':'Paket '+r.id+' verschieben (Pfeiltasten auf/ab)','title':'Paket '+r.id+' verschieben'},'⋮⋮');
  const row=el('div',{class:'item packitem',draggable:'true','data-item':r.id},handle,
   el('span',{},el('b',{},r.id+' '),r.title?el('span',{class:'mut'},r.title):null),
   r.state?el('span',{class:'pill '+(r.state==='BLOCKIERT'?'bad':'warn')},r.state):null,
   r.ordered===undefined?null:el('span',{class:'pill '+(r.ordered?'ok':'mut')},r.ordered?'priorisiert':'Standardordnung'));
  handle.addEventListener('keydown',e=>{
   if(e.key!=='ArrowUp'&&e.key!=='ArrowDown')return;
   e.preventDefault();
   const i=rows.findIndex(x=>x.id===r.id),n=e.key==='ArrowUp'?i-1:i+1;
   if(i<0||n<0||n>=rows.length)return;
   [rows[i],rows[n]]=[rows[n],rows[i]];draw();
   const h=list.querySelector('[data-drag-handle="'+r.id+'"]');if(h)h.focus()});
  row.addEventListener('dragstart',e=>{dragId=r.id;row.classList.add('dragging');
   e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',r.id)});
  row.addEventListener('dragend',()=>{dragId=null;row.classList.remove('dragging');
   /* F29-Review: Indikator auch zurücksetzen, wenn ohne Ablage beendet wird. */
   list.querySelectorAll('.dropbefore').forEach(x=>x.classList.remove('dropbefore'))});
  row.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='move';
   const rect=row.getBoundingClientRect();
   row.classList.toggle('dropbefore',e.clientY<rect.top+rect.height/2)});
  row.addEventListener('dragleave',()=>row.classList.remove('dropbefore'));
  row.addEventListener('drop',e=>{e.preventDefault();
   const before=row.classList.contains('dropbefore');row.classList.remove('dropbefore');
   if(!dragId||dragId===r.id)return;
   const from=rows.findIndex(x=>x.id===dragId);if(from<0)return;
   const moved=rows.splice(from,1)[0];
   let to=rows.findIndex(x=>x.id===r.id);
   if(to<0){rows.splice(from,0,moved);draw();return}
   if(!before)to+=1;
   rows.splice(to,0,moved);draw()});
  return row};
 const draw=()=>{list.replaceChildren(...rows.map(rowFor))};
 const render=data=>{
  /* F29-Review M1: Die Anzeige folgt der gespeicherten Reihenfolge
     (data.order), nicht der Auswahl-Queue — gesperrte und abhängigkeits-
     geblockte Pakete fehlen in der Queue, gehören aber mit ihrer gezogenen
     Position in die Karte, damit sie vorn stehen, sobald sie frei sind.
     F29-Review 2 M1: Offene Pakete ohne Eintrag in der Priorisierung folgen
     in der Läufer-Standardordnung (data.standard: TICKETS vor FEEDBACK,
     innerhalb der TICKETS nach Priorität) — blankes Speichern legt sonst
     eine Ordnung ab, die der Läufer ohne Priorisierung nicht wählen würde.
     Erledigte und unbekannte Einträge (fehlt) erscheinen nicht als Zeile;
     unbekannte werden im Hinweis genannt und beim nächsten Speichern aus
     PACKAGE_ORDER entfernt. */
  const order=data.order||[];
  const visible=new Set((d.items||[]).map(i=>i.id));
  const configured=new Set(),missing=[];
  rows=order.filter(o=>{
   if(!visible.has(o.id)){if(o.status==='fehlt')missing.push(o.id);return false}
   return true})
   .map(o=>({id:o.id,title:o.title,ordered:true,state:stateOf[o.id]}));
  order.forEach(o=>configured.add(o.id));
  const shown=new Set(rows.map(r=>r.id));
  const byId=new Map((d.items||[]).map(i=>[i.id,i]));
  const remaining=(d.items||[]).filter(i=>!configured.has(i.id));
  const ids=data.standard&&data.standard.length
   ?data.standard.map(o=>o.id):remaining.map(i=>i.id);
  ids.concat(remaining.filter(i=>!ids.includes(i.id)).map(i=>i.id))
   .forEach(id=>{
    const i=byId.get(id);
    if(i&&!shown.has(id)){shown.add(id);
     rows.push({id:i.id,title:i.title,state:i.state,ordered:false})}});
  hintBox.textContent=missing.length
   ?('Unbekannte Kennungen in der gespeicherten Priorisierung (nicht in diesem Projekt): '+missing.join(', ')+'. Sie werden beim nächsten Speichern entfernt.')
   :'';
  draw()};
 const save=el('button',{class:'b p',type:'button',on:{click:async()=>{
  setErr('');const r=await api('/api/priority',{name,action:'set',order:rows.map(x=>x.id).join(' ')});
  toast(r.message||'');if(!r.ok)setErr(r.message);
  if(r.ok&&r.priority)render(r.priority)}}},'Speichern');
 const clear=el('button',{class:'b',type:'button',on:{click:async()=>{
  setErr('');const r=await api('/api/priority',{name,action:'clear'});
  toast(r.message||'');if(!r.ok)setErr(r.message);
  if(r.ok&&r.priority)render(r.priority)}}},'Leeren (Standardordnung)');
 rows=(d.items||[]).map(i=>({id:i.id,title:i.title,state:i.state}));
 draw();
 api('/api/priority?name='+encodeURIComponent(name)).then(render)
  .catch(e=>setErr('Priorisierung nicht verfügbar: '+String(e&&e.message||e)));
 return el('div',{class:'card','data-open-packages-card':''},
  el('div',{class:'bar'},el('b',{},'Offene Arbeitspakete ('+d.items.length+')')),
  d.items.length?el('div',{},list,
   el('div',{class:'mut'},'Reihenfolge am Handle ändern — durch Ziehen oder mit den Pfeiltasten am Handle. „Speichern“ legt sie als PACKAGE_ORDER ab (für die Agentenläufe verbindlich); „Leeren“ stellt die Standardordnung wieder her.'),
   el('div',{class:'bar'},save,clear),hintBox,errBox)
  :el('span',{class:'ok'},'Alles abgehakt'))}

/* ---------- Kosten ---------- */
const PRICE_SOURCE={user:'eigener Preis',system:'Systempreis',kostenlos:'kostenlos',unbekannt:'Preis unbekannt'};
const COSTS_POLL_MS=5000;
const COSTS_HEAD=['Projekt','Pakete','Sitzungen','Eingabe','davon cached','Ausgabe','Kosten'];
const PACKAGE_HEAD=['Paket / Modell','Sitzungen','Eingabe','davon cached','Ausgabe','Kosten'];
function fmtN(n){return Number(n||0).toLocaleString('de-DE')}
function fmtEUR(v){return Number(v||0).toLocaleString('de-DE',{minimumFractionDigits:4,maximumFractionDigits:4})+' €'}
function pricePill(src){return el('span',{class:'pill '+(src==='user'?'ok':src==='unbekannt'?'warn':'mut'),title:'Preisquelle: '+(PRICE_SOURCE[src]||src)},PRICE_SOURCE[src]||src)}
function tokenCells(t){return [el('td',{class:'num'},fmtN(t.input)),el('td',{class:'num'},fmtN(t.cached)),el('td',{class:'num'},fmtN(t.output))]}
function costsNote(d){return el('div',{class:'mut'},'Preise in '+d.currency+' je 1 Mio. Tokens. „Eingabe“ enthält die gecachten Tokens, „Ausgabe“ die Reasoning-Tokens. Unbekannte Modelle werden mit 0 € angesetzt, bis ein Preis eingetragen ist. Eigene Preise gelten nur für dieses Projekt und schlagen Systempreise.')}
function costsStamp(){return new Date().toLocaleTimeString('de-DE')}
function costsRefreshError(node,error){node.textContent='Aktualisierung fehlgeschlagen: '+String(error&&error.message||error)}
function projectRow(p){
 return el('tr',{class:'row','data-project':p.name,on:{click:()=>costDetail(p.name).catch(showErr)}},
  el('td',{},p.name),el('td',{class:'num'},fmtN(p.packages)),el('td',{class:'num'},fmtN(p.sessions)),...tokenCells(p.tokens),el('td',{class:'num'},fmtEUR(p.cost)))
}
function projectSignature(p){return JSON.stringify([p.packages,p.sessions,p.tokens,p.cost])}
function fillProjectTotal(row,total){
 row.replaceChildren(el('td',{},el('b',{},'Gesamt')),el('td',{}),el('td',{class:'num'},fmtN(total.sessions)),...tokenCells(total.tokens),el('td',{class:'num'},el('b',{},fmtEUR(total.cost))))
}
function packageNodes(p){
 const nodes=[el('tr',{class:'row','data-package':p.id||'ohne'},el('td',{},el('b',{},p.id||'Ohne Arbeitspaket'),p.title&&p.id?el('div',{class:'mut'},p.title):null),
  el('td',{class:'num'},fmtN(p.sessions)),...tokenCells(p.tokens),el('td',{class:'num'},fmtEUR(p.cost)))];
 p.models.forEach(m=>nodes.push(el('tr',{class:'mut','data-model-row':m.model},
  el('td',{style:'padding-left:22px'},m.agent+' · '+m.model+' ',pricePill(m.price_source)),
  el('td',{}),...tokenCells(m.tokens),el('td',{class:'num'},fmtEUR(m.cost)))));
 return nodes
}
function packageSignature(p){return JSON.stringify([p.sessions,p.tokens,p.cost,p.models])}
function fillPackageTotal(row,total){
 row.replaceChildren(el('td',{},el('b',{},'Summe Projekt')),el('td',{class:'num'},fmtN(total.sessions)),...tokenCells(total.tokens),el('td',{class:'num'},el('b',{},fmtEUR(total.cost))))
}
async function costs(){
 clearInterval(timer);timer=null;
 const warning=el('div',{class:'warn',hidden:''});
 const empty=el('span',{class:'mut',hidden:''},'Keine Projekte gefunden.');
 const table=el('table',{id:'costs-table'},el('tr',{},...COSTS_HEAD.map(h=>el('th',{},h))));
 const totalRow=el('tr',{id:'costs-total'});
 table.append(totalRow);
 const sourceNote=el('div',{class:'mut',style:'margin-top:8px'});
 const updated=el('span',{class:'mut',id:'costs-updated','aria-live':'polite'});
 const rows=new Map();let lastTotal=null,lastData='',lastStamp='';
 const render=d=>{
  warning.hidden=!!d.available;
  if(!d.available)warning.textContent='Sitzungsdaten nicht verfügbar: '+(d.message||'unbekannt');
  const seen=new Set();let orderChanged=false;
  d.projects.forEach(p=>{
   seen.add(p.name);
   const sig=projectSignature(p);
   const old=rows.get(p.name);
   if(old&&old.sig===sig)return;
   const tr=projectRow(p);
   if(old)old.tr.replaceWith(tr);
   else orderChanged=true;
   rows.set(p.name,{tr,sig});
  });
  for(const[name,entry]of rows){
   if(seen.has(name))continue;
   entry.tr.remove();rows.delete(name);orderChanged=true;
  }
  if(orderChanged)d.projects.forEach(p=>{const entry=rows.get(p.name);if(entry)totalRow.before(entry.tr)});
  const totalSig=JSON.stringify([d.total.sessions,d.total.tokens,d.total.cost]);
  if(totalSig!==lastTotal){fillProjectTotal(totalRow,d.total);lastTotal=totalSig}
  table.hidden=!d.projects.length;
  empty.hidden=!!d.projects.length;
  if(!sourceNote.textContent)sourceNote.textContent='Quelle: '+(d.db||'—')+' (nur lesend). Projekt anklicken für Arbeitspakete, Agenten und Modelle.';
  const dataSig=JSON.stringify([d.available,d.projects,d.total]);
  if(dataSig!==lastData){lastData=dataSig;const stamp=costsStamp();if(stamp!==lastStamp){lastStamp=stamp;updated.textContent='Stand: '+stamp}}
 };
 const clearRefreshError=()=>{if(updated.textContent.startsWith('Aktualisierung fehlgeschlagen'))updated.textContent=lastStamp?'Stand: '+lastStamp:''};
 const refresh=async()=>{
  try{render(await api('/api/costs'));clearRefreshError()}catch(e){costsRefreshError(updated,e)}
 };
 const initial=await api('/api/costs');
 render(initial);
 main.replaceChildren(el('div',{class:'card',id:'costs'},el('div',{class:'bar'},el('b',{},'Kosten je Projekt'),el('span',{class:'mut'},'EUR je 1 Mio. Tokens')),
  warning,empty,table,sourceNote,
  el('div',{class:'bar'},updated,el('button',{class:'b',on:{click:()=>costs().catch(showErr)}},'Aktualisieren'))));
 timer=setInterval(()=>{if(tab==='costs'&&!document.hidden)refresh()},COSTS_POLL_MS);
}
async function costDetail(name){
 clearInterval(timer);timer=null;
 const d=await api('/api/costs?name='+encodeURIComponent(name));
 const warning=el('div',{class:'warn',hidden:''});
 const statePill=el('span',{class:'pill '+(d.available?'ok':'bad')},d.available?'Daten gelesen':'keine Daten');
 const empty=el('span',{class:'mut',hidden:''},'Keine Sitzungen für dieses Projekt gefunden.');
 const table=el('table',{id:'cost-detail-table'},el('tr',{},...PACKAGE_HEAD.map(h=>el('th',{},h))));
 const totalRow=el('tr',{id:'cost-detail-total'});
 table.append(totalRow);
 const priceArea=el('div',{id:'cost-price-area'});
 const updated=el('span',{class:'mut',id:'costs-updated','aria-live':'polite'});
 const packages=new Map();let lastTotal=null,lastData='',lastStamp='',priceSig=null;
 const priceCard=models=>{
  const priceInputs=[];
  const priceRows=models.map(m=>{
   const cur=m.price||{input:0,cached_input:0,output:0};
   const fields=[['input','Eingabe'],['cached_input','cached'],['output','Ausgabe']].map(([f,l])=>{
    const inp=el('input',{type:'number',min:'0',step:'0.0001','data-model':m.model,'data-field':f,'aria-label':l+' '+m.model,value:String(cur[f]??0),style:'width:110px'});
    priceInputs.push(inp);return el('label',{style:'display:inline-flex;gap:4px;align-items:center;margin-right:12px'},l,inp)});
   const reset=el('button',{class:'b',on:{click:async()=>{const r=await api('/api/costs',{name,action:'prices',prices:{[m.model]:null}});toast(r.message);if(r.ok)costDetail(name).catch(showErr)}}},'Systempreis');
   return el('div',{class:'bar','data-price-model':m.model},el('b',{},m.model),pricePill(m.price_source),...fields,reset)});
  const save=el('button',{class:'b p',on:{click:async()=>{
    const prices={};
    for(const inp of priceInputs){const raw=String(inp.value).trim().replace(',','.');
     if(raw===''){toast('Bitte für '+inp.dataset.model+' alle drei Preise eintragen.');inp.focus();return}
     const num=Number(raw);
     if(!Number.isFinite(num)||num<0){toast('Preis für '+inp.dataset.model+' ist ungültig.');inp.focus();return}
     (prices[inp.dataset.model]=prices[inp.dataset.model]||{})[inp.dataset.field]=num}
    const r=await api('/api/costs',{name,action:'prices',prices});toast(r.message);
    if(r.ok)costDetail(name).catch(showErr)}}},'Preise speichern');
  return el('div',{class:'card',id:'cost-prices'},el('b',{},'Preise je 1 Mio. Tokens (nur dieses Projekt)'),
   el('div',{class:'mut'},'Eigene Preise schlagen systemische Preise. „Systempreis“ entfernt den eigenen Preis.'),
   ...(priceRows.length?priceRows:[el('span',{class:'mut'},'Noch keine Modelle in diesem Projekt verwendet.')]),
   priceRows.length?el('div',{class:'bar'},save):null)
 };
 const renderPackages=d=>{
  const seen=new Set();let orderChanged=false;
  d.packages.forEach(p=>{
   const key=p.id||'';
   seen.add(key);
   const sig=packageSignature(p);
   const old=packages.get(key);
   if(old&&old.sig===sig)return;
   const nodes=packageNodes(p);
   if(old){const first=old.nodes[0];first.replaceWith(...nodes);old.nodes.slice(1).forEach(node=>node.remove())}
   else orderChanged=true;
   packages.set(key,{nodes,sig});
  });
  for(const[key,entry]of packages){
   if(seen.has(key))continue;
   entry.nodes.forEach(node=>node.remove());packages.delete(key);orderChanged=true;
  }
  if(orderChanged)d.packages.forEach(p=>{const entry=packages.get(p.id||'');if(entry)entry.nodes.forEach(node=>totalRow.before(node))});
 };
 const render=d=>{
  warning.hidden=!!d.available;
  if(!d.available)warning.textContent='Sitzungsdaten nicht verfügbar: '+(d.message||'unbekannt');
  statePill.textContent=d.available?'Daten gelesen':'keine Daten';
  statePill.className='pill '+(d.available?'ok':'bad');
  renderPackages(d);
  const totalSig=JSON.stringify([d.total.sessions,d.total.tokens,d.total.cost]);
  if(totalSig!==lastTotal){fillPackageTotal(totalRow,d.total);lastTotal=totalSig}
  table.hidden=!d.packages.length;
  empty.hidden=!!d.packages.length;
  const modelsSig=JSON.stringify(d.models.map(m=>[m.model,m.price_source,m.price]));
  if(modelsSig!==priceSig){priceSig=modelsSig;priceArea.replaceChildren(priceCard(d.models))}
  const dataSig=JSON.stringify([d.available,d.packages,d.total,d.models]);
  if(dataSig!==lastData){lastData=dataSig;const stamp=costsStamp();if(stamp!==lastStamp){lastStamp=stamp;updated.textContent='Stand: '+stamp}}
 };
 const clearRefreshError=()=>{if(updated.textContent.startsWith('Aktualisierung fehlgeschlagen'))updated.textContent=lastStamp?'Stand: '+lastStamp:''};
 const refresh=async()=>{
  try{render(await api('/api/costs?name='+encodeURIComponent(name)));clearRefreshError()}catch(e){costsRefreshError(updated,e)}
 };
 main.replaceChildren(
  el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>costs().catch(showErr)}},'← alle Projekte'),el('h2',{style:'margin:0'},name),el('span',{class:'mut'},'Kosten in '+d.currency)),
  el('div',{class:'card',id:'cost-detail','data-project':name},
   el('div',{class:'bar'},el('b',{},'Kosten je Arbeitspaket'),statePill),
   warning,
   costsNote(d),
   empty,table),
  priceArea,
  el('div',{class:'bar'},updated));
 render(d);
 timer=setInterval(()=>{if(tab==='costs'&&!document.hidden)refresh()},COSTS_POLL_MS);
}

/* ---------- Agenten, Modelle, Profile ---------- */
let AG=null;
function mval(node){return node&&typeof node==='object'?String(node.wert??node.text??'unbekannt'):'unbekannt'}
function msrc(node){if(!node||!node.quelle)return 'Quelle unbekannt';return node.quelle+(node.datum?' ('+node.datum+')':'')}
function mart(node){return node&&node.art?' ['+node.art+']':''}
function mAssert(label,node){return el('div',{class:'mut','data-assertion':label},el('b',{},label+': '),mval(node),mart(node),el('span',{class:'mut'},' — '+msrc(node)))}
function mList(label,rows){return el('div',{},el('b',{},label),rows&&rows.length?el('ul',{class:'l'},rows.map(node=>el('li',{},mval(node)+mart(node)+' — '+msrc(node)))):el('div',{class:'mut'},'keine Angaben'))}
function mPrice(m){const p=(m&&m.preis)||{};const rows=[el('div',{},el('b',{},'Preis: '),p.text||'unbekannt')];
 if(p.status&&p.status!=='unbekannt'){rows.push(el('div',{class:'mut'},'Währung: '+(p.waehrung||'?')+' · Einheit: '+(p.einheit||'?')+' · Stand: '+(p.stand||'?')+' · Quelle: '+(p.quelle||'?')));
  const t=p.tarife||{};rows.push(el('div',{class:'mut'},'Tarife je Einheit: Eingabe '+(t.eingabe??'?')+', Ausgabe '+(t.ausgabe??'?')+(t.cache_lesen!=null?', Cache lesen '+t.cache_lesen:'')+(t.cache_schreiben!=null?', Cache schreiben '+t.cache_schreiben:'')));
  (t.staffeln||[]).forEach(s=>rows.push(el('div',{class:'mut'},'Staffel ab '+(s.ab_kontext??'?')+' Kontext: '+(s.eingabe??'?')+' / '+(s.ausgabe??'?'))))}
 else if(p.grund){rows.push(el('div',{class:'mut'},'Grund: '+p.grund))}
 return el('div',{class:'mprice'},...rows)}
function modelLabel(id,info){const m=info[id];if(!m)return id;return `${id} — ${(m.preis||{}).text||'unbekannt'} · ${mval((m.einschaetzungen||{}).tempo)}, ${mval((m.einschaetzungen||{}).aufwand)} Aufwand, Daten ${mval((m.fakten||{}).daten)}`}
function modelSelect(models,info,current,blank){const s=el('select',{});if(blank)s.append(el('option',{value:''},blank));const groups={};
 models.forEach(m=>{(groups[m.split('/')[0]]=groups[m.split('/')[0]]||[]).push(m)});if(current&&!models.includes(current))(groups[current.split('/')[0]]=groups[current.split('/')[0]]||[]).push(current);
 Object.entries(groups).forEach(([g,ms])=>{const og=el('optgroup',{label:g});ms.forEach(m=>og.append(el('option',{value:m},modelLabel(m,info))));s.append(og)});if(current)s.value=current;return s}
function allowedLabel(agent){
 if(agent.task_mode==='all')return 'alle';
 if(agent.task_mode==='custom'&&agent.allowed_agents&&agent.allowed_agents.length)return agent.allowed_agents.join(', ');
 return 'keine';
}
async function agents(){AG=await api('/api/agents');const d=AG;
 const isPi=(await harnessSelected())==='pi';
 // AP03: Die allgemeine Verwaltung zeigt und ändert ausschließlich
 // systemweite Agenten. Projektmodelle werden nur in den Projekteinstellungen
 // überschrieben; projektlokale Agentendateien erscheinen hier nicht.
 const va=d.vibe_agent||{};
 const vibeText=!va.name?'Kein Vibe-Agent definiert. In der Liste einem Agenten die Rolle „vibe“ zuweisen.'
  :(!va.configured?'Vibe-Agent '+va.name+' hat kein Modell konfiguriert. Vorher können keine Projekte ausgeführt werden.'
   :'Vibe-Agent '+va.name+' ist bereit. Standardmodell: '+va.model+'. Ohne weitere Agenten übernimmt er alle Aufgaben.');
 const status=el('div',{id:'vibe-status','data-vibe-configured':va.configured?'ja':'nein'},
  el('div',{class:'bar'},el('b',{},'Vibe-Agent'),el('span',{class:'pill '+(va.configured?'ok':'bad')},va.configured?'bereit':'nicht konfiguriert')),
  el('div',{class:'mut'},vibeText));
 const rows=d.global_agents||[];
 const tb=el('table',{},el('tr',{},...['Agent','Rolle','Aufgabe','Ergebnis','Subagenten','Standardmodell',''].map(h=>el('th',{},h))));
 rows.forEach(a=>{
  const role=el('select',{'data-role':a.name,'aria-label':'Rolle von '+a.name},
   el('option',{value:''},'— keine Rolle —'),el('option',{value:'coder'},'coder'),
   el('option',{value:'reviewer'},'reviewer'),el('option',{value:'vibe'},'vibe (Standardagent)'),
   el('option',{value:'tester'},'tester'),el('option',{value:'analyst'},'analyst'),
   el('option',{value:'sonstiges'},'sonstiges'),el('option',{value:'content-creator'},'content-creator'));
  role.value=a.role||'';
  role.addEventListener('change',async()=>{const r=await api('/api/agent',{action:'role',scope:'global',name:a.name,role:role.value});
   toast(r.message);if(r.ok)agents().catch(showErr);else role.value=a.role||''});
  tb.append(el('tr',{'data-agent':a.name,'data-scope':'global'},
   el('td',{},a.name,a.is_vibe?el('span',{class:'pill ok'},' vibe'):null,
    a.valid?null:el('span',{class:'pill bad',title:'Datei ist kein gültiger Agent – im Rohtexteditor bearbeitbar'},' defekt')),
   el('td',{},role),
   el('td',{'data-aufgabe':a.name},a.description||'—'),
   el('td',{class:'mut','data-ergebnis':a.name},a.result||'—'),
   el('td',{'data-erlaubt':a.name},allowedLabel(a)),
   el('td',{class:'mut','data-modell':a.name},a.model_missing?'— nicht gesetzt —':a.model),
   el('td',{},el('button',{class:'b',type:'button',on:{click:()=>agentForm('global',a.name).catch(showErr)}},'Bearbeiten'))));
 });
 main.replaceChildren(el('div',{class:'card',id:'agents'},
   el('div',{class:'bar'},el('b',{},'Agenten'),el('button',{class:'b p',type:'button',on:{click:()=>agentForm(null,null).catch(showErr)}},'Neuer Agent')),
   status,
   rows.length?el('div',{class:'tablewrap'},tb):el('span',{class:'mut'},'Keine systemweiten Agenten vorhanden.'),
   el('div',{class:'mut',style:'margin-top:8px'},isPi
    ? 'Bei Pi ist die Agentendatei nur die Prompt-Quelle: Der Lauf liest den Prompt-Text der Datei, Frontmatter (Beschreibung, Rechte, Modell) bleibt ungenutzt. Die Dateien liegen weiterhin unter ~/.config/opencode/agents und gelten für alle Projekte.'
    : 'Systemweite Agenten liegen unter ~/.config/opencode/agents und gelten für alle Projekte. Ein Projekt verwendet ausschließlich diese Agenten; nur sein Modell lässt sich in den Projekteinstellungen überschreiben. Aufgabe, Ergebnis und Subagenten-Rechte sind hier direkt sichtbar.')),
  profilesCard(d,isPi),modelsCard(d,isPi))}
function profilesCard(d,isPi){const P=JSON.parse(JSON.stringify(d.profiles));const names=Object.keys(P.profile);const cur=el('select',{},...names.map(n=>el('option',{value:n},n+(n===P.aktiv?' (aktiv)':''))));cur.value=P.aktiv;
 const roles=['coder','reviewer'];const body=el('div',{});
 const draw=()=>{const prof=P.profile[cur.value];body.replaceChildren(
   el('table',{},el('tr',{},el('th',{},'Rolle'),el('th',{},'Agenten in dieser Rolle'),el('th',{},'Modell im Profil „'+cur.value+'“')),
    ...roles.map(r=>{const ms=modelSelect(d.models,d.info,prof[r]||'','— nicht ändern —');ms.addEventListener('change',()=>{prof[r]=ms.value});
      return el('tr',{},el('td',{},r),el('td',{class:'mut'},Object.entries(P.rollen).filter(([a,x])=>x===r).map(([a])=>a).join(', ')||'—'),el('td',{},ms))})))};
 cur.addEventListener('change',draw);draw();
 const roleRows=(d.global_agents||[]).filter(a=>a.role).map(a=>a.name+' → '+a.role);
 const rol=el('div',{class:'mut'},'Rollen werden in der Agentenliste gesetzt (Rolle je Agent). '+(roleRows.length?roleRows.join(' · '):'Noch keine Rolle zugewiesen.'));
 return el('div',{class:'card'},el('details',{open:'open'},el('summary',{},'Profile – Modelle pro Rolle umschalten (z. B. kostenlos ↔ bezahlt)'),
  el('div',{class:'mut',style:'margin:6px 0'},'Ein Profil legt fest, welches Modell die Rollen Coder und Reviewer nutzen. „Anwenden“ schreibt die model:-Zeile der zugeordneten globalen Agenten (mit Sicherung). '+(isPi?'Bezahlte Modelle erscheinen erst, wenn der Anbieter in Pi angemeldet ist (Ergebnis von „pi --list-models“).':'Bezahlte Modelle erscheinen erst, wenn der Anbieter verbunden ist (/connect bzw. opencode auth login).')),
  el('div',{class:'bar'},cur,el('button',{class:'b',on:{click:async()=>{const r=await api('/api/profiles',{action:'save',data:P});toast(r.message)}}},'Profile speichern'),
   el('button',{class:'b p',on:{click:async()=>{const sv=await api('/api/profiles',{action:'save',data:P});const r=await api('/api/profiles',{action:'use',profile:cur.value});toast(r.message);if(r.ok)agents().catch(showErr)}}},'Speichern und anwenden')),body,rol))}
function modelsCard(d,isPi){const used={};d.agents.forEach(a=>{(used[a.model]=used[a.model]||[]).push(a.name+(a.scope==='global'?'':'@'+a.scope))});
 const K=d.katalog||{};const known=d.models.length>0;
 const ids=d.models.filter(m=>m.startsWith('opencode/')||d.info[m]);Object.keys(d.info).forEach(i=>{if(!ids.includes(i))ids.push(i)});
 const other={};d.models.filter(m=>!m.startsWith('opencode/')&&!d.info[m]).forEach(m=>{other[m.split('/')[0]]=(other[m.split('/')[0]]||0)+1});
 const tb=el('table',{},el('tr',{},...['Modell','Anbieter','Preis','Tempo','Aufwand','Daten','Bilder','Coder','Reviewer','in Verwendung'].map(h=>el('th',{},h))));
 ids.forEach(id=>{const m=d.info[id]||null;const gone=!!m&&known&&!d.models.includes(id);
  let det;
  if(!m){det=el('tr',{class:'detail','data-model-detail':id},el('td',{colspan:'10'},el('div',{'data-model-unknown':'1'},
    el('b',{},'Kein Katalogeintrag'),el('div',{class:'mut'},'Für dieses verbundene Modell liegen keine belegten Fakten, Einschätzungen oder Preise vor.'))));det.style.display='none'}
  else{const facts=Object.entries(m.fakten||{}).map(([k,n])=>mAssert(k,n));
   const assessments=Object.entries(m.einschaetzungen||{}).map(([k,n])=>mAssert(k,n));
   const beleg=m.id_beleg||{};
   det=el('tr',{class:'detail','data-model-detail':id},el('td',{colspan:'10'},el('div',{class:'grid3'},
    el('div',{class:'mfacts'},el('b',{},'Fakten (Quelle/Datum)'),...(facts.length?facts:[el('div',{class:'mut'},'keine Angaben')])),
    el('div',{class:'mopinion'},el('b',{},'Einschätzungen (Quelle/Datum)'),...(assessments.length?assessments:[el('div',{class:'mut'},'keine Angaben')]),mList('Stärken',m.staerken),mList('Schwächen',m.schwaechen)),
    el('div',{class:'mproof'},el('b',{},'Preis und Beleg'),mPrice(m),
     el('div',{class:'mut'},'ID-Beleg: '+(beleg.quelle||'—')+(beleg.datum?' ('+beleg.datum+')':'')),
     el('div',{class:'mut'},'ID-Status: '+(m.id_status||'unbekannt')),
     gone?el('div',{class:'bad'},isPi
      ?'Nicht in „pi --list-models“ (Pi meldet dieses Modell nicht; Anbieter in Pi abgemeldet oder Modell entfernt).'
      :'Nicht in „opencode models“ (Anbieter nicht verbunden oder Modell entfernt).'):null,
     m.id_status==='entfernt'?el('div',{class:'bad'},'Als entfernt geführt'+(m.entfernt_am?' seit '+m.entfernt_am:'')+(m.entfernt_quelle?' ('+m.entfernt_quelle+')':'')):null))));
   det.style.display='none'}
  const price=(m&&m.preis)||{};
  const removed=!!m&&(gone||m.id_status==='entfernt');
  tb.append(el('tr',{class:'row','data-model-row':id,on:{click:()=>{det.style.display=det.style.display==='none'?'table-row':'none'}}},
   el('td',{},'▸ '+((m&&m.name)||id),removed?el('span',{class:'pill bad'},' nicht mehr gelistet'):null,el('div',{class:'mut'},id)),
   el('td',{class:'mut'},(m&&m.anbieter)||'?'),
   el('td',{class:'mprice-cell','data-price-status':price.status||'unbekannt'},price.text||'unbekannt'),
   el('td',{},badge(mval(m&&(m.einschaetzungen||{}).tempo))),el('td',{},badge(mval(m&&(m.einschaetzungen||{}).aufwand))),
   el('td',{},badge(mval(m&&(m.fakten||{}).daten))),el('td',{},badge(mval(m&&(m.fakten||{}).bild))),
   el('td',{},badge(mval(m&&(m.einschaetzungen||{}).coder))),el('td',{},badge(mval(m&&(m.einschaetzungen||{}).reviewer))),
   el('td',{class:'mut'},(used[id]||[]).join(', ')||'—')));tb.append(det)});
 const findings=K.findings||[];
 const findingBox=findings.length?el('div',{class:'card err','data-catalog-findings':findings.length},el('b',{},'Katalogbefunde ('+findings.length+')'),el('ul',{class:'l'},findings.map(f=>el('li',{},f.text)))):null;
 const legacy=K.legacy?el('div',{class:'bad'},'Altkatalog (Schema 1): Die Angaben sind nicht erneut geprüft und nur als Altbestand lesbar.'):null;
 const nei=K.nicht_uebernommen||[];
 const altbestand=nei.length?el('details',{'data-not-adopted':'1'},el('summary',{},'Nicht übernommene Altbestände ('+nei.length+')'),
   el('div',{class:'mut'},'Diese Modelle standen im Altkatalog, sind aber am Prüftag nicht bestätigt und werden deshalb nicht als Fakten geführt.'),
   el('ul',{class:'l'},nei.map(x=>el('li',{},el('b',{},x.id),' – '+(x.grund||'kein Grund'))))):null;
 const sources=(K.quellen||[]).map(q=>q.name+(q.datum?' ('+q.datum+')':''));
 return el('div',{class:'card',id:'models'},el('details',{},el('summary',{},'Modelle – Fakten, Einschätzungen und Preise (aufklappen, Zeile anklicken für Details)'),
   el('div',{class:'mut',style:'margin:8px 0'},'Stand '+(d.stand||'?')+' · Katalog '+(K.version||'?')+'. '+d.hinweis),
   legacy,findingBox,
   el('div',{class:'mut','data-catalog-sources':'1'},'Quellen: '+(sources.length?sources.join('; '):'keine Quellen im Katalog')),
   tb,
   altbestand,
   Object.keys(other).length?el('div',{class:'mut',style:'margin-top:8px'},'Weitere verbundene Anbieter (ohne Katalogeintrag): '+Object.entries(other).map(([k,v])=>k+' ('+v+' Modelle)').join(', ')):null))}
async function agentForm(scope,name){const d=AG||await api('/api/agents');const isNew=!name;
 let text='',digest=null,fields={},backups=[];
 if(!isNew){const loaded=await api('/api/agent?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name));text=loaded.text;digest=loaded.digest;fields=loaded.fields||{};backups=loaded.backups||[]}
 const structured=!fields.invalid;
 // AP03: In der allgemeinen Verwaltung werden ausschließlich systemweite
 // Agenten angelegt und bearbeitet. Projekte überschreiben nur das Modell.
 const row=(d.global_agents||[]).find(a=>a.name===name)||{};
 const nm=el('input',{'aria-label':'Name',placeholder:'name (a-z, 0-9, -, _)'});if(!isNew){nm.value=name;nm.setAttribute('disabled','disabled')}
 const sc=el('select',{'aria-label':'Geltung'},el('option',{value:'global'},'global (alle Projekte)'));sc.value='global';sc.setAttribute('disabled','disabled');
 const ds=el('input',{'aria-label':'Beschreibung',placeholder:'Wofür ist der Agent da? (Pflicht)',value:fields.description||''});
 const md=el('select',{'aria-label':'Modus'},el('option',{value:''},'— nicht gesetzt —'),el('option',{value:'subagent'},'subagent (wird von anderen aufgerufen)'),el('option',{value:'primary'},'primary (direkt startbar)'),el('option',{value:'all'},'all'));
 md.value=fields.mode||(isNew?'subagent':'');
 const mo=modelSelect(d.models,d.info,fields.model||'','— Standardmodell —');mo.setAttribute('aria-label','Modell');
 // AP03: Rolle, Ergebnis und Subagenten-Rechte. Die Rolle wird in
 // profiles.json geführt, das Ergebnis getrennt von der Agentendatei.
 const ro=el('select',{'aria-label':'Rolle'},el('option',{value:''},'— keine Rolle —'),
  el('option',{value:'coder'},'coder'),el('option',{value:'reviewer'},'reviewer'),
  el('option',{value:'vibe'},'vibe (Standardagent)'));
 ro.value=row.role||'';
 const rs=el('input',{'aria-label':'Ergebnis',placeholder:'Was liefert der Agent?',value:row.result||''});
 const tm=el('select',{'aria-label':'Subagenten-Rechte'},el('option',{value:'keine'},'keine'),
  el('option',{value:'ausgewählt'},'ausgewählt'),el('option',{value:'alle'},'alle'));
 tm.value=row.task_mode==='all'?'alle':(row.task_mode==='custom'?'ausgewählt':'keine');
 const allowed=new Set(row.allowed_agents||[]);
 // F32: Den eigenen Namen separat führen; bei isNew gibt es ihn noch nicht.
 if(!isNew)allowed.delete(name);
 let selfOn=(row.allowed_agents||[]).includes(name);
 const otherAgents=(d.global_agents||[]).filter(a=>a.name!==name&&(a.mode==='subagent'||a.mode==='all')).map(a=>a.name);
 const subBox=el('div',{'data-subagents':'1'});
 const drawSubs=()=>{subBox.replaceChildren();
  if(tm.value!=='ausgewählt')return;
  subBox.append(el('div',{class:'mut'},'Erlaubte Subagenten (nur systemweite Agenten):'));
  otherAgents.forEach(a=>{const cb=el('input',{type:'checkbox','data-subagent':a,'aria-label':'Subagent '+a});
   cb.checked=allowed.has(a);
   cb.addEventListener('change',()=>{if(cb.checked)allowed.add(a);else allowed.delete(a)});
   subBox.append(el('label',{style:'display:block'},cb,' ',a))});
  // F32: Vibe-Rolle hat Vorrang vor dem Modus; sonst die Opt-in-Checkbox.
  if(ro.value==='vibe'){
   subBox.append(el('div',{class:'mut'},'Der Vibe-Agent ruft keine Subagenten seines eigenen Typs auf.'));
  }else if(md.value==='primary'){
   subBox.append(el('div',{class:'mut'},'Subagenten des eigenen Typs erfordern den Modus subagent oder all.'));
  }else{
   const cb=el('input',{type:'checkbox'});
   cb.checked=selfOn;
   cb.addEventListener('change',()=>{selfOn=cb.checked});
   subBox.append(el('label',{style:'display:block'},cb,' Subagenten des eigenen Typs erlauben (Parallelisierung)'),
    el('div',{class:'mut'},'Kein Standard: nur aktivieren, wenn dieser Agent Arbeit an Agenten desselben Typs parallelisieren soll.'));
  }};
 tm.addEventListener('change',drawSubs);md.addEventListener('change',drawSubs);ro.addEventListener('change',drawSubs);drawSubs();
 const permsFor=()=>d.perms;
 const pm=el('select',{'aria-label':'Rechte'});
 const setPerms=()=>{const keep=pm.value;const list=Object.entries(permsFor()).map(([k,v])=>el('option',{value:k},v));
  if(!isNew)list.unshift(el('option',{value:''},fields.permission_custom?'individuell – unverändert lassen':'— nicht gesetzt —'));
  pm.replaceChildren(...list);
  pm.value=keep&&permsFor()[keep]?keep:(isNew?'lesen':(fields.permission&&permsFor()[fields.permission]?fields.permission:''))};
 setPerms();
 const tp=el('input',{'aria-label':'Temperatur',placeholder:'z. B. 0.1',value:isNew?'0.1':(fields.temperature||'')});
 const st=el('input',{'aria-label':'Max. Schritte',placeholder:'z. B. 60',value:isNew?'':(fields.steps||'')});
 const pr=el('textarea',{'aria-label':'Prompt',rows:5,placeholder:'System-Prompt: Rolle, Regeln, Ausgabeformat',value:isNew?'':(fields.prompt||'')});
 const raw=el('textarea',{class:'raw','aria-label':'Datei (Frontmatter + Prompt)'});raw.value=text;
 // F17: Ausgangsstand der strukturierten Felder. Beim Speichern werden nur
 // geänderte Felder übernommen; freie Rohtextänderungen an anderer Stelle
 // bleiben erhalten und eine geänderte Modellauswahl geht nicht verloren.
 const formValues=()=>({description:ds.value,mode:md.value,model:mo.value,temperature:tp.value,steps:st.value,permission:pm.value,prompt:pr.value});
 let baseline=formValues();
 const hint=el('div',{class:'mut'});
 const updHint=()=>{const dirs=sc.value==='global'?null:(d.write_dirs[sc.value]||[]);const err=sc.value==='global'?null:(d.write_dirs_errors||{})[sc.value];
  hint.textContent=err?'Schreibrechte nicht lesbar: '+err:(sc.value==='global'?'Global: volle Schreibrechte ohne Verzeichnisgrenze.':'Schreibrechte (edit, voll) nur in: '+(dirs&&dirs.length?dirs.join(', '):'keine Verzeichnisse – Schreiben gesperrt')+'. Shell (bash) bleibt erlaubt.')};
 updHint();
 const unknown=el('div',{class:'mut',id:'agent-unknown'},
  fields.invalid?'Strukturierte Bearbeitung nicht möglich: '+fields.invalid:
  (fields.unknown&&fields.unknown.length?'Unbekannte Felder bleiben beim Speichern erhalten: '+fields.unknown.join(', '):'Keine unbekannten Frontmatter-Felder.'));
 const gen=async()=>{const r=await api('/api/agent_template',{description:ds.value,mode:md.value,model:mo.value,temperature:tp.value,steps:st.value,perm:pm.value||'lesen',prompt:pr.value,scope:sc.value});if(r.ok)raw.value=r.message;else toast(r.message)};
 const apply=async()=>{if(!structured){toast('Strukturierte Bearbeitung nicht möglich: '+fields.invalid);return}
  const r=await api('/api/agent',{action:'render',scope:sc.value,name:name,text:raw.value,values:{description:ds.value,mode:md.value,model:mo.value,temperature:tp.value,steps:st.value,permission:pm.value,prompt:pr.value}});
  toast(r.message);if(r.ok)raw.value=r.text};
 // AP03: Vibe unterstützt aktiv bei der Formulierung des Prompts. Das Gerüst
 // stellt Aufgabe und Ergebnis in den Mittelpunkt und kapselt die Aufgabe ab.
 const scaffold=async()=>{const r=await api('/api/agent',{action:'scaffold',aufgabe:ds.value,ergebnis:rs.value});
  toast(r.message);if(r.ok)pr.value=r.message};
 sc.addEventListener('change',()=>{setPerms();updHint();if(isNew)gen().catch(showErr)});
 if(isNew)setTimeout(()=>gen().catch(showErr),0);
 const kopf=isNew?el('div',{},el('div',{class:'grid'},el('div',{},el('label',{},'Name'),nm),el('div',{},el('label',{},'Geltung'),sc))):
  el('div',{},el('div',{class:'bar'},el('b',{},name),el('span',{class:'pill'},scope==='global'?'global':'Projekt: '+scope),
   el('span',{class:'mut'},(d.agents.find(a=>a.name===name&&a.scope===scope)||{}).priority||'')));
 const felder=el('div',{id:'agent-fields'},
  el('label',{},'Beschreibung'),ds,
  el('div',{class:'grid3'},el('div',{},el('label',{},'Modus'),md),el('div',{},el('label',{},'Modell'),mo),el('div',{},el('label',{},'Rechte'),pm)),
  hint,
  el('div',{class:'grid'},el('div',{},el('label',{},'Temperatur'),tp),el('div',{},el('label',{},'Max. Schritte'),st)),
  el('div',{class:'grid'},el('div',{},el('label',{},'Rolle'),ro),el('div',{},el('label',{},'Ergebnis'),rs)),
  el('label',{},'Subagenten-Rechte'),tm,subBox,
  el('label',{},'Prompt'),pr,unknown,
  el('div',{class:'bar'},isNew?el('button',{class:'b',type:'button',on:{click:()=>gen()}},'Datei aus Eingaben erzeugen'):
   el('button',{class:'b',type:'button',on:{click:()=>apply()}},'In Rohtext übernehmen'),
   el('button',{class:'b',type:'button',on:{click:()=>scaffold()}},'Prompt-Gerüst'),
   el('span',{class:'mut'},'Das Ergebnis unten kann vor dem Speichern frei bearbeitet werden.')));
 const save=async()=>{const n=isNew?nm.value:name,s='global';
  if(!n){toast('Name fehlt');return}
  // Ein laufendes Speichern sperrt den Knopf, damit ein zweiter Klick nicht
  // mit veralteter Prüfsumme geschrieben wird.
  saveBtn.disabled=true;
  try{
   const payload={action:'save',scope:s,name:n,text:raw.value,create:isNew,expected:digest};
   if(structured){const current=formValues(),changed={};for(const k in current)if(current[k]!==baseline[k])changed[k]=current[k];
    if(Object.keys(changed).length)payload.values=changed}
   const own=isNew?nm.value.trim():name;
   const allowedNow=[...allowed].sort();
   if(own){if(selfOn){if(!allowedNow.includes(own))allowedNow.push(own)}
    else{const i=allowedNow.indexOf(own);if(i>=0)allowedNow.splice(i,1)}}
   allowedNow.sort();
   const allowedBefore=[...(row.allowed_agents||[])].sort();
   const modeNow=tm.value==='alle'?'all':(tm.value==='ausgewählt'?'custom':'none');
   const taskChanged=isNew||modeNow!==(row.task_mode||'none')||(modeNow==='custom'&&allowedNow.join(',')!==allowedBefore.join(','));
   if(isNew||ro.value!==(row.role||''))payload.role=ro.value;
   if(isNew||rs.value!==(row.result||''))payload.result=rs.value;
   if(taskChanged){if(modeNow==='all')payload.task_all=true;else payload.task_allowed=modeNow==='custom'?allowedNow:[]}
   const r=await api('/api/agent',payload);toast(r.message);
   if(r.ok){baseline=formValues();row.role=ro.value;row.result=rs.value;row.task_mode=modeNow;row.allowed_agents=allowedNow;
    if(isNew)agents().catch(showErr);else{digest=r.digest;raw.value=r.text}}
  }finally{saveBtn.disabled=false}};
 const saveBtn=el('button',{class:'b p',type:'button',on:{click:save}},'Speichern');
 const delAgent=isNew?null:el('button',{class:'b d',type:'button',on:{click:()=>askInline(delAgent,'Agent „'+name+'“ löschen? Eine Sicherung bleibt in agent-backups.','Ja, löschen',async()=>{const r=await api('/api/agent',{action:'delete',scope,name});toast(r.message);if(r.ok)agents().catch(showErr)})}},'Löschen');
 const backupBox=el('div',{id:'agent-backups'},el('span',{class:'mut'},'Noch keine Sicherung.'));
 const drawBackups=()=>{backupBox.replaceChildren(...(backups.length?backups.map(b=>{const btn=el('button',{class:'b',type:'button',on:{click:()=>askInline(btn,'Sicherung „'+b+'“ wiederherstellen? Der aktuelle Stand wird vorher gesichert.','Ja, wiederherstellen',async()=>{const r=await api('/api/agent',{action:'restore',scope,name,backup:b});toast(r.message);if(r.ok)agentForm(scope,name).catch(showErr)})}},'Wiederherstellen');
  return el('div',{class:'bar'},el('span',{class:'mut'},b),btn)}):[el('span',{class:'mut'},'Noch keine Sicherung vorhanden.')]))};
 const backupBtn=isNew?null:el('button',{class:'b',type:'button',on:{click:async()=>{const loaded=await api('/api/agent?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name));backups=loaded.backups||[];drawBackups();backupBox.hidden=false;toast(backups.length?backups.length+' Sicherung(en).':'Noch keine Sicherung vorhanden.')}}},'Sicherungen anzeigen');
 main.replaceChildren(el('div',{class:'bar'},el('button',{class:'b',type:'button',on:{click:()=>agents().catch(showErr)}},'← zurück'),el('h2',{style:'margin:0'},isNew?'Neuer Agent':'Agent bearbeiten')),
  el('div',{class:'card'},kopf,felder,el('label',{},'Datei (Frontmatter + Prompt)'),raw,
   el('div',{class:'bar'},saveBtn,
    isNew?null:backupBtn,delAgent)),
  isNew?null:el('div',{class:'card'},el('b',{},'Sicherungen'),el('div',{class:'mut'},'Vor jedem Speichern wird der bisherige Stand gesichert. Die Wiederherstellung sichert zuerst den aktuellen Stand.'),backupBox))}
/* ---------- MCP-Tools ---------- */
async function mcp(){const d=await api('/api/mcp');
 const isPi=(await harnessSelected())==='pi';
 const tb=el('table',{},el('tr',{},...['Name','Geltung','Typ','Ziel','aktiv',''].map(h=>el('th',{},h))));
 d.servers.forEach(s=>{ if(s.error){tb.append(el('tr',{},el('td',{colspan:'6',class:'bad'},s.scope+': Konfiguration nicht lesbar: '+s.error)));return}
  tb.append(el('tr',{},el('td',{},s.name),el('td',{},s.scope==='global'?el('span',{class:'pill ok'},'global'):el('span',{class:'pill'},'Projekt: '+s.scope)),el('td',{},s.type),el('td',{class:'mut'},s.target),el('td',{},badge(s.enabled?'ja':'nein')),
   el('td',{},el('div',{class:'bar',style:'margin:0'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/mcp',{action:'test',scope:s.scope,name:s.name});mcpResult(r)}}},'Testen'),
    el('button',{class:'b',on:{click:()=>mcpForm(s.scope,s.name).catch(showErr)}},'Bearbeiten'),
    el('button',{class:'b',on:{click:async()=>{const r=await api('/api/mcp',{action:'toggle',scope:s.scope,name:s.name});toast(s.name+' '+r.message);mcp().catch(showErr)}}},s.enabled?'Ausschalten':'Einschalten')))))});
 const layouts=[...new Set(d.servers.filter(s=>s.layout).map(s=>s.scope+': '+s.layout+' → '+s.path))];
 main.replaceChildren(el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'MCP-Server (Model Context Protocol)'),el('button',{class:'b p',on:{click:()=>mcpForm(null,null).catch(showErr)}},'Neuer MCP-Server')),
  d.servers.length?tb:el('span',{class:'mut'},'Keine MCP-Server konfiguriert.'),
  el('div',{class:'mut',style:'margin-top:8px'},'MCP-Server geben dem Agenten zusätzliche Werkzeuge (z. B. Notizen, Datenbanken, Dokumentation). Die Werkzeuge belegen Kontext und kosten dadurch Tokens: nur aktivieren, was gebraucht wird. Geheimnisse (Token, Schlüssel) werden hier maskiert; beim Speichern bleiben sie unverändert.'),
  el('div',{class:'mut'},'Verbindungstest: startet bei local ein Programm und stellt bei remote eine Netzverbindung her. Unterstützt werden local (stdio) und remote (Streamable HTTP); andere Transporte werden nicht getestet. Geprüft werden nur initialize und tools/list, keine fachlichen Werkzeuge. OAuth: vibe führt keine Anmeldung durch und liest keine Tokens. '+(isPi?'Bei Pi werden MCP-Server vom Agentenlauf nicht eingebunden; die Konfiguration richtet sich auf opencode aus.':'Bei OAuth-Servern zuerst „opencode mcp auth“ ausführen.')),
  layouts.length?el('div',{class:'mut'},'Konfigurationsdateien: '+layouts.join(' | ')):null),el('div',{id:'mcpres'}))}
function mcpResult(r,into){const t=r.result;const box=into||document.getElementById('mcpres');if(!box)return toast(r.message);
 box.replaceChildren(el('div',{class:'card '+(t&&t.ok?'':'err')},el('b',{class:t&&t.ok?'ok':'bad'},t?(t.ok?'Test bestanden':'Test fehlgeschlagen'):'Fehler'),r.ok?null:el('div',{class:'bad'},r.message),
  t&&t.warning?el('div',{class:'warn'},'Hinweis: '+t.warning):null,
  t&&t.transport?el('div',{class:'mut'},'Transport: '+t.transport):null,
  t&&t.category?el('div',{class:'mut'},'Fehlerart: '+t.category):null,
  t&&t.server&&t.server.name?el('div',{class:'mut'},'Server: '+t.server.name+' '+(t.server.version||'')):null,...(t?t.steps.map(s=>el('div',{class:'mut'},'✓ '+s)):[]),...(t&&t.notes?t.notes.map(n=>el('div',{class:'mut'},'ℹ '+n)):[]),
  t&&t.error?el('div',{class:'bad'},t.error):null,t&&t.hint?el('div',{class:'warn'},'Hinweis: '+t.hint):null,
  t&&t.tools&&t.tools.length?el('div',{},el('b',{},t.tools.length+' Werkzeuge'),el('ul',{class:'l'},t.tools.map(x=>el('li',{},el('b',{},x.name),x.description?' – '+x.description:'')))):null))}
const lines=s=>s.split('\n').map(x=>x.trim()).filter(Boolean);
const kv=(s,sep)=>{const o={};lines(s).forEach(l=>{const i=l.indexOf(sep);if(i>0)o[l.slice(0,i).trim()]=l.slice(i+1).trim()});return o};
const unkv=(o,sep)=>Object.entries(o||{}).map(([a,b])=>a+sep+b).join('\n');
async function mcpForm(scope,name){const d=await api('/api/mcp');let e={type:'local',command:[],enabled:true},digest=null;
 if(name){const loaded=await api('/api/mcp_entry?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name));e=loaded.entry;digest=loaded.digest}
 const isNew=!name;const nm=el('input',{value:name||'',placeholder:'name (Buchstaben, Ziffern, _ -)'});
 const sc=el('select',{},el('option',{value:'global'},'global (alle Projekte)'),...d.projects.map(p=>el('option',{value:p},'Projekt: '+p)));sc.value=scope||'global';if(!isNew)sc.setAttribute('disabled','disabled');
 const ty=el('select',{},el('option',{value:'local'},'local (Programm starten, stdio)'),el('option',{value:'remote'},'remote (URL, Streamable HTTP)'));ty.value=e.type||'local';
 const cmd=el('textarea',{rows:4,placeholder:'ein Argument pro Zeile, z. B.\nnpx\n-y\n@modelcontextprotocol/server-everything'});cmd.value=(e.command||[]).join('\n');
 const envv=el('textarea',{rows:3,placeholder:'NAME=Wert (eine pro Zeile; {env:VARIABLE} erlaubt)'});envv.value=unkv(e.environment,'=');
 const cwd=el('input',{value:e.cwd||'',placeholder:'optional'});
 const url=el('input',{value:e.url||'',placeholder:'https://…/mcp'});
 const hdr=el('textarea',{rows:3,placeholder:'Name: Wert (eine pro Zeile, z. B. Authorization: Bearer {env:TOKEN})'});hdr.value=unkv(e.headers,': ');
 const noauth=el('input',{type:'checkbox'});noauth.checked=e.oauth===false;
 const en=el('input',{type:'checkbox'});en.checked=e.enabled!==false;
 const to=el('input',{value:String(e.timeout||''),placeholder:'ms, Standard 30000'});
 const loc=el('div',{},el('label',{},'Befehl (Programm und Argumente)'),cmd,el('label',{},'Umgebungsvariablen'),envv,el('label',{},'Arbeitsordner'),cwd);
 const rem=el('div',{},el('label',{},'URL'),url,el('label',{},'Header'),hdr,el('label',{},el('span',{},'OAuth abschalten (für Server mit Schlüssel im Header) '),noauth));
 const show=()=>{loc.style.display=ty.value==='local'?'block':'none';rem.style.display=ty.value==='remote'?'block':'none'};ty.addEventListener('change',show);show();
 const build=()=>{const o={type:ty.value};if(ty.value==='local'){o.command=lines(cmd.value);const ev=kv(envv.value,'=');if(Object.keys(ev).length)o.environment=ev;if(cwd.value.trim())o.cwd=cwd.value.trim()}
  else{o.url=url.value.trim();const hv=kv(hdr.value,':');if(Object.keys(hv).length)o.headers=hv;if(noauth.checked)o.oauth=false;else if(e.oauth&&typeof e.oauth==='object')o.oauth=e.oauth}
  o.enabled=en.checked;if(to.value.trim())o.timeout=parseInt(to.value,10);return o};
 const res=el('div',{});
 const delMcp=isNew?null:el('button',{class:'b d',on:{click:()=>askInline(delMcp,'MCP-Server „'+name+'“ löschen?','Ja, löschen',async()=>{const r=await api('/api/mcp',{action:'delete',scope,name});toast(r.message);if(r.ok)mcp().catch(showErr)})}},'Löschen');
 main.replaceChildren(el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>mcp().catch(showErr)}},'← zurück'),el('h2',{style:'margin:0'},isNew?'Neuer MCP-Server':'MCP-Server bearbeiten')),
  el('div',{class:'card'},el('div',{class:'grid'},el('div',{},el('label',{},'Name (Werkzeuge erscheinen mit diesem Präfix)'),nm),el('div',{},el('label',{},'Geltung'),sc)),
   el('div',{class:'grid'},el('div',{},el('label',{},'Typ'),ty),el('div',{},el('label',{},'Timeout (ms)'),to)),loc,rem,el('label',{},el('span',{},'aktiv '),en),
   el('div',{class:'mut',style:'margin-top:6px'},'Maskierte Werte (***) bleiben beim Speichern unverändert. Zum Ändern den ganzen Wert neu eintragen.'),
   el('div',{class:'mut'},'Beim Testen wird ein Programm gestartet (local) oder eine Netzverbindung hergestellt (remote). Der Test ruft nur initialize und tools/list auf, keine fachlichen Werkzeuge. OAuth-Anmeldungen führt vibe nicht durch.'),
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/mcp',{action:'save',scope:isNew?sc.value:scope,name:nm.value,old_name:isNew?'':name,create:isNew,entry:build(),expected:digest});toast(r.message);if(r.ok)mcp().catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:async()=>{res.replaceChildren(el('div',{class:'mut'},'Teste … (kann bis zu einer Minute dauern, z. B. wenn npx Pakete lädt)'));const r=await api('/api/mcp',{action:'test',scope:isNew?sc.value:scope,name:isNew?'':name,entry:build()});mcpResult(r,res)}}},'Testen (mit den Werten oben)'),
    delMcp)),res)}
function harnessCard(hs){
 const sel=el('select',{id:'harness-select','aria-label':'Harness'});
 hs.harnesses.forEach(h=>sel.append(el('option',{value:h.harness},h.name+' ('+h.harness+')')));
 sel.value=hs.selected;
 const result=el('div',{});
 const use=el('button',{class:'b p',id:'harness-use',on:{click:async()=>{
  use.disabled=true;
  try{const r=await api('/api/harness',{action:'use',harness:sel.value});
   result.replaceChildren(el('span',{class:r.ok?'ok':'bad'},r.message));if(r.ok)header()}
  catch(e){result.replaceChildren(el('span',{class:'bad'},String(e&&e.message||e)))}
  finally{use.disabled=false}}}}, 'Harness verwenden');
 const entries=hs.harnesses.map(h=>el('div',{class:'mut'},el('b',{},h.name+' ('+h.harness+')'),' – ',
  h.installed?(h.version?'Version '+h.version:'vorhanden'):'nicht installiert',
  h.hint?el('div',{},h.hint):null,
  h.official?el('div',{},'Offiziell: '+h.official):null,
  h.install_command&&h.install_command.length?el('div',{},'Einrichten: '+h.install_command.join(' ')):null));
 return el('div',{class:'card',id:'harness'},el('b',{},'Harness'),
  el('div',{class:'bar'},el('label',{style:'margin:0'},el('span',{},' Aktiver Harness '),sel),use),result,
  el('div',{class:'mut'},'Die Auswahl gilt für neue Agentenläufe; laufende Prozesse werden nicht umgestellt. Ohne gespeicherte Auswahl bleibt opencode der Standard.'),
  ...entries)}
async function env(){const d=await api('/api/doctor');const f=await api('/api/fritz');const rel=await api('/api/health');const hs=await api('/api/harness');
 const origin=rel.release_origin==='installation'?'Installation':rel.release_origin==='quelle'?'Quelle':'unbekannt';
 main.replaceChildren(el('div',{class:'card'},el('b',{},'Release'),el('div',{},'Version '+rel.version+(rel.commit?' · Commit '+rel.commit:'')+' · '+origin)),
  harnessCard(hs),
  el('div',{class:'card'},el('b',{},'Umgebungsprüfung'),...d.map(c=>el('div',{},el('span',{class:c.ok?'ok':'bad'},c.ok?'OK   ':'FEHL '),c.label,c.ok||!c.hint?null:el('span',{class:'mut'},'  → '+c.hint)))),fritzCard(f))}
function fritzCard(f){
 const cb=el('input',{type:'checkbox'});cb.checked=!!f.automation;
 const state=el('span',{class:'pill '+(f.automation?'warn':'mut')},'Automatik: '+(f.automation?'an':'aus'));
 const ready=el('span',{class:'pill '+(f.ready?'ok':'bad')},f.ready?'bereit':'nicht bereit');
 const resultBox=el('div',{});
 const recon=el('button',{class:'b p'},'Jetzt neu verbinden');
 recon.disabled=!f.ready;
 recon.addEventListener('click',()=>askInline(recon,'FRITZ!Box neu verbinden? Die Internetverbindung wird kurz getrennt; alle Geräte im Netz sind betroffen.','Ja, verbinden',async()=>{
  recon.disabled=true;resultBox.replaceChildren(el('div',{class:'mut'},'Reconnect läuft … (die FRITZ!Box prüft bis zu drei Minuten auf eine neue IP)'));
  try{const r=await api('/api/fritz',{action:'reconnect'});
   resultBox.replaceChildren(el('div',{class:'card '+(r.ok?'':'err')},el('b',{class:r.ok?'ok':'bad'},r.ok?'Reconnect erfolgreich':'Reconnect fehlgeschlagen'),
    el('pre',{style:'white-space:pre-wrap;margin:8px 0 0'},(r.result&&r.result.output)||r.message||'')))}catch(e){resultBox.replaceChildren(el('div',{class:'card err'},String(e&&e.message||e)))}finally{recon.disabled=!f.ready}}));
 return el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Fritzbox-Reconnect'),state,ready,recon),
  el('div',{class:'mut'},'Optionale Altintegration: Nach einem fehlgeschlagenen Agentenlauf kann eine neue Internet-IP angefordert werden (z. B. nach einem Anbieter-Limit). Ein Reconnect trennt die Internetverbindung der FRITZ!Box kurz; das betrifft alle Geräte im Netz. Die Automatik ist standardmäßig aus und greift nur nach einem Fehler, nie während eines laufenden Pakets.'),
  el('div',{class:'mut'},'Konfiguration: '+f.env+' (nicht im Repository)'+(f.configured?' – vorhanden':' – fehlt oder unvollständig')),
  el('div',{class:'mut'},'Helfer: '+f.script+(f.script_ok?'':' (fehlt)')+' · Python: '+(f.python||'nicht gefunden')+(f.python_ok?'':' (nicht ausführbar)')+' · Voraussetzung: fritzconnection im Python installiert'),
  el('div',{class:'bar'},el('label',{style:'margin:0'},el('span',{},' Automatik nach fehlgeschlagenem Agentenlauf '),cb),
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/fritz',{action:'automation',enabled:cb.checked});toast(r.message);if(r.ok)env().catch(showErr)}}},'Automatik übernehmen')),
  resultBox)}
window.addEventListener('unhandledrejection',e=>showErr(e.reason));
/* ---------- AP13: Anmeldung und Karte „Zugriffssicherheit“ ---------- */
/* AP13: Ohne Token prüft der Start die Berechtigung direkt am Server und
   zeigt andernfalls die Anmeldekarte. Ein Token aus dem #t=-Hash wird beim
   ersten Laden gegen einen Session-Cookie eingetauscht (POST /api/login),
   damit ein Neuladen ohne Hash angemeldet bleibt. Die Prüfung läuft bewusst
   über eine echte Anfrage statt über clientseitige Annahmen: Nur der Server
   kennt den wirklichen Berechtigungszustand. */
async function boot(){
 try{
  // Token → Session-Cookie tauschen; ohne Token bleibt der Aufruf weg.
  if(T)await api('/api/login',{token:T});
  await api('/api/projects');
  setTab('projects');
 }catch(e){showLogin()}}
function showLogin(){
 const inp=el('input',{type:'password',placeholder:'Kennwort oder Token','aria-label':'Kennwort oder Token'});
 const go=()=>doLogin(inp);
 const btn=el('button',{class:'b p',type:'button',on:{click:go}},'Anmelden');
 inp.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();go()}});
 main.replaceChildren(el('div',{class:'card',id:'login'},el('b',{},'Anmeldung'),
  el('div',{class:'mut'},'Diese Oberfläche ist geschützt. Bitte Kennwort oder Token eingeben.'),
  el('label',{},'Kennwort oder Token'),inp,el('div',{class:'bar'},btn)));
 inp.focus()}
async function doLogin(inp){
 const v=String(inp.value||'').trim();
 if(!v){inp.focus();return}
 // Der Wert wird als Token und als Kennwort angeboten; der Server prüft
 // zuerst das Token und fällt sonst auf das Kennwort zurück. So genügt eine
 // Eingabe für beide Anmeldearten, ohne dass die Oberfläche den Unterschied
 // raten muss. Kennwort und Token erscheinen in keiner Meldung.
 try{const r=await api('/api/login',{token:v,password:v});
  if(r.ok){toast(r.message||'Angemeldet.');setTab('projects')}
  else toast(r.message||'Anmeldung fehlgeschlagen.')}
 catch(e){toast('Anmeldung fehlgeschlagen: '+String(e&&e.message||e))}}
/* AP13: Karte „Zugriffssicherheit“. Sie zeigt den laufenden Zustand (Port,
   Bind-Adresse, Allowlist, Passwortstatus) und speichert Änderungen in
   ui.json; sie wirken erst nach einem Neustart des Dashboards, deshalb der
   dauerhafte Hinweis und die Zusatzwarnung, wenn gespeicherte Werte vom
   laufenden Server abweichen. Der Tab ist bewusst nicht Teil des
   periodischen Pollings: Nach jeder Aktion wird die Ansicht einmalig neu
   geladen. Die Ansicht enthält keine Kennwort- oder Hash-Auskunft. */
async function security(){
 let s=await api('/api/security');
 const fact=(k,v)=>el('div',{class:'factrow'},el('span',{class:'mut'},k),el('span',{},String(v)));
 const facts=el('div',{});
 const warn=el('div',{class:'warn',hidden:''},'Wirksame Änderung steht aus: Der gespeicherte Port oder die Bind-Adresse weicht vom laufenden Server ab. Damit die Änderung greift, das Dashboard neu starten („vibe ui“ beenden und erneut starten).');
 const portInp=el('input',{inputmode:'numeric',placeholder:'neuer Port (leer = unverändert)','aria-label':'Port'});
 const bindInp=el('input',{placeholder:'neue Bind-Adresse, z. B. 0.0.0.0 (leer = unverändert)','aria-label':'Bind-Adresse'});
 // „Leer = unverändert": Ein leeres Eingabefeld ändert die gespeicherte
 // Allowlist nicht; sie lässt sich nur über den Knopf „Alle Clients
 // zulassen" leeren.
 const allowInp=el('input',{placeholder:'IPs oder Netze, getrennt durch Leerzeichen oder Komma (leer = unverändert)','aria-label':'IP-Allowlist'});
 const passInp=el('input',{type:'password',placeholder:'neues Passwort (mind. 8 Zeichen)','aria-label':'Neues Passwort'});
 const draw=()=>{
  facts.replaceChildren(
   fact('Port',s.port),fact('Bind-Adresse',s.bind),
   fact('Allowlist',(s.allowlist&&s.allowlist.length)?s.allowlist.join(', '):'alle Clients erlaubt'),
   fact('Passwort',s.password_set?'gesetzt':'nicht gesetzt'));
  warn.hidden=!s.restart_required;
  removeBtn.hidden=!s.password_set};
 const refresh=async()=>{try{s=await api('/api/security')}catch(e){/* Ansicht bleibt beim letzten Stand */}draw()};
 const saveBtn=el('button',{class:'b p',type:'button',on:{click:async()=>{
  const port=portInp.value.trim();
  if(port&&!/^\d+$/.test(port)){toast('Bitte eine gültige Portnummer eingeben.');portInp.focus();return}
  const bind=bindInp.value.trim();
  const allow=allowInp.value.trim()?allowInp.value.split(/[\s,]+/).filter(Boolean):[];
  const pw=passInp.value;
  saveBtn.disabled=true;
  try{
   // Leere Felder werden nicht gesendet: Der Server ändert dann nichts.
   // So setzt ein reines Kennwort-Speichern weder Port noch Bind-Adresse
   // noch Allowlist nebenbei zurück.
   const update={action:'save'};
   if(port)update.port=Number(port);
   if(bind)update.bind=bind;
   if(allow.length)update.allowlist=allow;
   const r=await api('/api/security',update);toast(r.message||'');
   if(r.ok&&pw){const rp=await api('/api/security',{action:'password',password:pw});toast(rp.message||'')}
  }catch(e){toast('Speichern fehlgeschlagen: '+String(e&&e.message||e))}
  finally{saveBtn.disabled=false}
  portInp.value='';bindInp.value='';allowInp.value='';passInp.value='';
  await refresh()}}},'Speichern');
 const removeBtn=el('button',{class:'b',type:'button',on:{click:()=>askInline(removeBtn,'Passwort entfernen? Die Anmeldung mit Token bleibt möglich.','Ja, entfernen',async()=>{
  try{const r=await api('/api/security',{action:'password',clear:true});toast(r.message||'')}
  catch(e){toast('Entfernen fehlgeschlagen: '+String(e&&e.message||e))}
  await refresh()})}},'Passwort entfernen');
 const clearBtn=el('button',{class:'b',type:'button',on:{click:()=>askInline(clearBtn,'Allowlist entfernen? Danach dürfen alle Clients im Netz zugreifen; der lokale Rechner (Loopback) bleibt immer zugelassen.','Ja, zulassen',async()=>{
  try{const r=await api('/api/security',{action:'save',allowlist:[]});toast(r.message||'')}
  catch(e){toast('Zulassen fehlgeschlagen: '+String(e&&e.message||e))}
  await refresh()})}},'Alle Clients zulassen');
 draw();
 main.replaceChildren(el('div',{class:'card',id:'security'},el('b',{},'Zugriffssicherheit'),facts,
  el('div',{class:'mut'},'Änderungen an Port, Bind-Adresse und Allowlist werden in ui.json im Zustandsordner gespeichert und wirken erst nach einem Neustart des Dashboards. Ohne Allowlist sind alle Clients zugelassen; der lokale Rechner (Loopback) bleibt immer zugelassen.'),
  warn,
  el('label',{},'Port'),portInp,
  el('label',{},'Bind-Adresse'),bindInp,
  el('label',{},'IP-Allowlist'),allowInp,
  el('label',{},'Neues Passwort'),passInp,
  el('div',{class:'bar'},saveBtn,clearBtn,removeBtn)))}
boot();
