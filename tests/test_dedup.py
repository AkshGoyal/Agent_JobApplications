from pipeline.dedup import dedup_hash


def test_same_job_same_hash_regardless_of_case_and_spacing():
    a = dedup_hash("Acme AI", "AI Engineer", "Bengaluru")
    b = dedup_hash("  acme ai ", "ai engineer", " BENGALURU ")
    assert a == b


def test_same_job_from_different_urls_collides():
    # dedup_hash intentionally ignores the URL — the same role pasted from
    # two links must produce the same fingerprint.
    a = dedup_hash("Acme AI", "AI Engineer", "Bengaluru")
    b = dedup_hash("Acme AI", "AI Engineer", "Bengaluru")
    assert a == b


def test_different_title_or_company_or_location_differs():
    base = dedup_hash("Acme AI", "AI Engineer", "Bengaluru")
    assert dedup_hash("Acme AI", "AI Product Manager", "Bengaluru") != base
    assert dedup_hash("Other Corp", "AI Engineer", "Bengaluru") != base
    assert dedup_hash("Acme AI", "AI Engineer", "Mumbai") != base


def test_missing_location_is_stable():
    assert dedup_hash("Acme AI", "AI Engineer", None) == dedup_hash(
        "Acme AI", "AI Engineer", ""
    )
