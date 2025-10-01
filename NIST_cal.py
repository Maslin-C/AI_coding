from flask import Flask, request, render_template, redirect, url_for, make_response, jsonify
from datetime import datetime
from jinja2 import DictLoader
import csv
import io
import os
import sys

app = Flask(__name__)

# -------------------------------------------------
# NIST AI RMF-lite model (GOVERN / MAP / MEASURE / MANAGE)
# -------------------------------------------------
AI_RMF_FUNCTIONS = {
    "GOVERN": [
        ("นโยบาย/ความรับผิดชอบ (Accountability) ชัดเจนและได้รับอนุมัติ", "govern_policy"),
        ("การกำหนด Risk Appetite/Threshold สำหรับระบบ AI", "govern_appetite"),
        ("การกำกับดูแลผู้ให้บริการภายนอก/Third-Party AI", "govern_third_party"),
    ],
    "MAP": [
        ("ระบุบริบทและกรณีใช้งาน (Use Case) อย่างชัดเจน", "map_context"),
        ("แหล่งที่มาข้อมูล/Provenance และคุณภาพข้อมูล", "map_data"),
        ("การจำแนกผลกระทบต่อผู้มีส่วนได้ส่วนเสีย", "map_stakeholders"),
    ],
    "MEASURE": [
        ("การประเมินความเอนเอียง/ความเป็นธรรม (Bias/Fairness)", "measure_fairness"),
        ("ความทนทาน/ความปลอดภัยเชิงเทคนิค (Robustness/Security)", "measure_robust"),
        ("ประสิทธิภาพ/ความถูกต้อง และความเป็นส่วนตัว (Perf/Privacy)", "measure_perf_privacy"),
    ],
    "MANAGE": [
        ("Monitoring/Drift/Logging/Alerting ทำอย่างต่อเนื่อง", "manage_monitoring"),
        ("กระบวนการเปลี่ยนแปลง/เวอร์ชัน/อนุมัติ (Change Mgmt)", "manage_change"),
        ("การกำกับดูแลโดยมนุษย์/Incident Response/ปิดความเสี่ยง", "manage_oversight"),
    ],
}

IMPACT_DIMENSIONS = [
    ("ผลกระทบต่อความปลอดภัยของบุคคล (Safety)", "impact_safety"),
    ("ผลกระทบด้านกฎหมาย/คอมพลายแอนซ์ (Legal/Compliance)", "impact_legal"),
    ("ผลกระทบด้านความเป็นส่วนตัว (Privacy)", "impact_privacy"),
    ("ผลกระทบทางการเงิน/ชื่อเสียงองค์กร (Financial/Reputation)", "impact_finrep"),
    ("ผลกระทบต่อการปฏิบัติการ/ธุรกิจ (Operational)", "impact_ops"),
]

# --------------------- helpers ---------------------

def scale_1_to_5_to_0_1(v: int) -> float:
    v = max(1, min(5, int(v)))
    return (v - 1) / 4.0


def classify_risk(score: float) -> str:
    # scale 1..25 (higher = riskier)
    if score >= 18:
        return "รุนแรงมาก (Severe)"
    elif score >= 12:
        return "สูง (High)"
    elif score >= 7:
        return "ปานกลาง (Moderate)"
    else:
        return "ต่ำ (Low)"


def build_recommendations(fn_scores, control_avg):
    recs = []
    for fn, score in fn_scores.items():
        if score < 3:
            if fn == "GOVERN":
                recs.append("ยกระดับการกำกับดูแล: ตั้งคณะทำงาน/เจ้าของความเสี่ยง AI, อัปเดตนโยบาย และกำหนด Risk Appetite ให้ชัดเจน")
            elif fn == "MAP":
                recs.append("เติมเต็มการทำความเข้าใจบริบทและข้อมูล: บันทึก Use Case, ทำ Data Provenance และประเมินผู้มีส่วนได้ส่วนเสีย")
            elif fn == "MEASURE":
                recs.append("เสริมการทดสอบ/วัดผล: ทำ Bias & Fairness test, Robustness/Security test และ Privacy assessment อย่างเป็นระบบ")
            elif fn == "MANAGE":
                recs.append("เพิ่มความต่อเนื่องในการควบคุม: สร้าง Monitoring/Alert, จัดการเวอร์ชัน และวาง Incident Response playbook")
    if control_avg < 3:
        recs.append("โดยรวมควรเร่งสร้างควบคุมพื้นฐานให้ถึงระดับ 3/5 ก่อนนำระบบไปใช้ในวงกว้าง")
    return recs

