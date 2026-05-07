/* Native <dialog>-based expand modal for chart cards.
   Pages register chart renderers by id; clicking the expand button on a card
   opens a fullscreen modal and calls the renderer against the modal host. */
(function () {
  const registry = new Map();
  let dialog = null;
  let titleEl = null;
  let bodyEl = null;
  let subEl = null;
  let activeId = null;

  function ensureDialog() {
    if (dialog) return;
    dialog = document.createElement("dialog");
    dialog.className = "expand-modal";
    dialog.innerHTML = `
      <div class="expand-shell">
        <header class="expand-head">
          <div>
            <h2 class="expand-title">—</h2>
            <div class="expand-sub"></div>
          </div>
          <button class="btn btn-icon btn-ghost expand-close" aria-label="Close">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
          </button>
        </header>
        <div class="expand-body"></div>
      </div>`;
    document.body.appendChild(dialog);
    titleEl = dialog.querySelector(".expand-title");
    subEl = dialog.querySelector(".expand-sub");
    bodyEl = dialog.querySelector(".expand-body");
    dialog.querySelector(".expand-close").addEventListener("click", close);
    dialog.addEventListener("click", (ev) => { if (ev.target === dialog) close(); });
    dialog.addEventListener("close", () => {
      const closingId = activeId;
      bodyEl.innerHTML = "";
      activeId = null;
      /* Give the registered renderer a chance to rebuild the page-level chart.
         Chart.js destroys the prior instance when we re-target the modal canvas,
         so the page chart needs to be re-rendered on close. */
      const r = closingId && registry.get(closingId);
      if (r && typeof r.onClose === "function") {
        try { r.onClose(); } catch (e) { console.error("[expand] onClose threw", e); }
      }
    });
    window.addEventListener("themechange", () => {
      if (activeId && dialog.open) {
        bodyEl.innerHTML = "";
        const r = registry.get(activeId);
        if (r) r.render(bodyEl);
      }
    });
  }

  function register(id, opts) {
    registry.set(id, opts);
  }

  function open(id) {
    const r = registry.get(id);
    if (!r) return;
    ensureDialog();
    activeId = id;
    titleEl.textContent = r.title || "";
    subEl.textContent = r.sub || "";
    bodyEl.innerHTML = "";
    r.render(bodyEl);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function close() {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  /* Wire any data-expand="ID" buttons in the document (called once after register). */
  function wireButtons() {
    document.querySelectorAll("[data-expand]").forEach(btn => {
      if (btn._wired) return;
      btn._wired = true;
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        open(btn.getAttribute("data-expand"));
      });
    });
  }

  window.Expand = { register, open, close, wireButtons };
})();
