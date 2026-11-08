/**
 * DomoLink-Camera Custom Panel for Home Assistant
 * Modern glassmorphism UI matching Domolink-Alarm design language
 */

class DomolinkCameraPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._cameras = [];
    this._availableEntities = [];
    this._activeTab = "cameras"; // "cameras" or "settings"
    this._liveCameras = new Set();
    this._draggedIndex = null;
    this._hasUnsavedOrder = false;
    this._pairingActive = false;
    this._pairingLogs = [];
    this._scanResults = [];
    this._selectedCamera = null;
    this._refreshTimer = null;
    this._toastMsg = null;
  }

  set hass(hass) {
    const isFirst = !this._hass;
    this._hass = hass;
    if (isFirst) {
      this._init();
    } else {
      this._updateEntitiesState();
    }
  }

  connectedCallback() {
    this._startPeriodicRefresh();
  }

  disconnectedCallback() {
    this._stopPeriodicRefresh();
  }

  async _init() {
    await this._fetchCameras();
    await this._fetchAvailableEntities();
    this.render();
  }

  _startPeriodicRefresh() {
    this._stopPeriodicRefresh();
    // Refresh snapshot timestamps / status every 8 seconds if in cameras tab
    this._refreshTimer = setInterval(() => {
      if (this._activeTab === "cameras") {
        this._fetchCameras(false);
      }
    }, 8000);
  }

  _stopPeriodicRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  async _fetchCameras(renderAfter = true) {
    if (!this._hass) return;
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/get_cameras" });
      if (resp && resp.cameras) {
        this._cameras = resp.cameras;
        if (renderAfter) this.render();
      }
    } catch (e) {
      console.error("[DomoLink-Camera] Failed to fetch cameras:", e);
    }
  }

  async _fetchAvailableEntities() {
    if (!this._hass) return;
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/get_entities" });
      if (resp && resp.entities) {
        this._availableEntities = resp.entities;
      }
    } catch (e) {
      console.error("[DomoLink-Camera] Failed to fetch entities:", e);
    }
  }

  _updateEntitiesState() {
    // Light live refresh of entities in bottom banners
    const strips = this.shadowRoot.querySelectorAll(".entity-badge");
    strips.forEach((el) => {
      const entityId = el.dataset.entityId;
      const stateObj = this._hass.states[entityId];
      if (stateObj) {
        const valEl = el.querySelector(".badge-state");
        if (valEl) {
          const unit = stateObj.attributes.unit_of_measurement || "";
          valEl.textContent = `${stateObj.state} ${unit}`.trim();
        }
        if (stateObj.state === "on") {
          el.classList.add("active");
        } else {
          el.classList.remove("active");
        }
      }
    });
  }

  _showToast(msg, duration = 3000) {
    this._toastMsg = msg;
    const toast = this.shadowRoot.querySelector(".toast-bar");
    if (toast) {
      toast.textContent = msg;
      toast.classList.add("show");
      setTimeout(() => {
        toast.classList.remove("show");
      }, duration);
    }
  }

  // --- Drag and Drop Handlers ---
  _handleDragStart(e, index) {
    this._draggedIndex = index;
    e.dataTransfer.effectAllowed = "move";
    e.target.classList.add("dragging");
  }

  _handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }

  _handleDragEnter(e) {
    const card = e.target.closest(".camera-card");
    if (card) card.classList.add("drag-over");
  }

  _handleDragLeave(e) {
    const card = e.target.closest(".camera-card");
    if (card) card.classList.remove("drag-over");
  }

  _handleDrop(e, targetIndex) {
    e.preventDefault();
    const card = e.target.closest(".camera-card");
    if (card) card.classList.remove("drag-over");

    if (this._draggedIndex !== null && this._draggedIndex !== targetIndex) {
      const movedItem = this._cameras.splice(this._draggedIndex, 1)[0];
      this._cameras.splice(targetIndex, 0, movedItem);
      this._hasUnsavedOrder = true;
      this.render();
    }
    this._draggedIndex = null;
  }

  _handleDragEnd(e) {
    e.target.classList.remove("dragging");
    const cards = this.shadowRoot.querySelectorAll(".camera-card");
    cards.forEach((c) => c.classList.remove("drag-over"));
  }

  async _saveLayoutOrder() {
    if (!this._hass) return;
    const order = this._cameras.map((c) => c.id);
    try {
      await this._hass.callWS({
        type: "domolink_camera/save_layout",
        order: order,
      });
      this._hasUnsavedOrder = false;
      this._showToast("Disposition des caméras sauvegardée avec succès !");
      this.render();
    } catch (e) {
      console.error("Save layout failed", e);
      this._showToast("Erreur lors de la sauvegarde de l'ordre");
    }
  }

  // --- Live Stream Toggle ---
  _toggleLive(camId) {
    if (this._liveCameras.has(camId)) {
      this._liveCameras.delete(camId);
      this._hass.callWS({ type: "domolink_camera/trigger_live", camera_id: camId, live: false });
    } else {
      this._liveCameras.add(camId);
      this._hass.callWS({ type: "domolink_camera/trigger_live", camera_id: camId, live: true });
    }
    this.render();
  }

  // --- Toggle HA Entity from Card Banner ---
  async _toggleEntity(entityId) {
    if (!this._hass) return;
    const domain = entityId.split(".")[0];
    try {
      if (domain === "switch" || domain === "light" || domain === "fan") {
        await this._hass.callService("homeassistant", "toggle", { entity_id: entityId });
      } else if (domain === "lock") {
        const cur = this._hass.states[entityId]?.state;
        const svc = cur === "locked" ? "unlock" : "lock";
        await this._hass.callService("lock", svc, { entity_id: entityId });
      } else {
        this._showToast(`Entité ${entityId} : ${this._hass.states[entityId]?.state || "N/A"}`);
      }
    } catch (e) {
      console.error("Failed to toggle entity", e);
    }
  }

  // --- Settings Actions ---
  async _startPairing() {
    const ssidInput = this.shadowRoot.querySelector("#pair-ssid");
    const passInput = this.shadowRoot.querySelector("#pair-pass");
    const apIpInput = this.shadowRoot.querySelector("#pair-ap-ip");

    const ssid = ssidInput ? ssidInput.value.trim() : "";
    const pass = passInput ? passInput.value.trim() : "";
    const apIp = apIpInput ? apIpInput.value.trim() || "192.168.1.254" : "192.168.1.254";

    if (!ssid) {
      alert("Veuillez saisir le SSID de votre réseau Wi-Fi.");
      return;
    }

    this._pairingActive = true;
    this._pairingLogs = ["Initialisation de l'assistant d'appairage..."];
    this.render();

    try {
      await this._hass.callWS({
        type: "domolink_camera/start_pairing",
        ssid: ssid,
        password: pass,
        camera_ap_ip: apIp,
      });

      // Poll pairing status every 2 seconds
      const pollTimer = setInterval(async () => {
        try {
          const st = await this._hass.callWS({ type: "domolink_camera/pair_status" });
          if (st) {
            this._pairingLogs = st.logs || [];
            if (!st.active) {
              clearInterval(pollTimer);
              this._pairingActive = false;
              if (st.discovered && st.discovered.length > 0) {
                this._scanResults = st.discovered;
                this._showToast("Caméra appairée avec succès !");
              }
              this.render();
            } else {
              this._updatePairingLogs();
            }
          }
        } catch (e) {
          clearInterval(pollTimer);
          this._pairingActive = false;
          this.render();
        }
      }, 2000);
    } catch (e) {
      this._pairingActive = false;
      this._showToast("Échec du démarrage de l'appairage");
      this.render();
    }
  }

  _updatePairingLogs() {
    const logBox = this.shadowRoot.querySelector(".pairing-logs");
    if (logBox) {
      logBox.innerHTML = this._pairingLogs.map((l) => `<div>> ${l}</div>`).join("");
      logBox.scrollTop = logBox.scrollHeight;
    }
  }

  async _scanLocalNetwork() {
    this._showToast("Recherche de caméras sur le réseau local (UDP 32108)...");
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/scan_local" });
      if (resp && resp.devices) {
        this._scanResults = resp.devices;
        this._showToast(`${resp.devices.length} caméra(s) détectée(s) !`);
        this.render();
      }
    } catch (e) {
      this._showToast("Erreur lors du scan local");
    }
  }

  async _addDiscoveredCamera(dev) {
    const newCam = {
      name: dev.model || "Caméra Wi-Fi",
      description: "Nouvelle caméra détectée sur le réseau local",
      driver: dev.driver || "ysxlite_pppp",
      host: dev.host,
      port: dev.port || 32108,
      linked_entities: [],
    };
    await this._saveCamera(newCam);
    // Remove from scan results
    this._scanResults = this._scanResults.filter((d) => d.host !== dev.host);
    this._showToast(`Caméra ${dev.host} ajoutée avec succès !`);
    await this._fetchCameras();
    this.render();
  }

  async _saveCamera(cam) {
    try {
      await this._hass.callWS({
        type: "domolink_camera/save_camera",
        camera: cam,
      });
      this._showToast("Caméra enregistrée !");
      await this._fetchCameras();
      this._selectedCamera = null;
      this.render();
    } catch (e) {
      this._showToast("Erreur d'enregistrement de la caméra");
    }
  }

  async _deleteCamera(camId) {
    if (!confirm("Voulez-vous vraiment supprimer cette caméra ?")) return;
    try {
      await this._hass.callWS({
        type: "domolink_camera/delete_camera",
        camera_id: camId,
      });
      this._showToast("Caméra supprimée.");
      await this._fetchCameras();
      this.render();
    } catch (e) {
      this._showToast("Erreur lors de la suppression");
    }
  }

  _formatTime(timestamp) {
    if (!timestamp) return "Pas de snapshot";
    const d = new Date(timestamp * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  _getEntityIcon(domain) {
    switch (domain) {
      case "light":
        return "💡";
      case "switch":
        return "🔌";
      case "binary_sensor":
        return "🚨";
      case "sensor":
        return "🌡️";
      case "lock":
        return "🔒";
      case "cover":
        return "🪟";
      case "climate":
        return "❄️";
      default:
        return "⚡";
    }
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          box-sizing: border-box;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          background: #0d1117;
          color: #f0f6fc;
          margin: 0;
          padding: 24px;
        }

        /* ─── Domolink Glassmorphism Theme ─── */
        .panel-container {
          max-width: 1500px;
          margin: 0 auto;
        }

        header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding-bottom: 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          margin-bottom: 24px;
        }

        .brand-box {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .brand-icon {
          width: 44px;
          height: 44px;
          background: linear-gradient(135deg, #2563eb, #3b82f6);
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 24px;
          box-shadow: 0 4px 16px rgba(37, 99, 235, 0.35);
        }

        .brand-title {
          font-size: 22px;
          font-weight: 700;
          letter-spacing: -0.5px;
          background: linear-gradient(90deg, #f0f6fc, #93c5fd);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .brand-subtitle {
          font-size: 13px;
          color: #8b949e;
        }

        /* Tabs */
        .tabs {
          display: flex;
          background: rgba(22, 27, 34, 0.85);
          padding: 4px;
          border-radius: 10px;
          border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .tab-btn {
          background: transparent;
          border: none;
          color: #8b949e;
          padding: 8px 18px;
          font-size: 14px;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .tab-btn.active {
          background: #3b82f6;
          color: #ffffff;
          box-shadow: 0 2px 8px rgba(59, 130, 246, 0.4);
        }

        .tab-btn:hover:not(.active) {
          color: #f0f6fc;
        }

        /* Unsaved Order Floating Bar */
        .save-order-bar {
          position: fixed;
          bottom: 24px;
          left: 50%;
          transform: translateX(-50%);
          background: rgba(37, 99, 235, 0.95);
          backdrop-filter: blur(12px);
          color: #fff;
          padding: 12px 24px;
          border-radius: 50px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(59, 130, 246, 0.5);
          display: flex;
          align-items: center;
          gap: 16px;
          z-index: 1000;
          animation: popUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes popUp {
          from { opacity: 0; transform: translate(-50%, 20px); }
          to { opacity: 1; transform: translate(-50%, 0); }
        }

        .save-btn {
          background: #ffffff;
          color: #1e3a8a;
          border: none;
          padding: 8px 18px;
          border-radius: 20px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .save-btn:hover {
          background: #eff6ff;
          transform: scale(1.05);
        }

        /* Grid */
        .camera-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 24px;
        }

        /* Camera Card */
        .camera-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
          backdrop-filter: blur(20px);
          transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
          position: relative;
          cursor: grab;
        }

        .camera-card:hover {
          border-color: rgba(59, 130, 246, 0.4);
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), 0 0 16px rgba(59, 130, 246, 0.15);
        }

        .camera-card.dragging {
          opacity: 0.4;
          transform: scale(0.98);
        }

        .camera-card.drag-over {
          border: 2px dashed #3b82f6;
          transform: scale(1.02);
        }

        /* Card Header */
        .card-header {
          padding: 12px 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
          background: rgba(13, 17, 23, 0.6);
        }

        .card-title-box {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #8b949e;
        }

        .status-dot.online { background: #10b981; box-shadow: 0 0 8px #10b981; }
        .status-dot.streaming { background: #ef4444; box-shadow: 0 0 8px #ef4444; animation: blink 1s infinite; }
        .status-dot.offline { background: #64748b; }

        @keyframes blink {
          50% { opacity: 0.4; }
        }

        .card-name {
          font-weight: 600;
          font-size: 15px;
        }

        .driver-badge {
          font-size: 10px;
          background: rgba(255, 255, 255, 0.08);
          color: #93c5fd;
          padding: 2px 6px;
          border-radius: 4px;
          text-transform: uppercase;
        }

        /* Viewport / Video Area */
        .viewport {
          position: relative;
          width: 100%;
          aspect-ratio: 16 / 9;
          background: #000;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .viewport img {
          width: 100%;
          height: 100%;
          object-fit: cover;
          display: block;
        }

        /* Rollover Tooltip */
        .rollover-tooltip {
          position: absolute;
          top: 10px;
          left: 10px;
          right: 10px;
          background: rgba(13, 17, 23, 0.92);
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255, 255, 255, 0.15);
          padding: 8px 12px;
          border-radius: 8px;
          font-size: 12px;
          color: #f0f6fc;
          opacity: 0;
          transform: translateY(-6px);
          pointer-events: none;
          transition: all 0.2s ease;
          z-index: 10;
          line-height: 1.4;
          box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        }

        .viewport:hover .rollover-tooltip {
          opacity: 1;
          transform: translateY(0);
        }

        /* Live Button on Viewport */
        .live-btn {
          position: absolute;
          bottom: 10px;
          right: 10px;
          background: rgba(22, 27, 34, 0.85);
          backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.2);
          color: #f0f6fc;
          padding: 6px 12px;
          border-radius: 6px;
          font-size: 11px;
          font-weight: 700;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: all 0.15s ease;
          z-index: 5;
        }

        .live-btn:hover {
          background: #2563eb;
          border-color: #60a5fa;
        }

        .live-btn.active {
          background: #ef4444;
          border-color: #f87171;
          color: white;
          animation: pulseRed 2s infinite;
        }

        @keyframes pulseRed {
          0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.6); }
          50% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
        }

        .time-badge {
          position: absolute;
          bottom: 10px;
          left: 10px;
          background: rgba(0, 0, 0, 0.65);
          color: #94a3b8;
          font-size: 10px;
          padding: 3px 6px;
          border-radius: 4px;
        }

        /* Bottom Interactive Banner (Linked Entities) */
        .bottom-banner {
          background: rgba(15, 23, 42, 0.7);
          border-top: 1px solid rgba(255, 255, 255, 0.05);
          padding: 8px 12px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          align-items: center;
          min-height: 38px;
        }

        .banner-empty-msg {
          font-size: 11px;
          color: #64748b;
          font-style: italic;
        }

        .entity-badge {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          padding: 4px 8px;
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 11px;
          color: #cbd5e1;
          cursor: pointer;
          transition: all 0.15s ease;
          user-select: none;
        }

        .entity-badge:hover {
          background: rgba(59, 130, 246, 0.2);
          border-color: #3b82f6;
          color: #ffffff;
        }

        .entity-badge.active {
          background: rgba(16, 185, 129, 0.2);
          border-color: #10b981;
          color: #a7f3d0;
        }

        .badge-icon { font-size: 13px; }
        .badge-name { font-weight: 500; }
        .badge-state { font-weight: 600; opacity: 0.9; }

        /* Settings View */
        .settings-container {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .settings-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 24px;
          backdrop-filter: blur(20px);
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        .settings-card h3 {
          margin-top: 0;
          font-size: 18px;
          display: flex;
          align-items: center;
          gap: 10px;
          color: #f0f6fc;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 12px;
        }

        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 16px;
          margin-top: 16px;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .form-group label {
          font-size: 12px;
          font-weight: 600;
          color: #8b949e;
        }

        .form-input, .form-select {
          background: rgba(13, 17, 23, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 8px;
          padding: 10px 12px;
          color: #f0f6fc;
          font-size: 14px;
          outline: none;
          transition: border-color 0.15s ease;
        }

        .form-input:focus, .form-select:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }

        .btn-primary {
          background: #2563eb;
          color: white;
          border: none;
          padding: 10px 18px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          transition: background 0.15s ease;
        }

        .btn-primary:hover { background: #1d4ed8; }

        .btn-secondary {
          background: rgba(255, 255, 255, 0.08);
          color: #f0f6fc;
          border: 1px solid rgba(255, 255, 255, 0.15);
          padding: 8px 14px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.14);
        }

        .btn-danger {
          background: rgba(239, 68, 68, 0.2);
          color: #f87171;
          border: 1px solid rgba(239, 68, 68, 0.4);
          padding: 8px 14px;
          border-radius: 8px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-danger:hover {
          background: #ef4444;
          color: white;
        }

        /* Pairing Logs Box */
        .pairing-logs {
          background: #000;
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          padding: 12px;
          font-family: monospace;
          font-size: 12px;
          color: #4ade80;
          max-height: 160px;
          overflow-y: auto;
          margin-top: 14px;
        }

        /* Discovered List */
        .discovered-list {
          margin-top: 16px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .discovered-item {
          background: rgba(13, 17, 23, 0.6);
          border: 1px solid rgba(16, 185, 129, 0.3);
          border-radius: 8px;
          padding: 12px 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        /* Toast */
        .toast-bar {
          position: fixed;
          top: 20px;
          right: 20px;
          background: #1e293b;
          border: 1px solid #3b82f6;
          color: #f0f6fc;
          padding: 12px 20px;
          border-radius: 10px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.4);
          font-size: 14px;
          font-weight: 500;
          opacity: 0;
          transform: translateY(-10px);
          pointer-events: none;
          transition: all 0.25s ease;
          z-index: 2000;
        }

        .toast-bar.show {
          opacity: 1;
          transform: translateY(0);
        }

        /* Camera Edit List */
        .camera-edit-table {
          width: 100%;
          border-collapse: collapse;
          margin-top: 16px;
        }

        .camera-edit-table th, .camera-edit-table td {
          padding: 12px;
          text-align: left;
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .camera-edit-table th {
          color: #8b949e;
          font-size: 12px;
        }
      </style>

      <div class="panel-container">
        <!-- Toast Notification -->
        <div class="toast-bar"></div>

        <!-- Header -->
        <header>
          <div class="brand-box">
            <div class="brand-icon">📹</div>
            <div>
              <div class="brand-title">DomoLink-Camera</div>
              <div class="brand-subtitle">Gestion & Flux en direct pour caméras Wi-Fi</div>
            </div>
          </div>

          <div class="tabs">
            <button class="tab-btn ${this._activeTab === "cameras" ? "active" : ""}" id="tab-cameras">
              <span>🖼️</span> Caméras (${this._cameras.length})
            </button>
            <button class="tab-btn ${this._activeTab === "settings" ? "active" : ""}" id="tab-settings">
              <span>⚙️</span> Paramètres & Appairage
            </button>
          </div>
        </header>

        <!-- Main Content Area -->
        ${this._activeTab === "cameras" ? this._renderCamerasGrid() : this._renderSettings()}

        <!-- Save Layout Order Floating Bar -->
        ${
          this._hasUnsavedOrder && this._activeTab === "cameras"
            ? `
          <div class="save-order-bar">
            <span>✨ Disposition des vignettes modifiée</span>
            <button class="save-btn" id="btn-save-layout">💾 Sauvegarder l'ordre</button>
          </div>
        `
            : ""
        }
      </div>
    `;

    this._bindEvents();
  }

  _renderCamerasGrid() {
    if (!this._cameras || this._cameras.length === 0) {
      return `
        <div style="text-align: center; padding: 80px 20px; background: rgba(22,27,34,0.5); border-radius: 16px; border: 1px dashed rgba(255,255,255,0.1);">
          <div style="font-size: 48px; margin-bottom: 16px;">📹</div>
          <div style="font-size: 18px; font-weight: 600; margin-bottom: 8px;">Aucune caméra configurée</div>
          <div style="color: #8b949e; margin-bottom: 24px; max-width: 480px; margin-left: auto; margin-right: auto;">
            Ajoutez votre première caméra Wi-Fi (YsxLite, A9, RTSP, ONVIF) depuis l'onglet Paramètres sans aucune application mobile.
          </div>
          <button class="btn-primary" id="btn-goto-settings">Lancer l'appairage</button>
        </div>
      `;
    }

    return `
      <div class="camera-grid">
        ${this._cameras
          .map((cam, idx) => {
            const isLive = this._liveCameras.has(cam.id);
            const statusClass = cam.status || "offline";
            const snapUrl = isLive
              ? `/api/domolink_camera/stream/${cam.id}`
              : `/api/domolink_camera/snapshot/${cam.id}?t=${cam.snapshot_timestamp || Date.now()}`;

            return `
            <div class="camera-card" 
                 draggable="true" 
                 data-id="${cam.id}" 
                 data-index="${idx}">
              
              <!-- Card Header -->
              <div class="card-header">
                <div class="card-title-box">
                  <div class="status-dot ${isLive ? "streaming" : statusClass}"></div>
                  <div class="card-name">${cam.name}</div>
                  <span class="driver-badge">${cam.driver === "ysxlite_pppp" ? "YsxLite" : "RTSP"}</span>
                </div>
                <div style="font-size: 12px; color: #8b949e; cursor: grab;" title="Glisser pour réorganiser">⠿</div>
              </div>

              <!-- Viewport with Image/Live Stream -->
              <div class="viewport">
                <img src="${snapUrl}" alt="${cam.name}" loading="lazy" />

                <!-- Rollover Hover Tooltip -->
                <div class="rollover-tooltip">
                  <strong>${cam.name}</strong> (${cam.host || "IP non assignée"})<br/>
                  ${cam.description ? cam.description : "<i>Aucune description renseignée.</i>"}
                </div>

                <!-- Live Button -->
                <button class="live-btn ${isLive ? "active" : ""}" data-cam-id="${cam.id}">
                  ${isLive ? "🔴 EN DIRECT" : "▶ LIVE"}
                </button>

                <!-- Snapshot Time badge -->
                <div class="time-badge">
                  ${isLive ? "Flux continu" : this._formatTime(cam.snapshot_timestamp)}
                </div>
              </div>

              <!-- Bottom Interactive Banner (Linked Entities) -->
              <div class="bottom-banner">
                ${
                  cam.linked_entities && cam.linked_entities.length > 0
                    ? cam.linked_entities
                        .map((entId) => {
                          const stateObj = this._hass ? this._hass.states[entId] : null;
                          const domain = entId.split(".")[0];
                          const icon = this._getEntityIcon(domain);
                          const friendly = stateObj ? stateObj.attributes.friendly_name || entId : entId;
                          const stateVal = stateObj ? stateObj.state : "N/A";
                          const unit = stateObj?.attributes.unit_of_measurement || "";
                          const isActive = stateVal === "on";

                          return `
                        <div class="entity-badge ${isActive ? "active" : ""}" data-entity-id="${entId}" title="${friendly} (${entId})">
                          <span class="badge-icon">${icon}</span>
                          <span class="badge-name">${friendly}</span>
                          <span class="badge-state">${stateVal} ${unit}</span>
                        </div>
                      `;
                        })
                        .join("")
                    : `<span class="banner-empty-msg">Aucune entité liée (ajoutez switchs/capteurs dans les réglages)</span>`
                }
              </div>

            </div>
          `;
          })
          .join("")}
      </div>
    `;
  }

  _renderSettings() {
    return `
      <div class="settings-container">
        <!-- Section 1: Autonomous Wi-Fi Pairing -->
        <div class="settings-card">
          <h3><span>📡</span> Appairage Wi-Fi Autonome (Sans Application Mobile)</h3>
          <p style="color: #8b949e; font-size: 13px; margin: 0 0 16px 0;">
            Connectez vos caméras Wi-Fi (YsxLite, A9, X5, PPPP) directement à votre réseau domestique.
          </p>

          <div style="background: rgba(13, 17, 23, 0.6); padding: 14px; border-radius: 8px; border-left: 3px solid #3b82f6; margin-bottom: 16px; font-size: 13px; line-height: 1.5;">
            <strong>Procédure rapide :</strong><br/>
            1. Allumez la caméra (la LED clignote en bleu = mode Point d'accès).<br/>
            2. Connectez temporairement votre appareil au Wi-Fi de la caméra (ex: <i>AYS-...</i> ou <i>ACCQ-...</i>).<br/>
            3. Renseignez ci-dessous le nom (SSID) et le mot de passe de votre box Wi-Fi, puis cliquez sur <strong>Lancer l'appairage</strong>.
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label for="pair-ssid">SSID de votre Box / Routeur Wi-Fi</label>
              <input type="text" id="pair-ssid" class="form-input" placeholder="Ex: MonReseauWifi" />
            </div>

            <div class="form-group">
              <label for="pair-pass">Mot de passe du Wi-Fi</label>
              <input type="password" id="pair-pass" class="form-input" placeholder="••••••••" />
            </div>

            <div class="form-group">
              <label for="pair-ap-ip">IP par défaut de la caméra en mode AP</label>
              <input type="text" id="pair-ap-ip" class="form-input" value="192.168.1.254" />
            </div>
          </div>

          <div style="margin-top: 16px; display: flex; gap: 12px; align-items: center;">
            <button class="btn-primary" id="btn-start-pairing" ${this._pairingActive ? "disabled" : ""}>
              ${this._pairingActive ? "⏳ Appairage en cours..." : "🚀 Lancer l'appairage"}
            </button>
            <button class="btn-secondary" id="btn-scan-lan">
              🔍 Scanner le réseau local (UDP 32108)
            </button>
          </div>

          ${
            this._pairingLogs && this._pairingLogs.length > 0
              ? `
            <div class="pairing-logs">
              ${this._pairingLogs.map((l) => `<div>> ${l}</div>`).join("")}
            </div>
          `
              : ""
          }

          ${
            this._scanResults && this._scanResults.length > 0
              ? `
            <div class="discovered-list">
              <div style="font-weight: 600; font-size: 14px; color: #4ade80;">Caméras détectées :</div>
              ${this._scanResults
                .map(
                  (dev) => `
                <div class="discovered-item">
                  <div>
                    <strong>${dev.model}</strong> (${dev.host}:${dev.port})
                    <div style="font-size: 11px; color: #8b949e;">ID: ${dev.device_id || "N/A"}</div>
                  </div>
                  <button class="btn-primary btn-add-discovered" data-host="${dev.host}">+ Ajouter cette caméra</button>
                </div>
              `
                )
                .join("")}
            </div>
          `
              : ""
          }
        </div>

        <!-- Section 2: Camera Configuration & Linked Entities -->
        <div class="settings-card">
          <h3><span>🛠️</span> Configuration des Caméras & Entités Associées</h3>
          <p style="color: #8b949e; font-size: 13px; margin: 0 0 16px 0;">
            Renommez vos caméras, ajustez leur description (affichée en rollover au survol) et liez des switchs/capteurs Home Assistant.
          </p>

          <table class="camera-edit-table">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Description (Rollover)</th>
                <th>Adresse IP</th>
                <th>Modèle / Protocole</th>
                <th>Entités liées (Bandeau bas)</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${
                this._cameras.length === 0
                  ? `<tr><td colspan="6" style="text-align: center; color: #8b949e;">Aucune caméra.</td></tr>`
                  : this._cameras
                      .map(
                        (cam) => `
                    <tr>
                      <td>
                        <input type="text" class="form-input cam-input-name" data-id="${cam.id}" value="${cam.name}" style="width: 140px;" />
                      </td>
                      <td>
                        <input type="text" class="form-input cam-input-desc" data-id="${cam.id}" value="${cam.description || ""}" placeholder="Ex: Salon grand angle" style="width: 200px;" />
                      </td>
                      <td>
                        <input type="text" class="form-input cam-input-host" data-id="${cam.id}" value="${cam.host}" style="width: 130px;" />
                      </td>
                      <td>
                        <select class="form-select cam-input-driver" data-id="${cam.id}">
                          <option value="ysxlite_pppp" ${cam.driver === "ysxlite_pppp" ? "selected" : ""}>YsxLite PPPP</option>
                          <option value="generic_rtsp" ${cam.driver === "generic_rtsp" ? "selected" : ""}>RTSP / ONVIF</option>
                        </select>
                      </td>
                      <td>
                        <select multiple class="form-select cam-input-entities" data-id="${cam.id}" style="height: 60px; width: 220px; font-size: 11px;">
                          ${this._availableEntities
                            .map((e) => {
                              const isSelected = cam.linked_entities && cam.linked_entities.includes(e.entity_id);
                              return `<option value="${e.entity_id}" ${isSelected ? "selected" : ""}>${e.name} (${e.entity_id})</option>`;
                            })
                            .join("")}
                        </select>
                      </td>
                      <td>
                        <div style="display: flex; gap: 8px;">
                          <button class="btn-primary btn-save-cam" data-id="${cam.id}" title="Enregistrer">💾</button>
                          <button class="btn-danger btn-del-cam" data-id="${cam.id}" title="Supprimer">🗑️</button>
                        </div>
                      </td>
                    </tr>
                  `
                      )
                      .join("")
              }
            </tbody>
          </table>

          <div style="margin-top: 20px;">
            <button class="btn-secondary" id="btn-add-manual-cam">+ Ajouter manuellement une caméra</button>
          </div>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    // Tabs
    const tabCams = this.shadowRoot.querySelector("#tab-cameras");
    const tabSets = this.shadowRoot.querySelector("#tab-settings");
    if (tabCams) {
      tabCams.onclick = () => {
        this._activeTab = "cameras";
        this.render();
      };
    }
    if (tabSets) {
      tabSets.onclick = () => {
        this._activeTab = "settings";
        this.render();
      };
    }

    const gotoSets = this.shadowRoot.querySelector("#btn-goto-settings");
    if (gotoSets) {
      gotoSets.onclick = () => {
        this._activeTab = "settings";
        this.render();
      };
    }

    // Save Layout Button
    const saveLayoutBtn = this.shadowRoot.querySelector("#btn-save-layout");
    if (saveLayoutBtn) {
      saveLayoutBtn.onclick = () => this._saveLayoutOrder();
    }

    // Live Toggles
    const liveBtns = this.shadowRoot.querySelectorAll(".live-btn");
    liveBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this._toggleLive(btn.dataset.camId);
      };
    });

    // Entity Badges Toggle
    const entityBadges = this.shadowRoot.querySelectorAll(".entity-badge");
    entityBadges.forEach((badge) => {
      badge.onclick = (e) => {
        e.stopPropagation();
        this._toggleEntity(badge.dataset.entityId);
      };
    });

    // Drag and Drop on Cards
    const cards = this.shadowRoot.querySelectorAll(".camera-card");
    cards.forEach((card) => {
      const idx = parseInt(card.dataset.index, 10);
      card.ondragstart = (e) => this._handleDragStart(e, idx);
      card.ondragover = (e) => this._handleDragOver(e);
      card.ondragenter = (e) => this._handleDragEnter(e);
      card.ondragleave = (e) => this._handleDragLeave(e);
      card.ondrop = (e) => this._handleDrop(e, idx);
      card.ondragend = (e) => this._handleDragEnd(e);
    });

    // Pairing buttons
    const startPairBtn = this.shadowRoot.querySelector("#btn-start-pairing");
    if (startPairBtn) {
      startPairBtn.onclick = () => this._startPairing();
    }

    const scanLanBtn = this.shadowRoot.querySelector("#btn-scan-lan");
    if (scanLanBtn) {
      scanLanBtn.onclick = () => this._scanLocalNetwork();
    }

    const addDiscoveredBtns = this.shadowRoot.querySelectorAll(".btn-add-discovered");
    addDiscoveredBtns.forEach((btn) => {
      btn.onclick = () => {
        const dev = this._scanResults.find((d) => d.host === btn.dataset.host);
        if (dev) this._addDiscoveredCamera(dev);
      };
    });

    // Save individual camera
    const saveCamBtns = this.shadowRoot.querySelectorAll(".btn-save-cam");
    saveCamBtns.forEach((btn) => {
      btn.onclick = () => {
        const id = btn.dataset.id;
        const nameInp = this.shadowRoot.querySelector(`.cam-input-name[data-id="${id}"]`);
        const descInp = this.shadowRoot.querySelector(`.cam-input-desc[data-id="${id}"]`);
        const hostInp = this.shadowRoot.querySelector(`.cam-input-host[data-id="${id}"]`);
        const driverInp = this.shadowRoot.querySelector(`.cam-input-driver[data-id="${id}"]`);
        const entSelect = this.shadowRoot.querySelector(`.cam-input-entities[data-id="${id}"]`);

        const selectedEntities = Array.from(entSelect ? entSelect.selectedOptions : []).map((o) => o.value);

        const current = this._cameras.find((c) => c.id === id) || {};
        const updated = {
          ...current,
          id: id,
          name: nameInp ? nameInp.value.trim() : current.name,
          description: descInp ? descInp.value.trim() : "",
          host: hostInp ? hostInp.value.trim() : current.host,
          driver: driverInp ? driverInp.value : current.driver,
          linked_entities: selectedEntities,
        };

        this._saveCamera(updated);
      };
    });

    // Delete camera
    const delCamBtns = this.shadowRoot.querySelectorAll(".btn-del-cam");
    delCamBtns.forEach((btn) => {
      btn.onclick = () => this._deleteCamera(btn.dataset.id);
    });

    // Add manual camera
    const addManualBtn = this.shadowRoot.querySelector("#btn-add-manual-cam");
    if (addManualBtn) {
      addManualBtn.onclick = () => {
        const newCam = {
          name: "Nouvelle Caméra",
          description: "Caméra configurée manuellement",
          driver: "ysxlite_pppp",
          host: "192.168.1.100",
          port: 32108,
          linked_entities: [],
        };
        this._saveCamera(newCam);
      };
    }
  }
}

customElements.define("domolink-camera-panel", DomolinkCameraPanel);
