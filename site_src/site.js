(function () {
  var root = document.documentElement;
  function stored() { try { return localStorage.getItem("ra-theme"); } catch (e) { return null; } }
  function apply(t) { root.setAttribute("data-theme", t); var b = document.getElementById("theme"); if (b) b.textContent = t === "dark" ? "Light" : "Dark"; }
  var t = stored() || (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  apply(t);
  document.addEventListener("DOMContentLoaded", function () {
    apply(root.getAttribute("data-theme"));
    var b = document.getElementById("theme");
    if (b) b.addEventListener("click", function () {
      var n = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      apply(n); try { localStorage.setItem("ra-theme", n); } catch (e) {}
    });
    var q = document.getElementById("q"), f = document.getElementById("field"), rows = document.querySelectorAll("#registry tbody tr[data-text]");
    function filter() {
      var s = (q && q.value || "").toLowerCase(), fv = f && f.value || "";
      rows.forEach(function (r) {
        var ok = r.getAttribute("data-text").indexOf(s) >= 0 && (!fv || r.getAttribute("data-field") === fv);
        r.style.display = ok ? "" : "none";
      });
    }
    if (q) q.addEventListener("input", filter);
    if (f) f.addEventListener("change", filter);
  });
})();