# --------------------- templates ---------------------
BASE_HTML = """
<!doctype html>
<html lang=\"th\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>AI Risk Calculator (NIST AI RMF)</title>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
  <link href=\"https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@300;400;600;700&display=swap\" rel=\"stylesheet\">
  <style>
    body { font-family: 'Noto Sans Thai', sans-serif; margin:0; background:#0f172a; color:#e2e8f0 }
    a { color:#93c5fd; text-decoration:none }
    .container { max-width:1000px; margin:0 auto; padding:24px }
    .card { background:#111827; border:1px solid #1f2937; border-radius:16px; padding:20px; margin-bottom:16px; box-shadow:0 10px 24px rgba(0,0,0,.25) }
    .title { font-size:26px; font-weight:700; margin:8px 0 16px }
    .subtitle { font-size:18px; opacity:.85; margin-bottom:12px }
    .grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr)); gap:14px }
    .field { display:flex; flex-direction:column; gap:6px; background:#0b1220; border:1px solid #1f2a44; padding:12px; border-radius:12px }
    label { font-weight:600; font-size:14px }
    input[type=range]{ width:100% }
    .hint { font-size:12px; color:#8da2c0 }
    .btn { display:inline-block; padding:12px 16px; background:#2563eb; color:#fff; border-radius:12px; border:none; cursor:pointer; font-weight:700 }
    .btn.secondary { background:#334155 }
    .row { display:flex; gap:10px; flex-wrap:wrap }
    .badge { padding:6px 10px; border-radius:999px; border:1px solid #334155; background:#0b1220; font-size:12px }
    .score { font-size:36px; font-weight:800 }
    .muted { color:#94a3b8 }
    .footer { margin-top:24px; font-size:12px; color:#94a3b8 }
    .hr { height:1px; background:#1f2937; margin:14px 0 }
    .pill { padding:6px 10px; border-radius:999px; background:#1f2937; border:1px solid #334155; font-weight:700 }
    .matrix { display:grid; grid-template-columns:repeat(5,1fr); gap:4px }
    .cell { padding:14px 8px; border-radius:8px; text-align:center; border:1px solid #1f2937 }
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"card\">
      <div class=\"title\">AI Risk Calculator — ตามกรอบ NIST AI RMF</div>
      <div class=\"subtitle\">ประเมินความเสี่ยงการใช้งาน AI ภายในองค์กรแบบย่อ (Single-File Flask)</div>
      <div class=\"row\">
        <span class=\"badge\">GOVERN</span>
        <span class=\"badge\">MAP</span>
        <span class=\"badge\">MEASURE</span>
        <span class=\"badge\">MANAGE</span>
      </div>
    </div>
    {% block content %}{% endblock %}
    <div class=\"footer\">เวอร์ชันตัวอย่างเพื่อการศึกษา — อัปเดต {{now}}</div>
  </div>
</body>
</html>
"""

