#!/bin/bash
cd "$(dirname "$0")"
echo "🚀 啟動 PDD KPI 系統..."
echo "📊 開啟瀏覽器：http://localhost:5001"
open http://localhost:5001
python3 app.py
