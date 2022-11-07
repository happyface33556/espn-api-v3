import numpy as np
import pandas as pd
from copy import copy
from typing import Callable
from espn_api.football import League, Team
from src.doritostats.filter_utils import get_any_records, exclude_most_recent_week

""" ANALYTIC FUNCTIONS """


def get_lineup(league: League, team: Team, week: int, box_scores=None):
    """Return the lineup of the given team during the given week"""
    # Get the lineup for the team during the specified week
    if box_scores is None:
        box_scores = league.box_scores(week)
    for box_score in box_scores:
        if team == box_score.home_team:
            return box_score.home_lineup
        elif team == box_score.away_team:
            return box_score.away_lineup


def get_top_players(lineup: list, slot: str, n: int):
    """Takes a list of players and returns a list of the top n players based on points scored."""
    # Gather players of the desired position
    eligible_players = []
    for player in lineup:
        if slot in player.eligibleSlots:
            eligible_players.append(player)

    return sorted(eligible_players, key=lambda x: x.points, reverse=True)[:n]


def get_best_lineup(league: League, lineup: list):
    """Returns the best possible lineup for team during the loaded week."""
    # Save full roster
    saved_roster = copy(lineup)

    # Find Best Lineup
    best_lineup = []
    # Get best RB before best RB/WR/TE
    for slot in sorted(league.roster_settings["starting_roster_slots"].keys(), key=len):
        num_players = league.roster_settings["starting_roster_slots"][slot]
        best_players = get_top_players(saved_roster, slot, num_players)
        best_lineup.extend(best_players)

        # Remove selected players from consideration for other slots
        for player in best_players:
            saved_roster.remove(player)

    return np.sum([player.points for player in best_lineup])


def get_best_trio(league: League, lineup: list):
    """Returns the the sum of the top QB/RB/Reciever trio for a team during the loaded week."""
    qb = get_top_players(lineup, "QB", 1)[0].points
    rb = get_top_players(lineup, "RB", 1)[0].points
    wr = get_top_players(lineup, "WR", 1)[0].points
    te = get_top_players(lineup, "TE", 1)[0].points
    best_trio = round(qb + rb + max(wr, te), 2)
    return best_trio


def get_lineup_efficiency(league: League, lineup: list):
    max_score = get_best_lineup(league, lineup)
    real_score = np.sum(
        [player.points for player in lineup if player.slot_position not in ("BE", "IR")]
    )
    return real_score / max_score


def get_weekly_finish(league: League, team: Team, week: int):
    """Returns the rank of a team compared to the rest of the league by points for (for the loaded week)"""
    league_scores = [tm.scores[week - 1] for tm in league.teams]
    league_scores = sorted(league_scores, reverse=True)
    return league_scores.index(team.scores[week - 1]) + 1


def get_num_out(league: League, lineup: list):
    """Returns the (esimated) number of players who did not play for a team for the loaded week (excluding IR slot players)."""
    num_out = 0
    # TODO: write new code based on if player was injured
    return num_out


def avg_slot_score(league: League, lineup: list, slot: str):
    """
    Returns the average score for starting players of a specified slot.
    `lineup` is either BoxScore().away_lineup or BoxScore().home_lineup (a list of BoxPlayers)
    """
    return np.mean([player.points for player in lineup if player.slot_position == slot])


def sum_bench_points(league: League, lineup: list):
    """
    Returns the total score for bench players
    `lineup` is either BoxScore().away_lineup or BoxScore().home_lineup (a list of BoxPlayers)
    """
    return np.sum([player.points for player in lineup if player.slot_position == "BE"])


""" ADVANCED STATS """


