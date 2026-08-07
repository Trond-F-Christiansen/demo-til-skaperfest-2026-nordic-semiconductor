"""Quiz game.

Multiple-choice quiz that follows the same contract as snake.run: it is
launched from the menu (main.py) as run(screen, clock, controller) and returns
the run's score (number of correct answers). main.py then shows the shared
game-over screen ("Score: N", Restart / Main Menu), so nothing extra is needed
here for that.

The pot of questions is @ref QUESTIONS below; each run draws @ref
QUESTIONS_PER_RUN of them at random (no repeats within a run), so consecutive
plays differ. Grow the pot by adding entries to that list.

Layout: the question prompt is drawn across the top; the answer options are
stacked top -> down below it. Questions are answered one at a time in order.
Picking an answer holds the question on screen for @ref REVEAL_SECONDS with the
correct option filled green -- and the pick filled red when it was wrong -- then
moves on by itself. When the last question is answered, run() returns the score.

Input is either the keyboard or the finger counter: the finger_digits board
sends a settled digit (0-5) over BLE, which is turned into the matching number
key here, so N fingers picks option N exactly as pressing N would:
    1 .. 5        pick that option and advance
    UP / DOWN     move the highlight,  ENTER / SPACE pick it
A held-up hand produces one digit, not a stream: the firmware only reports after
five identical predictions in a row. Digits with no matching option (0, or a
count above the option count) are ignored.
Run indirectly via `python main.py`; the font loads with a path relative to the
current directory, so run from the game/ folder.
"""

import random
from collections import namedtuple

import pygame

import ui

# How many of QUESTIONS one run asks: they are drawn at random without repeats,
# so consecutive runs differ. Raise or lower freely; a value at or above the pot
# size just asks every question once, in a random order.
QUESTIONS_PER_RUN = 10

# How long an answered question stays on screen with the correct option marked
# green before the next one replaces it. Long enough to read which answer was
# right; short enough not to stall a run of ten. See _reveal().
REVEAL_SECONDS = 2.0

# A single quiz question. `answer` is the 0-based index into `options`.
Question = namedtuple("Question", "prompt options answer")

# The question pot: add as many as you like here, that is the only change
# needed. Keep it to 5 options at most -- the finger counter only shows 1-5, so
# a sixth option could never be picked -- and vary where the correct one sits.
QUESTIONS = [
    Question("Hvor mange mager har en ku?",
             ["2", "1", "4", "3", "Ingen, lurespørsmål:P"], 2),
    Question("Hvilken temperatur viser nøyaktig det samme i både Celsius og Fahrenheit?",
             ["-40 grader", "0 grader", "32 grader", "-17 grader", "-100 grader"], 0),
    Question("Hva betyr ordet «idiot» opprinnelig på gresk?",
             ["en person som ikke kan lese", "en person uten far", "en person som snakker for mye", "en person som er født utenfor byen", "en person som ikke er interessert i politikk"], 4),
    Question("Hvilket dyr sover med det ene øyet åpent?",
             ["struts", "delfin", "ugle", "kamel", "flodhest"], 1),
    Question("Hva er det største dyret som lever på land?",
             ["neshorn", "giraff", "flodhest", "savanneelefanten", "indisk elefant"], 3),
    Question("Hva er rosiner laget av?",
             ["plommer", "tranebær", "fiken", "dadler", "druer"], 4),
    Question("Hvor mange farger har regnbuen?",
             ["5", "7", "3", "9", "6"], 1),
    Question("Hvor mange av hvert dyr tok Moses med på arken?",
             ["2", "14", "1", "0", "7"], 3),
    Question("Hva kan du holde i venstre hånd, men aldri i høyre hånd?",
             ["høyre albue", "venstre albue", "høyre hånd", "venstre kne", "egen skygge"], 0),
    Question("Hvor mange egg tilsvarer et strutseegg",
             ["ca. 12 egg", "ca. 100 egg", "ca. 24 egg", "ca. 6 egg", "ca. 40 egg"], 2),
    Question("Hvilket dyr har fingeravtrykk som er nesten identiske med menneskers?",
             ["gorilla", "koala", "sjimpanse", "vaskebjørn", "orangutang"], 1),
    Question("Hvor raskt er et nys?",
             ["opptil 10km/t", "opptil 60km/t", "opptil 120km/t", "opptil 160km/t", "opptil 220km/t"], 3),
    Question("Hva heter Norges lengste fjord?",
             ["oslofjorden", "hardangerfjorden", "geirangerfjorden", "sognefjorden", "trondheimsfjorden"], 3),
    Question("Hva het Norges første kvinnelige statsminister?",
             ["Anne Enger", "Erna Solberg", "Gro Harlem Brundtland", "Siv Jensen", "Kirsti Kolle Grøndahl"], 2),
    Question("Hvilket land har flest tidssoner?",
             ["Frankrike", "Russland", "USA", "Kina", "Australia"], 0),
    Question("Hva er verdens største ørken?",
             ["Gobi", "Sahara", "Kalahari", "Antarktis", "Arabiske ørken"], 3),
    Question("Hvilket land har lengst kystlinje i verden?",
             ["Australia", "Norge", "Canada", "Russland", "Indonesia"], 2),
    Question("Hvor mange strenger har en fiolin?",
             ["fire", "seks", "to", "tre", "fem"], 0),
    Question("Hvor mange måneder i året har 31 dager?",
             ["seks", "tolv", "åtte", "fem", "syv"], 4),
    Question("Hva kalles vitenskapen som studerer vær og klima?",
             ["oseanografi", "meteorologi", "geologi", "astronomi", "seismologi"], 1),
    Question("Hvilken fugl ble valgt til Norges nasjonalfugl i 1963?",
             ["fossekall", "havørn", "lundefugl", "ravn", "kjøttmeis"], 0),
    Question('Hvem skrev eventyret om "Den stygge andungen"?',
             ["Astrid Lindgren", "Brødrene Grimm", "Asbjørnsen og Moe", "H. C. Andersen", "Thorbjørn Egner"], 3),
    Question("Hvilket metall er flytende ved romtemperatur?",
             ["tinn", "kvikksølv", "bly", "aluminium", "natrium"], 1),
    Question("Hvilken farge har solen, fysisk sett?",
             ["oransje", "gul", "hvit", "rød", "blå"], 2),
    Question("Hvor mange spillere er det på hvert lag i strandvolleyball?",
             ["seks", "fire", "én", "tre", "to"], 4),
    Question("Hvor mange ganger kan tallet 1 trekkes fra 1111?",
             ["fire ganger", "1111 ganger", "en gang", "elleve ganger", "uendelig mange ganger"], 2),
    Question("Hvor høy er Erling Braut Haaland?",
             ["1,91 m", "1,92 m", "1,93 m", "1,94 m", "1,95 m"], 4),
    Question("Hva står VG for?",
             ["Verdens Gangart", "Verdens Gåte", "Vårt Grunnlag", "Verdens Gang", "Verdens Grunnlag"], 3),
    Question("Hva er en NPU?",
             ["Null Peiling, (U)kis", "Nordic Processing Unit", "Node Power Unit", "Neural Processing Unit"], 3),
    Question("Hva er favorittfargen til Selma?",
             ["rød", "svart", "rosa", "grønn"], 3),
    Question("Hva er favorittfargen til Maria?",
             ["rød", "blå", "rosa", "grønn"], 1),
    Question("Hva er favorittfargen til Nicholas?",
             ["rød", "svart", "rosa", "grønn"], 1),
    Question("Hva heter statsministeren i Storbritannia?",
             ["Keir Starmer", "John Hopkins", "Andy Burnham", "Connor Man"], 2),
]


