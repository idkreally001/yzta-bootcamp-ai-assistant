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
        onMounted(() => {
            this._loadHistory();
            this._scrollToBottom();
        });
    }

    async _loadHistory() {
        try {
            const resp = await fetch("/odoo-ai/history", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {} }),
            });
            const payload = await resp.json();
            const turns = (payload.result && payload.result.turns) || [];
            turns.forEach((turn) => {
                this.state.messages.push({ role: "user", text: turn.question });
                this.state.messages.push({
                    role: "assistant",
                    text: turn.answer,
                    meta: turn.model ? `model: ${turn.model} · ${turn.count} kayıt` : null,
                    chart: null,
                    streaming: false,
                });
            });
            this._scrollToBottom();
        } catch {
            // Non-fatal — panel still works, just starts empty this time.
        }
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

    maxChartValue(chart) {
        return Math.max(...chart.points.map((p) => p.value));
    }

    barPct(point, chart) {
        const max = this.maxChartValue(chart);
        return max > 0 ? (point.value / max) * 100 : 0;
    }

    formatValue(value) {
        return Number(value).toLocaleString("tr-TR");
    }

    _ask(question) {
        this.state.messages.push({ role: "user", text: question });
        const assistantMsg = { role: "assistant", text: "", meta: null, chart: null, streaming: true };
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
            if (data.chart && data.chart.points && data.chart.points.length) {
                assistantMsg.chart = data.chart;
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