def get_weekly_luck_index(league: League, team: Team, week: int):
    """
    This function returns an index quantifying how 'lucky' a team was in a given week

    Luck index:
        70% probability of playing a team with a lower total
        20% your play compared to previous weeks
        10% opp's play compared to previous weeks
    """
    opp = team.schedule[week - 1]
    num_teams = len(league.teams)

    # Set weights
    w_sched = 7
    w_team = 2
    w_opp = 1

    # Luck Index based on where the team and its opponent finished compared to the rest of the league
    rank = get_weekly_finish(league, team, week)
    opp_rank = get_weekly_finish(league, opp, week)

    if rank < opp_rank:  # If the team won...
        # Odds of this team playing a team with a higher score than it
        luck_index = w_sched * (rank - 1) / (num_teams - 1)
    elif rank > opp_rank:  # If the team lost or tied...
        # Odds of this team playing a team with a lower score than it
        luck_index = -w_sched * (num_teams - rank) / (num_teams - 1)

    # If the team tied...
    elif rank < (num_teams / 2):
        # They are only half as unlucky, because tying is not as bad as losing
        luck_index = -w_sched / 2 * (num_teams - rank - 1) / (num_teams - 1)
    else:
        # They are only half as lucky, because tying is not as good as winning
        luck_index = w_sched / 2 * (rank - 1) / (num_teams - 1)

    # Update luck index based on how team played compared to normal
    team_score = team.scores[week - 1]
    team_avg = np.mean(team.scores[:week])
    team_std = np.std(team.scores[:week])
    if team_std != 0:
        # Get z-score of the team's performance
        z = (team_score - team_avg) / team_std

        # Noramlize the z-score so that a performance 2 std dev's away from the mean has an effect of 20% on the luck index
        z_norm = z / 2 * w_team
        luck_index += z_norm

    # Update luck index based on how opponent played compared to normal
    opp_score = opp.scores[week - 1]
    opp_avg = np.mean(opp.scores[:week])
    opp_std = np.std(opp.scores[:week])
    if team_std != 0:
        # Get z-score of the team's performance
        z = (opp_score - opp_avg) / opp_std

        # Noramlize the z-score so that a performance 2 std dev's away from the mean has an effect of 10% on the luck index
        z_norm = z / 2 * w_opp
        luck_index -= z_norm

    return luck_index / np.sum([w_sched, w_team, w_opp])


def get_season_luck_indices(league: League, week: int):
    """This function returns an index quantifying how 'lucky' a team was all season long (up to a certain week)"""
    luck_indices = {team: 0 for team in league.teams}
    for wk in range(1, week + 1):
        # Update luck_index for each team
        for team in league.teams:
            luck_indices[team] += get_weekly_luck_index(league, team, week)

    return luck_indices


def sort_lineups_by_func(league: League, week: int, func, box_scores=None, **kwargs):
    """
    Sorts league teams according to function.
    Values are sorted ascending.
    DOES NOT ACCOUNT FOR TIES
    """
    if box_scores is None:
        box_scores = league.box_scores(week)
    return sorted(
        league.teams,
        key=lambda x: func(league, get_lineup(league, x, week, box_scores), **kwargs),
    )


def get_leader_str(stats_list: list, high_first: bool = True):
    """Return a list of team owners who have the best stat,
    given a list of teams and stat values.

    Args:
        stats_list (list): list of teams and a stat value
          - Ex: [('Team 1', 103.7), ('Team 2', 83.7), ('Team 3', 98.8)]
        high_first (bool, optional): Are higher values better than lower values?. Defaults to True.

    Returns:
        str: List of team owners with the highest value
    """

    # Sort list
    sorted_stats_list = sorted(stats_list, key=lambda x: x[1], reverse=high_first)

    # Check if there is no tie
    if sorted_stats_list[0][1] != sorted_stats_list[1][1]:
        return sorted_stats_list[0][1], "{}".format(sorted_stats_list[0][0])

    # If there is a tie, return all teams tied for first
    else:
        leaders = [sorted_stats_list[0][0]]
        for i in range(1, len(sorted_stats_list)):
            if sorted_stats_list[i][1] == sorted_stats_list[i - 1][1]:
                leaders.append(sorted_stats_list[i][0])
            else:
                return sorted_stats_list[0][1], "{}".format(", ".join(leaders))


def make_ordinal(n):
    """
    Convert an integer into its ordinal representation::
        make_ordinal(3)   => '3rd'
        make_ordinal(122) => '122nd'
        make_ordinal(213) => '213th'
    """
    n = int(n)
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = ["th", "st", "nd", "rd", "th"][min(n % 10, 4)]
    return str(n) + suffix


def print_records(
    df: pd.DataFrame,
    year: int,
    week: int,
    stat: str,
    stat_units: str,
    high_first: bool = True,
    n: int = 5,
):
    """Print out any records.

    Args:
        df (pd.DataFrame): Historical stats dataframe
        year (int): Year to check for a record
        week (int): Week to check for a record
        stat (str): The stat of note ('team_score', 'QB_pts', etc.)
        stat_units (str): ('pts', 'pts/gm', etc.)
        high_first (bool): Are higher values better than lower values?. Defaults to True.
        n (int): How far down the record list to check (defaults to 5)
    """
    records_df = get_any_records(
        df=df, year=year, week=week, stat=stat, high_first=high_first, n=n
    )

    # Print out any records
    superlative = "highest" if high_first else "lowest"
    for (_, row) in records_df.iterrows():
        print(
            "{} had the {} {} {} ({:.2f} {}) in league history".format(
                row.team_owner,
                make_ordinal(row["rank"]),
                superlative,
                stat,
                row[stat],
                stat_units,
            )
        )


