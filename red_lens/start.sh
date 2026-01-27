#!/bin/bash
# RedLens Quick Start Script

echo "=================================================="
echo "  RedLens - 小红书摄影博主分析工具"
echo "=================================================="
echo ""

cd "$(dirname "$0")/.."

# Check if database exists
if [ ! -f "red_lens/red_lens.db" ]; then
    echo "📦 Initializing database..."
    python red_lens/db.py
    echo ""
fi

# Show statistics
echo "📊 Current Statistics:"
python -c "
import sys
sys.path.insert(0, '.')
from red_lens.db import BloggerDB, NoteDB, init_db
init_db()
total = len(BloggerDB.get_all_bloggers())
pending = BloggerDB.count_by_status('pending')
scraped = BloggerDB.count_by_status('scraped')
print(f'  • Total bloggers: {total}')
print(f'  • Pending: {pending}')
print(f'  • Scraped: {scraped}')
"
echo ""

# Launch Streamlit
echo "🚀 Launching Streamlit dashboard..."
echo "   Open browser at: http://localhost:8501"
echo ""
streamlit run red_lens/app.py
