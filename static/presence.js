// How many browsers have this page open. A count, not a record: the server is
// told "still here" and answers with a number, and nothing about what anyone
// searched for is sent or stored.
//
// Deliberately quiet. The line stays hidden at a count of one, because you are
// always one of them and "1 person using this now" to the only person online
// says nothing. Most of the day this renders nothing at all.
(function () {
  var EL = document.getElementById("presence");
  if (!EL) return;

  // Must match HEARTBEAT_SECONDS in presence.py; the server's window is three
  // beats wide, so one dropped request never blinks anyone out of the count.
  var BEAT_MS = 60 * 1000;
  // A tab left open on an unattended desk would otherwise beat for ever and
  // count someone who went home. The Page Visibility API does not catch that:
  // the tab is still visible, just nobody is there.
  var IDLE_MS = 10 * 60 * 1000;

  var lastActive = Date.now();
  var timer = null;

  function render(count) {
    if (!(count > 1)) {
      EL.hidden = true;
      return;
    }
    EL.textContent = count + " people using this now";
    EL.hidden = false;
  }

  function beat() {
    if (document.hidden || Date.now() - lastActive > IDLE_MS) return;
    fetch("/api/presence", { method: "POST" })
      .then(function (res) {
        if (res.status === 401) {
          window.location = "/login";
          return null;
        }
        return res.ok ? res.json() : null;
      })
      .then(function (data) {
        if (data && typeof data.count === "number") render(data.count);
      })
      .catch(function () {
        // Offline, or the server is unhappy. Leave the last good number on
        // screen rather than flashing a wrong one; the next beat will correct
        // it. This must never disturb the search box.
      });
  }

  function markActive() {
    var wasIdle = Date.now() - lastActive > IDLE_MS;
    lastActive = Date.now();
    // Coming back from idle, check in at once rather than waiting out the
    // interval, so the number is right by the time they have read it.
    if (wasIdle) beat();
  }

  ["pointermove", "keydown", "scroll", "focus"].forEach(function (evt) {
    window.addEventListener(evt, markActive, { passive: true });
  });

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) markActive();
  });

  beat();
  timer = setInterval(beat, BEAT_MS);
  window.addEventListener("pagehide", function () {
    clearInterval(timer);
  });
})();