def print_franchise_records(
    df: pd.DataFrame,
    year: int,
    week: int,
    stat: str,
    stat_units: str,
    high_first: bool = True,
    n: int = 1,
):
    """Print out any franchise records.

    Args:
        df (pd.DataFrame): Historical stats dataframe
        year (int): Year to check for a record
        week (int): Week to check for a record
        stat (str): The stat of note ('team_score', 'QB_pts', etc.)
        stat_units (str): ('pts', 'pts/gm', etc.)
        high_first (bool): Are higher values better than lower values?. Defaults to True.
        n (int): How far down the record list to check (defaults to 5)
    """
    # Get a list of all active teams that have been in the league for 2+ years
    current_teams = df.query(f"year == {df.year.max()}").team_owner.unique()
    list_of_teams = df.groupby(["team_owner"]).nunique()
    list_of_teams = list_of_teams[
        (list_of_teams.year > 1) & list_of_teams.index.isin(current_teams)
    ].index.tolist()

    for team_owner in list_of_teams:
        # Get all rows for the given team
        team_df = df.query(f"team_owner == {team_owner}")

        # Get any records for that team
        records_df = get_any_records(
            df=team_df, year=year, week=week, stat=stat, high_first=high_first, n=n
        )

        # Print out any records
        superlative = "highest" if high_first else "lowest"
        for (_, row) in records_df.iterrows():
            print(
                "{} had the {} {} {} ({:.2f} {}) in franchise history".format(
                    row.team_owner,
                    make_ordinal(row["rank"]),
                    superlative,
                    stat,
                    row[stat],
                    stat_units,
                )
            )


def get_wins_leaderboard(df: pd.DataFrame):
    """Get the all time wins leaderboard for the league.

    Args:
        df (pd.DataFrame): Historical stats dataframe

    Returns:
        pd.Series: Ordered leaderboard by career wins
    """
    df = df.query(f"outcome == 'win' & is_meaningful_game == True")
    leaderboard_df = (
        df.groupby("team_owner")
        .count()["outcome"]
        .sort_values(ascending=False)
        .reset_index()
    )
    leaderboard_df.index += 1
    return leaderboard_df


def get_losses_leaderboard(df: pd.DataFrame):
    """Get the all time losses leaderboard for the league.

    Args:
        df (pd.DataFrame): Historical stats dataframe

    Returns:
        pd.Series: Ordered leaderboard by career wins
    """
    df = df.query(f"outcome == 'lose' & is_meaningful_game == True")
    leaderboard_df = (
        df.groupby("team_owner")
        .count()["outcome"]
        .sort_values(ascending=False)
        .reset_index()
    )
    leaderboard_df.index += 1
    return leaderboard_df


def leaderboard_change(
    df: pd.DataFrame, leaderboard_func: Callable = get_wins_leaderboard
):
    """This function takes a leaderboard function and calculates
    the change of that leaderboard from the previous week to the current week.

    I.e.: If the get_wins_leaderboard() function is passed in,

    The function will rank teams 1 - n from the previous week.
    Then the leaderboard will be updated with the outcomes of the current week.
    The function will return the change of each team.
    If Team A went from being the winningest team to the 2nd-most winningest team, they would have a change of -1.

    Args:
        df (pd.DataFrame): Historical stats dataframe
        leaderboard_func (Callable, optional): A leaderboard function. Defaults to get_wins_leaderboard.

    Returns:
        pd.DataFrame: A dataframe containing the current leaderboard, previousl eaderboard, and the difference
    """

    # Get current leaderboard
    current_leaderboard = leaderboard_func(df).reset_index()

    # Get leaderboard from last week
    last_week_df = exclude_most_recent_week(df)
    last_week_leaderboard = leaderboard_func(last_week_df).reset_index()

    # Merge the leaderboards on 'team_owner'
    leaderboard_change = (
        current_leaderboard.drop(columns=["outcome"])
        .merge(
            last_week_leaderboard.drop(columns=["outcome"]),
            on="team_owner",
            suffixes=("_current", "_last"),
        )
        .set_index("team_owner")
    )

    # Subtract the two weeks to find the change in leaderboard postioning
    leaderboard_change["change"] = (
        leaderboard_change.index_last - leaderboard_change.index_current
    )

    return leaderboard_change


