def human_size(num_bytes):
    if num_bytes is None:
        return "—"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def short_timestamp(value):
    if not value:
        return "—"
    return str(value).split(".")[0].replace("T", " ")


def summarize_prune_result(result):
    parts = []
    space = result.get("SpaceReclaimed")
    if space is not None:
        parts.append(f"Освобождено места: {human_size(space)}")

    deleted_key = next((key for key in result if key.endswith("Deleted")), None)
    if deleted_key:
        deleted = result.get(deleted_key) or []
        if deleted:
            parts.append(f"Удалено объектов: {len(deleted)}")

    return "\n".join(parts) if parts else "Нечего удалять."
