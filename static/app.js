/**
 * Woofalytics - Real-time Bark Detection Dashboard
 * NASA Mission Control Edition
 */

class WoofalyticsApp {
    constructor() {
        this.ws = null;
        this.wsAudio = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.events = [];
        this.maxEvents = 50;

        // SVG gauge constants
        this.gaugeRadius = 54;
        this.gaugeCircumference = 2 * Math.PI * this.gaugeRadius;

        // Mission Control state
        this.missionStartTime = Date.now();
        this.isBarkActive = false;
        this.barkTimeout = null;

        // Waveform visualizer
        this.waveformVisualizer = null;

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.connectAudioWebSocket();
        this.loadStatus();
        this.loadEvidence();
        this.initMissionClock();
        this.initGeolocation();
        this.initWaveformVisualizer();

        // Refresh status every 30 seconds
        setInterval(() => this.loadStatus(), 30000);
    }

    initWaveformVisualizer() {
        this.waveformVisualizer = new WaveformVisualizer('waveform-canvas');
    }

    // =========================================
    // NASA Mission Control Telemetry
    // =========================================

    initMissionClock() {
        // Update mission clock every 10ms for centisecond precision
        setInterval(() => this.updateMissionClock(), 10);
    }

    updateMissionClock() {
        const elapsed = Date.now() - this.missionStartTime;
        const hours = Math.floor(elapsed / 3600000);
        const minutes = Math.floor((elapsed % 3600000) / 60000);
        const seconds = Math.floor((elapsed % 60000) / 1000);
        const centiseconds = Math.floor((elapsed % 1000) / 10);

        const clockValue = document.getElementById('mission-clock');
        if (clockValue) {
            clockValue.textContent =
                `${hours.toString().padStart(2, '0')}:` +
                `${minutes.toString().padStart(2, '0')}:` +
                `${seconds.toString().padStart(2, '0')}.` +
                `${centiseconds.toString().padStart(2, '0')}`;
        }
    }

