// IAS Machine — Offline Manager
const DB_NAME = 'ias-offline-meta';
const STORE = 'books';

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'url' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function dbPut(entry) {
  const db = await openDB();
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(entry);
    tx.oncomplete = res;
    tx.onerror = () => rej(tx.error);
  });
}

async function dbGetAll() {
  const db = await openDB();
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => res(req.result || []);
    req.onerror = () => rej(req.error);
  });
}

async function dbDelete(url) {
  const db = await openDB();
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(url);
    tx.oncomplete = res;
    tx.onerror = () => rej(tx.error);
  });
}

async function dbClear() {
  const db = await openDB();
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).clear();
    tx.oncomplete = res;
    tx.onerror = () => rej(tx.error);
  });
}

async function saveBookOffline(bookId, title) {
  const url = '/read/' + bookId;
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error('Fetch failed');
    const blob = await r.blob();
    const cache = await caches.open('ias-books-v4');
    await cache.put(url, new Response(blob, { headers: { 'Content-Type': 'application/pdf' } }));
    await dbPut({
      url: url,
      bookId: bookId,
      title: title || ('Book #' + bookId),
      size: blob.size,
      savedAt: Date.now()
    });
    return { ok: true, size: blob.size };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function removeBookOffline(bookId) {
  const url = '/read/' + bookId;
  const cache = await caches.open('ias-books-v4');
  await cache.delete(url);
  await dbDelete(url);
  return { ok: true };
}

async function clearAllBooks() {
  await caches.delete('ias-books-v4');
  await dbClear();
  return { ok: true };
}

async function getStorageEstimate() {
  if (navigator.storage && navigator.storage.estimate) {
    const est = await navigator.storage.estimate();
    return {
      usage: est.usage || 0,
      quota: est.quota || 0,
      usageMB: Math.round((est.usage || 0) / 1024 / 1024 * 10) / 10,
      quotaMB: Math.round((est.quota || 0) / 1024 / 1024),
      percent: Math.round((est.usage / est.quota) * 100 * 10) / 10
    };
  }
  return { usage: 0, quota: 0, usageMB: 0, quotaMB: 0, percent: 0 };
}

async function listOfflineBooks() {
  const items = await dbGetAll();
  return items.sort((a, b) => (b.savedAt || 0) - (a.savedAt || 0));
}

window.IASOffline = {
  saveBookOffline, removeBookOffline, clearAllBooks,
  listOfflineBooks, getStorageEstimate
};

/* ============ PATCH 19B: Real streaming save with progress ============ */
(function(){
  const CACHE_NAME = 'ias-books-v4';

  async function streamSave(bookId, title, onProgress) {
    const url = '/book/' + bookId + '/stream';
    const cache = await caches.open(CACHE_NAME);

    // HEAD to get size first (fetch with Range just for headers)
    let total = 0;
    try {
      const head = await fetch(url, { method: 'HEAD' });
      total = parseInt(head.headers.get('Content-Length') || '0', 10);
    } catch(e){}

    if (total > 120 * 1024 * 1024) {
      throw new Error('Too big (' + Math.round(total/1024/1024) + ' MB). Use laptop.');
    }

    const r = await fetch(url);
    if (!r.ok) throw new Error('HTTP ' + r.status);

    if (!r.body || !r.body.getReader) {
      // Fallback: no stream support — but we can still cache.put
      await cache.put(url, r.clone());
      const blob = await r.blob();
      return { size: blob.size, total: blob.size };
    }

    const reader = r.body.getReader();
    const chunks = [];
    let received = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.length;
      if (onProgress) onProgress(received, total);
    }

    const blob = new Blob(chunks, { type: 'application/pdf' });
    await cache.put(url, new Response(blob, {
      headers: { 'Content-Type': 'application/pdf', 'Content-Length': String(blob.size) }
    }));

    // Also cache the reader HTML page so /reader/<id> works offline
    try {
      const readerUrl = '/reader/' + bookId;
      const rr = await fetch(readerUrl, {credentials:'same-origin'});
      if (rr.ok) {
        const pc = await caches.open('ias-pages-ias-v6');
        await pc.put(new Request(readerUrl, {credentials:'same-origin'}), rr.clone());
      }
    } catch(e){ console.warn('reader cache:', e); }

    return { size: blob.size, total: total || blob.size };
  }

  async function saveWithMeta(bookId, title, onProgress) {
    const info = await streamSave(bookId, title, onProgress);
    // Metadata into IndexedDB (existing dbSave function)
    try {
      if (typeof dbPut === 'function') {
        await dbPut({ id: bookId, bookId, title: title || ('Book #' + bookId),
                      size: info.size, savedAt: Date.now() });
      } else if (typeof window.dbPut === 'function') {
        await window.dbPut({ id: bookId, bookId, title: title || ('Book #' + bookId),
                             size: info.size, savedAt: Date.now() });
      }
    } catch(e){ console.warn('meta save failed', e); }
    return info;
  }

  // Override the old versions
  if (window.IASOffline) {
    window.IASOffline.saveBookOffline = saveWithMeta;
  }
  window.saveOfflineDetail = async function(bookId, title, btn) {
    const orig = btn ? btn.innerHTML : '';
    if (btn) { btn.disabled = true; btn.innerHTML = '⬇ Starting…'; }
    try {
      const info = await saveWithMeta(bookId, title, (recv, tot) => {
        if (!btn) return;
        if (tot > 0) {
          const pct = Math.floor(recv * 100 / tot);
          btn.innerHTML = '⬇ ' + pct + '% (' + Math.round(recv/1024/1024*10)/10 + ' MB)';
        } else {
          btn.innerHTML = '⬇ ' + Math.round(recv/1024/1024*10)/10 + ' MB';
        }
      });
      if (btn) btn.innerHTML = '✅ Saved (' + Math.round(info.size/1024/1024*10)/10 + ' MB)';
      alert('Saved offline: ' + (title || ('Book #'+bookId)) +
            '\nSize: ' + Math.round(info.size/1024/1024*10)/10 + ' MB\n' +
            'Now works in airplane mode.');
    } catch(e) {
      if (btn) btn.innerHTML = orig || '⬇ Save Offline';
      alert('Save failed: ' + e.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  console.log('[patch19b] streaming offline save ready');
})();
