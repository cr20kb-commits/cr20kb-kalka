importScripts('./precache.js');
const CACHE='cr20kb-kalka-web-0.1.0';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(self.KALKA_ASSETS))));
self.addEventListener('activate',event=>event.waitUntil((async()=>{for(const name of await caches.keys())if(name.startsWith('cr20kb-kalka-web-')&&name!==CACHE)await caches.delete(name);await self.clients.claim()})()));
self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(event.request.method!=='GET'||url.origin!==self.location.origin||!url.pathname.startsWith(new URL(self.registration.scope).pathname))return;event.respondWith(caches.open(CACHE).then(async cache=>(await cache.match(event.request,{ignoreSearch:true}))||(event.request.mode==='navigate'&&url.pathname===new URL(self.registration.scope).pathname?await cache.match('./index.html'):null)||fetch(event.request)));});
self.addEventListener('message',event=>{if(event.data==='ready')event.waitUntil((async()=>{const cache=await caches.open(CACHE);for(const asset of self.KALKA_ASSETS)if(!await cache.match(asset)){event.ports[0]?.postMessage({ready:false});return}event.ports[0]?.postMessage({ready:true})})());});
