import json
import logging

from odoo import api, http
from odoo.http import request

from ..services.agent import run_agent, prepare_stream, stream_answer_text

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

    def _save_turn(self, conversation, question, result):
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

        self._save_turn(conversation, question, result)

        return {
            "answer": result["answer"],
            "model": result["model"],
            "tools": result.get("tools", []),
            "count": result["count"],
            "chart": result.get("chart"),
        }

    @http.route("/odoo-ai/chat/stream", type="http", auth="user", methods=["GET"])
    def chat_stream(self, question=None, **kwargs):
        """SSE endpoint: streams the answer text as it's generated, then a
        final `event: done` frame with the same metadata /chat returns.
        EventSource only supports GET with no custom body, hence query param."""
        question = (question or "").strip()
        if not question:
            def empty_gen():
                yield "event: error\ndata: {}\n\n".format(
                    json.dumps({"error": "Soru boş olamaz."})
                )
            return request.make_response(
                empty_gen(),
                headers=[("Content-Type", "text/event-stream")],
            )

        conversation = self._get_or_create_conversation()
        history = self._load_history(conversation)
        conversation_id = conversation.id
        registry = request.env.registry
        uid = request.env.uid

        # All ORM/RAG work happens here, synchronously, while the request's
        # cursor is still open. Only the pure-network LLM streaming below
        # runs inside the generator, which Odoo's WSGI layer iterates after
        # this handler returns (i.e. potentially after the cursor closes) —
        # so the generator captures plain values (ids, a fresh registry
        # handle) instead of holding onto request-scoped recordsets/env.
        try:
            llm, ctx = prepare_stream(request.env, question, history=history)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("AI agent prepare_stream failed")

            def error_gen():
                yield "event: error\ndata: {}\n\n".format(json.dumps({"error": str(exc)}))
            return request.make_response(
                error_gen(),
                headers=[("Content-Type", "text/event-stream")],
            )

        def generate():
            try:
                final_result = None
                for item in stream_answer_text(llm, ctx):
                    if isinstance(item, dict) and item.get("__final__"):
                        final_result = {k: v for k, v in item.items() if k != "__final__"}
                        break
                    chunk = json.dumps({"text": item})
                    yield f"event: chunk\ndata: {chunk}\n\n"

                if final_result is not None:
                    with registry.cursor() as cr:
                        env = api.Environment(cr, uid, {})
                        env["odoo.ai.conversation.line"].create({
                            "conversation_id": conversation_id,
                            "question": question,
                            "answer": final_result["answer"],
                            "model_name": final_result.get("model") or False,
                            "tools": ",".join(final_result.get("tools", [])),
                            "domain": json.dumps(final_result.get("domain") or []),
                            "field_names": (
                                json.dumps(final_result.get("fields"))
                                if final_result.get("fields") else False
                            ),
                            "limit": final_result.get("limit") or 0,
                            "order": final_result.get("order") or False,
                            "record_count": final_result.get("count", 0),
                        })
                    done_payload = json.dumps({
                        "model": final_result.get("model"),
                        "tools": final_result.get("tools", []),
                        "count": final_result.get("count", 0),
                        "chart": final_result.get("chart"),
                    })
                    yield f"event: done\ndata: {done_payload}\n\n"
            except Exception as exc:  # noqa: BLE001 — surface any agent failure to the UI
                _logger.exception("AI agent stream failed")
                yield "event: error\ndata: {}\n\n".format(json.dumps({"error": str(exc)}))

        return request.make_response(
            generate(),
            headers=[
                ("Content-Type", "text/event-stream"),
                ("Cache-Control", "no-cache"),
                ("X-Accel-Buffering", "no"),
            ],
        )

    @http.route("/odoo-ai/history", type="jsonrpc", auth="user", methods=["GET", "POST"])
    def get_history(self, **kwargs):
        """Return this session's prior turns so the UI can rehydrate the
        chat on page/panel (re)load instead of always starting empty."""
        conversation = self._get_or_create_conversation()
        turns = []
        for line in conversation.line_ids:
            turns.append({
                "question": line.question,
                "answer": line.answer,
                "model": line.model_name or None,
                "count": line.record_count,
            })
        return {"turns": turns}

    @http.route("/odoo-ai/history/clear", type="jsonrpc", auth="user", methods=["POST"])
    def clear_history(self, **kwargs):
        conversation = self._get_or_create_conversation()
        conversation.line_ids.unlink()
        return {"ok": True}
