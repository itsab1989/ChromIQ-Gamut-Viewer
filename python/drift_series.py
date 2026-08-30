"""One device, profiled again and again, and what moved between the times.

WHAT THIS ANSWERS THAT THE PAIR COMPARISON DOES NOT. ``ti3gamut.compare_profiles``
holds two profiles side by side. That is the right tool for "is my new profile
different from my old one". It is the wrong tool for "has my scanner been
drifting", because two readings cannot tell a steady creep from a single bad
day, and the difference between those two decides what you do about it.

TWO SERIES, AND BOTH ARE NEEDED. Measured on six profiles of one imaginary
scanner drifting evenly:

    against the FIRST     0.55  1.08  1.68  2.19  2.67     <- climbs
    against the PREVIOUS  0.55  0.53  0.60  0.50  0.49     <- flat

Read only the second and the answer is "nothing is happening, every year looks
like the last". Read only the first and a steady creep cannot be told from one
bad year followed by four quiet ones. They disagree BY DESIGN, and a tool that
showed one of them would mislead in one of the two directions. So both are
computed, always, and drawn together.

WHAT IT DOES NOT MEASURE, and this gets WORSE with a series rather than better.
Each profile records one day's measurements of one chart. Six profiles is six
charts, each with its own fade. A line climbing steadily is as consistent with
six charts ageing as with one scanner drifting, and nothing in the arithmetic
can separate them. A trend line is exactly the kind of picture people trust
more than they should, so the caller is expected to say this where the line is,
not only in a help panel somewhere.

Needs nothing installed: profiles are read by ``icc_read`` in this process.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

#: Below this, in ΔE2000, most people would not notice the difference side by
#: side. ⚠ NOT "nobody can see it", which is what this said: Paravina et al.
#: 2015 put 50:50 perceptibility at 0.8 ΔE00 as a psychometric MIDPOINT, so at
#: 1.0 a good half of observers do see it. The threshold is a sound trade
#: convention and is unchanged; only the claim about eyes is corrected.
INVISIBLE = 1.0

#: Above this it is hard to miss. Between the two, a careful eye on a smooth
#: gradient. The same two numbers the pair comparison uses, deliberately --
#: one vocabulary across the application, not two.
OBVIOUS = 3.0

#: Dates a great many profiles share because a build stamped them rather than a
#: measurement. Ordering by a date like this invents a history, so it is
#: treated as no date at all.
#:
#: NOT GUESSWORK: measured on this machine, six of the profiles macOS ships
#: carry 2022-01-01 00:00:00 exactly -- Display P3, DCI(P3) RGB and ACESCG
#: Linear among them. A midnight-on-the-first is a stamp, not a moment somebody
#: measured something.
SUSPICIOUS_DATES = {(2022, 1, 1, 0, 0, 0)}


@dataclass(frozen=True)
class Entry:
    """One profile in the run, and what could be learned about it."""
    path: Path
    when: "tuple | None"        # (y, m, d, H, M, S) from the header, or None
    space: str                  # RGB, CMYK …
    table: str                  # A2B1, A2B0 or matrix
    trouble: str = ""           # why it could not be used, if it could not

    @property
    def name(self) -> str:
        return self.path.stem

    @property
    def usable(self) -> bool:
        return not self.trouble

    @property
    def dated(self) -> str:
        """The date as somebody would write it, or a plain admission."""
        if self.when is None:
            return "no usable date"
        return "{:04d}-{:02d}-{:02d}".format(*self.when[:3])


@dataclass(frozen=True)
class Step:
    """One comparison in a series: what moved between two of them."""
    before: str
    after: str
    worst: float
    average: float
    over_one: int
    of: int
    before_on: str = ""         # the dates, when the profiles carry them
    after_on: str = ""

    @property
    def spans(self) -> str:
        """The step named the way a reader can act on it.

        A JUMP IS ONLY USEFUL IF IT COMES WITH A WHEN. Telling somebody the
        largest step is "y2 to y3" invites the question the sentence was
        supposed to answer -- they then have to go and work out when y2 and y3
        were made. Where the profiles carry dates, this says so outright, and
        falls back to the names when they do not.
        """
        if self.before_on and self.after_on:
            return (f"{self.before} to {self.after} "
                    f"({self.before_on} to {self.after_on})")
        return f"{self.before} to {self.after}"


@dataclass(frozen=True)
class Run:
    """A whole run of profiles, both series, and everything wrong with it."""
    entries: list = field(default_factory=list)
    since_first: list = field(default_factory=list)
    since_previous: list = field(default_factory=list)
    ordered_by: str = ""        # "date" or "the order you added them"
    complaints: list = field(default_factory=list)

    @property
    def usable(self) -> list:
        return [e for e in self.entries if e.usable]

    @property
    def total(self) -> float:
        """How far it has moved altogether, first to last."""
        return self.since_first[-1].worst if self.since_first else 0.0

    @property
    def steady(self) -> bool:
        """Whether each step is about the size of every other step.

        THE QUESTION THE TWO SERIES EXIST TO SEPARATE. Even steps mean the
        device is creeping and will keep creeping; one big step among small
        ones means something HAPPENED, on a date the reader can now go and
        look up. The advice differs completely, so the picture has to make
        which one it is unmissable.
        """
        steps = [s.worst for s in self.since_previous]
        if len(steps) < 2:
            return True
        biggest, smallest = max(steps), min(steps)
        if biggest <= INVISIBLE:
            return True                     # nothing is moving at all
        return biggest <= 2.0 * max(smallest, 0.01)

    @property
    def worst_step(self) -> "Step | None":
        """The single biggest jump, which is the one worth a date."""
        return max(self.since_previous, key=lambda s: s.worst,
                   default=None)

    @property
    def furthest(self) -> "Step | None":
        """The point at which it was FURTHEST from where it started.

        Not the same as where it ended, and the difference is the whole
        reason this exists.
        """
        return max(self.since_first, key=lambda s: s.worst, default=None)

    @property
    def came_back(self) -> bool:
        """True when it wandered off and returned close to where it began.

        ASKED BY BASTI, and it turned out to be the case this whole feature
        was most likely to lie about: "what if a profile drifts in one
        direction for two years and then back the other, matching the initial
        one again -- would this be visible?"

        MEASURED, on five profiles built to do exactly that:

            since the FIRST    2.60, 5.39, 2.60, 0.54
            since the ONE BEFORE   2.60, 2.67, 2.67, 2.08

        The PICTURE shows it plainly -- the cumulative line arches up and
        comes back while the step line stays flat, and two lines disagreeing
        in that particular way mean one thing only. The WORDS did not: the
        verdict read the ends and printed "Nothing has moved that anybody
        could see", of a device that had been ΔE 5.39 away in 2021 and has
        since returned. Anything printed that year was visibly wrong, and
        that sentence is saved into the page and the table, where it outlives
        the chart that would have corrected it.

        THE TEST IS AGAINST THE THRESHOLD OF VISIBILITY, not a ratio. What
        makes this worth saying is not that the excursion was some multiple
        of the ending -- it is that somebody could SEE the difference while it
        lasted and cannot see one now. So: it went at least as far as the
        point where a difference becomes visible, and it came back by at
        least that much again.
        """
        peak = self.furthest
        if peak is None or len(self.since_first) < 2:
            return False
        return peak.worst >= INVISIBLE and (peak.worst - self.total) >= INVISIBLE


def read_created(path) -> "tuple | None":
    """When the profile says it was made, from the ICC header.

    Bytes 24 to 36 hold the creation date as six big-endian uint16, in the
    order year, month, day, hour, minute, second. Present and real on every
    profile checked -- but see SUSPICIOUS_DATES: a build stamp is not a
    measurement, and ordering a run by one would invent the history the reader
    is trying to read.
    """
    try:
        raw = Path(path).read_bytes()[:36]
    except OSError:
        return None
    if len(raw) < 36:
        return None
    when = struct.unpack(">6H", raw[24:36])
    if when[0] == 0:                        # the specification's "not set"
        return None
    if not (1 <= when[1] <= 12 and 1 <= when[2] <= 31):
        return None                         # a date that is not a date
    if when in SUSPICIOUS_DATES:
        return None
    return when


def inspect(path) -> Entry:
    """Everything worth knowing about one profile, without judging the run.

    NEVER RAISES. A run of eight profiles with one bad file in it should show
    the seven and name the eighth, not refuse the lot -- the reader can then
    go and find out what is wrong with that one file rather than with their
    whole afternoon.
    """
    import icc_read

    path = Path(path)
    try:
        head = icc_read.describe(path)
        table = icc_read.which_table(path)
    except Exception as why:                 # noqa: BLE001
        return Entry(path=path, when=None, space="", table="",
                     trouble=str(why))
    return Entry(path=path, when=read_created(path), space=head["space"],
                 table=table)


def order(entries) -> tuple:
    """The run in the order it happened, and how that order was decided.

    BY DATE WHEN EVERY PROFILE HAS ONE, because that is the truth of it and
    the reader should not have to sort their own files. By the order they were
    added when any profile does not, because a run sorted by date with two
    undated files dropped somewhere arbitrary is worse than one that admits it
    is going on what it was told: the picture would look authoritative and be
    partly invented.
    """
    usable = [e for e in entries if e.usable]
    if usable and all(e.when is not None for e in usable):
        # Sorted on the date and then the name, so two profiles made in the
        # same minute come out in a stable order rather than a random one.
        return (sorted(entries, key=lambda e: (e.when or (0,) * 6, e.name)),
                "date")
    return list(entries), "the order you added them"


def build(paths, *, steps: int = 9) -> Run:
    """The whole run: both series, and every complaint worth making.

    *steps* is per channel, so 9 means 729 colours asked of each profile. The
    arithmetic is cheap -- ten comparisons measured at under a hundredth of a
    second -- so the grid is the same one the pair comparison uses and there is
    nothing to gain by coarsening it.
    """
    from ti3gamut import compare_profiles

    entries = [inspect(p) for p in paths]
    entries, how = order(entries)
    complaints = []

    for bad in (e for e in entries if not e.usable):
        complaints.append(f"{bad.path.name} could not be read: {bad.trouble}")

    good = [e for e in entries if e.usable]
    if len(good) < 2:
        complaints.append(
            "A run needs at least two profiles of the same device. With one "
            "there is nothing to compare it against.")
        return Run(entries=entries, ordered_by=how, complaints=complaints)

    # ONE DEVICE, OR IT IS NOT A RUN. The grid is in device coordinates, so
    # 50% grey asked of an RGB profile and of a CMYK one are not the same
    # request. Mixing them would draw a confident line describing nothing.
    spaces = {e.space for e in good}
    if len(spaces) > 1:
        named = ", ".join(f"{e.name} ({e.space})" for e in good)
        complaints.append(
            f"These are not all profiles of the same kind of device: {named}. "
            f"A run has to be one device profiled again and again, so there "
            f"is nothing here to follow over time.")
        return Run(entries=entries, ordered_by=how, complaints=complaints)

    tables = {e.table for e in good}
    if len(tables) > 1:
        # NOT FATAL, BUT SAID LOUDLY. A colorimetric table against a
        # perceptual one differs by a large amount that has nothing to do with
        # drift, because perceptual rendering moves colour on purpose.
        # Measured on real files: ΔE 45 worst, 12.7 average, and meaningless.
        import icc_read
        named = ", ".join(
            f"{e.name} was read through {icc_read.TABLE_NAMES[e.table]}"
            for e in good)
        complaints.append(
            f"These profiles were not all read the same way — {named}. Those "
            f"answer different questions, so most of what the line below "
            f"shows is that difference rather than anything that drifted. "
            f"Compare profiles built the same way for a figure you can trust.")

    def step(a: Entry, b: Entry) -> "Step | None":
        try:
            d = compare_profiles(a.path, b.path, steps=steps)
        except Exception as why:             # noqa: BLE001
            complaints.append(
                f"{a.name} could not be compared with {b.name}: {why}")
            return None
        return Step(before=a.name, after=b.name, worst=d.worst,
                    average=d.average, over_one=d.over_one, of=d.matched,
                    before_on=a.dated if a.when else "",
                    after_on=b.dated if b.when else "")

    first = good[0]
    since_first = [s for s in (step(first, e) for e in good[1:]) if s]
    since_previous = [s for s in (step(good[i - 1], good[i])
                                 for i in range(1, len(good))) if s]

    # THE SAME FILE TWICE IS ALMOST CERTAINLY A MISTAKE, and it produces a
    # perfectly clean zero that looks like wonderful news rather than like the
    # slip it is.
    seen: dict = {}
    for e in good:
        seen.setdefault(e.path.resolve(), []).append(e.name)
    for again in (names for names in seen.values() if len(names) > 1):
        complaints.append(
            f"The same file is in this run more than once ({again[0]}). The "
            f"step across it will read as no change at all, which is true of "
            f"the file and says nothing about the device.")

    return Run(entries=entries, since_first=since_first,
               since_previous=since_previous, ordered_by=how,
               complaints=complaints)


def figure(run: Run, *, mode: str = "dark", title: str = ""):
    """The run as a picture: both series, on one pair of axes.

    A LINE CHART RATHER THAN A SHAPE, and that is the honest form for this.
    The 3D cloud answers "where in colour", which is a question about one
    comparison. This answers "when, and how fast", which is a question about
    time -- and time is not a direction in Lab. Drawing it as anything else
    would be decoration pretending to be information.

    BOTH LINES ON ONE PAIR OF AXES because the reader has to see them
    disagree. Apart, on two charts, the eye reads each as its own story and
    the whole point -- that flat steps can add up to a long way -- is lost in
    the gap between them.

    The two bands are drawn behind the lines, not over them: below ΔE 1 most
    people would not notice a difference side by side, and above ΔE 3 it is
    hard to miss. Those are the
    same two numbers the pair comparison uses, so a reader who has learned
    them once does not meet a second vocabulary here.
    """
    import plotly.graph_objects as go

    from ti3gamut import SCENE_COLOURS
    c = SCENE_COLOURS["light" if mode == "light" else "dark"]

    names = [e.name for e in run.usable]
    fig = go.Figure()
    if len(names) < 2:
        return fig

    # SPACED BY REAL TIME WHEN THE DATES ALLOW IT, and this is not a nicety.
    # The whole question is "how fast is it drifting", and an axis that puts
    # 2019, 2020, 2021 and 2024 at even intervals draws a steady line through
    # a device that was quiet for three years and then moved. The rate would
    # be read straight off a picture that had thrown the rate away.
    #
    # Falls back to the names when any profile is undated, because a mixture
    # of real dates and invented ones is worse than an honest list.
    by_date = (run.ordered_by == "date"
               and all(e.when is not None for e in run.usable))
    if by_date:
        labels = ["{:04d}-{:02d}-{:02d}".format(*e.when[:3])
                  for e in run.usable[1:]]
        axis = dict(type="date")
        # ROOM AT BOTH ENDS, or the first date label lands in the corner and
        # is printed across the "0" of the side axis. Found by the layout
        # check at four window sizes in both engines -- 44 to 47 square pixels
        # of one number over another, which is small and unreadable rather
        # than obviously broken, so it is exactly the sort of thing a person
        # skims past and a measurement does not.
        #
        # A category axis already pads itself by half a slot; a date axis
        # fits the data exactly, so it has to be asked. A twentieth of the
        # span at each end is enough to clear the corner and too little to
        # look like missing data.
        import datetime as _dt

        try:
            days = [_dt.date(*e.when[:3]).toordinal() for e in run.usable]
            if len(days) > 1 and days[-1] > days[0]:
                # A TWELFTH, NOT A TWENTIETH, and the difference is a
                # measured one. At a twentieth the first profile's tick sat
                # about ten pixels from the axis on a 320px screen, and its
                # label was printed across the "0" of the side axis -- caught
                # by the layout check at 320x700 in WebKit, 24 square pixels
                # of one number over another. A twelfth clears it at every
                # size checked and still reads as one run rather than a line
                # marooned in the middle of an empty chart.
                edge = max((days[-1] - days[0]) / 12.0, 1.0)
                axis["range"] = [
                    _dt.date.fromordinal(int(days[0] - edge)).isoformat(),
                    _dt.date.fromordinal(int(days[-1] + edge)).isoformat()]
            # A TICK FOR EVERY PROFILE, while there are few enough to read.
            #
            # Left to itself the library picks round years, and a profile made
            # in March sits between two of them with nothing naming it --
            # which is exactly what Basti met: "the 2020 value has no 2020
            # label and does not seem to be on the exact line that would
            # represent 2020". It was on no line because there was no line.
            #
            # Twelve is where a date every point stops fitting across a phone
            # and the round years become the readable choice again; above it
            # the library's own spacing is better than a crowd of overlapping
            # labels.
            if len(run.usable) <= 12:
                axis["tickmode"] = "array"
                axis["tickvals"] = [
                    "{:04d}-{:02d}-{:02d}".format(*e.when[:3])
                    for e in run.usable]
                # THE YEAR ALONE WHERE THAT IS UNAMBIGUOUS. A run of yearly
                # profiles reads as 2019, 2020, 2021; two in one year would
                # then wear the same label, so those get the month as well.
                years = [e.when[0] for e in run.usable]
                same_year = len(set(years)) != len(years)
                axis["ticktext"] = [
                    "{:04d}-{:02d}".format(*e.when[:2]) if same_year
                    else f"{e.when[0]}" for e in run.usable]
        except (ValueError, TypeError, OverflowError):
            pass          # an impossible date simply gets the default range
    else:
        labels = names[1:]
        axis = dict(type="category")

    top = max([s.worst for s in run.since_first]
              + [s.worst for s in run.since_previous] + [OBVIOUS]) * 1.15

    # THE BANDS FIRST, so the lines are read over them rather than through.
    for low, high, colour, words in (
            (0.0, INVISIBLE, "rgba(120,200,140,0.10)",
             "most would not notice this"),
            (OBVIOUS, top, "rgba(255,69,115,0.10)", "hard to miss")):
        if high > low:
            fig.add_hrect(y0=low, y1=high, line_width=0, fillcolor=colour,
                          layer="below", annotation_text=words,
                          annotation_position="top left",
                          annotation_font=dict(size=10, color=c["caption"]))

    # THE FIRST PROFILE IS ON THE CHART, AT ZERO, and it belongs there.
    #
    # Reported by Basti: "such an overview should also show the 2019 reference
    # as the reference point at zero". He is right, and it was doing two
    # separate harms. The cumulative line is measured FROM that profile, so
    # leaving it off drew a line whose origin was nowhere on the picture --
    # the first thing plotted was already a whole year of drift, at ΔE 2.60,
    # which reads as where the run began.
    #
    # AND IT WAS WHY THE SECOND PROFILE HAD NO LABEL, which he also spotted.
    # With the run starting at 2020-03-01 the padded axis began 2020-01-06,
    # five days after the 2020 tick would have fallen -- so the axis was
    # labelled 2021, 2022, 2023 and the 2020 point sat in an unnamed gap. His
    # own guess, that the profiles were not evenly spaced, was the one thing
    # it was not: measured, all four gaps are exactly 12 months.
    #
    # ONLY THE CUMULATIVE LINE GETS IT. "Since the one before" has no
    # previous for the first profile, so it starts at the second, and that
    # difference between the two lines is itself worth seeing.
    first = run.usable[0]
    start = ("{:04d}-{:02d}-{:02d}".format(*first.when[:3]) if by_date
             else first.name)
    fig.add_trace(go.Scatter(
        x=[start] + labels,
        y=[0.0] + [s.worst for s in run.since_first], mode="lines+markers",
        name=f"since {names[0]} (how far altogether)",
        line=dict(color="#ff4573", width=2.5), marker=dict(size=8),
        hovertemplate="%{x}<br>ΔE %{y:.2f} since the first<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=labels, y=[s.worst for s in run.since_previous],
        mode="lines+markers", name="since the one before (how far each time)",
        line=dict(color="#c9a227", width=2.5, dash="dot"),
        marker=dict(size=8),
        hovertemplate="%{x}<br>ΔE %{y:.2f} since the one before<extra></extra>"))

    # THE TITLE AND THE KEY GET SEPARATE BANDS, and that is a correction
    # rather than a preference. Both used to be left-anchored inside one 70px
    # top margin, which worked only while the key happened to fit on a single
    # row; the moment it wrapped, its second row climbed into the title.
    # Measured on the shipped pages, in both engines, it collided in 14 of 20
    # window sizes -- including a large desktop, so this was never only a
    # phone fault. Reported by Basti from an iPhone.
    #
    # THE AXIS TITLE IS BROKEN OVER TWO LINES for a second, separate reason
    # found by the same measurement. Rotated upright, "ΔE2000 — the biggest
    # difference" is about 175px tall, and on a short window the plot area is
    # about 116px, so it stuck out of both ends and crossed the title. Two
    # lines are half as tall and fit. Both layouts were then checked at ten
    # window sizes in two engines, with a short device name and with a very
    # long one: nothing overlaps anywhere.
    # AND WHERE IT WAS FURTHEST, marked, when the run came back from it.
    #
    # The arch in the cumulative line already says so to anybody who reads
    # both lines together. This is for the reader who glances at the last
    # point, sees it near the floor, and closes the page -- which is the
    # reading this shape of run invites and the one that is wrong. Only drawn
    # when there IS an excursion to point at, so it never becomes furniture.
    if run.came_back and run.furthest is not None:
        peak = run.furthest
        at = peak.after_on if by_date else peak.after
        fig.add_annotation(
            x=at, y=peak.worst, text="furthest from the first",
            showarrow=True, arrowhead=0, arrowwidth=1, ax=0, ay=-26,
            arrowcolor=c["caption"],
            font=dict(size=10, color=c["caption"]))

    fig.update_layout(
        title=dict(text=(title or "How far this device has moved")
                   + " — the biggest difference at each step",
                   font=dict(size=13, color=c["caption"]), x=0.01,
                   yref="container", y=1.0, yanchor="top",
                   pad=dict(t=8), automargin=True),
        paper_bgcolor=c["page"], plot_bgcolor=c["plot"],
        font=dict(color=c["text"], size=12),
        xaxis=dict(title="", gridcolor=c["grid"], color=c["text"], **axis),
        # THE AXIS SAYS ITS UNIT, AND ONLY ITS UNIT.
        #
        # It used to read "ΔE2000 / the biggest difference" on two lines, and
        # that was measured -- at ten window sizes, in two engines -- against
        # the SAVED PAGE, where the graph is given 68% of the screen. Nobody
        # measured the application's own pane, which is about 200px tall. At
        # that height the second line, 153px when it is stood on end, runs
        # straight through the caption; at 200px it starts at y = -5, which is
        # to say outside the plot altogether. Basti photographed it.
        #
        # A one-line title is 54px and fits at every height measured, down to
        # 170. What the number MEANS moves into the caption, where it reads as
        # a sentence rather than as a label stood on its end -- and where it
        # cannot collide with anything, because it is the thing everything
        # else is laid out around.
        yaxis=dict(title="ΔE2000",
                   gridcolor=c["grid"], color=c["text"], rangemode="tozero"),
        legend=dict(orientation="h", yanchor="top", y=-0.16, x=0,
                    xanchor="left", font=dict(color=c["text"])),
        margin=dict(l=70, r=30, t=44, b=100))
    return fig


def verdict(run: Run) -> str:
    """What the run amounts to, in a sentence somebody can act on."""
    if not run.since_first:
        return ""
    total = run.total
    span = f"{run.usable[0].name} to {run.usable[-1].name}"
    # WENT AWAY AND CAME BACK, ASKED FIRST because every branch below reads
    # only where the run STARTED and where it ENDED, and for this shape of
    # run those two are nearly the same while the middle is not. Reaching
    # "nothing has moved" first is exactly how this came to print that of a
    # printer that had been visibly wrong for a year. See Run.came_back.
    if run.came_back:
        peak = run.furthest
        scale = ("visible on a careful look" if peak.worst < OBVIOUS
                 else "plainly visible")
        ended = ("almost exactly where it started" if total < INVISIBLE
                 else f"ΔE {total:.2f} from where it started")
        return (f"It went away and came back. Where it ended is {ended}, so "
                f"comparing only the first and last profile would have shown "
                f"you almost nothing. It did not stay there: by "
                f"{peak.after_on or peak.after} it had drifted ΔE "
                f"{peak.worst:.2f} from {run.usable[0].name}, which is "
                f"{scale}. Anything you printed around then will not match "
                f"what you print now, and this is the one shape of run where "
                f"the first and last profile on their own would have misled "
                f"you.")
    if total < INVISIBLE:
        return (f"Nothing has moved that most people would notice. From "
                f"{span} the biggest difference is ΔE {total:.2f}, which is "
                f"below the usual rule of thumb for a difference worth "
                f"chasing — and no larger than the 1 ΔEab two identical "
                f"instruments can disagree by on one patch.")
    scale = ("findable by a careful eye" if total < OBVIOUS
             else "hard to miss")
    if run.steady:
        return (f"It has drifted steadily. From {span} the biggest difference "
                f"has reached ΔE {total:.2f}, which is {scale}, and each step "
                f"is about the size of the last — so it is likely to keep "
                f"going at the same rate.")
    worst = run.worst_step
    return (f"Most of the movement happened at one point rather than "
            f"gradually. From {span} the biggest difference has reached "
            f"ΔE {total:.2f}, which is {scale}, and the largest single step "
            f"is {worst.spans} at ΔE {worst.worst:.2f}. "
            f"Something happened between those two — that is what is worth "
            f"chasing, rather than the trend.")
