import sys


def reset_screen():
    sys.stdout.flush()
    sys.stdout.write(u"\u001b[1000D")
    sys.stdout.write(u"\u001b[1000A")


def write_horiz_line(columns) -> str:
    return linify("\u001b[1000D"+ ("─"*columns) + "\n", columns)

def change_win_title(title: str):
    sys.stdout.write(f'\u001b]0;{title}\x07')

def move_full_left():
    sys.stdout.write(u"\u001b[1000D")

def linify(text: str, columns):
    return f"{text}{" " * (columns-len(text))}"