INDEX_HTML = """
{% extends 'base.html' %}
{% block content %}
<form method=\"post\" action=\"{{ url_for('calculate') }}\">
  <div class=\"card\">
    <div class=\"title\">1) ระดับโอกาสเกิดเหตุ (Likelihood) และผลกระทบ (Impact)</div>
    <div class=\"grid\">
      <div class=\"field\">
        <label>โอกาสเกิดเหตุ (1=น้อยมาก, 5=มากมาก)</label>
        <input type=\"range\" min=\"1\" max=\"5\" value=\"3\" name=\"likelihood\" oninput=\"l_out.innerText=this.value\">
        <div class=\"hint\">ค่าปัจจุบัน: <b id=\"l_out\">3</b></div>
      </div>
      {% for label, name in impacts %}
      <div class=\"field\">
        <label>{{label}}</label>
        <input type=\"range\" min=\"1\" max=\"5\" value=\"3\" name=\"{{name}}\" oninput=\"{{name}}_out.innerText=this.value\">
        <div class=\"hint\">ค่าปัจจุบัน: <b id=\"{{name}}_out\">3</b></div>
      </div>
      {% endfor %}
    </div>
  </div>

  <div class=\"card\">
    <div class=\"title\">2) ระดับความพร้อม/ควบคุม ตามฟังก์ชัน AI RMF (1=เริ่มต้น, 5=ดีมาก)</div>
    <div class=\"grid\">
      {% for fn, qs in functions.items() %}
        {% for label, name in qs %}
        <div class=\"field\">
          <label>{{fn}} — {{label}}</label>
          <input type=\"range\" min=\"1\" max=\"5\" value=\"3\" name=\"{{name}}\" oninput=\"{{name}}_out.innerText=this.value\">
          <div class=\"hint\">ค่าปัจจุบัน: <b id=\"{{name}}_out\">3</b></div>
        </div>
        {% endfor %}
      {% endfor %}
    </div>
  </div>

  <div class=\"card\">
    <div class=\"title\">3) ข้อมูลระบบ (System Card แบบย่อ)</div>
    <div class=\"grid\">
      <div class=\"field\"><label>ชื่อระบบ/โครงการ</label><input type=\"text\" name=\"system_name\" placeholder=\"เช่น: Chatbot ฝ่ายบริการลูกค้า\"></div>
      <div class=\"field\"><label>คำอธิบายสั้น ๆ</label><input type=\"text\" name=\"system_desc\" placeholder=\"เช่น: ระบบช่วยตอบแชทลูกค้าด้วย LLM\"></div>
      <div class=\"field\"><label>หน่วยงานเจ้าของระบบ</label><input type=\"text\" name=\"owner\" placeholder=\"เช่น: ฝ่ายดิจิทัล\"></div>
      <div class=\"field\"><label>เวอร์ชัน/วันประเมิน</label><input type=\"text\" name=\"version\" placeholder=\"เช่น: v1.0 / {{today}}\"></div>
    </div>
  </div>

  <div class=\"card\">
    <button class=\"btn\" type=\"submit\">คำนวณความเสี่ยง</button>
    <a class=\"btn secondary\" href=\"{{ url_for('index') }}\">ล้างค่า</a>
  </div>
</form>
{% endblock %}
"""

RESULT_HTML = """
{% extends 'base.html' %}
{% block content %}
<div class=\"card\">
  <div class=\"title\">สรุปผล — {{ system_name or 'โครงการไม่มีชื่อ' }}</div>
  <div class=\"subtitle\">Inherent Risk = Likelihood × Impact (เฉลี่ยหลายมิติ) → Residual Risk = Inherent × (1 − 0.7×Mitigation)</div>
  <div class=\"grid\">
    <div class=\"field\"><div class=\"muted\">Likelihood</div><div class=\"score\">{{ likelihood }}</div></div>
    <div class=\"field\"><div class=\"muted\">Impact (เฉลี่ย)</div><div class=\"score\">{{ impact_avg }}</div></div>
    <div class=\"field\"><div class=\"muted\">Inherent Risk</div><div class=\"score\">{{ inherent_risk }}</div><div class=\"hint\">ระดับ: {{ inherent_class }}</div></div>
    <div class=\"field\"><div class=\"muted\">Mitigation Factor (0-1)</div><div class=\"score\">{{ mitigation_factor }}</div><div class=\"hint\">คำนวณจากค่า GOVERN/MAP/MEASURE/MANAGE</div></div>
    <div class=\"field\"><div class=\"muted\">Residual Risk</div><div class=\"score\">{{ residual_risk }}</div><div class=\"hint\">ระดับ: {{ residual_class }}</div></div>
  </div>
  <div class=\"hr\"></div>
  <div class=\"row\">
    <span class=\"pill\">GOVERN: {{ fn_scores['GOVERN']|round(2) }}/5</span>
    <span class=\"pill\">MAP: {{ fn_scores['MAP']|round(2) }}/5</span>
    <span class=\"pill\">MEASURE: {{ fn_scores['MEASURE']|round(2) }}/5</span>
    <span class=\"pill\">MANAGE: {{ fn_scores['MANAGE']|round(2) }}/5</span>
  </div>
</div>

<div class=\"card\">
  <div class=\"title\">เมทริกซ์ความเสี่ยง (Risk Matrix)</div>
  <div class=\"subtitle\">ตำแหน่ง: Likelihood = {{likelihood}}, Impact เฉลี่ย = {{impact_avg}}</div>
  <div class=\"matrix\">{% for i in range(5,0,-1) %}{% for j in range(1,6) %}{% set score = i * j %}{% set bg = '#14532d' if score<=6 else ('#78350f' if score<=12 else ('#7f1d1d' if score<=18 else '#450a0a')) %}<div class=\"cell\" style=\"background: {{bg}};\">{{score}}</div>{% endfor %}{% endfor %}</div>
</div>

<div class=\"card\">
  <div class=\"title\">คำแนะนำ (Prioritized Recommendations)</div>
  {% if recs %}<ul>{% for r in recs %}<li>{{ r }}</li>{% endfor %}</ul>{% else %}<div class=\"muted\">การควบคุมอยู่ในระดับดีแล้ว รักษาการทดสอบและการเฝ้าติดตามอย่างต่อเนื่อง</div>{% endif %}
</div>

<div class=\"card\">
  <div class=\"title\">ดาวน์โหลดผลลัพธ์</div>
  <div class=\"row\"><a class=\"btn\" href=\"{{ url_for('download_csv') }}\">CSV</a><a class=\"btn secondary\" href=\"{{ url_for('download_json') }}\">JSON</a></div>
</div>

<div class=\"card\">
  <div class=\"title\">System Card (ย่อ)</div>
  <div class=\"grid\">
    <div class=\"field\"><label>ชื่อระบบ</label><div>{{ system_name or '-' }}</div></div>
    <div class=\"field\"><label>คำอธิบาย</label><div>{{ system_desc or '-' }}</div></div>
    <div class=\"field\"><label>หน่วยงาน</label><div>{{ owner or '-' }}</div></div>
    <div class=\"field\"><label>เวอร์ชัน/วันประเมิน</label><div>{{ version or '-' }}</div></div>
  </div>
</div>

<div class=\"card\"><a class=\"btn\" href=\"{{ url_for('index') }}\">ประเมินใหม่</a></div>
{% endblock %}
"""

