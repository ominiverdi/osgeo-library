#!/bin/bash
cd /home/ominiverdi/github/osgeo-library
LOG="/home/ominiverdi/github/osgeo-library/logs/resume_incomplete.log"
MONITOR_LOG="/home/ominiverdi/github/osgeo-library/logs/batch2_monitor.log"

# Initialize counters if not exist
if [ ! -f /tmp/extract_last_count ]; then
    echo "0" > /tmp/extract_last_count
    date +%s > /tmp/extract_last_time
fi

while true; do
    {
        echo "=== CHECK $(date '+%Y-%m-%d %H:%M') ==="
        echo ""

        # Health checks
        echo "[HEALTH]"
        if dmesg -T 2>/dev/null | tail -20 | grep -qi "wedged\|gpu.*reset\|gpu.*error\|amdgpu.*error"; then
            echo "  GPU: ALERT"
        else
            echo "  GPU: OK"
        fi

        if curl -s --max-time 10 http://localhost:8090/health 2>/dev/null | grep -q ok; then
            echo "  Vision: OK"
        else
            echo "  Vision: FAILED or TIMEOUT"
        fi

        if pgrep -f "extract.*batch2\|resume_incomplete" > /dev/null; then
            echo "  Process: RUNNING"
        else
            echo "  Process: STOPPED"
            echo ""
            echo "=== EXTRACTION ENDED ==="
            break
        fi
        echo ""

        # Rate calculation
        echo "[PROGRESS]"
        total_now=0
        for doc in nas_ghg_2022 unep_methane_2023 foss4g_2017 gfoi_mgd_2016 gnss_overview_2022 gnss_overview_2023 wildfire_california_2020 copernicus_cimr_mrd jacie_2022 foss4g_2015; do
            count=$(ls db/data/$doc/pages/*.json 2>/dev/null | wc -l)
            total_now=$((total_now + count))
        done

        last_count=$(cat /tmp/extract_last_count 2>/dev/null || echo 0)
        last_time=$(cat /tmp/extract_last_time 2>/dev/null || date +%s)
        now_time=$(date +%s)
        elapsed=$(( (now_time - last_time) / 60 ))
        pages_done=$((total_now - last_count))
        
        if [ "$elapsed" -gt 0 ]; then
            rate=$(echo "scale=2; $pages_done / $elapsed" | bc 2>/dev/null || echo "?")
        else
            rate="--"
        fi
        
        echo "$total_now" > /tmp/extract_last_count
        echo "$now_time" > /tmp/extract_last_time
        echo "  +$pages_done pages in ${elapsed}min (${rate} pages/min)"
        echo ""

        # Per-document status
        echo "[DOCUMENTS]"
        for doc in nas_ghg_2022 unep_methane_2023 foss4g_2017 gfoi_mgd_2016 gnss_overview_2022 gnss_overview_2023 wildfire_california_2020 copernicus_cimr_mrd jacie_2022 foss4g_2015; do
            count=$(ls db/data/$doc/pages/*.json 2>/dev/null | wc -l)
            total=$(python3 -c "import json; print(json.load(open('db/data/$doc/document.json')).get('total_pages', '?'))" 2>/dev/null || echo "?")
            if [ "$total" != "?" ] && [ "$count" -lt "$total" ]; then
                pct=$((count * 100 / total))
                bar=$(printf '%*s' $((pct/5)) '' | tr ' ' '#')
                printf "  %-28s %3d/%3d [%-20s] %d%%\n" "$doc" "$count" "$total" "$bar" "$pct"
            elif [ "$total" != "?" ]; then
                echo "  $doc: DONE ($count)"
            fi
        done
        echo ""

        # Recent log activity
        echo "[LAST ACTIVITY]"
        LAST_PROGRESS=$(grep -oP '\[\d+/\d+\]' "$LOG" 2>/dev/null | tail -1)
        echo "  Log progress: $LAST_PROGRESS"
        tail -5 "$LOG" 2>/dev/null | grep -E "Page|completed|error" | sed 's/^/  /'
        echo ""
        echo "---"
        echo ""
    } >> "$MONITOR_LOG"

    sleep 1800
done
