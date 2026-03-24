#!/usr/bin/env bash

if [ -z "${1}" ]; then
    echo "Usage: $0 <queue-name>"
    exit 1
fi

queue_name="${1}"

export LOCAL_QUEUE_NAME=${queue_name}
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

celery -A config.celery worker -l INFO --concurrency 1 -Q ${queue_name},celery -n ${queue_name}