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
            this.updateStatus('error', 'Disconnected');
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
        el.className = `status-indicator ${status}`;
        el.querySelector('.status-text').textContent = text;
    }

    updateBarkEvent(data) {
        // Update probability meter
        const probability = data.probability * 100;
        document.getElementById('probability-bar').style.width = `${probability}%`;
        document.getElementById('probability-value').textContent = `${probability.toFixed(1)}%`;

        // Update bark status
        const barkStatus = document.getElementById('bark-status');
        if (data.is_barking) {
            barkStatus.className = 'bark-status barking';
            barkStatus.querySelector('.bark-icon').textContent = '🔊';
            barkStatus.querySelector('.bark-text').textContent = 'BARK DETECTED!';
        } else {
            barkStatus.className = 'bark-status';
            barkStatus.querySelector('.bark-icon').textContent = '🔇';
            barkStatus.querySelector('.bark-text').textContent = 'No bark detected';
        }

        // Update DOA compass
        if (data.doa) {
            const angle = data.doa.bartlett;
            // Convert 0-180 to -90 to 90 for needle rotation
            const rotation = angle - 90;
            document.getElementById('doa-needle').style.transform =
                `translateX(-50%) rotate(${rotation}deg)`;
            document.getElementById('doa-value').textContent =
                `${angle}° (${data.doa.direction})`;
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

        if (this.events.length === 0) {
            container.innerHTML = '<p class="events-empty">No events yet</p>';
            return;
        }

        const html = this.events.slice(0, 10).map(event => {
            const time = new Date(event.timestamp).toLocaleTimeString();
            const prob = (event.probability * 100).toFixed(1);
            const barking = event.is_barking ? 'barking' : '';

            return `
                <div class="event-item ${barking}">
                    <span class="event-time">${time}</span>
                    <span class="event-prob">${prob}%</span>
                </div>
            `;
        }).join('');

        container.innerHTML = html;
    }

    updateAudioLevel(level, peak) {
        document.getElementById('audio-level').style.width = `${level * 100}%`;
        document.getElementById('audio-peak').style.left = `${peak * 100}%`;
    }

    updateSystemStatus(data) {
        document.getElementById('total-barks').textContent = data.total_barks || 0;
        document.getElementById('uptime').textContent = this.formatUptime(data.uptime_seconds || 0);

        if (data.microphone) {
            const micName = data.microphone.length > 15
                ? data.microphone.substring(0, 15) + '...'
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
                container.innerHTML = '<p class="evidence-empty">No recordings yet</p>';
                return;
            }

            const html = data.evidence.map(item => {
                const date = new Date(item.timestamp_local).toLocaleString();
                const duration = item.duration_seconds.toFixed(1);
                const peak = (item.peak_probability * 100).toFixed(1);

                return `
                    <div class="evidence-item">
                        <div class="evidence-info">
                            <div class="evidence-filename">${item.filename}</div>
                            <div class="evidence-meta">
                                ${date} | ${duration}s | Peak: ${peak}% | ${item.bark_count_in_clip} barks
                            </div>
                        </div>
                        <div class="evidence-actions">
                            <a href="/api/evidence/${item.filename}" class="btn-download" download>
                                Download WAV
                            </a>
                            <a href="/api/evidence/${item.filename.replace('.wav', '.json')}"
                               class="btn-download" download>
                                Metadata
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
