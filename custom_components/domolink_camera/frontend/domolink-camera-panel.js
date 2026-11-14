/**
 * DomoLink-Camera Custom Panel for Home Assistant
 * Modern glassmorphism UI matching Domolink-Alarm design language
 */

class DomolinkCameraPanel extends HTMLElement {
  _escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }


  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._cameras = [];
    this._arloAccounts = [];
    this._arloWizard = {
      open: false,
      mode: "credentials",
      step: "login",
      loading: false,
      error: "",
      message: "",
      sessionId: "",
      factors: [],
      selectedFactorId: "",
      factorAuthCode: "",
      accountName: "",
      email: "",
      password: "",
      otpCode: "",
      token: "",
      userId: "",
      xcloudId: "",
      cookie: "",
      editingAccountId: "",
    };
    this._availableEntities = [];
    this._activeTab = "cameras"; // "cameras" or "settings"
    this._liveCameras = new Set();
    this._draggedIndex = null;
    this._hasUnsavedOrder = false;
    this._pairingActive = false;
    this._pairingLogs = [];
    try {
      this._pairSsid = localStorage.getItem("domolink_pair_ssid") || "";
      this._pairPass = localStorage.getItem("domolink_pair_pass") || "";
      this._pairApIp = localStorage.getItem("domolink_pair_ap_ip") || "192.168.1.1";
    } catch (e) {
      this._pairSsid = "";
      this._pairPass = "";
      this._pairApIp = "192.168.1.1";
    }
    this._pollTimer = null;
    this._detectedAps = [];
    this._selectedCameraAp = null;
    this._showQrCode = false;
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
    this._fullscreenCamId = null;
    this._liveFrameTimers = new Map();
    this._blobUrls = new Map();
    this._camHlsPlayers = new Map();
    this._fitModes = new Map();
    this._gridDensity = "standard";
    try {
      const savedDensity = localStorage.getItem("domolink_grid_density");
      if (savedDensity) this._gridDensity = savedDensity;
      const savedFits = localStorage.getItem("domolink_fit_modes");
      if (savedFits) {
        const parsed = JSON.parse(savedFits);
        Object.entries(parsed).forEach(([k, v]) => this._fitModes.set(k, v));
      }
    } catch (e) {}
    this._boundKeyDown = (e) => {
      if (e.key === "Escape" && this._fullscreenCamId) {
        this._closeLightbox();
      }
    };
  }

  set panel(panel) {
    this._panel = panel;
  }

  set hass(hass) {
    const isFirst = !this._hass;
    this._hass = hass;
    this._fetchAvailableEntities();
    if (isFirst) {
      this._init();
    } else {
      this._updateEntitiesState();
    }
  }

  connectedCallback() {
    this.render();
    this._startPeriodicRefresh();
    window.addEventListener("keydown", this._boundKeyDown);
  }

  disconnectedCallback() {
    this._stopPeriodicRefresh();
    window.removeEventListener("keydown", this._boundKeyDown);
    this._cleanupAllStreamsAndBlobs();
  }

  _cleanupAllStreamsAndBlobs() {
    for (const camId of Array.from(this._liveFrameTimers.keys())) {
      this._stopLiveFramePump(camId);
    }
    for (const [key, player] of this._camHlsPlayers.entries()) {
      try { player.destroy(); } catch (e) {}
    }
    this._camHlsPlayers.clear();
    if (this._hlsPlayer) {
      try { this._hlsPlayer.destroy(); } catch (e) {}
      this._hlsPlayer = null;
    }
    for (const url of this._blobUrls.values()) {
      try { URL.revokeObjectURL(url); } catch (e) {}
    }
    this._blobUrls.clear();
  }

  async _init() {
    this.render();
    try {
      await Promise.all([
        this._fetchCameras(false),
        this._fetchArloAccounts(false),
      ]);
    } catch (e) {
      console.error("[DomoLink-Camera] Error fetching initial data:", e);
    }
    this.render();
  }

  _startPeriodicRefresh() {
    this._stopPeriodicRefresh();
    // Targeted in-place refresh every 8 seconds without destroying active streams
    this._refreshTimer = setInterval(() => {
      if (this._activeTab === "cameras" && this._draggedIndex === null) {
        this._refreshCamerasInPlace();
      }
    }, 8000);
  }

  _stopPeriodicRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  _appendCacheBuster(url, ts) {
    if (!url) return "";
    const sep = url.includes("?") ? "&" : "?";
    return `${url}${sep}t=${ts}`;
  }

  _getSnapshotUrl(cam, forceTs = null) {
    const ts = forceTs || cam.snapshot_timestamp || Date.now();
    if (cam.signed_snapshot_url) {
      return this._appendCacheBuster(cam.signed_snapshot_url, ts);
    }
    const stateObj = (cam.driver === "ha_proxy" && this._hass) ? this._hass.states[cam.host] : null;
    if (cam.driver === "ha_proxy" && stateObj?.attributes?.entity_picture) {
      return stateObj.attributes.entity_picture;
    }
    return `/api/domolink_camera/snapshot/${cam.id}?t=${ts}`;
  }

  _getStreamUrl(cam) {
    if (cam.signed_stream_url) {
      return cam.signed_stream_url;
    }
    return `/api/domolink_camera/stream/${cam.id}`;
  }

  _getFitMode(camId) {
    return this._fitModes.get(camId) || "contain";
  }

  _toggleFitMode(camId) {
    const next = this._getFitMode(camId) === "contain" ? "cover" : "contain";
    this._fitModes.set(camId, next);
    try {
      const obj = {};
      this._fitModes.forEach((v, k) => { obj[k] = v; });
      localStorage.setItem("domolink_fit_modes", JSON.stringify(obj));
    } catch (e) {}

    const mediaEls = this.shadowRoot.querySelectorAll(
      `.camera-card[data-id="${camId}"] .cam-media, #lightbox-host .cam-media`
    );
    mediaEls.forEach((el) => {
      el.classList.toggle("fit-contain", next === "contain");
      el.classList.toggle("fit-cover", next === "cover");
    });

    const fitBtns = this.shadowRoot.querySelectorAll(`.btn-fit-toggle[data-cam-id="${camId}"]`);
    fitBtns.forEach((btn) => {
      btn.title = next === "contain" ? "Remplir le cadre (Cover)" : "Afficher tout le cadre (Contain)";
      btn.textContent = next === "contain" ? "📐 Remplir" : "📐 Entier";
    });
  }

  async _fetchAuthBlobUrl(apiPath, camId, keyPrefix = "snap") {
    try {
      let resp;
      if (this._hass && typeof this._hass.fetchWithAuth === "function") {
        resp = await this._hass.fetchWithAuth(apiPath);
      } else {
        resp = await fetch(apiPath, { credentials: "same-origin" });
      }
      if (!resp || !resp.ok) return null;
      const blob = await resp.blob();
      if (!blob || blob.size === 0) return null;
      const key = `${keyPrefix}_${camId}`;
      const oldUrl = this._blobUrls.get(key);
      if (oldUrl) {
        try { URL.revokeObjectURL(oldUrl); } catch (e) {}
      }
      const objUrl = URL.createObjectURL(blob);
      this._blobUrls.set(key, objUrl);
      return objUrl;
    } catch (e) {
      return null;
    }
  }

  async _loadSnapshotWithFallback(imgEl, camId) {
    if (!imgEl || imgEl.dataset.authFallback === camId) return;
    imgEl.dataset.authFallback = camId;
    const objUrl = await this._fetchAuthBlobUrl(`/api/domolink_camera/snapshot/${camId}?t=${Date.now()}`, camId, "snap");
    if (objUrl && imgEl.isConnected) {
      imgEl.src = objUrl;
    }
  }

  _stopLiveFramePump(camId) {
    const state = this._liveFrameTimers.get(camId);
    if (state) {
      state.active = false;
      this._liveFrameTimers.delete(camId);
    }
  }

  async _startLiveFramePump(camId, imgEl) {
    if (this._liveFrameTimers.has(camId) || !this._liveCameras.has(camId)) return;
    const state = { active: true };
    this._liveFrameTimers.set(camId, state);

    while (state.active && this._liveCameras.has(camId) && imgEl && imgEl.isConnected) {
      const objUrl = await this._fetchAuthBlobUrl(`/api/domolink_camera/snapshot/${camId}?t=${Date.now()}`, camId, "pump");
      if (!state.active || !this._liveCameras.has(camId) || !imgEl.isConnected) break;
      if (objUrl) {
        imgEl.src = objUrl;
      }
      await new Promise((r) => setTimeout(r, 220));
    }
    this._liveFrameTimers.delete(camId);
  }

  _bindCameraMediaElement(slot, cam, isLive) {
    if (!slot || !cam) return;
    const fitClass = this._getFitMode(cam.id) === "cover" ? "fit-cover" : "fit-contain";

    // Cleanup any existing HLS player for this camera card slot
    const existingHls = this._camHlsPlayers.get(cam.id);
    if (existingHls) {
      try { existingHls.destroy(); } catch (e) {}
      this._camHlsPlayers.delete(cam.id);
    }

    const useVideoPlayer = isLive && Boolean(cam.channel_id || (cam.hls_url && cam.hls_url.includes(".m3u8")));
    if (useVideoPlayer) {
      const video = document.createElement("video");
      video.className = `cam-media ${fitClass}`;
      video.playsInline = true;
      video.autoplay = true;
      video.muted = true;
      video.controls = true;
      slot.innerHTML = "";
      slot.appendChild(video);
      this._attachCameraVideo(video, cam);
      return;
    }

    const img = document.createElement("img");
    img.className = `cam-media ${fitClass}`;
    img.alt = cam.name || "Caméra";
    if (!isLive) img.loading = "lazy";
    img.src = isLive ? this._getStreamUrl(cam) : this._getSnapshotUrl(cam);
    img.onerror = () => {
      if (this._liveCameras.has(cam.id)) {
        this._startLiveFramePump(cam.id, img);
      } else {
        this._loadSnapshotWithFallback(img, cam.id);
      }
    };
    slot.innerHTML = "";
    slot.appendChild(img);
  }

  async _attachCameraVideo(videoEl, cam) {
    const hlsUrl = cam.hls_url || cam.web_hls_url || "";
    const mp4Url = cam.signed_tv_live_url || (cam.channel_id ? `/api/domolink_camera/tv_live/${cam.channel_id}` : "");
    const fallbackToMjpeg = () => {
      const slot = videoEl.parentElement;
      if (!slot || !this._liveCameras.has(cam.id)) return;
      const fitClass = this._getFitMode(cam.id) === "cover" ? "fit-cover" : "fit-contain";
      const img = document.createElement("img");
      img.className = `cam-media ${fitClass}`;
      img.alt = cam.name || "Caméra";
      img.src = this._getStreamUrl(cam);
      img.onerror = () => this._startLiveFramePump(cam.id, img);
      slot.innerHTML = "";
      slot.appendChild(img);
    };

    if (hlsUrl && hlsUrl.includes(".m3u8")) {
      if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
        videoEl.src = hlsUrl;
        videoEl.onerror = () => (mp4Url ? (videoEl.src = mp4Url) : fallbackToMjpeg());
        videoEl.play().catch(() => {});
        return;
      }
      try {
        await this._ensureHlsJs();
        if (window.Hls && window.Hls.isSupported()) {
          const hls = new window.Hls({ enableWorker: true, lowLatencyMode: true });
          this._camHlsPlayers.set(cam.id, hls);
          hls.loadSource(hlsUrl);
          hls.attachMedia(videoEl);
          hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
            videoEl.play().catch(() => {});
          });
          hls.on(window.Hls.Events.ERROR, (_, data) => {
            if (data && data.fatal) {
              try { hls.destroy(); } catch (e) {}
              this._camHlsPlayers.delete(cam.id);
              if (mp4Url) {
                videoEl.src = mp4Url;
                videoEl.onerror = fallbackToMjpeg;
                videoEl.play().catch(fallbackToMjpeg);
              } else {
                fallbackToMjpeg();
              }
            }
          });
          return;
        }
      } catch (e) {}
    }

    if (mp4Url) {
      videoEl.src = this._appendCacheBuster(mp4Url, Date.now());
      videoEl.onerror = fallbackToMjpeg;
      videoEl.play().catch(() => {});
    } else {
      fallbackToMjpeg();
    }
  }

  async _refreshCamerasInPlace() {
    if (!this._hass || this._activeTab !== "cameras" || this._draggedIndex !== null) return;
    const prevIds = this._cameras.map((c) => c.id).join(",");
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/get_cameras" });
      if (!resp || !resp.cameras) return;
      const nextIds = resp.cameras.map((c) => c.id).join(",");
      this._cameras = resp.cameras;

      if (prevIds !== nextIds) {
        this.render();
        return;
      }

      this._cameras.forEach((cam) => {
        const card = this.shadowRoot.querySelector(`.camera-card[data-id="${cam.id}"]`);
        if (!card) return;

        const isLive = this._liveCameras.has(cam.id);
        const dot = card.querySelector(".status-dot");
        if (dot) {
          dot.className = `status-dot ${isLive ? "streaming" : (cam.status || "offline")}`;
        }

        const badge = card.querySelector(".time-badge");
        if (badge) {
          badge.textContent = isLive
            ? (cam.fps > 0 ? `🔴 ${cam.fps} FPS` : "Flux continu")
            : this._formatTime(cam.snapshot_timestamp);
        }

        if (!isLive) {
          const img = card.querySelector(".cam-media-slot img.cam-media");
          if (img) {
            this._preloadAndSwapSnapshot(img, cam);
          }
        }
      });
    } catch (e) {
      console.error("[DomoLink-Camera] In-place refresh error:", e);
    }
  }

  _preloadAndSwapSnapshot(imgEl, cam, forceNow = false) {
    const nextUrl = this._getSnapshotUrl(cam, forceNow ? Date.now() : null);
    const loader = new Image();
    loader.onload = () => {
      if (imgEl.isConnected && !this._liveCameras.has(cam.id)) {
        delete imgEl.dataset.authFallback;
        imgEl.src = nextUrl;
      }
    };
    loader.onerror = async () => {
      if (imgEl.isConnected && !this._liveCameras.has(cam.id)) {
        const blobUrl = await this._fetchAuthBlobUrl(
          `/api/domolink_camera/snapshot/${cam.id}?t=${Date.now()}`,
          cam.id,
          "snap"
        );
        if (blobUrl && imgEl.isConnected && !this._liveCameras.has(cam.id)) {
          imgEl.src = blobUrl;
        }
      }
    };
    loader.src = nextUrl;
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

  _resetArloWizard(open = false, mode = "credentials", editingAcc = null) {
    this._arloWizard = {
      open: open,
      mode: mode,
      step: "login",
      loading: false,
      error: "",
      message: "",
      sessionId: "",
      factors: [],
      selectedFactorId: "",
      factorAuthCode: "",
      accountName: editingAcc ? (editingAcc.name || "") : "",
      email: editingAcc ? (editingAcc.email || "") : "",
      password: "",
      otpCode: "",
      token: "",
      userId: editingAcc ? (editingAcc.user_id || "") : "",
      xcloudId: editingAcc ? (editingAcc.xcloud_id || "") : "",
      cookie: "",
      editingAccountId: editingAcc ? (editingAcc.id || "") : "",
    };
  }

  async _fetchArloAccounts(renderAfter = true) {
    if (!this._hass) return;
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/get_arlo_accounts" });
      if (resp && Array.isArray(resp.accounts)) {
        this._arloAccounts = resp.accounts;
        if (renderAfter) this.render();
      }
    } catch (e) {
      console.error("[DomoLink-Camera] Failed to fetch Arlo accounts:", e);
    }
  }

  async _startArloLogin() {
    const w = this._arloWizard;
    if (!w.email.trim() || !w.password) {
      w.error = "Veuillez saisir l'e-mail et le mot de passe de votre compte Arlo.";
      this.render();
      return;
    }
    w.loading = true;
    w.error = "";
    w.message = "";
    this.render();

    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/arlo_start_login",
        email: w.email.trim(),
        password: w.password,
        account_name: w.accountName.trim(),
        auto_add: true,
      });
      w.loading = false;
      if (resp.status === "connected") {
        w.open = false;
        w.password = "";
        this._showToast(`Compte Arlo connecté ! ${resp.imported_count || 0} caméra(s) importée(s).`);
        await Promise.all([this._fetchArloAccounts(false), this._fetchCameras(false)]);
      } else if (resp.status === "2fa_required") {
        w.step = "factor";
        w.sessionId = resp.session_id || "";
        w.factors = resp.factors || [];
        w.selectedFactorId = w.factors.length > 0 ? w.factors[0].factorId : "";
        w.message = "Authentification Arlo 2FA requise. Choisissez votre méthode de validation ci-dessous.";
      } else if (resp.status === "cloudflare_blocked") {
        w.mode = "token";
        w.error = resp.error || "Cloudflare bloque la connexion directe. Passez par l'onglet Jeton Direct.";
      } else {
        w.error = resp.error || "Échec de connexion à Arlo.";
      }
    } catch (err) {
      w.loading = false;
      w.error = err?.message || String(err);
    }
    this.render();
  }

  async _requestArlo2faCode() {
    const w = this._arloWizard;
    if (!w.sessionId || !w.selectedFactorId) {
      w.error = "Sélectionnez un facteur de vérification 2FA.";
      this.render();
      return;
    }
    w.loading = true;
    w.error = "";
    this.render();

    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/arlo_request_2fa",
        session_id: w.sessionId,
        factor_id: w.selectedFactorId,
      });
      w.loading = false;
      if (resp.status === "code_sent") {
        w.step = "otp";
        w.factorAuthCode = resp.factor_auth_code || "";
        w.message = "Code de vérification envoyé ! Consultez votre e-mail / SMS et saisissez le code ci-dessous.";
      } else {
        w.error = resp.error || "Impossible d'envoyer le code 2FA.";
      }
    } catch (err) {
      w.loading = false;
      w.error = err?.message || String(err);
    }
    this.render();
  }

  async _verifyArlo2faCode() {
    const w = this._arloWizard;
    if (!w.otpCode.trim()) {
      w.error = "Veuillez saisir le code OTP reçu.";
      this.render();
      return;
    }
    w.loading = true;
    w.error = "";
    this.render();

    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/arlo_verify_2fa",
        session_id: w.sessionId,
        otp_code: w.otpCode.trim(),
        factor_auth_code: w.factorAuthCode || undefined,
        auto_add: true,
      });
      w.loading = false;
      if (resp.status === "connected") {
        this._resetArloWizard(false);
        this._showToast(`Compte Arlo validé ! ${resp.imported_count || 0} caméra(s) importée(s).`);
        await Promise.all([this._fetchArloAccounts(false), this._fetchCameras(false)]);
      } else {
        w.error = resp.error || "Code 2FA refusé par Arlo.";
      }
    } catch (err) {
      w.loading = false;
      w.error = err?.message || String(err);
    }
    this.render();
  }

  async _saveArloDirectToken() {
    const w = this._arloWizard;
    if (!w.token.trim()) {
      w.error = "Veuillez coller le jeton Authorization Arlo.";
      this.render();
      return;
    }
    w.loading = true;
    w.error = "";
    this.render();

    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/arlo_save_token",
        email: w.email.trim(),
        account_name: w.accountName.trim(),
        token: w.token.trim(),
        user_id: w.userId.trim(),
        xcloud_id: w.xcloudId.trim(),
        cookie: w.cookie.trim(),
        account_id: w.editingAccountId || "",
        auto_add: true,
      });
      w.loading = false;
      if (resp.status === "connected") {
        this._resetArloWizard(false);
        this._showToast(`Compte Arlo synchronisé (${resp.total_devices || 0} caméra(s), ${resp.imported_count || 0} ajoutée(s)).`);
        await Promise.all([this._fetchArloAccounts(false), this._fetchCameras(false)]);
      } else {
        w.error = resp.error || "Impossible de valider ce jeton Arlo.";
      }
    } catch (err) {
      w.loading = false;
      w.error = err?.message || String(err);
    }
    this.render();
  }

  async _syncArloAccount(accountId, autoAdd = true) {
    this._showToast("Synchronisation du compte Arlo en cours...");
    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/arlo_sync_account",
        account_id: accountId,
        auto_add: autoAdd,
      });
      if (resp.status === "synced") {
        this._showToast(`Synchro Arlo réussie : ${resp.total_devices} caméra(s), ${resp.imported_count} nouvelle(s) !`);
        await Promise.all([this._fetchArloAccounts(false), this._fetchCameras(false)]);
      } else {
        this._showToast(`Erreur synchro Arlo : ${resp.error || "Jeton expiré"}`);
      }
    } catch (err) {
      this._showToast(`Erreur synchro Arlo : ${err?.message || err}`);
    }
    this.render();
  }

  async _deleteArloAccount(accountId) {
    if (!confirm("Voulez-vous supprimer ce compte Arlo de DomoLink ?")) return;
    const delCams = confirm("Souhaitez-vous également supprimer les caméras liées à ce compte ?");
    try {
      await this._hass.callWS({
        type: "domolink_camera/arlo_delete_account",
        account_id: accountId,
        delete_cameras: delCams,
      });
      this._showToast("Compte Arlo supprimé.");
      await Promise.all([this._fetchArloAccounts(false), this._fetchCameras(false)]);
    } catch (err) {
      this._showToast("Erreur lors de la suppression du compte Arlo");
    }
    this.render();
  }

  async _addArloCameraFromAccount(accountId, dev) {
    const newCam = {
      name: dev.name || `Arlo ${dev.device_id}`,
      description: `Arlo ${dev.model_id || ""} (${dev.account_email || ""})`.trim(),
      driver: "arlo_cloud",
      host: dev.device_id,
      port: 443,
      arlo_account_id: accountId,
      arlo_device_id: dev.device_id,
      parent_id: dev.parent_id || dev.device_id,
      xcloud_id: dev.xcloud_id || "",
      model_id: dev.model_id || "Arlo",
      account_email: dev.account_email || "",
      linked_entities: [],
    };
    await this._saveCamera(newCam);
    await this._fetchArloAccounts(true);
  }

  _fetchAvailableEntities() {
    if (!this._hass || !this._hass.states) return;
    try {
      const allowed = ["switch", "light", "cover", "lock", "fan"];
      this._availableEntities = Object.values(this._hass.states)
        .filter((s) => allowed.includes(s.entity_id.split(".")[0]))
        .slice(0, 150)
        .map((s) => ({
          entity_id: s.entity_id,
          name: s.attributes.friendly_name || s.entity_id,
        }))
        .sort((a, b) => a.name.localeCompare(b.name));
    } catch (e) {
      this._availableEntities = [];
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

  // --- Live Stream Toggle (targeted update, zero DOM teardown) ---
  async _toggleLive(camId, forceLive = null) {
    const currentlyLive = this._liveCameras.has(camId);
    const targetLive = forceLive !== null ? forceLive : !currentlyLive;
    const cam = this._cameras.find((c) => c.id === camId);
    const hadHls = Boolean(cam && (cam.channel_id || (cam.hls_url && cam.hls_url.includes(".m3u8"))));

    if (targetLive) {
      this._liveCameras.add(camId);
    } else {
      this._liveCameras.delete(camId);
      this._stopLiveFramePump(camId);
    }

    this._updateSingleCameraCardLiveState(camId);

    try {
      const resp = await this._hass.callWS({
        type: "domolink_camera/trigger_live",
        camera_id: camId,
        live: targetLive,
      });
      if (resp && cam) {
        if (resp.signed_stream_url) cam.signed_stream_url = resp.signed_stream_url;
        if (resp.signed_snapshot_url) cam.signed_snapshot_url = resp.signed_snapshot_url;
        if (resp.hls_url) cam.hls_url = resp.hls_url;
        const nowHasHls = Boolean(cam.channel_id || (cam.hls_url && cam.hls_url.includes(".m3u8")));
        if (targetLive && !hadHls && nowHasHls && this._liveCameras.has(camId)) {
          this._updateSingleCameraCardLiveState(camId);
        }
      }
    } catch (e) {
      console.error("[DomoLink-Camera] trigger_live error:", e);
    }
  }

  _updateSingleCameraCardLiveState(camId) {
    const cam = this._cameras.find((c) => c.id === camId);
    if (!cam) return;
    const isLive = this._liveCameras.has(camId);

    const card = this.shadowRoot.querySelector(`.camera-card[data-id="${camId}"]`);
    if (card) {
      const dot = card.querySelector(".status-dot");
      if (dot) dot.className = `status-dot ${isLive ? "streaming" : (cam.status || "offline")}`;

      const liveBtn = card.querySelector(".live-btn");
      if (liveBtn) {
        liveBtn.classList.toggle("active", isLive);
        liveBtn.textContent = isLive ? "🔴 EN DIRECT" : "▶ LIVE";
      }

      const badge = card.querySelector(".time-badge");
      if (badge) {
        badge.textContent = isLive ? "Flux continu" : this._formatTime(cam.snapshot_timestamp);
      }

      const slot = card.querySelector(".cam-media-slot");
      if (slot) {
        this._bindCameraMediaElement(slot, cam, isLive);
      }
    }

    // Update Lightbox if currently open for this camera
    if (this._fullscreenCamId === camId) {
      this._renderLightboxContent(camId);
    }

    // Update global "Tout en Direct" button state
    const allLiveBtn = this.shadowRoot.querySelector("#btn-toggle-all-live");
    if (allLiveBtn && this._cameras.length > 0) {
      const allLive = this._cameras.every((c) => this._liveCameras.has(c.id));
      allLiveBtn.classList.toggle("active", allLive);
      allLiveBtn.textContent = allLive ? "⏹ Tout Arrêter" : "▶ Tout en Direct";
    }
  }

  async _toggleAllLive() {
    if (!this._cameras || this._cameras.length === 0) return;
    const allLive = this._cameras.every((c) => this._liveCameras.has(c.id));
    const target = !allLive;
    await Promise.all(this._cameras.map((cam) => this._toggleLive(cam.id, target)));
  }

  _refreshAllSnapshots() {
    if (!this._cameras) return;
    let refreshed = 0;
    this._cameras.forEach((cam) => {
      if (!this._liveCameras.has(cam.id)) {
        const img = this.shadowRoot.querySelector(`.camera-card[data-id="${cam.id}"] .cam-media-slot img.cam-media`);
        if (img) {
          this._preloadAndSwapSnapshot(img, cam, true);
          refreshed++;
        }
      }
    });
    this._showToast(refreshed > 0 ? "Actualisation des vignettes..." : "Toutes les caméras sont déjà en direct");
  }

  async _toggleNightVision(camId) {
    const cam = this._cameras.find((c) => c.id === camId);
    if (!cam || !this._hass) return;
    const nextState = !cam.night_vision;
    try {
      await this._hass.callWS({
        type: "domolink_camera/set_ir",
        camera_id: camId,
        enabled: nextState,
      });
      cam.night_vision = nextState;
      const irBtns = this.shadowRoot.querySelectorAll(`.btn-ir-toggle[data-cam-id="${camId}"]`);
      irBtns.forEach((btn) => btn.classList.toggle("active", nextState));
      this._showToast(`Vision nocturne IR ${nextState ? "activée" : "désactivée"}`);
    } catch (e) {
      this._showToast("Erreur lors du changement IR");
    }
  }

  _setGridDensity(density) {
    this._gridDensity = density;
    try { localStorage.setItem("domolink_grid_density", density); } catch (e) {}
    const grid = this.shadowRoot.querySelector(".camera-grid");
    if (grid) {
      grid.classList.remove("grid-compact", "grid-standard", "grid-large");
      grid.classList.add(`grid-${density}`);
    }
    const btns = this.shadowRoot.querySelectorAll(".density-btn");
    btns.forEach((b) => b.classList.toggle("active", b.dataset.density === density));
  }

  _openLightbox(camId) {
    this._fullscreenCamId = camId;
    if (!this._liveCameras.has(camId)) {
      this._toggleLive(camId, true);
    } else {
      this._renderLightboxContent(camId);
    }
  }

  _closeLightbox() {
    if (this._fullscreenCamId) {
      const existingHls = this._camHlsPlayers.get(`lb_${this._fullscreenCamId}`);
      if (existingHls) {
        try { existingHls.destroy(); } catch (e) {}
        this._camHlsPlayers.delete(`lb_${this._fullscreenCamId}`);
      }
    }
    this._fullscreenCamId = null;
    const host = this.shadowRoot.querySelector("#lightbox-host");
    if (host) host.innerHTML = "";
  }

  _renderLightboxContent(camId) {
    const host = this.shadowRoot.querySelector("#lightbox-host");
    const cam = this._cameras.find((c) => c.id === camId);
    if (!host || !cam) return;

    const isLive = this._liveCameras.has(camId);
    const fitMode = this._getFitMode(camId);
    const hasIr = Boolean(cam.capabilities && cam.capabilities.night_vision);

    host.innerHTML = `
      <div class="lightbox-overlay" id="lightbox-overlay">
        <div class="lightbox-dialog">
          <div class="lightbox-header">
            <div class="card-title-box">
              <div class="status-dot ${isLive ? "streaming" : (cam.status || "offline")}"></div>
              <span class="card-name">${this._escapeHtml(cam.name)}</span>
              <span class="driver-badge">${this._escapeHtml(cam.host || cam.driver)}</span>
            </div>
            <div class="lightbox-actions">
              <button class="btn-secondary btn-fit-toggle" data-cam-id="${cam.id}">
                ${fitMode === "contain" ? "📐 Remplir" : "📐 Entier"}
              </button>
              ${hasIr ? `<button class="btn-secondary btn-ir-toggle ${cam.night_vision ? "active" : ""}" data-cam-id="${cam.id}">🌙 IR</button>` : ""}
              <button class="btn-secondary lb-live-btn ${isLive ? "active" : ""}" data-cam-id="${cam.id}">
                ${isLive ? "🔴 EN DIRECT" : "▶ LIVE"}
              </button>
              <button class="btn-secondary" id="lb-native-fs">⛶ Plein écran</button>
              <button class="btn-danger" id="lb-close">✕ Fermer</button>
            </div>
          </div>
          <div class="lightbox-viewport" id="lb-viewport"></div>
        </div>
      </div>
    `;

    const vp = host.querySelector("#lb-viewport");
    this._bindCameraMediaElement(vp, cam, isLive);

    const overlay = host.querySelector("#lightbox-overlay");
    if (overlay) {
      overlay.onclick = (e) => {
        if (e.target === overlay) this._closeLightbox();
      };
    }
    const closeBtn = host.querySelector("#lb-close");
    if (closeBtn) closeBtn.onclick = () => this._closeLightbox();

    const fsBtn = host.querySelector("#lb-native-fs");
    if (fsBtn && vp) {
      fsBtn.onclick = () => {
        if (vp.requestFullscreen) vp.requestFullscreen();
        else if (vp.webkitRequestFullscreen) vp.webkitRequestFullscreen();
      };
    }

    const fitBtn = host.querySelector(".btn-fit-toggle");
    if (fitBtn) fitBtn.onclick = () => this._toggleFitMode(cam.id);

    const irBtn = host.querySelector(".btn-ir-toggle");
    if (irBtn) irBtn.onclick = () => this._toggleNightVision(cam.id);

    const lbLive = host.querySelector(".lb-live-btn");
    if (lbLive) lbLive.onclick = () => this._toggleLive(cam.id);
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
      logBox.innerHTML = this._pairingLogs.map((l) => `<div>> ${this._escapeHtml(l)}</div>`).join("");
      logBox.scrollTop = logBox.scrollHeight;
    }
  }

  _triggerBrowserSideApPairing(apIp, ssid, pass) {
    const targets = [apIp, "192.168.1.1", "192.168.10.1", "192.168.1.254"].filter(Boolean);
    const uniqueTargets = Array.from(new Set(targets));
    const qSsid = encodeURIComponent(ssid);
    const qPass = encodeURIComponent(pass);

    // 1. Multi-path HTTP CGI injection (standard on YsxLite / A9 / HiSilicon / BK chips)
    uniqueTargets.forEach((ip) => {
      const urls = [
        `http://${ip}/set_wifi.cgi?ssid=${qSsid}&pwd=${qPass}`,
        `http://${ip}/wifi_set?ssid=${qSsid}&password=${qPass}`,
        `http://${ip}/cgi-bin/hi3510/param.cgi?cmd=setwirelessattr&-wf_ssid=${qSsid}&-wf_key=${qPass}`,
        `http://${ip}/config?ssid=${qSsid}&pwd=${qPass}`,
        `http://${ip}:8080/wifi_set?ssid=${qSsid}&password=${qPass}`,
      ];
      urls.forEach((u) => {
        try {
          const ctl = new AbortController();
          setTimeout(() => ctl.abort(), 2000);
          fetch(u, { mode: "no-cors", cache: "no-store", signal: ctl.signal }).catch(() => {});
          const img = new Image();
          img.src = u;
        } catch (e) {}
      });
    });

    // 2. WebRTC STUN datagram trigger on port 32108 (browser UDP packet dispatch)
    try {
      const rtcCls = window.RTCPeerConnection || window.webkitRTCPeerConnection;
      if (rtcCls) {
        const iceServers = uniqueTargets.map((ip) => ({ urls: `stun:${ip}:32108` }));
        const pc = new rtcCls({ iceServers: iceServers });
        pc.createDataChannel("domolink_probe");
        pc.createOffer()
          .then((offer) => pc.setLocalDescription(offer))
          .catch(() => {});
        setTimeout(() => {
          try {
            pc.close();
          } catch (e) {}
        }, 3000);
      }
    } catch (e) {}
  }

  async _startPairing() {
    const ssidInput = this.shadowRoot.querySelector("#pair-ssid");
    const passInput = this.shadowRoot.querySelector("#pair-pass");
    const apIpInput = this.shadowRoot.querySelector("#pair-ap-ip");

    const ssid = (ssidInput ? ssidInput.value : this._pairSsid || "").trim();
    const pass = passInput ? passInput.value : this._pairPass || "";
    const apIp = (apIpInput ? apIpInput.value : this._pairApIp || "192.168.1.1").trim() || "192.168.1.1";

    this._pairSsid = ssid;
    this._pairPass = pass;
    this._pairApIp = apIp;
    try {
      localStorage.setItem("domolink_pair_ssid", ssid);
      localStorage.setItem("domolink_pair_pass", pass);
      localStorage.setItem("domolink_pair_ap_ip", apIp);
    } catch (e) {}

    if (!ssid) {
      this._showToast("Veuillez saisir le SSID de votre réseau Wi-Fi.");
      this._appendLog("⚠️ [VALIDATION] Nom du réseau Wi-Fi (SSID) manquant.");
      return;
    }

    this._pairingActive = true;
    this._pairingLogs = [];
    this._showQrCode = true; // Auto-display QR Code for optical pairing
    this._appendLog(`🚀 [DÉMARRAGE] Assistant d'appairage lancé pour le réseau '${ssid}'...`);
    this._appendLog("📱 [QR CODE OPTIQUE GÉNÉRÉ] Pointez l'objectif de votre caméra vers le QR Code ci-dessous (15-20 cm) jusqu'au bip !");
    this._appendLog(`📋 [VÉRIFICATION] Longueur SSID=${ssid.length} car. | Longueur clé=${pass.length} car. | IP cible AP=${apIp}`);

    if (apIp === "192.168.1.254" || apIp === "192.168.0.254") {
      this._appendLog(`⚠️ [ATTENTION] L'adresse '${apIp}' est l'adresse de votre passerelle Freebox !`);
      this._appendLog("💡 L'adresse par défaut du point d'accès de votre caméra est généralement 192.168.1.1 ou 192.168.10.1.");
    }

    if (this._selectedCameraAp) {
      this._appendLog(`🎯 [PONT CAMÉRA] Point d'accès cible : '${this._selectedCameraAp}'`);
    }

    this.render();

    // Trigger immediate browser-side multi-vector injection (CGI + WebRTC UDP)
    this._appendLog(`📡 [INJECTION DIRECTE] Émission des trames Wi-Fi vers ${apIp}:32108 & HTTP CGI...`);
    this._triggerBrowserSideApPairing(apIp, ssid, pass);

    // Arm Home Assistant backend if connected
    try {
      await this._hass.callWS({
        type: "domolink_camera/start_pairing",
        ssid: ssid,
        password: pass,
        camera_ap_ip: apIp,
        camera_ssid: this._selectedCameraAp || undefined,
      });
      this._appendLog("✅ [SERVEUR ARMÉ] Home Assistant écoute et scanne le réseau local (72s).");
    } catch (e) {
      const errMsg = e?.message || (typeof e === "object" ? JSON.stringify(e) : String(e));
      this._appendLog(`ℹ️ [REMARQUE LIAISON] Déconnexion temporaire HA (${errMsg}) - Basculez sur votre Wi-Fi Freebox ('${ssid}').`);
      this._appendLog("💡 Astuce : La méthode la plus rapide et infaillible est de présenter le QR Code ci-dessous à la caméra !");
    }

    this._startResilientPairingPoll(ssid, pass, apIp);
  }

  _startResilientPairingPoll(ssid, pass, apIp) {
    if (this._pollTimer) clearInterval(this._pollTimer);
    let offlineCount = 0;
    let attempts = 0;
    const maxAttempts = 36; // 36 * 2s = 72s

    this._pollTimer = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts || !this._pairingActive) {
        clearInterval(this._pollTimer);
        this._pollTimer = null;
        this._pairingActive = false;
        this._appendLog("⚠️ [FIN DE TENTATIVE] Délai d'attente atteint (72s).");
        this._appendLog("💡 Cliquez sur 'Scanner le réseau' une fois votre appareil reconnecté à la Freebox.");
        this.render();
        return;
      }

      try {
        const st = await this._hass.callWS({ type: "domolink_camera/pair_status" });
        if (offlineCount > 0) {
          this._appendLog("🟢 [RECONNEXION HOME ASSISTANT] Liaison rétablie avec le serveur !");
          offlineCount = 0;
        }
        if (st) {
          if (st.logs && st.logs.length > 0) {
            this._pairingLogs = st.logs;
          }
          if (!st.active) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
            this._pairingActive = false;
            if (st.discovered && st.discovered.length > 0) {
              this._scanResults = st.discovered;
              this._scanCompatible = st.discovered;
              this._appendLog(`🎉 [SUCCÈS] Caméra découverte et appairée avec succès : ${st.discovered[0].name} (${st.discovered[0].host}) !`);
              this._showToast("Caméra appairée avec succès !");
            } else {
              this._appendLog("ℹ️ Écoute terminée. Lancement de la détection sur le réseau local...");
              this._scanLocalNetwork();
            }
            this.render();
          } else {
            this._updatePairingLogs();
          }
        }
      } catch (err) {
        offlineCount++;
        // Caught disconnection while user is on camera AP
        if (offlineCount === 1) {
          this._appendLog("📶 [BASCULE WI-FI DÉTECTÉE] Connecté au point d'accès de la caméra.");
          this._appendLog("📡 Envoi continu des identifiants Wi-Fi...");
        }
        if (offlineCount % 2 === 0) {
          this._triggerBrowserSideApPairing(apIp, ssid, pass);
        }
        this._updatePairingLogs();
      }
    }, 2000);
  }

  async _stopPairing() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
    this._pairingActive = false;
    try {
      await this._hass.callWS({ type: "domolink_camera/stop_pairing" });
    } catch (e) {}
    this._appendLog("🛑 [ARRÊT] Assistant d'appairage annulé.");
    this._showToast("Appairage annulé");
    this.render();
  }

  async _scanCameraAps() {
    this._appendLog("📡 [SCAN WI-FI AP] Recherche des caméras à proximité (Supervisor wlan0, nmcli & airport)...");
    try {
      const resp = await this._hass.callWS({ type: "domolink_camera/scan_wifi_aps" });
      if (resp && resp.aps) {
        this._detectedAps = resp.aps;
        const cams = resp.aps.filter((a) => a.is_camera);
        if (cams.length > 0) {
          this._appendLog(`🎯 [DÉTECTION] ${cams.length} caméra(s) identifiée(s) par motif ou UID :`);
          cams.forEach((c) => {
            this._appendLog(`   • SSID: ${c.ssid} (Signal: ${c.signal}%)`);
          });
          this._showToast(`${cams.length} caméra(s) Wi-Fi détectée(s) !`);
          // Auto-select first camera AP if none selected
          if (!this._selectedCameraAp && cams.length > 0) {
            this._selectedCameraAp = cams[0].ssid;
            this._pairApIp = "192.168.1.1";
          }
        } else {
          this._appendLog(`ℹ️ [INFO] Aucun SSID de caméra identifié parmi les ${resp.aps.length} réseaux scannés.`);
        }
        this.render();
      }
    } catch (err) {
      const errMsg = err?.message || (typeof err === "object" ? JSON.stringify(err) : String(err));
      this._appendLog(`⚠️ Analyse Wi-Fi non disponible sur l'hôte : ${errMsg}`);
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
      port: dev.port !== undefined ? dev.port : (dev.driver === "generic_rtsp" ? 554 : 32108),
      http_port: dev.http_port || 80,
      stream_path: dev.stream_path || "",
      snapshot_path: dev.snapshot_path || "",
      arlo_account_id: dev.arlo_account_id || "",
      arlo_device_id: dev.arlo_device_id || "",
      parent_id: dev.parent_id || "",
      xcloud_id: dev.xcloud_id || "",
      model_id: dev.model_id || "",
      account_email: dev.account_email || "",
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

  async _renderQrCode(container) {
    if (!container) return;
    try {
      if (!this._QRCodeClass) {
        const mod = await import("./qrcode.js");
        this._QRCodeClass = mod.QRCode;
      }
      container.innerHTML = "";
      const qrString = `WIFI:T:WPA;S:${this._pairSsid || ""};P:${this._pairPass || ""};;`;
      new this._QRCodeClass(container, {
        text: qrString,
        width: 200,
        height: 200,
      });
    } catch (err) {
      console.error("DomoLink-Camera: Erreur QR Code:", err);
      container.innerHTML = `<div style="color: #ef4444; font-size: 12px; padding: 12px;">Erreur génération QR : ${err.message || err}</div>`;
    }
  }

  render() {
    try {
      this._renderInner();
    } catch (err) {
      console.error("[DomoLink-Camera] Render error:", err);
      if (this.shadowRoot) {
        this.shadowRoot.innerHTML = `
          <div style="padding: 40px; color: #ef4444; font-family: sans-serif; background: #0d1117; min-height: 100vh;">
            <h2>⚠️ Erreur d'affichage DomoLink Camera</h2>
            <pre style="background: rgba(0,0,0,0.5); padding: 16px; border-radius: 8px; color: #f87171; white-space: pre-wrap;">${err.stack || err.message || err}</pre>
            <button id="btn-reload-panel" style="background: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; margin-top: 16px;">Réessayer</button>
          </div>
        `;
        const rBtn = this.shadowRoot.querySelector("#btn-reload-panel");
        if (rBtn) rBtn.onclick = () => this.render();
      }
    }
  }

  _renderInner() {
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

        /* Camera Toolbar & Grid Densities */
        .cameras-toolbar {
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          margin-bottom: 18px;
          padding: 10px 14px;
          background: rgba(22, 27, 34, 0.72);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
        }

        .toolbar-info {
          font-size: 13px;
          color: #94a3b8;
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .toolbar-actions {
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 8px;
        }

        .density-group {
          display: inline-flex;
          background: rgba(13, 17, 23, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 8px;
          padding: 2px;
        }

        .density-btn {
          background: transparent;
          border: none;
          color: #8b949e;
          font-size: 12px;
          font-weight: 600;
          padding: 5px 10px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .density-btn.active {
          background: #3b82f6;
          color: #ffffff;
        }

        .btn-toolbar {
          background: rgba(255, 255, 255, 0.07);
          border: 1px solid rgba(255, 255, 255, 0.14);
          color: #f0f6fc;
          font-size: 12px;
          font-weight: 600;
          padding: 6px 12px;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-toolbar:hover {
          background: rgba(59, 130, 246, 0.25);
          border-color: #3b82f6;
        }

        .btn-toolbar.active {
          background: rgba(239, 68, 68, 0.25);
          border-color: #ef4444;
          color: #fca5a5;
        }

        /* Grid */
        .camera-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
          gap: 24px;
        }

        .camera-grid.grid-compact {
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 16px;
        }

        .camera-grid.grid-large {
          grid-template-columns: repeat(auto-fill, minmax(520px, 1fr));
          gap: 26px;
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

        .cam-media-slot {
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .viewport img,
        .viewport video,
        .cam-media {
          width: 100%;
          height: 100%;
          display: block;
          background: #000;
        }

        .cam-media.fit-contain { object-fit: contain; }
        .cam-media.fit-cover { object-fit: cover; }

        /* Quick Viewport Actions */
        .viewport-actions {
          position: absolute;
          top: 8px;
          right: 8px;
          display: flex;
          gap: 6px;
          z-index: 6;
          opacity: 0.85;
          transition: opacity 0.2s ease;
        }

        .viewport:hover .viewport-actions {
          opacity: 1;
        }

        .vp-action-btn {
          background: rgba(13, 17, 23, 0.78);
          backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.18);
          color: #f0f6fc;
          font-size: 11px;
          font-weight: 600;
          padding: 4px 8px;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .vp-action-btn:hover {
          background: rgba(37, 99, 235, 0.85);
          border-color: #60a5fa;
        }

        .vp-action-btn.active {
          background: rgba(245, 158, 11, 0.85);
          border-color: #fbbf24;
          color: #111827;
        }

        /* Lightbox Fullscreen Modal */
        .lightbox-overlay {
          position: fixed;
          inset: 0;
          background: rgba(3, 7, 18, 0.92);
          backdrop-filter: blur(10px);
          z-index: 3000;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        }

        .lightbox-dialog {
          width: 100%;
          max-width: 1280px;
          background: #0d1117;
          border: 1px solid rgba(255, 255, 255, 0.15);
          border-radius: 16px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          box-shadow: 0 24px 60px rgba(0, 0, 0, 0.8);
        }

        .lightbox-header {
          padding: 12px 18px;
          background: rgba(22, 27, 34, 0.95);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          flex-wrap: wrap;
          justify-content: space-between;
          align-items: center;
          gap: 10px;
        }

        .lightbox-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          align-items: center;
        }

        .lightbox-actions .lb-live-btn.active {
          background: #ef4444;
          border-color: #f87171;
          color: #ffffff;
        }

        .lightbox-viewport {
          width: 100%;
          height: 75vh;
          background: #000000;
          display: flex;
          align-items: center;
          justify-content: center;
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
        <div id="lightbox-host"></div>

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

    const allLive = this._cameras.every((c) => this._liveCameras.has(c.id));
    const onlineCount = this._cameras.filter((c) => c.status === "online" || c.status === "streaming" || this._liveCameras.has(c.id)).length;

    return `
      <div class="cameras-toolbar">
        <div class="toolbar-info">
          <span>📡 <strong>${onlineCount}/${this._cameras.length}</strong> caméra(s) accessible(s)</span>
          <span>•</span>
          <span><strong>${this._liveCameras.size}</strong> flux en direct</span>
        </div>
        <div class="toolbar-actions">
          <div class="density-group" title="Taille d'affichage de la grille">
            <button class="density-btn ${this._gridDensity === "compact" ? "active" : ""}" data-density="compact">Compact</button>
            <button class="density-btn ${this._gridDensity === "standard" ? "active" : ""}" data-density="standard">Standard</button>
            <button class="density-btn ${this._gridDensity === "large" ? "active" : ""}" data-density="large">Large</button>
          </div>
          <button class="btn-toolbar" id="btn-refresh-all" title="Actualiser immédiatement toutes les vignettes">
            🔄 Actualiser tout
          </button>
          <button class="btn-toolbar ${allLive ? "active" : ""}" id="btn-toggle-all-live" title="Basculer toutes les caméras en mode direct">
            ${allLive ? "⏹ Tout Arrêter" : "▶ Tout en Direct"}
          </button>
        </div>
      </div>

      <div class="camera-grid grid-${this._escapeHtml(this._gridDensity)}">
        ${this._cameras
          .map((cam, idx) => {
            const isLive = this._liveCameras.has(cam.id);
            const statusClass = cam.status || "offline";
            const snapUrl = isLive ? this._getStreamUrl(cam) : this._getSnapshotUrl(cam);
            const fitMode = this._getFitMode(cam.id);
            const fitClass = fitMode === "cover" ? "fit-cover" : "fit-contain";
            const hasIr = Boolean(cam.capabilities && cam.capabilities.night_vision);

            const driverLabel =
              cam.driver === "arlo_cloud"
                ? "Arlo Cloud"
                : cam.driver === "ysxlite_pppp"
                ? "YsxLite"
                : cam.driver === "ha_proxy"
                ? "Passerelle HA"
                : cam.driver === "generic_mjpeg"
                ? "MJPEG"
                : "RTSP";

            const batLevel = cam.capabilities && cam.capabilities.battery_level;
            const hasBattery = batLevel !== undefined && batLevel !== null && batLevel !== "";

            return `
            <div class="camera-card"
                 draggable="true"
                 data-id="${this._escapeHtml(cam.id)}"
                 data-index="${idx}">

              <!-- Card Header -->
              <div class="card-header">
                <div class="card-title-box">
                  <div class="status-dot ${isLive ? "streaming" : statusClass}"></div>
                  <div class="card-name">${this._escapeHtml(cam.name)}</div>
                  <span class="driver-badge">${driverLabel}</span>
                  ${hasBattery ? `<span class="driver-badge" title="Niveau batterie">${Number(batLevel) <= 20 ? "🪫" : "🔋"} ${this._escapeHtml(batLevel)}%</span>` : ""}
                </div>
                <div style="font-size: 12px; color: #8b949e; cursor: grab;" title="Glisser pour réorganiser">⠿</div>
              </div>

              <!-- Viewport with Image/Live Stream -->
              <div class="viewport" data-cam-id="${this._escapeHtml(cam.id)}">
                <div class="cam-media-slot" data-cam-id="${this._escapeHtml(cam.id)}">
                  <img class="cam-media ${fitClass}" src="${this._escapeHtml(snapUrl)}" alt="${this._escapeHtml(cam.name)}" ${isLive ? "" : 'loading="lazy"'} />
                </div>

                <!-- Quick Readability & Stream Controls -->
                <div class="viewport-actions">
                  <button class="vp-action-btn btn-snap-refresh" data-cam-id="${this._escapeHtml(cam.id)}" title="Rafraîchir la vignette">🔄</button>
                  ${
                    hasIr
                      ? `<button class="vp-action-btn btn-ir-toggle ${cam.night_vision ? "active" : ""}" data-cam-id="${this._escapeHtml(cam.id)}" title="Vision nocturne IR">🌙</button>`
                      : ""
                  }
                  <button class="vp-action-btn btn-fit-toggle" data-cam-id="${this._escapeHtml(cam.id)}" title="${fitMode === "contain" ? "Remplir le cadre (Cover)" : "Afficher tout le cadre (Contain)"}">
                    ${fitMode === "contain" ? "📐 Remplir" : "📐 Entier"}
                  </button>
                  <button class="vp-action-btn btn-cam-fullscreen" data-cam-id="${this._escapeHtml(cam.id)}" title="Agrandir / Plein écran">⛶</button>
                </div>

                <!-- Rollover Hover Tooltip -->
                <div class="rollover-tooltip">
                  <strong>${this._escapeHtml(cam.name)}</strong> (${this._escapeHtml(cam.host || "IP non assignée")})<br/>
                  ${cam.description ? this._escapeHtml(cam.description) : "<i>Aucune description renseignée.</i>"}
                </div>

                <!-- Live Button -->
                <button class="live-btn ${isLive ? "active" : ""}" data-cam-id="${this._escapeHtml(cam.id)}">
                  ${isLive ? "🔴 EN DIRECT" : "▶ LIVE"}
                </button>

                <!-- Snapshot Time / FPS badge -->
                <div class="time-badge">
                  ${isLive ? (cam.fps > 0 ? `🔴 ${cam.fps} FPS` : "Flux continu") : this._formatTime(cam.snapshot_timestamp)}
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

    // Reset existing stream
    if (this._hlsPlayer) {
      this._hlsPlayer.destroy();
      this._hlsPlayer = null;
    }
    video.pause();
    video.removeAttribute("src");
    video.load();

    this._showToast(`Chargement de ${channel.name}...`);
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

      const startPlayback = () => {
        video.muted = false;
        video.play().catch((err) => {
          if (err && err.name === "NotAllowedError") {
            video.muted = true;
            video.play().catch(() => {});
            this._showToast("Lecture démarrée en sourdine (cliquez pour le son)");
          }
        });
      };

      if (isHls) {
        if (video.canPlayType("application/vnd.apple.mpegurl")) {
          video.src = streamUrl;
          startPlayback();
        } else {
          await this._ensureHlsJs();
          if (window.Hls && window.Hls.isSupported()) {
            this._hlsPlayer = new window.Hls({
              enableWorker: true,
              lowLatencyMode: true,
            });
            this._hlsPlayer.loadSource(streamUrl);
            this._hlsPlayer.attachMedia(video);
            this._hlsPlayer.on(window.Hls.Events.MANIFEST_PARSED, () => {
              startPlayback();
            });
            this._hlsPlayer.on(window.Hls.Events.ERROR, (event, data) => {
              if (data && data.fatal) {
                console.warn("HLS fatal error, switching to proxy:", data);
                video.src = `/api/domolink_camera/tv_live/${channel.id}?t=${Date.now()}`;
                startPlayback();
              }
            });
          } else {
            video.src = streamUrl;
            startPlayback();
          }
        }
      } else {
        const fullUrl = streamUrl.startsWith("http") || streamUrl.startsWith("/")
          ? `${streamUrl}${streamUrl.includes("?") ? "&" : "?"}t=${Date.now()}`
          : streamUrl;
        video.src = fullUrl;
        startPlayback();
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
                          ? `<img src="${item.logo}" class="channel-logo-img" alt="${item.name}" onerror="this.onerror=null; this.src='data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20100%2060%22%3E%3Crect%20width%3D%22100%22%20height%3D%2260%22%20rx%3D%2210%22%20fill%3D%22%231e293b%22/%3E%3Ctext%20x%3D%2250%22%20y%3D%2238%22%20fill%3D%22%2360A5FA%22%20font-family%3D%22sans-serif%22%20font-size%3D%2222%22%20font-weight%3D%22800%22%20text-anchor%3D%22middle%22%3E${item.num || "TV"}%3C/text%3E%3C/svg%3E';" />`
                          : `<span style="font-weight: 800; color: #3b82f6;">${item.num || "TV"}</span>`
                      }
                    </div>
                    <div class="channel-details">
                      <div class="channel-name">${item.num ? `${this._escapeHtml(item.num)}. ` : ""}${this._escapeHtml(item.name)}</div>
                      <div class="channel-sub">${this._escapeHtml(item.category || "Direct")} • ${this._escapeHtml(item.quality || "HD")}</div>
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

  _renderArloAccountsSection() {
    const w = this._arloWizard;
    const accounts = this._arloAccounts || [];

    return `
        <!-- Section 0: Multi-Account Arlo Cloud Protocol -->
        <div class="settings-card">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 12px; margin-bottom: 16px;">
            <h3 style="margin: 0; border-bottom: none; padding-bottom: 0;">
              <span>☁️</span> Comptes Caméras Cloud — Arlo (Multi-Comptes)
            </h3>
            <button class="btn-primary" id="btn-arlo-open-wizard">
              ${w.open ? "✕ Fermer l'assistant" : "➕ Ajouter un compte Arlo"}
            </button>
          </div>
          <p style="color: #8b949e; font-size: 13px; margin: 0 0 16px 0;">
            Connectez un ou plusieurs comptes Arlo en natif (snapshots économie d'énergie &amp; flux RTSPS live à la demande) ou associez des caméras externes déjà présentes dans Home Assistant.
          </p>

          ${
            w.open
              ? `
            <div style="background: rgba(13, 17, 23, 0.78); border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 12px; padding: 18px; margin-bottom: 20px;">
              <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;">
                <button class="btn-arlo-mode-tab ${w.mode === "credentials" ? "btn-primary" : "btn-secondary"}" data-mode="credentials">
                  🔐 Email + Mot de passe + 2FA
                </button>
                <button class="btn-arlo-mode-tab ${w.mode === "token" ? "btn-primary" : "btn-secondary"}" data-mode="token">
                  🔑 Jeton Direct (Authorization Token)
                </button>
              </div>

              ${
                w.error
                  ? `<div style="background: rgba(239,68,68,0.18); border: 1px solid rgba(239,68,68,0.45); color: #fca5a5; padding: 10px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 12px;">⚠️ ${this._escapeHtml(w.error)}</div>`
                  : ""
              }
              ${
                w.message
                  ? `<div style="background: rgba(59,130,246,0.18); border: 1px solid rgba(59,130,246,0.45); color: #93c5fd; padding: 10px 12px; border-radius: 8px; font-size: 13px; margin-bottom: 12px;">ℹ️ ${this._escapeHtml(w.message)}</div>`
                  : ""
              }

              ${
                w.mode === "credentials"
                  ? w.step === "login"
                    ? `
                  <div class="form-grid">
                    <div class="form-group">
                      <label for="arlo-account-name">Nom du compte (Libellé)</label>
                      <input type="text" id="arlo-account-name" class="form-input" placeholder="Ex: Maison, Bureau, Parents..." value="${this._escapeHtml(w.accountName)}" />
                    </div>
                    <div class="form-group">
                      <label for="arlo-email">Adresse e-mail Arlo</label>
                      <input type="email" id="arlo-email" class="form-input" placeholder="prenom.nom@exemple.com" value="${this._escapeHtml(w.email)}" />
                    </div>
                    <div class="form-group">
                      <label for="arlo-password">Mot de passe Arlo</label>
                      <input type="password" id="arlo-password" class="form-input" placeholder="••••••••" value="${this._escapeHtml(w.password)}" />
                    </div>
                  </div>
                  <div style="margin-top: 14px; display: flex; gap: 10px;">
                    <button class="btn-primary" id="btn-arlo-login-submit" ${w.loading ? "disabled" : ""}>
                      ${w.loading ? "⏳ Connexion à Arlo..." : "🔗 Se connecter à Arlo"}
                    </button>
                  </div>
                `
                    : w.step === "factor"
                    ? `
                  <div class="form-group">
                    <label for="arlo-factor-select">Méthode de double authentification (2FA)</label>
                    <select id="arlo-factor-select" class="form-select">
                      ${
                        w.factors && w.factors.length > 0
                          ? w.factors
                              .map(
                                (f) =>
                                  `<option value="${this._escapeHtml(f.factorId)}" ${w.selectedFactorId === f.factorId ? "selected" : ""}>${this._escapeHtml(f.factorType)} — ${this._escapeHtml(f.displayName)}</option>`
                              )
                              .join("")
                          : `<option value="">Aucun facteur détecté</option>`
                      }
                    </select>
                  </div>
                  <div style="margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap;">
                    <button class="btn-primary" id="btn-arlo-send-otp" ${w.loading ? "disabled" : ""}>
                      ${w.loading ? "⏳ Envoi en cours..." : "📩 Envoyer le code de vérification"}
                    </button>
                    <button class="btn-secondary" id="btn-arlo-back-login">← Retour</button>
                  </div>
                `
                    : `
                  <div class="form-grid">
                    <div class="form-group">
                      <label for="arlo-otp-code">Code de vérification à 6 chiffres (OTP)</label>
                      <input type="text" id="arlo-otp-code" class="form-input" placeholder="Ex: 123456" value="${this._escapeHtml(w.otpCode)}" />
                    </div>
                  </div>
                  <div style="margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap;">
                    <button class="btn-primary" id="btn-arlo-verify-otp" ${w.loading ? "disabled" : ""}>
                      ${w.loading ? "⏳ Validation..." : "✅ Valider &amp; Importer les caméras"}
                    </button>
                    <button class="btn-secondary" id="btn-arlo-back-login">← Recommencer</button>
                  </div>
                `
                  : `
                <div style="font-size: 12px; color: #94a3b8; margin-bottom: 12px; line-height: 1.5;">
                  💡 Si Cloudflare bloque l'authentification par mot de passe sur cette IP, connectez-vous sur <code>my.arlo.com</code> dans votre navigateur, copiez l'en-tête <code>Authorization</code> d'une requête réseau et collez-le ci-dessous.
                </div>
                <div class="form-grid">
                  <div class="form-group">
                    <label for="arlo-account-name">Nom du compte (Libellé)</label>
                    <input type="text" id="arlo-account-name" class="form-input" placeholder="Ex: Maison Arlo" value="${this._escapeHtml(w.accountName)}" />
                  </div>
                  <div class="form-group">
                    <label for="arlo-email">E-mail Arlo (optionnel)</label>
                    <input type="email" id="arlo-email" class="form-input" placeholder="prenom.nom@exemple.com" value="${this._escapeHtml(w.email)}" />
                  </div>
                  <div class="form-group" style="grid-column: 1 / -1;">
                    <label for="arlo-token">Jeton Authorization (Token Arlo)</label>
                    <input type="password" id="arlo-token" class="form-input" placeholder="Collez votre jeton Authorization Arlo ici..." value="${this._escapeHtml(w.token)}" />
                  </div>
                  <div class="form-group">
                    <label for="arlo-userid">User ID (optionnel — auto-détecté)</label>
                    <input type="text" id="arlo-userid" class="form-input" placeholder="Auto" value="${this._escapeHtml(w.userId)}" />
                  </div>
                  <div class="form-group">
                    <label for="arlo-xcloudid">xCloudId (optionnel — auto-détecté)</label>
                    <input type="text" id="arlo-xcloudid" class="form-input" placeholder="Auto" value="${this._escapeHtml(w.xcloudId)}" />
                  </div>
                </div>
                <div style="margin-top: 14px; display: flex; gap: 10px;">
                  <button class="btn-primary" id="btn-arlo-save-token" ${w.loading ? "disabled" : ""}>
                    ${w.loading ? "⏳ Vérification..." : "💾 Valider le jeton &amp; Importer"}
                  </button>
                </div>
              `
              }
            </div>
          `
              : ""
          }

          ${
            accounts.length === 0
              ? `<div style="padding: 16px; border: 1px dashed rgba(255,255,255,0.12); border-radius: 10px; color: #8b949e; font-size: 13px; text-align: center;">
                  Aucun compte Arlo Cloud configuré pour le moment. Cliquez sur <strong>➕ Ajouter un compte Arlo</strong> ci-dessus.
                </div>`
              : `
            <div class="discovered-list">
              ${accounts
                .map((acc) => {
                  const isOk = acc.status === "connected";
                  const statusLabel = isOk
                    ? "🟢 Connecté"
                    : acc.status === "token_expired"
                    ? "🟠 Jeton expiré"
                    : "🔴 Déconnecté";
                  const syncStr = acc.last_sync ? this._formatTime(acc.last_sync) : "Jamais";
                  const devs = acc.devices || [];
                  return `
                  <div class="discovered-item" style="flex-direction: column; align-items: stretch; gap: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;">
                      <div>
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                          <span class="badge-protocol ${isOk ? "badge-green" : "badge-orange"}">${statusLabel}</span>
                          <strong style="color: #f0f6fc; font-size: 15px;">${this._escapeHtml(acc.name || acc.email || acc.id)}</strong>
                          ${acc.email ? `<span style="color: #8b949e; font-size: 12px;">(${this._escapeHtml(acc.email)})</span>` : ""}
                        </div>
                        <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">
                          ${acc.camera_count || devs.length} caméra(s) détectée(s) • Dernière synchro : ${this._escapeHtml(syncStr)}
                          ${acc.last_error ? `<span style="color: #fca5a5;"> • ⚠️ ${this._escapeHtml(acc.last_error)}</span>` : ""}
                        </div>
                      </div>
                      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <button class="btn-secondary btn-arlo-sync" data-account-id="${this._escapeHtml(acc.id)}" title="Synchroniser et importer les nouvelles caméras">🔄 Synchroniser</button>
                        <button class="btn-secondary btn-arlo-update-token" data-account-id="${this._escapeHtml(acc.id)}" title="Renouveler le jeton Authorization">🔑 Jeton</button>
                        <button class="btn-danger btn-arlo-delete-acc" data-account-id="${this._escapeHtml(acc.id)}" title="Supprimer ce compte Arlo">🗑️</button>
                      </div>
                    </div>

                    ${
                      devs.length > 0
                        ? `
                      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 10px;">
                        ${devs
                          .map(
                            (dev) => `
                          <div style="background: rgba(15,23,42,0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 10px; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                            <div style="min-width: 0;">
                              <div style="font-weight: 600; color: #f0f6fc; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${this._escapeHtml(dev.name)}</div>
                              <div style="font-size: 11px; color: #8b949e;">
                                ${this._escapeHtml(dev.model_id || "Arlo")}
                                ${dev.battery_level !== null && dev.battery_level !== undefined ? ` • 🔋 ${this._escapeHtml(dev.battery_level)}%` : ""}
                              </div>
                            </div>
                            ${
                              dev.already_added
                                ? `<span class="badge-already-added" style="font-size: 11px; padding: 3px 8px;">✓ Intégrée</span>`
                                : `<button class="btn-primary btn-arlo-add-dev" data-account-id="${this._escapeHtml(acc.id)}" data-device-id="${this._escapeHtml(dev.device_id)}" style="padding: 5px 10px; font-size: 11px;">+ Ajouter</button>`
                            }
                          </div>
                        `
                          )
                          .join("")}
                      </div>
                    `
                        : ""
                    }
                  </div>
                `;
                })
                .join("")}
            </div>
          `
          }
        </div>
    `;
  }

  _renderSettings() {
    return `
      <div class="settings-container">
        ${this._renderArloAccountsSection()}
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
              <input type="text" id="pair-ssid" class="form-input" placeholder="Ex: MonReseauWifi" value="${this._pairSsid || ""}" />
            </div>

            <div class="form-group">
              <label for="pair-pass">Mot de passe du Wi-Fi</label>
              <input type="password" id="pair-pass" class="form-input" placeholder="••••••••" value="${this._pairPass || ""}" />
            </div>

            <div class="form-group">
              <label for="pair-ap-ip">IP de la caméra en mode Point d'Accès (Routeur)</label>
              <input type="text" id="pair-ap-ip" class="form-input" value="${this._pairApIp || "192.168.1.1"}" placeholder="Ex: 192.168.1.1 ou 192.168.10.1" />
            </div>
          </div>

          ${
            this._selectedCameraAp
              ? `
            <div style="font-size: 13px; color: #34d399; margin-top: 10px; display: flex; align-items: center; gap: 8px;">
              <span>🎯 Caméra AP sélectionnée :</span>
              <strong style="background: rgba(16, 185, 129, 0.2); padding: 3px 8px; border-radius: 4px; color: #6ee7b7;">${this._selectedCameraAp}</strong>
              <button id="btn-clear-ap-sel" style="background: transparent; border: 1px solid rgba(255,255,255,0.2); color: #94a3b8; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 11px;">✕ Désélectionner</button>
            </div>
          `
              : ""
          }

          ${
            this._detectedAps && this._detectedAps.length > 0
              ? `
            <div style="background: rgba(30, 41, 59, 0.6); padding: 12px 14px; border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.3); margin-top: 14px;">
              <div style="font-size: 13px; font-weight: 600; color: #93c5fd; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
                <span>🎯 Réseaux Wi-Fi de caméras détectés à proximité :</span>
                <span style="font-size: 11px; color: #94a3b8;">Cliquez sur un réseau pour l'associer</span>
              </div>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                ${this._detectedAps
                  .filter((a) => a.is_camera)
                  .map(
                    (ap) => `
                  <button class="btn-ap-chip" data-ssid="${ap.ssid}" style="background: ${this._selectedCameraAp === ap.ssid ? "#2563eb" : "rgba(15, 23, 42, 0.85)"}; border: 1px solid ${this._selectedCameraAp === ap.ssid ? "#60a5fa" : "#3b82f6"}; color: #fff; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; transition: all 0.2s ease;">
                    📶 <strong>${ap.ssid}</strong> (${ap.signal}%)
                  </button>
                `
                  )
                  .join("")}
                ${this._detectedAps.filter((a) => a.is_camera).length === 0 ? `<div style="font-size: 12px; color: #94a3b8;">Aucun point d'accès caméra identifié. Vérifiez que la caméra clignote en bleu et relancez le scan.</div>` : ""}
              </div>
            </div>
          `
              : ""
          }

          <div style="margin-top: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
            <button class="btn-primary" id="btn-start-pairing" ${this._pairingActive ? "disabled" : ""}>
              ${this._pairingActive ? "⏳ Appairage en cours..." : "🚀 Lancer l'appairage"}
            </button>
            ${
              this._pairingActive
                ? `<button class="btn-danger" id="btn-stop-pairing">🛑 Annuler l'appairage</button>`
                : ""
            }
            <button class="btn-secondary" id="btn-scan-aps">
              📡 Scanner Wi-Fi Caméras
            </button>
            <button class="btn-secondary" id="btn-scan-lan" ${this._isScanning ? "disabled" : ""}>
              ${this._isScanning ? "⏳ Scan en cours..." : "🔍 Scanner le réseau & Détecter les caméras"}
            </button>
            <button class="btn-secondary" id="btn-show-qr">
              ${this._showQrCode ? "✕ Masquer QR Code" : "📱 Afficher QR Code Caméra"}
            </button>
          </div>

          ${
            this._showQrCode
              ? `
            <div style="background: #ffffff; color: #0f172a; padding: 20px; border-radius: 12px; margin-top: 16px; text-align: center; max-width: 320px; margin-left: auto; margin-right: auto; box-shadow: 0 8px 30px rgba(0,0,0,0.5);">
              <div style="font-weight: 700; font-size: 15px; margin-bottom: 4px; color: #0f172a;">Appairage Optique QR Code</div>
              <div style="font-size: 12px; color: #475569; margin-bottom: 12px;">Pointez l'objectif de la caméra vers ce code à 15-20 cm</div>
              <div id="camera-qr-container" style="display: flex; justify-content: center; margin: 12px 0; min-height: 200px;"></div>
              <div style="font-size: 11px; color: #334155; font-family: monospace; background: #f1f5f9; padding: 6px; border-radius: 6px; word-break: break-all;">
                Réseau : <strong>${this._pairSsid || "Non spécifié"}</strong>
              </div>
            </div>
          `
              : ""
          }

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
                  ? this._pairingLogs.map((l) => `<div>> ${this._escapeHtml(l)}</div>`).join("")
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
                        <strong style="color: #f0f6fc; font-size: 14px;">${this._escapeHtml(dev.name || dev.model)}</strong>
                      </div>
                      <div style="font-size: 12px; color: #8b949e;">
                        IP: <code style="color: #60a5fa;">${dev.host}${dev.port ? `:${dev.port}` : ""}</code>
                        ${dev.model ? ` • Modèle : ${this._escapeHtml(dev.model)}` : ""}
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
                        <strong style="color: #f0f6fc; font-size: 14px;">${this._escapeHtml(dev.name)}</strong>
                        ${dev.model ? `<span style="font-size: 12px; color: #8b949e;">(${this._escapeHtml(dev.model)})</span>` : ""}
                      </div>
                      <div style="font-size: 12px; color: #8b949e;">
                        Entité HA: <code style="color: #e2e8f0;">${dev.entity_id || dev.host}</code>
                      </div>
                      <div class="reason-box">
                        <strong>⚠️ Raison de non-intégration directe :</strong> ${this._escapeHtml(dev.reason)}
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
                        <input type="text" class="form-input cam-input-name" data-id="${cam.id}" value="${this._escapeHtml(cam.name)}" style="width: 140px;" />
                      </td>
                      <td>
                        <input type="text" class="form-input cam-input-desc" data-id="${cam.id}" value="${this._escapeHtml(cam.description || "")}" placeholder="Ex: Salon grand angle" style="width: 200px;" />
                      </td>
                      <td>
                        <input type="text" class="form-input cam-input-host" data-id="${cam.id}" value="${this._escapeHtml(cam.host)}" style="width: 130px;" />
                      </td>
                      <td>
                        <select class="form-select cam-input-driver" data-id="${cam.id}">
                          <option value="arlo_cloud" ${cam.driver === "arlo_cloud" ? "selected" : ""}>Arlo Cloud Direct</option>
                          <option value="ysxlite_pppp" ${cam.driver === "ysxlite_pppp" ? "selected" : ""}>YsxLite PPPP</option>
                          <option value="generic_rtsp" ${cam.driver === "generic_rtsp" ? "selected" : ""}>RTSP / ONVIF</option>
                          <option value="generic_mjpeg" ${cam.driver === "generic_mjpeg" ? "selected" : ""}>MJPEG / HTTP (Webcam & ESP32-CAM)</option>
                          <option value="ha_proxy" ${cam.driver === "ha_proxy" ? "selected" : ""}>Passerelle HA</option>
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
        this._fetchArloAccounts(true);
      };
    }

    this._bindArloEvents();

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

    // Toolbar Controls
    const densityBtns = this.shadowRoot.querySelectorAll(".density-btn");
    densityBtns.forEach((btn) => {
      btn.onclick = () => this._setGridDensity(btn.dataset.density);
    });

    const refreshAllBtn = this.shadowRoot.querySelector("#btn-refresh-all");
    if (refreshAllBtn) {
      refreshAllBtn.onclick = () => this._refreshAllSnapshots();
    }

    const toggleAllLiveBtn = this.shadowRoot.querySelector("#btn-toggle-all-live");
    if (toggleAllLiveBtn) {
      toggleAllLiveBtn.onclick = () => this._toggleAllLive();
    }

    // Live Toggles
    const liveBtns = this.shadowRoot.querySelectorAll(".live-btn");
    liveBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this._toggleLive(btn.dataset.camId);
      };
    });

    // Quick Viewport Action Buttons (Refresh, IR, Fit Mode, Lightbox)
    const snapRefreshBtns = this.shadowRoot.querySelectorAll(".btn-snap-refresh");
    snapRefreshBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const camId = btn.dataset.camId;
        const cam = this._cameras.find((c) => c.id === camId);
        const img = this.shadowRoot.querySelector(`.camera-card[data-id="${camId}"] .cam-media-slot img.cam-media`);
        if (cam && img) {
          this._preloadAndSwapSnapshot(img, cam, true);
        }
      };
    });

    const irToggleBtns = this.shadowRoot.querySelectorAll(".btn-ir-toggle");
    irToggleBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this._toggleNightVision(btn.dataset.camId);
      };
    });

    const fitToggleBtns = this.shadowRoot.querySelectorAll(".btn-fit-toggle");
    fitToggleBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this._toggleFitMode(btn.dataset.camId);
      };
    });

    const fsCamBtns = this.shadowRoot.querySelectorAll(".btn-cam-fullscreen");
    fsCamBtns.forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        this._openLightbox(btn.dataset.camId);
      };
    });

    const viewports = this.shadowRoot.querySelectorAll(".viewport[data-cam-id]");
    viewports.forEach((vp) => {
      vp.ondblclick = (e) => {
        e.stopPropagation();
        this._openLightbox(vp.dataset.camId);
      };
    });

    // Attach media fallback & HLS video player for active cards
    const mediaSlots = this.shadowRoot.querySelectorAll(".cam-media-slot[data-cam-id]");
    mediaSlots.forEach((slot) => {
      const camId = slot.dataset.camId;
      const cam = this._cameras.find((c) => c.id === camId);
      if (!cam) return;
      const isLive = this._liveCameras.has(camId);
      const useVideoPlayer = isLive && Boolean(cam.channel_id || (cam.hls_url && cam.hls_url.includes(".m3u8")));
      if (useVideoPlayer) {
        this._bindCameraMediaElement(slot, cam, true);
      } else {
        const img = slot.querySelector("img.cam-media");
        if (img) {
          img.onerror = () => {
            if (this._liveCameras.has(camId)) {
              this._startLiveFramePump(camId, img);
            } else {
              this._loadSnapshotWithFallback(img, camId);
            }
          };
        }
      }
    });

    if (this._fullscreenCamId && this._activeTab === "cameras") {
      this._renderLightboxContent(this._fullscreenCamId);
    }

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

    // Input persistence on typing (prevents resets)
    const ssidInput = this.shadowRoot.querySelector("#pair-ssid");
    if (ssidInput) {
      ssidInput.oninput = (e) => {
        this._pairSsid = e.target.value.trim();
        try { localStorage.setItem("domolink_pair_ssid", this._pairSsid); } catch (err) {}
      };
    }

    const passInput = this.shadowRoot.querySelector("#pair-pass");
    if (passInput) {
      passInput.oninput = (e) => {
        this._pairPass = e.target.value;
        try { localStorage.setItem("domolink_pair_pass", this._pairPass); } catch (err) {}
      };
    }

    const apIpInput = this.shadowRoot.querySelector("#pair-ap-ip");
    if (apIpInput) {
      apIpInput.oninput = (e) => {
        this._pairApIp = e.target.value.trim();
        try { localStorage.setItem("domolink_pair_ap_ip", this._pairApIp); } catch (err) {}
      };
    }

    // Pairing buttons
    const startPairBtn = this.shadowRoot.querySelector("#btn-start-pairing");
    if (startPairBtn) {
      startPairBtn.onclick = () => this._startPairing();
    }

    const stopPairBtn = this.shadowRoot.querySelector("#btn-stop-pairing");
    if (stopPairBtn) {
      stopPairBtn.onclick = () => this._stopPairing();
    }

    const scanApsBtn = this.shadowRoot.querySelector("#btn-scan-aps");
    if (scanApsBtn) {
      scanApsBtn.onclick = () => this._scanCameraAps();
    }

    const scanLanBtn = this.shadowRoot.querySelector("#btn-scan-lan");
    if (scanLanBtn) {
      scanLanBtn.onclick = () => this._scanLocalNetwork();
    }

    const showQrBtn = this.shadowRoot.querySelector("#btn-show-qr");
    if (showQrBtn) {
      showQrBtn.onclick = () => {
        this._showQrCode = !this._showQrCode;
        this.render();
      };
    }

    const clearApBtn = this.shadowRoot.querySelector("#btn-clear-ap-sel");
    if (clearApBtn) {
      clearApBtn.onclick = () => {
        this._selectedCameraAp = null;
        this.render();
      };
    }

    const apChips = this.shadowRoot.querySelectorAll(".btn-ap-chip");
    apChips.forEach((btn) => {
      btn.onclick = () => {
        this._selectedCameraAp = btn.dataset.ssid;
        this._pairApIp = "192.168.1.1";
        this._appendLog(`🎯 Point d'accès caméra sélectionné : ${btn.dataset.ssid}`);
        this.render();
      };
    });

    if (this._showQrCode) {
      const qrTarget = this.shadowRoot.querySelector("#camera-qr-container");
      if (qrTarget) {
        this._renderQrCode(qrTarget);
      }
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

    // Category pills filter (without destroying playing video)
    const catPills = this.shadowRoot.querySelectorAll(".category-pill");
    catPills.forEach((pill) => {
      pill.onclick = () => {
        this._tvFilter = pill.dataset.category;
        catPills.forEach((p) => p.classList.toggle("active", p === pill));
        this._updateChannelGrid();
      };
    });

    // Search input
    const searchInp = this.shadowRoot.querySelector("#tv-search-input");
    if (searchInp) {
      searchInp.oninput = (e) => {
        this._tvSearch = e.target.value;
        this._updateChannelGrid();
      };
    }

    // Channel cards click
    this._bindChannelCards();
  }

  _bindArloEvents() {
    const root = this.shadowRoot;
    const w = this._arloWizard;

    const openBtn = root.querySelector("#btn-arlo-open-wizard");
    if (openBtn) {
      openBtn.onclick = () => {
        this._resetArloWizard(!w.open, "credentials");
        this.render();
      };
    }

    root.querySelectorAll(".btn-arlo-mode-tab").forEach((btn) => {
      btn.onclick = () => {
        w.mode = btn.dataset.mode || "credentials";
        w.step = "login";
        w.error = "";
        w.message = "";
        this.render();
      };
    });

    const bindInput = (sel, key) => {
      const el = root.querySelector(sel);
      if (el) {
        el.oninput = (e) => {
          w[key] = e.target.value;
        };
      }
    };
    bindInput("#arlo-account-name", "accountName");
    bindInput("#arlo-email", "email");
    bindInput("#arlo-password", "password");
    bindInput("#arlo-otp-code", "otpCode");
    bindInput("#arlo-token", "token");
    bindInput("#arlo-userid", "userId");
    bindInput("#arlo-xcloudid", "xcloudId");

    const factorSelect = root.querySelector("#arlo-factor-select");
    if (factorSelect) {
      factorSelect.onchange = (e) => {
        w.selectedFactorId = e.target.value;
      };
    }

    const loginBtn = root.querySelector("#btn-arlo-login-submit");
    if (loginBtn) loginBtn.onclick = () => this._startArloLogin();

    const sendOtpBtn = root.querySelector("#btn-arlo-send-otp");
    if (sendOtpBtn) sendOtpBtn.onclick = () => this._requestArlo2faCode();

    const verifyOtpBtn = root.querySelector("#btn-arlo-verify-otp");
    if (verifyOtpBtn) verifyOtpBtn.onclick = () => this._verifyArlo2faCode();

    const backBtn = root.querySelector("#btn-arlo-back-login");
    if (backBtn) {
      backBtn.onclick = () => {
        w.step = "login";
        w.error = "";
        w.message = "";
        this.render();
      };
    }

    const saveTokenBtn = root.querySelector("#btn-arlo-save-token");
    if (saveTokenBtn) saveTokenBtn.onclick = () => this._saveArloDirectToken();

    root.querySelectorAll(".btn-arlo-sync").forEach((btn) => {
      btn.onclick = () => this._syncArloAccount(btn.dataset.accountId, true);
    });

    root.querySelectorAll(".btn-arlo-update-token").forEach((btn) => {
      btn.onclick = () => {
        const acc = (this._arloAccounts || []).find((a) => a.id === btn.dataset.accountId);
        this._resetArloWizard(true, "token", acc || null);
        this.render();
      };
    });

    root.querySelectorAll(".btn-arlo-delete-acc").forEach((btn) => {
      btn.onclick = () => this._deleteArloAccount(btn.dataset.accountId);
    });

    root.querySelectorAll(".btn-arlo-add-dev").forEach((btn) => {
      btn.onclick = () => {
        const accId = btn.dataset.accountId;
        const devId = btn.dataset.deviceId;
        const acc = (this._arloAccounts || []).find((a) => a.id === accId);
        const dev = acc && (acc.devices || []).find((d) => String(d.device_id) === String(devId));
        if (dev) {
          this._addArloCameraFromAccount(accId, dev);
        }
      };
    });
  }

  _updateChannelGrid() {
    const grid = this.shadowRoot.querySelector(".channel-grid");
    if (!grid) return;
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
                    ? `<img src="${item.logo}" class="channel-logo-img" alt="${item.name}" onerror="this.onerror=null; this.src='data:image/svg+xml;utf8,%3Csvg%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%20viewBox%3D%220%200%20100%2060%22%3E%3Crect%20width%3D%22100%22%20height%3D%2260%22%20rx%3D%2210%22%20fill%3D%22%231e293b%22/%3E%3Ctext%20x%3D%2250%22%20y%3D%2238%22%20fill%3D%22%2360A5FA%22%20font-family%3D%22sans-serif%22%20font-size%3D%2222%22%20font-weight%3D%22800%22%20text-anchor%3D%22middle%22%3E${item.num || "TV"}%3C/text%3E%3C/svg%3E';" />`
                    : `<span style="font-weight: 800; color: #3b82f6;">${item.num || "TV"}</span>`
                }
              </div>
              <div class="channel-details">
                <div class="channel-name">${item.num ? `${this._escapeHtml(item.num)}. ` : ""}${this._escapeHtml(item.name)}</div>
                <div class="channel-sub">${this._escapeHtml(item.category || "Direct")} • ${this._escapeHtml(item.quality || "HD")}</div>
              </div>
            </div>
          `;
            })
            .join("")
        : `<div style="grid-column: 1 / -1; text-align: center; color: #8b949e; padding: 40px 0;">Aucune chaîne trouvée.</div>`;

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
