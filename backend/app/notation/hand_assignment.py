"""Continuity-aware RH/LH hand assignment.

Replaces the naive "highest simultaneous pitch is melody" rule with an exact
dynamic-programming (Viterbi-style) search over every legal way to split
each onset's notes between two hands, scored by:

  * continuity  -- how far a hand's pitch centroid has to jump from where
    it last was, so a hand's notes stay coherent over time instead of being
    re-picked from scratch at every onset;
  * span        -- a soft penalty past ~1 octave of simultaneous span for a
    single hand, and a hard exclusion past ~2 octaves (no pianist can
    stretch that far), so a wide chord gets split into two physically
    plausible spans instead of dumping everything but the top note into
    one hand;
  * crossing    -- a small penalty when the two hands' registers overlap,
    so a plain top/bottom split remains the default unless continuity or
    span pressure clearly justifies a hand-crossing;
  * switching   -- a fixed hysteresis penalty whenever a note would land in
    a different hand than the nearest-pitch note at the previous onset.
    Without this, a note whose pitch sits roughly equidistant between both
    hands' centroids can flip the argmin on noise-level cost differences,
    producing audible flicker (rapid hand alternation) on passages
    clustered tightly in one register. This is the fix for that bug.

No absolute-pitch threshold is used anywhere: only relative motion/spacing
decide hand assignment. This is deliberate -- it preserves the existing,
separate convention (see app.notation.hand_split's dynamic clef changes)
that a melody may legitimately dip into the bass register (or an
accompaniment rise into the treble) without being reassigned to the other
hand; a hand's own notes are simply redrawn with a temporary clef.

A lone note at an onset (no simultaneous partner) is *always* assigned to
the right hand, mirroring the current codebase's existing melody rule
exactly (the highest -- and only -- note in a group of one is always
"the melody"). This is a deliberate special case, not a DP decision: it
keeps a sustained low monophonic run in RH (where the temporary-clef
mechanism draws it in bass clef) rather than letting continuity pull it
into LH, which would silently change today's intentional behavior.
"""

import itertools
from dataclasses import dataclass, field
from typing import Optional

from app.notation.types import NoteEvent

# --- Tunable constants -----------------------------------------------------
# All hand-tuned against a handful of synthetic stress cases plus one real
# ~350-note transcribed piano clip. Revisit with more real-audio data before
# trusting these far outside that regime.

# Onsets within this many seconds of each other are treated as simultaneous
# (matches the rounding hand_split.py already uses for onset grouping).
ONSET_ROUND_DECIMALS = 3

# Beyond this many simultaneous notes, exact 2^n mask enumeration is
# abandoned in favor of the old top-note-wins rule, purely to bound
# worst-case runtime -- this many simultaneous real piano notes is already
# implausible input (mistranscription/noise), not a real musical texture.
MAX_GROUP_SIZE_FOR_DP = 10

# Beam width: how many candidate (particle) hand-assignment histories are
# kept after each onset. Bounds runtime to roughly beam_width * 2^group_size
# per onset regardless of piece length.
BEAM_WIDTH = 16

SOFT_SPAN_SEMITONES = 12  # ~1 octave -- a single hand's span above this is penalized
HARD_SPAN_SEMITONES = 24  # ~2 octaves -- a single hand's span above this is disallowed
SPAN_PENALTY_WEIGHT = 1.0  # cost per semitone of span past the soft threshold

CONTINUITY_WEIGHT = 1.0  # cost per semitone a hand's centroid has to jump
NEW_HAND_COST = 0.0  # flat cost for a hand's first-ever note
EMA_ALPHA = 0.5  # how much a new onset's mean pitch moves a hand's centroid (vs. keeping its prior value)

