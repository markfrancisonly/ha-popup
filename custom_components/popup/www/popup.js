// Popup overlay: renders a Lovelace card sent by the popup integration
// (popup.open / popup.close) on top of whatever dashboard is showing.
(function () {
    const Z = 2147483000;
    let overlay = null, current = null, pump = null, timer = null;
    const getHass = () => document.querySelector('home-assistant')?.hass;
    // Mount inside Home Assistant's element tree: card tap actions (hass-action)
    // and more-info requests are handled by ancestors there, not by <body>.
    const mount = () => document.querySelector('home-assistant')?.shadowRoot?.querySelector('home-assistant-main')?.shadowRoot || document.body;

    function close(id) {
        if (!overlay) return;
        if (id && current && id !== current) return;
        clearInterval(pump); pump = null;
        clearTimeout(timer); timer = null;
        overlay.remove(); overlay = null; current = null;
    }

    // "view": "/lovelace/keypad" -> that view's cards, resolved in the browser
    async function viewCard(view) {
        const parts = String(view).replace(/^\/+/, '').split('/');
        const urlPath = parts[0] === 'lovelace' ? null : parts[0];
        const key = parts[1] ?? '0';
        const cfg = await getHass().callWS({ type: 'lovelace/config', url_path: urlPath });
        const v = cfg.views.find((x, i) => x.path === key || String(i) === key);
        if (!v) throw new Error(`popup: view ${view} not found`);
        const cards = v.cards || [];
        return cards.length === 1 ? cards[0] : { type: 'vertical-stack', cards };
    }

    // message-only popup: a small banner at the bottom (a toast)
    function toast(id, message, timeout, dismissable) {
        close();
        overlay = document.createElement('div');
        overlay.id = 'ha-popup-toast';
        overlay.style.cssText = `position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:${Z};` +
            'background:var(--card-background-color,#222);color:var(--primary-text-color,#fff);' +
            'padding:14px 22px;border-radius:10px;font-size:18px;box-shadow:0 6px 24px rgba(0,0,0,.5);max-width:90vw;';
        overlay.textContent = message;
        if (dismissable) overlay.addEventListener('click', () => close());
        mount().appendChild(overlay);
        current = id;
        if (timeout) timer = setTimeout(() => close(id), timeout * 1000);
    }

    async function open(data) {
        const { id, card, view, message, title, dismissable = true, timeout, close_on_tap = false } = data || {};
        if (!id) return;
        if (!(card || view)) { if (message) toast(id, message, timeout || 5, dismissable); return; }
        close();
        let config = card;
        try { if (!config) config = await viewCard(view); }
        catch (e) { console.warn(e); return; }
        // render through hui-card, as Home Assistant's own views do: it is the
        // wrapper that performs a card's tap actions (hass-action)
        await window.loadCardHelpers();
        const el = document.createElement('hui-card');
        el.hass = getHass();
        el.config = config;
        el.load();

        overlay = document.createElement('div');
        overlay.id = 'ha-popup-overlay';
        overlay.style.cssText =
            `position:fixed;inset:0;z-index:${Z};background:rgba(0,0,0,.6);` +
            'display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;';
        const box = document.createElement('div');
        box.style.cssText =
            'background:var(--card-background-color,#111);color:var(--primary-text-color);' +
            'border-radius:12px;max-width:min(96vw,720px);max-height:96vh;width:100%;' +
            'overflow:auto;box-shadow:0 8px 32px rgba(0,0,0,.6);';
        if (title) {
            const h = document.createElement('div');
            h.textContent = title;
            h.style.cssText = 'font-size:20px;font-weight:500;padding:16px 16px 0;';
            box.appendChild(h);
        }
        const body = document.createElement('div');
        body.style.cssText = 'padding:8px;';
        body.appendChild(el);
        box.appendChild(body);
        overlay.appendChild(box);
        if (dismissable) overlay.addEventListener('click', (ev) => { if (ev.target === overlay) close(); });
        // close_on_tap: any tap inside the card closes the popup after the
        // tap's own action has fired (menus of one-shot buttons)
        if (close_on_tap) body.addEventListener('click', () => setTimeout(() => close(id), 150));
        mount().appendChild(overlay);
        current = id;
        pump = setInterval(() => { const h = getHass(); if (h && overlay) el.hass = h; }, 1000);
        if (timeout) timer = setTimeout(() => close(id), timeout * 1000);
    }

    document.addEventListener('keydown', (ev) => {
        if (ev.key === 'Escape' && overlay) { ev.stopPropagation(); ev.preventDefault(); close(); }
    }, true);

    async function subscribe() {
        for (let i = 0; i < 240; i++) {
            const conn = getHass()?.connection;
            if (conn) {
                conn.subscribeMessage((msg) => {
                    if (msg?.event_type === 'popup_open') open(msg.data);
                    else if (msg?.event_type === 'popup_close') close(msg.data?.id);
                }, { type: 'popup/subscribe' }).catch((e) => console.warn('popup: subscribe failed', e));
                return;
            }
            await new Promise((r) => setTimeout(r, 500));
        }
    }
    subscribe();
    window.haPopup = { open, close };

    // LOCAL open from a dashboard tap action (this browser only):
    //   tap_action: { action: fire-dom-event, popup: { id: x, card: {...}, title: ... } }
    //   tap_action: { action: fire-dom-event, popup: close }
    window.addEventListener('ll-custom', (ev) => {
        const cfg = ev.detail?.popup;
        if (!cfg) return;
        if (cfg === 'close' || cfg.action === 'close') close(cfg.id);
        else open({ id: cfg.id || 'local', ...cfg });
    });
})();
