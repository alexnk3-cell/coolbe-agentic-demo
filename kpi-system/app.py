import os
import io
import csv
import json
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from db import init_db, get_db, recalc_scores, populate_eval_template

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

os.chdir(os.path.dirname(os.path.abspath(__file__)))
init_db()


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ─── Static / SPA ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")


# ─── Members ───────────────────────────────────────────────────────────────────

@app.route("/api/members")
def list_members():
    db = get_db()
    return jsonify(rows_to_list(db.execute("SELECT * FROM members ORDER BY role, name").fetchall()))


@app.route("/api/members", methods=["POST"])
def create_member():
    data = request.json
    db = get_db()
    db.execute("INSERT INTO members (name, role) VALUES (?,?)", (data["name"], data["role"]))
    db.commit()
    return jsonify({"ok": True})


# ─── Products ──────────────────────────────────────────────────────────────────

@app.route("/api/products")
def list_products():
    db = get_db()
    return jsonify(rows_to_list(db.execute("SELECT * FROM products ORDER BY id").fetchall()))


@app.route("/api/products", methods=["POST"])
def create_product():
    data = request.json
    db = get_db()
    db.execute(
        "INSERT INTO products (name, icon, category) VALUES (?,?,?)",
        (data["name"], data.get("icon", "⭐"), data.get("category", ""))
    )
    db.commit()
    return jsonify({"ok": True})


# ─── Milestones ────────────────────────────────────────────────────────────────

@app.route("/api/milestones")
def list_milestones():
    year = request.args.get("year", 2026, type=int)
    db = get_db()
    rows = db.execute("""
        SELECT m.*, p.name as product_name, p.icon as product_icon
        FROM milestones m JOIN products p ON m.product_id = p.id
        WHERE m.year = ?
        ORDER BY m.product_id, m.month
    """, (year,)).fetchall()
    return jsonify(rows_to_list(rows))


