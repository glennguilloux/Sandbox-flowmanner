# Celery Task System Documentation

This directory contains the Celery task processing system with RabbitMQ as the message broker. The system uses priority-based routing and task-type specific routing to ensure efficient task processing.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Celery Task    │────▶│  TaskPriority   │────▶│  RabbitMQ       │
│  Producer       │     │  Router         │     │  Exchange       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                    ┌─────────────────────────────────────┼─────────────────────────────────────┐
                    │                                     │                                     │
                    ▼                                     ▼                                     ▼
          ┌─────────────────┐                   ┌─────────────────┐                   ┌─────────────────┐
          │ priority        │                   │ tasks           │                   │ default         │
          │ (direct)        │                   │ (direct)        │                   │ (direct)        │
          └─────────────────┘                   └─────────────────┘                   └─────────────────┘
                    │                                     │                                     │
        ┌───────────┼───────────┐             ┌───────────┼───────────┐                     │
        │           │           │             │           │           │                     │
        ▼           ▼           ▼             ▼           ▼           ▼                     ▼
┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│ high_     │ │ medium_   │ │ low_      │ │ langgraph │ │ phase4    │ │ workers   │ │ default   │
│ priority  │ │ priority  │ │ priority  │ │ queue     │ │ queue     │ │ queue     │ │ queue     │
└───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘
        │           │           │             │           │           │                     │
        └───────────┴───────────┴─────────────┴───────────┴───────────┴─────────────────────┘
                                          │
                                          ▼
                               ┌─────────────────┐
                               │  Celery Worker  │
                               │  (Consumes from │
                               │   all queues)   │
                               └─────────────────┘
```

## RabbitMQ Infrastructure

### Exchanges

Three direct exchanges are defined:

| Exchange | Type   | Purpose                                          |
|----------|--------|--------------------------------------------------|
| priority | direct | Routes tasks to priority-based queues            |
| tasks    | direct | Routes tasks to type-specific queues             |
| default  | direct | Fallback for unrouted tasks                      |

### Queues

#### Priority Queues (with RabbitMQ priority support)

| Queue           | Exchange | Routing Key       | Max Priority |
|-----------------|----------|-------------------|--------------|
| high_priority   | priority | high_priority     | 10           |
| medium_priority | priority | medium_priority   | 10           |
| low_priority    | priority | low_priority      | 10           |

Priority queues use RabbitMQ's native priority queue feature (`x-max-priority: 10`), allowing messages with higher priority values to be delivered first.

#### Task-Type Queues

| Queue      | Exchange | Routing Key | Task Type                               |
|------------|----------|-------------|-----------------------------------------|
| langgraph  | tasks    | langgraph   | LangGraph workflow tasks                |
| phase4     | tasks    | phase4      | Phase 4 processing tasks                |
| n8n        | tasks    | n8n         | n8n automation tasks                    |
| comfyui    | tasks    | comfyui     | ComfyUI image generation tasks          |
| workers    | tasks    | workers     | General worker tasks                    |
| swarm      | tasks    | swarm       | Swarm consensus and coordination tasks  |
| deepagents | tasks    | deepagents  | DeepAgents AI tasks                     |

#### Default Queue

| Queue   | Exchange | Routing Key | Purpose                                    |
|---------|----------|-------------|--------------------------------------------|
| default | default  | default     | Fallback for tasks without specific routes |

## How Priority Routing Works

### Task Priority Assignment

The `TaskPriorityRouter` class in `task_optimizer.py` determines task priority based on:

1. **Explicit priority** in task options (highest precedence)
2. **Task name patterns** (automatic assignment):

| Pattern          | Priority | Examples              |
|------------------|----------|-----------------------|
| notification     | HIGH (9) | urgent, alert, chat   |
| email, report    | MEDIUM (5)| analytics, api, dashboard |
| backup, cleanup  | LOW (1)  | maintenance, log, stats |

### Routing Decision Flow

```
Task Submission
      │
      ▼
┌─────────────────┐
│ route_task()    │
│  - Extract task │
│  - Check options│
│  - Determine    │
│    priority     │
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Select Queue    │
│ based on        │
│ priority level  │
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ Return routing  │
│ dict:           │
│ {exchange,      │
│  routing_key,   │
│  priority}      │
└─────────────────┘
```

## File Structure

```
app/tasks/
├── __init__.py           # Package initialization
├── celery_app.py         # Main Celery app configuration with Kombu declarations
├── task_optimizer.py     # Priority routing and performance optimization
├── init_rabbitmq.py      # Standalone RabbitMQ initialization script
├── base_task.py          # Base task class with common functionality
├── langgraph_tasks.py    # LangGraph-specific tasks
├── phase4_tasks.py       # Phase 4 processing tasks
├── n8n_tasks.py          # n8n automation tasks
├── comfyui_tasks.py      # ComfyUI tasks
├── swarm_tasks.py        # Swarm coordination tasks
└── README.md             # This file
```

## Key Configuration Files

### celery_app.py

- Defines all exchanges and queues using Kombu
- Configures task routing
- Applies performance optimizations
- Logs configuration details on startup

### task_optimizer.py

- `TaskOptimizerConfig`: Configuration constants
- `TaskPriorityRouter`: Routes tasks to appropriate queues
- `TaskPerformanceMonitor`: Monitors task execution
- `TaskProfiler`: Profiles task performance
- `TaskRetryHandler`: Manages retry logic

### init_rabbitmq.py

Standalone script for RabbitMQ infrastructure management:

```bash
# Initialize all exchanges and queues
python -m app.tasks.init_rabbitmq

# Or import and use programmatically
from app.tasks.init_rabbitmq import (
    initialize_rabbitmq_infrastructure,
    verify_rabbitmq_infrastructure,
    get_infrastructure_status
)

