# Setting Up the HeatLink Development Environment

This guide provides instructions for setting up a development environment for the HeatLink project.

## Prerequisites

Before you begin, ensure you have the following software installed on your system:

- **Python 3.8+**
- **Docker** and **Docker Compose**
- **Git**
- **PostgreSQL** client tools (optional, for direct database access)

## Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/losesky/HeatLink.git
cd HeatLink
```

### 2. Create a Virtual Environment

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Linux/macOS
source venv/bin/activate
# On Windows
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Copy the example environment file and customize it for your development setup:

```bash
cp .env.example .env.local
```

Edit `.env.local` to set the appropriate values for your environment.

## Starting the Development Environment

HeatLink provides a convenient script for starting the local development environment:

```bash
# Start the local development environment
./local-dev.sh
```

This script will:
1. Create a database backup if a database already exists
2. Start the required Docker containers (PostgreSQL, Redis)
3. Copy `.env.local` to `.env`
4. Run database migrations
5. Initialize basic data if needed

## Backend Development

### Starting the Backend API Server

```bash
cd backend
python start_server.py --reload
```

With the `--reload` flag, the server will automatically restart when code changes are detected.

### Starting the Worker Service

For developing with background tasks and Celery:

```bash
cd backend
python worker_start.py
```

### Starting the Beat Service

For developing with scheduled tasks:

```bash
cd backend
python beat_start.py
```

## Frontend Development

If the project includes a frontend component:

```bash
cd app
npm install
npm run dev
```

## Database Management

### Accessing the Database

```bash
# Connect to the PostgreSQL database
docker exec -it heatlink-postgres-local psql -U postgres -d heatlink_dev
```

### Creating and Applying Migrations

```bash
cd backend
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head
```

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific tests
pytest tests/test_specific_feature.py
```

### Test Coverage

```bash
# Generate coverage report
coverage run -m pytest
coverage report
coverage html  # For a more detailed HTML report
```

## Debugging

### Using the Flask Debugger

When running the API server in development mode, the Flask debugger is enabled by default.

### Debugging Celery Tasks

For debugging Celery tasks, you can use:

```bash
# Run a specific task and wait for the result
cd backend
python run_task.py task_name --wait

# Check the status of a task
python task_status.py <task_id>
```

## Development Tools

### Flower for Celery Monitoring

```bash
# Start Flower for monitoring Celery tasks
celery -A worker.celery_app flower --port=5555
```

Then access the Flower dashboard at http://localhost:5555

### Database Backups

```bash
# Create a database backup
docker exec -t heatlink-postgres-local pg_dump -U postgres -d heatlink_dev > backup_$(date +%Y%m%d_%H%M%S).sql
```

## Common Issues and Solutions

### Docker Container Issues

If you encounter issues with Docker containers:

```bash
# Stop all containers and remove volumes
docker compose -f docker-compose.local.yml down -v

# Start fresh
./local-dev.sh
```

### Database Connectivity Issues

If you cannot connect to the database:

1. Ensure the database container is running: `docker ps`
2. Check the database logs: `docker logs heatlink-postgres-local`
3. Verify the database connection settings in your `.env` file

### Dependencies Issues

If you encounter dependency conflicts:

1. Update your virtual environment: `pip install -r requirements.txt --upgrade`
2. If issues persist, try recreating your virtual environment

## Conclusion

This development environment setup should provide you with everything you need to start developing for the HeatLink project. If you encounter any issues or have questions, please refer to the [Troubleshooting](../maintenance/troubleshooting.md) section or contact the development team. 