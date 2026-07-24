from odoo import fields, models


class AIConversation(models.Model):
    _name = "odoo.ai.conversation"
    _description = "AI Query Assistant Conversation"
    _order = "create_date desc"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    session_key = fields.Char(index=True)
    line_ids = fields.One2many("odoo.ai.conversation.line", "conversation_id")
    active = fields.Boolean(default=True)


class AIConversationLine(models.Model):
    _name = "odoo.ai.conversation.line"
    _description = "AI Query Assistant Conversation Turn"
    _order = "create_date asc"

    conversation_id = fields.Many2one(
        "odoo.ai.conversation", required=True, index=True, ondelete="cascade"
    )
    question = fields.Text(required=True)
    answer = fields.Text()
    model_name = fields.Char(help="Odoo model queried by the query_data tool, if used")
    tools = fields.Char(help="Comma-separated list of tools the agent selected")
    domain = fields.Text(help="JSON-encoded domain used by the query_data tool, if any")
    field_names = fields.Text(help="JSON-encoded field list used by the query_data tool")
    limit = fields.Integer()
    order = fields.Char()
    record_count = fields.Integer()
