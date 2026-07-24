import json
import logging

from odoo import http
from odoo.http import request

from ..services.agent import run_agent

_logger = logging.getLogger(__name__)

HISTORY_TURNS = 10


class AIQueryController(http.Controller):
    @http.route("/odoo-ai", type="http", auth="user", website=False)
    def chat_page(self, **kwargs):
        return request.render("odoo_ai_query.chat_page", {})

    def _get_or_create_conversation(self):
        session_key = request.session.sid
        Conversation = request.env["odoo.ai.conversation"]
        conversation = Conversation.search(
            [("user_id", "=", request.env.uid), ("session_key", "=", session_key)],
            limit=1,
        )
        if not conversation:
            conversation = Conversation.create(
                {"user_id": request.env.uid, "session_key": session_key}
            )
        return conversation

    def _load_history(self, conversation):
        lines = conversation.line_ids[-HISTORY_TURNS:]
        history = []
        for line in lines:
            history.append({
                "question": line.question,
                "answer": line.answer,
                "model": line.model_name or None,
                "tools": (line.tools or "").split(",") if line.tools else [],
                "domain": json.loads(line.domain) if line.domain else [],
                "fields": json.loads(line.field_names) if line.field_names else None,
                "limit": line.limit or None,
                "order": line.order or None,
                "count": line.record_count,
            })
        return history

    @http.route("/odoo-ai/chat", type="jsonrpc", auth="user", methods=["POST"])
    def chat(self, question=None, **kwargs):
        question = (question or "").strip()
        if not question:
            return {"error": "Soru boş olamaz."}

        conversation = self._get_or_create_conversation()
        history = self._load_history(conversation)

        try:
            result = run_agent(request.env, question, history=history)
        except Exception as exc:  # noqa: BLE001 — surface any agent failure to the UI
            _logger.exception("AI agent failed")
            return {"error": f"Bir hata oluştu: {exc}"}

        request.env["odoo.ai.conversation.line"].create({
            "conversation_id": conversation.id,
            "question": question,
            "answer": result["answer"],
            "model_name": result.get("model") or False,
            "tools": ",".join(result.get("tools", [])),
            "domain": json.dumps(result.get("domain") or []),
            "field_names": json.dumps(result.get("fields")) if result.get("fields") else False,
            "limit": result.get("limit") or 0,
            "order": result.get("order") or False,
            "record_count": result["count"],
        })

        return {
            "answer": result["answer"],
            "model": result["model"],
            "tools": result.get("tools", []),
            "count": result["count"],
        }

    @http.route("/odoo-ai/history", type="jsonrpc", auth="user", methods=["POST"])
    def clear_history(self, **kwargs):
        conversation = self._get_or_create_conversation()
        conversation.line_ids.unlink()
        return {"ok": True}
