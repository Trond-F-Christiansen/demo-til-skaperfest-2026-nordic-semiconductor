"""Quiz game.

Multiple-choice quiz that follows the same contract as snake.run: it is
launched from the menu (main.py) as run(screen, clock, controller) and returns
the run's score (number of correct answers). main.py then shows the shared
game-over screen ("Score: N", Restart / Main Menu), so nothing extra is needed
here for that.

Layout: the question prompt is drawn across the top; the answer options are
stacked top -> down below it. Questions are answered one at a time in order;
picking an answer advances to the next question. When the last question is
answered, run() returns the score.

Input is keyboard for now (the planned controller input is a finger counter:
1-4 fingers -> option 1-4, which maps straight onto the number keys):
    1 .. N        pick that option and advance
    UP / DOWN     move the highlight,  ENTER / SPACE pick it
Run indirectly via `python main.py`; the font loads with a path relative to the
current directory, so run from the game/ folder.
"""

from collections import namedtuple

import pygame

FONT_PATH = 'Font/PoetsenOne-Regular.ttf'

BG_COLOR = (100, 0, 255)
TEXT_COLOR = (56, 64, 12)
HILITE_BG = (10, 100, 150)

# A single quiz question. `answer` is the 0-based index into `options`.
Question = namedtuple("Question", "prompt options answer")

# Questions ported from the console draft; the answer index matches the draft's
# 1-based correct answer (e.g. '4' -> index 3). The draft's 5th prompt (the
# animal one) wasn't wired in; add it here the same way when you want it.
QUESTIONS = [
    Question("questions with four answer options?",
             ["1", "2", "3", "4"], 0),
    Question("hva er favorittfargen til Selma?",
             ["rød", "svart", "rosa", "grønn"], 3),
    Question("hva er favorittfargen til Maria?",
             ["rød", "blå", "rosa", "grønn"], 2),
    Question("hva er favorittfargen til Selma?",
             ["rød", "svart", "rosa", "grønn"], 3),
]


def _wrap_text(text, font, max_width):
    """Break `text` into lines that each fit within `max_width` pixels."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _ask(screen, clock, controller, question, index, total, fonts):
    """Show one question and return the chosen option index.

    @return the selected 0-based option index, or None if the window was closed.
    """
    prompt_font, option_font, hint_font, small_font = fonts
    width, height = screen.get_size()
    cx = width // 2
    margin = 40

    prompt_lines = _wrap_text(question.prompt, prompt_font, width - 2 * margin)
    line_h = prompt_font.get_linesize()

    # K_1..K_9 -> option 0..8 (finger-count stand-in), capped to the options.
    digit_keys = {getattr(pygame, f"K_{n}"): n - 1 for n in range(1, 10)}

    selected = 0
    while True:
        # HOOK: controller directions are dropped for now. When the finger
        # counter lands, translate a count here into the chosen option index.
        while not controller.directions.empty():
            controller.directions.get()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                if event.key in digit_keys and digit_keys[event.key] < len(question.options):
                    return digit_keys[event.key]
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(question.options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(question.options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return selected

        # ---- draw ----
        screen.fill(BG_COLOR)

        # Progress line, then the prompt, across the top.
        progress = small_font.render(f"Question {index + 1} / {total}", True, TEXT_COLOR)
        screen.blit(progress, progress.get_rect(center=(cx, 50)))

        prompt_top = 110
        for i, line in enumerate(prompt_lines):
            surf = prompt_font.render(line, True, TEXT_COLOR)
            screen.blit(surf, surf.get_rect(center=(cx, prompt_top + i * line_h)))

        # Options stacked top -> down, starting below the prompt block.
        options_top = prompt_top + len(prompt_lines) * line_h + 90
        gap = 90
        for i, text in enumerate(question.options):
            is_sel = (i == selected)
            surf = option_font.render(f"{i + 1}.  {text}", True, TEXT_COLOR)
            rect = surf.get_rect(center=(cx, options_top + i * gap))
            if is_sel:
                box = rect.inflate(80, 26)
                pygame.draw.rect(screen, HILITE_BG, box, border_radius=8)
                pygame.draw.rect(screen, TEXT_COLOR, box, 3, border_radius=8)
            screen.blit(surf, rect)

        hint = hint_font.render(
            f"Press 1-{len(question.options)}    or    UP / DOWN + ENTER",
            True, TEXT_COLOR)
        screen.blit(hint, hint.get_rect(center=(cx, height - 60)))

        pygame.display.update()
        clock.tick(60)


def run(screen, clock, controller):
    """Ask every question in order and return the number answered correctly.

    @return the score (int), or None if the player closed the window.
    """
    fonts = (
        pygame.font.Font(FONT_PATH, 40),  # prompt
        pygame.font.Font(FONT_PATH, 36),  # options
        pygame.font.Font(FONT_PATH, 24),  # hint
        pygame.font.Font(FONT_PATH, 28),  # progress
    )

    # Drop anything the controller queued before the quiz started.
    while not controller.directions.empty():
        controller.directions.get()

    score = 0
    total = len(QUESTIONS)
    for index, question in enumerate(QUESTIONS):
        choice = _ask(screen, clock, controller, question, index, total, fonts)
        if choice is None:  # window closed mid-quiz
            return None
        if choice == question.answer:
            score += 1
    return score
