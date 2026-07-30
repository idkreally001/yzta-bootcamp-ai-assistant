import logging
import os

from . import rag_store
from .gemini_client import GeminiClient
from .lmstudio_client import LMStudioClient

_logger = logging.getLogger(__name__)

# Safety: hard allowlist of queryable models + their exposed fields.
# The LLM can only ever request data through this whitelist — never raw SQL,
# never fields outside this list, never write/delete operations.
ALLOWED_MODELS = {
    "sale.order": {
        "label": "Satış Siparişleri",
        "fields": ["name", "partner_id", "amount_total", "state", "date_order"],
        "chart_label_field": "name",
        "chart_value_field": "amount_total",
    },
    "product.product": {
        "label": "Ürünler",
        "fields": ["name", "list_price", "default_code", "type", "categ_id"],
        "chart_label_field": "name",
        "chart_value_field": "list_price",
    },
    "stock.quant": {
        "label": "Stok Durumu",
        "fields": ["product_id", "quantity", "location_id"],
        "chart_label_field": "product_id",
        "chart_value_field": "quantity",
    },
}

# Only render a chart for small, genuinely comparable result sets — a 24-row
# bar chart is noise, not insight.
CHART_MAX_ROWS = 10

MAX_ROWS = 50


def get_llm_client():
    backend = os.environ.get("AI_QUERY_BACKEND", "gemini").lower()
    if backend == "lmstudio":
        return LMStudioClient()
    return GeminiClient()


def _validate_domain(domain):
    """Reject anything that isn't a flat list of [field, operator, value] triples."""
    if not isinstance(domain, list):
        raise ValueError("domain must be a list")
    for clause in domain:
        if not (isinstance(clause, list) and len(clause) == 3):
            raise ValueError(f"invalid domain clause: {clause!r}")
        field, op, _value = clause
        if not isinstance(field, str) or not isinstance(op, str):
            raise ValueError(f"invalid domain clause types: {clause!r}")
    return domain


TOOL_ROUTER_PROMPT = """Sen bir Odoo iş asistanısın. Kullanıcının sorusuna yanıt vermek için
hangi araç(lar)ın kullanılması gerektiğine karar ver.

Kullanılabilir araçlar:
1. query_data — canlı işletme verisi sorgular (satış siparişleri, ürünler, stok miktarları).
   Sayısal/listeleme sorularında kullanılır (örn. "kaç sipariş var", "en pahalı ürünler").
   Sorgulanabilir modeller: {models}
2. search_docs — Odoo kullanım rehberi / SSS içinde arama yapar (örn. "sipariş nasıl
   oluşturulur", "iade nasıl yapılır", süreç/prosedür soruları — canlı veri değil).

DİKKAT: Yalnızca cümlede "sipariş", "ürün", "stok" gibi kelimeler geçiyor diye araç seçme.
Sorunun GERÇEK NİYETİNİ değerlendir. "Pasta nasıl yapılır" gibi işle alakasız bir soru,
içinde "satış siparişi" kelimesi geçse bile Odoo/işletme ile ilgili DEĞİLDİR — bu durumda
tools boş liste [] olmalı. Test: bu soru gerçekten Odoo'daki bir işletme sürecini mi
soruyor, yoksa tamamen alakasız bir konuda mı (yemek tarifi, hava durumu, vb.)?

Son konuşma geçmişi (araç, model, soru):
{recent_turns}

VARSAYILAN KURAL: Kullanıcının sorusu kısa/belirsizse (örn. "kimlerden?", "fiyatları?",
"ücretleri?", "ne zaman?", "toplamı?") EN SON TURDAKİ ARAÇ VE MODELİ TEKRAR SEÇ. Bu tür
sorular neredeyse her zaman önceki sonuç kümesinin bir detayını sorar. Hangi bağlamda
olduğumuzu SON TURDAN anla, kelimenin kendisinden değil.

Yalnızca kullanıcı YENİ bir konu için AÇIK bir isim/kelime kullanırsa araç/model değiştir.
Bir soru hem canlı veri hem prosedür bilgisi gerektiriyorsa iki aracı da seçebilirsin.

Yalnızca şu JSON formatında yanıt ver:
{{"tools": ["query_data" | "search_docs", ...], "model": "<query_data için model.name ya da null>", "reasoning": "<kısa açıklama>"}}

Eğer soru hiçbir araçla ilgili değilse tools boş liste [] yap.
"""

