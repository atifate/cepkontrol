'use strict';
const $ = id => document.getElementById(id);
const encoder = new TextEncoder(), decoder = new TextDecoder();
const aad = encoder.encode('AcikDestek/v1');
let current = null, generation = 0, pos = {x:.5,y:.5}, dragging = false, multi = false, lastMove = 0, scrollY = 0, scrollRemainder = 0;
let gesture = null, holdTimer = null;
let pointerMode = 'trackpad';
try{if(localStorage.getItem('acikdestek.pointerMode')==='direct')pointerMode='direct';}catch{}
let retryTimer = null;
let autoResume = true, installPrompt = null;
const storageKey = 'acikdestek.phones.v1';
const connectionGraceMs = 45000;
const codePattern = /^AD2\.([1-9][0-9]{8})\.([A-Z2-7]{26})$/;
function validCredential(value){return value&&/^[a-f0-9]{32}$/.test(value.id)&&/^[a-f0-9]{64}$/.test(value.token);}
function records(){try{const list=JSON.parse(localStorage.getItem(storageKey)||'[]');return Array.isArray(list)?list.filter(p=>validCredential(p)&&codePattern.test(p.code)).slice(0,5):[];}catch{return[];}}
function renderSaved(){
  const list=records();$('saved').hidden=!list.length;$('saved-list').replaceChildren();
  for(const phone of list){
    const row=document.createElement('div');row.className='saved-row';
    const connectButton=document.createElement('button');connectButton.type='button';connectButton.className='primary';connectButton.textContent=(phone.name||'Bilgisayarım')+' · Bağlan';connectButton.addEventListener('click',()=>connect(phone.code,phone));
    const forget=document.createElement('button');forget.type='button';forget.textContent='Unut';forget.title='Kaydı bu tarayıcıdan sil';forget.addEventListener('click',()=>{try{localStorage.setItem(storageKey,JSON.stringify(records().filter(p=>p.id!==phone.id)));autoResume=false;release();stop('Telefon kaydı silindi. Yeniden eşleştirmek için bilgisayardaki QR kodunu kullan.');}catch{status('Telefon tarayıcısı kaydı değiştiremiyor.',true);}});
    row.append(connectButton,forget);$('saved-list').append(row);
  }
}
function remember(phone){
  try{localStorage.setItem(storageKey,JSON.stringify([phone,...records().filter(p=>p.id!==phone.id)].slice(0,5)));renderSaved();navigator.storage?.persist?.().catch(()=>{});return true;}catch{return false;}
}
function standalone(){return matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;}
function installButtons(){for(const id of ['install-app','install-live'])$(id).hidden=standalone();}
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;installButtons();});
window.addEventListener('appinstalled',()=>{installPrompt=null;for(const id of ['install-app','install-live'])$(id).hidden=true;});
async function install(){
  if(installPrompt){const prompt=installPrompt;installPrompt=null;await prompt.prompt();await prompt.userChoice;return;}
  $('install-instructions').textContent=/iPhone|iPad/.test(navigator.userAgent)?'Safari’de Paylaş düğmesine, ardından “Ana Ekrana Ekle” seçeneğine dokun.':'Chrome’un ⋮ menüsünden “Uygulamayı yükle” veya “Ana ekrana ekle” seçeneğini kullan.';
  $('install-help').showModal();
}
$('install-app').addEventListener('click',install);$('install-live').addEventListener('click',install);
$('close-install').addEventListener('click',()=>$('install-help').close());installButtons();
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
function hexBytes(text){return Uint8Array.from(text.match(/../g),v=>parseInt(v,16));}
function hex(bytes){return [...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,'0')).join('');}
const fingers = new Map();
function status(text, error=false) { $('status').textContent=text; $('status').classList.toggle('error',error); }
function cancelHold(){clearTimeout(holdTimer);holdTimer=null;}
function clearControls(){cancelHold();gesture=null;fingers.clear();dragging=false;multi=false;scrollRemainder=0;$('cursor').classList.remove('dragging');$('ctrl').setAttribute('aria-pressed','false');}
function stop(message='Bağlantı kapatıldı. Kayıtlı bilgisayarına tekrar bağlanabilirsin.') {
  generation++;
  clearTimeout(retryTimer);retryTimer=null;
  const ctx=current; current=null;
  if(ctx){clearInterval(ctx.heartbeat);clearTimeout(ctx.deadline);ctx.ws.close(1000,'Client stopped');}
  clearControls(); $('desktop').hidden=true; $('connect-panel').hidden=false; $('typing').hidden=true;
  $('screen').removeAttribute('src');$('cursor').hidden=true;$('waiting').hidden=false;
  $('connect').disabled=false;$('cancel').hidden=true;renderSaved();status(message);
}
function send(ctx, message) {
  const encryptionKey=ctx.key;
  ctx.tx=ctx.tx.then(async()=>{
    if(current!==ctx||ctx.ws.readyState!==WebSocket.OPEN)return;
    const iv=crypto.getRandomValues(new Uint8Array(12));
    const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad,tagLength:128},encryptionKey,encoder.encode(JSON.stringify(message)));
    if(current!==ctx||ctx.ws.readyState!==WebSocket.OPEN)return;
    const out=new Uint8Array(12+ciphertext.byteLength);out.set(iv);out.set(new Uint8Array(ciphertext),12);ctx.ws.send(out);
  }).catch(()=>{if(current===ctx)connectionLost(ctx);});
  return ctx.tx;
}
function input(event) {
  const ctx=current;if(!ctx?.session)return;
  if(ctx.ws.bufferedAmount>262144&&['move','heartbeat'].includes(event.kind))return;
  send(ctx,{type:'input',session:ctx.session,seq:++ctx.seq,event});
}
function release(){input({kind:'release'});clearControls();}
function key(name){input({kind:'keydown',key:name});input({kind:'keyup',key:name});}
function connectionLost(ctx){
  if(current!==ctx)return;
  const resume=autoResume&&ctx.credential;
  stop(resume?'Bilgisayar bekleniyor… Hazır olduğunda otomatik bağlanacak.':'Bağlantı kesildi. Tekrar bağlanabilirsin.');
  if(!resume)return;
  $('cancel').hidden=false;
  if(!navigator.onLine){status('İnternet bekleniyor… Bağlantı gelince otomatik devam edecek.');return;}
  if(document.hidden)return;
  const delay=Math.min(15000,1500*2**Math.min(ctx.retry,4));
  retryTimer=setTimeout(()=>{retryTimer=null;if(autoResume&&!document.hidden)connect(ctx.code,ctx.credential,ctx.retry+1);},delay);
}
async function connect(code, credential=null, retry=0){
  autoResume=true;
  if(!crypto.subtle){status('Güvenli bağlantı gerekiyor. Bu sayfayı HTTPS adresinden aç.',true);return;}
  const match=codePattern.exec(code.trim());
  if(!match){status('Bilgisayardaki bağlantı kodunu eksiksiz yapıştır.',true);return;}
  credential=credential||records().find(p=>p.code===code.trim())||null;
  if(credential&&!validCredential(credential)){status('Telefon eşleştirme bağlantısı geçersiz.',true);return;}
  clearTimeout(retryTimer);retryTimer=null;
  if(current)stop();const attempt=++generation;$('connect').disabled=true;$('cancel').hidden=false;status('Bilgisayara bağlanılıyor…');
  try{
    const digest=await crypto.subtle.digest('SHA-256',encoder.encode('AcikDestek/v2/'+match[2]));
    const aes=await crypto.subtle.importKey('raw',digest,'AES-GCM',false,['encrypt','decrypt']);
    if(attempt!==generation)return;
    const ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/viewer/'+match[1]);
    ws.binaryType='arraybuffer';
    const ctx=current={ws,key:aes,session:null,seq:0,tx:Promise.resolve(),rx:Promise.resolve(),heartbeat:null,deadline:null,credential,code:code.trim(),room:match[1],retry,lastReceived:Date.now()};
    ctx.deadline=setTimeout(()=>{if(current===ctx){if(ctx.credential)connectionLost(ctx);else stop('Onay süresi doldu. Bilgisayardan yeni kod oluştur.');}},credential?20000:60000);
    ws.onmessage=event=>{
      ctx.rx=ctx.rx.then(async()=>{
        if(current!==ctx)return;
        ctx.lastReceived=Date.now();
        if(typeof event.data==='string'){
          if(JSON.parse(event.data).relay==='ready'){
            status(credential?'Kayıtlı telefon doğrulanıyor…':'Bilgisayarda “Bağlantıya izin ver” düğmesine bas.');
            send(ctx,{type:'hello',name:'Telefon · '+(/iPhone|iPad/.test(navigator.userAgent)?'Safari / iOS':'Mobil tarayıcı'),phone_id:credential?.id,frame_ack:true});
          }return;
        }
        const bytes=new Uint8Array(event.data);if(bytes.length<28)return;
        let msg;
        try{const clear=await crypto.subtle.decrypt({name:'AES-GCM',iv:bytes.slice(0,12),additionalData:aad,tagLength:128},ctx.key,bytes.slice(12));msg=JSON.parse(decoder.decode(clear));}catch{return;}
        if(current!==ctx)return;
        if(msg.type==='phone_challenge'&&credential&&/^[a-f0-9]{64}$/.test(msg.challenge)){
          const hmac=await crypto.subtle.importKey('raw',hexBytes(credential.token),{name:'HMAC',hash:'SHA-256'},false,['sign']);
          const context=msg.challenge+'\0'+ctx.room+'\0'+credential.id;
          const proof=await crypto.subtle.sign('HMAC',hmac,encoder.encode('AcikDestek/pair/v1\0'+context));
          const nextKey=await crypto.subtle.sign('HMAC',hmac,encoder.encode('AcikDestek/session/v1\0'+context));
          await send(ctx,{type:'phone_proof',proof:hex(proof)});
          if(current===ctx)ctx.key=await crypto.subtle.importKey('raw',nextKey,'AES-GCM',false,['encrypt','decrypt']);
        }else if(msg.type==='accepted'&&!ctx.session){
          ctx.session=msg.session;ctx.retry=0;clearTimeout(ctx.deadline);$('connect-panel').hidden=true;$('desktop').hidden=false;
          pos={x:.5,y:.5};$('live-status').textContent='● Tek oturum · Telefon kaydedilmedi';
          if(validCredential(msg.pairing)&&credential&&msg.pairing.id===credential.id){
            ctx.credential={id:msg.pairing.id,token:msg.pairing.token,code:ctx.code,name:String(msg.pairing.name||'Bilgisayarım').slice(0,64)};
            $('live-status').textContent=remember(ctx.credential)?'● Telefon eşleşti':'Telefon kaydı saklanamadı';
          }
          $('code').value='';
          ctx.heartbeat=setInterval(()=>{if(!document.hidden){if(Date.now()-ctx.lastReceived>connectionGraceMs)connectionLost(ctx);else input({kind:'heartbeat'});}},1000);
        }else if(msg.type==='rejected'){autoResume=false;stop(credential?'Telefon eşleşmesi geçersiz veya kaldırılmış. Bilgisayardan yeni QR ile eşleştir.':'Bilgisayar bağlantıyı reddetti.');}
        else if(msg.type==='frame'&&ctx.session&&msg.session===ctx.session&&typeof msg.jpeg==='string'&&msg.jpeg.length<4194304){
          let acknowledged=false;
          $('screen').onload=()=>{if(current===ctx&&!acknowledged&&Number.isSafeInteger(msg.frame_id)){acknowledged=true;send(ctx,{type:'frame_ack',session:ctx.session,frame_id:msg.frame_id});}};
          $('screen').src='data:image/jpeg;base64,'+msg.jpeg;$('waiting').hidden=true;
        }
      }).catch(()=>{if(current===ctx)connectionLost(ctx);});
    };
    ws.onclose=()=>{
      connectionLost(ctx);
    };
    ws.onerror=()=>{if(current===ctx)status('Bağlantı bekleniyor…');};
  }catch{if(attempt===generation)stop('Bağlantı başlatılamadı. Güncel Chrome veya Safari ile tekrar dene.');}
}
$('connect-form').addEventListener('submit',e=>{e.preventDefault();if(!current)connect($('code').value);});
$('disconnect').addEventListener('click',()=>{autoResume=false;release();stop();});
$('cancel').addEventListener('click',()=>{autoResume=false;stop('Bağlantı isteği iptal edildi.');});
$('fullscreen').addEventListener('click',async()=>{
  try{if(document.fullscreenElement)await document.exitFullscreen();else if($('desktop').requestFullscreen)await $('desktop').requestFullscreen();else $('live-status').textContent='Daha büyük ekran için telefonu yatay çevir';}catch{$('live-status').textContent='Telefonu yatay çevir';}
});
const clamp=value=>Math.max(.002,Math.min(.998,value));
function coordinates(e){const r=$('screen').getBoundingClientRect();if(!r.width||!r.height)return null;return{x:clamp((e.clientX-r.left)/r.width),y:clamp((e.clientY-r.top)/r.height)};}
function point(p){pos=p;const image=$('screen').getBoundingClientRect(),stage=$('stage').getBoundingClientRect();if(!image.width||!image.height)return;$('cursor').style.left=(image.left-stage.left+p.x*image.width)+'px';$('cursor').style.top=(image.top-stage.top+p.y*image.height)+'px';$('cursor').hidden=false;}
function renderPointerMode(){
  $('pointer-mode').textContent=pointerMode==='trackpad'?'İmleç: Dokunmatik yüzey':'İmleç: Doğrudan dokun';
  $('pointer-mode').setAttribute('aria-pressed',String(pointerMode==='trackpad'));
  $('gesture-hint').textContent=pointerMode==='trackpad'?'Herhangi bir yerden kaydır: imleci taşı · Dokun: tıkla · Uzun bas ve taşı: sürükle · İki parmak: kaydır':'Dokun: tıkla · Basılı tutup taşı: sürükle · İki parmak: kaydır';
}
$('pointer-mode').addEventListener('click',()=>{release();pointerMode=pointerMode==='trackpad'?'direct':'trackpad';try{localStorage.setItem('acikdestek.pointerMode',pointerMode);}catch{}renderPointerMode();});
renderPointerMode();
$('screen').addEventListener('load',()=>{if(current?.session)point(pos);});
new ResizeObserver(()=>{if(current?.session)point(pos);}).observe($('screen'));
$('stage').addEventListener('pointerdown',e=>{
  if(!current?.session||!$('screen').naturalWidth)return;
  if(pointerMode==='direct'&&e.target!==$('screen'))return;
  e.preventDefault();$('stage').setPointerCapture(e.pointerId);fingers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(fingers.size>1){cancelHold();input({kind:'release'});dragging=false;$('cursor').classList.remove('dragging');gesture=null;multi=true;scrollY=[...fingers.values()].reduce((a,p)=>a+p.y,0)/fingers.size;return;}
  if(multi)return;
  gesture={id:e.pointerId,x:e.clientX,y:e.clientY,started:performance.now(),moved:false,relative:pointerMode==='trackpad',button:e.button===2?'right':'left'};
  lastMove=0;
  if(!gesture.relative){const p=coordinates(e);if(p){point(p);input({kind:'down',...p,button:gesture.button});dragging=true;}}
  else{
    const active=gesture;
    holdTimer=setTimeout(()=>{holdTimer=null;if(gesture===active&&!active.moved&&!multi&&current?.session){input({kind:'down',...pos,button:active.button});dragging=true;$('cursor').classList.add('dragging');}},450);
  }
});
function movePointer(e,force=false){
  const previous=fingers.get(e.pointerId);if(!previous)return;
  fingers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if(!gesture||multi)return;
  const active=gesture;
  if(Math.hypot(e.clientX-active.x,e.clientY-active.y)>6){active.moved=true;cancelHold();}
  if(active.relative){
    const r=$('screen').getBoundingClientRect();
    // Ignore a tap's small finger wobble, then account for the whole initial
    // displacement. Lifting and touching elsewhere never repositions the cursor.
    if((active.moved||dragging)&&r.width&&r.height){
      const origin=active.moving?previous:active;
      point({x:clamp(pos.x+(e.clientX-origin.x)/r.width),y:clamp(pos.y+(e.clientY-origin.y)/r.height)});
      active.moving=true;
    }
  }else{const p=coordinates(e);if(p)point(p);}
  const now=performance.now();
  if((active.moved||dragging)&&(force||now-lastMove>30)){lastMove=now;input({kind:'move',...pos});}
}
$('stage').addEventListener('pointermove',e=>{
  if(!fingers.has(e.pointerId))return;e.preventDefault();
  if(fingers.size>1){fingers.set(e.pointerId,{x:e.clientX,y:e.clientY});const center=[...fingers.values()].reduce((a,p)=>a+p.y,0)/fingers.size;scrollRemainder+=(center-scrollY);scrollY=center;const steps=Math.trunc(scrollRemainder/25);if(steps){input({kind:'scroll',steps:Math.max(-5,Math.min(5,steps))});scrollRemainder-=steps*25;}return;}
  movePointer(e);
});
function pointerEnd(e){
  if(!fingers.has(e.pointerId))return;e.preventDefault();cancelHold();
  const completed=e.type==='pointerup';
  if(completed)movePointer(e,true);
  if(dragging){input({kind:'up',...pos,button:gesture?.button||'left'});dragging=false;}
  else if(completed&&gesture?.relative&&!gesture.moved&&!multi&&performance.now()-gesture.started<450){input({kind:'down',...pos,button:gesture.button});input({kind:'up',...pos,button:gesture.button});}
  fingers.delete(e.pointerId);gesture=null;$('cursor').classList.remove('dragging');
  if(!fingers.size){multi=false;scrollRemainder=0;}
}
for(const event of ['pointerup','pointercancel','lostpointercapture'])$('stage').addEventListener(event,pointerEnd);
$('stage').addEventListener('contextmenu',e=>e.preventDefault());
$('right-click').addEventListener('click',()=>{input({kind:'down',...pos,button:'right'});input({kind:'up',...pos,button:'right'});});
for(const button of document.querySelectorAll('[data-key]'))button.addEventListener('click',()=>key(button.dataset.key));
$('ctrl').addEventListener('click',()=>{const down=$('ctrl').getAttribute('aria-pressed')!=='true';input({kind:down?'keydown':'keyup',key:'ctrlleft'});$('ctrl').setAttribute('aria-pressed',String(down));});
$('scroll-up').addEventListener('click',()=>input({kind:'scroll',steps:3}));$('scroll-down').addEventListener('click',()=>input({kind:'scroll',steps:-3}));
$('keyboard-toggle').addEventListener('click',()=>{release();$('typing').hidden=!$('typing').hidden;if(!$('typing').hidden)$('text').focus();});
$('typing').addEventListener('submit',e=>{
  e.preventDefault();const value=$('text').value;if(value.length>8000){$('live-status').textContent='En fazla 8000 karakter gönder';return;}
  let chunk='';const flush=()=>{if(chunk){input({kind:'text',text:chunk});chunk='';}};
  for(const char of value){if(char==='\n'||char==='\t'){flush();key(char==='\n'?'enter':'tab');}else if(char>=' '){chunk+=char;if([...chunk].length>=8)flush();}}flush();$('text').value='';
});
function openSaved(){
  if(!autoResume||document.hidden)return;
  if(current&&current.ws.readyState<WebSocket.CLOSING){
    if(current.session&&Date.now()-current.lastReceived>connectionGraceMs)connectionLost(current);
    return;
  }
  const saved=records();if(saved.length)connect(saved[0].code,saved[0]);
}
document.addEventListener('visibilitychange',()=>{if(document.hidden){release();clearTimeout(retryTimer);retryTimer=null;}else openSaved();});
window.addEventListener('online',openSaved);
window.addEventListener('pageshow',event=>{if(event.persisted)openSaved();});
window.addEventListener('blur',release);window.addEventListener('pagehide',()=>{release();if(current)current.ws.close(1000,'Page closed');});
function consumeInvitation(){
  const params=new URLSearchParams(location.hash.slice(1)),invitation=params.get('code');
  if(invitation){let credential=params.has('pairId')?{id:params.get('pairId'),token:params.get('pairToken')}:null;if(credential)credential=records().find(p=>p.id===credential.id&&p.code===invitation)||credential;$('code').value=invitation;history.replaceState(null,'',location.pathname);connect(invitation,credential);return true;}
  return false;
}
window.addEventListener('hashchange',consumeInvitation);renderSaved();
if(!consumeInvitation())openSaved();