def get_team(league: League, team_owner: str):
    """Get the Team object corresponding to the team_owner

    Args:
        league (League): League object containing the teams
        team_owner (str): Team owner to get Team object of

    Raises:
        Exception: If the team owner does not have a Team object in the league

    Returns:
        Team: Team object
    """
    for team in league.teams:
        if team.owner == team_owner:
            return team

    raise Exception(f"Owner {team_owner} not in league.")


def get_division_standings(league: League):
    standings = {}
    for division in league.settings.division_map.values():
        teams = [team for team in league.teams if team.division_name == division]
        standings[division] = sorted(teams, key=lambda x: x.standing)
    return standings


def game_of_the_week_stats(league: League, df: pd.DataFrame, owner1: str, owner2: str):
    gow_df = df.query(
        f"team_owner == {owner1} & opp_owner == {owner2} & is_meaningful_game == True"
    )
    gow_df.sort_values(["year", "week"], ascending=True, inplace=True)

    print(
        "{} has won {} / {} matchups.".format(
            owner1, len(gow_df.query(f"outcome == 'win'")), len(gow_df)
        )
    )
    print(
        "{} has won {} / {} matchups.".format(
            owner2, len(gow_df.query(f"outcome == 'lose'")), len(gow_df)
        )
    )
    print("There have been {} ties".format(len(gow_df.query(f"outcome == 'win'"))))

    last_matchup = gow_df.iloc[-1]
    print(
        "\nMost recent game: {:.0f} Week {:.0f}".format(
            last_matchup.year, last_matchup.week
        )
    )
    print(
        "{} {:.2f} - {:.2f} {}".format(
            last_matchup.team_owner,
            last_matchup.team_score,
            last_matchup.opp_score,
            last_matchup.opp_owner,
        )
    )

    team1 = get_team(league, owner1)
    team2 = get_team(league, owner2)
    division_standings = get_division_standings(league)
    print("\nThis season:\n-----------------------")
    print(f"{owner1} has a record of {team1.wins}-{team1.losses}-{team1.ties}")
    print(
        "They have averaged {:.2f} points per game.".format(
            df.query(
                f"team_owner == {owner1} & year == {league.year} & is_meaningful_game == True"
            ).team_score.mean()
        )
    )
    print(
        "{} is currently {}/{} in the {} division.".format(
            team1.team_name,
            division_standings[team1.division_name].index(team1) + 1,
            len(division_standings[team1.division_name]),
            team1.division_name,
        )
    )
    print()
    print(f"{owner2} has a record of {team2.wins}-{team2.losses}-{team2.ties}")
    print(
        "They have averaged {:.2f} points per game.".format(
            df.query(
                f"team_owner == {owner2} & year == {league.year} & is_meaningful_game == True"
            ).team_score.mean()
        )
    )
    print(
        "{} is currently {}/{} in the {} division.".format(
            team2.team_name,
            division_standings[team2.division_name].index(team2) + 1,
            len(division_standings[team2.division_name]),
            team2.division_name,
        )
    )