@app.route("/api/milestones", methods=["POST"])
def create_milestone():
    data = request.json
    db = get_db()
    db.execute(
        "INSERT INTO milestones (product_id, year, month, title, type, status, note) VALUES (?,?,?,?,?,?,?)",
        (data["product_id"], data.get("year", 2026), data["month"],
         data["title"], data["type"], data.get("status", "pending"), data.get("note"))
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/milestones/<int:mid>", methods=["PUT"])
def update_milestone(mid):
    data = request.json
    db = get_db()
    fields = []
    vals = []
    for f in ("title", "type", "status", "note"):
        if f in data:
            fields.append(f"{f}=?")
            vals.append(data[f])
    if fields:
        vals.append(mid)
        db.execute(f"UPDATE milestones SET {', '.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify({"ok": True})


@app.route("/api/milestones/<int:mid>", methods=["DELETE"])
def delete_milestone(mid):
    db = get_db()
    db.execute("DELETE FROM milestones WHERE id=?", (mid,))
    db.commit()
    return jsonify({"ok": True})


# ─── Weekly Records ────────────────────────────────────────────────────────────

@app.route("/api/weekly")
def list_weekly():
    db = get_db()
    limit = request.args.get("limit", 50, type=int)
    owner_id = request.args.get("owner_id", type=int)
    product_id = request.args.get("product_id", type=int)

    query = """
        SELECT w.*, m.name as owner_name, m.role as owner_role,
               p.name as product_name, p.icon as product_icon
        FROM weekly_records w
        LEFT JOIN members m ON w.owner_id = m.id
        LEFT JOIN products p ON w.product_id = p.id
        WHERE 1=1
    """
    params = []
    if owner_id:
        query += " AND w.owner_id=?"
        params.append(owner_id)
    if product_id:
        query += " AND w.product_id=?"
        params.append(product_id)
    query += " ORDER BY w.record_date DESC LIMIT ?"
    params.append(limit)

    return jsonify(rows_to_list(db.execute(query, params).fetchall()))


@app.route("/api/weekly", methods=["POST"])
def create_weekly():
    data = request.json
    db = get_db()
    db.execute("""
        INSERT INTO weekly_records
        (record_date, owner_id, collaborator_ids, product_id, work_log, blockers, next_steps, event_name, deliverable_url, stage)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        data["record_date"], data.get("owner_id"), json.dumps(data.get("collaborator_ids", [])),
        data.get("product_id"), data.get("work_log"), data.get("blockers"),
        data.get("next_steps"), data.get("event_name"), data.get("deliverable_url"), data.get("stage")
    ))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/weekly/<int:wid>", methods=["PUT"])
def update_weekly(wid):
    data = request.json
    db = get_db()
    fields = []
    vals = []
    for f in ("record_date", "owner_id", "product_id", "work_log", "blockers",
              "next_steps", "event_name", "deliverable_url", "stage"):
        if f in data:
            fields.append(f"{f}=?")
            vals.append(data[f])
    if fields:
        vals.append(wid)
        db.execute(f"UPDATE weekly_records SET {', '.join(fields)} WHERE id=?", vals)
        db.commit()
    return jsonify({"ok": True})


@app.route("/api/weekly/<int:wid>", methods=["DELETE"])
def delete_weekly(wid):
    db = get_db()
    db.execute("DELETE FROM weekly_records WHERE id=?", (wid,))
    db.commit()
    return jsonify({"ok": True})


# ─── Evaluations ───────────────────────────────────────────────────────────────

@app.route("/api/evaluations")
def list_evaluations():
    db = get_db()
    year = request.args.get("year", 2026, type=int)
    quarter = request.args.get("quarter", type=int)
    member_id = request.args.get("member_id", type=int)

    query = """
        SELECT e.*, m.name as member_name, m.role as member_role,
               m.primary_product_id, m.exclude_from_perf
        FROM evaluations e JOIN members m ON e.member_id = m.id
        WHERE e.year=? AND m.exclude_from_perf=0
    """
    params = [year]
    if quarter:
        query += " AND e.quarter=?"
        params.append(quarter)
    if member_id:
        query += " AND e.member_id=?"
        params.append(member_id)
    query += " ORDER BY e.quarter, m.name"

    rows = rows_to_list(db.execute(query, params).fetchall())
    # recalc scores on fetch
    for row in rows:
        recalc_scores(db, row["id"])
    # re-fetch after recalc
    rows = rows_to_list(db.execute(query, params).fetchall())
    return jsonify(rows)


@app.route("/api/evaluations/<int:eid>")
def get_evaluation(eid):
    db = get_db()
    recalc_scores(db, eid)
    row = row_to_dict(db.execute("""
        SELECT e.*, m.name as member_name, m.role as member_role
        FROM evaluations e JOIN members m ON e.member_id = m.id
        WHERE e.id=?
    """, (eid,)).fetchone())
    if not row:
        return jsonify({"error": "not found"}), 404

    items = rows_to_list(db.execute(
        "SELECT * FROM eval_items WHERE evaluation_id=? ORDER BY part, id", (eid,)
    ).fetchall())
    row["items"] = items
    return jsonify(row)


@app.route("/api/evaluations", methods=["POST"])
def create_evaluation():
    data = request.json
    db = get_db()
    # Check if already exists
    existing = db.execute(
        "SELECT id FROM evaluations WHERE member_id=? AND year=? AND quarter=?",
        (data["member_id"], data["year"], data["quarter"])
    ).fetchone()
    if existing:
        return jsonify({"error": "已存在此評估", "id": existing["id"]}), 409

    db.execute(
        "INSERT INTO evaluations (member_id, year, quarter, status) VALUES (?,?,?,?)",
        (data["member_id"], data["year"], data["quarter"], data.get("status", "draft"))
    )
    db.commit()
    eval_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Auto-populate role-specific template items
    member = db.execute("SELECT role FROM members WHERE id=?", (data["member_id"],)).fetchone()
    if member:
        populate_eval_template(db, eval_id, member["role"])

    return jsonify({"ok": True, "id": eval_id})


@app.route("/api/evaluations/<int:eid>/items", methods=["POST"])
def upsert_eval_items(eid):
    items = request.json
    db = get_db()
    for item in items:
        if item.get("id"):
            db.execute("""
                UPDATE eval_items SET
                  self_score=?, first_review=?, second_review=?, evidence=?
                WHERE id=? AND evaluation_id=?
            """, (
                item.get("self_score"), item.get("first_review"),
                item.get("second_review"), item.get("evidence"),
                item["id"], eid
            ))
        else:
            db.execute("""
                INSERT INTO eval_items
                (evaluation_id, part, dimension, sub_indicator, criteria_1, criteria_2, criteria_3, criteria_4,
                 weight, self_score, first_review, second_review, evidence)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                eid, item["part"], item["dimension"], item["sub_indicator"],
                item.get("criteria_1"), item.get("criteria_2"),
                item.get("criteria_3"), item.get("criteria_4"),
                item.get("weight", 0), item.get("self_score"),
                item.get("first_review"), item.get("second_review"), item.get("evidence")
            ))
    recalc_scores(db, eid)
    return jsonify({"ok": True})


@app.route("/api/evaluations/<int:eid>/status", methods=["PUT"])
def update_eval_status(eid):
    data = request.json
    db = get_db()
    db.execute("UPDATE evaluations SET status=?, updated_at=datetime('now') WHERE id=?",
               (data["status"], eid))
    db.commit()
    return jsonify({"ok": True})


# ─── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/api/dashboard")
def dashboard():
    db = get_db()

    # Milestone completion stats
    ms_stats = rows_to_list(db.execute("""
        SELECT p.name as product_name, p.icon,
               COUNT(*) as total,
               SUM(CASE WHEN m.status='done' THEN 1 ELSE 0 END) as done,
               SUM(CASE WHEN m.type='scopeout' THEN 1 ELSE 0 END) as scopeout,
               SUM(CASE WHEN m.type='key' THEN 1 ELSE 0 END) as key_total,
               SUM(CASE WHEN m.type='key' AND m.status='done' THEN 1 ELSE 0 END) as key_done
        FROM milestones m JOIN products p ON m.product_id = p.id
        WHERE m.year=2026 AND m.type != 'scopeout'
        GROUP BY p.id
    """).fetchall())

    # Recent blockers
    blockers = rows_to_list(db.execute("""
        SELECT w.record_date, w.event_name, w.blockers, m.name as owner_name, p.name as product_name
        FROM weekly_records w
        LEFT JOIN members m ON w.owner_id = m.id
        LEFT JOIN products p ON w.product_id = p.id
        WHERE w.blockers IS NOT NULL AND w.blockers != ''
        ORDER BY w.record_date DESC LIMIT 5
    """).fetchall())

    # Performance grouped by product line
    # Use explicit primary_product_id for grouping (excludes MING)
    all_products = rows_to_list(db.execute(
        "SELECT * FROM products WHERE id IN (SELECT DISTINCT primary_product_id FROM members WHERE primary_product_id IS NOT NULL) ORDER BY id"
    ).fetchall())

    all_evals = rows_to_list(db.execute("""
        SELECT e.member_id, m.name, m.role, e.final_score, e.status, e.quarter, e.id as eval_id,
               e.part1_total, e.part2_total, m.primary_product_id
        FROM evaluations e
        JOIN members m ON e.member_id = m.id
        WHERE e.year=2026 AND m.exclude_from_perf=0
    """).fetchall())

    perf_by_product = []
    assigned_member_ids = set()

    for p in all_products:
        members_in_product = [ev for ev in all_evals if ev["primary_product_id"] == p["id"]]
        if members_in_product:
            scores = [m["final_score"] for m in members_in_product if m["final_score"]]
            perf_by_product.append({
                "product_id": p["id"],
                "product_name": p["name"],
                "product_icon": p["icon"],
                "avg_score": round(sum(scores)/len(scores), 2) if scores else None,
                "members": members_in_product,
            })
            assigned_member_ids.update(m["member_id"] for m in members_in_product)

    # Cross-product members (primary_product_id IS NULL, not excluded)
    cross = [ev for ev in all_evals if ev["primary_product_id"] is None and ev["member_id"] not in assigned_member_ids]
    if cross:
        scores = [m["final_score"] for m in cross if m["final_score"]]
        perf_by_product.append({
            "product_id": None,
            "product_name": "跨產品線",
            "product_icon": "🟡",
            "avg_score": round(sum(scores)/len(scores), 2) if scores else None,
            "members": cross,
        })

    # Weekly activity count by week
    weekly_trend = rows_to_list(db.execute("""
        SELECT strftime('%Y-W%W', record_date) as week,
               COUNT(*) as count
        FROM weekly_records
        GROUP BY week
        ORDER BY week DESC LIMIT 8
    """).fetchall())

    # Upcoming milestones (next 2 months)
    from datetime import date
    current_month = date.today().month
    upcoming = rows_to_list(db.execute("""
        SELECT m.*, p.name as product_name, p.icon as product_icon
        FROM milestones m JOIN products p ON m.product_id = p.id
        WHERE m.year=2026 AND m.month BETWEEN ? AND ? AND m.status='pending'
        ORDER BY m.month, m.type DESC
    """, (current_month, current_month + 2)).fetchall())

    return jsonify({
        "milestone_stats": ms_stats,
        "recent_blockers": blockers,
        "performance_by_product": perf_by_product,
        "weekly_trend": weekly_trend,
        "upcoming_milestones": upcoming,
    })


# ─── Jira Import ───────────────────────────────────────────────────────────────

# Jira CSV 欄位名稱對應（支援英文版與中文版匯出）
JIRA_FIELD_MAP = {
    "Issue Key":        "issue_key",
    "Issue id":         "issue_key",      # fallback
    "Issue Type":       "issue_type",
    "Summary":          "summary",
    "Status":           "status",
    "Assignee":         "assignee",
    "Reporter":         "reporter",
    "Priority":         "priority",
    "Component/s":      "component",
    "Components":       "component",
    "Epic Link":        "epic_link",
    "Epic Name":        "epic_name",
    "Story Points":     "story_points",
    "Story point estimate": "story_points",
    "Time Spent":       "time_spent_raw",
    "Remaining Estimate": "time_estimate_raw",
    "Original Estimate": "time_estimate_raw",
    "Created":          "created_date",
    "Updated":          "updated_date",
    "Due Date":         "due_date",
    "Resolved":         "resolved_date",
    "Labels":           "labels",
    "Description":      "description",
}


def _parse_jira_time(val):
    """Convert Jira time string like '3h 30m' or '1d 2h' to seconds."""
    if not val or val.strip() in ("", "None"):
        return 0
    total = 0
    import re
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([wdhm])", val.lower()):
        n = float(num)
        if unit == "w":   total += int(n * 5 * 8 * 3600)
        elif unit == "d": total += int(n * 8 * 3600)
        elif unit == "h": total += int(n * 3600)
        elif unit == "m": total += int(n * 60)
    return total


def _auto_link_milestone(db, issue):
    """Match Epic Name (or summary for Epic type) to an existing milestone title (fuzzy)."""
    import re
    candidate = issue.get("epic_name") or (
        issue.get("summary") if issue.get("issue_type") == "Epic" else None
    )
    if not candidate:
        return None
    rows = db.execute("SELECT id, title FROM milestones").fetchall()
    # Strip emojis and symbols for clean comparison
    def clean(s):
        return re.sub(r"[^\w一-鿿]", " ", s).lower().strip()
    needle = clean(candidate)
    best_id, best_len = None, 0
    for r in rows:
        hay = clean(r["title"])
        # Check overlap by longest common word sequence
        words = [w for w in needle.split() if len(w) > 1]
        matches = sum(1 for w in words if w in hay)
        if matches >= 2 and matches > best_len:
            best_id, best_len = r["id"], matches
    return best_id


@app.route("/api/jira/import", methods=["POST"])
def jira_import():
    if "file" not in request.files:
        return jsonify({"error": "請上傳 CSV 檔案"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".csv"):
        return jsonify({"error": "請上傳 .csv 格式"}), 400

    content = f.read().decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []

    # Build column map for this file's actual headers
    col_map = {}
    for h in headers:
        stripped = h.strip()
        if stripped in JIRA_FIELD_MAP:
            col_map[stripped] = JIRA_FIELD_MAP[stripped]

    if "issue_key" not in col_map.values():
        return jsonify({"error": f"找不到 Issue Key 欄位，目前欄位：{headers}"}), 400

    db = get_db()
    inserted = updated = skipped = 0

    for row in reader:
        issue = {}
        for h, field in col_map.items():
            issue[field] = (row.get(h) or "").strip() or None

        if not issue.get("issue_key"):
            skipped += 1
            continue

        # Parse time fields
        issue["time_spent_seconds"]    = _parse_jira_time(issue.pop("time_spent_raw", None))
        issue["time_estimate_seconds"] = _parse_jira_time(issue.pop("time_estimate_raw", None))

        # Parse story points
        try:
            issue["story_points"] = float(issue["story_points"]) if issue.get("story_points") else None
        except ValueError:
            issue["story_points"] = None

        # Auto-link to milestone
        issue["milestone_id"] = _auto_link_milestone(db, issue)

        existing = db.execute(
            "SELECT id FROM jira_issues WHERE issue_key=?", (issue["issue_key"],)
        ).fetchone()

        fields = ["issue_key","issue_type","summary","status","assignee","reporter",
                  "priority","component","epic_link","epic_name","story_points",
                  "time_spent_seconds","time_estimate_seconds","created_date",
                  "updated_date","due_date","resolved_date","labels","description","milestone_id"]

        vals = [issue.get(f) for f in fields]

        if existing:
            set_clause = ", ".join(f"{f}=?" for f in fields[1:])  # skip issue_key
            db.execute(
                f"UPDATE jira_issues SET {set_clause}, imported_at=datetime('now') WHERE issue_key=?",
                vals[1:] + [issue["issue_key"]]
            )
            updated += 1
        else:
            placeholders = ", ".join("?" * len(fields))
            db.execute(
                f"INSERT INTO jira_issues ({', '.join(fields)}) VALUES ({placeholders})",
                vals
            )
            inserted += 1

    db.commit()

    summary = db.execute("""
        SELECT issue_type, COUNT(*) as cnt,
               SUM(CASE WHEN status IN ('Done','完成','Closed') THEN 1 ELSE 0 END) as done_cnt
        FROM jira_issues GROUP BY issue_type
    """).fetchall()

    return jsonify({
        "ok": True,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "summary": rows_to_list(summary),
    })


@app.route("/api/jira/issues")
def list_jira_issues():
    db = get_db()
    issue_type = request.args.get("type")
    milestone_id = request.args.get("milestone_id", type=int)
    status = request.args.get("status")
    limit = request.args.get("limit", 100, type=int)

    query = "SELECT j.*, m.title as milestone_title FROM jira_issues j LEFT JOIN milestones m ON j.milestone_id=m.id WHERE 1=1"
    params = []
    if issue_type:
        query += " AND j.issue_type=?"
        params.append(issue_type)
    if milestone_id:
        query += " AND j.milestone_id=?"
        params.append(milestone_id)
    if status:
        query += " AND j.status=?"
        params.append(status)
    query += " ORDER BY j.issue_key LIMIT ?"
    params.append(limit)

    return jsonify(rows_to_list(db.execute(query, params).fetchall()))


@app.route("/api/jira/issues/<issue_key>/link", methods=["PUT"])
def link_jira_issue(issue_key):
    data = request.json
    db = get_db()
    db.execute(
        "UPDATE jira_issues SET milestone_id=?, weekly_record_id=? WHERE issue_key=?",
        (data.get("milestone_id"), data.get("weekly_record_id"), issue_key)
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/jira/stats")
def jira_stats():
    db = get_db()

    by_type = rows_to_list(db.execute("""
        SELECT issue_type,
               COUNT(*) as total,
               SUM(CASE WHEN status IN ('Done','完成','Closed','DONE') THEN 1 ELSE 0 END) as done,
               SUM(CASE WHEN status IN ('In Progress','進行中','IN PROGRESS') THEN 1 ELSE 0 END) as in_progress,
               SUM(CASE WHEN status IN ('Blocked','阻塞','BLOCKED') THEN 1 ELSE 0 END) as blocked,
               ROUND(SUM(time_spent_seconds)/3600.0, 1) as total_hours
        FROM jira_issues GROUP BY issue_type
    """).fetchall())

    by_component = rows_to_list(db.execute("""
        SELECT COALESCE(component,'未分類') as component,
               COUNT(*) as total,
               SUM(CASE WHEN status IN ('Done','完成','Closed','DONE') THEN 1 ELSE 0 END) as done,
               ROUND(SUM(time_spent_seconds)/3600.0, 1) as hours
        FROM jira_issues WHERE issue_type != 'Bug'
        GROUP BY component ORDER BY total DESC
    """).fetchall())

    epics_with_progress = rows_to_list(db.execute("""
        SELECT e.issue_key, e.summary, e.status, e.due_date, e.assignee,
               COUNT(s.id) as story_count,
               SUM(CASE WHEN s.status IN ('Done','完成','Closed','DONE') THEN 1 ELSE 0 END) as story_done,
               ROUND(SUM(s.time_spent_seconds)/3600.0,1) as hours_spent,
               e.milestone_id
        FROM jira_issues e
        LEFT JOIN jira_issues s ON s.epic_link = e.issue_key
        WHERE e.issue_type = 'Epic'
        GROUP BY e.id ORDER BY e.issue_key
    """).fetchall())

    blocked = rows_to_list(db.execute("""
        SELECT issue_key, summary, issue_type, assignee, component, updated_date
        FROM jira_issues
        WHERE status IN ('Blocked','阻塞','BLOCKED')
        ORDER BY updated_date
    """).fetchall())

    total_issues = db.execute("SELECT COUNT(*) FROM jira_issues").fetchone()[0]

    return jsonify({
        "total_issues": total_issues,
        "by_type": by_type,
        "by_component": by_component,
        "epics_with_progress": epics_with_progress,
        "blocked": blocked,
    })


@app.route("/api/jira/issues/<issue_key>", methods=["DELETE"])
def delete_jira_issue(issue_key):
    db = get_db()
    db.execute("DELETE FROM jira_issues WHERE issue_key=?", (issue_key,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/jira/clear", methods=["DELETE"])
def clear_jira_issues():
    db = get_db()
    db.execute("DELETE FROM jira_issues")
    db.commit()
    return jsonify({"ok": True})


# ─── Monthly Report ────────────────────────────────────────────────────────────

@app.route("/api/monthly-report")
def monthly_report():
    year  = request.args.get("year",  2026, type=int)
    month = request.args.get("month",    5, type=int)
    db = get_db()

    # Weekly records for the month
    records = rows_to_list(db.execute("""
        SELECT w.*, m.name as owner_name, m.role as owner_role,
               p.name as product_name, p.icon as product_icon, p.id as pid
        FROM weekly_records w
        LEFT JOIN members m ON w.owner_id = m.id
        LEFT JOIN products p ON w.product_id = p.id
        WHERE strftime('%Y-%m', w.record_date) = ?
        ORDER BY w.product_id, w.stage, w.owner_id
    """, (f"{year}-{month:02d}",)).fetchall())

    # Milestones for the month
    milestones = rows_to_list(db.execute("""
        SELECT m.*, p.name as product_name, p.icon as product_icon
        FROM milestones m JOIN products p ON m.product_id = p.id
        WHERE m.year=? AND m.month=?
        ORDER BY m.product_id, m.type DESC
    """, (year, month)).fetchall())

    # Summary counts
    summary = {"achievements": 0, "processes": 0, "deposits": 0, "other_count": 0}
    for r in records:
        s = r.get("stage") or "其他"
        if s == "成果":   summary["achievements"] += 1
        elif s == "過程": summary["processes"]    += 1
        elif s == "沉澱": summary["deposits"]     += 1
        else:             summary["other_count"]  += 1
    summary["main_products"] = 2

    # Group records by product (exclude 其他/NULL)
    OTHER_IDS = {4}  # 內部系統
    grouped = {}
    other_records = []
    for r in records:
        pid  = r.get("pid") or r.get("product_id")
        pname = r.get("product_name") or "其他"
        if pid in OTHER_IDS or not pid or pname == "其他":
            other_records.append(r)
        else:
            if pname not in grouped:
                grouped[pname] = {"product_name": pname, "icon": r.get("product_icon",""), "records": []}
            grouped[pname]["records"].append(r)

    # Monthly focus axes (static content matching the reference site)
    axes = [
        {"product": "LINE WORKS",
         "focus": "從內部導入推進到可販售的 SaaS 產品基礎",
         "icon": "💬"},
        {"product": "IMPA SaaS / Image Search",
         "focus": "把平台整理到能 Demo、能交接、能對外說明",
         "icon": "🏢"},
    ]

    return jsonify({
        "year":    year,
        "month":   month,
        "summary": summary,
        "axes":    axes,
        "milestones": milestones,
        "records_by_product": list(grouped.values()),
        "other_records": other_records,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