PLAN_PROMPT = """Sen bir Odoo ORM sorgu planlayıcısısın. Kullanıcının sorusunu ve seçilen
modeli kullanarak bir Odoo domain filtresi ve alan listesi oluştur.

Model: {model}
Kullanılabilir alanlar: {fields}

Odoo domain formatı: [["alan", "operatör", "değer"], ...]
Operatörler: =, !=, >, <, >=, <=, like, ilike, in, not in

Sıralama gerekiyorsa (örn. "en pahalı", "en çok", "en yüksek") order alanını kullan.
Order formatı: "alan_adi desc" veya "alan_adi asc" (örn. "list_price desc").

Yalnızca şu JSON formatında yanıt ver:
{{"domain": [...], "fields": [...], "order": "<alan asc|desc ya da boş string>", "limit": <int, max 50>, "filter_changed": <true|false>}}

filter_changed alanı ÇOK ÖNEMLİDİR:
- Kullanıcı önceki sorgudan FARKLI bir filtre/kısıtlama istiyorsa (örn. "sadece X olanlar",
  "en pahalı N", belirli bir tarih/müşteri): filter_changed=true, yeni domain'i buna göre kur.
- Kullanıcı sadece önceki sonuç kümesi hakkında farklı bir DETAY soruyorsa (örn. "kimlerden?",
  "fiyatları?", "ücretleri peki", "toplamı ne?"): filter_changed=false, domain'i önemli değil
  (yok sayılacak), aynı kayıt kümesi kullanılacaktır.

Sorgu çok genelse (örn. "tüm siparişler") domain'i boş liste [] yap ve filter_changed=true yap.
"En pahalı N" / "en çok satan N" gibi sorularda limit'i N yap ve order'ı buna göre ayarla.

Önceki tur (varsa, aynı model üzerinde): {previous_turn}

Bugünün tarihi: {today}
"""

SUMMARY_PROMPT = """Sen bir işletme verisi asistanısın. Aşağıdaki bilgiyi kullanıcının
sorusuna doğal, kısa ve net bir Türkçe yanıt haline getir. Sayısal özetler
(toplam, ortalama, en yüksek/düşük) varsa SADECE aşağıdaki ham veriden hesapla.

ÖNEMLİ: Yalnızca aşağıda verilen bilgiyi kullan. Listede olmayan bir kayıttan
(örn. uydurma sipariş numarası) asla bahsetme. "Bulunan kayıt sayısı" değeri her
zaman doğrudur — önceki konuşmadaki bir sayıyla çelişse bile bu sayıyı kullan ve
gerekirse farkı kullanıcıya açıkla (örn. filtre değişti, farklı bir alt küme sorgulandı).

Kullanıcının orijinal sorusu: {question}

--- Canlı veri sonucu (varsa) ---
Sorgulanan model: {model}
Bulunan kayıt sayısı: {count}
Ham veri (JSON): {data}

--- SSS/rehber sonucu (varsa) ---
{doc_context}

Yalnızca doğal dilde yanıt ver, JSON değil, markdown formatlaması kullanma.
"""


def run_agent(env, question, history=None):
    """Agentic pipeline: tool routing -> (query_data and/or search_docs) -> summarize.

    Returns dict: {answer, model, count, steps, ...} — same shape as before,
    now implemented on top of _prepare_context() + a non-streaming complete_text().
    """
    llm = get_llm_client()
    ctx = _prepare_context(env, question, llm, history=history)
    if ctx.get("early_return"):
        return ctx["early_return"]

    answer = llm.complete_text(
        "Sen yardımsever bir işletme veri asistanısın.",
        _summary_prompt(ctx),
    )
    ctx["trace"].append({"step": "summarize", "output": {"answer": answer}})
    return _finalize(ctx, answer)


