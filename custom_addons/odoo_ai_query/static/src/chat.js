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

    async function sendQuestion(question) {
        const resp = await fetch("/odoo-ai/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { question: question } }),
        });
        const payload = await resp.json();
        return payload.result || {};
    }

    async function handleQuestion(question) {
        removeEmptyState();
        appendMessage(question, "user");
        const typingRow = appendTyping();
        inputEl.disabled = true;
        submitEl.disabled = true;

        try {
            const result = await sendQuestion(question);
            typingRow.remove();
            if (result.error) {
                appendMessage(result.error, "error");
            } else {
                const meta = result.model
                    ? `model: ${result.model} · ${result.count} kayıt`
                    : null;
                appendMessage(result.answer, "assistant", meta);
            }
        } catch (err) {
            typingRow.remove();
            appendMessage("Sunucuya bağlanılamadı: " + err, "error");
        } finally {
            inputEl.disabled = false;
            submitEl.disabled = false;
            inputEl.focus();
        }
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
