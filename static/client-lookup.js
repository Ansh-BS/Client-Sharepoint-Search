// Live client-name lists on the admin page (Remove a client, Add or update a
// client). Fetches the client list once, then filters it client-side as the
// office types so they can see and click the exact match instead of guessing
// at spelling.
(function () {
  let clientsPromise = null;
  function getClients() {
    if (!clientsPromise) {
      clientsPromise = fetch("/api/clients")
        .then((r) => (r.ok ? r.json() : []))
        .then((data) =>
          (data || []).slice().sort((a, b) =>
            (a.name || "").localeCompare(b.name || "")))
        .catch(() => []);
    }
    return clientsPromise;
  }

  function setupLookup(inputId, listId, onPick) {
    const input = document.getElementById(inputId);
    const list = document.getElementById(listId);
    if (!input || !list) return;

    function render(clients, query) {
      const q = query.trim().toLowerCase();
      const matches = q
        ? clients.filter((c) =>
            (c.name || "").toLowerCase().includes(q) ||
            (c.id || "").toLowerCase().includes(q))
        : clients;

      list.innerHTML = "";
      if (!matches.length) {
        const li = document.createElement("li");
        li.className = "suggest-empty";
        li.textContent = q ? "No matching client." : "No clients yet.";
        list.appendChild(li);
      } else {
        for (const c of matches) {
          const li = document.createElement("li");
          li.textContent = c.id ? `${c.name} (${c.id})` : c.name;
          // mousedown fires before the input's blur, so the click is
          // captured before hide() would otherwise remove the list.
          li.addEventListener("mousedown", (e) => {
            e.preventDefault();
            onPick(c);
            hide();
          });
          list.appendChild(li);
        }
      }
      list.hidden = false;
    }

    function hide() {
      list.hidden = true;
    }

    input.addEventListener("focus", () =>
      getClients().then((clients) => render(clients, input.value)));
    input.addEventListener("input", () =>
      getClients().then((clients) => render(clients, input.value)));
    input.addEventListener("blur", hide);
  }

  // Remove a client: click fills the query field with the precise ID.
  setupLookup("client_query", "client-suggestions", (c) => {
    document.getElementById("client_query").value = c.id || c.name;
  });

  // Add or update a client: click loads the existing record for editing.
  setupLookup("client_name", "client-name-suggestions", (c) => {
    document.getElementById("client_name").value = c.name || "";
    document.getElementById("client_id").value = c.id || "";
    document.getElementById("client_link").value = c.link || "";
  });
})();
