import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

class AIQuerySystrayItem extends Component {
    static template = "odoo_ai_query.SystrayItem";
    static props = {};

    onClick() {
        // Opens in a new tab for now. The chat page's logic lives in a
        // standalone module (chat.js) so this can later be swapped for an
        // embedded slide-out panel without rewriting the chat itself.
        window.open("/odoo-ai", "_blank");
    }
}

export const aiQuerySystrayItem = {
    Component: AIQuerySystrayItem,
};

registry.category("systray").add("odoo_ai_query.systray", aiQuerySystrayItem, { sequence: 1 });
