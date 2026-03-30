const API_BASE = "http://localhost:8200";
const STORAGE_KEY = "openteddy_username";

const loginScreen = document.getElementById("login-screen");
const chatScreen = document.getElementById("chat-screen");
const usernameInput = document.getElementById("username-input");
const loginBtn = document.getElementById("login-btn");
const messagesEl = document.getElementById("messages");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const headerUsername = document.getElementById("header-username");
const statusText = document.getElementById("status-text");
const logoutBtn = document.getElementById("logout-btn");

let username = "";

// ─── Init ───
function init() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
        username = saved;
        showChat();
    } else {
        showLogin();
    }
}

// ─── Login ───
function showLogin() {
    loginScreen.classList.remove("hidden");
    chatScreen.classList.add("hidden");
    usernameInput.value = "";
    usernameInput.focus();
}

function showChat() {
    loginScreen.classList.add("hidden");
    chatScreen.classList.remove("hidden");
    headerUsername.textContent = username;
    messageInput.focus();
}

usernameInput.addEventListener("input", () => {
    loginBtn.disabled = usernameInput.value.trim().length === 0;
});

usernameInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !loginBtn.disabled) {
        doLogin();
    }
});

loginBtn.addEventListener("click", doLogin);

function doLogin() {
    username = usernameInput.value.trim();
    if (!username) return;
    localStorage.setItem(STORAGE_KEY, username);
    showChat();
}

