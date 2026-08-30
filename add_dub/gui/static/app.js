// add_dub/gui/static/app.js
(function () {
    "use strict";

    let state = {
        isRunning: false,
        regionsByLang: {},
        voicesByRegion: {},
        currentEngine: "onecore",
    };

    // Éléments du DOM
    const inputPath = document.getElementById("input_path");
    const outputDir = document.getElementById("output_dir");
    const btnBrowseFile = document.getElementById("btn_browse_file");
    const btnBrowseFolder = document.getElementById("btn_browse_folder");
    const btnBrowseOutput = document.getElementById("btn_browse_output");

    const chkRecursive = document.getElementById("recursive");
    const chkPreserveTree = document.getElementById("preserve_tree");
    const chkSkipExisting = document.getElementById("skip_existing");
    const chkOverwrite = document.getElementById("overwrite");

    const selEngine = document.getElementById("tts_engine");
    const selVoiceLang = document.getElementById("voice_lang");
    const selVoiceRegion = document.getElementById("voice_region");
    const selVoiceId = document.getElementById("voice_id");
    const btnTestVoice = document.getElementById("btn_test_voice");
    const numMinRate = document.getElementById("min_rate_tts");
    const numMaxRate = document.getElementById("max_rate_tts");

    const selSubMode = document.getElementById("sub_mode");
    const numSubIndex = document.getElementById("sub_index");
    const chkTranslate = document.getElementById("translate");
    const txtTrFrom = document.getElementById("translate_from");
    const txtTrTo = document.getElementById("translate_to");
    const chkReuseSubs = document.getElementById("reuse_translated_subs");

    const selAudioIndex = document.getElementById("audio_index");
    const numDucking = document.getElementById("ducking_db");
    const numBgMix = document.getElementById("bg_mix");
    const numTtsMix = document.getElementById("tts_mix");
    const numOffsetMs = document.getElementById("offset_ms");
    const numOffsetVid = document.getElementById("offset_video_ms");
    const selCodec = document.getElementById("audio_codec");
    const selBitrate = document.getElementById("audio_bitrate");
    const txtOrigLang = document.getElementById("orig_audio_lang");

    const chkLimitDuration = document.getElementById("limit_duration");
    const numLimitSec = document.getElementById("limit_duration_sec");
    const btnRun = document.getElementById("btn_run");
    const progressFill = document.getElementById("progress_fill");
    const progressPercentBadge = document.getElementById("progress_percent_badge");
    const progressBarContainer = document.getElementById("progress_bar_container");
    const statusText = document.getElementById("status_text");

    // Initialisation
    window.addEventListener("DOMContentLoaded", () => {
        setupEventListeners();
        connectEventSource();
        loadInitialOptions();
    });

    function setupEventListeners() {
        // Navigation / Parcourir
        btnBrowseFile.addEventListener("click", () => browsePath("/api/browse-file", inputPath));
        btnBrowseFolder.addEventListener("click", () => browsePath("/api/browse-folder", inputPath));
        btnBrowseOutput.addEventListener("click", () => browsePath("/api/browse-folder", outputDir));

        // Checkboxes mutuellement exclusives
        chkOverwrite.addEventListener("change", () => {
            if (chkOverwrite.checked) {
                chkSkipExisting.checked = false;
            }
        });
        chkSkipExisting.addEventListener("change", () => {
            if (chkSkipExisting.checked) {
                chkOverwrite.checked = false;
            }
        });

        // Mode sous-titres
        selSubMode.addEventListener("change", onSubModeToggle);

        // Limite de test
        chkLimitDuration.addEventListener("change", onLimitDurationToggle);

        // Moteur TTS & Voix (Cascade à 3 niveaux)
        selEngine.addEventListener("change", () => onEngineChanged(selEngine.value));
        selVoiceLang.addEventListener("change", () => onLanguageChanged());
        selVoiceRegion.addEventListener("change", () => onRegionChanged());
        btnTestVoice.addEventListener("click", onTestVoice);

        // Traduction Toggle
        chkTranslate.addEventListener("change", onTranslateToggle);

        // Bouton Démarrer / Arrêter
        btnRun.addEventListener("click", onToggleRun);
    }

    function onSubModeToggle() {
        const isMkv = selSubMode.value === "mkv";
        numSubIndex.disabled = !isMkv;
    }

    function onLimitDurationToggle() {
        numLimitSec.disabled = !chkLimitDuration.checked;
    }

    async function browsePath(endpoint, targetInput) {
        try {
            const res = await fetch(endpoint, { method: "POST" });
            const data = await res.json();
            if (data.path) {
                targetInput.value = data.path;
            }
        } catch (err) {
            console.error("Erreur lors de la sélection du chemin :", err);
        }
    }

    async function loadInitialOptions() {
        try {
            const res = await fetch("/api/options");
            const opts = await res.json();

            if (opts.input_dir) inputPath.value = opts.input_dir;
            if (opts.output_dir) outputDir.value = opts.output_dir;

            chkPreserveTree.checked = !!opts.preserve_tree;
            numMinRate.value = opts.min_rate_tts || 1.2;
            numMaxRate.value = opts.max_rate_tts || 1.8;

            numDucking.value = opts.ducking_db || -5.0;
            numBgMix.value = opts.bg_mix || 1.0;
            numTtsMix.value = opts.tts_mix || 1.0;
            numOffsetMs.value = opts.offset_ms || 0;
            numOffsetVid.value = opts.offset_video_ms || 0;

            if (opts.audio_codec) selCodec.value = opts.audio_codec;
            if (opts.audio_bitrate) selBitrate.value = opts.audio_bitrate;
            if (opts.orig_audio_lang) txtOrigLang.value = opts.orig_audio_lang;

            chkTranslate.checked = !!opts.translate;
            if (opts.translate_to) txtTrTo.value = opts.translate_to;
            if (opts.translate_from) txtTrFrom.value = opts.translate_from;
            chkReuseSubs.checked = !!opts.reuse_translated_subs;

            onTranslateToggle();
            onSubModeToggle();
            onLimitDurationToggle();

            if (opts.tts_engine) {
                selEngine.value = opts.tts_engine;
            }
            await onEngineChanged(selEngine.value, opts.voice_id);
        } catch (err) {
            console.error("Erreur chargement options :", err);
        }
    }

    async function onEngineChanged(engine, targetVoiceId = null) {
        state.currentEngine = engine;
        try {
            const res = await fetch(`/api/voices?engine=${encodeURIComponent(engine)}`);
            const data = await res.json();
            state.regionsByLang = data.regions_by_lang || {};
            state.voicesByRegion = data.voices_by_region || {};

            selVoiceLang.innerHTML = "";
            const langs = data.languages || [];

            let selectedLang = langs.length > 0 ? langs[0].code : "fr";
            langs.forEach(l => {
                const opt = document.createElement("option");
                opt.value = l.code;
                opt.textContent = l.name;
                if (l.code === "fr") {
                    selectedLang = "fr";
                }
                selVoiceLang.appendChild(opt);
            });

            selVoiceLang.value = selectedLang;
            onLanguageChanged(targetVoiceId);
        } catch (err) {
            console.error("Erreur récupération voix :", err);
        }
    }

    function onLanguageChanged(targetVoiceId = null) {
        const langCode = selVoiceLang.value;
        const regions = state.regionsByLang[langCode] || [];

        selVoiceRegion.innerHTML = "";
        let selectedRegion = regions.length > 0 ? regions[0].code : "";

        regions.forEach(r => {
            const opt = document.createElement("option");
            opt.value = r.code;
            opt.textContent = r.name;
            if (r.code.toLowerCase() === `${langCode}-${langCode}`.toLowerCase() || r.code === "fr-FR" || r.code === "en-US") {
                selectedRegion = r.code;
            }
            selVoiceRegion.appendChild(opt);
        });

        selVoiceRegion.value = selectedRegion;
        onRegionChanged(targetVoiceId);
    }

    function onRegionChanged(targetVoiceId = null) {
        const regionCode = selVoiceRegion.value;
        const voices = state.voicesByRegion[regionCode] || [];

        selVoiceId.innerHTML = "";
        voices.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v.id;
            opt.textContent = v.display_name;
            selVoiceId.appendChild(opt);
        });

        if (targetVoiceId) {
            selVoiceId.value = targetVoiceId;
        } else if (voices.length > 0) {
            selVoiceId.value = voices[0].id;
        }
    }

    function onTranslateToggle() {
        const disabled = !chkTranslate.checked;
        txtTrFrom.disabled = disabled;
        txtTrTo.disabled = disabled;
    }

    async function onTestVoice() {
        btnTestVoice.disabled = true;
        btnTestVoice.textContent = "Génération...";

        const payload = {
            tts_engine: selEngine.value,
            voice_id: selVoiceId.value,
            lang: selVoiceRegion.value || selVoiceLang.value || "fr-FR",
            min_rate_tts: parseFloat(numMinRate.value) || 1.2,
            max_rate_tts: parseFloat(numMaxRate.value) || 1.8,
        };

        try {
            await fetch("/api/test-voice", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        } catch (err) {
            console.error("Erreur test vocal :", err);
        } finally {
            setTimeout(() => {
                btnTestVoice.disabled = false;
                btnTestVoice.textContent = "Tester la voix";
            }, 1000);
        }
    }

    async function onToggleRun() {
        if (state.isRunning) {
            btnRun.disabled = true;
            btnRun.textContent = "ARRÊT DEMANDÉ...";
            try {
                await fetch("/api/stop", { method: "POST" });
            } catch (err) {
                console.error("Erreur arrêt :", err);
            }
            return;
        }

        const payload = {
            input_path: inputPath.value.trim(),
            output_dir: outputDir.value.trim(),
            recursive: chkRecursive.checked,
            preserve_tree: chkPreserveTree.checked,
            skip_existing: chkSkipExisting.checked,
            overwrite: chkOverwrite.checked,

            tts_engine: selEngine.value,
            voice_id: selVoiceId.value,
            voice_lang: selVoiceRegion.value || selVoiceLang.value || "fr-FR",
            min_rate_tts: parseFloat(numMinRate.value) || 1.2,
            max_rate_tts: parseFloat(numMaxRate.value) || 1.8,

            sub_mode: selSubMode.value,
            sub_index: parseInt(numSubIndex.value, 10) || 0,
            translate: chkTranslate.checked,
            translate_from: txtTrFrom.value.trim(),
            translate_to: txtTrTo.value.trim(),
            reuse_translated_subs: chkReuseSubs.checked,

            audio_index: selAudioIndex.value,
            ducking_db: parseFloat(numDucking.value) || -5.0,
            bg_mix: parseFloat(numBgMix.value) || 1.0,
            tts_mix: parseFloat(numTtsMix.value) || 1.0,
            offset_ms: parseInt(numOffsetMs.value, 10) || 0,
            offset_video_ms: parseInt(numOffsetVid.value, 10) || 0,
            audio_codec: selCodec.value,
            audio_bitrate: selBitrate.value,
            orig_audio_lang: txtOrigLang.value.trim() || "Original",

            limit_duration: chkLimitDuration.checked,
            limit_duration_sec: parseInt(numLimitSec.value, 10) || 60,
        };

        if (!payload.input_path) {
            alert("Veuillez spécifier un fichier ou un dossier d'entrée.");
            return;
        }

        try {
            const res = await fetch("/api/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.error) {
                alert("Erreur : " + data.error);
            }
        } catch (err) {
            alert("Impossible de démarrer le traitement : " + err);
        }
    }

    function setRunningState(running) {
        state.isRunning = running;
        if (running) {
            btnRun.textContent = "ARRÊTER LE DOUBLAGE";
            btnRun.classList.remove("btn-primary");
            btnRun.classList.add("btn-danger");
            btnRun.disabled = false;
        } else {
            btnRun.textContent = "DÉMARRER LE DOUBLAGE";
            btnRun.classList.remove("btn-danger");
            btnRun.classList.add("btn-primary");
            btnRun.disabled = false;
        }
    }

    function connectEventSource() {
        const evtSource = new EventSource("/api/events");

        evtSource.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "status" || msg.type === "log") {
                    statusText.textContent = msg.data;
                } else if (msg.type === "error") {
                    statusText.textContent = "[Erreur] " + msg.data;
                } else if (msg.type === "progress") {
                    const pct = Math.max(0, Math.min(100, Math.round(parseFloat(msg.data))));
                    progressFill.style.width = pct + "%";
                    if (progressPercentBadge) progressPercentBadge.textContent = pct + " %";
                    if (progressBarContainer) {
                        progressBarContainer.setAttribute("aria-valuenow", pct);
                        progressBarContainer.setAttribute("aria-valuetext", "Progression : " + pct + " %");
                    }
                } else if (msg.type === "started") {
                    setRunningState(true);
                    if (progressPercentBadge) progressPercentBadge.textContent = "0 %";
                    progressFill.style.width = "0%";
                } else if (msg.type === "finished") {
                    setRunningState(false);
                    if (progressPercentBadge) progressPercentBadge.textContent = "100 %";
                    progressFill.style.width = "100%";
                }
            } catch (e) {
                // Ignore parse errors on keepalive
            }
        };

        evtSource.onerror = () => {
            // Reconnexion automatique gérée par EventSource
        };

        // Heartbeat périodique toutes les 2 secondes
        setInterval(() => {
            fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
        }, 2000);

        // Signaler l'arrêt lors de la fermeture de la fenêtre
        window.addEventListener("beforeunload", () => {
            if (navigator.sendBeacon) {
                navigator.sendBeacon("/api/shutdown", "");
            }
        });
    }
})();
