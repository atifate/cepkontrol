const {chromium}=require('./browser_runtime.cjs');
const {spawn}=require('node:child_process');
const {createInterface}=require('node:readline');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.MOBILE_TEST_HTTP||'http://127.0.0.1:18767';
const build=fs.realpathSync(path.resolve('build'));
const profile=fs.mkdtempSync(path.join(build,'phone-profile-'));
const children=[];let context;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn){for(let i=0;i<400;i++){if(fn())return;await sleep(30);}throw Error('Fixture timed out');}
async function launch(){const args=process.env.MOBILE_TEST_PUBLIC_IP?['--host-resolver-rules=MAP '+new URL(base).hostname+' '+process.env.MOBILE_TEST_PUBLIC_IP]:[];return chromium.launchPersistentContext(profile,{headless:true,args,executablePath:process.env.BROWSER_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1});}
(async()=>{
  if(!process.env.MOBILE_TEST_HTTP){
    const relay=spawn('python',['relay.py'],{env:{...process.env,PORT:'18767'},stdio:['ignore','ignore','pipe']});children.push(relay);
    for(let i=0;i<60;i++){try{if((await fetch(base)).ok)break;}catch{}await sleep(100);}
  }
  const events=[];let errors='';
  const host=spawn('python',['tests/trusted_host.py'],{env:{...process.env,MOBILE_TEST_WS:process.env.MOBILE_TEST_WS||base.replace(/^http/,'ws')},stdio:['pipe','pipe','pipe']});children.push(host);
  createInterface({input:host.stdout}).on('line',line=>{try{events.push(JSON.parse(line));}catch{}});
  host.stderr.on('data',data=>errors+=data);
  await until(()=>events.some(event=>event.type==='ready')).catch(error=>{throw Error(error.message+'; host stderr: '+errors);});
  const credential=events.find(event=>event.type==='ready').value;
  context=await launch();let page=await context.newPage();
  await page.goto(base);
  const manifest=await page.evaluate(async()=>await(await fetch('/manifest.webmanifest')).json());
  assert.equal(manifest.name,'CepKontrol');assert.equal(await page.title(),'CepKontrol · Telefondan kontrol');
  assert.equal(manifest.display,'standalone');assert.equal(manifest.start_url,'/?app=1');
  for(const icon of manifest.icons){const response=await page.request.get(base+icon.src);assert.equal(response.status(),200);assert(response.headers()['content-type'].startsWith('image/png'));}
  await page.waitForFunction(()=>!!navigator.serviceWorker.controller);
  await page.locator('#install-app').click();
  // The native install prompt isn't available in headless mode: verify the
  // manual installation help remains usable when the browser doesn't offer it.
  if(await page.locator('#install-help').isVisible())await page.locator('#close-install').click();
  await page.goto(base+'/#code='+credential.code+'&pairId='+credential.id+'&pairToken='+credential.token);
  await page.locator('#desktop').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.getElementById('screen').naturalWidth===1280);
  await until(()=>events.filter(event=>event.type==='video_ack').length>=3);
  const soakSeconds=Number(process.env.MOBILE_SOAK_SECONDS||0);
  if(soakSeconds){
    const accepted=events.filter(event=>event.type==='accepted').length;
    let frameLoads=0;await page.exposeFunction('observedFrame',()=>frameLoads++);
    await page.evaluate(()=>document.getElementById('screen').addEventListener('load',()=>window.observedFrame()));
    for(let elapsed=0;elapsed<soakSeconds;elapsed+=10){
      await sleep(Math.min(10,soakSeconds-elapsed)*1000);
      assert(await page.locator('#desktop').isVisible(),'Soak connection left the desktop');
      assert.equal(events.filter(event=>event.type==='accepted').length,accepted,'Soak unexpectedly reconnected: '+JSON.stringify(events.filter(event=>['accepted','ended','error'].includes(event.type))));
      if((elapsed+10)%60===0)console.log('SOAK '+(elapsed+10)+'s: '+frameLoads+' displayed frames, no reconnect');
    }
    assert(frameLoads>10,'Soak stopped displaying frames');
  }
  await page.evaluate(()=>{
    const key='acikdestek.phones.v1',saved=JSON.parse(localStorage.getItem(key));
    saved.push({id:'a'.repeat(32),token:'b'.repeat(64),code:'AD2.999999999.'+'A'.repeat(26),name:'Other computer'});
    localStorage.setItem(key,JSON.stringify(saved));
  });
  // Closing the browser process and reopening the same isolated profile checks
  // real persisted storage, rather than injecting a saved storage snapshot.
  await context.close();context=null;
  context=await launch();page=await context.newPage();
  await page.goto(base+manifest.start_url);
  await page.locator('#desktop').waitFor({state:'visible',timeout:20000});
  await page.waitForFunction(()=>document.getElementById('screen').naturalWidth===1280);
  assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('acikdestek.phones.v1'))[0].id),credential.id);
  assert.equal(events.filter(event=>event.type==='consent').length,0);
  await context.setOffline(true);
  await page.reload({waitUntil:'domcontentloaded'});
  await page.locator('#connect-panel').waitFor({state:'visible'});
  const cached=await page.evaluate(async()=>{const cache=await caches.open('acikdestek-shell-v3');return(await cache.keys()).map(request=>new URL(request.url).pathname);});
  assert(cached.includes('/mobile.js'));assert(cached.every(name=>['/','/mobile.js','/mobile.css','/manifest.webmanifest','/icon-180.png','/icon-192.png','/icon-512.png'].includes(name)));
  await context.setOffline(false);
  // The online event must reconnect without a page refresh or a button press.
  await page.locator('#desktop').waitFor({state:'visible',timeout:20000});
  // A PC unavailable beyond the former three-attempt limit must still recover.
  host.stdin.write('pause\n');await until(()=>events.some(event=>event.type==='paused'));
  await page.locator('#connect-panel').waitFor({state:'visible'});
  await sleep(14000);
  host.stdin.write('resume\n');await until(()=>events.some(event=>event.type==='resumed'));
  await page.locator('#desktop').waitFor({state:'visible',timeout:30000});
  await page.waitForFunction(()=>document.getElementById('screen').naturalWidth===1280);
  // User disconnect must suppress future online/foreground auto-reconnect.
  await page.locator('#disconnect').click();const accepted=events.filter(event=>event.type==='accepted').length;
  await page.evaluate(()=>{window.dispatchEvent(new Event('online'));document.dispatchEvent(new Event('visibilitychange'));});
  await sleep(3500);
  assert.equal(events.filter(event=>event.type==='accepted').length,accepted);
  assert.equal(events.filter(event=>event.type==='consent').length,0);assert.equal(errors,'');
  console.log('PWA OK: manifest, icons, service worker, browser restart, persisted pairing, automatic last-computer login, offline shell and recovery');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(context)await context.close();for(const child of children)child.kill();
  const resolved=fs.realpathSync(profile);
  if(!resolved.startsWith(build+path.sep)||!path.basename(resolved).startsWith('phone-profile-'))throw Error('Unexpected profile cleanup path');
  await fs.promises.rm(resolved,{recursive:true,force:true,maxRetries:5,retryDelay:200});
});
