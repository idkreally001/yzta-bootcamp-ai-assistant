(function () {
    "use strict";

    const messagesEl = document.getElementById("ai-chat-messages");
    const formEl = document.getElementById("ai-chat-form");
    const inputEl = document.getElementById("ai-chat-input");
    const submitEl = document.getElementById("ai-chat-submit");
    const emptyStateEl = document.getElementById("ai-chat-empty-state");

    function removeEmptyState() {
        if (emptyStateEl) emptyStateEl.remove();
    }

    function appendMessage(text, role, meta) {
        const row = document.createElement("div");
        row.className = "ai-msg-row " + role;

        const avatar = document.createElement("div");
        avatar.className = "ai-avatar " + (role === "user" ? "user" : "assistant");
        avatar.innerHTML = role === "user"
            ? '<i class="fa fa-user"/>'
            : '<i class="fa fa-magic"/>';

        const bubble = document.createElement("div");
        bubble.className = "ai-msg";
        bubble.textContent = text;
        if (meta) {
            const metaEl = document.createElement("span");
            metaEl.className = "meta";
            metaEl.textContent = meta;
            bubble.appendChild(metaEl);
        }

        row.appendChild(avatar);
        row.appendChild(bubble);
        messagesEl.appendChild(row);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return row;
    }

    function appendTyping() {
        const row = document.createElement("div");
        row.className = "ai-msg-row assistant";
        row.id = "ai-typing-row";
        row.innerHTML =
            '<div class="ai-avatar assistant"><i class="fa fa-magic"/></div>' +
            '<div class="ai-msg"><div class="ai-typing"><span/><span/><span/></div></div>';
        messagesEl.appendChild(row);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return row;
    }

    function streamQuestion(question, { onChunk, onDone, onError }) {
        const url = "/odoo-ai/chat/stream?question=" + encodeURIComponent(question);
        const source = new EventSource(url);

        source.addEventListener("chunk", function (ev) {
            const data = JSON.parse(ev.data);
            onChunk(data.text);
        });
        source.addEventListener("done", function (ev) {
            const data = JSON.parse(ev.data);
            source.close();
            onDone(data);
        });
        source.addEventListener("error", function (ev) {
            source.close();
            let message = "Bağlantı hatası";
            try {
                message = JSON.parse(ev.data).error || message;
            } catch (e) {
                // ev.data may be empty on network-level errors (no server payload)
            }
            onError(message);
        });
        // Native EventSource "error" fires on any connection failure too,
        // without necessarily going through our named "error" event above.
        source.onerror = function () {
            source.close();
            onError("Sunucu ile bağlantı kesildi.");
        };
    }

    function handleQuestion(question) {
        removeEmptyState();
        appendMessage(question, "user");
        const typingRow = appendTyping();
        inputEl.disabled = true;
        submitEl.disabled = true;

        let bubbleRow = null;
        let bubbleEl = null;
        let fullText = "";
        let settled = false;

        function finish() {
            if (settled) return;
            settled = true;
            inputEl.disabled = false;
            submitEl.disabled = false;
            inputEl.focus();
        }

        streamQuestion(question, {
            onChunk: function (text) {
                if (!bubbleRow) {
                    typingRow.remove();
                    bubbleRow = appendMessage("", "assistant");
                    bubbleEl = bubbleRow.querySelector(".ai-msg");
                }
                fullText += text;
                bubbleEl.textContent = fullText;
                messagesEl.scrollTop = messagesEl.scrollHeight;
            },
            onDone: function (meta) {
                if (bubbleEl && meta.model) {
                    const metaEl = document.createElement("span");
                    metaEl.className = "meta";
                    metaEl.textContent = `model: ${meta.model} · ${meta.count} kayıt`;
                    bubbleEl.appendChild(metaEl);
                }
                finish();
            },
            onError: function (message) {
                typingRow.remove();
                if (bubbleRow) bubbleRow.remove();
                appendMessage(message, "error");
                finish();
            },
        });
    }

    formEl.addEventListener("submit", function (ev) {
        ev.preventDefault();
        const question = inputEl.value.trim();
        if (!question) return;
        inputEl.value = "";
        handleQuestion(question);
    });

    document.querySelectorAll(".ai-suggestion-chip").forEach(function (chip) {
        chip.addEventListener("click", function () {
            handleQuestion(chip.dataset.question);
        });
    });

    inputEl.focus();
})();
