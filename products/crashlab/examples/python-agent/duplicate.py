"""Controlled negative subject: changing operation keys duplicates the logical mutation."""

from crashlab_tools import PartialFailure, update_customer

for attempt in range(3):
    try:
        update_customer("operation-" + str(attempt))
    except PartialFailure:
        continue
    else:
        break
