import math
import os
import sys

RED = "\u001b[31m"
RESET = "\u001b[0m"
BOLD = "\u001b[1m"
BLACK_BG = "\u001b[40m"
ORANGE = "\u001b[38;5;208m"  # used for mentions


MAGIC = 240 ** (1 / 3)  # represents a third of the color cube for ANSI 256 color

if sys.platform == "win32":
    import msvcrt

    def setup_terminal():
        pass

    def next_char():
        return msvcrt.getch()

    def has_char():
        return msvcrt.kbhit()

else:
    import tty
    import select

    def setup_terminal():
        tty.setcbreak(sys.stdin)

    def next_char():
        return sys.stdin.read(1).encode()

    def has_char():
        return True


def convert_to_ansi(r, g, b):
    r_percent = r / 256
    g_percent = g / 256
    b_percent = b / 256

    cube_width = MAGIC

    ansi_r = r_percent * cube_width  # goes 0 - cube_width
    ansi_g = max(g_percent * cube_width - 1, 0)
    ansi_b = b_percent * cube_width

    final_code = min(
        16 + math.ceil(ansi_g + (ansi_b * cube_width) + (ansi_r * cube_width**2)), 256
    )

    return f"\u001b[38;5;{final_code}m"


def reset_screen():
    sys.stdout.flush()
    reset_cursor()


def horiz_line(columns) -> str:
    return linify("\u001b[1000D" + ("─" * columns), columns)


def change_win_title(title: str):
    sys.stdout.write(f"\u001b]0;{title}\x07")


def move_full_left():
    sys.stdout.write("\u001b[1000D")


def reset_cursor():
    sys.stdout.write("\u001b[?25l")
    sys.stdout.write("\u001b[1000D")
    sys.stdout.write("\u001b[1000A")


def enter_alternative_mode(term_size):
    """Enter alternative drawing mode"""
    sys.stdout.write(f"\u001b[?1049h\u001b[2J\u001b[0;{term_size.lines}r")
    sys.stdout.flush()


def enter_standard_mode():
    """Enter standard drawing mode"""
    sys.stdout.write(f"\u001b[?1049l")
    sys.stdout.flush()


def linify(text: str, columns):
    return f"{text}{" " * (columns-len(text))}"
