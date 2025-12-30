#!/bin/bash
# Batch 2 extraction runner
# Processes PDFs from pdfs/batch2/ through the full pipeline
#
# GPU CONSTRAINT: Vision LLM and Text LLM cannot run simultaneously!
# Use two-phase workflow:
#   Phase 1: Extract all documents (Vision LLM on port 8090)
#   Phase 2: Enrich + ingest all (Text LLM on port 8080 + Embedding on 8094)
#
# Usage:
#   ./scripts/run_batch2.sh extract small    # Extract all small docs (Vision LLM)
#   ./scripts/run_batch2.sh enrich small     # Enrich + ingest small docs (Text LLM)
#   ./scripts/run_batch2.sh extract single SLUG
#   ./scripts/run_batch2.sh status
#   ./scripts/run_batch2.sh check extract    # Check Vision LLM
#   ./scripts/run_batch2.sh check enrich     # Check Text LLM + Embedding
#
# Options:
#   --resume    Skip documents already processed
#   --dry-run   Show what would be processed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PDF_DIR="$PROJECT_DIR/pdfs/batch2"
DATA_DIR="$PROJECT_DIR/db/data"
LOG_DIR="$PROJECT_DIR/logs/batch2"

cd "$PROJECT_DIR"
source .venv/bin/activate
mkdir -p "$LOG_DIR"

# Document definitions: SLUG|PDF_FILE|PAGES
SMALL_DOCS=(
    "usgs_projections_poster|projectionsPoster_USGS.pdf|2"
    "cdfw_projections|CDFW_Projection_and_Datum_Guidelines.pdf|3"
    "imeo_brochure_2022|climateGHG_IMEO-brochure_2022.pdf|4"
    "graph_databases_overview|Graph_databases_overview_CS2311924.pdf|6"
    "eu_kndvi_time|timeEU_kNdvi.pdf|6"
    "ghg_usa_points_2022|satGHG_USA_pts_2022.pdf|7"
    "sentinel2a_save_2024|save_S2A_2024.pdf|7"
    "proj_gdal_survey|survey_ProjGDAL.pdf|7"
    "jaxa_dashboard|cloudJAXA_dashboard.pdf|8"
    "eu_eo_overview|dataEO_EU_ovr.pdf|8"
    "gnss_mgpp_2023|gnss_MGPP_2023.pdf|8"
    "green_marble_2022|greenMarble_product_2022.pdf|8"
    "ghg_gulf_usa_2022|satGHG_gulf_USA_2022.pdf|10"
    "methane_harvard_2023|satMethane_harvardBall_2023.pdf|10"
    "gist_trees_1995|hellerstein-etal-1995.pdf|12"
    "amoc_atlantic_2024|oceanAtlantic_article_AMOC_2024.pdf|12"
    "mapreduce_dean_1995|sfwr_Dean_1995.pdf|12"
    "ecobird_2022|ecoBird_2022.pdf|14"
    "nasa_csda_roses_2021|NASA_CSDA_ROSES_data_2021.pdf|14"
    "earthdaily_2023|EarthDaily_Keith-Beckett_May_17.pdf|15"
    "lulc_esa_usgs_2021|lulcComp_esa_usgsPT_2021.pdf|16"
    "urban_osm_ml_2018|urbanML_OSM_forget_2018.pdf|16"
    "osm_history_2019|osmHist_Minghini_2019.pdf|17"
    "nasa_cms_ghg_2021|satGHG_NASA_CMS_2021.pdf|17"
    "rs_deep_learning_2021|remotesensing-13-04622.pdf|18"
    "coast_mapping_2021|coastMapping_robby_2021.pdf|19"
    "sentinel2_coverage_2019|esaSent2_coverages_2019.pdf|19"
    "geoss_2030_agenda|GEOSS_2030_agenda.pdf|19"
    "sql_trees_celko|Joe_Celco_Trees_in_SQL.pdf|20"
    "rs_land_cover_ml_2021|remotesensing-13-02428.pdf|20"
    "openeo_architecture_2021|openEO_arch_2021.pdf|21"
    "rs_sentinel2_cloud_2021|remotesensing-13-01125-v3.pdf|21"
    "rs_change_detection_2021|remotesensing-13-04807-v2.pdf|21"
    "planet_arp_2024|Planet_AnalysisReadyPlanetScopev1_2024.pdf|23"
    "gedi_l2_2020|ornl_GEDI2_2020.pdf|24"
    "methane_overview_2022|satMethane_ovr_2022.pdf|24"
    "carbon_mapper_2024|CarbonMapper_data_v114.pdf|25"
    "usfs_wildfire_crisis_2022|Confronting-Wildfire-Crisis_USFS_2022.pdf|25"
    "methane_rmi_2023|satMethane_RMI_2023.pdf|25"
    "noaa_ccap_ca_2023|dataAccess_NOAA_ccap_CA_2023.pdf|27"
    "esa_lsi_vc_2025|esa_LSI-VC_interop_2025.pdf|27"
    "tropomi_nl_2023|satTROPOMI_nl_2023.pdf|28"
    "land_cover_kotsev_2019|landcover_Kotsev_2019.pdf|29"
    "lclas_us_2023|satLCLAS_usob_2023.pdf|29"
)

