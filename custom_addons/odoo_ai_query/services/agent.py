import logging
import os

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
    },
    "product.product": {
        "label": "Ürünler",
        "fields": ["name", "list_price", "default_code", "type", "categ_id"],
    },
    "stock.quant": {
        "label": "Stok Durumu",
        "fields": ["product_id", "quantity", "location_id"],
    },
}

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


INTENT_PROMPT = """Sen bir Odoo iş verisi sorgu asistanısın. Kullanıcının sorusunu analiz et
ve hangi Odoo modelinin sorgulanması gerektiğine karar ver.

Kullanılabilir modeller:
{models}

Son konuşma geçmişi (model, soru):
{recent_turns}

VARSAYILAN KURAL: Kullanıcının sorusu kısa/belirsizse (örn. "kimlerden?", "fiyatları?",
"ücretleri?", "ne zaman?", "toplamı?") EN SON TURDAKİ MODELİ TEKRAR SEÇ. Bu tür sorular
neredeyse her zaman önceki sonuç kümesinin bir detayını sorar — "fiyatlar" bir sipariş
bağlamında sipariş tutarı, ürün bağlamında ürün fiyatı anlamına gelebilir; hangi bağlamda
olduğumuzu SON TURDAN anla, kelimenin kendisinden değil.

Yalnızca kullanıcı YENİ bir konu için AÇIK bir isim/kelime kullanırsa model değiştir
(örn. önceki tur sipariş iken kullanıcı "ürünler" veya "stok" kelimesini açıkça kullanırsa).

Yalnızca şu JSON formatında yanıt ver:
{{"model": "<model.name>", "reasoning": "<kısa açıklama>"}}

Eğer soru bu modellerin hiçbiriyle ilgili değilse model alanını null yap.
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

SUMMARY_PROMPT = """Sen bir işletme verisi asistanısın. Aşağıdaki ham veriyi kullanıcının
sorusuna doğal, kısa ve net bir Türkçe yanıt haline getir. Sayısal özetler
(toplam, ortalama, en yüksek/düşük) varsa SADECE aşağıdaki ham veriden hesapla.

ÖNEMLİ: Yalnızca aşağıda verilen ham veriyi kullan. Listede olmayan bir kayıttan
(örn. uydurma sipariş numarası) asla bahsetme. "Bulunan kayıt sayısı" değeri her
zaman doğrudur — önceki konuşmadaki bir sayıyla çelişse bile bu sayıyı kullan ve
gerekirse farkı kullanıcıya açıkla (örn. filtre değişti, farklı bir alt küme sorgulandı).

Kullanıcının orijinal sorusu: {question}
Sorgulanan model: {model}
Bulunan kayıt sayısı: {count}
Ham veri (JSON): {data}

Yalnızca doğal dilde yanıt ver, JSON değil, markdown formatlaması kullanma.
"""


def run_agent(env, question, history=None):
    """4-step agent pipeline: intent -> plan -> execute -> summarize.

    Returns dict: {answer, model, count, steps} where `steps` records what
    the agent decided at each stage (useful for demo/debugging transparency).
    """
    llm = get_llm_client()
    history = history or []
    trace = []

    # Step 1: intent classification
    models_desc = "\n".join(f"- {m}: {info['label']}" for m, info in ALLOWED_MODELS.items())
    recent_turns = "\n".join(
        f"- model={h.get('model')}, soru={h['question']!r}" for h in history[-3:]
    ) or "(yok)"
    intent = llm.complete_json(
        INTENT_PROMPT.format(models=models_desc, recent_turns=recent_turns),
        question,
    )
    trace.append({"step": "intent", "output": intent})

    model = intent.get("model")
    if not model or model not in ALLOWED_MODELS:
        return {
            "answer": "Bu soruyu mevcut verilerle yanıtlayamıyorum. Satış siparişleri, "
            "ürünler veya stok durumu hakkında sorabilirsiniz.",
            "model": None,
            "count": 0,
            "steps": trace,
        }

    # Step 2: query planning
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
        # Mechanically reuse the prior turn's exact query — never trust the LLM
        # to faithfully reconstruct "no change" from a text description, since
        # it tends to silently invent a different (wrong) filter instead.
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

    # Step 3: execute — read-only, under the calling user's own ACL/record rules
    records = env[model].search_read(domain, fields, limit=limit, order=order)
    trace.append({"step": "execute", "output": {"count": len(records)}})

    # Step 4: summarize
    # Data sent to the LLM is capped at MAX_ROWS (same as the query limit) so
    # the visible row count always matches `count` — a mismatch here previously
    # caused the model to narrate a wrong total taken from the truncated list.
    answer = llm.complete_text(
        "Sen yardımsever bir işletme veri asistanısın.",
        SUMMARY_PROMPT.format(
            question=question,
            model=ALLOWED_MODELS[model]["label"],
            count=len(records),
            data=records[:MAX_ROWS],
        ),
    )
    trace.append({"step": "summarize", "output": {"answer": answer}})

    return {
        "answer": answer,
        "model": model,
        "count": len(records),
        "domain": domain,
        "fields": fields,
        "limit": limit,
        "order": order,
        "steps": trace,
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