def prepare_stream(env, question, history=None):
    """Eagerly run all ORM/RAG work (steps 1-3) and return everything needed
    to stream the final answer text without touching `env` again. Safe to
    call from a request handler and then hand the result to a generator that
    outlives the request's cursor (e.g. an HTTP streaming response).

    Returns (llm, ctx). If ctx has "early_return", there's no LLM streaming
    to do — use ctx["early_return"] directly as the final result.
    """
    llm = get_llm_client()
    ctx = _prepare_context(env, question, llm, history=history)
    return llm, ctx


def stream_answer_text(llm, ctx):
    """Pure network/LLM generator, no ORM access — safe to iterate after the
    originating request's cursor has closed. Yields text chunks, then a
    final {"__final__": True, **result} dict."""
    if ctx.get("early_return"):
        result = ctx["early_return"]
        yield result["answer"]
        yield {"__final__": True, **result}
        return

    chunks = []
    for chunk in llm.stream_text("Sen yardımsever bir işletme veri asistanısın.", _summary_prompt(ctx)):
        chunks.append(chunk)
        yield chunk
    answer = "".join(chunks)
    ctx["trace"].append({"step": "summarize", "output": {"answer": answer}})
    yield {"__final__": True, **_finalize(ctx, answer)}


def _summary_prompt(ctx):
    doc_context = (
        "\n\n".join(f"[{d['title']}]\n{d['content']}" for d in ctx["doc_hits"]) or "(yok)"
    )
    model = ctx["model"]
    return SUMMARY_PROMPT.format(
        question=ctx["question"],
        model=ALLOWED_MODELS[model]["label"] if model else "(yok)",
        count=len(ctx["records"]),
        data=ctx["records"][:MAX_ROWS],
        doc_context=doc_context,
    )


def _finalize(ctx, answer):
    return {
        "answer": answer,
        "model": ctx["model"],
        "count": len(ctx["records"]),
        "tools": ctx["tools"],
        "domain": ctx["domain"],
        "fields": ctx["fields"],
        "limit": ctx["limit"],
        "order": ctx["order"],
        "chart": _build_chart(ctx["model"], ctx["records"]),
        "steps": ctx["trace"],
    }


def _build_chart(model, records):
    """Deterministic (non-LLM) bar-chart spec for small, comparable result
    sets — avoids asking the model to emit chart data mixed with free text,
    which would be fragile to parse and awkward to stream."""
    if not model or not records or len(records) > CHART_MAX_ROWS:
        return None

    config = ALLOWED_MODELS[model]
    label_field = config.get("chart_label_field")
    value_field = config.get("chart_value_field")
    if not label_field or not value_field:
        return None

    points = []
    for rec in records:
        value = rec.get(value_field)
        if not isinstance(value, (int, float)):
            continue
        label = rec.get(label_field)
        if isinstance(label, (list, tuple)) and len(label) == 2:
            label = label[1]  # many2one -> [id, display_name]
        points.append({"label": str(label), "value": value})

    if len(points) < 2:  # a chart with one bar isn't useful
        return None
    return {"points": points, "value_label": value_field}