def pick_questions(pot=QUESTIONS, count=QUESTIONS_PER_RUN):
    """Draw `count` questions from `pot` at random, without repeats.

    @return a new list; the whole pot (shuffled) if it holds fewer than `count`.
    """
    return random.sample(pot, min(count, len(pot)))


def _draw_question(screen, question, index, total, assets, selected, reveal=False):
    """Draw one frame of a question.

    @param selected  the option the player is on, outlined while answering and
                     kept as the record of their pick during the reveal.
    @param reveal    False while the question is open: `selected` is outlined in
                     ui.HILITE_BG. True once it has been answered: the correct
                     option is filled green, and `selected` is filled red when
                     it was not the correct one.
    """
    prompt_font, option_font, hint_font, small_font, finger_imgs = assets
    width, height = screen.get_size()
    cx = width // 2
    margin = 40

    prompt_lines = ui.wrap_text(question.prompt, prompt_font, width - 2 * margin)
    line_h = prompt_font.get_linesize()

    screen.fill(ui.BG_COLOR)

    # Progress line, then the prompt, across the top.
    progress = small_font.render(f"Question {index + 1} / {total}", True, ui.TEXT_COLOR)
    screen.blit(progress, progress.get_rect(center=(cx, 50)))

    prompt_top = 110
    for i, line in enumerate(prompt_lines):
        surf = prompt_font.render(line, True, ui.TEXT_COLOR)
        screen.blit(surf, surf.get_rect(center=(cx, prompt_top + i * line_h)))

    # Options stacked top -> down: text left-aligned, and the matching
    # finger graphic (one/two/three/four) right-aligned on the same row.
    left_x = margin
    right_x = width - margin
    options_top = prompt_top + len(prompt_lines) * line_h + 90
    gap = 112
    for i, text in enumerate(question.options):
        row_y = options_top + i * gap

        if reveal:
            if i == question.answer:
                box_color = ui.CORRECT_BG
            elif i == selected:
                box_color = ui.WRONG_BG
            else:
                box_color = None
        else:
            box_color = ui.HILITE_BG if i == selected else None

        img = finger_imgs[i] if i < len(finger_imgs) else None
        img_rect = img.get_rect(midright=(right_x, row_y)) if img else None

        # Options come from questions.md and can be long ("en person som
        # ikke er interessert i politikk"), so squeeze any that would
        # otherwise run into the finger graphic on the right.
        text_surf = option_font.render(text, True, ui.TEXT_COLOR)
        room = (img_rect.left - 24 if img_rect else right_x) - left_x
        if text_surf.get_width() > room:
            scale = room / text_surf.get_width()
            text_surf = pygame.transform.smoothscale(
                text_surf,
                (room, max(1, round(text_surf.get_height() * scale))))
        text_rect = text_surf.get_rect(midleft=(left_x, row_y))

        if box_color is not None:
            tops = [text_rect.top] + ([img_rect.top] if img_rect else [])
            bottoms = [text_rect.bottom] + ([img_rect.bottom] if img_rect else [])
            top = min(tops) - 12
            box = pygame.Rect(left_x - 24, top,
                              (right_x - left_x) + 48, max(bottoms) + 12 - top)
            pygame.draw.rect(screen, box_color, box, border_radius=10)
            pygame.draw.rect(screen, ui.TEXT_COLOR, box, 3, border_radius=10)

        screen.blit(text_surf, text_rect)
        if img:
            screen.blit(img, img_rect)

    # While answering, the hint says how to answer. During the reveal it would
    # be a lie -- input is dropped -- so it reports the outcome instead.
    if reveal:
        hint_text = "Correct!" if selected == question.answer else "The green one was right"
    else:
        hint_text = "Show 1-5 fingers"
    hint = hint_font.render(hint_text, True, ui.TEXT_COLOR)
    screen.blit(hint, hint.get_rect(center=(cx, height - 60)))


