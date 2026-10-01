from temp_codes import (fill_temp_codes, is_temp, merge_temp_clients,
                        merge_upload, needs_temp, next_temp_code,
                        pending_temp)


def c(cid, name, link=None):
    return {"id": cid, "name": name, "link": link}


# --- is_temp ---------------------------------------------------------------

def test_is_temp_matches_generated_codes():
    assert is_temp("TEMP01")
    assert is_temp("TEMP100")


def test_is_temp_is_case_insensitive_and_trims():
    # The office may retype a code by hand; temp01 is the same client state.
    assert is_temp("temp01")
    assert is_temp("  Temp02  ")


def test_is_temp_rejects_real_and_empty_codes():
    assert not is_temp("RED341")
    assert not is_temp("")
    assert not is_temp(None)
    assert not is_temp("TEMP")        # no number
    assert not is_temp("TEMP01A")     # not a bare number
    assert not is_temp("XTEMP01")


# --- next_temp_code --------------------------------------------------------

def test_next_temp_code_starts_at_one_and_pads():
    assert next_temp_code([]) == "TEMP01"
    assert next_temp_code([c("RED341", "Redwood")]) == "TEMP01"


def test_next_temp_code_skips_taken_numbers():
    clients = [c("TEMP01", "A"), c("TEMP02", "B")]
    assert next_temp_code(clients) == "TEMP03"


def test_next_temp_code_reuses_a_gap_left_by_an_assignment():
    # TEMP02 got its real ID, so 02 is free again.
    clients = [c("TEMP01", "A"), c("RED342", "B"), c("TEMP03", "C")]
    assert next_temp_code(clients) == "TEMP02"


def test_next_temp_code_ignores_case_when_scanning():
    assert next_temp_code([c("temp01", "A")]) == "TEMP02"


def test_next_temp_code_grows_past_two_digits():
    clients = [c("TEMP%02d" % n, str(n)) for n in range(1, 100)]
    assert next_temp_code(clients) == "TEMP100"


# --- pending_temp ----------------------------------------------------------

def test_pending_temp_returns_only_temp_rows_sorted_by_name():
    clients = [c("TEMP02", "Oakfield"), c("RED341", "Redwood"),
               c("TEMP01", "Ashby")]
    assert [x["name"] for x in pending_temp(clients)] == ["Ashby", "Oakfield"]


def test_pending_temp_empty_when_nothing_waiting():
    assert pending_temp([c("RED341", "Redwood")]) == []


# --- merge_temp_clients ----------------------------------------------------

def test_merge_keeps_a_temp_client_the_spreadsheet_does_not_have():
    current = [c("TEMP01", "Oakfield Trading Ltd", "https://oak")]
    new = [c("RED341", "Redwood Holdings Ltd", "https://red")]
    merged, kept = merge_temp_clients(new, current)
    assert [x["name"] for x in merged] == ["Redwood Holdings Ltd",
                                           "Oakfield Trading Ltd"]
    assert [x["name"] for x in kept] == ["Oakfield Trading Ltd"]
    # The kept row keeps its own link, not the file's.
    assert merged[1]["link"] == "https://oak"


def test_merge_lets_the_file_retire_a_temp_row_with_the_real_code():
    current = [c("TEMP01", "Oakfield Trading Ltd")]
    new = [c("OAK118", "Oakfield Trading Ltd", "https://oak")]
    merged, kept = merge_temp_clients(new, current)
    assert kept == []
    assert len(merged) == 1
    assert merged[0]["id"] == "OAK118"


def test_merge_matches_names_case_insensitively():
    current = [c("TEMP01", "oakfield trading ltd")]
    new = [c("OAK118", "Oakfield Trading Ltd")]
    merged, kept = merge_temp_clients(new, current)
    assert kept == []
    assert len(merged) == 1


def test_merge_leaves_non_temp_clients_alone():
    # A real client missing from the file still drops — the file is the
    # restore source for everyone who already has a code.
    current = [c("RED341", "Redwood Holdings Ltd")]
    new = [c("OAK118", "Oakfield Trading Ltd")]
    merged, kept = merge_temp_clients(new, current)
    assert kept == []
    assert [x["name"] for x in merged] == ["Oakfield Trading Ltd"]


def test_merge_does_not_mutate_the_parsed_list():
    current = [c("TEMP01", "Oakfield Trading Ltd")]
    new = [c("RED341", "Redwood Holdings Ltd")]
    merged, _ = merge_temp_clients(new, current)
    assert len(new) == 1
    assert len(merged) == 2


# --- needs_temp / fill_temp_codes ------------------------------------------

def test_needs_temp_for_blank_or_name_as_id():
    assert needs_temp(c("", "Acme Ltd"))
    assert needs_temp(c(None, "Acme Ltd"))
    assert needs_temp(c("  acme ltd ", "Acme Ltd"))


def test_needs_temp_leaves_real_temp_and_odd_codes_alone():
    assert not needs_temp(c("RED341", "Redwood"))
    assert not needs_temp(c("TEMP01", "Oakfield"))
    assert not needs_temp(c("ans108", "ansh"))


def test_fill_mints_distinct_codes_skipping_taken_numbers():
    clients = [c("TEMP01", "Oak"), c("Acme", "Acme"), c("", "Beta"),
               c("RED341", "Redwood")]
    filled, minted = fill_temp_codes(clients)
    assert [x["id"] for x in filled] == ["TEMP01", "TEMP02", "TEMP03", "RED341"]
    assert minted == [{"id": "TEMP02", "name": "Acme", "was": "Acme"},
                      {"id": "TEMP03", "name": "Beta", "was": ""}]


def test_fill_does_not_modify_its_input():
    clients = [c("Acme", "Acme", "https://a")]
    filled, _ = fill_temp_codes(clients)
    assert clients == [c("Acme", "Acme", "https://a")]
    assert filled == [c("TEMP01", "Acme", "https://a")]


def test_fill_reuses_a_previous_temp_code_by_name():
    previous = [c("TEMP07", "Acme Ltd")]
    filled, minted = fill_temp_codes([c("Acme Ltd", "acme ltd")], previous)
    assert filled[0]["id"] == "TEMP07"
    assert minted == []


def test_fill_lends_each_previous_code_once():
    previous = [c("TEMP01", "Acme")]
    filled, minted = fill_temp_codes([c("Acme", "Acme"), c("", "Acme")],
                                     previous)
    assert [x["id"] for x in filled] == ["TEMP01", "TEMP02"]
    assert [m["id"] for m in minted] == ["TEMP02"]


def test_fill_does_not_lend_a_code_the_file_already_uses():
    previous = [c("TEMP01", "Acme")]
    filled, _ = fill_temp_codes([c("TEMP01", "Other"), c("Acme", "Acme")],
                                previous)
    assert [x["id"] for x in filled] == ["TEMP01", "TEMP02"]


def test_merge_upload_is_stable_across_reuploads():
    file_rows = [c("Acme", "Acme"), c("RED341", "Redwood")]
    first, _, minted = merge_upload(file_rows, [])
    assert [m["id"] for m in minted] == ["TEMP01"]
    second, kept, minted = merge_upload(file_rows, first)
    assert second == first
    assert kept == [] and minted == []