MEDIUM_DOCS=(
    "copernicus_report_20|analytical-report_20_copernicus.pdf|30"
    "methane_egu_2022|satMethane_egu_2022.pdf|30"
    "landsat_50years_2021|landsat50_remotesensing_2021.pdf|33"
    "sentinel2_mpc_gri_v2|S2-MPC_PHB_MultiLayer_L1B_GRI_V2.pdf|34"
    "geoawesome_geoforgood_2025|Geoawesome_GeoForGood_2025.pdf|35"
    "random_forests_review|randomforests-rev.pdf|35"
    "sat_lao_us_2024|satLAO_us_2024.pdf|35"
    "copernicus_dem_v4_2022|demCopernicus_Handbook_v4_2022.pdf|36"
    "jacie_overview_2024|satJACIE_ovr_2024.pdf|36"
    "ghg_geo_2021|climateGHG_GEO_2021.pdf|38"
    "methane_egusphere_2023|satMethane_egusphere_2023.pdf|40"
    "india_space_2025|satIndia_SpaceEconomyRegulatoryHandbook_2025.pdf|41"
    "tropomi_nl_2022|satTROPOMI_nl_2022.pdf|47"
    "calfire_redbook_2020|CalFIRE_Redbook_2020.pdf|53"
    "carto_geodatascience_2024|carto_geoDataScience_2024.pdf|56"
    "open_geodata_2023|OpenGeodata_Ochwada_2023.pdf|59"
    "sentinel2_mpc_gcp_v3|S2-MPC_PHB_GCP_L1B_L1C_GRI_V3.pdf|68"
    "foss4g_na_2018_sql|FOSS4G_NA_2018_SQLFest.pdf|74"
    "copernicus_cristal_mrd|Copernicus_CRISTAL_MRD_v3_2020.pdf|78"
    "eu_jrc_data_2023|dataEU_JRC129900_2023.pdf|80"
    "geoland_handbook|GEOLAND-Handbook-EN.pdf|81"
    "copernicus_co2m_mrd|Copernicus_CO2M_MRD_v3_2020.pdf|84"
    "copernicus_rosel_mrd|Copernicus_ROSE-L_MRD_v2.pdf|90"
    "esa_cci_hrlc_field_2023|esa_CCI_HRLCv4_field_2023.pdf|91"
    "copernicus_chime_mrd|Copernicus_CHIME_MRD_v3_2021.pdf|97"
)

