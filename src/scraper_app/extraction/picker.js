/* Visual picker injected into pages opened by ProScraper. */
(() => {
  if (window.__proscraperPicker) return;

  const cssPath = (element, stopAt) => {
    if (element === stopAt) return ":scope";
    const parts = [];
    let node = element;
    while (node && node !== stopAt && node.nodeType === Node.ELEMENT_NODE) {
      const tag = node.tagName.toLowerCase();
      const stable = [...node.attributes]
        .filter(({ name, value }) =>
          /^(data-[\w-]+|id)$/.test(name) &&
          name !== "data-proscraper-highlight" &&
          value &&
          !/^\d+$/.test(value)
        )
        .slice(0, 2)
        .map(({ name, value }) => `[${name}="${CSS.escape(value)}"]`)[0];
      if (stable) {
        parts.unshift(`${tag}${stable}`);
        break;
      }
      const classes = [...node.classList]
        .filter(name => !/active|selected|hover|focus|css-|sc-/.test(name))
        .slice(0, 2)
        .map(name => `.${CSS.escape(name)}`);
      const siblings = node.parentElement
        ? [...node.parentElement.children].filter(sibling => sibling.tagName === node.tagName)
        : [];
      const position = siblings.length > 1 ? `:nth-of-type(${siblings.indexOf(node) + 1})` : "";
      parts.unshift(`${tag}${classes.join("")}${position}`);
      node = node.parentElement;
    }
    return parts.join(" > ");
  };

  const candidates = element => {
    const parent = element.parentElement;
    const candidates = [];
    for (let node = parent; node && node !== document.body; node = node.parentElement) {
      const peers = node.parentElement
        ? [...node.parentElement.children].filter(peer => peer.tagName === node.tagName)
        : [];
      if (peers.length > 1) {
        const selector = cssPath(node);
        const count = document.querySelectorAll(selector).length;
        if (count > 1) candidates.push({ node, selector, count });
        if (count >= 3) break;
      }
    }
    return candidates.sort((a, b) => Math.abs(a.count - 10) - Math.abs(b.count - 10));
  };

  window.__proscraperPicker = {
    active: false,
    enable() {
      if (this.active) return;
      this.active = true;
      this.onMove = event => {
        const target = event.target;
        if (!(target instanceof Element) || target.closest("#__proscraper-tip")) return;
        this.highlighted?.removeAttribute("data-proscraper-highlight");
        this.highlighted = target;
        target.setAttribute("data-proscraper-highlight", "true");
      };
      this.onClick = event => {
        const target = event.target;
        if (!(target instanceof Element) || target.closest("#__proscraper-tip")) return;
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        const patterns = candidates(target);
        const container = patterns[0]?.node || target.parentElement || target;
        const itemSelector = patterns[0]?.selector || cssPath(container);
        const fieldSelector = cssPath(target, container);
        const payload = {
          item_selector: itemSelector,
          field_selector: fieldSelector === ":scope" ? ":scope" : fieldSelector,
          count: document.querySelectorAll(itemSelector).length,
          sample: (target.innerText || target.textContent || "").trim().slice(0, 160),
          tag: target.tagName.toLowerCase(),
          suggested_name: target.getAttribute("aria-label") || target.getAttribute("alt") || target.tagName.toLowerCase()
        };
        this.disable();
        window.proscraperSelected(payload);
      };
      this.onKey = event => { if (event.key === "Escape") this.disable(); };
      document.addEventListener("mousemove", this.onMove, true);
      document.addEventListener("click", this.onClick, true);
      document.addEventListener("keydown", this.onKey, true);
      const style = document.createElement("style");
      style.id = "__proscraper-style";
      style.textContent = `
        [data-proscraper-highlight="true"] { outline: 3px solid #7c5cff !important; outline-offset: 2px !important; cursor: crosshair !important; }
        #__proscraper-tip { position: fixed; z-index: 2147483647; top: 12px; right: 12px; padding: 10px 14px;
          color: white; background: #17152b; border: 1px solid #7c5cff; border-radius: 10px;
          font: 13px -apple-system, sans-serif; box-shadow: 0 5px 24px #0005; pointer-events: none; }
      `;
      document.head.append(style);
      const tip = document.createElement("div");
      tip.id = "__proscraper-tip";
      tip.textContent = "Klik elemen untuk memilih · Esc untuk batal";
      document.body.append(tip);
    },
    disable() {
      this.active = false;
      document.removeEventListener("mousemove", this.onMove, true);
      document.removeEventListener("click", this.onClick, true);
      document.removeEventListener("keydown", this.onKey, true);
      this.highlighted?.removeAttribute("data-proscraper-highlight");
      document.querySelector("#__proscraper-tip")?.remove();
      document.querySelector("#__proscraper-style")?.remove();
    }
  };
})();
