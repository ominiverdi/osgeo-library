#!/bin/bash
# Run full extraction on all three PDFs
# Skips already-extracted pages for resumability
#
# Usage:
#   ./run_extraction.sh           # Run all
#   ./run_extraction.sh sam3      # Run specific document
#
# Estimated time:
#   sam3:           ~52 pages * 30s = ~26 minutes
#   alpine_change:  ~14 pages * 30s = ~7 minutes  
#   usgs_snyder:    ~384 pages * 30s = ~3.2 hours
#   Total: ~4 hours

set -e

cd /home/ominiverdi/github/osgeo-library
source .venv/bin/activate

echo "=========================================="
echo "Starting extraction at $(date)"
echo "=========================================="

# Check LLM server
if ! curl -s http://localhost:8090/health > /dev/null; then
    echo "ERROR: LLM server not responding at localhost:8090"
    exit 1
fi
echo "LLM server: OK"

# Function to extract a document
extract_doc() {
    local pdf=$1
    local name=$2
    
    echo ""
    echo "=========================================="
    echo "Extracting: $pdf -> $name"
    echo "Started at: $(date)"
    echo "=========================================="
    
    python extract_all_pages.py "$pdf" --name "$name" --skip-existing --delay 2
    
    echo "Finished $name at $(date)"
}

# Run based on argument or all
if [ "$1" = "sam3" ]; then
    extract_doc "sam3.pdf" "sam3"
elif [ "$1" = "alpine" ] || [ "$1" = "alpine_change" ]; then
    extract_doc "2511.00073v1.pdf" "alpine_change"
elif [ "$1" = "usgs" ] || [ "$1" = "usgs_snyder" ]; then
    extract_doc "usgs_snyder1987.pdf" "usgs_snyder"
else
    # Run all three
    extract_doc "sam3.pdf" "sam3"
    extract_doc "2511.00073v1.pdf" "alpine_change"
    extract_doc "usgs_snyder1987.pdf" "usgs_snyder"
fi

echo ""
echo "=========================================="
echo "All extractions complete at $(date)"
echo "=========================================="

python extract_all_pages.py --list
