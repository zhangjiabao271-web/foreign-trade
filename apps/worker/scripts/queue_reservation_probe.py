"""Round-trip synthetic non-task messages only on the isolated queue probe broker.

Run before starting any worker on that broker, inside the network-none container
namespace documented in the acceptance ledger. Never point this at a business broker.
"""

import json
import os

from worker.app import app


def main():
    if (
        os.environ.get("QUEUE_RESERVATION_PROBE") != "isolated"
        or app.conf.broker_url != "redis://127.0.0.1:6379/0"
    ):
        raise RuntimeError("Isolated probe configuration required")
    expected = {"default", "email", "documents", "ai", "acquisition", "exports"}
    queues = app.amqp.Queues(app.conf.task_queues)
    if set(queues) != expected:
        raise RuntimeError("Reserved queue inventory differs")
    with app.connection_for_write() as connection:
        for name in sorted(expected):
            with connection.SimpleQueue(queues[name]) as queue:
                queue.queue.declare()
                # Redis removes empty list keys; passive existence checks reject empty queues.
                if queue.queue.queue_declare()[1] != 0:
                    raise RuntimeError("Broker contains unexpected messages")
                payload = {"kind": "queue-reservation-probe", "queue": name}
                queue.put(payload, serializer="json")
                message = queue.get(block=True, timeout=5)
                if message.payload != payload:
                    raise RuntimeError("Queue routing mismatch")
                message.ack()
                if queue.queue.queue_declare()[1] != 0:
                    raise RuntimeError("Unexpected messages remain")
    print(json.dumps({"queues": sorted(expected), "round_trips": 6, "business_tasks": 0}))


if __name__ == "__main__":
    main()
