#!/bin/bash
# Extract all remaining batch2 documents
# Run with: nohup ./scripts/extract_remaining.sh > logs/batch2/master.log 2>&1 &

cd /home/ominiverdi/github/osgeo-library
source .venv/bin/activate

LOG_DIR="logs/batch2"
mkdir -p "$LOG_DIR"

# Function to extract a document
extract_doc() {
    local name="$1"
    local pdf="$2"
    local pages="$3"
    
    local data_dir="db/data/$name"
    local current_pages=$(ls "$data_dir/pages/"*.json 2>/dev/null | wc -l)
    
    if [ "$current_pages" -ge "$pages" ]; then
        echo "[SKIP] $name - already complete ($current_pages/$pages pages)"
        return 0
    fi
    
    echo ""
    echo "========================================"
    echo "[START] $name ($pages pages)"
    echo "Time: $(date)"
    echo "========================================"
    
    # Generate page list
    local page_list=$(seq -s, 1 $pages)
    
    .venv/bin/python -m doclibrary.cli extract "pdfs/batch2/$pdf" \
        --pages "$page_list" --output-dir "$data_dir" --skip-existing 2>&1
    
    local final_pages=$(ls "$data_dir/pages/"*.json 2>/dev/null | wc -l)
    echo "[DONE] $name - $final_pages/$pages pages extracted"
    echo "Time: $(date)"
}

echo "=========================================="
echo "BATCH2 EXTRACTION - REMAINING DOCUMENTS"
echo "Started: $(date)"
echo "=========================================="

# Documents in order of size (smallest first for quick wins)
extract_doc "esa_cci_hrlc_field_2023" "esa_CCI_HRLCv4_field_2023.pdf" 91
extract_doc "copernicus_chime_mrd" "Copernicus_CHIME_MRD_v3_2021.pdf" 97
extract_doc "sentinel_access_2021" "COPE-SERCO-RP-22-1312_Sentinel_Data_Access_Annual_2021.pdf" 128
extract_doc "sentinel_access_2019" "COPE-SERCO-RP-20-0570_Sentinel_Data_Access_Annual_2019.pdf" 134
extract_doc "esa_cci_hrlc_val1_2023" "esa_CCI_HRLCv4_val1_2023.pdf" 135
extract_doc "imeo_report_2022" "climateGHG_IMEO_2022.pdf" 136
extract_doc "nisar_spec_2019" "NASA_ISRO_NISAR_spec_2019.pdf" 139
extract_doc "gst_catalog_2022" "satSO_GST-catalog_2022.pdf" 140
extract_doc "esa_data_access_2024" "esa_dataAccess_2024.pdf" 142
extract_doc "unep_methane_2023" "unep_eye-on-methane_2023.pdf" 142
extract_doc "geo_fullpic_2020" "GEO_fullPic_2020.pdf" 143
extract_doc "foss4g_2017" "FOSS4G_2017_Full_Proceedings.pdf" 191
extract_doc "nas_ghg_2022" "climateGHG_NAS_2022.pdf" 196
extract_doc "wildfire_california_2020" "Wildfire-in-California_ccst_2020.pdf" 248
extract_doc "gnss_overview_2022" "gnss_ovr_2022.pdf" 250
extract_doc "gfoi_mgd_2016" "forestAU_GFOI-MGD_2016.pdf" 260
extract_doc "gnss_overview_2023" "gnss_ovr_2023.pdf" 262
extract_doc "water_worldbank_2016" "water_WorldBank_2016.pdf" 267
extract_doc "copernicus_cimr_mrd" "Copernicus_CIMR_MRD_v5_2023.pdf" 269
extract_doc "jacie_2022" "satJACIE_2022.pdf" 298
extract_doc "foss4g_2015" "FOSS4G_2015_Proceedings_v2.pdf" 437
extract_doc "geomatics_book_2019" "geombook2019.01.11.pdf" 455
extract_doc "ca_climate_2022" "ca_ClimateIndicators-4th_OEHH_2022.pdf" 665
extract_doc "proj_manual_96" "proj-org-en-9.6.pdf" 965

echo ""
echo "=========================================="
echo "EXTRACTION COMPLETE"
echo "Finished: $(date)"
echo "=========================================="

# Final summary
echo ""
echo "=== FINAL STATUS ==="
for dir in db/data/*/; do
    name=$(basename "$dir")
    count=$(ls "$dir/pages/"*.json 2>/dev/null | wc -l)
    echo "$name: $count pages"
done