# This is a solo-piano *arrangement* tool: the norm is both hands in use
# (melody + accompaniment), so leaving a hand fully idle for an onset that
# actually has >= 2 notes to distribute is disfavored by default -- e.g.
# without this, a bare 3-note chord with no other context happily piles
# into a single hand (physically fine, span-wise, so nothing else would
# stop it), which is a worse arrangement than splitting it.
#
# Must be large enough that PERSISTING single-hand consolidation across
# several onsets can never beat one legitimate large continuity jump on a
# correctly-split path -- found via a real regression: at 3.0, accumulating
# this penalty over 5 consecutive onsets (15.0) undercut a single honest
# 28-semitone LH jump on the correctly-split alternative (28.0), so the DP
# happily bundled a whole sustained accompaniment run into one hand instead
# of ever separating it. 6.0 keeps sustained bundling reliably more
# expensive than a single normal-register-range jump (verified against a
# sweep from 3.0-15.0; 5.0 was the lowest value that fixed it, so this
# keeps a safety margin) while still letting real continuity pressure
# (already-established hands whose centroids strongly favor one side)
# outweigh it for a single onset, since it's still only a flat per-onset
# cost, not compounding.
SINGLE_HAND_CONSOLIDATION_PENALTY = 6.0

CROSSING_PENALTY = 3.0  # flat cost when the two hands' registers overlap this onset

# Hysteresis / flicker fix: a fixed penalty whenever a note lands in a
# different hand than the nearest-pitch note at the immediately preceding
# onset. This is what damps rapid hand alternation on tightly-clustered
# passages where continuity alone leaves the choice near-ambiguous.
SWITCH_PENALTY = 4.0

# Tie-break only: when two splits are otherwise equal in cost, very
# slightly prefer RH staying a single melodic line rather than a stacked
# chord (mirrors the existing "one melody note in RH, the rest in LH"
# convention). Small enough to never override a real continuity/span/
# crossing signal -- it only decides genuine ties, e.g. the very first
# chord of a piece, before either hand has any history to lean on.
RH_MELODY_TIEBREAK_WEIGHT = 0.01


@dataclass
class _Particle:
    rh_centroid: Optional[float]
    lh_centroid: Optional[float]
    # (pitch, hand) pairs from this particle's own most recently resolved
    # onset, used only for the next onset's switch-cost lookup.
    last_onset_notes: list = field(default_factory=list)
    cost: float = 0.0
    parent: Optional["_Particle"] = None
    # (group, mask) chosen at this particle's own onset, for traceback.
    assignment: Optional[tuple] = None


def _group_by_onset(notes: list[NoteEvent]) -> list[list[NoteEvent]]:
    by_onset: dict[float, list[NoteEvent]] = {}
    for event in notes:
        by_onset.setdefault(round(event.start, ONSET_ROUND_DECIMALS), []).append(event)
    return [by_onset[onset] for onset in sorted(by_onset)]


def _candidate_masks(n: int) -> list[tuple[bool, ...]]:
    """All 2^n ways to split n notes between RH (True) and LH (False)."""
    return list(itertools.product([True, False], repeat=n))


def _span(pitches: list[int]) -> float:
    return max(pitches) - min(pitches) if len(pitches) >= 2 else 0.0


def _legal_masks(group: list[NoteEvent]) -> list[tuple[bool, ...]]:
    n = len(group)
    all_masks = _candidate_masks(n)
    legal = []
    for mask in all_masks:
        rh_pitches = [group[i].pitch for i in range(n) if mask[i]]
        lh_pitches = [group[i].pitch for i in range(n) if not mask[i]]
        if _span(rh_pitches) > HARD_SPAN_SEMITONES or _span(lh_pitches) > HARD_SPAN_SEMITONES:
            continue
        legal.append(mask)
    if legal:
        return legal
    # Safety net: no split keeps both hands under the hard span (extreme,
    # pathological spread). Fall back to every mask rather than producing
    # no candidates at all -- the soft span penalty still steers scoring.
    return all_masks