def _reveal(screen, clock, controller, question, index, total, assets, chosen):
    """Hold an answered question on screen, correct option green, for REVEAL_SECONDS.

    Input is dropped for the whole pause. The finger counter keeps reporting for
    as long as a hand is up, so without this a digit held through the pause would
    answer the next question the instant it appeared.

    @return True when the pause is over, False if the window was closed.
    """
    deadline = pygame.time.get_ticks() + int(REVEAL_SECONDS * 1000)

    while pygame.time.get_ticks() < deadline:
        controller.drain()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

        _draw_question(screen, question, index, total, assets, chosen, reveal=True)
        pygame.display.update()
        clock.tick(60)

    return True


def _ask(screen, clock, controller, question, index, total, assets):
    """Show one question, then reveal the answer, and return the chosen option.

    @return the selected 0-based option index, or None if the window was closed.
    """
    # K_1..K_9 -> option 0..8 (a finger count of N picks option N), capped to
    # the options. K_0 is deliberately absent: showing zero fingers picks
    # nothing, so a "ZERO" prediction falls through and is ignored.
    digit_keys = {getattr(pygame, f"K_{n}"): n - 1 for n in range(1, 10)}

    selected = 0
    while True:
        # Directions mean nothing in the quiz; drop them so they don't pile up.
        while not controller.directions.empty():
            controller.directions.get()

        # Turn each finger digit into the number key the player would have
        # pressed, then let the normal keyboard handling below do the rest.
        events = list(pygame.event.get())
        while not controller.digits.empty():
            digit = controller.digits.get()
            key = getattr(pygame, f"K_{digit}", None)
            if key is not None:
                events.append(pygame.event.Event(pygame.KEYDOWN, key=key))

        for event in events:
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN:
                choice = None
                if event.key in digit_keys and digit_keys[event.key] < len(question.options):
                    choice = digit_keys[event.key]
                elif event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(question.options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(question.options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    choice = selected

                # Answered: show which option was right before moving on. The
                # window can still be closed during that pause, which reads the
                # same as closing it mid-question.
                if choice is not None:
                    if not _reveal(screen, clock, controller, question,
                                   index, total, assets, choice):
                        return None
                    return choice

        _draw_question(screen, question, index, total, assets, selected)
        pygame.display.update()
        clock.tick(60)


def run(screen, clock, controller):
    """Ask QUESTIONS_PER_RUN random questions, returning the number answered right.

    The questions are drawn fresh from the pot on every call, so "Restart" on
    the game-over screen gives a different set rather than a replay.

    @return the score (int), or None if the player closed the window.
    """
    # Finger-count graphics, one per option (option i -> i+1 fingers), scaled
    # to a common height while keeping their aspect ratio. Five of them, since
    # questions.md allows up to MAX_OPTIONS options.
    finger_h = 84
    finger_imgs = []
    for name in ("one", "shaka", "rocknroll", "four", "five"):
        img = pygame.image.load(f'Graphics/{name}.png').convert_alpha()
        w, h = img.get_size()
        finger_imgs.append(
            pygame.transform.smoothscale(img, (round(w * finger_h / h), finger_h)))

    assets = (
        ui.font(40),   # prompt
        ui.font(36),   # options
        ui.font(24),   # hint
        ui.font(28),   # progress
        finger_imgs,
    )

    # Drop anything the controller queued before the quiz started, so a digit
    # shown while the menu was up doesn't answer the first question.
    controller.drain()

    questions = pick_questions()

    score = 0
    total = len(questions)
    for index, question in enumerate(questions):
        choice = _ask(screen, clock, controller, question, index, total, assets)
        if choice is None:  # window closed mid-quiz
            return None
        if choice == question.answer:
            score += 1
    controller.send_score("quiz", score)
    return score