def weekly_stats_analysis(df: pd.DataFrame, year: int, week: int):

    df = df.query("is_meaningful_game == True")

    print("----------------------------------------------------------------")
    print(
        "|                        Week {:2.0f} Analysis                      |".format(
            week
        )
    )
    print("----------------------------------------------------------------")

    # Good awards
    print("League-wide POSITIVE stats\n--------------------------")
    print_records(
        df, year=year, week=week, stat="team_score", stat_units="pts", high_first=True
    )
    print_records(
        df,
        year=year,
        week=week,
        stat="team_score_adj",
        stat_units="pts",
        high_first=True,
    )
    print_records(
        df, year=year, week=week, stat="score_dif", stat_units="pts", high_first=True
    )
    print_records(
        df,
        year=year,
        week=week,
        stat="lineup_efficiency",
        stat_units="pts",
        high_first=True,
    )
    print_records(
        df, year=year, week=week, stat="best_trio", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="QB_pts", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="RB_pts", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="WR_pts", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="TE_pts", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="RB_WR_TE_pts", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="D_ST_pts", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="K_pts", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="bench_points", stat_units="pts", high_first=True
    )
    print_records(
        df, year=year, week=week, stat="streak", stat_units="pts", high_first=True
    )

    # Good franchise awards
    print("\n\nFranchise POSITIVE stats\n--------------------------")
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="team_score",
        stat_units="pts",
        high_first=True,
        n=3,
    )
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="team_score_adj",
        stat_units="pts",
        high_first=True,
        n=3,
    )
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="score_dif",
        stat_units="pts",
        high_first=True,
        n=3,
    )
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="lineup_efficiency",
        stat_units="pts",
        high_first=True,
    )
    print_franchise_records(
        df, year=year, week=week, stat="best_trio", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="QB_pts", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="RB_pts", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="WR_pts", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="TE_pts", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="RB_WR_TE_pts", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="D_ST_pts", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="K_pts", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="bench_points", stat_units="pts", high_first=True
    )
    print_franchise_records(
        df, year=year, week=week, stat="streak", stat_units="pts", high_first=True, n=3
    )

    # Bad awards
    print("\n\nLeague-wide NEGATIVE stats\n--------------------------")
    print_records(
        df, year=year, week=week, stat="team_score", stat_units="pts", high_first=False
    )
    print_records(
        df,
        year=year,
        week=week,
        stat="team_score_adj",
        stat_units="pts",
        high_first=False,
    )
    print_records(
        df,
        year=year,
        week=week,
        stat="lineup_efficiency",
        stat_units="pts",
        high_first=False,
    )
    print_records(
        df, year=year, week=week, stat="best_trio", stat_units="pts", high_first=False
    )
    print_records(
        df, year=year, week=week, stat="QB_pts", stat_units="pts", high_first=False
    )
    print_records(
        df, year=year, week=week, stat="RB_pts", stat_units="pts", high_first=False
    )
    print_records(
        df, year=year, week=week, stat="WR_pts", stat_units="pts", high_first=False
    )
    print_records(
        df, year=year, week=week, stat="TE_pts", stat_units="pts", high_first=False
    )
    print_records(
        df,
        year=year,
        week=week,
        stat="RB_WR_TE_pts",
        stat_units="pts",
        high_first=False,
    )
    print_records(
        df, year=year, week=week, stat="D_ST_pts", stat_units="pts", high_first=False
    )
    print_records(
        df, year=year, week=week, stat="K_pts", stat_units="pts", high_first=False
    )
    print_records(
        df,
        year=year,
        week=week,
        stat="bench_points",
        stat_units="pts",
        high_first=False,
    )
    print_records(
        df, year=year, week=week, stat="streak", stat_units="pts", high_first=False
    )

    # Bad franchise records
    print("\n\nFranchise NEGATIVE stats\n--------------------------")
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="team_score",
        stat_units="pts",
        high_first=False,
        n=3,
    )
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="team_score_adj",
        stat_units="pts",
        high_first=False,
        n=3,
    )
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="lineup_efficiency",
        stat_units="pts",
        high_first=False,
    )
    print_franchise_records(
        df, year=year, week=week, stat="best_trio", stat_units="pts", high_first=False
    )
    print_franchise_records(
        df, year=year, week=week, stat="QB_pts", stat_units="pts", high_first=False
    )
    print_franchise_records(
        df, year=year, week=week, stat="RB_pts", stat_units="pts", high_first=False
    )
    print_franchise_records(
        df, year=year, week=week, stat="WR_pts", stat_units="pts", high_first=False
    )
    print_franchise_records(
        df, year=year, week=week, stat="TE_pts", stat_units="pts", high_first=False
    )
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="RB_WR_TE_pts",
        stat_units="pts",
        high_first=False,
    )
    print_franchise_records(
        df, year=year, week=week, stat="D_ST_pts", stat_units="pts", high_first=False
    )
    print_franchise_records(
        df, year=year, week=week, stat="K_pts", stat_units="pts", high_first=False
    )
    print_franchise_records(
        df,
        year=year,
        week=week,
        stat="bench_points",
        stat_units="pts",
        high_first=False,
    )
    print_franchise_records(
        df, year=year, week=week, stat="streak", stat_units="pts", high_first=False, n=3
    )


