/**
 * EVEZ Platform — Frontend Application
 * Chat, Search, Stream, Brain views with SSE streaming
 */

const API = '';
let currentView = 'chat';
let currentConversationId = null;
let currentModel = null;
let isStreaming = false;

// ---------------------------------------------------------------------------
// Native Speech (Android A16 bridge)
// ---------------------------------------------------------------------------

const hasNativeSpeech = typeof window.EVEZNative !== 'undefined';
const hasNativeSTT = typeof window.EVEZNative !== 'undefined' && typeof window.EVEZNative.startListening === 'function';

function nativeSpeak(text) {
    if (hasNativeSpeech) {
        window.EVEZNative.speak(text);
    } else if ('speechSynthesis' in window) {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.05;
        utterance.pitch = 0.95;
        speechSynthesis.speak(utterance);
    }
}

function nativeStopSpeaking() {
    if (hasNativeSpeech) {
        window.EVEZNative.stopSpeaking();
    } else if ('speechSynthesis' in window) {
        speechSynthesis.cancel();
    }
}

function nativeStartListening() {
    if (hasNativeSTT) {
        window.EVEZNative.startListening();
    } else if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        recognition.lang = 'en-US';
        recognition.interimResults = false;
        recognition.onresult = (event) => {
            const text = event.results[0][0].transcript;
            document.getElementById('chat-input').value = text;
            sendMessage();
        };
        recognition.start();
    }
}

// Listen for native STT results
window.addEventListener('evez-stt-result', (event) => {
    const text = event.detail;
    document.getElementById('chat-input').value = text;
    sendMessage();
});

// Auto-speak assistant responses
function autoSpeak(text) {
    // Strip markdown for speech
    const plain = text.replace(/```[\s\S]*?```/g, '[code block]')
                      .replace(/\*\*(.*?)\*\*/g, '$1')
                      .replace(/\[(.*?)\]\(.*?\)/g, '$1')
                      .replace(/#{1,3}\s/g, '')
                      .replace(/[|]/g, ' ')
                      .substring(0, 500);
    if (plain.length > 10) {
        nativeSpeak(plain);
    }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    initNav();
    initChat();
    initSearch();
    initStream();
    initSpine();
    loadModels();
    loadConversations();
    checkStatus();
});

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function initNav() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            switchView(view);
        });
    });

    document.querySelectorAll('.welcome-card').forEach(card => {
        card.addEventListener('click', () => {
            const prompt = card.dataset.prompt;
            document.getElementById('chat-input').value = prompt;
            switchView('chat');
            sendMessage();
        });
    });
}

