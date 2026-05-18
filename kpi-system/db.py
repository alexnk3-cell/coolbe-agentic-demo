import sqlite3
import json
from datetime import datetime, date

DB_PATH = "kpi.db"

# ── 各職稱評估模板 ─────────────────────────────────────────────────────────────
# 格式：(part, dimension, sub_indicator, c1, c2, c3, c4, weight)
# Part 1 各職稱共用相同的子指標結構，僅 criteria 文字依職稱不同

def _p1_items(role):
    """Return Part 1 eval items tailored to the given role."""
    r = role.upper()

    # ── 成果 ──────────────────────────────────────────────────────────────────
    if r == "PM":
        out_items = [
            (1,"成果","季承諾交付達成率",
             "未交付或不可驗收","有產出但延遲或需返工","準時完成可驗收","提前或超規格完成，支援 Demo/上線",25),
            (1,"成果","里程碑準時率",
             "3 項以上 Miss","1-2 項 Miss","全部里程碑準時","提前達成並有額外貢獻",20),
            (1,"成果","可驗收品質（Demo / 文件齊全）",
             "無法驗收","需大幅修改","符合驗收條件","超出驗收標準，客戶主動好評",15),
        ]
    elif r == "PD":
        out_items = [
            (1,"成果","季承諾設計交付達成率",
             "設計未交付或不可用","有產出但需大改","準時交付可用設計稿","提前交付並減少 RD 返工",25),
            (1,"成果","UI/Flow 還原度與可用性",
             "還原度 <60%","還原度 60-80% 需補充","還原度 >80% 可驗收","還原度 >90%，邊界狀態完整",20),
            (1,"成果","支援 Demo / 上線品質",
             "Demo 無法進行","Demo 需多次補圖","Demo 流暢完整","Demo 超出預期，客戶主動詢問",15),
        ]
    elif r == "FE":
        out_items = [
            (1,"成果","功能準時完成率",
             "功能未完成或無法合併","延遲 > 2 天或需大改","準時完成可測試","提前完成並協助 Code Review",25),
            (1,"成果","UI 還原度",
             "<60%","60-79%","80-90%",">90%，動畫/邊界狀態完整",20),
            (1,"成果","Bug 穩定性（P1/P2 數量）",
             "上線後 P1 Bug ≥ 3","P2 Bug ≥ 3 或 P1 Bug 1-2","P1=0，P2 ≤ 2","P1=0，P2=0 無回退",15),
        ]
    elif r == "BE":
        out_items = [
            (1,"成果","API/Service 準時完成率",
             "API 未完成或不可串接","延遲 > 2 天或接口頻繁變更","準時完成可串接並通過測試","提前完成並輸出 API 文件",25),
            (1,"成果","資料正確性與系統穩定性",
             "資料錯誤率 >5%","偶發錯誤需修補","資料正確，錯誤率 <1%","零錯誤，監控告警完整",20),
            (1,"成果","支援 FE 串接 / Demo / 上線",
             "多次阻塞 FE 進度","偶爾阻塞","協作順暢無卡點","主動提前告知接口變更",15),
        ]
    elif r == "RD":
        out_items = [
            (1,"成果","功能/模組準時完成率",
             "功能未完成或無法合併","延遲 > 2 天或需大改","準時完成可測試並通過驗收","提前完成並協助 Code Review / 技術分享",25),
            (1,"成果","程式碼品質與系統穩定性",
             "Bug 率高，需頻繁返工","偶發問題需補救","穩定上線，Bug 率 <1%","零重大 Bug，自動化測試覆蓋率 >80%",20),
            (1,"成果","跨職能協作（PM / PD / QA）",
             "多次造成跨組卡點","偶爾影響協作","協作順暢，準時提供所需介面","主動提前對齊需求，減少往返溝通",15),
        ]
    else:  # APM
        out_items = [
            (1,"成果","任務準時完成率",
             "未完成或遲交超過 3 天","遲交 1-2 天","準時完成","提前完成並主動補充細節",25),
            (1,"成果","文件/報告可用性",
             "文件缺失或不可用","需大幅補充","符合可用標準","文件完整，可直接複用",20),
            (1,"成果","支援 PM 推進效果",
             "多次造成 PM 等待","偶爾需 PM 催促","主動跟進，PM 無需催促","預判 PM 需求並提前準備",15),
        ]

    # ── 過程 ──────────────────────────────────────────────────────────────────
    process_items = [
        (1,"過程","週節奏運作率（週報/更新）",
         "常遲交或缺席","偶爾不準時","週報穩定準時","主動預警+節奏穩定",8),
        (1,"過程","風險提前揭露",
         "揭露時問題已爆發","揭露偏晚（< 2 天）","揭露及時（提前 ≥ 3 天）","超前揭露並附上預案",6),
        (1,"過程","協作效率",
         "常造成跨組卡點","偶爾影響協作","協作流暢無卡點","主動加速跨組推進",6),
    ]

    # ── 沉澱 ──────────────────────────────────────────────────────────────────
    if r in ("FE", "BE", "RD"):
        deposit_items = [
            (1,"沉澱","模板/元件/共用模組產出",
             "無產出","草稿但不可複用","可用元件/模組上線","跨專案可複用，有文件",6),
            (1,"沉澱","可觀測指標（Log/Monitoring）",
             "無","有但不全","有且可追蹤","完整可自動化告警",5),
            (1,"沉澱","知識分享與複用",
             "無","個人記錄","有分享","跨團隊複用，產出教學文件",4),
        ]
    else:
        deposit_items = [
            (1,"沉澱","模板/SOP 產出",
             "無產出","草稿不可用","可用文件/SOP","可複用模板，已推廣給他人使用",6),
            (1,"沉澱","可觀測指標/規則建立",
             "無","有但不全","有且可追蹤","完整可自動化",5),
            (1,"沉澱","知識分享與複用",
             "無","個人記錄","有分享（會議/文件）","跨團隊複用",4),
        ]

    # ── 其他 ──────────────────────────────────────────────────────────────────
    other_items = [
        (1,"其他","會議/出勤紀律",
         "常遲到或無故缺席","偶爾遲到","準時出席所有會議","主動主持或推動會議進展",2),
        (1,"其他","主動性與責任感",
         "被動等待指示","被動但能完成","主動完成並確認品質","超出角色範圍主動推進",3),
    ]

    return out_items + process_items + deposit_items + other_items


