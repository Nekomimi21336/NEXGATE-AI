(function () {
  var KEY = "nexgate_logo_anim_at";

  function onRevealEnd() {
    sessionStorage.setItem(KEY, String(Date.now()));
  }

  function bind() {
    if (document.documentElement.classList.contains("logo-brand-skip")) {
      return;
    }

    document.querySelectorAll(".logo-brand").forEach(function (el) {
      el.addEventListener(
        "animationend",
        function (e) {
          if (e.animationName !== "logoBrandReveal") {
            return;
          }
          onRevealEnd();
        },
        { once: true }
      );
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