LARGE_DOCS=(
    "unep_egr_2021|unep_EGR_2021.pdf|112"
    "landsat8_manual_v5|landsat8_datamanual_v5.pdf|114"
    "esa_cci_hrlc_val2_2023|esa_CCI_HRLCv4_val2_2023.pdf|115"
    "landsat9_manual|landsat9_datamanual.pdf|115"
    "sentinel_access_2018|COPE_Sentinel_Data_Access_Annual_2018.pdf|116"
    "sentinel_access_2020|COPE-SERCO-RP-21-1141_Sentinel_Data_Access_Annual_2020_v2.3.pdf|126"
    "sentinel_access_2021|COPE-SERCO-RP-22-1312_Sentinel_Data_Access_Annual_2021.pdf|128"
    "sentinel_access_2019|COPE-SERCO-RP-20-0570_Sentinel_Data_Access_Annual_2019.pdf|134"
    "esa_cci_hrlc_val1_2023|esa_CCI_HRLCv4_val1_2023.pdf|135"
    "imeo_report_2022|climateGHG_IMEO_2022.pdf|136"
    "nisar_spec_2019|NASA_ISRO_NISAR_spec_2019.pdf|139"
    "gst_catalog_2022|satSO_GST-catalog_2022.pdf|140"
    "esa_data_access_2024|esa_dataAccess_2024.pdf|142"
    "unep_methane_2023|unep_eye-on-methane_2023.pdf|142"
    "geo_fullpic_2020|GEO_fullPic_2020.pdf|143"
    "foss4g_2017|FOSS4G_2017_Full_Proceedings.pdf|191"
    "nas_ghg_2022|climateGHG_NAS_2022.pdf|196"
    "wildfire_california_2020|Wildfire-in-California_ccst_2020.pdf|248"
    "gnss_overview_2022|gnss_ovr_2022.pdf|250"
    "gfoi_mgd_2016|forestAU_GFOI-MGD_2016.pdf|260"
    "gnss_overview_2023|gnss_ovr_2023.pdf|262"
    "water_worldbank_2016|water_WorldBank_2016.pdf|267"
    "copernicus_cimr_mrd|Copernicus_CIMR_MRD_v5_2023.pdf|269"
    "jacie_2022|satJACIE_2022.pdf|298"
    "foss4g_2015|FOSS4G_2015_Proceedings_v2.pdf|437"
    "geomatics_book_2019|geombook2019.01.11.pdf|455"
    "ca_climate_2022|ca_ClimateIndicators-4th_OEHH_2022.pdf|665"
    "proj_manual_96|proj-org-en-9.6.pdf|965"
)

# Parse options
RESUME=false
DRY_RUN=false
for arg in "$@"; do
    case $arg in
        --resume) RESUME=true ;;
        --dry-run) DRY_RUN=true ;;
    esac
done

# Check servers for specific phase
check_extract_servers() {
    echo "Checking servers for EXTRACTION phase..."
    local ok=true
    
    if curl -s http://localhost:8090/health > /dev/null 2>&1; then
        echo "  Vision LLM (8090): OK"
    else
        echo "  Vision LLM (8090): FAILED"
        echo "    Start with: /media/nvme2g-a/llm_toolbox/servers/qwen3-vl-235b-8090.sh &"
        ok=false
    fi
    
    # Warn if text LLM is running (GPU conflict)
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "  WARNING: Text LLM (8080) is running - may cause GPU memory issues!"
        echo "    Consider stopping it: pkill -f qwen3-30b"
    fi
    
    [ "$ok" = true ]
}

check_enrich_servers() {
    echo "Checking servers for ENRICHMENT phase..."
    local ok=true
    
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "  Text LLM (8080): OK"
    else
        echo "  Text LLM (8080): FAILED"
        echo "    Start with: /media/nvme2g-a/llm_toolbox/servers/qwen3-30b-32k.sh &"
        ok=false
    fi
    
    if curl -s http://localhost:8094/health > /dev/null 2>&1; then
        echo "  Embedding (8094): OK"
    else
        echo "  Embedding (8094): FAILED"
        echo "    Start with: /media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh &"
        ok=false
    fi
    
    if psql -d osgeo_library -c "SELECT 1;" > /dev/null 2>&1; then
        echo "  Database: OK"
    else
        echo "  Database: FAILED"
        ok=false
    fi
    
    # Warn if vision LLM is running (GPU conflict)
    if curl -s http://localhost:8090/health > /dev/null 2>&1; then
        echo "  WARNING: Vision LLM (8090) is running - may cause GPU memory issues!"
        echo "    Consider stopping it: pkill -f qwen3-vl-235b"
    fi
    
    [ "$ok" = true ]
}

