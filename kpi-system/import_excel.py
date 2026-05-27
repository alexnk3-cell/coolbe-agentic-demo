"""
從 Excel 匯入真實資料到 kpi.db
執行：python3 import_excel.py
"""
import sqlite3
import sys
import os

EXCEL_PATH = os.path.expanduser(
    "~/Desktop/03_KPI 與里程碑/[Weekly]2026 產品發展部_推進事件記錄(新版).xlsx"
)
DB_PATH = os.path.join(os.path.dirname(__file__), "kpi.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def main():
    try:
        import openpyxl
    except ImportError:
        print("請先安裝 openpyxl: pip3 install openpyxl")
        sys.exit(1)

    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    conn = get_db()
    c = conn.cursor()

    # ── 1. 確保 小帽 存在（PD），Jessica 改為 APM ──────────────────────────
    # 先查現有成員
    members_db = {r["name"]: dict(r) for r in c.execute("SELECT * FROM members").fetchall()}

    # Jessica 在 DB 是 PD，參考資料她是 APM，更新
    if "Jessica" in members_db and members_db["Jessica"]["role"] == "PD":
        c.execute("UPDATE members SET role='APM' WHERE name='Jessica'")
        print("✓ 更新 Jessica 角色：PD → APM")

    # 若 小帽 不存在，新增
    if "小帽" not in members_db:
        c.execute("INSERT INTO members (name, role) VALUES (?,?)", ("小帽", "PD"))
        conn.commit()
        print("✓ 新增成員：小帽 (PD)")

    # 重新載入成員 map
    member_map = {r["name"]: r["id"] for r in c.execute("SELECT id, name FROM members").fetchall()}

    # ── 2. 產品 ID mapping ──────────────────────────────────────────────────
    product_rows = c.execute("SELECT id, name FROM products").fetchall()
    product_map = {}
    for p in product_rows:
        n = p["name"]
        pid = p["id"]
        if "Image Search" in n or "以圖搜圖" in n:
            product_map["Image Search"] = pid
            product_map["以圖搜圖"] = pid
        elif "IMPA SaaS" in n or "LINE OA SaaS" in n:
            product_map["IMPA SaaS"] = pid
        elif "LINE WORKS" in n:
            product_map["LINE WORKS"] = pid

    # ── 3. 清除現有 5 月週記錄，改用 Excel 真實資料 ─────────────────────────
    # 先刪除 2026-05 的週記錄
    c.execute("DELETE FROM weekly_records WHERE record_date LIKE '2026-05%'")
    deleted = c.execute("SELECT changes()").fetchone()[0]
    print(f"✓ 清除現有 2026-05 週記錄 {deleted} 筆")

    stage_map = {
        "過程（推動）": "過程",
        "成果（交付）": "成果",
        "沉澱（知識）": "沉澱",
        "過程": "過程", "成果": "成果", "沉澱": "沉澱",
    }

    inserted_weekly = 0

    def insert_weekly(date_val, work_log, owner_name, product_key, blockers, next_steps,
                      deliverable_url, stage_raw, event_name=None, collab_name=None):
        if not work_log or not date_val:
            return
        owner_id = member_map.get(owner_name)
        product_id = product_map.get(product_key) if product_key else None
        stage = stage_map.get(stage_raw or "", "其他")
        date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
        collab_ids = []
        if collab_name and collab_name in member_map:
            collab_ids = [member_map[collab_name]]
        import json
        c.execute("""
            INSERT INTO weekly_records
              (record_date, owner_id, collaborator_ids, product_id,
               work_log, blockers, next_steps, event_name, deliverable_url, stage)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            date_str, owner_id, json.dumps(collab_ids), product_id,
            work_log, blockers or None, next_steps or None,
            event_name or None, deliverable_url or None, stage
        ))

    # PM 記錄-Nina&Chris
    ws_nina = wb["PM 記錄-Nina&Chris"]
    rows_nina = list(ws_nina.iter_rows(min_row=3, values_only=True))
    for row in rows_nina:
        date_val, work_log, owner, collab, product, blockers, next_steps, _, event_name, deliverable, stage = (
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10]
        )
        if not date_val or not work_log:
            continue
        # 只取 2026-05
        if hasattr(date_val, "month") and date_val.month == 5 and date_val.year == 2026:
            # 取 deliverable 第一個 URL
            url = str(deliverable).split("\n")[0].strip() if deliverable else None
            if url and not url.startswith("http"):
                url = None
            insert_weekly(date_val, work_log, owner, product, blockers, next_steps,
                          url, stage, event_name, collab)
            inserted_weekly += 1

    # PM 記錄-Geer&Jolin
    ws_geer = wb["PM 記錄-Geer&Jolin"]
    for row in ws_geer.iter_rows(min_row=3, values_only=True):
        date_val, work_log, owner, collab, product, blockers, next_steps, _, event_name, deliverable, stage = (
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], row[10]
        )
        if not date_val or not work_log:
            continue
        if hasattr(date_val, "month") and date_val.month == 5 and date_val.year == 2026:
            url = str(deliverable).split("\n")[0].strip() if deliverable else None
            if url and not url.startswith("http"):
                url = None
            # Geer&Jolin 中沒有 collab 的方向：owner 可能是 Geer 或 Jolin
            insert_weekly(date_val, work_log, owner, product, blockers, next_steps,
                          url, stage, event_name, collab)
            inserted_weekly += 1

    # PD 記錄-小帽
    ws_pd = wb["PD 記錄-小帽"]
    for row in ws_pd.iter_rows(min_row=3, values_only=True):
        date_val, work_log, product, blockers, next_steps, event_name, deliverable, stage = (
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
        )
        if not date_val or not work_log:
            continue
        if hasattr(date_val, "month") and date_val.month == 5 and date_val.year == 2026:
            url = str(deliverable).strip() if deliverable else None
            if url and not url.startswith("http"):
                url = None
            insert_weekly(date_val, work_log, "小帽", product, blockers, next_steps,
                          url, stage, event_name)
            inserted_weekly += 1

    print(f"✓ 匯入週記錄 {inserted_weekly} 筆")

    # ── 4. 更新 5 月里程碑（清舊補新）─────────────────────────────────────
    c.execute("DELETE FROM milestones WHERE year=2026 AND month=5")
    print(f"✓ 清除 2026-05 里程碑")

    # 依參考資料和 Excel 里程碑檢視
    # product_id: Image Search=1, IMPA SaaS=2, LINE WORKS=3
    pid_img    = product_map.get("Image Search", 1)
    pid_impa   = product_map.get("IMPA SaaS", 2)
    pid_lws    = product_map.get("LINE WORKS", 3)

    milestones_may = [
        # Image Search - Nina 主責
        (pid_img,  2026, 5, "Image Search v1.0 上線穩定",       "key",     "pending"),
        (pid_img,  2026, 5, "Image Search v1.0 定價確認",        "planned", "delayed"),

        # IMPA SaaS - Nina/Chris 主責
        (pid_impa, 2026, 5, "CoolBe IMPA SaaS 平台 v1.0（白牌基礎）", "key",  "pending"),
        (pid_impa, 2026, 5, "IMPA SaaS 平台 v1.0 定價確認",      "planned", "delayed"),
        (pid_impa, 2026, 5, "IMPA SaaS 平台 v1.1 優化",          "planned", "done"),

        # LINE WORKS - Geer 主責
        (pid_lws,  2026, 5, "LINE WORKS SaaS 平台 Beta 規劃",    "key",     "pending"),
        (pid_lws,  2026, 5, "LINE WORKS 打卡 Bot MVP",            "planned", "pending"),
        (pid_lws,  2026, 5, "LINE WORKS 對內導入（第一階段）",    "planned", "done"),
        (pid_lws,  2026, 5, "LINE WORKS 對外販售基礎（Sales Kit v1）", "planned", "pending"),
        (pid_lws,  2026, 5, "LINE WORKS 官方網站規劃",            "planned", "pending"),
        (pid_lws,  2026, 5, "LINE WORKS 串接 OA Bot MVP v1.0 規劃完成", "planned", "pending"),
    ]

    c.executemany(
        "INSERT INTO milestones (product_id, year, month, title, type, status) VALUES (?,?,?,?,?,?)",
        milestones_may
    )
    print(f"✓ 新增 2026-05 里程碑 {len(milestones_may)} 筆")

    conn.commit()
    conn.close()
    print("\n✅ 匯入完成！")


if __name__ == "__main__":
    main()
