/* Gap Scout dashboard: small progressive enhancements. Every page also works without this file. */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  function hide(toast) {
    toast.classList.add("hide");
    setTimeout(function () { toast.remove(); }, 300);
  }

  function initToasts() {
    document.querySelectorAll("[data-toast]").forEach(function (toast) {
      var close = toast.querySelector("[data-dismiss]");
      if (close) close.addEventListener("click", function () { hide(toast); });
      if (!toast.hasAttribute("data-sticky")) setTimeout(function () { hide(toast); }, 5000);
    });
    // Forget ?msg= / ?err= so a reload does not show the same toast again.
    var url = new URL(window.location.href);
    if (url.searchParams.has("msg") || url.searchParams.has("err")) {
      url.searchParams.delete("msg");
      url.searchParams.delete("err");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
  }

  function initConfirm() {
    // <form data-confirm="Question?"> asks before submitting (replaces inline onsubmit handlers).
    document.addEventListener("submit", function (event) {
      var form = event.target;
      var message = form instanceof HTMLFormElement ? form.getAttribute("data-confirm") : null;
      if (message && !window.confirm(message)) event.preventDefault();
    });
  }

  function initOpeners() {
    // <button data-open="#id"> opens <details id="id"> and focuses its first field.
    document.querySelectorAll("[data-open]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = document.querySelector(button.getAttribute("data-open"));
        if (!target) return;
        target.open = true;
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        var field = target.querySelector("textarea, input, select");
        if (field) field.focus({ preventScroll: true });
      });
    });
  }

  var GO = { h: "/", g: "/gaps", a: "/pipeline", k: "/knowledge", s: "/settings" };

  function typing(el) {
    return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  }

  function initShortcuts() {
    // "g" then h/g/a/k/s jumps to a section; "/" focuses the search box where there is one.
    var gPressedAt = 0;
    document.addEventListener("keydown", function (event) {
      if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target)) return;
      if (event.key === "/") {
        var search = document.querySelector("[data-search]");
        if (search) {
          event.preventDefault();
          search.focus();
          search.select();
        }
        return;
      }
      if (gPressedAt && Date.now() - gPressedAt < 1000 && GO[event.key]) {
        gPressedAt = 0;
        window.location.href = GO[event.key];
        return;
      }
      gPressedAt = event.key === "g" ? Date.now() : 0;
    });
  }

  initToasts();
  initConfirm();
  initOpeners();
  initShortcuts();
})();
