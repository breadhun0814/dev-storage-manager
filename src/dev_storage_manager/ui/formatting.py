"""Display units only: underlying byte totals and numeric sort keys stay exact."""


def format_size(value: int) -> str:
    magnitude = abs(value)
    sign = "−" if value < 0 else ""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if magnitude < 1024 or unit == "PB":
            number = f"{magnitude:,}" if unit == "B" else f"{magnitude:,.1f}"
            return f"{sign}{number} {unit}"
        magnitude /= 1024


def exact_size(value: int) -> str:
    return f"{format_size(value)} · {value:,} B"