def _score_mask(particle: _Particle, group: list[NoteEvent], mask: tuple[bool, ...]) -> tuple[float, Optional[float], Optional[float]]:
    """Returns (cost_delta, new_rh_centroid, new_lh_centroid)."""
    rh_notes = [group[i] for i in range(len(group)) if mask[i]]
    lh_notes = [group[i] for i in range(len(group)) if not mask[i]]
    cost = 0.0

    if rh_notes and lh_notes:
        if min(e.pitch for e in rh_notes) < max(e.pitch for e in lh_notes):
            cost += CROSSING_PENALTY
    elif len(group) >= 2:
        cost += SINGLE_HAND_CONSOLIDATION_PENALTY

    cost += max(0.0, _span([e.pitch for e in rh_notes]) - SOFT_SPAN_SEMITONES) * SPAN_PENALTY_WEIGHT
    cost += max(0.0, _span([e.pitch for e in lh_notes]) - SOFT_SPAN_SEMITONES) * SPAN_PENALTY_WEIGHT

    if rh_notes:
        mean_pitch = sum(e.pitch for e in rh_notes) / len(rh_notes)
        if particle.rh_centroid is None:
            cost += NEW_HAND_COST
            new_rh_centroid = mean_pitch
        else:
            cost += abs(mean_pitch - particle.rh_centroid) * CONTINUITY_WEIGHT
            new_rh_centroid = EMA_ALPHA * mean_pitch + (1 - EMA_ALPHA) * particle.rh_centroid
    else:
        new_rh_centroid = particle.rh_centroid

    if lh_notes:
        mean_pitch = sum(e.pitch for e in lh_notes) / len(lh_notes)
        if particle.lh_centroid is None:
            cost += NEW_HAND_COST
            new_lh_centroid = mean_pitch
        else:
            cost += abs(mean_pitch - particle.lh_centroid) * CONTINUITY_WEIGHT
            new_lh_centroid = EMA_ALPHA * mean_pitch + (1 - EMA_ALPHA) * particle.lh_centroid
    else:
        new_lh_centroid = particle.lh_centroid

    if particle.last_onset_notes:
        for i, event in enumerate(group):
            hand = "R" if mask[i] else "L"
            nearest_hand = min(particle.last_onset_notes, key=lambda pn: abs(pn[0] - event.pitch))[1]
            if nearest_hand != hand:
                cost += SWITCH_PENALTY

    if len(rh_notes) > 1:
        cost += RH_MELODY_TIEBREAK_WEIGHT * len(rh_notes)

    return cost, new_rh_centroid, new_lh_centroid


def assign_hands(notes: list[NoteEvent]) -> tuple[list[NoteEvent], list[NoteEvent]]:
    """Split notes between right and left hand using exact DP (Viterbi-style,
    beam-limited) continuity scoring over onset groups.

    Returns (rh_notes, lh_notes), each sorted by (start, pitch). Pure
    function of the input notes -- no I/O, no global state.
    """
    if not notes:
        return [], []

    groups = _group_by_onset(notes)
    particles = [_Particle(rh_centroid=None, lh_centroid=None)]

    for group in groups:
        n = len(group)
        if n == 1:
            masks = [(True,)]
        elif n > MAX_GROUP_SIZE_FOR_DP:
            top_idx = max(range(n), key=lambda i: group[i].pitch)
            masks = [tuple(i == top_idx for i in range(n))]
        else:
            masks = _legal_masks(group)

        new_particles = []
        for particle in particles:
            for mask in masks:
                cost_delta, new_rh, new_lh = _score_mask(particle, group, mask)
                last_onset_notes = [
                    (group[i].pitch, "R" if mask[i] else "L") for i in range(n)
                ]
                new_particles.append(
                    _Particle(
                        rh_centroid=new_rh,
                        lh_centroid=new_lh,
                        last_onset_notes=last_onset_notes,
                        cost=particle.cost + cost_delta,
                        parent=particle,
                        assignment=(group, mask),
                    )
                )
        new_particles.sort(key=lambda p: p.cost)
        particles = new_particles[:BEAM_WIDTH]

    best = min(particles, key=lambda p: p.cost)
    rh_notes: list[NoteEvent] = []
    lh_notes: list[NoteEvent] = []
    p: Optional[_Particle] = best
    while p is not None and p.assignment is not None:
        group, mask = p.assignment
        for i, event in enumerate(group):
            (rh_notes if mask[i] else lh_notes).append(event)
        p = p.parent

    rh_notes.sort(key=lambda e: (e.start, e.pitch))
    lh_notes.sort(key=lambda e: (e.start, e.pitch))
    return rh_notes, lh_notes
