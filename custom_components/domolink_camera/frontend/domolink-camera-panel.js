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
    this._scanCompatible = [];
    this._scanIncompatible = [];
    this._scanSummary = null;
    this._isScanning = false;
    this._selectedCamera = null;
    this._refreshTimer = null;
    this._toastMsg = null;
    this._boxInfo = null;
    this._tvChannels = [];
    this._selectedChannel = null;
    this._tvSearch = "";
    this._tvFilter = "all";
    this._hlsPlayer = null;
    this._isLoadingTv = false;
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
  _appendLog(msg) {
    const time = new Date().toLocaleTimeString("fr-FR", { hour12: false });
    const formatted = `[${time}] ${msg}`;
    if (!this._pairingLogs) this._pairingLogs = [];
    this._pairingLogs.push(formatted);
    if (this._pairingLogs.length > 80) this._pairingLogs.shift();
    this._updatePairingLogs();
  }

  _updatePairingLogs() {
    const logBox = this.shadowRoot.querySelector("#pairing-logs") || this.shadowRoot.querySelector(".pairing-logs");
    if (logBox) {
      logBox.innerHTML = this._pairingLogs.map((l) => `<div>> ${l}</div>`).join("");
      logBox.scrollTop = logBox.scrollHeight;
    }
  }

  async _startPairing() {
    const ssidInput = this.shadowRoot.querySelector("#pair-ssid");
    const passInput = this.shadowRoot.querySelector("#pair-pass");
    const apIpInput = this.shadowRoot.querySelector("#pair-ap-ip");

    const ssid = ssidInput ? ssidInput.value.trim() : "";
    const pass = passInput ? passInput.value.trim() : "";
    const apIp = apIpInput ? apIpInput.value.trim() || "192.168.10.1" : "192.168.10.1";

    if (!ssid) {
      this._showToast("Veuillez saisir le SSID de votre réseau Wi-Fi.");
      this._appendLog("⚠️ [VALIDATION] Nom du réseau Wi-Fi (SSID) manquant.");
      return;
    }

    this._pairingActive = true;
    this._pairingLogs = [];
    this._appendLog(`🚀 [DÉMARRAGE] Assistant d'appairage lancé pour le réseau '${ssid}'...`);
    this._appendLog(`📋 [VÉRIFICATION] Longueur SSID=${ssid.length} car. | Longueur clé=${pass.length} car. | IP cible=${apIp}`);

    if (apIp === "192.168.1.254" || apIp === "192.168.1.1") {
      this._appendLog(`⚠️ [ATTENTION] L'adresse '${apIp}' est l'adresse de votre Freebox / Box Internet !`);
      this._appendLog("💡 Assurez-vous d'avoir connecté votre PC ou smartphone au Wi-Fi propre de la caméra (ex: AYS-xxx, ACCQ-xxx) avant de lancer.");
    }

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
            if (st.logs && st.logs.length > 0) {
              this._pairingLogs = st.logs;
            }
            if (!st.active) {
              clearInterval(pollTimer);
              this._pairingActive = false;
              if (st.discovered && st.discovered.length > 0) {
                this._scanResults = st.discovered;
                this._appendLog(`🎉 [SUCCÈS] Caméra découverte et appairée avec succès : ${st.discovered[0].name} (${st.discovered[0].host}) !`);
                this._showToast("Caméra appairée avec succès !");
              } else {
                this._appendLog("⚠️ [FIN DE TENTATIVE] Aucune nouvelle caméra n'a rejoint le réseau.");
              }
              this.render();
            } else {
              this._updatePairingLogs();
            }
          }
        } catch (e) {
          clearInterval(pollTimer);
          this._pairingActive = false;
          this._appendLog(`❌ [ERREUR APPAIRAGE] ${e.message || e}`);
          this.render();
        }
      }, 2000);
    } catch (e) {
      this._pairingActive = false;
      this._appendLog(`❌ [ÉCHEC DÉMARRAGE] ${e.message || e}`);
      this._showToast("Échec du démarrage de l'appairage");
      this.render();
    }
  }

  async _scanLocalNetwork() {
    this._isScanning = true;
    this._appendLog("🔍 [SCAN RÉSEAU] Démarrage du scan multi-sources (Local LAN & Entités HA)...");
    this._appendLog("📡 [LAN] Envoi broadcast UDP sur le port 32108 pour détecter caméras PPPP / YsxLite...");
    this._appendLog("🌐 [LAN] Analyse de la table ARP et test de réponse RTSP port 554...");
    this._appendLog("🏠 [HA] Inspection des comptes et entités caméras enregistrées dans Home Assistant...");
    this._showToast("Scan du réseau en cours (UDP 32108, RTSP 554 & Entités HA)...");
    this.render();

    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/scan_local" });
      this._isScanning = false;
      if (resp) {
        this._scanCompatible = resp.compatible || [];
        this._scanIncompatible = resp.incompatible || [];
        this._scanSummary = resp.summary || {
          total: this._scanCompatible.length + this._scanIncompatible.length,
          compatible_count: this._scanCompatible.length,
          incompatible_count: this._scanIncompatible.length,
        };
        this._scanResults = this._scanCompatible;

        this._appendLog(`✅ [SCAN TERMINÉ] ${this._scanCompatible.length} caméra(s) compatible(s) trouvée(s) et prête(s) à l'ajout !`);
        if (this._scanIncompatible.length > 0) {
          this._appendLog(`ℹ️ [INFO] ${this._scanIncompatible.length} entité(s) secondaire(s) ou distantes filtrées.`);
        }

        this._showToast(
          `Scan terminé : ${this._scanCompatible.length} caméra(s) prête(s) à l'intégration !`
        );
        this.render();
      }
    } catch (e) {
      this._isScanning = false;
      this._appendLog(`❌ [ERREUR SCAN] Échec de l'analyse : ${e.message || e}`);
      this._showToast("Erreur lors du scan du réseau");
      this.render();
    }
  }

  async _addDiscoveredCamera(dev) {
    this._appendLog(`📥 [INTÉGRATION] Ajout de la caméra '${dev.name}' en cours...`);
    this._appendLog(`⚙️ [CONFIGURATION] Pilote assigné : ${dev.driver} (Cible : ${dev.host})`);

    const newCam = {
      name: dev.name || dev.model || "Caméra Wi-Fi",
      description: dev.details || "Caméra intégrée",
      driver: dev.driver || "ha_proxy",
      host: dev.host,
      port: dev.port || (dev.driver === "generic_rtsp" ? 554 : 32108),
      linked_entities: [],
    };

    try {
      this._appendLog("📸 [TEST FLUX] Vérification de l'acquisition de snapshot et initialisation du pilote...");
      await this._saveCamera(newCam);

      dev.already_added = true;
      this._appendLog(`✅ [SUCCÈS] Caméra '${dev.name}' ajoutée à DomoLink ! Retrouvez-la dans l'onglet Caméras.`);
      this._showToast(`Caméra ${dev.name} ajoutée avec succès !`);
      await this._fetchCameras();
      this.render();
    } catch (err) {
      this._appendLog(`❌ [ERREUR INTÉGRATION] Impossible d'ajouter '${dev.name}' : ${err.message || err}`);
      this._showToast(`Erreur lors de l'ajout : ${err.message || err}`);
    }
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

        /* Pairing Logs Terminal Card */
        .terminal-card {
          margin-top: 18px;
          background: #060a12;
          border: 1px solid rgba(74, 222, 128, 0.3);
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
        }

        .terminal-header {
          background: rgba(15, 23, 42, 0.95);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding: 10px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .terminal-dots {
          display: flex;
          gap: 6px;
        }

        .terminal-dots span {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          display: inline-block;
        }

        .dot-red { background: #ef4444; }
        .dot-yellow { background: #f59e0b; }
        .dot-green { background: #10b981; }

        .terminal-title {
          font-size: 12px;
          font-family: 'SF Mono', Monaco, Consolas, monospace;
          color: #94a3b8;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .terminal-status-badge {
          background: rgba(16, 185, 129, 0.2);
          color: #34d399;
          font-size: 10px;
          padding: 2px 6px;
          border-radius: 4px;
        }

        .btn-clear-terminal {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #94a3b8;
          font-size: 11px;
          padding: 3px 10px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .btn-clear-terminal:hover {
          color: #ffffff;
          border-color: #3b82f6;
          background: rgba(59, 130, 246, 0.15);
        }

        .pairing-logs {
          background: #040810;
          padding: 14px 16px;
          font-family: 'SF Mono', Monaco, Consolas, monospace;
          font-size: 12px;
          line-height: 1.6;
          color: #4ade80;
          min-height: 120px;
          max-height: 240px;
          overflow-y: auto;
          white-space: pre-wrap;
          word-break: break-word;
        }

        /* Discovered List & Categorized Scan */
        .scan-summary-bar {
          display: flex;
          gap: 12px;
          margin-top: 16px;
          flex-wrap: wrap;
        }

        .summary-chip {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 8px 14px;
          border-radius: 20px;
          font-size: 13px;
          font-weight: 600;
        }

        .summary-chip.chip-compatible {
          background: rgba(16, 185, 129, 0.15);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .summary-chip.chip-incompatible {
          background: rgba(245, 158, 11, 0.15);
          color: #fbbf24;
          border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .scan-category-section {
          margin-top: 20px;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .scan-category-header {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 600;
          padding-bottom: 6px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }

        .discovered-list {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }

        .discovered-item {
          background: rgba(13, 17, 23, 0.7);
          border-radius: 10px;
          padding: 14px 16px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          transition: transform 0.15s, border-color 0.15s;
        }

        .discovered-item.compatible {
          border: 1px solid rgba(16, 185, 129, 0.35);
        }

        .discovered-item.compatible:hover {
          border-color: rgba(16, 185, 129, 0.6);
          transform: translateY(-1px);
        }

        .discovered-item.incompatible {
          border: 1px solid rgba(245, 158, 11, 0.3);
          background: rgba(24, 20, 16, 0.6);
        }

        .badge-protocol {
          display: inline-block;
          font-size: 11px;
          font-weight: 600;
          padding: 2px 8px;
          border-radius: 6px;
          margin-right: 6px;
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }

        .badge-protocol.badge-green {
          background: rgba(16, 185, 129, 0.2);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.4);
        }

        .badge-protocol.badge-orange {
          background: rgba(245, 158, 11, 0.2);
          color: #fbbf24;
          border: 1px solid rgba(245, 158, 11, 0.4);
        }

        .badge-protocol.badge-gray {
          background: rgba(148, 163, 184, 0.15);
          color: #94a3b8;
          border: 1px solid rgba(148, 163, 184, 0.3);
        }

        .badge-already-added {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: 12px;
          font-weight: 600;
          color: #34d399;
          background: rgba(16, 185, 129, 0.15);
          padding: 6px 12px;
          border-radius: 6px;
          border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .reason-box {
          margin-top: 6px;
          padding: 8px 12px;
          background: rgba(245, 158, 11, 0.08);
          border-left: 3px solid #f59e0b;
          border-radius: 0 6px 6px 0;
          font-size: 12px;
          color: #e2e8f0;
          line-height: 1.4;
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

        /* TV Section Styles */
        .tv-container {
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        .box-info-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(59, 130, 246, 0.3);
          border-radius: 16px;
          padding: 18px 24px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
          backdrop-filter: blur(20px);
        }

        .box-info-left {
          display: flex;
          align-items: center;
          gap: 16px;
        }

        .box-icon {
          font-size: 32px;
          background: rgba(59, 130, 246, 0.15);
          width: 56px;
          height: 56px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 14px;
          border: 1px solid rgba(59, 130, 246, 0.3);
        }

        .box-title {
          font-size: 17px;
          font-weight: 700;
          color: #f0f6fc;
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .box-badge {
          background: #10b981;
          color: #064e3b;
          font-size: 11px;
          font-weight: 700;
          padding: 3px 9px;
          border-radius: 12px;
        }

        .box-desc {
          font-size: 13px;
          color: #8b949e;
          margin-top: 4px;
        }

        .tv-player-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          overflow: hidden;
          box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
          backdrop-filter: blur(20px);
        }

        .tv-player-header {
          padding: 14px 20px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: rgba(13, 17, 23, 0.8);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }

        .tv-channel-title {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .tv-ch-num {
          background: #3b82f6;
          color: #ffffff;
          font-weight: 800;
          font-size: 13px;
          padding: 2px 8px;
          border-radius: 6px;
        }

        .tv-ch-name {
          font-size: 18px;
          font-weight: 700;
          color: #ffffff;
        }

        .tv-live-tag {
          background: rgba(239, 68, 68, 0.2);
          color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.4);
          font-size: 11px;
          font-weight: 700;
          padding: 3px 8px;
          border-radius: 6px;
          display: flex;
          align-items: center;
          gap: 5px;
        }

        .tv-header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .btn-tv-action {
          background: rgba(255, 255, 255, 0.08);
          color: #f0f6fc;
          border: 1px solid rgba(255, 255, 255, 0.15);
          padding: 7px 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          transition: all 0.2s ease;
        }

        .btn-tv-action:hover {
          background: rgba(59, 130, 246, 0.2);
          border-color: #3b82f6;
          color: #60a5fa;
        }

        .btn-tv-action.primary {
          background: #3b82f6;
          color: #ffffff;
          border: none;
        }

        .btn-tv-action.primary:hover {
          background: #2563eb;
        }

        .tv-player-wrapper {
          position: relative;
          background: #000000;
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          min-height: 380px;
          max-height: 560px;
        }

        .tv-player-wrapper video {
          width: 100%;
          height: auto;
          max-height: 560px;
          display: block;
        }

        /* Fullscreen handling */
        .tv-player-wrapper:fullscreen {
          width: 100vw;
          height: 100vh;
          max-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #000000;
        }

        .tv-player-wrapper:fullscreen video {
          max-height: 100vh;
          width: 100%;
          height: 100%;
          object-fit: contain;
        }

        /* TV Channel Selector */
        .tv-selector-card {
          background: rgba(22, 27, 34, 0.85);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 24px;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
          backdrop-filter: blur(20px);
        }

        .tv-selector-header {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          margin-bottom: 20px;
        }

        .tv-search-box {
          position: relative;
          min-width: 280px;
          flex: 1;
          max-width: 400px;
        }

        .tv-search-input {
          width: 100%;
          padding: 10px 14px 10px 38px;
          background: rgba(13, 17, 23, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          color: #f0f6fc;
          font-size: 14px;
          outline: none;
          box-sizing: border-box;
          transition: border-color 0.2s ease;
        }

        .tv-search-input:focus {
          border-color: #3b82f6;
        }

        .tv-search-icon {
          position: absolute;
          left: 12px;
          top: 50%;
          transform: translateY(-50%);
          font-size: 14px;
          color: #8b949e;
        }

        .category-pills {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }

        .category-pill {
          background: rgba(255, 255, 255, 0.05);
          color: #8b949e;
          border: 1px solid rgba(255, 255, 255, 0.08);
          padding: 6px 14px;
          border-radius: 20px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .category-pill:hover {
          background: rgba(255, 255, 255, 0.1);
          color: #f0f6fc;
        }

        .category-pill.active {
          background: #3b82f6;
          color: #ffffff;
          border-color: #3b82f6;
        }

        .channel-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 16px;
          max-height: 480px;
          overflow-y: auto;
          padding-right: 6px;
        }

        .channel-card {
          background: rgba(13, 17, 23, 0.6);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 14px;
          display: flex;
          align-items: center;
          gap: 12px;
          cursor: pointer;
          transition: all 0.2s ease;
          position: relative;
        }

        .channel-card:hover {
          background: rgba(59, 130, 246, 0.1);
          border-color: rgba(59, 130, 246, 0.4);
          transform: translateY(-2px);
        }

        .channel-card.active {
          background: rgba(59, 130, 246, 0.2);
          border-color: #3b82f6;
          box-shadow: 0 0 16px rgba(59, 130, 246, 0.3);
        }

        .channel-logo-box {
          width: 44px;
          height: 44px;
          background: rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          flex-shrink: 0;
        }

        .channel-logo-img {
          max-width: 38px;
          max-height: 38px;
          object-fit: contain;
        }

        .channel-details {
          flex: 1;
          min-width: 0;
        }

        .channel-name {
          font-weight: 600;
          font-size: 14px;
          color: #f0f6fc;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .channel-sub {
          font-size: 11px;
          color: #8b949e;
          margin-top: 2px;
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
            <button class="tab-btn ${this._activeTab === "tv" ? "active" : ""}" id="tab-tv">
              <span>📺</span> TV en Direct
            </button>
            <button class="tab-btn ${this._activeTab === "settings" ? "active" : ""}" id="tab-settings">
              <span>⚙️</span> Paramètres & Appairage
            </button>
          </div>
        </header>

        <!-- Main Content Area -->
        ${
          this._activeTab === "cameras"
            ? this._renderCamerasGrid()
            : this._activeTab === "tv"
            ? this._renderTvSection()
            : this._renderSettings()
        }

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

  // --- TV Section & Player ---
  async _fetchTvData() {
    if (this._isLoadingTv) return;
    this._isLoadingTv = true;
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/get_tv_channels" });
      if (resp) {
        this._boxInfo = resp.box || null;
        this._tvChannels = resp.channels || [];
        if (!this._selectedChannel && this._tvChannels.length > 0) {
          this._selectedChannel = this._tvChannels[0];
        }
        this.render();
        if (this._selectedChannel) {
          this._playChannelStream(this._selectedChannel);
        }
      }
    } catch (err) {
      console.error("Error loading TV channels:", err);
      this._showToast("Erreur lors de la détection de la Box ou des flux TV");
    } finally {
      this._isLoadingTv = false;
    }
  }

  _ensureHlsJs() {
    if (window.Hls) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://cdn.jsdelivr.net/npm/hls.js@1.5.8/dist/hls.min.js";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Impossible de charger le moteur HLS"));
      document.head.appendChild(script);
    });
  }

  async _playChannelStream(channel) {
    if (!channel) return;
    this._selectedChannel = channel;
    const video = this.shadowRoot.querySelector("#tv-video-player");
    if (!video) return;

    this._showToast(`Chargement du direct : ${channel.name}...`);
    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/get_tv_stream",
        channel_id: channel.id,
      });

      if (!resp || !resp.url) {
        this._showToast(`Flux indisponible pour ${channel.name}`);
        return;
      }

      const streamUrl = resp.url;
      const isHls = streamUrl.includes(".m3u8") || resp.format === "hls";

      if (isHls) {
        if (video.canPlayType("application/vnd.apple.mpegurl")) {
          video.src = streamUrl;
          video.play().catch(() => {});
        } else {
          await this._ensureHlsJs();
          if (window.Hls && window.Hls.isSupported()) {
            if (this._hlsPlayer) {
              this._hlsPlayer.destroy();
            }
            this._hlsPlayer = new window.Hls({
              enableWorker: true,
              lowLatencyMode: true,
            });
            this._hlsPlayer.loadSource(streamUrl);
            this._hlsPlayer.attachMedia(video);
            this._hlsPlayer.on(window.Hls.Events.MANIFEST_PARSED, () => {
              video.play().catch(() => {});
            });
          } else {
            video.src = streamUrl;
            video.play().catch(() => {});
          }
        }
      } else {
        video.src = streamUrl;
        video.play().catch(() => {});
      }
    } catch (err) {
      console.error("TV stream error:", err);
      this._showToast(`Erreur flux TV: ${err.message || err}`);
    }
  }

  _toggleFullscreen() {
    const wrapper = this.shadowRoot.querySelector("#tv-player-wrapper");
    if (!wrapper) return;

    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
      if (wrapper.requestFullscreen) {
        wrapper.requestFullscreen();
      } else if (wrapper.webkitRequestFullscreen) {
        wrapper.webkitRequestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
  }

  async _togglePip() {
    const video = this.shadowRoot.querySelector("#tv-video-player");
    if (!video) return;
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
      } else if (video.requestPictureInPicture) {
        await video.requestPictureInPicture();
      }
    } catch (e) {
      console.warn("PiP error:", e);
    }
  }

  async _pinCurrentChannel() {
    if (!this._selectedChannel) return;
    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/pin_tv_camera",
        channel_id: this._selectedChannel.id,
      });
      if (resp && resp.success) {
        this._showToast(`Chaîne ${this._selectedChannel.name} ajoutée à vos caméras !`);
        await this._fetchCameras();
      }
    } catch (err) {
      this._showToast(`Erreur lors de l'épinglage: ${err.message || err}`);
    }
  }

  _renderTvSection() {
    if (!this._boxInfo && !this._isLoadingTv) {
      setTimeout(() => this._fetchTvData(), 10);
      return `
        <div style="text-align: center; padding: 60px 20px;">
          <div class="loading-spinner"></div>
          <div style="margin-top: 16px; color: #8b949e;">Détection de votre Box Internet et chargement des flux TV...</div>
        </div>
      `;
    }

    const box = this._boxInfo || {
      brand: "free",
      name: "Freebox Server",
      model: "Freebox Ultra",
      badge: "Multiposte Actif ⚡",
      description: "Accès direct aux flux vidéo Multiposte RTSP locaux en qualité maximale.",
    };

    const isFree = box.brand === "free";
    const boxIcon = isFree ? "⚡" : box.brand === "orange" ? "🍊" : box.brand === "sfr" ? "🔴" : box.brand === "bouygues" ? "🔷" : "🌐";

    const ch = this._selectedChannel || (this._tvChannels.length > 0 ? this._tvChannels[0] : null);

    const filteredChannels = (this._tvChannels || []).filter((c) => {
      const matchFilter = this._tvFilter === "all" || c.category === this._tvFilter;
      const matchSearch =
        !this._tvSearch ||
        c.name.toLowerCase().includes(this._tvSearch.toLowerCase()) ||
        (c.num && String(c.num).includes(this._tvSearch));
      return matchFilter && matchSearch;
    });

    const categories = ["all", "Généraliste", "Information", "Culture", "Jeunesse", "Sport", "Musique", "Régionale"];

    return `
      <div class="tv-container">
        <!-- Box Identification Banner -->
        <div class="box-info-card">
          <div class="box-info-left">
            <div class="box-icon">${boxIcon}</div>
            <div>
              <div class="box-title">
                ${box.name}
                <span class="box-badge">${box.badge || "Connecté"}</span>
              </div>
              <div class="box-desc">${box.description}</div>
            </div>
          </div>
          <div style="text-align: right; color: #8b949e; font-size: 13px;">
            <span>${this._tvChannels.length} chaîne(s) disponible(s)</span>
          </div>
        </div>

        <!-- TV Player Card with Fullscreen & Controls -->
        <div class="tv-player-card">
          <div class="tv-player-header">
            <div class="tv-channel-title">
              ${ch && ch.num ? `<span class="tv-ch-num">CH ${ch.num}</span>` : ""}
              <span class="tv-ch-name">${ch ? ch.name : "Aucune chaîne sélectionnée"}</span>
              <span class="tv-live-tag">🔴 EN DIRECT</span>
            </div>
            <div class="tv-header-actions">
              <button class="btn-tv-action" id="btn-pin-channel" title="Ajouter cette chaîne dans la grille de vos caméras">
                📌 Épingler aux Caméras
              </button>
              <button class="btn-tv-action" id="btn-pip-player" title="Incrustation d'image (Picture-in-Picture)">
                🪟 PiP
              </button>
              <button class="btn-tv-action primary" id="btn-fullscreen-player" title="Passer en plein écran">
                ⛶ Plein Écran
              </button>
            </div>
          </div>

          <div class="tv-player-wrapper" id="tv-player-wrapper">
            <video id="tv-video-player" playsinline autoplay controls></video>
          </div>
        </div>

        <!-- Channel Selector -->
        <div class="tv-selector-card">
          <div class="tv-selector-header">
            <div class="category-pills">
              ${categories
                .map(
                  (cat) => `
                <button class="category-pill ${this._tvFilter === cat ? "active" : ""}" data-category="${cat}">
                  ${cat === "all" ? "Toutes les chaînes" : cat}
                </button>
              `
                )
                .join("")}
            </div>

            <div class="tv-search-box">
              <span class="tv-search-icon">🔍</span>
              <input type="text" class="tv-search-input" id="tv-search-input" placeholder="Rechercher une chaîne ou un numéro..." value="${this._tvSearch}" />
            </div>
          </div>

          <div class="channel-grid">
            ${
              filteredChannels.length > 0
                ? filteredChannels
                    .map((item) => {
                      const isActive = ch && ch.id === item.id;
                      return `
                  <div class="channel-card ${isActive ? "active" : ""}" data-channel-id="${item.id}">
                    <div class="channel-logo-box">
                      ${
                        item.logo
                          ? `<img src="${item.logo}" class="channel-logo-img" alt="${item.name}" />`
                          : `<span style="font-weight: 800; color: #3b82f6;">${item.num || "TV"}</span>`
                      }
                    </div>
                    <div class="channel-details">
                      <div class="channel-name">${item.num ? `${item.num}. ` : ""}${item.name}</div>
                      <div class="channel-sub">${item.category || "Direct"} • ${item.quality || "HD"}</div>
                    </div>
                  </div>
                `;
                    })
                    .join("")
                : `<div style="grid-column: 1 / -1; text-align: center; color: #8b949e; padding: 40px 0;">Aucune chaîne ne correspond à votre recherche.</div>`
            }
          </div>
        </div>
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
              <input type="text" id="pair-ap-ip" class="form-input" value="192.168.10.1" placeholder="Ex: 192.168.10.1 ou 192.168.1.254" />
            </div>
          </div>

          <div style="margin-top: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
            <button class="btn-primary" id="btn-start-pairing" ${this._pairingActive ? "disabled" : ""}>
              ${this._pairingActive ? "⏳ Appairage en cours..." : "🚀 Lancer l'appairage"}
            </button>
            <button class="btn-secondary" id="btn-scan-lan" ${this._isScanning ? "disabled" : ""}>
              ${this._isScanning ? "⏳ Scan en cours..." : "🔍 Scanner le réseau & Détecter les caméras"}
            </button>
          </div>

          <!-- Interactive Live Diagnostic Terminal -->
          <div class="terminal-card">
            <div class="terminal-header">
              <div class="terminal-dots">
                <span class="dot-red"></span>
                <span class="dot-yellow"></span>
                <span class="dot-green"></span>
              </div>
              <div class="terminal-title">
                🖥️ Terminal d'Appairage & Diagnostic en Temps Réel
                <span class="terminal-status-badge">${this._pairingActive ? "⏳ ACTIF" : "🟢 PRÊT"}</span>
              </div>
              <button class="btn-clear-terminal" id="btn-clear-logs" title="Effacer l'historique du terminal">Effacer</button>
            </div>
            <div class="pairing-logs" id="pairing-logs">
              ${
                this._pairingLogs && this._pairingLogs.length > 0
                  ? this._pairingLogs.map((l) => `<div>> ${l}</div>`).join("")
                  : `<div style="color: #6ee7b7; opacity: 0.6;">> En attente d'une action (Appairage, Scan réseau ou Ajout de caméra)...</div>`
              }
            </div>
          </div>

          ${
            this._scanSummary
              ? `
            <div class="scan-summary-bar">
              <span class="summary-chip chip-compatible">
                🟢 ${this._scanCompatible.length} Caméras Compatibles (Protocoles intégrés)
              </span>
              <span class="summary-chip chip-incompatible">
                🟠 ${this._scanIncompatible.length} Caméras Détectées (Protocoles Non Intégrés - Cloud / Propriétaire)
              </span>
            </div>
          `
              : ""
          }

          ${
            this._scanCompatible && this._scanCompatible.length > 0
              ? `
            <div class="scan-category-section">
              <div class="scan-category-header" style="color: #34d399;">
                <span>🟢</span>
                <span>Caméras Compatibles avec DomoLink (YsxLite PPPP, RTSP, ONVIF, MJPEG)</span>
                <span style="font-size: 12px; color: #8b949e; font-weight: normal;">— Flux direct local accessible</span>
              </div>
              <div class="discovered-list">
                ${this._scanCompatible
                  .map(
                    (dev) => `
                  <div class="discovered-item compatible">
                    <div style="flex: 1;">
                      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                        <span class="badge-protocol badge-green">${dev.protocol || dev.driver}</span>
                        <strong style="color: #f0f6fc; font-size: 14px;">${dev.name || dev.model}</strong>
                      </div>
                      <div style="font-size: 12px; color: #8b949e;">
                        IP: <code style="color: #60a5fa;">${dev.host}${dev.port ? `:${dev.port}` : ""}</code>
                        ${dev.model ? ` • Modèle : ${dev.model}` : ""}
                      </div>
                      ${
                        dev.details
                          ? `<div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">${dev.details}</div>`
                          : ""
                      }
                    </div>
                    <div>
                      ${
                        dev.already_added
                          ? `<span class="badge-already-added">✓ Déjà intégrée</span>`
                          : `<button class="btn-primary btn-add-discovered" data-host="${dev.host}">+ Ajouter à DomoLink</button>`
                      }
                    </div>
                  </div>
                `
                  )
                  .join("")}
              </div>
            </div>
          `
              : ""
          }

          ${
            this._scanIncompatible && this._scanIncompatible.length > 0
              ? `
            <div class="scan-category-section" style="margin-top: 24px;">
              <div class="scan-category-header" style="color: #fbbf24;">
                <span>🟠</span>
                <span>Autres Caméras Détectées (Protocoles Non Intégrés - Cloud / Propriétaire)</span>
                <span style="font-size: 12px; color: #8b949e; font-weight: normal;">— Flux fermé ou hébergé dans un cloud distant</span>
              </div>
              <div class="discovered-list">
                ${this._scanIncompatible
                  .map(
                    (dev) => `
                  <div class="discovered-item incompatible">
                    <div style="flex: 1;">
                      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px; flex-wrap: wrap;">
                        <span class="badge-protocol badge-orange">${dev.platform}</span>
                        <span class="badge-protocol badge-gray">${dev.protocol}</span>
                        <strong style="color: #f0f6fc; font-size: 14px;">${dev.name}</strong>
                        ${dev.model ? `<span style="font-size: 12px; color: #8b949e;">(${dev.model})</span>` : ""}
                      </div>
                      <div style="font-size: 12px; color: #8b949e;">
                        Entité HA: <code style="color: #e2e8f0;">${dev.entity_id || dev.host}</code>
                      </div>
                      <div class="reason-box">
                        <strong>⚠️ Raison de non-intégration directe :</strong> ${dev.reason}
                        <div style="margin-top: 4px; font-size: 11px; color: #94a3b8;">
                          💡 <em>Astuce : Vous pouvez associer les interrupteurs ou capteurs de présence de cette caméra dans le bandeau inférieur de vos caméras DomoLink.</em>
                        </div>
                      </div>
                    </div>
                  </div>
                `
                  )
                  .join("")}
              </div>
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
    const tabTv = this.shadowRoot.querySelector("#tab-tv");
    const tabSets = this.shadowRoot.querySelector("#tab-settings");
    if (tabCams) {
      tabCams.onclick = () => {
        this._activeTab = "cameras";
        this.render();
      };
    }
    if (tabTv) {
      tabTv.onclick = () => {
        this._activeTab = "tv";
        this.render();
        if (!this._boxInfo) {
          this._fetchTvData();
        } else if (this._selectedChannel) {
          this._playChannelStream(this._selectedChannel);
        }
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

    const clearLogsBtn = this.shadowRoot.querySelector("#btn-clear-logs");
    if (clearLogsBtn) {
      clearLogsBtn.onclick = () => {
        this._pairingLogs = [];
        this._updatePairingLogs();
      };
    }

    const addDiscoveredBtns = this.shadowRoot.querySelectorAll(".btn-add-discovered");
    addDiscoveredBtns.forEach((btn) => {
      btn.onclick = () => {
        const dev = (this._scanCompatible || this._scanResults || []).find((d) => d.host === btn.dataset.host);
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

    // --- TV Tab Controls & Fullscreen ---
    const fsBtn = this.shadowRoot.querySelector("#btn-fullscreen-player");
    if (fsBtn) {
      fsBtn.onclick = () => this._toggleFullscreen();
    }

    const pipBtn = this.shadowRoot.querySelector("#btn-pip-player");
    if (pipBtn) {
      pipBtn.onclick = () => this._togglePip();
    }

    const pinBtn = this.shadowRoot.querySelector("#btn-pin-channel");
    if (pinBtn) {
      pinBtn.onclick = () => this._pinCurrentChannel();
    }

    const tvVideo = this.shadowRoot.querySelector("#tv-video-player");
    if (tvVideo) {
      tvVideo.ondblclick = () => this._toggleFullscreen();
    }

    // Category pills filter
    const catPills = this.shadowRoot.querySelectorAll(".category-pill");
    catPills.forEach((pill) => {
      pill.onclick = () => {
        this._tvFilter = pill.dataset.category;
        this.render();
      };
    });

    // Search input
    const searchInp = this.shadowRoot.querySelector("#tv-search-input");
    if (searchInp) {
      searchInp.oninput = (e) => {
        this._tvSearch = e.target.value;
        const grid = this.shadowRoot.querySelector(".channel-grid");
        if (grid) {
          const filtered = (this._tvChannels || []).filter((c) => {
            const matchFilter = this._tvFilter === "all" || c.category === this._tvFilter;
            const matchSearch =
              !this._tvSearch ||
              c.name.toLowerCase().includes(this._tvSearch.toLowerCase()) ||
              (c.num && String(c.num).includes(this._tvSearch));
            return matchFilter && matchSearch;
          });

          grid.innerHTML =
            filtered.length > 0
              ? filtered
                  .map((item) => {
                    const isActive = this._selectedChannel && this._selectedChannel.id === item.id;
                    return `
                  <div class="channel-card ${isActive ? "active" : ""}" data-channel-id="${item.id}">
                    <div class="channel-logo-box">
                      ${
                        item.logo
                          ? `<img src="${item.logo}" class="channel-logo-img" alt="${item.name}" />`
                          : `<span style="font-weight: 800; color: #3b82f6;">${item.num || "TV"}</span>`
                      }
                    </div>
                    <div class="channel-details">
                      <div class="channel-name">${item.num ? `${item.num}. ` : ""}${item.name}</div>
                      <div class="channel-sub">${item.category || "Direct"} • ${item.quality || "HD"}</div>
                    </div>
                  </div>
                `;
                  })
                  .join("")
              : `<div style="grid-column: 1 / -1; text-align: center; color: #8b949e; padding: 40px 0;">Aucune chaîne trouvée.</div>`;

          this._bindChannelCards();
        }
      };
    }

    // Channel cards click
    this._bindChannelCards();
  }

  _bindChannelCards() {
    const chCards = this.shadowRoot.querySelectorAll(".channel-card");
    chCards.forEach((card) => {
      card.onclick = () => {
        const chId = card.dataset.channelId;
        const channel = (this._tvChannels || []).find((c) => c.id === chId);
        if (channel) {
          this._selectedChannel = channel;
          chCards.forEach((c) => c.classList.remove("active"));
          card.classList.add("active");
          const nameEl = this.shadowRoot.querySelector(".tv-ch-name");
          if (nameEl) nameEl.textContent = channel.name;
          const numEl = this.shadowRoot.querySelector(".tv-ch-num");
          if (numEl) numEl.textContent = channel.num ? `CH ${channel.num}` : "";
          this._playChannelStream(channel);
        }
      };
    });
  }
}

customElements.define("domolink-camera-panel", DomolinkCameraPanel);
