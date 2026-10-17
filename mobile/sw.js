'use strict';
// Only the application shell is cached. Credentials stay in the page's local
// storage; screen frames and control messages use WebSocket, never this cache.
const CACHE='acikdestek-shell-v3';
const ASSETS=['/','/mobile.js','/mobile.css','/manifest.webmanifest','/icon-180.png','/icon-192.png','/icon-512.png'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('acikdestek-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
  const url=new URL(event.request.url);
  if(event.request.method!=='GET'||url.origin!==self.location.origin||!ASSETS.includes(url.pathname))return;
  event.respondWith((async()=>{
    const cache=await caches.open(CACHE);
    try{
      const response=await fetch(event.request,{cache:'no-store'});
      if(response.ok){await cache.put(url.pathname,response.clone());return response;}
      return await cache.match(url.pathname)||response;
    }catch{return await cache.match(url.pathname)||Response.error();}
  })());
});
