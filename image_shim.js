/* sized-variant shim — injected into every page by optimize_images.py.
 *
 * Squarespace's runtime image loader requests `<path>/name.ext?format=300w`.
 * On static hosting the query string is ignored, so that request is answered
 * with whatever single file sits at that path — a thumbnail slot gets a
 * full-size master. The summary and gallery blocks rebuild their <img>
 * elements client-side, so rewriting the static HTML does not reach them.
 *
 * This maps those requests onto the real `name__<N>w.ext` files that
 * optimize_images.py emits. MANIFEST is { canonicalPath: [availableWidths] }.
 * Anything not in the manifest — the Klarna GIF included — is passed through
 * untouched, and any failure returns the original URL, which is exactly the
 * behaviour that existed before this shim.
 */
(function () {
  try {
    var MANIFEST = __MANIFEST__;
    var RE = /^(.*)\.([A-Za-z0-9]+)\?format=(\d+)w$/;

    function map(url) {
      try {
        var s = String(url);
        if (s.indexOf('?format=') < 0) return url;
        var m = RE.exec(s.replace(/^https?:\/\/[^/]+/, ''));
        if (!m) return url;
        var widths = MANIFEST[decodeURIComponent(m[1] + '.' + m[2])];
        if (!widths) return url;
        var want = +m[3], pick = null;
        for (var i = 0; i < widths.length; i++) {
          if (widths[i] >= want) { pick = widths[i]; break; }
        }
        if (pick === null) pick = widths[widths.length - 1];
        return m[1] + '__' + pick + 'w.' + m[2];
      } catch (e) { return url; }
    }

    var desc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
    if (desc && desc.set) {
      Object.defineProperty(HTMLImageElement.prototype, 'src', {
        configurable: true,
        enumerable: desc.enumerable,
        get: function () { return desc.get.call(this); },
        set: function (v) { desc.set.call(this, map(v)); }
      });
    }

    var setAttr = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function (name, value) {
      if (this instanceof HTMLImageElement && String(name).toLowerCase() === 'src') {
        value = map(value);
      }
      return setAttr.call(this, name, value);
    };
  } catch (e) { /* leave the page exactly as it was */ }
})();