def season_stats_analysis(league: League, df: pd.DataFrame, week: int = None):
    """Display season-bests and -worsts.

    Args:
        league (League): League object
        df (pd.DataFrame): Historical records dataframe
        week (int, optional): Maximum week to include. Defaults to None.
    """
    if week is None:
        week = df.query(f"year == {df.year.max()}").week.max()

    df = df.query("is_meaningful_game == True")
    df_current_year = df.query(f"year == {league.year}")
    df_current_week = df_current_year.query(f"week == {league.current_week - 1}")

    print("----------------------------------------------------------------")
    print(
        "|             Season {:2.0f} Analysis (through Week {:2.0f})           |".format(
            league.year, week
        )
    )
    print("----------------------------------------------------------------")

    # Good awards
    print(
        "Most wins this season              - {:.0f} wins - {}".format(
            *get_leader_str([(team.owner, team.wins) for team in league.teams])
        )
    )
    print(
        "Highest single game score          - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year[["team_owner", "team_score"]].values, high_first=True
            )
        )
    )
    print(
        "Highest average points this season - {:.0f} pts/gm - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner")
                .mean()["team_score"]
                .to_dict()
                .items()
            )
        )
    )
    print(
        "Longest active win streak          - {:.0f} gms - {}".format(
            *get_leader_str(
                df_current_week[["team_owner", "streak"]].values, high_first=True
            )
        )
    )
    print(
        "Longest win streak this season     - {:.0f} gms - {}".format(
            *get_leader_str(
                df_current_year[["team_owner", "streak"]].values, high_first=True
            )
        )
    )

    # Bad awards
    print()
    print(
        "Most losses this season           - {:.0f} losses - {}".format(
            *get_leader_str([(team.owner, team.losses) for team in league.teams])
        )
    )
    print(
        "Lowest single game score          - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year[["team_owner", "team_score"]].values, high_first=False
            )
        )
    )
    print(
        "Lowest average points this season - {:.0f} pts/gm - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner")
                .mean()["team_score"]
                .to_dict()
                .items(),
                high_first=False,
            )
        )
    )
    print(
        "Longest active loss streak        - {:.0f} gms - {}".format(
            *get_leader_str(
                df_current_week[["team_owner", "streak"]].values, high_first=False
            )
        )
    )
    print(
        "Longest loss streak this season   - {:.0f} gms - {}".format(
            *get_leader_str(
                df_current_year[["team_owner", "streak"]].values, high_first=False
            )
        )
    )

    print()
    print(
        "Most QB pts this season           - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["QB_pts"].to_dict().items(),
                high_first=True,
            )
        )
    )
    print(
        "Most RB pts this season           - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["RB_pts"].to_dict().items(),
                high_first=True,
            )
        )
    )
    print(
        "Most WR pts this season           - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["WR_pts"].to_dict().items(),
                high_first=True,
            )
        )
    )
    print(
        "Most TE pts this season           - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["TE_pts"].to_dict().items(),
                high_first=True,
            )
        )
    )
    print(
        "Most RB/WR/TE pts this season     - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner")
                .sum()["RB_WR_TE_pts"]
                .to_dict()
                .items(),
                high_first=True,
            )
        )
    )
    print(
        "Most D/ST pts this season         - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner")
                .sum()["D_ST_pts"]
                .to_dict()
                .items(),
                high_first=True,
            )
        )
    )
    print(
        "Most K pts this season            - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["K_pts"].to_dict().items(),
                high_first=True,
            )
        )
    )

    print()
    print(
        "Fewest QB pts this season         - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["QB_pts"].to_dict().items(),
                high_first=False,
            )
        )
    )
    print(
        "Fewest RB pts this season         - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["RB_pts"].to_dict().items(),
                high_first=False,
            )
        )
    )
    print(
        "Fewest WR pts this season         - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["WR_pts"].to_dict().items(),
                high_first=False,
            )
        )
    )
    print(
        "Fewest TE pts this season         - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["TE_pts"].to_dict().items(),
                high_first=False,
            )
        )
    )
    print(
        "Fewest RB/WR/TE pts this season   - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner")
                .sum()["RB_WR_TE_pts"]
                .to_dict()
                .items(),
                high_first=False,
            )
        )
    )
    print(
        "Fewest D/ST pts this season       - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner")
                .sum()["D_ST_pts"]
                .to_dict()
                .items(),
                high_first=False,
            )
        )
    )
    print(
        "Fewest K pts this season          - {:.0f} pts - {}".format(
            *get_leader_str(
                df_current_year.groupby("team_owner").sum()["K_pts"].to_dict().items(),
                high_first=False,
            )
        )
    )