function switchView(view) {
    currentView = view;
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${view}`));

    if (view === 'spine') loadSpine();
    if (view === 'stream') loadStreamStatus();
}

// ---------------------------------------------------------------------------
// API Helpers
// ---------------------------------------------------------------------------

async function api(path, options = {}) {
    const res = await fetch(`${API}${path}`, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    return res.json();
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

async function loadModels() {
    try {
        const data = await api('/api/models');
        const select = document.getElementById('model-select');
        select.innerHTML = '';
        data.models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = `${m.name}${m.local ? ' (local)' : ''}${m.free ? ' ✓' : ''}`;
            select.appendChild(opt);
        });
        if (data.models.length > 0) {
            currentModel = data.models[0].id;
        }
        select.addEventListener('change', () => {
            currentModel = select.value;
        });
    } catch (e) {
        document.getElementById('model-select').innerHTML = '<option>Error loading</option>';
    }
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

async function checkStatus() {
    try {
        const data = await api('/api/system/status');
        const dot = document.querySelector('.status-dot');
        const text = document.querySelector('.status-text');
        dot.classList.remove('online', 'error');

        if (data.ollama) {
            dot.classList.add('online');
            text.textContent = 'Ollama connected';
        } else {
            dot.classList.add('online');
            text.textContent = 'Cloud API ready';
        }
    } catch (e) {
        const dot = document.querySelector('.status-dot');
        const text = document.querySelector('.status-text');
        dot.classList.add('error');
        text.textContent = 'Offline';
    }
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

async function loadConversations() {
    try {
        const data = await api('/api/conversations');
        const list = document.getElementById('conversation-list');
        list.innerHTML = '';
        data.conversations.forEach(c => {
            const item = document.createElement('div');
            item.className = `conv-item${c.id === currentConversationId ? ' active' : ''}`;
            item.textContent = c.title || 'New Chat';
            item.addEventListener('click', () => loadConversation(c.id));
            list.appendChild(item);
        });
    } catch (e) {
        console.error('Failed to load conversations:', e);
    }
}

async function loadConversation(id) {
    currentConversationId = id;
    try {
        const data = await api(`/api/conversations/${id}`);
        const container = document.getElementById('chat-messages');
        container.innerHTML = '';
        data.messages.forEach(msg => appendMessage(msg.role, msg.content, false));
        loadConversations();
    } catch (e) {
        console.error('Failed to load conversation:', e);
    }
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

function initChat() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const newChatBtn = document.getElementById('new-chat-btn');

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 200) + 'px';
    });

    sendBtn.addEventListener('click', sendMessage);
    newChatBtn.addEventListener('click', newChat);
}

async function newChat() {
    try {
        const data = await api('/api/conversations/new', {
            method: 'POST',
            body: JSON.stringify({ title: 'New Chat' }),
        });
        currentConversationId = data.conversation_id;
        document.getElementById('chat-messages').innerHTML = '';
        loadConversations();
        document.getElementById('chat-input').focus();
    } catch (e) {
        console.error('Failed to create conversation:', e);
    }
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message || isStreaming) return;

    input.value = '';
    input.style.height = 'auto';
    isStreaming = true;
    document.getElementById('send-btn').disabled = true;

    // Remove welcome
    const welcome = document.querySelector('.welcome');
    if (welcome) welcome.remove();

    // Add user message
    appendMessage('user', message);

    // Add loading indicator
    const loadingId = appendLoading();

    try {
        const response = await fetch(`${API}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                model: currentModel,
                conversation_id: currentConversationId,
                stream: true,
            }),
        });

        removeLoading(loadingId);

        if (!response.ok) {
            appendMessage('assistant', `Error: ${response.statusText}`);
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantContent = '';
        let msgEl = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value, { stream: true });
            const lines = text.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'conversation_id') {
                            currentConversationId = data.id;
                            loadConversations();
                        } else if (data.type === 'content') {
                            assistantContent += data.content;
                            if (!msgEl) {
                                msgEl = appendMessage('assistant', '', true);
                            }
                            updateMessageContent(msgEl, assistantContent);
                        } else if (data.type === 'error') {
                            appendMessage('assistant', `Error: ${data.error}`);
                        }
                    } catch (e) {
                        // Skip non-JSON lines
                    }
                }
            }
        }

        if (!msgEl && assistantContent) {
            appendMessage('assistant', assistantContent);
        }
    } catch (e) {
        removeLoading(loadingId);
        appendMessage('assistant', `Connection error: ${e.message}`);
    } finally {
        isStreaming = false;
        document.getElementById('send-btn').disabled = false;
        document.getElementById('chat-input').focus();
    }
}

function appendMessage(role, content, streaming = false) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `
        <div class="message-avatar">${role === 'user' ? 'U' : '⚡'}</div>
        <div class="message-content">${role === 'user' ? escapeHtml(content) : renderMarkdown(content)}</div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

function updateMessageContent(msgEl, content) {
    const contentEl = msgEl.querySelector('.message-content');
    contentEl.innerHTML = renderMarkdown(content);
    const container = document.getElementById('chat-messages');
    container.scrollTop = container.scrollHeight;
}

function appendLoading() {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'loading-' + Date.now();
    div.innerHTML = `
        <div class="message-avatar">⚡</div>
        <div class="message-loading">
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
            <div class="loading-dot"></div>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div.id;
}

function removeLoading(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function initSearch() {
    const input = document.getElementById('search-input');
    const btn = document.getElementById('search-btn');

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') performSearch();
    });
    btn.addEventListener('click', performSearch);
}

async function performSearch() {
    const input = document.getElementById('search-input');
    const query = input.value.trim();
    if (!query) return;

    const results = document.getElementById('search-results');
    results.innerHTML = '<div class="message-loading"><div class="loading-dot"></div><div class="loading-dot"></div><div class="loading-dot"></div></div>';

    try {
        const data = await api('/api/search', {
            method: 'POST',
            body: JSON.stringify({ query, max_results: 8 }),
        });

        let html = '';

        // AI answer
        if (data.answer) {
            html += `<div class="search-answer"><h2>💡 Answer</h2>${renderMarkdown(data.answer)}</div>`;
        }

        // Sources
        if (data.sources && data.sources.length > 0) {
            html += '<h3 style="margin-bottom:12px;color:var(--text-secondary)">Sources</h3>';
            data.sources.forEach((s, i) => {
                html += `
                    <div class="search-result">
                        <h3><a href="${escapeHtml(s.url)}" target="_blank">${escapeHtml(s.title)}</a></h3>
                        <div class="url">${escapeHtml(s.url)}</div>
                        <div class="snippet">${escapeHtml(s.snippet)}</div>
                    </div>
                `;
            });
        }

        results.innerHTML = html;
    } catch (e) {
        results.innerHTML = `<div class="search-result"><div class="snippet" style="color:var(--error)">Search failed: ${e.message}</div></div>`;
    }
}

