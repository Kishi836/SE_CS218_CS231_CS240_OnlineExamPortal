// FR-028: tell the server each time the examination window loses focus. The request carries no time;
// the server stamps it (UT_067). Loaded by the attempt page with data-focus-url set on <body>.
(() => {
  const url = document.body.dataset.focusUrl;
  if (!url) {
    return;
  }
  const csrf = document.querySelector("input[name=csrfmiddlewaretoken]");

  const report = () => {
    const body = new FormData();
    if (csrf) {
      body.append("csrfmiddlewaretoken", csrf.value);
    }
    fetch(url, { method: "POST", body, keepalive: true });
  };

  let away = false;

  const onAway = () => {
    if (!away) {
      away = true;
      report();
    }
  };

  const onReturn = () => {
    away = false;
  };

  window.addEventListener("blur", onAway);
  window.addEventListener("focus", onReturn);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      onAway();
    } else {
      onReturn();
    }
  });
})();
