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

    BACKSPACE = 8
    LEFT_ARROW = 75
    RIGHT_ARROW = 77
    UP_ARROW = 72
    DOWN_ARROW = 80
    PG_UP = 73
    PG_DOWN = 81
    ENTER = 13

    def arrow_pressed(key: int):
        return key == 224

    def setup_terminal():
        pass

    def next_char():
        return msvcrt.getch()

    def has_char():
        return msvcrt.kbhit()

else:
    import tty
    import select
    import termios
    import atexit

    BACKSPACE = 127
    LEFT_ARROW = 68
    RIGHT_ARROW = 67
    UP_ARROW = 65
    DOWN_ARROW = 66
    PG_UP = 53
    PG_DOWN = 54
    ENTER = 10

    def arrow_pressed(key: int):
        if key != 27:
            return False
        return next_char() == 91

    def enable_echo(fd, enabled):
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(fd)

        if enabled:
            lflag |= termios.ECHO
        else:
            lflag &= ~termios.ECHO

        new_attr = [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
        termios.tcsetattr(fd, termios.TCSANOW, new_attr)

    def setup_terminal():
        tty.setcbreak(sys.stdin)
        enable_echo(sys.stdin.fileno(), False)
        atexit.register(enable_echo, sys.stdin.fileno(), True)

    def next_char():
        return sys.stdin.read(1).encode()

    def has_char():
        return select.select([sys.stdin], [], [], 0)[0]


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
