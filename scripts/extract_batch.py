#!/usr/bin/env python3
"""Simple batch extraction script that processes documents sequentially."""

import subprocess
import sys
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
PDF_DIR = PROJECT_DIR / "pdfs" / "batch2"
DATA_DIR = PROJECT_DIR / "db" / "data"

# Small docs (< 30 pages)
SMALL_DOCS = [
    ("usgs_projections_poster", "projectionsPoster_USGS.pdf", 2),
    ("cdfw_projections", "CDFW_Projection_and_Datum_Guidelines.pdf", 3),
    ("imeo_brochure_2022", "climateGHG_IMEO-brochure_2022.pdf", 4),
    ("graph_databases_overview", "Graph_databases_overview_CS2311924.pdf", 6),
    ("eu_kndvi_time", "timeEU_kNdvi.pdf", 6),
    ("ghg_usa_points_2022", "satGHG_USA_pts_2022.pdf", 7),
    ("sentinel2a_save_2024", "save_S2A_2024.pdf", 7),
    ("proj_gdal_survey", "survey_ProjGDAL.pdf", 7),
    ("jaxa_dashboard", "cloudJAXA_dashboard.pdf", 8),
    ("eu_eo_overview", "dataEO_EU_ovr.pdf", 8),
    ("gnss_mgpp_2023", "gnss_MGPP_2023.pdf", 8),
    ("green_marble_2022", "greenMarble_product_2022.pdf", 8),
    ("ghg_gulf_usa_2022", "satGHG_gulf_USA_2022.pdf", 10),
    ("methane_harvard_2023", "satMethane_harvardBall_2023.pdf", 10),
    ("gist_trees_1995", "hellerstein-etal-1995.pdf", 12),
    ("amoc_atlantic_2024", "oceanAtlantic_article_AMOC_2024.pdf", 12),
    ("mapreduce_dean_1995", "sfwr_Dean_1995.pdf", 12),
    ("ecobird_2022", "ecoBird_2022.pdf", 14),
    ("nasa_csda_roses_2021", "NASA_CSDA_ROSES_data_2021.pdf", 14),
    ("earthdaily_2023", "EarthDaily_Keith-Beckett_May_17.pdf", 15),
    ("lulc_esa_usgs_2021", "lulcComp_esa_usgsPT_2021.pdf", 16),
    ("urban_osm_ml_2018", "urbanML_OSM_forget_2018.pdf", 16),
    ("osm_history_2019", "osmHist_Minghini_2019.pdf", 17),
    ("nasa_cms_ghg_2021", "satGHG_NASA_CMS_2021.pdf", 17),
    ("rs_deep_learning_2021", "remotesensing-13-04622.pdf", 18),
    ("coast_mapping_2021", "coastMapping_robby_2021.pdf", 19),
    ("sentinel2_coverage_2019", "esaSent2_coverages_2019.pdf", 19),
    ("geoss_2030_agenda", "GEOSS_2030_agenda.pdf", 19),
    ("sql_trees_celko", "Joe_Celco_Trees_in_SQL.pdf", 20),
    ("rs_land_cover_ml_2021", "remotesensing-13-02428.pdf", 20),
    ("openeo_architecture_2021", "openEO_arch_2021.pdf", 21),
    ("rs_sentinel2_cloud_2021", "remotesensing-13-01125-v3.pdf", 21),
    ("rs_change_detection_2021", "remotesensing-13-04807-v2.pdf", 21),
    ("planet_arp_2024", "Planet_AnalysisReadyPlanetScopev1_2024.pdf", 23),
    ("gedi_l2_2020", "ornl_GEDI2_2020.pdf", 24),
    ("methane_overview_2022", "satMethane_ovr_2022.pdf", 24),
    ("carbon_mapper_2024", "CarbonMapper_data_v114.pdf", 25),
    ("usfs_wildfire_crisis_2022", "Confronting-Wildfire-Crisis_USFS_2022.pdf", 25),
    ("methane_rmi_2023", "satMethane_RMI_2023.pdf", 25),
    ("noaa_ccap_ca_2023", "dataAccess_NOAA_ccap_CA_2023.pdf", 27),
    ("esa_lsi_vc_2025", "esa_LSI-VC_interop_2025.pdf", 27),
    ("tropomi_nl_2023", "satTROPOMI_nl_2023.pdf", 28),
    ("land_cover_kotsev_2019", "landcover_Kotsev_2019.pdf", 29),
    ("lclas_us_2023", "satLCLAS_usob_2023.pdf", 29),
]


def is_extracted(slug: str, expected_pages: int) -> bool:
    """Check if document is already extracted."""
    pages_dir = DATA_DIR / slug / "pages"
    if not pages_dir.exists():
        return False
    page_files = list(pages_dir.glob("page_*.json"))
    return len(page_files) >= expected_pages


def extract_document(slug: str, pdf_file: str) -> bool:
    """Extract a single document."""
    pdf_path = PDF_DIR / pdf_file
    output_dir = DATA_DIR / slug

    cmd = [
        sys.executable,
        "-m",
        "doclibrary.cli",
        "extract",
        str(pdf_path),
        "--pages",
        "all",
        "--output-dir",
        str(output_dir),
        "--skip-existing",
    ]

    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    return result.returncode == 0


def main():
    batch = sys.argv[1] if len(sys.argv) > 1 else "small"

    if batch == "small":
        docs = SMALL_DOCS
    else:
        print(f"Unknown batch: {batch}")
        sys.exit(1)

    total = len(docs)
    extracted = 0
    skipped = 0
    failed = 0

    print(f"\nBatch extraction: {batch} ({total} documents)")
    print("=" * 50)

    for i, (slug, pdf_file, pages) in enumerate(docs, 1):
        if is_extracted(slug, pages):
            print(f"[{i}/{total}] SKIP: {slug} (already extracted)")
            skipped += 1
            continue

        print(f"\n[{i}/{total}] Extracting: {slug} ({pages} pages)")
        print("-" * 50)

        if extract_document(slug, pdf_file):
            extracted += 1
            print(f"[{i}/{total}] DONE: {slug}")
        else:
            failed += 1
            print(f"[{i}/{total}] FAILED: {slug}")

    print("\n" + "=" * 50)
    print(f"Completed: {extracted} extracted, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
