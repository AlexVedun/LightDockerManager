def reload_and_get_attrs(obj):
    """Refreshes a docker-py model object and returns its attrs dict.

    Meant to run on a background thread (via workers.task_worker.run_task)
    since .reload() is a blocking Docker API call.
    """
    obj.reload()
    return obj.attrs
