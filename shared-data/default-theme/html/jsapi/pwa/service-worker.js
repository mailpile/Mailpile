// Placeholder logic, copied from here: 
// https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers

{# Magic #}
{% do http_response_headers.append(('Service-Worker-Allowed', U("/"))) %}

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open('v1').then(function(cache) {
      return cache.addAll([
        '{{ U("/static/img/logo.svg") }}',
      ]);
    })
  );
});

//self.addEventListener('fetch', function(event) {
//  event.respondWith(caches.match(event.request).then(function(response) {
//    // caches.match() always resolves
//    // but in case of success response will have value
//    if (response !== undefined) {
//      return response;
//    } else {
//      return fetch(event.request).then(function (response) {
//        // response may be used only once
//        // we need to save clone to put one copy in cache
//        // and serve second one
//        let responseClone = response.clone();
//        caches.open('v1').then(function (cache) {
//          cache.put(event.request, responseClone);
//        });
//        return response;
//// Disabled fallback, for now.
////    }).catch(function () {
////      return caches.match('/sw-test/gallery/myLittleVader.jpg');
//      });
//    }
//  }));
//});

console.log('Service worker loaded, hooray!');
