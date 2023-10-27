import datetime
import os
import pytest
from espn_api.football import League, Matchup
import src.doritostats.fetch_utils as fetch  # The code to test


league_id = os.getenv("LEAGUE_ID")
swid = os.getenv("SWID")
espn_s2 = os.getenv("ESPN_S2")
print("LEAGUE_ID: {}".format(league_id))
print("SWID: {}".format(swid))
print("ESPN_S2: {}".format(espn_s2))

current_league_year = (datetime.datetime.now() - datetime.timedelta(days=60)).year
league_2018 = League(league_id=league_id, year=2018, swid=swid, espn_s2=espn_s2)
league_2021 = League(league_id=league_id, year=2021, swid=swid, espn_s2=espn_s2)
league_curr = League(
    league_id=league_id, year=current_league_year, swid=swid, espn_s2=espn_s2
)


@pytest.mark.parametrize(
    "league, endpoint",
    [
        (
            league_2018,
            "https://fantasy.espn.com/apis/v3/games/ffl/leagueHistory/1086064?seasonId=2018&",
        ),
        (
            league_2021,
            "https://fantasy.espn.com/apis/v3/games/ffl/leagueHistory/1086064?seasonId=2021&",
        ),
        (
            league_curr,
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/{}/segments/0/leagues/1086064?".format(
                league_curr.year
            ),
        ),
    ],
)
def test_set_league_endpoint(league: League, endpoint: str):
    fetch.set_league_endpoint(league)
    assert league.endpoint == endpoint


@pytest.mark.parametrize(
    "league, swid, espn_s2, results",
    [
        (
            league_2018,
            swid,
            espn_s2,
            {
                "league_name": "Make Football Great Again",
                "roster_settings": {
                    "roster_slots": {
                        "QB": 1,
                        "RB": 3,
                        "WR": 3,
                        "TE": 1,
                        "D/ST": 1,
                        "K": 1,
                        "BE": 8,
                        "IR": 1,
                        "RB/WR/TE": 1,
                    },
                    "starting_roster_slots": {
                        "QB": 1,
                        "RB": 3,
                        "WR": 3,
                        "TE": 1,
                        "D/ST": 1,
                        "K": 1,
                        "RB/WR/TE": 1,
                    },
                },
            },
        ),
        (
            league_curr,
            swid,
            espn_s2,
            {
                "league_name": "La Lega dei Cugini",
                "roster_settings": {
                    "roster_slots": {
                        "QB": 1,
                        "RB": 2,
                        "WR": 2,
                        "TE": 1,
                        "D/ST": 1,
                        "K": 1,
                        "BE": 8,
                        "IR": 1,
                        "RB/WR/TE": 2,
                    },
                    "starting_roster_slots": {
                        "QB": 1,
                        "RB": 2,
                        "WR": 2,
                        "TE": 1,
                        "D/ST": 1,
                        "K": 1,
                        "RB/WR/TE": 2,
                    },
                },
            },
        ),
    ],
)
def test_get_roster_settings(league: League, swid: str, espn_s2: str, results: dict):
    league.cookies = {"swid": swid, "espn_s2": espn_s2}
    fetch.get_roster_settings(league)
    assert league.name == results["league_name"]
    assert league.roster_settings == results["roster_settings"]


@pytest.mark.parametrize(
    "league_id, year, swid, espn_s2, results",
    [
        (
            league_id,
            2018,
            swid,
            espn_s2,
            {
                "league_name": "Make Football Great Again",
                "cookies": {"swid": swid, "espn_s2": espn_s2},
            },
        ),
        (
            league_id,
            2022,
            swid,
            espn_s2,
            {
                "league_name": "La Lega dei Cugini",
                "cookies": {"swid": swid, "espn_s2": espn_s2},
            },
        ),
    ],
)
def test_fetch_league(
    league_id: int, year: int, swid: str, espn_s2: str, results: dict
):
    league = fetch.fetch_league(league_id, year, swid, espn_s2)
    assert type(league)
    assert league.cookies == results["cookies"]


@pytest.mark.parametrize(
    "league, matchup, week, result",
    [
        (
            league_2018,
            fetch.PseudoMatchup(league_2018.teams[0], league_2018.teams[0].schedule[0]),
            1,
            False,
        ),  # Regular season
        (
            league_2018,
            fetch.PseudoMatchup(
                league_2018.teams[0], league_2018.teams[0].schedule[12]
            ),
            13,
            True,
        ),  # Known playoff game
        (
            league_2018,
            fetch.PseudoMatchup(
                league_2018.teams[5], league_2018.teams[5].schedule[12]
            ),
            13,
            False,
        ),  # Known consolation game
        (league_2021, league_2021.box_scores(1)[0], 1, False),  # Regular season
        (league_2021, league_2021.box_scores(15)[0], 15, False),  # Playoff Bye
        (league_2021, league_2021.box_scores(15)[1], 15, True),  # Playoff game
        (league_2021, league_2021.box_scores(15)[-1], 15, False),  # Consolation game
    ],
)
def test_is_playoff_game(league: League, matchup: Matchup, week: int, result: bool):
    assert fetch.is_playoff_game(league, matchup, week) == result