def _p2_items(role):
    """Return Part 2 eval items (core value, same structure all roles)."""
    r = role.upper()
    if r == "PD":
        s3 = "設計元件/Flow 模板/SOP 產出"
    elif r == "FE":
        s3 = "元件庫/技術文件/優化方案產出"
    elif r in ("BE", "RD"):
        s3 = "API 文件/共用 Service/架構決策記錄"
    elif r == "APM":
        s3 = "流程文件/SOP/協作規範產出"
    else:
        s3 = "SOP/模板/可複用文件產出"

    return [
        (2,"成果","關鍵里程碑事件 #1",
         None,None,None,None,20),
        (2,"成果","關鍵里程碑事件 #2",
         None,None,None,None,20),
        (2,"過程","問題排解與預測力",
         None,None,None,None,20),
        (2,"沉澱", s3,
         None,None,None,None,15),
        (2,"其他","自我評估：未轉成成果的努力、可優化之處、如果重來",
         None,None,None,None,25),
    ]


def get_eval_template(role):
    """Return full eval item template for a given role."""
    return _p1_items(role) + _p2_items(role)


def populate_eval_template(conn, eval_id, role):
    """Insert default items for an evaluation if none exist."""
    c = conn.cursor()
    existing = c.execute(
        "SELECT COUNT(*) FROM eval_items WHERE evaluation_id=?", (eval_id,)
    ).fetchone()[0]
    if existing > 0:
        return  # already has items

    items = get_eval_template(role)
    c.executemany("""
        INSERT INTO eval_items
          (evaluation_id, part, dimension, sub_indicator,
           criteria_1, criteria_2, criteria_3, criteria_4, weight)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, [(eval_id, *item) for item in items])
    conn.commit()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS jira_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_key TEXT NOT NULL UNIQUE,
            issue_type TEXT,
            summary TEXT,
            status TEXT,
            assignee TEXT,
            reporter TEXT,
            priority TEXT,
            component TEXT,
            epic_link TEXT,
            epic_name TEXT,
            story_points REAL,
            time_spent_seconds INTEGER DEFAULT 0,
            time_estimate_seconds INTEGER DEFAULT 0,
            created_date TEXT,
            updated_date TEXT,
            due_date TEXT,
            resolved_date TEXT,
            labels TEXT,
            description TEXT,
            milestone_id INTEGER REFERENCES milestones(id),
            weekly_record_id INTEGER REFERENCES weekly_records(id),
            imported_at TEXT DEFAULT (datetime('now'))
        );
    """)

    c.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('PM','PD','FE','BE','APM','RD')),
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '⭐',
            category TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER REFERENCES products(id),
            year INTEGER NOT NULL DEFAULT 2026,
            month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
            title TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('planned','scopeout','key')),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','delayed')),
            note TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS weekly_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_date TEXT NOT NULL,
            owner_id INTEGER REFERENCES members(id),
            collaborator_ids TEXT DEFAULT '[]',
            product_id INTEGER REFERENCES products(id),
            work_log TEXT,
            blockers TEXT,
            next_steps TEXT,
            event_name TEXT,
            deliverable_url TEXT,
            stage TEXT CHECK(stage IN ('成果','過程','沉澱','其他')),
            week_end_date TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER REFERENCES members(id),
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL CHECK(quarter BETWEEN 1 AND 4),
            status TEXT DEFAULT 'draft' CHECK(status IN ('draft','submitted','reviewed')),
            part1_total REAL DEFAULT 0,
            part2_total REAL DEFAULT 0,
            final_score REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS eval_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id INTEGER REFERENCES evaluations(id),
            part INTEGER NOT NULL CHECK(part IN (1,2)),
            dimension TEXT NOT NULL,
            sub_indicator TEXT NOT NULL,
            criteria_1 TEXT,
            criteria_2 TEXT,
            criteria_3 TEXT,
            criteria_4 TEXT,
            weight REAL NOT NULL DEFAULT 0,
            self_score INTEGER CHECK(self_score BETWEEN 1 AND 4),
            first_review INTEGER CHECK(first_review BETWEEN 1 AND 4),
            second_review INTEGER CHECK(second_review BETWEEN 1 AND 4),
            evidence TEXT
        );
    """)

    conn.commit()
    _seed(conn)
    conn.close()


def _seed(conn):
    c = conn.cursor()

    if c.execute("SELECT COUNT(*) FROM members").fetchone()[0] > 0:
        return  # already seeded

    # Members
    members = [
        ("Nina", "PM"), ("Chris", "PM"), ("Geer", "PM"), ("Jolin", "APM"),
        ("小帽", "PD"), ("Ricky", "FE"), ("Mark", "BE"),
    ]
    c.executemany("INSERT INTO members (name, role) VALUES (?,?)", members)

    # Products
    products = [
        ("以圖搜圖 (Image Search)", "🔍", "AI-related"),
        ("CoolBe IMPA SaaS", "🏢", "New Business"),
        ("LINE WORKS", "💬", "New Business"),
        ("內部系統", "🔧", "Internal"),
    ]
    c.executemany("INSERT INTO products (name, icon, category) VALUES (?,?,?)", products)

    # Milestones (2026) - based on the Excel data
    milestone_data = [
        # Image Search
        (1, 2026, 1, "✅ Image Search v3.3 上線", "planned", "done"),
        (1, 2026, 1, "✅ KPI 指標定義完成", "planned", "done"),
        (1, 2026, 2, "👑 v4.0 核心功能 Demo", "key", "done"),
        (1, 2026, 2, "✅ 前端 UI 重構完成", "planned", "done"),
        (1, 2026, 3, "✅ API 穩定性達 99.9%", "planned", "done"),
        (1, 2026, 3, "👑 客戶 POC 驗收", "key", "done"),
        (1, 2026, 4, "✅ v4.1 上線", "planned", "done"),
        (1, 2026, 4, "✅ 效能優化 (latency < 500ms)", "planned", "done"),
        (1, 2026, 5, "✅ 多模態搜尋功能開發", "planned", "pending"),
        (1, 2026, 5, "👑 Q2 Demo Day 展示", "key", "pending"),
        (1, 2026, 6, "✅ v4.2 上線", "planned", "pending"),
        (1, 2026, 6, "❌ 語音搜尋 (Scope Out)", "scopeout", "pending"),
        (1, 2026, 7, "✅ 商業客戶擴充 x3", "planned", "pending"),
        (1, 2026, 8, "👑 年中回顧里程碑", "key", "pending"),
        (1, 2026, 9, "✅ v5.0 規劃完成", "planned", "pending"),

        # IMPA SaaS
        (2, 2026, 1, "✅ 需求文件 v1.0", "planned", "done"),
        (2, 2026, 2, "✅ 系統架構設計確認", "planned", "done"),
        (2, 2026, 3, "👑 MVP Demo 內部驗收", "key", "done"),
        (2, 2026, 4, "✅ 第一批客戶導入", "planned", "pending"),
        (2, 2026, 5, "✅ 計費模組上線", "planned", "pending"),
        (2, 2026, 5, "❌ 多語系支援 Q2 (延至 Q3)", "scopeout", "pending"),
        (2, 2026, 6, "👑 正式版 v1.0 上線", "key", "pending"),
        (2, 2026, 7, "✅ SLA 99.5% 達標", "planned", "pending"),
        (2, 2026, 8, "✅ 客戶擴充 5 家", "planned", "pending"),
        (2, 2026, 9, "👑 Series A 商業模型確認", "key", "pending"),

        # LINE WORKS
        (3, 2026, 2, "✅ LINE WORKS API 串接 PoC", "planned", "done"),
        (3, 2026, 3, "✅ 基本訊息功能上線", "planned", "done"),
        (3, 2026, 4, "👑 Beta 版上線", "key", "pending"),
        (3, 2026, 5, "✅ Bot 自動回覆功能", "planned", "pending"),
        (3, 2026, 6, "✅ 第一批企業客戶", "planned", "pending"),
        (3, 2026, 7, "❌ 影片通話整合 (Scope Out)", "scopeout", "pending"),
        (3, 2026, 8, "👑 正式商業化", "key", "pending"),
    ]
    c.executemany(
        "INSERT INTO milestones (product_id, year, month, title, type, status) VALUES (?,?,?,?,?,?)",
        milestone_data
    )

    # Weekly records
    member_ids = {r[0]: i+1 for i, r in enumerate(members)}
    weekly_data = [
        ("2026-05-09", 1, "[1]", 1, "完成多模態搜尋 API 設計文件", "BE 端尚未評估工時", "安排 BE 估點會議", "多模態搜尋 API 設計", "https://docs.google.com/...", "成果"),
        ("2026-05-09", 1, "[1]", 1, "Image Search v4.1 客戶回饋整理", None, "彙整成 Backlog", "客戶回饋整理", None, "過程"),
        ("2026-05-09", 3, "[2]", 2, "IMPA SaaS 計費模組需求確認", "前端開發資源排程衝突", "協調前後端優先序", "計費模組需求 v2", "https://figma.com/...", "成果"),
        ("2026-05-09", 5, "[]", 1, "Image Search v4.1 UI 元件庫更新", None, "本週完成剩餘 3 個元件", "UI 元件庫 v2", "https://figma.com/components", "沉澱"),
        ("2026-05-02", 1, "[1]", 1, "v4.0 Demo Day 準備與彩排", "Demo 環境不穩定", "申請獨立測試環境", "Q2 Demo Day", None, "過程"),
        ("2026-05-02", 3, "[2]", 2, "IMPA SaaS 第一批客戶 onboarding 文件", None, "完成 FAQ 文件", "Onboarding SOP", "https://notion.so/...", "沉澱"),
        ("2026-04-25", 2, "[]", 3, "LINE WORKS Beta 版 QA 測試", "發現 3 個 P1 Bug", "本週修復並回歸測試", "Beta QA Report", None, "過程"),
        ("2026-04-25", 1, "[1]", 1, "Image Search 效能優化 latency 降至 480ms", None, "文件更新並通知客戶", "效能優化成果", None, "成果"),
    ]
    c.executemany(
        """INSERT INTO weekly_records
           (record_date, owner_id, collaborator_ids, product_id, work_log, blockers, next_steps, event_name, deliverable_url, stage)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        weekly_data
    )

    # Evaluations - all 7 members, Q1 2026
    # member_id, role, status, sample scores for Part1 self/first/second (None = blank draft)
    eval_seed = [
        (1, "PM", "submitted"),   # Nina
        (2, "PM", "draft"),       # Chris
        (3, "PM", "draft"),       # Geer
        (4, "APM", "draft"),      # Jolin
        (5, "PD", "draft"),       # 小帽
        (6, "FE", "draft"),       # Ricky
        (7, "BE", "draft"),       # Mark
    ]

    for member_id, role, status in eval_seed:
        conn.execute(
            "INSERT INTO evaluations (member_id, year, quarter, status) VALUES (?,2026,1,?)",
            (member_id, status)
        )
        conn.commit()
        eval_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        populate_eval_template(conn, eval_id, role)

    # Pre-fill Nina's scores as a demo (submitted)
    nina_eval = conn.execute(
        "SELECT id FROM evaluations WHERE member_id=1 AND year=2026 AND quarter=1"
    ).fetchone()["id"]
    scores = [4,3,4, 4,3,3, 3,2,3, 4,4,  # Part1 11 items: self_score
              4,3,3,3,3]                    # Part2 5 items: self_score
    items = conn.execute(
        "SELECT id FROM eval_items WHERE evaluation_id=? ORDER BY part,id", (nina_eval,)
    ).fetchall()
    evidences = [
        "Image Search v4.1 提前 3 天上線，客戶驗收 OK",
        "Q1 里程碑全數達成",
        "Demo 流暢，客戶正面回饋",
        "週報 100% 準時",
        "Demo 環境問題提前 1 週揭露",
        "跨部門對齊順暢",
        "完成 Onboarding SOP v1",
        "KPI 儀表板建立中",
        "月會知識分享 x2",
        "0 次遲到",
        "主動提出多模態方向",
        "Image Search v4.1 提前上線，latency 降至 480ms，客戶 POC 驗收通過",
        "Q2 Demo Day 規劃：多模態搜尋 Demo 準備，協調跨部門資源",
        "Demo 環境問題提前 1 週識別，安排備用方案",
        "完成 Onboarding SOP，可供後續 PM 複用",
        "Q1 主要貢獻在交付面，Q2 目標加強客戶需求洞察能力",
    ]
    for i, (item, score, ev) in enumerate(zip(items, scores, evidences)):
        conn.execute(
            "UPDATE eval_items SET self_score=?, first_review=?, second_review=?, evidence=? WHERE id=?",
            (score, score, max(score-1, 1), ev, item["id"])
        )

    # Pre-fill Geer's self scores (draft)
    geer_eval = conn.execute(
        "SELECT id FROM evaluations WHERE member_id=3 AND year=2026 AND quarter=1"
    ).fetchone()["id"]
    geer_scores = [3,3,3, 4,2,3, 2,2,3, 4,3,  3,None,3,2,3]
    geer_items = conn.execute(
        "SELECT id FROM eval_items WHERE evaluation_id=? ORDER BY part,id", (geer_eval,)
    ).fetchall()
    for item, score in zip(geer_items, geer_scores):
        if score is not None:
            conn.execute("UPDATE eval_items SET self_score=? WHERE id=?", (score, item["id"]))

    conn.commit()


def recalc_scores(conn, eval_id):
    c = conn.cursor()
    items = c.execute("SELECT * FROM eval_items WHERE evaluation_id=?", (eval_id,)).fetchall()

    p1 = [i for i in items if i["part"] == 1]
    p2 = [i for i in items if i["part"] == 2]

    def weighted(items, score_col):
        total_w = sum(i["weight"] for i in items if i[score_col])
        if total_w == 0:
            return 0
        return sum(i["weight"] * i[score_col] for i in items if i[score_col]) / total_w if total_w else 0

    p1_score = weighted(p1, "self_score")
    p2_score = weighted(p2, "self_score")
    final = p1_score * 0.8 + p2_score * 0.2

    c.execute(
        "UPDATE evaluations SET part1_total=?, part2_total=?, final_score=?, updated_at=datetime('now') WHERE id=?",
        (round(p1_score, 2), round(p2_score, 2), round(final, 2), eval_id)
    )
    conn.commit()
