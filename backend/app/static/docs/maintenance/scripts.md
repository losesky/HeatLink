# HeatLink Maintenance Scripts

This document provides an overview of the maintenance scripts in the HeatLink project, their functions, and usage guidelines.

## Overview

HeatLink includes various maintenance scripts, primarily prefixed with `verify*`, `fix_*`, and `check_*`. These scripts are essential tools for data source monitoring, database repair, and system diagnostics during project operation and maintenance.

## The Unified Maintenance Script

HeatLink provides a unified maintenance script (`maintenance.sh`) that consolidates various maintenance functions:

```bash
# Run with interactive menu
./maintenance.sh

# Run specific tasks
./maintenance.sh --cleanup            # Clean temporary files
./maintenance.sh --clean-logs         # Clean old log files
./maintenance.sh --organize-tests     # Organize test files
./maintenance.sh --organize           # Organize maintenance tools
./maintenance.sh --remove-redundant   # Remove redundant scripts

# Run all maintenance tasks
./maintenance.sh --all
```

The unified script provides the following capabilities:
- Cleaning Python cache files and temporary files
- Managing log files (removing files older than 7 days)
- Organizing test files into the proper directory
- Organizing maintenance tools into the tools directory
- Removing redundant scripts that have been moved to the tools directory

## Script Categories and Functions

### 1. Data Source Monitoring Tools

| Filename | Path | Main Function | Notes |
|----------|------|---------------|-------|
| `check_sources_health.py` | `./tools/data_sources/` | Checks data source health status and repairs CLS data sources; monitors various data source statuses and automatically fixes CLS-related data sources in ERROR state | Use as a regular monitoring tool |
| `check_cls_api.py` | `./tools/data_sources/` | Tests CLS API and web scraping functionality; checks multiple API endpoints' availability and saves responses; analyzes webpage structure | Use as a diagnostic tool |
| `check_cls_with_selenium.py` | `./tools/data_sources/` | Tests CLS data scraping functionality using Selenium | Use as a backup diagnostic tool |
| `check_thepaper_structure.py` | `./tools/data_sources/` | Analyzes ThePaper website structure to help update the crawler | Use as a diagnostic tool |
| `verify_thepaper_fix.py` | `./tools/data_sources/` | Verifies the effectiveness of ThePaper data source fixes | Use as a diagnostic tool |

#### Usage Examples

```bash
# Check data source health
python tools/data_sources/check_sources_health.py

# Test CLS API
python tools/data_sources/check_cls_api.py

# Verify ThePaper fixes
python tools/data_sources/verify_thepaper_fix.py
```

### 2. Database Maintenance Tools

| Filename | Path | Main Function | Notes |
|----------|------|---------------|-------|
| `fix_database.sh` | `./tools/database/` | Repairs database schema and initializes data, including creating table structures, setting migration versions, and initializing base data | Core system recovery tool |
| `fix_categories.py` | `./tools/database/` | Fixes category data issues | Database maintenance tool |
| `verify_data.py` | `./backend/scripts/` | Verifies data consistency in the database, checks table structures and key data integrity | System validation tool |
| `fix_thepaper_source.py` | `./tools/data_sources/` | Fixes ThePaper data source configuration and crawling logic | Data source maintenance tool |

#### Usage Examples

```bash
# Fix database issues
./tools/database/fix_database.sh

# Fix category data
python tools/database/fix_categories.py

# Verify data consistency
python backend/scripts/verify_data.py verify

# Fix ThePaper source
python tools/data_sources/fix_thepaper_source.py
```

## Scheduled Maintenance

For critical monitoring and maintenance, consider setting up scheduled tasks:

```bash
# Run source health check every 4 hours
0 */4 * * * /home/username/HeatLink/backend/run_sources_health_check.sh

# Clean up temporary files and logs daily at 2 AM
0 2 * * * /home/username/HeatLink/maintenance.sh --cleanup --clean-logs

# Verify data integrity weekly on Sunday at 3 AM
0 3 * * 0 cd /home/username/HeatLink/backend && python scripts/verify_data.py verify --fix
```

## Best Practices

1. **Regular Monitoring**: Run health check scripts regularly to ensure data sources are functioning properly
2. **Preventive Maintenance**: Schedule routine cleanup and organization tasks to prevent issues
3. **Post-Update Verification**: After system updates, run verification scripts to ensure data integrity
4. **Logging**: Keep maintenance logs to track system health over time
5. **Notifications**: Set up notifications for critical issues detected by monitoring scripts

## Comprehensive Assessment

All scripts analyzed serve a clear purpose and provide practical value for system operation and maintenance:

1. **Data Source Monitoring Scripts**: Ensure stable fetching from external data sources (such as CLS, ThePaper), which is critical for content aggregation systems
2. **Database Maintenance Scripts**: Safeguard data integrity and consistency, supporting stable system operation
3. **Diagnostic Scripts**: Provide quick localization and diagnostic capabilities when system issues occur

## Conclusion

The maintenance scripts in the HeatLink project are essential safeguards for stable system operation. Using the unified `maintenance.sh` script provides a consistent interface to these tools, improving system maintainability and stability. 