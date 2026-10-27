(function () {
  "use strict";

  var gallery = document.querySelector("[data-gallery]");
  var dialog = document.querySelector(".lightbox");
  if (!gallery || !dialog || typeof dialog.showModal !== "function") return;

  var links = Array.prototype.slice.call(gallery.querySelectorAll("a"));
  var image = dialog.querySelector(".lightbox__image");
  var caption = dialog.querySelector(".lightbox__caption");
  var currentIndex = 0;
  var opener = null;

  function show(index) {
    currentIndex = (index + links.length) % links.length;
    var link = links[currentIndex];
    var thumbnail = link.querySelector("img");
    image.srcset = link.dataset.medium + " 800w, " + link.href + " 1600w";
    image.sizes = "100vw";
    image.src = link.href;
    image.width = Number(link.dataset.width);
    image.height = Number(link.dataset.height);
    image.alt = thumbnail.alt;
    caption.textContent = (currentIndex + 1) + " / " + links.length;
  }

  function open(index, trigger) {
    opener = trigger;
    show(index);
    dialog.showModal();
    dialog.querySelector(".lightbox__close").focus();
  }

  gallery.addEventListener("click", function (event) {
    var link = event.target.closest("a");
    if (!link) return;
    event.preventDefault();
    open(links.indexOf(link), link);
  });

  dialog.querySelector(".lightbox__previous").addEventListener("click", function () { show(currentIndex - 1); });
  dialog.querySelector(".lightbox__next").addEventListener("click", function () { show(currentIndex + 1); });
  dialog.querySelector(".lightbox__close").addEventListener("click", function () { dialog.close(); });

  dialog.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft") show(currentIndex - 1);
    if (event.key === "ArrowRight") show(currentIndex + 1);
  });

  dialog.addEventListener("close", function () {
    image.removeAttribute("srcset");
    image.removeAttribute("src");
    if (opener) opener.focus();
  });
})();
