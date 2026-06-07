import datetime


def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_text(path: str, text: str) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")


def print_section(title: str, body: str) -> None:
    divider = "=" * max(20, len(title) + 4)
    print(divider)
    print(title)
    print(divider)
    print(body)
    print()
