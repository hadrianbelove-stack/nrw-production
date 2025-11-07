#!/bin/bash
# DEPRECATED: daily_update.sh has been replaced by daily_orchestrator.py
#
# This file is maintained only as a stub to redirect users to the new daily automation system.
# The legacy implementation has been moved to museum_legacy/daily_update.sh for reference.

echo "❌ DEPRECATED: daily_update.sh is no longer supported"
echo ""
echo "The daily update functionality has been integrated into the production orchestration system."
echo "Please use the following command instead:"
echo ""
echo "  For complete daily pipeline:"
echo "    python3 daily_orchestrator.py"
echo ""
echo "  For manual steps:"
echo "    python3 generate_data.py --discover  # Discovery + monitoring"
echo "    python3 generate_data.py             # Data enrichment"
echo ""
echo "The legacy implementation is available at:"
echo "    museum_legacy/daily_update.sh"
echo ""
echo "For more information, see README.md and NRW_DATA_WORKFLOW_EXPLAINED.md"

# Exit with error code to indicate deprecation
exit 1