# Register templates in-memory so Jinja `{% extends %}` works with names
app.jinja_loader = DictLoader({
    'base.html': BASE_HTML,
    'index.html': INDEX_HTML,
    'result.html': RESULT_HTML,
})

# --------------------- routes ---------------------
LAST_RESULT = {}

@app.route("/")
def index():
    return render_template(
        'index.html',
        functions=AI_RMF_FUNCTIONS,
        impacts=IMPACT_DIMENSIONS,
        today=datetime.now().strftime("%Y-%m-%d"),
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


@app.route("/calculate", methods=["POST"])
def calculate():
    form = request.form

    likelihood = int(form.get("likelihood", 3))
    impact_vals = [int(form.get(name, 3)) for _, name in IMPACT_DIMENSIONS]
    impact_avg = round(sum(impact_vals) / len(impact_vals), 2)

    inherent_risk = round(likelihood * impact_avg, 2)  # 1-25
    inherent_class = classify_risk(inherent_risk)

    fn_scores = {}
    all_ctrl_scores = []
    for fn, qs in AI_RMF_FUNCTIONS.items():
        vals = [int(form.get(name, 3)) for _, name in qs]
        fn_scores[fn] = round(sum(vals) / len(vals), 2)
        all_ctrl_scores.extend(vals)
    control_avg = round(sum(all_ctrl_scores) / len(all_ctrl_scores), 2)

    # Mitigation factor (0..1)
    weights = {"GOVERN": 0.25, "MAP": 0.2, "MEASURE": 0.3, "MANAGE": 0.25}
    mitigation_factor = 0.0
    for fn, sc in fn_scores.items():
        mitigation_factor += weights[fn] * scale_1_to_5_to_0_1(sc)
    mitigation_factor = round(mitigation_factor, 2)

    residual_risk = inherent_risk * (1 - 0.7 * mitigation_factor)
    residual_risk = round(max(1.0, residual_risk), 2)
    residual_class = classify_risk(residual_risk)

    recs = build_recommendations(fn_scores, control_avg)

    global LAST_RESULT
    LAST_RESULT = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "system": {
            "name": form.get("system_name", ""),
            "desc": form.get("system_desc", ""),
            "owner": form.get("owner", ""),
            "version": form.get("version", ""),
        },
        "likelihood": likelihood,
        "impacts": {name: int(form.get(name, 3)) for _, name in IMPACT_DIMENSIONS},
        "impact_avg": impact_avg,
        "inherent_risk": inherent_risk,
        "inherent_class": inherent_class,
        "functions": fn_scores,
        "mitigation_factor": mitigation_factor,
        "residual_risk": residual_risk,
        "residual_class": residual_class,
        "recommendations": recs,
    }

    return render_template(
        'result.html',
        likelihood=likelihood,
        impact_avg=impact_avg,
        inherent_risk=inherent_risk,
        inherent_class=inherent_class,
        fn_scores=fn_scores,
        mitigation_factor=mitigation_factor,
        residual_risk=residual_risk,
        residual_class=residual_class,
        recs=recs,
        system_name=LAST_RESULT["system"]["name"],
        system_desc=LAST_RESULT["system"]["desc"],
        owner=LAST_RESULT["system"]["owner"],
        version=LAST_RESULT["system"]["version"],
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


@app.route("/download.csv")
def download_csv():
    if not LAST_RESULT:
        return redirect(url_for('index'))
    buf = io.StringIO()
    writer = csv.writer(buf)
    r = LAST_RESULT
    writer.writerow(["timestamp", r["timestamp"]])
    writer.writerow(["system_name", r["system"]["name"]])
    writer.writerow(["system_desc", r["system"]["desc"]])
    writer.writerow(["owner", r["system"]["owner"]])
    writer.writerow(["version", r["system"]["version"]])
    writer.writerow([])
    writer.writerow(["likelihood", r["likelihood"]])
    writer.writerow(["impact_avg", r["impact_avg"]])
    writer.writerow(["inherent_risk", r["inherent_risk"]])
    writer.writerow(["inherent_class", r["inherent_class"]])
    writer.writerow(["mitigation_factor", r["mitigation_factor"]])
    writer.writerow(["residual_risk", r["residual_risk"]])
    writer.writerow(["residual_class", r["residual_class"]])
    writer.writerow([])
    writer.writerow(["FUNCTION", "SCORE"])
    for fn, sc in r["functions"].items():
        writer.writerow([fn, sc])
    writer.writerow([])
    writer.writerow(["IMPACT_DIMENSION", "SCORE"])
    for k, v in r["impacts"].items():
        writer.writerow([k, v])
    writer.writerow([])
    writer.writerow(["RECOMMENDATIONS"])    
    for rec in r["recommendations"]:
        writer.writerow([rec])
    out = make_response(buf.getvalue())
    out.headers["Content-Disposition"] = f"attachment; filename=ai_risk_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    out.headers["Content-Type"] = "text/csv"
    return out


@app.route("/download.json")
def download_json():
    if not LAST_RESULT:
        return redirect(url_for('index'))
    import json
    out = make_response(json.dumps(LAST_RESULT, ensure_ascii=False, indent=2))
    out.headers["Content-Disposition"] = f"attachment; filename=ai_risk_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.headers["Content-Type"] = "application/json; charset=utf-8"
    return out


@app.route("/healthz")
def healthz():
    return "ok", 200


@app.route("/_selftest")
def selftest():
    """ชุดทดสอบ: ฟังก์ชันหลัก + เส้นทางเว็บ (ไม่ต้องสตาร์ทเซิร์ฟเวอร์จริง)"""
    results = []
    all_passed = True

    def check(name, fn):
        nonlocal all_passed
        try:
            fn()
            results.append({"name": name, "result": "pass"})
        except AssertionError as e:
            results.append({"name": name, "result": "fail", "error": str(e)})
            all_passed = False

    # --- Logic tests ---
    def test_scale():
        assert scale_1_to_5_to_0_1(1) == 0.0
        assert scale_1_to_5_to_0_1(3) == 0.5
        assert scale_1_to_5_to_0_1(5) == 1.0
    check("scale_1_to_5_to_0_1", test_scale)

    def test_classify_boundaries():
        assert classify_risk(6.99) == "ต่ำ (Low)"
        assert classify_risk(7) == "ปานกลาง (Moderate)"
        assert classify_risk(11.99) == "ปานกลาง (Moderate)"
        assert classify_risk(12) == "สูง (High)"
        assert classify_risk(17.99) == "สูง (High)"
        assert classify_risk(18) == "รุนแรงมาก (Severe)"
    check("classify_risk_boundaries", test_classify_boundaries)

    def test_risk_math_baseline():
        likelihood = 3
        impact_avg = 3
        inherent = round(likelihood * impact_avg, 2)
        assert inherent == 9
        fn_scores = {"GOVERN": 3, "MAP": 3, "MEASURE": 3, "MANAGE": 3}
        weights = {"GOVERN": 0.25, "MAP": 0.2, "MEASURE": 0.3, "MANAGE": 0.25}
        mitigation = 0
        for fn, sc in fn_scores.items():
            mitigation += weights[fn] * scale_1_to_5_to_0_1(sc)
        mitigation = round(mitigation, 2)
        assert mitigation == 0.5
        residual = round(inherent * (1 - 0.7 * mitigation), 2)
        assert residual == 5.85
        assert classify_risk(residual) == "ต่ำ (Low)"
    check("risk_math_baseline", test_risk_math_baseline)

    def test_risk_math_extremes():
        inherent = 25
        mitigation = 0.0
        residual = round(inherent * (1 - 0.7 * mitigation), 2)
        assert residual == 25
        assert classify_risk(residual) == "รุนแรงมาก (Severe)"
        mitigation = 1.0
        residual = round(inherent * (1 - 0.7 * mitigation), 2)
        assert residual == 7.5
        assert classify_risk(residual) == "ปานกลาง (Moderate)"
    check("risk_math_extremes", test_risk_math_extremes)

    def test_recommendations_rules():
        recs = build_recommendations({"GOVERN": 2.5, "MAP": 3.5, "MEASURE": 2.0, "MANAGE": 4.0}, control_avg=3.0)
        assert any("กำกับดูแล" in r for r in recs)
        assert any("ทดสอบ/วัดผล" in r or "Bias" in r for r in recs)
    check("recommendations_rules", test_recommendations_rules)

    # --- Route smoke tests (NEW) ---
    def test_routes():
        with app.test_client() as c:
            rv = c.get("/"); assert rv.status_code == 200
            rv = c.get("/healthz"); assert rv.status_code == 200 and rv.data == b"ok"
            rv = c.get("/download.csv"); assert rv.status_code in (301, 302)
            rv = c.get("/download.json"); assert rv.status_code in (301, 302)
            # simulate a calculated result then download
            global LAST_RESULT
            LAST_RESULT = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "system": {"name": "T", "desc": "D", "owner": "O", "version": "V"},
                "likelihood": 3,
                "impacts": {name: 3 for _, name in IMPACT_DIMENSIONS},
                "impact_avg": 3.0,
                "inherent_risk": 9.0,
                "inherent_class": classify_risk(9.0),
                "functions": {"GOVERN": 3, "MAP": 3, "MEASURE": 3, "MANAGE": 3},
                "mitigation_factor": 0.5,
                "residual_risk": 5.85,
                "residual_class": classify_risk(5.85),
                "recommendations": [],
            }
            rv = c.get("/download.csv"); assert rv.status_code == 200 and rv.data.startswith(b"timestamp,")
            rv = c.get("/download.json"); assert rv.status_code == 200 and b"\"likelihood\"" in rv.data
    check("route_smoke_tests", test_routes)

    # --- New: end-to-end calculate flow ---
    def test_calculate_flow():
        with app.test_client() as c:
            form = {"likelihood": "4"}
            # add some explicit inputs (others default to 3)
            for _, name in IMPACT_DIMENSIONS:
                form[name] = "3"
            for _, qs in AI_RMF_FUNCTIONS.items():
                for _, name in qs:
                    form[name] = "3"
            rv = c.post("/calculate", data=form)
            assert rv.status_code == 200
            assert b"Residual Risk" in rv.data
            # after calculate, downloads should work
            rv = c.get("/download.csv"); assert rv.status_code == 200
            rv = c.get("/download.json"); assert rv.status_code == 200
            assert LAST_RESULT.get("likelihood") == 4
    check("calculate_flow", test_calculate_flow)

    status = 200 if all_passed else 500
    return jsonify({"passed": all_passed, "results": results}), status


# -------------------------------
# Running — hardened for sandbox
#   * host 127.0.0.1 (avoid 0.0.0.0 blocking)
#   * use_reloader=False (no fork)
#   * threaded=False (avoid ThreadedWSGIServer -> SystemExit)
#   * Catch SystemExit/OSError and write to stderr safely
# -------------------------------

def _safe_debug_default() -> bool:
    want = os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")
    if not want:
        return False
    try:
        import _multiprocessing  # noqa: F401
        return True
    except Exception:
        return False


def _run_server():
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    debug_mode = _safe_debug_default()
    app.run(host=host, port=port, debug=debug_mode, use_reloader=False, threaded=False)


def _log_err(msg: str) -> None:
    try:
        sys.stderr.write(msg + "\n")
    except Exception:
        try:
            print(msg)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        _run_server()
    except (SystemExit, OSError) as e:
        _log_err(f"[WARN] Server could not start in this environment: {e}")
        _log_err("Tip: Deploy under a WSGI server (gunicorn/uwsgi) or run locally.")
        # Do not re-raise; allow the module to be imported (tests and routes still usable)
