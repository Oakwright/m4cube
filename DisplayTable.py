from adafruit_display_text import label
import displayio
import terminalio
from adafruit_progressbar.horizontalprogressbar import (
    HorizontalProgressBar,
    HorizontalFillDirection,
)


def build_line(text, min_val, max_val, start_val):
    line_text = label.Label(terminalio.FONT, text=text, x=0, y=5)
    line_bar = HorizontalProgressBar(
        (108, 0), (20, 9), direction=HorizontalFillDirection.LEFT_TO_RIGHT,
        min_value=min_val,
        max_value=max_val,
        value=start_val
    )
    return line_text, line_bar


class DisplayTable:
    _canvas = displayio.Group()
    _lines = 0
    spacing = 9

    def __init__(self, inner_displayscreen):
        inner_displayscreen.show(self._canvas)
        pass

    def add_line(self, start_text, min_val, max_val, start_val):
        line_text, line_progressbar = build_line(start_text, min_val, max_val, start_val)

        line = displayio.Group()
        line.y = self.spacing * self._lines
        self._lines += 1
        line.append(line_text)
        line.append(line_progressbar)
        self._canvas.append(line)
        return line_text, line_progressbar

    @property
    def canvas(self):
        return self._canvas
