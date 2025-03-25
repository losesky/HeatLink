# Data Migration and Redeployment Guide

This document provides detailed guidance on migrating data between different environments and avoiding data issues when redeploying the system.

## Data Backup and Recovery

### Automatic Backup

The `local-dev.sh` script automatically checks the existing database and creates a backup each time it starts. Backup files are saved in the `db_backups` folder in the project root directory. This backup is useful for preventing data loss during development.

### Manual Backup

You can manually create database backups using the following commands:

```bash
# Backup a running database
docker exec -t heatlink-postgres-local pg_dump -U postgres -d heatlink_dev > backup_$(date +%Y%m%d_%H%M%S).sql

# Or use our data export script (backs up core data only)
cd backend
python scripts/verify_data.py export --output ../data_export.json
```

### Data Recovery

Recovering from an SQL backup:

```bash
# First ensure the database container is running
docker compose -f docker-compose.local.yml up -d

# Restore from SQL file
cat backup.sql | docker exec -i heatlink-postgres-local psql -U postgres -d heatlink_dev

# Restart services
docker compose -f docker-compose.local.yml restart
```

Recovering from exported JSON data:

```bash
cd backend
python scripts/verify_data.py import --input ../data_export.json
```

## Data Validation and Repair

We provide a dedicated data validation script that can check for data consistency issues and automatically fix some common problems:

```bash
# Validate data
cd backend
python scripts/verify_data.py verify

# Show detailed information
python scripts/verify_data.py verify --verbose

# Attempt to automatically fix issues
python scripts/verify_data.py verify --fix
```

## Cross-Environment Data Migration

When you need to migrate data between development, testing, and production environments, the following workflow is recommended:

1. **Export data from the source environment**:
   ```bash
   cd backend
   python scripts/verify_data.py export --output data_export.json
   ```

2. **Copy the exported JSON file to the target environment**

3. **Import data in the target environment**:
   ```bash
   cd backend
   python scripts/verify_data.py import --input data_export.json
   ```

   If you need to clear existing data in the target environment:
   ```bash
   python scripts/verify_data.py import --input data_export.json --clear
   ```

## Best Practices for System Redeployment

Follow these steps to maximize data consistency protection when redeploying the system:

1. **Pre-deployment backup**:
   ```bash
   # If you have a running database
   docker exec -t heatlink-postgres-local pg_dump -U postgres -d heatlink_dev > pre_deploy_backup.sql
   
   # Or use core data export
   cd backend
   python scripts/verify_data.py export --output pre_deploy_data.json
   ```

2. **Clean deployment**:
   ```bash
   ./local-dev.sh
   ```
   This script will automatically:
   - Create a data backup
   - Start services
   - Execute database migrations
   - Verify data consistency
   - Initialize basic data if necessary

3. **Post-deployment validation**:
   ```bash
   cd backend
   python scripts/verify_data.py verify --verbose
   ```

4. **Restore from backup if there are issues**:
   ```bash
   cat pre_deploy_backup.sql | docker exec -i heatlink-postgres-local psql -U postgres -d heatlink_dev
   ```

## Common Issues and Solutions

### Database Migration Failure

If migration fails, you can try:

1. Check logs to determine the cause of failure
2. Use `alembic stamp head` to mark the current version
3. Create a new migration: `alembic revision --autogenerate -m "Fix migration"`
4. Apply the new migration: `alembic upgrade head`

### Missing Basic Data

If the `sources`, `categories`, or `tags` tables are empty:

```bash
cd backend
python scripts/init_all.py
```

Or manually initialize each component:

```bash
cd backend
python scripts/init_sources.py
python scripts/init_tags.py
python scripts/create_admin.py --non-interactive
```

### Data Relationship Inconsistencies

Use the validation tool to fix data relationships:

```bash
cd backend
python scripts/verify_data.py verify --fix
```

## Administrator Accounts

When redeploying, you may need to create new administrator accounts:

```bash
# Interactive creation
cd backend
python scripts/create_admin.py

# Or non-interactive creation (auto-generated password)
python scripts/create_admin.py --non-interactive --email admin@example.com

# Specify password
python scripts/create_admin.py --non-interactive --email admin@example.com --password secure_password
```

## Complete Environment Reset

If you need to completely reset the development environment:

```bash
# Stop all containers and delete volumes
docker compose -f docker-compose.local.yml down -v

# Restart the environment
./local-dev.sh
```

This will delete all data and reinitialize the environment. 