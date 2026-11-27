(function () {
  var root = document.documentElement;
  function stored() { try { return localStorage.getItem("ra-theme"); } catch (e) { return null; } }
  var t = stored() || (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  root.setAttribute("data-theme", t);
  root.classList.add("js");

  document.addEventListener("DOMContentLoaded", function () {
    var b = document.getElementById("theme");
    if (b) b.addEventListener("click", function () {
      var n = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", n);
      try { localStorage.setItem("ra-theme", n); } catch (e) {}
    });
    var m = document.getElementById("menu"), links = document.querySelector(".nav-links");
    if (m && links) m.addEventListener("click", function () {
      var open = links.classList.toggle("open"); m.setAttribute("aria-expanded", open);
    });

    // scroll reveal
    var els = document.querySelectorAll(".reveal");
    els.forEach(function (e) { if (e.getBoundingClientRect().top < window.innerHeight) e.classList.add("in"); });
    setTimeout(function () { els.forEach(function (e) { e.classList.add("in"); }); }, 2500); // never leave content hidden
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
      }, { threshold: 0.12 });
      els.forEach(function (e) { io.observe(e); });
    } else { els.forEach(function (e) { e.classList.add("in"); }); }

    // registry filter
    var q = document.getElementById("q"), f = document.getElementById("field"),
        rows = document.querySelectorAll("[data-text]"), none = document.getElementById("nomatch");
    function filter() {
      var s = (q && q.value || "").toLowerCase(), fv = f && f.value || "", shown = 0;
      rows.forEach(function (r) {
        var ok = r.getAttribute("data-text").indexOf(s) >= 0 && (!fv || r.getAttribute("data-field") === fv);
        r.style.display = ok ? "" : "none"; if (ok) shown++;
      });
      if (none) none.style.display = shown || !rows.length ? "none" : "";
    }
    if (q) q.addEventListener("input", filter);
    if (f) f.addEventListener("change", filter);

    // copy buttons
    document.querySelectorAll("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var el = document.getElementById(btn.getAttribute("data-copy"));
        if (!el || !navigator.clipboard) return;
        navigator.clipboard.writeText(el.textContent).then(function () {
          var o = btn.textContent; btn.textContent = "Copied"; setTimeout(function () { btn.textContent = o; }, 1500);
        });
      });
    });
  });
})();
