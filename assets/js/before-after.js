(function () {
  "use strict";

  document.querySelectorAll("[data-before-after]").forEach(function (figure) {
    var control = figure.querySelector(".before-after__control");
    var slider = control.querySelector("input");

    function update() {
      figure.style.setProperty("--split", slider.value + "%");
      slider.setAttribute("aria-valuetext", slider.value + " % avant");
    }

    slider.addEventListener("input", update);
    control.hidden = false;
    figure.classList.add("is-interactive");
    update();
  });
})();
