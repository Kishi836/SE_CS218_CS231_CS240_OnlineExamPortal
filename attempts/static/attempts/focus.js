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
  // A page being unloaded (moving to another question, submitting) is hidden too; that is not a focus
  // loss. pagehide fires before the unload's visibilitychange; pageshow clears it on a back-forward restore.
  let leaving = false;
  window.addEventListener("pagehide", () => {
    leaving = true;
  });
  window.addEventListener("pageshow", () => {
    leaving = false;
  });

  const onAway = () => {
    if (!away && !leaving) {
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