    initGeolocation() {
        // Try to get geolocation for the coordinates display
        if ('geolocation' in navigator) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude;
                    const lon = position.coords.longitude;
                    const latEl = document.getElementById('coord-lat');
                    const lonEl = document.getElementById('coord-lon');
                    if (latEl && lonEl) {
                        latEl.textContent = (lat >= 0 ? '+' : '') + lat.toFixed(4);
                        lonEl.textContent = (lon >= 0 ? '+' : '') + lon.toFixed(4);
                    }
                },
                () => {
                    // Geolocation denied or unavailable - leave defaults
                }
            );
        }
    }

    updateLedStatus(ledId, state) {
        const led = document.getElementById(ledId);
        if (led) {
            led.classList.remove('active', 'warning', 'alert');
            if (state) {
                led.classList.add(state);
            }
        }
    }

    // WebSocket Connection
    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/bark`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateStatus('connected', 'Connected');
            this.updateLedStatus('led-ws', 'active');
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateStatus('disconnected', 'Disconnected');
            this.updateLedStatus('led-ws', 'warning');
            this.scheduleReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateStatus('error', 'Error');
            this.updateLedStatus('led-ws', 'alert');
        };
    }

    connectAudioWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/audio`;

        this.wsAudio = new WebSocket(wsUrl);

        this.wsAudio.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'audio_level') {
                this.updateAudioLevel(data.data.level, data.data.peak);
                // Update MIC LED based on audio level
                if (data.data.level > 0.01) {
                    this.updateLedStatus('led-mic', 'active');
                }
                // Feed sample to waveform visualizer
                if (this.waveformVisualizer) {
                    this.waveformVisualizer.addSample(data.data.level);
                }
            }
        };

        this.wsAudio.onclose = () => {
            // Reconnect audio WebSocket after 2 seconds
            setTimeout(() => this.connectAudioWebSocket(), 2000);
        };
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            this.reconnectAttempts++;
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
            setTimeout(() => this.connectWebSocket(), delay);
        }
    }

    handleMessage(data) {
        switch (data.type) {
            case 'bark_event':
                this.updateBarkEvent(data.data);
                break;
            case 'status':
                this.updateSystemStatus(data.data);
                break;
            case 'ping':
                this.ws.send(JSON.stringify({ type: 'pong' }));
                break;
        }
    }

    // UI Updates
    updateStatus(status, text) {
        const el = document.getElementById('status');
        el.className = `status-badge ${status}`;
        el.querySelector('.status-text').textContent = text;
    }

    updateBarkEvent(data) {
        // Update probability gauge (SVG circular)
        const probability = data.probability * 100;
        const gaugeFill = document.getElementById('gauge-fill');
        if (gaugeFill) {
            const offset = this.gaugeCircumference - (probability / 100) * this.gaugeCircumference;
            gaugeFill.style.strokeDashoffset = offset;
        }

        // Update probability value text
        const probValue = document.getElementById('probability-value');
        if (probValue) {
            probValue.textContent = Math.round(probability);
        }

        // Update bark panel state
        const barkPanel = document.getElementById('bark-panel');
        const barkIcon = document.getElementById('bark-icon');
        const barkText = document.getElementById('bark-text');

        if (barkPanel && barkIcon && barkText) {
            if (data.is_barking) {
                barkPanel.classList.add('barking');
                barkIcon.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 5L6 9H2v6h4l5 4V5z"/>
                        <path d="M19.07 4.93a10 10 0 010 14.14"/>
                        <path d="M15.54 8.46a5 5 0 010 7.07"/>
                    </svg>
                `;
                barkText.textContent = 'BARK DETECTED!';

                // Update BARK LED to alert state
                this.updateLedStatus('led-bark', 'alert');
                this.isBarkActive = true;

                // Clear any existing timeout
                if (this.barkTimeout) {
                    clearTimeout(this.barkTimeout);
                }

                // Reset bark LED after 2 seconds of no barking
                this.barkTimeout = setTimeout(() => {
                    if (!this.isBarkActive) {
                        this.updateLedStatus('led-bark', null);
                    }
                }, 2000);
            } else {
                barkPanel.classList.remove('barking');
                barkIcon.innerHTML = `
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 5L6 9H2v6h4l5 4V5z"/>
                        <line x1="23" y1="9" x2="17" y2="15"/>
                        <line x1="17" y1="9" x2="23" y2="15"/>
                    </svg>
                `;
                barkText.textContent = 'Monitoring';
                this.isBarkActive = false;
            }
        }

        // Update DOA compass
        if (data.doa) {
            const angle = data.doa.bartlett;
            const needle = document.getElementById('doa-needle');
            const doaValue = document.getElementById('doa-value');
            if (needle && doaValue) {
                // Convert 0-180 to position on the horizontal track
                // 0° = left, 90° = center, 180° = right
                const position = (angle / 180) * 100;
                needle.style.left = `${position}%`;
                doaValue.textContent = `${angle}°`;
            }
        }

        // Add to events list
        this.addEvent(data);
    }

    addEvent(data) {
        this.events.unshift(data);
        if (this.events.length > this.maxEvents) {
            this.events.pop();
        }
        this.renderEvents();
    }

    renderEvents() {
        const container = document.getElementById('events-list');
        const countEl = document.getElementById('event-count');

        // Update event count
        const barkCount = this.events.filter(e => e.is_barking).length;
        countEl.textContent = `${barkCount} bark${barkCount !== 1 ? 's' : ''}`;

        if (this.events.length === 0) {
            container.innerHTML = `
                <div class="events-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 6v6l4 2"/>
                    </svg>
                    <span>Waiting for events...</span>
                </div>
            `;
            return;
        }

        const html = this.events.slice(0, 10).map(event => {
            const time = new Date(event.timestamp).toLocaleTimeString();
            const prob = (event.probability * 100).toFixed(0);
            const barking = event.is_barking ? 'barking' : '';
            const icon = event.is_barking
                ? '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="6"/></svg>'
                : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/></svg>';

            return `
                <div class="event-item ${barking}">
                    <span class="event-icon">${icon}</span>
                    <span class="event-time">${time}</span>
                    <span class="event-prob">${prob}%</span>
                </div>
            `;
        }).join('');

        container.innerHTML = html;
    }

    updateAudioLevel(level, peak) {
        // Convert 0-1 to percentage
        const levelPercent = Math.min(100, level * 100);
        const peakPercent = Math.min(100, peak * 100);

        document.getElementById('audio-level').style.width = `${levelPercent}%`;
        document.getElementById('audio-peak').style.left = `${peakPercent}%`;

        // Update VU segment highlights based on level
        const segments = document.querySelectorAll('.vu-segments span');
        const activeCount = Math.floor((levelPercent / 100) * segments.length);
        segments.forEach((seg, i) => {
            if (i < activeCount) {
                seg.classList.add('active');
                // Color segments based on level (green < yellow < red)
                if (i >= segments.length * 0.8) {
                    seg.classList.add('red');
                    seg.classList.remove('yellow');
                } else if (i >= segments.length * 0.6) {
                    seg.classList.add('yellow');
                    seg.classList.remove('red');
                } else {
                    seg.classList.remove('yellow', 'red');
                }
            } else {
                seg.classList.remove('active', 'yellow', 'red');
            }
        });
    }

    updateSystemStatus(data) {
        document.getElementById('total-barks').textContent = data.total_barks || 0;
        document.getElementById('uptime').textContent = this.formatUptime(data.uptime_seconds || 0);

        if (data.microphone) {
            const micName = data.microphone.length > 20
                ? data.microphone.substring(0, 20) + '...'
                : data.microphone;
            document.getElementById('microphone').textContent = micName;
        }
    }

    formatUptime(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }

    // API Calls
    async loadStatus() {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();

            document.getElementById('total-barks').textContent = data.total_barks_detected || 0;
            document.getElementById('uptime').textContent = this.formatUptime(data.uptime_seconds || 0);
            document.getElementById('evidence-count').textContent = data.evidence_files_count || 0;
        } catch (error) {
            console.error('Error loading status:', error);
        }
    }

    async loadEvidence() {
        try {
            const response = await fetch('/api/evidence?count=10');
            const data = await response.json();

            const container = document.getElementById('evidence-list');

            if (!data.evidence || data.evidence.length === 0) {
                container.innerHTML = `
                    <div class="evidence-empty">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                            <path d="M14 2v6h6"/>
                            <path d="M12 18v-6"/>
                            <path d="M9 15l3 3 3-3"/>
                        </svg>
                        <span>No recordings yet</span>
                    </div>
                `;
                return;
            }

            const html = data.evidence.map(item => {
                const date = new Date(item.timestamp_local);
                const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const dateStr = date.toLocaleDateString([], { month: 'short', day: 'numeric' });
                const duration = item.duration_seconds.toFixed(1);
                const peak = (item.peak_probability * 100).toFixed(0);

                return `
                    <div class="evidence-item">
                        <div class="evidence-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M9 18V5l12-2v13"/>
                                <circle cx="6" cy="18" r="3"/>
                                <circle cx="18" cy="16" r="3"/>
                            </svg>
                        </div>
                        <div class="evidence-info">
                            <span class="evidence-time">${timeStr} · ${dateStr}</span>
                            <span class="evidence-meta">${duration}s · ${peak}% peak · ${item.bark_count_in_clip} bark${item.bark_count_in_clip !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="evidence-actions">
                            <a href="/api/evidence/${item.filename}" class="btn-icon" title="Download WAV" download>
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                                    <polyline points="7 10 12 15 17 10"/>
                                    <line x1="12" y1="15" x2="12" y2="3"/>
                                </svg>
                            </a>
                        </div>
                    </div>
                `;
            }).join('');

            container.innerHTML = html;
            document.getElementById('evidence-count').textContent = data.count;
        } catch (error) {
            console.error('Error loading evidence:', error);
        }
    }
}

// Global function for refresh button
function loadEvidence() {
    window.app.loadEvidence();
}

// =========================================
// Waveform Visualizer Class
// =========================================

class WaveformVisualizer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext('2d');
        this.samples = [];
        this.maxSamples = 200;  // Number of samples to display
        this.phosphorTrails = [];  // For persistence effect
        this.maxTrails = 3;

        // Colors for gradient based on amplitude
        this.colorLow = { r: 20, g: 184, b: 166 };      // Teal
        this.colorHigh = { r: 248, g: 81, b: 73 };      // Coral

        this.resize();
        window.addEventListener('resize', () => this.resize());

        // Start animation loop
        this.animate();
    }

    resize() {
        if (!this.canvas) return;
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width * window.devicePixelRatio;
        this.canvas.height = rect.height * window.devicePixelRatio;
        this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        this.width = rect.width;
        this.height = rect.height;
    }

    addSample(level) {
        this.samples.push(level);
        if (this.samples.length > this.maxSamples) {
            this.samples.shift();
        }
    }

    interpolateColor(t) {
        // t is 0-1, interpolate between teal and coral
        const r = Math.round(this.colorLow.r + (this.colorHigh.r - this.colorLow.r) * t);
        const g = Math.round(this.colorLow.g + (this.colorHigh.g - this.colorLow.g) * t);
        const b = Math.round(this.colorLow.b + (this.colorHigh.b - this.colorLow.b) * t);
        return `rgb(${r}, ${g}, ${b})`;
    }

    animate() {
        if (!this.canvas) return;

        // Clear with slight fade for phosphor persistence effect
        this.ctx.fillStyle = 'rgba(33, 38, 45, 0.3)';
        this.ctx.fillRect(0, 0, this.width, this.height);

        // Draw grid lines
        this.ctx.strokeStyle = 'rgba(125, 133, 144, 0.1)';
        this.ctx.lineWidth = 1;

        // Horizontal center line
        this.ctx.beginPath();
        this.ctx.moveTo(0, this.height / 2);
        this.ctx.lineTo(this.width, this.height / 2);
        this.ctx.stroke();

        // Vertical grid lines
        const gridSpacing = this.width / 10;
        for (let x = gridSpacing; x < this.width; x += gridSpacing) {
            this.ctx.beginPath();
            this.ctx.moveTo(x, 0);
            this.ctx.lineTo(x, this.height);
            this.ctx.stroke();
        }

        if (this.samples.length < 2) {
            requestAnimationFrame(() => this.animate());
            return;
        }

        // Draw waveform with glow effect
        const stepX = this.width / (this.maxSamples - 1);
        const centerY = this.height / 2;
        const amplitude = this.height * 0.4;

        // Draw glow layer
        this.ctx.lineWidth = 6;
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        this.ctx.beginPath();
        for (let i = 0; i < this.samples.length; i++) {
            const x = i * stepX;
            const level = this.samples[i];
            const y = centerY - (level * amplitude * 2 - amplitude);

            if (i === 0) {
                this.ctx.moveTo(x, y);
            } else {
                this.ctx.lineTo(x, y);
            }
        }

        // Glow effect
        const avgLevel = this.samples.reduce((a, b) => a + b, 0) / this.samples.length;
        const glowColor = this.interpolateColor(avgLevel);
        this.ctx.strokeStyle = glowColor.replace('rgb', 'rgba').replace(')', ', 0.3)');
        this.ctx.stroke();

        // Draw main waveform line
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();

        for (let i = 0; i < this.samples.length; i++) {
            const x = i * stepX;
            const level = this.samples[i];
            const y = centerY - (level * amplitude * 2 - amplitude);

            if (i === 0) {
                this.ctx.moveTo(x, y);
            } else {
                this.ctx.lineTo(x, y);
            }
        }

        // Create gradient based on average level
        const gradient = this.ctx.createLinearGradient(0, 0, this.width, 0);
        gradient.addColorStop(0, this.interpolateColor(0.2));
        gradient.addColorStop(0.5, this.interpolateColor(avgLevel));
        gradient.addColorStop(1, this.interpolateColor(Math.min(avgLevel * 1.5, 1)));

        this.ctx.strokeStyle = gradient;
        this.ctx.stroke();

        // Draw leading edge dot
        if (this.samples.length > 0) {
            const lastX = (this.samples.length - 1) * stepX;
            const lastLevel = this.samples[this.samples.length - 1];
            const lastY = centerY - (lastLevel * amplitude * 2 - amplitude);

            this.ctx.beginPath();
            this.ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
            this.ctx.fillStyle = this.interpolateColor(lastLevel);
            this.ctx.fill();

            // Add glow to the dot
            this.ctx.beginPath();
            this.ctx.arc(lastX, lastY, 8, 0, Math.PI * 2);
            const dotGlow = this.ctx.createRadialGradient(lastX, lastY, 0, lastX, lastY, 8);
            dotGlow.addColorStop(0, this.interpolateColor(lastLevel).replace('rgb', 'rgba').replace(')', ', 0.5)'));
            dotGlow.addColorStop(1, 'transparent');
            this.ctx.fillStyle = dotGlow;
            this.ctx.fill();
        }

        requestAnimationFrame(() => this.animate());
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new WoofalyticsApp();
});
