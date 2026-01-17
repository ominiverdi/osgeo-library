#!/bin/bash
# Resume incomplete batch2 extractions
# Run with: nohup ./scripts/resume_incomplete.sh > logs/resume_incomplete.log 2>&1 &
#
# Updated: 2026-01-12
# - Split into priority docs and optional/books (skipped for now)
# - Optional docs tracked in SKIPPED_DOCS for future processing

set -e
cd /home/ominiverdi/github/osgeo-library
source .venv/bin/activate

# ============================================
# PRIORITY DOCUMENTS - Process these now
# ============================================
declare -A DOCS=(
    ["copernicus_cimr_mrd"]="Copernicus_CIMR_MRD_v5_2023.pdf"
    ["foss4g_2015"]="FOSS4G_2015_Proceedings_v2.pdf"
    ["foss4g_2017"]="FOSS4G_2017_Full_Proceedings.pdf"
    ["gfoi_mgd_2016"]="forestAU_GFOI-MGD_2016.pdf"
    ["gnss_overview_2022"]="gnss_ovr_2022.pdf"
    ["gnss_overview_2023"]="gnss_ovr_2023.pdf"
    ["jacie_2022"]="satJACIE_2022.pdf"
    ["nas_ghg_2022"]="climateGHG_NAS_2022.pdf"
    ["unep_methane_2023"]="unep_eye-on-methane_2023.pdf"
    ["wildfire_california_2020"]="Wildfire-in-California_ccst_2020.pdf"
)

# ============================================
# SKIPPED DOCUMENTS - Large books / optional
# Listed in osgeo7-gallery:/home/shared/2twopass_list.txt under "optional or other"
# To process later, move entries from SKIPPED_DOCS to DOCS
# ============================================
declare -A SKIPPED_DOCS=(
    # PROJ reference manual - 965 pages, largest document
    ["proj_manual_96"]="proj-org-en-9.6.pdf"
    
    # California Climate Indicators report - 665 pages, listed as optional
    ["ca_ClimateIndicators-4th_OEHH_2022"]="ca_ClimateIndicators-4th_OEHH_2022.pdf"
    
    # Geomatics textbook - 455 pages
    ["geomatics_book_2019"]="geombook2019.01.11.pdf"
    
    # World Bank water report - 267 pages, listed as optional
    ["water_worldbank_2016"]="water_WorldBank_2016.pdf"
)

echo "=========================================="
echo "Resuming incomplete extractions"
echo "Started: $(date)"
echo "=========================================="

# Show what we're skipping
echo ""
echo "SKIPPED (optional/books - ${#SKIPPED_DOCS[@]} documents):"
for doc in "${!SKIPPED_DOCS[@]}"; do
    pdf="${SKIPPED_DOCS[$doc]}"
    output_dir="db/data/$doc"
    current=$(ls "$output_dir/pages/"*.json 2>/dev/null | wc -l)
    total=$(python3 -c "import fitz; print(fitz.open('pdfs/batch2/$pdf').page_count)" 2>/dev/null || echo "?")
    echo "  - $doc: $current/$total pages"
done

echo ""
echo "PROCESSING (${#DOCS[@]} documents):"

for doc in "${!DOCS[@]}"; do
    pdf="${DOCS[$doc]}"
    pdf_path="pdfs/batch2/$pdf"
    output_dir="db/data/$doc"
    
    # Count current progress
    current=$(ls "$output_dir/pages/"*.json 2>/dev/null | wc -l)
    total=$(python3 -c "import fitz; print(fitz.open('$pdf_path').page_count)")
    remaining=$((total - current))
    
    if [ "$remaining" -gt 0 ]; then
        echo ""
        echo "[$doc] $current/$total pages done, $remaining remaining"
        echo "  PDF: $pdf"
        echo "  Starting: $(date)"
        
        python -m doclibrary.cli extract "$pdf_path" \
            --pages 1-999 \
            --output-dir "$output_dir" \
            --skip-existing
        
        echo "  Finished: $(date)"
    else
        echo "  - $doc: complete ($current pages)"
    fi
done

echo ""
echo "=========================================="
echo "Priority extractions complete"
echo "Finished: $(date)"
echo ""
echo "To process skipped documents later, edit this script"
echo "and move entries from SKIPPED_DOCS to DOCS."
echo "=========================================="
