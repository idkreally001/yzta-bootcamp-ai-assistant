import logging

from odoo import http
from odoo.http import request

from ..services.agent import run_agent

_logger = logging.getLogger(__name__)

# Conversation history kept in-process, keyed by Odoo session id.
# Fine for a bootcamp demo; would move to a persisted model for production.
_SESSION_HISTORY = {}


class AIQueryController(http.Controller):
    @http.route("/odoo-ai", type="http", auth="user", website=False)
    def chat_page(self, **kwargs):
        return request.render("odoo_ai_query.chat_page", {})

    @http.route("/odoo-ai/chat", type="jsonrpc", auth="user", methods=["POST"])
    def chat(self, question=None, **kwargs):
        question = (question or "").strip()
        if not question:
            return {"error": "Soru boş olamaz."}

        session_key = request.session.sid
        history = _SESSION_HISTORY.setdefault(session_key, [])

        try:
            result = run_agent(request.env, question, history=history)
        except Exception as exc:  # noqa: BLE001 — surface any agent failure to the UI
            _logger.exception("AI agent failed")
            return {"error": f"Bir hata oluştu: {exc}"}

        history.append({
            "question": question,
            "answer": result["answer"],
            "model": result["model"],
            "tools": result.get("tools", []),
            "domain": result.get("domain", []),
            "fields": result.get("fields"),
            "limit": result.get("limit"),
            "order": result.get("order"),
            "count": result["count"],
        })
        history[:] = history[-10:]  # keep last 10 turns

        return {
            "answer": result["answer"],
            "model": result["model"],
            "tools": result.get("tools", []),
            "count": result["count"],
        }

    @http.route("/odoo-ai/history", type="jsonrpc", auth="user", methods=["POST"])
    def clear_history(self, **kwargs):
        _SESSION_HISTORY.pop(request.session.sid, None)
        return {"ok": True}