# Check extraction status
is_extracted() {
    local slug=$1
    local doc_dir="$DATA_DIR/$slug"
    [ -d "$doc_dir/pages" ] && [ "$(ls -1 "$doc_dir/pages"/page_*.json 2>/dev/null | wc -l)" -gt 0 ]
}

is_enriched() {
    local slug=$1
    local doc_dir="$DATA_DIR/$slug"
    # Check if document.json has summary (enrichment marker)
    [ -f "$doc_dir/document.json" ] && grep -q '"summary"' "$doc_dir/document.json" 2>/dev/null
}

is_in_db() {
    local slug=$1
    local count=$(psql -d osgeo_library -t -c "SELECT COUNT(*) FROM documents WHERE slug='$slug';" 2>/dev/null | tr -d ' ')
    [ "$count" -gt 0 ]
}

# Extract a single document (Vision LLM phase)
extract_document() {
    local slug=$1
    local pdf_file=$2
    local pages=$3
    local pdf_path="$PDF_DIR/$pdf_file"
    local log_file="$LOG_DIR/${slug}_extract.log"
    
    echo ""
    echo "========================================"
    echo "EXTRACT: $slug ($pages pages)"
    echo "========================================"
    
    if [ ! -f "$pdf_path" ]; then
        echo "ERROR: PDF not found: $pdf_path"
        return 1
    fi
    
    if [ "$RESUME" = true ] && is_extracted "$slug"; then
        echo "SKIP: Already extracted"
        return 0
    fi
    
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY RUN] Would extract $slug"
        return 0
    fi
    
    echo "Started: $(date)"
    
    # Use doclibrary CLI with --pages all and --skip-existing for resumability
    python -m doclibrary.cli extract "$pdf_path" \
        --pages all \
        --output-dir "$DATA_DIR/$slug" \
        --skip-existing 2>&1 | tee "$log_file"
    
    echo "Completed: $(date)"
}

# Enrich and ingest a single document (Text LLM phase)
enrich_document() {
    local slug=$1
    local log_file="$LOG_DIR/${slug}_enrich.log"
    
    echo ""
    echo "========================================"
    echo "ENRICH+INGEST: $slug"
    echo "========================================"
    
    if ! is_extracted "$slug"; then
        echo "SKIP: Not yet extracted"
        return 0
    fi
    
    if [ "$RESUME" = true ] && is_in_db "$slug"; then
        echo "SKIP: Already in database"
        return 0
    fi
    
    if [ "$DRY_RUN" = true ]; then
        echo "[DRY RUN] Would enrich+ingest $slug"
        return 0
    fi
    
    echo "Started: $(date)"
    
    echo "Enriching..."
    python -m doclibrary.cli enrich "$slug" --skip-existing 2>&1 | tee "$log_file"
    
    echo "Ingesting..."
    python -m doclibrary.cli ingest "$slug" --delete-first 2>&1 | tee -a "$log_file"
    
    echo "Completed: $(date)"
}