logoutBtn.addEventListener("click", () => {
    localStorage.removeItem(STORAGE_KEY);
    username = "";
    messagesEl.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-bear">
                <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="18" cy="18" r="14" fill="#d4a054" opacity="0.6"/>
                    <circle cx="62" cy="18" r="14" fill="#d4a054" opacity="0.6"/>
                    <circle cx="40" cy="42" r="28" fill="#d4a054" opacity="0.8"/>
                    <circle cx="31" cy="36" r="3.5" fill="#1a1d23"/>
                    <circle cx="49" cy="36" r="3.5" fill="#1a1d23"/>
                    <ellipse cx="40" cy="46" rx="6" ry="4.5" fill="#1a1d23" opacity="0.7"/>
                    <path d="M34 52 Q40 58 46 52" stroke="#1a1d23" stroke-width="2" fill="none" stroke-linecap="round"/>
                </svg>
            </div>
            <p class="welcome-text">Hi! I'm your ETIM classification assistant.<br>Ask me to classify products, create spreadsheets, or browse the web.</p>
        </div>`;
    showLogin();
});

// ─── Chat ───
function addMessage(role, text) {
    // Remove welcome message on first real message
    const welcome = messagesEl.querySelector(".welcome-message");
    if (welcome) welcome.remove();

    const msg = document.createElement("div");
    msg.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";

    if (role === "assistant") {
        avatar.innerHTML = `<svg viewBox="0 0 80 80" fill="none"><circle cx="18" cy="18" r="14" fill="#d4a054" opacity="0.8"/><circle cx="62" cy="18" r="14" fill="#d4a054" opacity="0.8"/><circle cx="40" cy="42" r="28" fill="#d4a054"/><circle cx="31" cy="36" r="3.5" fill="#1a1d23"/><circle cx="49" cy="36" r="3.5" fill="#1a1d23"/><ellipse cx="40" cy="46" rx="6" ry="4.5" fill="#1a1d23" opacity="0.7"/></svg>`;
    } else {
        avatar.textContent = username.charAt(0).toUpperCase();
    }

    const content = document.createElement("div");
    content.className = "message-content";

    const etimData = tryParseEtimJson(text);
    if (role === "assistant" && etimData) {
        content.innerHTML = renderEtimCard(etimData, text);
    } else {
        content.innerHTML = renderMarkdown(text);
    }

    msg.appendChild(avatar);
    msg.appendChild(content);
    messagesEl.appendChild(msg);
    scrollToBottom();
}

// ─── ETIM card detection & rendering ───
function tryParseEtimJson(text) {
    // Try to extract JSON from the text (may be wrapped in markdown code block or bare)
    let jsonStr = null;

    // Try: ```json ... ```
    const codeBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
    if (codeBlockMatch) jsonStr = codeBlockMatch[1].trim();

    // Try: bare JSON object
    if (!jsonStr) {
        const braceMatch = text.match(/\{[\s\S]*\}/);
        if (braceMatch) jsonStr = braceMatch[0];
    }

    if (!jsonStr) return null;

    try {
        const obj = JSON.parse(jsonStr);
        if (obj.class_code && obj.group_code) return obj;
    } catch {}
    return null;
}

function renderEtimCard(d, rawText) {
    const cardId = "etim-" + Math.random().toString(36).slice(2, 8);

    const isFilled = !!(d.filled_features && d.filled_features.length);
    const featuresList = isFilled ? d.filled_features : (d.features || []);

    const featuresHtml = featuresList.map(f => {
        const code = f.code ? `<span class="etim-feature-code">${escapeHtml(f.code)}</span>` : "";
        const label = escapeHtml(f.nl || f.en || f);
        const sub = f.en && f.nl ? `<div class="etim-feature-en">${escapeHtml(f.en)}</div>` : "";

        if (isFilled) {
            const hasEvCode = f.value_code && f.value_label;
            const displayVal = hasEvCode
                ? f.value_label
                : (f.value !== null && f.value !== undefined ? String(f.value) : "—");
            const unit = f.unit && !hasEvCode ? ` ${escapeHtml(f.unit)}` : "";
            const evBadge = hasEvCode ? `<span class="etim-ev-code">${escapeHtml(f.value_code)}</span>` : "";
            const conf = f.value_confidence || "unknown";
            const confClass = `etim-val-${conf}`;
            const source = f.value_source ? `<div class="etim-val-source">${escapeHtml(f.value_source)}</div>` : "";
            return `<div class="etim-feature-item etim-filled-feature">
                <div class="etim-feature-header">${code}<span class="etim-feature-label">${label}</span></div>
                <div class="etim-feature-value-row">
                    ${evBadge}<span class="etim-feature-value ${confClass}">${escapeHtml(displayVal)}${unit}</span>
                    <span class="etim-val-badge ${confClass}">${escapeHtml(conf)}</span>
                </div>
                ${source}${sub}
            </div>`;
        }

        return `<div class="etim-feature-item">${code}<span class="etim-feature-label">${label}</span>${sub}</div>`;
    }).join("");

    const synNlHtml = (d.synonyms_nl || []).map(s => `<span class="etim-syn-tag">${escapeHtml(s)}</span>`).join("");
    const synEnHtml = (d.synonyms_en || []).map(s => `<span class="etim-syn-tag en">${escapeHtml(s)}</span>`).join("");

    const hasSynonyms = (d.synonyms_en && d.synonyms_en.length) || (d.synonyms_nl && d.synonyms_nl.length);

    const confidenceHtml = d.confidence
        ? `<span class="etim-confidence etim-confidence-${d.confidence}">${escapeHtml(d.confidence)}</span>`
        : "";

    const reasoningHtml = d.reasoning
        ? `<div class="etim-reasoning">${escapeHtml(d.reasoning)}</div>`
        : "";

    const sourceUrlHtml = d.source_url
        ? `<div class="etim-source-url"><span class="etim-source-label">Bron:</span> <a href="${escapeHtml(d.source_url)}" target="_blank" rel="noopener">${escapeHtml(d.source_url)}</a></div>`
        : "";

    return `
        <div class="etim-card">
            ${sourceUrlHtml}
            <div class="etim-hero">
                <div class="etim-eyebrow">
                    <span class="etim-group-badge">${escapeHtml(d.group_code)}</span>
                    <span class="etim-group-name">${escapeHtml(d.group_description_nl || d.group_description_en || "")}</span>
                    ${confidenceHtml}
                </div>
                <a class="etim-class-code" href="https://prod.etim-international.com/Class/Details?classId=${encodeURIComponent(d.class_code)}" target="_blank" rel="noopener">${escapeHtml(d.class_code)}</a>
                <div class="etim-class-desc">${escapeHtml(d.class_description_nl || d.class_description_en || "")}</div>
                <div class="etim-class-desc-sub">${escapeHtml(d.class_description_en || "")}</div>
                ${reasoningHtml}
            </div>

            ${featuresList.length ? `
            <div class="etim-section">
                <div class="etim-section-header">
                    <span class="etim-section-title">${isFilled ? "Kenmerken (ingevuld)" : "Kenmerken"}</span>
                    <span class="etim-section-count">${featuresList.length}</span>
                </div>
                <div class="etim-features-grid ${isFilled ? 'etim-features-filled' : ''}">${featuresHtml}</div>
            </div>` : ""}

            ${hasSynonyms ? `
            <div class="etim-section">
                <div class="etim-section-header">
                    <span class="etim-section-title">Synoniemen</span>
                    <div class="etim-lang-toggle">
                        <button class="etim-lang-btn active" onclick="toggleEtimSyn('${cardId}','nl',this)">NL</button>
                        <button class="etim-lang-btn" onclick="toggleEtimSyn('${cardId}','en',this)">EN</button>
                        <button class="etim-lang-btn" onclick="toggleEtimSyn('${cardId}','all',this)">Alle</button>
                    </div>
                </div>
                <div class="etim-syn-wrap" id="${cardId}-syn-nl">${synNlHtml}</div>
                <div class="etim-syn-wrap" id="${cardId}-syn-en" style="display:none">${synEnHtml}</div>
                <div class="etim-syn-wrap" id="${cardId}-syn-all" style="display:none">${synNlHtml}${synEnHtml}</div>
            </div>` : ""}

            <div class="etim-raw-toggle">
                <button class="etim-raw-btn" onclick="toggleEtimRaw('${cardId}',this)">
                    <span>View raw JSON</span>
                    <span class="etim-chevron">&#9662;</span>
                </button>
            </div>
            <pre class="etim-raw-json" id="${cardId}-raw">${syntaxHighlightJson(JSON.stringify(d, null, 2))}</pre>
        </div>
    `;
}

function toggleEtimSyn(cardId, lang, btn) {
    btn.closest('.etim-lang-toggle').querySelectorAll('.etim-lang-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    ['en','nl','all'].forEach(l => {
        const el = document.getElementById(`${cardId}-syn-${l}`);
        if (el) el.style.display = l === lang ? 'flex' : 'none';
    });
}

function toggleEtimRaw(cardId, btn) {
    const el = document.getElementById(`${cardId}-raw`);
    const visible = el.style.display === 'block';
    el.style.display = visible ? 'none' : 'block';
    btn.classList.toggle('open', !visible);
    btn.querySelector('span').textContent = visible ? 'View raw JSON' : 'Hide raw JSON';
}

function syntaxHighlightJson(json) {
    return escapeHtml(json)
        .replace(/"([^"]+)"(?=\s*:)/g, '<span class="json-key">"$1"</span>')
        .replace(/:\s*"([^"]*?)"/g, ': <span class="json-string">"$1"</span>')
        .replace(/[{}\[\]]/g, '<span class="json-bracket">$&</span>');
}

function addTypingIndicator() {
    const msg = document.createElement("div");
    msg.className = "message assistant";
    msg.id = "typing";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.innerHTML = `<svg viewBox="0 0 80 80" fill="none"><circle cx="18" cy="18" r="14" fill="#d4a054" opacity="0.8"/><circle cx="62" cy="18" r="14" fill="#d4a054" opacity="0.8"/><circle cx="40" cy="42" r="28" fill="#d4a054"/><circle cx="31" cy="36" r="3.5" fill="#1a1d23"/><circle cx="49" cy="36" r="3.5" fill="#1a1d23"/><ellipse cx="40" cy="46" rx="6" ry="4.5" fill="#1a1d23" opacity="0.7"/></svg>`;

    const content = document.createElement("div");
    content.className = "message-content";
    content.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;

    msg.appendChild(avatar);
    msg.appendChild(content);
    messagesEl.appendChild(msg);
    scrollToBottom();
}

function removeTypingIndicator() {
    const el = document.getElementById("typing");
    if (el) el.remove();
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;

    messageInput.value = "";
    messageInput.style.height = "auto";
    sendBtn.disabled = true;

    addMessage("user", text);
    addTypingIndicator();
    statusText.textContent = "Thinking...";

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, username }),
        });

        removeTypingIndicator();

        if (!res.ok) {
            const err = await res.text();
            addMessage("assistant", `Error: ${res.status} - ${err}`);
            statusText.textContent = "Error";
            return;
        }

        const data = await res.json();
        addMessage("assistant", data.response);
        statusText.textContent = "Ready";
    } catch (err) {
        removeTypingIndicator();
        addMessage("assistant", `Could not reach the server. Is it running?\n\n\`${err.message}\``);
        statusText.textContent = "Disconnected";
    } finally {
        sendBtn.disabled = messageInput.value.trim().length === 0;
    }
}