// ---------------------------------------------------------------------------
// Stream
// ---------------------------------------------------------------------------

function initStream() {
    document.getElementById('stream-toggle').addEventListener('click', toggleStream);
}

async function toggleStream() {
    const btn = document.getElementById('stream-toggle');
    const badge = document.getElementById('stream-status');

    try {
        const status = await api('/api/stream/status');
        if (status.running) {
            await api('/api/stream/stop', { method: 'POST' });
            btn.textContent = 'Start Stream';
            badge.textContent = 'OFFLINE';
            badge.classList.remove('live');
        } else {
            await api('/api/stream/start', { method: 'POST' });
            btn.textContent = 'Stop Stream';
            badge.textContent = 'LIVE';
            badge.classList.add('live');
            startStreamFeed();
        }
    } catch (e) {
        console.error('Stream toggle failed:', e);
    }
}

async function loadStreamStatus() {
    try {
        const status = await api('/api/stream/status');
        const btn = document.getElementById('stream-toggle');
        const badge = document.getElementById('stream-status');

        if (status.running) {
            btn.textContent = 'Stop Stream';
            badge.textContent = 'LIVE';
            badge.classList.add('live');
        } else {
            btn.textContent = 'Start Stream';
            badge.textContent = 'OFFLINE';
            badge.classList.remove('live');
        }

        // Load recent events
        const events = await api('/api/stream/events?n=20');
        const feed = document.getElementById('stream-feed');
        feed.innerHTML = '';
        events.events.reverse().forEach(e => appendStreamEvent(e));
    } catch (e) {
        console.error('Failed to load stream status:', e);
    }
}

function startStreamFeed() {
    const evtSource = new EventSource(`${API}/api/stream/live`);
    evtSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            appendStreamEvent(data);
        } catch (e) {}
    };
    evtSource.onerror = () => {
        evtSource.close();
    };
}

function appendStreamEvent(event) {
    const feed = document.getElementById('stream-feed');
    const div = document.createElement('div');
    div.className = 'stream-event';
    div.innerHTML = `
        <div class="event-type">${escapeHtml(event.type || 'event')}</div>
        <div class="event-time">${escapeHtml(event.ts_iso || new Date().toISOString())}</div>
        <div class="event-content">${renderMarkdown(event.content || JSON.stringify(event))}</div>
    `;
    feed.insertBefore(div, feed.firstChild);
}

// ---------------------------------------------------------------------------
// Spine & Memory
// ---------------------------------------------------------------------------

function initSpine() {
    document.querySelectorAll('.spine-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.spine-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.spine-tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab).classList.add('active');
        });
    });
}

async function loadSpine() {
    try {
        // Load spine events
        const spineData = await api('/api/spine?n=50');
        const spineList = document.getElementById('spine-list');
        spineList.innerHTML = '';
        spineData.events.reverse().forEach(e => {
            const div = document.createElement('div');
            div.className = 'event-item';
            div.innerHTML = `
                <div class="event-header">
                    <span class="event-type-tag">${escapeHtml(e.type)}</span>
                    <span class="event-ts">${escapeHtml(e.ts)}</span>
                </div>
                <div class="event-data">${escapeHtml(JSON.stringify(e.data).slice(0, 200))}</div>
            `;
            spineList.appendChild(div);
        });

        // Load memories
        const memData = await api('/api/memory');
        const memList = document.getElementById('memory-list');
        memList.innerHTML = '';
        memData.memories.forEach(m => {
            const strengthClass = m.strength > 0.7 ? 'strong' : m.strength > 0.3 ? 'medium' : 'weak';
            const div = document.createElement('div');
            div.className = 'memory-item';
            div.innerHTML = `
                <div class="memory-header">
                    <span class="memory-key">${escapeHtml(m.key)}</span>
                    <span class="memory-strength ${strengthClass}">${(m.strength * 100).toFixed(0)}%</span>
                </div>
                <div class="memory-content">${escapeHtml(m.content)}</div>
            `;
            memList.appendChild(div);
        });
    } catch (e) {
        console.error('Failed to load spine:', e);
    }
}

// ---------------------------------------------------------------------------
// Markdown Renderer (minimal, safe)
// ---------------------------------------------------------------------------

function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    // Lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
    // Paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p><(h[1-3]|ul|pre)/g, '<$1');
    html = html.replace(/<\/(h[1-3]|ul|pre)><\/p>/g, '</$1>');
    html = html.replace(/<p><\/p>/g, '');

    return html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
