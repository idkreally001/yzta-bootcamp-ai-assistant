{
    "name": "AI Business Query Assistant",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "summary": "Doğal dil ile işletme verilerini sorgulayan AI asistanı",
    "description": """
Odoo verileriniz üzerinde doğal dil ile soru sorabileceğiniz bir AI asistanı.
Sorular çok adımlı bir agent hattından geçer: niyet tespiti, sorgu planlama,
Odoo ORM üzerinden güvenli veri çekme ve doğal dilde özetleme.
""",
    "author": "idkreally001",
    "license": "LGPL-3",
    "depends": ["base", "sale_management", "stock"],
    "data": [
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "odoo_ai_query/static/src/chat.css",
            "odoo_ai_query/static/src/chat.js",
        ],
        "web.assets_backend": [
            "odoo_ai_query/static/src/systray/ai_query_systray.js",
            "odoo_ai_query/static/src/systray/ai_query_systray.xml",
        ],
    },
    "installable": True,
    "application": True,
}