def _prepare_context(env, question, llm, history=None):
    """Steps 1-3 of the pipeline: tool routing, query planning/execution,
    and/or RAG retrieval. Returns everything the summarize step needs.

    The router picks one or both tools per question — this is genuine agentic
    tool-selection, not a fixed sequence: a data question skips RAG entirely,
    a procedural question skips the ORM query entirely, and a mixed question
    (rare) can trigger both, merged into one summary.
    """
    history = history or []
    trace = []

    # Step 1: tool routing
    models_desc = "\n".join(f"- {m}: {info['label']}" for m, info in ALLOWED_MODELS.items())
    recent_turns = "\n".join(
        f"- araç={h.get('tools')}, model={h.get('model')}, soru={h['question']!r}"
        for h in history[-3:]
    ) or "(yok)"
    routing = llm.complete_json(
        TOOL_ROUTER_PROMPT.format(models=models_desc, recent_turns=recent_turns),
        question,
    )
    trace.append({"step": "route", "output": routing})

    tools = routing.get("tools") or []
    model = routing.get("model")

    if not tools:
        return {
            "early_return": {
                "answer": "Bu soruyu mevcut verilerle yanıtlayamıyorum. Satış siparişleri, "
                "ürünler, stok durumu veya Odoo kullanım rehberi hakkında sorabilirsiniz.",
                "model": None,
                "count": 0,
                "tools": [],
                "steps": trace,
            }
        }

    records = []
    domain = fields = limit = order = None
    previous_turn = None

    if "query_data" in tools and model in ALLOWED_MODELS:
        # Step 2a: query planning
        allowed_fields = ALLOWED_MODELS[model]["fields"]
        previous_turn = _previous_turn_context(history, model)
        plan = llm.complete_json(
            PLAN_PROMPT.format(
                model=model,
                fields=allowed_fields,
                previous_turn=previous_turn,
                today=env.context.get("today") or "",
            ),
            question,
        )
        trace.append({"step": "plan", "output": plan})

        filter_changed = plan.get("filter_changed", True)
        if not filter_changed and previous_turn and previous_turn.get("domain") is not None:
            # Mechanically reuse the prior turn's exact query — never trust the
            # LLM to faithfully reconstruct "no change" from a text description,
            # since it tends to silently invent a different (wrong) filter.
            domain = previous_turn["domain"]
            fields = previous_turn.get("fields") or allowed_fields
            limit = previous_turn.get("limit") or MAX_ROWS
            order = previous_turn.get("order")
        else:
            domain = _validate_domain(plan.get("domain", []))
            requested_fields = plan.get("fields") or allowed_fields
            fields = [f for f in requested_fields if f in allowed_fields]
            if not fields:
                fields = allowed_fields
            limit = min(int(plan.get("limit") or MAX_ROWS), MAX_ROWS)
            order = plan.get("order") or None
            if order:
                order_field = order.split()[0]
                if order_field not in allowed_fields:
                    order = None

        # Step 3a: execute — read-only, under the calling user's own ACL/record rules
        records = env[model].search_read(domain, fields, limit=limit, order=order)
        trace.append({"step": "execute", "output": {"count": len(records)}})
    else:
        model = None

    doc_hits = []
    if "search_docs" in tools:
        # Step 2b/3b: RAG retrieval over the Odoo usage FAQ
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                doc_hits = rag_store.search_docs(question, api_key)
            except Exception:
                _logger.exception("RAG search failed")
        trace.append({"step": "search_docs", "output": {"hits": len(doc_hits)}})

    if not records and not doc_hits:
        return {
            "early_return": {
                "answer": "Bu konuda mevcut verilerde veya rehberde bir sonuç bulamadım.",
                "model": model,
                "count": 0,
                "tools": tools,
                "domain": domain,
                "steps": trace,
            }
        }

    # Data sent to the LLM is capped at MAX_ROWS (same as the query limit) so
    # the visible row count always matches `count` — a mismatch here previously
    # caused the model to narrate a wrong total taken from the truncated list.
    return {
        "question": question,
        "model": model,
        "records": records,
        "doc_hits": doc_hits,
        "tools": tools,
        "domain": domain,
        "fields": fields,
        "limit": limit,
        "order": order,
        "trace": trace,
    }


def _previous_turn_context(history, model):
    """Structured context from the most recent turn on the same model, so
    follow-up questions ('kimlerden?', 'toplam değil mi?') refine the same
    domain instead of the LLM silently re-deriving a different filter."""
    for turn in reversed(history):
        if turn.get("model") == model:
            return {
                "question": turn["question"],
                "domain": turn.get("domain", []),
                "fields": turn.get("fields"),
                "limit": turn.get("limit"),
                "order": turn.get("order"),
                "count": turn.get("count"),
            }
    return None
