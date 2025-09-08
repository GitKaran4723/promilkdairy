if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/static/service-worker.js').then(function(reg){
      // console.log('SW registered');
    }).catch(function(err){
      // console.warn('SW failed', err);
    });
  });
}