# Process batch
process_extract_batch() {
    local batch_name=$1
    shift
    local docs=("$@")
    local total=${#docs[@]}
    local count=0
    
    echo ""
    echo "========================================"
    echo "EXTRACT batch: $batch_name ($total documents)"
    echo "Started: $(date)"
    echo "========================================"
    
    for doc_entry in "${docs[@]}"; do
        IFS='|' read -r slug pdf_file pages <<< "$doc_entry"
        ((count++))
        echo ""
        echo "[$count/$total]"
        extract_document "$slug" "$pdf_file" "$pages"
    done
    
    echo ""
    echo "========================================"
    echo "EXTRACT batch $batch_name complete: $(date)"
    echo "========================================"
}

process_enrich_batch() {
    local batch_name=$1
    shift
    local docs=("$@")
    local total=${#docs[@]}
    local count=0
    
    echo ""
    echo "========================================"
    echo "ENRICH batch: $batch_name ($total documents)"
    echo "Started: $(date)"
    echo "========================================"
    
    for doc_entry in "${docs[@]}"; do
        IFS='|' read -r slug pdf_file pages <<< "$doc_entry"
        ((count++))
        echo ""
        echo "[$count/$total]"
        enrich_document "$slug"
    done
    
    echo ""
    echo "========================================"
    echo "ENRICH batch $batch_name complete: $(date)"
    echo "========================================"
}

# Status display
show_status() {
    echo ""
    echo "Batch 2 Extraction Status"
    echo "========================================"
    
    local ext=0 enr=0 db=0 pend=0
    
    echo ""
    echo "Small (<30 pages):"
    for doc_entry in "${SMALL_DOCS[@]}"; do
        IFS='|' read -r slug pdf_file pages <<< "$doc_entry"
        local status=""
        if is_extracted "$slug"; then
            status="[extracted]"
            ((ext++)) || true
            if is_enriched "$slug"; then
                status="$status[enriched]"
                ((enr++)) || true
            fi
            if is_in_db "$slug"; then
                status="$status[DB]"
                ((db++)) || true
            fi
        else
            status="[pending]"
            ((pend++)) || true
        fi
        printf "  %-35s %3s pages %s\n" "$slug" "$pages" "$status"
    done
    
    echo ""
    echo "Medium (30-100 pages):"
    for doc_entry in "${MEDIUM_DOCS[@]}"; do
        IFS='|' read -r slug pdf_file pages <<< "$doc_entry"
        local status=""
        if is_extracted "$slug"; then
            status="[extracted]"
            ((ext++)) || true
            if is_enriched "$slug"; then
                status="$status[enriched]"
                ((enr++)) || true
            fi
            if is_in_db "$slug"; then
                status="$status[DB]"
                ((db++)) || true
            fi
        else
            status="[pending]"
            ((pend++)) || true
        fi
        printf "  %-35s %3s pages %s\n" "$slug" "$pages" "$status"
    done
    
    echo ""
    echo "Large (100+ pages):"
    for doc_entry in "${LARGE_DOCS[@]}"; do
        IFS='|' read -r slug pdf_file pages <<< "$doc_entry"
        local status=""
        if is_extracted "$slug"; then
            status="[extracted]"
            ((ext++)) || true
            if is_enriched "$slug"; then
                status="$status[enriched]"
                ((enr++)) || true
            fi
            if is_in_db "$slug"; then
                status="$status[DB]"
                ((db++)) || true
            fi
        else
            status="[pending]"
            ((pend++)) || true
        fi
        printf "  %-35s %3s pages %s\n" "$slug" "$pages" "$status"
    done
    
    echo ""
    echo "========================================"
    echo "Summary: $ext extracted, $enr enriched, $db in DB, $pend pending"
    echo "========================================"
}

find_doc_by_slug() {
    local target=$1
    for doc_entry in "${SMALL_DOCS[@]}" "${MEDIUM_DOCS[@]}" "${LARGE_DOCS[@]}"; do
        IFS='|' read -r slug pdf_file pages <<< "$doc_entry"
        if [ "$slug" = "$target" ]; then
            echo "$doc_entry"
            return 0
        fi
    done
    return 1
}

get_batch_docs() {
    local batch=$1
    case $batch in
        small) echo "${SMALL_DOCS[@]}" ;;
        medium) echo "${MEDIUM_DOCS[@]}" ;;
        large) echo "${LARGE_DOCS[@]}" ;;
        all) echo "${SMALL_DOCS[@]}" "${MEDIUM_DOCS[@]}" "${LARGE_DOCS[@]}" ;;
    esac
}

