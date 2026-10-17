const {chromium}=require('./browser_runtime.cjs');
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.MOBILE_TEST_HTTP || 'http://127.0.0.1:18766';
const ws = base.replace(/^http/,'ws');
const children=[]; let browser;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,timeout=12000){const end=Date.now()+timeout;while(Date.now()<end){if(fn())return;await sleep(30);}throw Error('Timed out waiting for fixture');}
(async()=>{
  if(!process.env.MOBILE_TEST_HTTP){
    const relay=spawn('python',['relay.py'],{env:{...process.env,PORT:'18766'},stdio:['ignore','ignore','pipe']});children.push(relay);
    for(let i=0;i<60;i++){try{if((await fetch(base)).ok)break;}catch{}await sleep(100);}
  }
  const events=[];
  const trusted=process.env.MOBILE_TRUSTED==='1';
  const host=spawn('python',[trusted?'tests/trusted_host.py':'tests/mobile_host.py'],{env:{...process.env,MOBILE_TEST_WS:ws},stdio:['pipe','pipe','pipe']});children.push(host);
  const lines=createInterface({input:host.stdout});lines.on('line',line=>{try{events.push(JSON.parse(line));}catch{}});
  let errors='';host.stderr.on('data',d=>errors+=d);
  await until(()=>events.some(e=>e.type==='ready')).catch(error=>{throw Error(error.message+'; host stderr: '+errors);});
  const ready=events.find(e=>e.type==='ready').value;
  const code=trusted?ready.code:ready;
  browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1});
  const page=await context.newPage();const pageErrors=[];page.on('pageerror',e=>pageErrors.push(e.message));
  await page.goto(base);
  await page.locator('#code').fill('wrong');await page.locator('#connect').click();
  await page.locator('#status.error').waitFor();
  await page.screenshot({path:'build/mobile-connect.png',fullPage:true});
  // Test QR invitation fragments, including removal of the secret from the URL.
  await page.goto(base+'/#code='+code+(trusted?'&pairId='+ready.id+'&pairToken='+ready.token:''));
  await page.locator('#desktop').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.getElementById('screen').naturalWidth===1280);
  assert.match(await page.locator('#live-status').innerText(),trusted?/Telefon eşleşti/:/Tek oturum/);
  assert.equal(new URL(page.url()).hash,'');
  const bounds=await page.locator('#screen').boundingBox();assert(bounds.width>300&&bounds.height>100);
  const x=bounds.x+bounds.width*.45,y=bounds.y+bounds.height*.55;
  // The default trackpad must click at the cursor, not at the touching finger.
  await page.touchscreen.tap(x,y);
  await until(()=>events.some(e=>e.type==='input'&&e.value.kind==='up'));
  const down=events.find(e=>e.type==='input'&&e.value.kind==='down').value;
  assert(Math.abs(down.x-.5)<.02&&Math.abs(down.y-.5)<.02);
  const cdp=await context.newCDPSession(page);
  const touch=(id,px,py)=>({id,x:px,y:py,radiusX:2,radiusY:2,force:1});
  let from=events.length;
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[touch(1,x,y)]});
  await sleep(60);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[touch(1,x+20,y+15)]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await until(()=>events.slice(from).some(e=>e.type==='input'&&e.value.kind==='move'));
  await sleep(100);
  let inputs=events.slice(from).filter(e=>e.type==='input').map(e=>e.value);
  assert(!inputs.some(e=>['down','up'].includes(e.kind)),'Moving the cursor must not press a mouse button');
  const moved=inputs.filter(e=>e.kind==='move').at(-1);
  assert(Math.abs(moved.x-(.5+20/bounds.width))<.015&&Math.abs(moved.y-(.5+15/bounds.height))<.015);
  // Reposition the finger far away, in the letterbox margin. Movement must
  // continue from the cursor's last position, without a jump to the finger.
  const stage=await page.locator('#stage').boundingBox();const marginY=stage.y+20;
  assert(marginY<bounds.y);
  from=events.length;
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[touch(1,60,marginY)]});
  await sleep(60);
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[touch(1,75,marginY+10)]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await until(()=>events.slice(from).some(e=>e.type==='input'&&e.value.kind==='move'));
  await sleep(100);
  inputs=events.slice(from).filter(e=>e.type==='input').map(e=>e.value);
  const continued=inputs.filter(e=>e.kind==='move').at(-1);
  assert(Math.abs(continued.x-(moved.x+15/bounds.width))<.015&&Math.abs(continued.y-(moved.y+10/bounds.height))<.015);
  assert(!inputs.some(e=>['down','up'].includes(e.kind)));
  // Long hold then move drags at the cursor; release cannot leave a held button.
  from=events.length;
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[touch(1,80,marginY)]});
  await until(()=>events.slice(from).some(e=>e.type==='input'&&e.value.kind==='down'));
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[touch(1,100,marginY+10)]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await until(()=>events.slice(from).some(e=>e.type==='input'&&e.value.kind==='up'));
  // A cancelled short touch must never become a click.
  from=events.length;
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[touch(1,x,y)]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchCancel',touchPoints:[]});
  await sleep(550);
  assert(!events.slice(from).some(e=>e.type==='input'&&['down','up'].includes(e.value.kind)));
  from=events.length;
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[touch(1,x-30,y),touch(2,x+30,y)]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[touch(1,x-30,y+40),touch(2,x+30,y+40)]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await until(()=>events.slice(from).some(e=>e.type==='input'&&e.value.kind==='scroll'));
  assert(!events.slice(from).some(e=>e.type==='input'&&e.value.kind==='down'),'Two fingers must not click');
  // Keep direct touch as a saved user preference.
  await page.locator('#pointer-mode').click();from=events.length;
  const directBounds=await page.locator('#screen').boundingBox();
  await page.touchscreen.tap(directBounds.x+directBounds.width*.45,directBounds.y+directBounds.height*.55);
  await until(()=>events.slice(from).some(e=>e.type==='input'&&e.value.kind==='up'));
  const direct=events.slice(from).find(e=>e.type==='input'&&e.value.kind==='down').value;
  assert(Math.abs(direct.x-.45)<.02&&Math.abs(direct.y-.55)<.02);
  assert.equal(await page.evaluate(()=>localStorage.getItem('acikdestek.pointerMode')),'direct');
  await page.locator('#pointer-mode').click();
  await page.locator('#right-click').click();
  await page.locator('#keyboard-toggle').click();
  await page.locator('#text').fill('Türkçe ğüşİ\n');await page.locator('#typing button').click();
  await until(()=>events.some(e=>e.type==='input'&&e.value.kind==='keydown'&&e.value.key==='enter'));
  const text=events.filter(e=>e.type==='input'&&e.value.kind==='text').map(e=>e.value.text).join('');
  assert.equal(text,'Türkçe ğüşİ');
  await page.locator('#keyboard-toggle').click();
  await page.screenshot({path:'build/mobile-desktop.png',fullPage:true});
  await page.setViewportSize({width:844,height:390});
  await page.screenshot({path:'build/mobile-landscape.png',fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('#disconnect').click();
  await page.locator('#connect-panel').waitFor({state:'visible'});
  if(trusted){
    const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('acikdestek.phones.v1')));
    assert.equal(saved.length,1);assert.equal(saved[0].id,ready.id);assert.notEqual(saved[0].token,ready.token);
    assert.equal(events.filter(e=>e.type==='consent').length,0);
    // Restart the Windows UI using its encrypted credential file, then open the
    // phone page with no code or QR. It must authenticate without local consent.
    host.stdin.write('restart\n');await until(()=>events.some(e=>e.type==='restarted'));
    await page.goto(base);
    await page.locator('#desktop').waitFor({state:'visible',timeout:20000});
    await page.waitForFunction(()=>document.getElementById('screen').naturalWidth===1280);
    assert.equal(events.filter(e=>e.type==='consent').length,0);
    host.stdin.write('revoke\n');await until(()=>events.some(e=>e.type==='revoked'));
    await page.locator('#connect-panel').waitFor({state:'visible'});
    const count=events.filter(e=>e.type==='accepted').length;
    await sleep(2500);assert.equal(events.filter(e=>e.type==='accepted').length,count);
    assert.equal(events.filter(e=>e.type==='unexpected_consent').length,0);
  }
  assert.deepEqual(pageErrors,[]);assert.equal(errors,'');
  console.log('MOBILE OK: encryption, QR, relative cursor, repositioned finger, margin touchpad, tap, long-press drag, cancel, two-finger scroll, direct mode, right click, Turkish text, portrait/landscape, reconnect');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();for(const child of children)child.kill();});
