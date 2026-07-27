import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";

class AIQuerySystrayItem extends Component {
    static template = "odoo_ai_query.SystrayItem";
    static components = { Dropdown };
    static props = {};

    setup() {
        this.dropdown = useDropdownState();
        this.state = useState({
            messages: [], // {role: 'user'|'assistant'|'error', text, meta}
            pending: false,
        });
        this.inputRef = useRef("input");
        this.messagesRef = useRef("messages");
        onMounted(() => this._scrollToBottom());
    }

    _scrollToBottom() {
        if (this.messagesRef.el) {
            this.messagesRef.el.scrollTop = this.messagesRef.el.scrollHeight;
        }
    }

    onSubmit(ev) {
        ev.preventDefault();
        const input = this.inputRef.el;
        const question = input.value.trim();
        if (!question || this.state.pending) return;
        input.value = "";
        this._ask(question);
    }

    onSuggestion(question) {
        if (this.state.pending) return;
        this._ask(question);
    }

    _ask(question) {
        this.state.messages.push({ role: "user", text: question });
        const assistantMsg = { role: "assistant", text: "", meta: null, streaming: true };
        this.state.pending = true;

        const url = "/odoo-ai/chat/stream?question=" + encodeURIComponent(question);
        const source = new EventSource(url);
        let started = false;

        source.addEventListener("chunk", (ev) => {
            if (!started) {
                started = true;
                this.state.messages.push(assistantMsg);
            }
            const data = JSON.parse(ev.data);
            assistantMsg.text += data.text;
            this._scrollToBottom();
        });
        source.addEventListener("done", (ev) => {
            const data = JSON.parse(ev.data);
            if (data.model) {
                assistantMsg.meta = `model: ${data.model} · ${data.count} kayıt`;
            }
            assistantMsg.streaming = false;
            source.close();
            this.state.pending = false;
            this._scrollToBottom();
        });
        source.addEventListener("error", (ev) => {
            source.close();
            this.state.pending = false;
            let message = "Bağlantı hatası";
            try {
                message = JSON.parse(ev.data).error || message;
            } catch {
                // ev.data may be empty on network-level errors
            }
            if (!started) {
                this.state.messages.push({ role: "error", text: message });
            } else {
                assistantMsg.streaming = false;
            }
            this._scrollToBottom();
        });
        source.onerror = () => {
            source.close();
            this.state.pending = false;
            if (!started) {
                this.state.messages.push({ role: "error", text: "Sunucu ile bağlantı kesildi." });
            }
        };
    }
}

export const aiQuerySystrayItem = {
    Component: AIQuerySystrayItem,
};

registry.category("systray").add("odoo_ai_query.systray", aiQuerySystrayItem, { sequence: 1 });