# Main
case "${1:-}" in
    check)
        case "${2:-}" in
            extract) check_extract_servers ;;
            enrich) check_enrich_servers ;;
            *)
                echo "Usage: $0 check [extract|enrich]"
                echo "  extract - Check Vision LLM for extraction phase"
                echo "  enrich  - Check Text LLM + Embedding for enrichment phase"
                ;;
        esac
        ;;
    
    status)
        show_status
        ;;
    
    extract)
        case "${2:-}" in
            small|medium|large|all)
                check_extract_servers || exit 1
                case "$2" in
                    small) process_extract_batch "small" "${SMALL_DOCS[@]}" ;;
                    medium) process_extract_batch "medium" "${MEDIUM_DOCS[@]}" ;;
                    large) process_extract_batch "large" "${LARGE_DOCS[@]}" ;;
                    all)
                        process_extract_batch "small" "${SMALL_DOCS[@]}"
                        process_extract_batch "medium" "${MEDIUM_DOCS[@]}"
                        process_extract_batch "large" "${LARGE_DOCS[@]}"
                        ;;
                esac
                ;;
            single)
                if [ -z "${3:-}" ]; then
                    echo "Usage: $0 extract single SLUG"
                    exit 1
                fi
                check_extract_servers || exit 1
                doc_entry=$(find_doc_by_slug "$3") || { echo "Unknown slug: $3"; exit 1; }
                IFS='|' read -r slug pdf_file pages <<< "$doc_entry"
                extract_document "$slug" "$pdf_file" "$pages"
                ;;
            *)
                echo "Usage: $0 extract [small|medium|large|all|single SLUG]"
                ;;
        esac
        ;;
    
    enrich)
        case "${2:-}" in
            small|medium|large|all)
                check_enrich_servers || exit 1
                case "$2" in
                    small) process_enrich_batch "small" "${SMALL_DOCS[@]}" ;;
                    medium) process_enrich_batch "medium" "${MEDIUM_DOCS[@]}" ;;
                    large) process_enrich_batch "large" "${LARGE_DOCS[@]}" ;;
                    all)
                        process_enrich_batch "small" "${SMALL_DOCS[@]}"
                        process_enrich_batch "medium" "${MEDIUM_DOCS[@]}"
                        process_enrich_batch "large" "${LARGE_DOCS[@]}"
                        ;;
                esac
                ;;
            single)
                if [ -z "${3:-}" ]; then
                    echo "Usage: $0 enrich single SLUG"
                    exit 1
                fi
                check_enrich_servers || exit 1
                enrich_document "$3"
                ;;
            *)
                echo "Usage: $0 enrich [small|medium|large|all|single SLUG]"
                ;;
        esac
        ;;
    
    *)
        cat << 'EOF'
Batch 2 Extraction Runner

GPU CONSTRAINT: Vision LLM and Text LLM cannot run simultaneously!
Run extraction first, then stop Vision LLM and run enrichment.

Usage: ./scripts/run_batch2.sh COMMAND [BATCH] [OPTIONS]

Commands:
  check extract     Check Vision LLM is ready
  check enrich      Check Text LLM + Embedding are ready
  status            Show extraction status for all documents

  extract small     Extract all small documents (<30 pages)
  extract medium    Extract all medium documents (30-100 pages)
  extract large     Extract all large documents (100+ pages)
  extract all       Extract all documents
  extract single SLUG  Extract single document

  enrich small      Enrich + ingest small documents
  enrich medium     Enrich + ingest medium documents
  enrich large      Enrich + ingest large documents
  enrich all        Enrich + ingest all documents
  enrich single SLUG   Enrich + ingest single document

Options:
  --resume          Skip already processed documents
  --dry-run         Show what would be processed

Workflow Example:
  1. Start Vision LLM:
     /media/nvme2g-a/llm_toolbox/servers/qwen3-vl-235b-8090.sh &

  2. Extract all small documents:
     ./scripts/run_batch2.sh extract small --resume

  3. Stop Vision LLM, start Text LLM + Embedding:
     pkill -f qwen3-vl-235b
     /media/nvme2g-a/llm_toolbox/servers/qwen3-30b-32k.sh &
     /media/nvme2g-a/llm_toolbox/servers/bge-m3-embed-8094.sh &

  4. Enrich + ingest:
     ./scripts/run_batch2.sh enrich small --resume
EOF
        ;;
esac
