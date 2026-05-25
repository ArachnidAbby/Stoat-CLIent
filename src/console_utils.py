import math
import os
import sys

RED = "\u001b[31m"
RESET = "\u001b[0m"
BOLD = "\u001b[1m"
BLACK_BG = "\u001b[40m"
ORANGE = "\u001b[38;5;208m"  # used for mentions
REVERSE = "\u001b[7m"


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
        return next_char() == 91 and next_char() == 91

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


def is_ansi_code(text: str, *, offset=0) -> int:
    """Returns 0 if this text does not start with an ANSI code
    otherwise- returns the length of the ansi code"""
    if text[offset : offset + 2] != "\u001b[":
        return 0
    for i in range(2 + offset, len(text), 2):
        if not text[i].isalpha() and not (text[i] == ";" and text[i + 1].isnumeric()):
            return 0
        if text[i].isalpha():
            return i
    return 0


def remove_ansi_codes(text: str):
    while (i := text.find("\u001b[")) != -1:
        if code := is_ansi_code(text, offset=i):
            text = text[0:i] + text[i + code :]
    return text


def visible_len(text: str):
    """Get the length of the text- minus the size of invisible ANSI codes"""
    offset = 0
    i = 0
    while (i := text.find("\u001b[", i)) != -1:
        if code := is_ansi_code(text, offset=i):
            offset += code
            i += code
            continue
        i += 1
    return len(text) - offset


def get_visible_index(text: str, idx: int) -> int:
    """Get the index of a visible section, -1 if out of bounds"""
    i = 0
    while i < idx:
        if code := is_ansi_code(text, offset=i):
            i += code
            continue
        i += 1
        if i >= len(text):
            return idx
    return i


def break_and_wrap_text(text: str, width: int) -> list[str]:
    """Break text by lines and do line wrapping. Does this purely by visible length (skipping ahead of ANSI codes)"""
    lines = text.split("\n")
    output = []
    while len(lines) > 0:
        line = lines.pop(0)
        if visible_len(line) > width:
            output.append(line[0 : get_visible_index(line, width)])
            lines.insert(
                0, line[get_visible_index(line, width) :]
            )  # insert rest of line back into input buffer to be processed
            continue
        output.append(line)
    return output


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
    return f"{text}{" " * (columns-visible_len(text))}"
