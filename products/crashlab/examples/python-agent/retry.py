"""Preserve a logical operation key across a partial fake-service failure."""

from crashlab_tools import PartialFailure, update_customer

for attempt in range(3):
    try:
        update_customer("operation-1")
    except PartialFailure as error:
        if error.status_code != 503 or attempt == 2:
            raise
    else:
        break
