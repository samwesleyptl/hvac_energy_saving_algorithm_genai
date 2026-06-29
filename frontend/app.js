/* =========================================
   Smart AC Energy Saving Agent — App Logic
   ========================================= */

(function() {
    'use strict';

    // ---- Config ----
    const API_BASE = window.location.origin;
    let apiKey = '';
    let autoSimulate = false;
    let autoInterval = null;
    const SIM_INTERVAL_MS = 2000; // tick every 2 seconds

    // ---- DOM Refs ----
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const dom = {
        statusDot: $('#statusDot'),
        statusLabel: $('#statusLabel'),
        acPowerBadge: $('#acPowerBadge'),
        dialSetpoint: $('#dialSetpoint'),
        ringFill: $('#ringFill'),
        acModeTag: $('#acModeTag'),
        acFanSpeed: $('#acFanSpeed'),
        indoorTemp: $('#indoorTemp'),
        baselineTemp: $('#baselineTemp'),
        
        sliderOutdoor: $('#sliderOutdoor'),
        sliderTarget: $('#sliderTarget'),
        sliderHumidity: $('#sliderHumidity'),
        sliderHour: $('#sliderHour'),
        valOutdoor: $('#valOutdoor'),
        valTarget: $('#valTarget'),
        valHumidity: $('#valHumidity'),
        valHour: $('#valHour'),
        
        btnOccupancy: $('#btnOccupancy'),
        occupancyText: $('#occupancyText'),
        btnApplyEnv: $('#btnApplyEnv'),
        
        btnRunOptimize: $('#btnRunOptimize'),
        btnAutoToggle: $('#btnAutoToggle'),
        btnResetMetrics: $('#btnResetMetrics'),
        
        graphNodes: {
            retrieve: $('#nodeRetrieve'),
            optimize: $('#nodeOptimize'),
            validate: $('#nodeValidate')
        },
        graphEdges: $$('.graph-edge'),
        
        timeLabel: $('#timeLabel'),
        metricAgentKwh: $('#metricAgentKwh'),
        metricBaselineKwh: $('#metricBaselineKwh'),
        metricSavingsUsd: $('#metricSavingsUsd'),
        metricCo2: $('#metricCo2'),
        metricRate: $('#metricRate'),
        metricSavingsPct: $('#metricSavingsPct'),
        
        policiesList: $('#policiesList'),
        logContainer: $('#logContainer'),
        btnClearLog: $('#btnClearLog'),
        
        btnApiKey: $('#btnApiKey'),
        modalOverlay: $('#modalOverlay'),
        inputApiKey: $('#inputApiKey'),
        btnModalCancel: $('#btnModalCancel'),
        btnModalSave: $('#btnModalSave'),
    };

    let occupancy = true;

    // ---- Utility ----
    function formatTemp(v) { return parseFloat(v).toFixed(1) + '°C'; }
    function formatHour(h) {
        const hrs = Math.floor(h);
        const mins = Math.round((h - hrs) * 60);
        return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
    }

    // ---- Slider Live Updates ----
    function initSliders() {
        dom.sliderOutdoor.addEventListener('input', () => {
            dom.valOutdoor.textContent = formatTemp(dom.sliderOutdoor.value);
        });
        dom.sliderTarget.addEventListener('input', () => {
            dom.valTarget.textContent = formatTemp(dom.sliderTarget.value);
        });
        dom.sliderHumidity.addEventListener('input', () => {
            dom.valHumidity.textContent = dom.sliderHumidity.value + '%';
        });
        dom.sliderHour.addEventListener('input', () => {
            dom.valHour.textContent = formatHour(parseFloat(dom.sliderHour.value));
        });
    }

    // ---- Occupancy Toggle ----
    function initOccupancyToggle() {
        dom.btnOccupancy.addEventListener('click', () => {
            occupancy = !occupancy;
            dom.btnOccupancy.classList.toggle('active', occupancy);
            dom.occupancyText.textContent = occupancy ? 'Occupied' : 'Unoccupied';
        });
    }

    // ---- API Calls ----
    async function apiGet(path) {
        try {
            const res = await fetch(`${API_BASE}${path}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            addLog(`API Error (GET ${path}): ${err.message}`, 'warning');
            return null;
        }
    }

    async function apiPost(path, body = {}) {
        try {
            const res = await fetch(`${API_BASE}${path}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (err) {
            addLog(`API Error (POST ${path}): ${err.message}`, 'warning');
            return null;
        }
    }

    // ---- Update UI from state ----
    function updateDashboard(state) {
        if (!state) return;

        // AC Status
        const isOn = state.ac_power === 'ON';
        dom.acPowerBadge.textContent = state.ac_power;
        dom.acPowerBadge.className = 'ac-power-badge ' + (isOn ? 'on' : 'off');
        
        // Visually dim the entire AC card when power is OFF
        const acCard = document.getElementById('cardAcStatus');
        if (acCard) {
            acCard.classList.toggle('ac-off', !isOn);
            acCard.classList.toggle('ac-on', isOn);
        }
        
        dom.dialSetpoint.textContent = parseFloat(state.ac_setpoint).toFixed(1);
        
        // Update thermostat ring arc (map 18-30°C range to stroke offset)
        const minT = 18, maxT = 30;
        const pct = Math.max(0, Math.min(1, (state.ac_setpoint - minT) / (maxT - minT)));
        const circumference = 326.73;
        if (isOn) {
            dom.ringFill.style.strokeDashoffset = circumference * (1 - pct);
            dom.ringFill.style.opacity = '1';
        } else {
            dom.ringFill.style.strokeDashoffset = circumference; // Empty ring
            dom.ringFill.style.opacity = '0.25';
        }
        
        // Mode tag
        const mode = (state.ac_mode || 'Cool').toLowerCase();
        dom.acModeTag.textContent = isOn ? state.ac_mode : 'OFF';
        dom.acModeTag.className = 'detail-value mode-tag ' + (isOn ? mode : 'off');
        
        dom.acFanSpeed.textContent = isOn ? state.ac_fan_speed : '—';
        dom.indoorTemp.textContent = formatTemp(state.indoor_temp);
        dom.baselineTemp.textContent = formatTemp(state.baseline_indoor_temp);
        
        // Time
        dom.timeLabel.textContent = state.time_of_day || formatHour(state.hour_of_day);
        
        // Metrics
        dom.metricAgentKwh.textContent = parseFloat(state.agent_energy_kwh).toFixed(3);
        dom.metricBaselineKwh.textContent = parseFloat(state.baseline_energy_kwh).toFixed(3);
        dom.metricSavingsUsd.textContent = '$' + parseFloat(state.savings_usd).toFixed(3);
        dom.metricCo2.textContent = parseFloat(state.co2_saved_kg).toFixed(3);
        dom.metricRate.textContent = '$' + parseFloat(state.electricity_rate).toFixed(2);
        
        // Peak indicator on rate tile
        const rateTile = dom.metricRate.closest('.metric-tile');
        if (state.is_peak_hours) {
            rateTile.style.borderColor = 'rgba(248, 113, 113, 0.3)';
            dom.metricRate.style.color = '#f87171';
        } else {
            rateTile.style.borderColor = '';
            dom.metricRate.style.color = '';
        }

        // Savings pct from agent decision
        if (state.agent_decision) {
            dom.metricSavingsPct.textContent = state.agent_decision.savings_pct + '%';
        }

        // Update slider values to match server state (for environmental drift)
        dom.sliderOutdoor.value = state.outdoor_temp;
        dom.valOutdoor.textContent = formatTemp(state.outdoor_temp);
        dom.sliderHour.value = state.hour_of_day;
        dom.valHour.textContent = state.time_of_day || formatHour(state.hour_of_day);
    }

    // ---- LangGraph Node Animation ----
    function resetGraphNodes() {
        Object.values(dom.graphNodes).forEach(n => {
            n.classList.remove('active', 'completed');
        });
        dom.graphEdges.forEach(e => e.classList.remove('active'));
    }

    async function animateGraphExecution(nodesExecuted) {
        resetGraphNodes();
        
        const nodeMap = {
            'retrieve_policies': dom.graphNodes.retrieve,
            'optimize_settings': dom.graphNodes.optimize,
            'validate_safety': dom.graphNodes.validate,
        };
        const edges = Array.from(dom.graphEdges);

        for (let i = 0; i < nodesExecuted.length; i++) {
            const nodeName = nodesExecuted[i];
            const nodeEl = nodeMap[nodeName];
            if (!nodeEl) continue;

            // Activate current node
            nodeEl.classList.add('active');
            
            // Wait for visual effect
            await sleep(500);
            
            // Mark as completed
            nodeEl.classList.remove('active');
            nodeEl.classList.add('completed');
            
            // Activate connecting edge
            if (i < edges.length) {
                edges[i].classList.add('active');
            }
            
            await sleep(200);
        }
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // ---- Policies Display ----
    function displayPolicies(policies) {
        if (!policies || policies.length === 0) {
            dom.policiesList.innerHTML = '<div class="policy-empty">No policies retrieved for the current state.</div>';
            return;
        }
        dom.policiesList.innerHTML = policies.map(p =>
            `<div class="policy-card">${escapeHtml(p)}</div>`
        ).join('');
    }

    // ---- Log ----
    function addLog(message, type = 'info') {
        const entry = document.createElement('div');
        entry.className = `log-entry log-${type}`;
        const time = new Date().toLocaleTimeString('en-US', { hour12: false });
        entry.textContent = `[${time}] ${message}`;
        dom.logContainer.appendChild(entry);
        dom.logContainer.scrollTop = dom.logContainer.scrollHeight;
        
        // Limit log entries
        while (dom.logContainer.children.length > 100) {
            dom.logContainer.removeChild(dom.logContainer.firstChild);
        }
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ---- Status Indicator ----
    function setStatus(label, active = false) {
        dom.statusLabel.textContent = label;
        dom.statusDot.classList.toggle('active', active);
    }

    // ---- Core Actions ----
    async function applyEnvironment() {
        const body = {
            outdoor_temp: parseFloat(dom.sliderOutdoor.value),
            target_temp: parseFloat(dom.sliderTarget.value),
            humidity: parseFloat(dom.sliderHumidity.value),
            hour_of_day: parseFloat(dom.sliderHour.value),
            occupancy: occupancy
        };
        
        setStatus('Applying...', true);
        const state = await apiPost('/api/state', body);
        updateDashboard(state);
        addLog(`Environment updated: Outdoor=${body.outdoor_temp}°C, Target=${body.target_temp}°C, Humidity=${body.humidity}%, Hour=${formatHour(body.hour_of_day)}, Occupancy=${occupancy ? 'Yes' : 'No'}`, 'info');
        
        // Auto-run optimization so AC status updates immediately
        addLog('Auto-optimizing AC settings for new environment...', 'info');
        await runOptimization();
    }

    async function runOptimization() {
        setStatus('Optimizing...', true);
        dom.btnRunOptimize.disabled = true;
        addLog('Triggering LangGraph optimization pipeline...', 'info');
        
        resetGraphNodes();
        
        const state = await apiPost('/api/optimize', { api_key: apiKey });
        
        if (state && state.agent_decision) {
            const dec = state.agent_decision;
            
            // Animate the graph node execution
            await animateGraphExecution(dec.nodes_executed || []);
            
            // Display policies
            displayPolicies(dec.policies);
            
            // Log reasoning
            addLog(`Agent Decision → Power: ${dec.power}, Mode: ${dec.mode}, Setpoint: ${dec.setpoint}°C, Fan: ${dec.fan_speed}`, 'success');
            addLog(`Reasoning: ${dec.explanation}`, 'agent');
            addLog(`Estimated Savings: ${dec.savings_pct}%`, 'success');
        }
        
        updateDashboard(state);
        dom.btnRunOptimize.disabled = false;
        setStatus(autoSimulate ? 'Auto-Running' : 'Idle', autoSimulate);
    }

    async function runSimStep() {
        const state = await apiPost('/api/step', { api_key: apiKey });
        if (state && state.agent_decision) {
            const dec = state.agent_decision;
            displayPolicies(dec.policies);
            
            // Quick node animation (faster during auto)
            animateGraphExecution(dec.nodes_executed || []);
        }
        updateDashboard(state);
    }

    async function resetMetrics() {
        const state = await apiPost('/api/reset');
        updateDashboard(state);
        addLog('Accumulated metrics reset to zero.', 'info');
    }

    // ---- Auto Simulate ----
    function toggleAutoSimulate() {
        autoSimulate = !autoSimulate;
        dom.btnAutoToggle.textContent = `Auto-Simulate: ${autoSimulate ? 'ON' : 'OFF'}`;
        dom.btnAutoToggle.classList.toggle('btn-accent', autoSimulate);
        dom.btnAutoToggle.classList.toggle('btn-primary', !autoSimulate);
        
        if (autoSimulate) {
            setStatus('Auto-Running', true);
            addLog('Auto-simulation started. Stepping every 2 seconds with agent optimization.', 'success');
            autoInterval = setInterval(() => {
                runSimStep();
            }, SIM_INTERVAL_MS);
        } else {
            setStatus('Idle');
            addLog('Auto-simulation stopped.', 'info');
            clearInterval(autoInterval);
            autoInterval = null;
        }
    }

    // ---- API Key Modal ----
    function openModal() {
        dom.modalOverlay.classList.add('show');
        dom.inputApiKey.value = apiKey;
        dom.inputApiKey.focus();
    }
    function closeModal() {
        dom.modalOverlay.classList.remove('show');
    }
    function saveApiKey() {
        apiKey = dom.inputApiKey.value.trim();
        closeModal();
        if (apiKey) {
            addLog('OpenAI API key set. LLM-powered reasoning enabled.', 'success');
        } else {
            addLog('API key cleared. Using built-in rule engine.', 'info');
        }
    }

    // ---- Event Bindings ----
    function bindEvents() {
        dom.btnApplyEnv.addEventListener('click', applyEnvironment);
        dom.btnRunOptimize.addEventListener('click', runOptimization);
        dom.btnAutoToggle.addEventListener('click', toggleAutoSimulate);
        dom.btnResetMetrics.addEventListener('click', resetMetrics);
        dom.btnClearLog.addEventListener('click', () => {
            dom.logContainer.innerHTML = '<div class="log-entry log-info">Log cleared.</div>';
        });
        dom.btnApiKey.addEventListener('click', openModal);
        dom.btnModalCancel.addEventListener('click', closeModal);
        dom.btnModalSave.addEventListener('click', saveApiKey);
        dom.modalOverlay.addEventListener('click', (e) => {
            if (e.target === dom.modalOverlay) closeModal();
        });

        // Keyboard shortcut: Enter to save in modal
        dom.inputApiKey.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') saveApiKey();
        });
    }

    // ---- Initialize ----
    async function init() {
        initSliders();
        initOccupancyToggle();
        bindEvents();
        
        // Fetch initial state from server
        addLog('Connecting to SmartAC Agent backend...', 'info');
        const state = await apiGet('/api/state');
        if (state) {
            updateDashboard(state);
            addLog('Connected to backend. System ready.', 'success');
            setStatus('Ready');
            
            // Sync slider values from server state
            dom.sliderTarget.value = state.target_temp;
            dom.valTarget.textContent = formatTemp(state.target_temp);
            dom.sliderHumidity.value = state.humidity;
            dom.valHumidity.textContent = state.humidity + '%';
            occupancy = state.occupancy;
            dom.btnOccupancy.classList.toggle('active', occupancy);
            dom.occupancyText.textContent = occupancy ? 'Occupied' : 'Unoccupied';
        } else {
            addLog('Could not connect to backend. Please ensure the server is running on ' + API_BASE, 'warning');
            setStatus('Disconnected');
        }
    }

    // Boot
    document.addEventListener('DOMContentLoaded', init);
})();