sendBtn.addEventListener("click", sendMessage);

messageInput.addEventListener("input", () => {
    sendBtn.disabled = messageInput.value.trim().length === 0;
    // Auto-grow textarea
    messageInput.style.height = "auto";
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
});

messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) sendMessage();
    }
});

// ─── Simple markdown renderer ───
function renderMarkdown(text) {
    let html = escapeHtml(text);

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
        `<pre><code>${code.trim()}</code></pre>`
    );

    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    // Italic
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Tables
    html = html.replace(/^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)+)/gm, (_, header, sep, body) => {
        const ths = header.split("|").filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join("");
        const rows = body.trim().split("\n").map(row => {
            const tds = row.split("|").filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join("");
            return `<tr>${tds}</tr>`;
        }).join("");
        return `<table><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
    });

    // Unordered lists
    html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);

    // Headers
    html = html.replace(/^### (.+)$/gm, "<strong>$1</strong>");
    html = html.replace(/^## (.+)$/gm, "<strong>$1</strong>");
    html = html.replace(/^# (.+)$/gm, "<strong>$1</strong>");

    // Line breaks → paragraphs
    html = html.replace(/\n\n+/g, "</p><p>");
    html = `<p>${html}</p>`;
    html = html.replace(/<p>\s*<\/p>/g, "");

    // Single newlines within paragraphs
    html = html.replace(/\n/g, "<br>");

    return html;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ─── Boot ───
init();
