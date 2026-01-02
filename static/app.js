/**
 * Woofalytics - Real-time Bark Detection Dashboard
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

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.connectAudioWebSocket();
        this.loadStatus();
        this.loadEvidence();

        // Refresh status every 30 seconds
        setInterval(() => this.loadStatus(), 30000);
    }

    // WebSocket Connection
    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/bark`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.updateStatus('connected', 'Connected');
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.updateStatus('disconnected', 'Disconnected');
            this.scheduleReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateStatus('error', 'Error');
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
        const offset = this.gaugeCircumference - (probability / 100) * this.gaugeCircumference;
        gaugeFill.style.strokeDashoffset = offset;

        // Update probability value text
        document.getElementById('probability-value').textContent = Math.round(probability);

        // Update bark panel state
        const barkPanel = document.getElementById('bark-panel');
        const barkIcon = document.getElementById('bark-icon');
        const barkText = document.getElementById('bark-text');

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
        }

        // Update DOA compass
        if (data.doa) {
            const angle = data.doa.bartlett;
            // Convert 0-180 to position on the horizontal track
            // 0° = left, 90° = center, 180° = right
            const position = (angle / 180) * 100;
            document.getElementById('doa-needle').style.left = `${position}%`;
            document.getElementById('doa-value').textContent = `${angle}°`;
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

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new WoofalyticsApp();
});
