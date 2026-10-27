(function () {
  "use strict";

  var links = document.querySelectorAll(".filters a");
  if (!links.length) return;

  function markCurrent() {
    var hash = window.location.hash || "#realisations";
    links.forEach(function (link) {
      if (link.getAttribute("href") === hash) {
        link.setAttribute("aria-current", "true");
      } else {
        link.removeAttribute("aria-current");
      }
    });
  }

  window.addEventListener("hashchange", markCurrent);
  markCurrent();
})();