# Initialize with custom retry settings
result = initialize_rabbitmq_infrastructure(max_retries=10, retry_delay=3)

# Verify infrastructure is healthy
health = verify_rabbitmq_infrastructure()
if health["healthy"]:
    print("All exchanges and queues exist")

# Get detailed status
print(get_infrastructure_status())
```

## Docker Compose Integration

The `docker-compose.yml` has been configured to:

1. Run `init_rabbitmq.py` before starting Celery workers
2. Wait for RabbitMQ health checks to pass
3. Ensure infrastructure exists before task processing begins

```yaml
celery-worker:
  command: sh -c "cd /app && python -m app.tasks.init_rabbitmq && python -m celery -A app.tasks.celery_app worker ..."
  depends_on:
    rabbitmq:
      condition: service_healthy

celery-beat:
  command: sh -c "cd /app && python -m app.tasks.init_rabbitmq && ..."
  depends_on:
    rabbitmq:
      condition: service_healthy
```

## Adding New Task Types

To add a new task type:

1. **Create task module** (e.g., `app/tasks/new_tasks.py`):

```python
from celery import shared_task
from app.tasks.task_optimizer import high_priority_task

@shared_task(bind=True)
@high_priority_task
def my_new_task(self, data):
    # Task implementation
    return result
```

2. **Update celery_app.py**:

```python
# Add to included_modules
included_modules.append('app.tasks.new_tasks')

# Add queue definition
new_queue = Queue(
    "newtype",
    exchange=tasks_exchange,
    routing_key="newtype",
    durable=True
)
all_queues.append(new_queue)

# Add route configuration
task_routes_config['app.tasks.new_tasks.*'] = {
    'queue': 'newtype',
    'exchange': 'tasks'
}
```

3. **Update init_rabbitmq.py**:

```python
# Add to QUEUES dictionary
QUEUES["newtype"] = {"exchange": "tasks", "routing_key": "newtype"}
```

4. **Restart services**:

```bash
docker-compose up -d celery-worker celery-beat
```

## Troubleshooting

### "no exchange 'X' in vhost '/'" Error

This error occurs when RabbitMQ infrastructure hasn't been created. Solutions:

1. **Run initialization script manually**:
   ```bash
   docker-compose exec celery-worker python -m app.tasks.init_rabbitmq
   ```

2. **Restart Celery services** (they run init on startup):
   ```bash
   docker-compose restart celery-worker celery-beat
   ```

3. **Verify RabbitMQ is running**:
   ```bash
   docker-compose ps rabbitmq
   docker-compose logs rabbitmq
   ```

### Priority Queues Not Working

1. **Verify queue arguments**:
   ```bash
   docker-compose exec rabbitmq rabbitmqctl list_queues name arguments
   ```
   Should show `x-max-priority: 10` for priority queues.

2. **Check task routing**:
   Enable DEBUG logging to see routing decisions:
   ```python
   # In celery_app.py or task_optimizer.py
   logging.getLogger('app.tasks.task_optimizer').setLevel(logging.DEBUG)
   ```

### Connection Issues

1. **Check broker URL**:
   ```bash
   docker-compose exec celery-worker env | grep CELERY_BROKER_URL
   ```

2. **Test RabbitMQ connectivity**:
   ```bash
   docker-compose exec celery-worker python -c "
   from kombu import Connection
   from app.config import Config
   with Connection(Config.CELERY_BROKER_URL) as conn:
       conn.connect()
       print('Connection successful')
   "
   ```

### Monitoring

Check infrastructure status:

```bash
docker-compose exec celery-worker python -c "
from app.tasks.init_rabbitmq import get_infrastructure_status
print(get_infrastructure_status())
"
```

## Environment Variables

| Variable            | Default                                      | Description                          |
|---------------------|----------------------------------------------|--------------------------------------|
| CELERY_BROKER_URL   | amqp://rabbitmq:rabbitmq_password@rabbitmq:5672// | RabbitMQ connection URL         |
| CELERY_RESULT_BACKEND | redis://redis:6379                         | Result storage backend               |
| CELERY_MAX_RETRIES  | 3                                            | Maximum task retry attempts          |
| CELERY_RETRY_DELAY  | 60                                           | Base retry delay in seconds          |
| CELERY_EXPONENTIAL_BACKOFF | true                                  | Enable exponential backoff           |
| CELERY_ENABLE_PROFILING | false                                  | Enable task profiling                |
| CELERY_PROFILE_THRESHOLD | 1.0                                    | Slow task threshold in seconds       |

## Best Practices

1. **Always use the initialization script** before starting workers
2. **Set appropriate priorities** for tasks based on urgency
3. **Monitor queue depths** to detect bottlenecks
4. **Use task-specific queues** for different workload types
5. **Enable profiling** in production to identify slow tasks
6. **Set reasonable retry policies** to avoid infinite loops

## Sequence Diagram

```mermaid
sequenceDiagram
    participant Task as Celery Task
    participant Router as TaskPriorityRouter
    participant Exchange as RabbitMQ Exchange
    participant Queue as Priority Queue
    participant Worker as Celery Worker

    Task->>Router: route_task()
    Router->>Router: _determine_priority()
    Router->>Exchange: Publish to 'priority' exchange
    Exchange->>Queue: Route to high/medium/low queue
    Queue->>Worker: Deliver task by priority
    Worker->>Worker: Execute task
```

## Further Reading

- [Celery Documentation](https://docs.celeryproject.org/)
- [Kombu Documentation](https://kombu.readthedocs.io/)
- [RabbitMQ Priority Queue](https://www.rabbitmq.com/priority.html)
- [Celery Routing Guide](https://docs.celeryproject.org/en/stable/userguide/routing.html)
