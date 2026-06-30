/* =========================================
   Smart AC Energy Saving Agent — App Logic
   ========================================= */

(function() {
    'use strict';

    // ---- Config & State ----
    const API_BASE = window.location.origin;
    let keyProvider = localStorage.getItem('ac_key_provider') || 'gemini';
    let apiKeyGemini = localStorage.getItem('ac_api_key_gemini') || '';
    let apiKeyOpenAI = localStorage.getItem('ac_api_key_openai') || '';
    
    function getActiveKey() {
        return keyProvider === 'gemini' ? apiKeyGemini : apiKeyOpenAI;
    }

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
        btnModalCancel: $('#btnModalCancel'),
        btnModalSave: $('#btnModalSave'),
        
        // Tab elements
        btnTabLog: $('#btnTabLog'),
        btnTabAssistant: $('#btnTabAssistant'),
        tabContentLog: $('#tabContentLog'),
        tabContentAssistant: $('#tabContentAssistant'),
        
        // Chat elements
        chatMessages: $('#chatMessages'),
        chatInput: $('#chatInput'),
        btnSendChat: $('#btnSendChat'),
        chatSuggestions: $('#chatSuggestions'),
        
        // Multi-API Key Modal controls
        selectKeyType: $('#selectKeyType'),
        inputGeminiKey: $('#inputGeminiKey'),
        inputOpenaiKey: $('#inputOpenaiKey'),
        containerGeminiKey: $('#containerGeminiKey'),
        containerOpenaiKey: $('#containerOpenaiKey')
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
        
        const state = await apiPost('/api/optimize', { api_key: getActiveKey(), key_type: keyProvider });
        
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
        const state = await apiPost('/api/step', { api_key: getActiveKey(), key_type: keyProvider });
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
        dom.selectKeyType.value = keyProvider;
        dom.inputGeminiKey.value = apiKeyGemini;
        dom.inputOpenaiKey.value = apiKeyOpenAI;
        toggleKeyInputs();
        
        // Focus the appropriate input
        if (keyProvider === 'gemini') {
            dom.inputGeminiKey.focus();
        } else {
            dom.inputOpenaiKey.focus();
        }
    }
    
    function toggleKeyInputs() {
        const type = dom.selectKeyType.value;
        if (type === 'gemini') {
            dom.containerGeminiKey.style.display = 'block';
            dom.containerOpenaiKey.style.display = 'none';
        } else {
            dom.containerGeminiKey.style.display = 'none';
            dom.containerOpenaiKey.style.display = 'block';
        }
    }
    
    function closeModal() {
        dom.modalOverlay.classList.remove('show');
    }
    
    function saveApiKey() {
        keyProvider = dom.selectKeyType.value;
        apiKeyGemini = dom.inputGeminiKey.value.trim();
        apiKeyOpenAI = dom.inputOpenaiKey.value.trim();
        
        localStorage.setItem('ac_key_provider', keyProvider);
        localStorage.setItem('ac_api_key_gemini', apiKeyGemini);
        localStorage.setItem('ac_api_key_openai', apiKeyOpenAI);
        
        closeModal();
        
        const activeKey = getActiveKey();
        const providerName = keyProvider === 'gemini' ? 'Google Gemini' : 'OpenAI';
        
        if (activeKey) {
            addLog(`${providerName} API key set. LLM agentic features active.`, 'success');
        } else {
            addLog(`API key cleared. Running in local fallback rules mode.`, 'info');
        }
    }

    // ---- Tabs Switching ----
    function switchTab(tab) {
        if (tab === 'log') {
            dom.btnTabLog.classList.add('active');
            dom.btnTabAssistant.classList.remove('active');
            dom.tabContentLog.classList.add('active');
            dom.tabContentAssistant.classList.remove('active');
        } else {
            dom.btnTabLog.classList.remove('active');
            dom.btnTabAssistant.classList.add('active');
            dom.tabContentLog.classList.remove('active');
            dom.tabContentAssistant.classList.add('active');
            // Scroll chat to bottom
            dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
        }
    }

    // ---- Chat Logic ----
    let chatHistory = [];

    function appendChatMessage(sender, content, isTool = false) {
        const bubble = document.createElement('div');
        if (isTool) {
            bubble.className = 'chat-bubble chat-tool';
            bubble.innerHTML = `⚙️ <span>${escapeHtml(content)}</span>`;
        } else {
            bubble.className = `chat-bubble chat-${sender}`;
            const inner = document.createElement('div');
            inner.className = 'bubble-content';
            inner.innerHTML = escapeHtml(content).replace(/\n/g, '<br>');
            bubble.appendChild(inner);
        }
        dom.chatMessages.appendChild(bubble);
        dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    }

    function appendTypingIndicator() {
        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble chat-agent';
        bubble.id = 'chatTypingIndicator';
        bubble.innerHTML = `
            <div class="typing-indicator-dots">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;
        dom.chatMessages.appendChild(bubble);
        dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
    }

    function removeTypingIndicator() {
        const el = document.getElementById('chatTypingIndicator');
        if (el) el.remove();
    }

    async function sendChatMessage(messageText) {
        if (!messageText) return;
        
        appendChatMessage('user', messageText);
        appendTypingIndicator();
        
        const activeKey = getActiveKey();
        const payload = {
            message: messageText,
            history: chatHistory,
            api_key: activeKey,
            key_type: keyProvider
        };
        
        const result = await apiPost('/api/chat', payload);
        removeTypingIndicator();
        
        if (result) {
            if (result.tool_calls && result.tool_calls.length > 0) {
                result.tool_calls.forEach(tc => {
                    const argStr = JSON.stringify(tc.args);
                    appendChatMessage('agent', `Executed tool: ${tc.name}(${argStr}) → ${tc.result}`, true);
                });
            }
            
            appendChatMessage('agent', result.response);
            
            chatHistory.push({ role: 'user', content: messageText });
            chatHistory.push({ role: 'assistant', content: result.response });
            
            if (chatHistory.length > 20) {
                chatHistory = chatHistory.slice(-20);
            }
            
            if (result.simulator_state) {
                updateDashboard(result.simulator_state);
            }
        } else {
            appendChatMessage('agent', 'I encountered an error trying to process that request. Please try again.');
        }
    }

    function initChatSuggestions() {
        dom.chatSuggestions.addEventListener('click', (e) => {
            const chip = e.target.closest('.chip');
            if (chip) {
                const msg = chip.getAttribute('data-msg');
                if (msg) {
                    sendChatMessage(msg);
                }
            }
        });
    }

    // ---- Event Bindings ----
    function bindEvents() {
        dom.btnApplyEnv.addEventListener('click', applyEnvironment);
        dom.btnRunOptimize.addEventListener('click', runOptimization);
        dom.btnAutoToggle.addEventListener('click', toggleAutoSimulate);
        dom.btnResetMetrics.addEventListener('click', resetMetrics);
        
        // Log clear vs Chat send
        dom.btnClearLog.addEventListener('click', () => {
            const activeTab = $('.tab-btn.active').getAttribute('data-tab');
            if (activeTab === 'log') {
                dom.logContainer.innerHTML = '<div class="log-entry log-info">Log cleared.</div>';
            } else {
                dom.chatMessages.innerHTML = `
                    <div class="chat-bubble chat-agent">
                        <div class="bubble-content">Chat history cleared. How can I help you optimize your AC settings?</div>
                    </div>
                `;
                chatHistory = [];
            }
        });
        
        // Tabs triggers
        dom.btnTabLog.addEventListener('click', () => switchTab('log'));
        dom.btnTabAssistant.addEventListener('click', () => switchTab('assistant'));
        
        // Chat Actions
        dom.btnSendChat.addEventListener('click', () => {
            const val = dom.chatInput.value.trim();
            if (val) {
                sendChatMessage(val);
                dom.chatInput.value = '';
            }
        });
        
        dom.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const val = dom.chatInput.value.trim();
                if (val) {
                    sendChatMessage(val);
                    dom.chatInput.value = '';
                }
            }
        });
        
        initChatSuggestions();
        
        // API Key Modal Trigger & Action Handlers
        dom.btnApiKey.addEventListener('click', openModal);
        dom.btnModalCancel.addEventListener('click', closeModal);
        dom.btnModalSave.addEventListener('click', saveApiKey);
        dom.selectKeyType.addEventListener('change', toggleKeyInputs);
        
        dom.modalOverlay.addEventListener('click', (e) => {
            if (e.target === dom.modalOverlay) closeModal();
        });

        // Keypress overrides inside Modal Inputs
        dom.inputGeminiKey.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') saveApiKey();
        });
        dom.inputOpenaiKey.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') saveApiKey();
        });
    }

    // ---- Initialize ----
    async function init() {
        initSliders();
        initOccupancyToggle();
        bindEvents();
        
        // Clear log button label change depending on tab context
        dom.btnTabLog.addEventListener('click', () => dom.btnClearLog.textContent = 'Clear Log');
        dom.btnTabAssistant.addEventListener('click', () => dom.btnClearLog.textContent = 'Clear Chat');
        
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
            
            const activeKey = getActiveKey();
            if (activeKey) {
                const providerName = keyProvider === 'gemini' ? 'Google Gemini' : 'OpenAI';
                addLog(`Restored saved ${providerName} key from localStorage.`, 'info');
            }
        } else {
            addLog('Could not connect to backend. Please ensure the server is running on ' + API_BASE, 'warning');
            setStatus('Disconnected');
        }
    }

    // Boot
    document.addEventListener('DOMContentLoaded', init);
})();
