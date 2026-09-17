from analyze_difficulty_ratings import analyze_ratings


def _ratings(**by_name):
    """by_name: name -> (easy, medium, hard) scores (None for missing)."""
    out = []
    for name, (easy, medium, hard) in by_name.items():
        for tier, score in (("easy", easy), ("medium", medium), ("hard", hard)):
            out.append({"name": name, "tier": tier, "score": score, "notes": ""})
    return out


def test_all_monotonic_no_violations_no_ties():
    ratings = _ratings(piece_a=(2, 5, 8), piece_b=(1, 4, 7))
    result = analyze_ratings(ratings)
    assert result["violations"] == []
    assert result["ties"] == []
    assert result["all_monotonic"] is True
    assert result["n_pieces_rated"] == 2
    assert result["n_pieces_incomplete"] == 0


def test_violation_detected_when_a_later_tier_scores_lower():
    ratings = _ratings(piece_a=(2, 5, 8), piece_b=(3, 7, 6))  # medium > hard for piece_b
    result = analyze_ratings(ratings)
    assert result["all_monotonic"] is False
    assert len(result["violations"]) == 1
    assert result["violations"][0]["name"] == "piece_b"


def test_tie_recorded_separately_not_a_violation():
    ratings = _ratings(piece_a=(2, 5, 5))  # medium == hard
    result = analyze_ratings(ratings)
    assert result["violations"] == []
    assert len(result["ties"]) == 1
    assert result["ties"][0]["name"] == "piece_a"
    assert result["all_monotonic"] is True


def test_incomplete_piece_excluded_from_stats_and_counted():
    ratings = _ratings(piece_a=(2, 5, 8), piece_b=(1, None, 7))
    result = analyze_ratings(ratings)
    assert result["n_pieces_rated"] == 1
    assert result["n_pieces_incomplete"] == 1
    assert result["tier_stats"]["easy"]["mean"] == 2.0


def test_tier_stats_aggregate_across_pieces():
    ratings = _ratings(piece_a=(2, 4, 6), piece_b=(4, 6, 8))
    result = analyze_ratings(ratings)
    assert result["tier_stats"]["easy"] == {"mean": 3.0, "min": 2, "max": 4}
    assert result["tier_stats"]["medium"] == {"mean": 5.0, "min": 4, "max": 6}
    assert result["tier_stats"]["hard"] == {"mean": 7.0, "min": 6, "max": 8}
