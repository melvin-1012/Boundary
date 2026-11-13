"""Read-only, evidence-backed question answering over curated cricket data."""

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from difflib import get_close_matches

import numpy as np
import pandas as pd

from analytics.cricket_metrics import calculate_player_metrics, rank_players


MIN_MATCHES = 3
MIN_PRESSURE_OPPORTUNITIES = 12
EVIDENCE_LIMIT = 200
SUPPORTED_QUESTION_CATEGORIES = {
    "pressure_ranking": "Best batter/bowler under pressure, pressure strike rate, or pressure economy.",
    "season_ranking": "Season-filtered batter/bowler ranks and leaders by season.",
    "format_comparison": "IPL versus T20I descriptive role-metric comparison.",
    "season_comparison": "Role-metric comparison across two requested seasons.",
    "player_comparison": "Two identified batters or two identified bowlers.",
    "player_profile": "Pressure versus normal performance and role metrics for a player.",
    "phase_analysis": "Powerplay, middle-over, or death-over filtered performance.",
    "consistency": "Most consistent eligible batters or bowlers.",
    "reliability": "Most reliable eligible batters or bowlers.",
    "ranking_comparison": (
        "Natural-language rank gaps, top-N rankings, ordinal rank selection, "
        "and comparison against eligible-player averages."
    ),
    "ranking_explanation": "Player rank, SPI, exposure, reliability, and calculation evidence.",
    "sample_analysis": "Pressure opportunities, sample eligibility, and reliability.",
    "season_trend": "Historical season-by-season role leaders.",
    "team_analysis": "Role-filtered player analysis for a mapped team.",
    "match_analysis": "Delivery-level pressure context for an explicit match ID.",
}
SQL_COMMAND = re.compile(
    r"^\s*(select|insert|update|delete|drop|alter|create|pragma|attach|detach)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Question:
    text: str
    intent: str
    role: str | None
    players: tuple[tuple[int, str], ...]
    season: str | None
    format: str | None
    competition: str | None
    phase: str | None
    match_id: int | None
    team: str | None
    compare_seasons: tuple[str, ...] | None = None
    ranking_metric: str | None = None
    ranking_comparison: str | None = None
    start_rank: int = 1
    result_count: int = 1


def _normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def resolve_players(question, deliveries):
    """Resolve unambiguous player names, surnames, or explicit numeric IDs."""
    player_rows = pd.concat(
        [
            deliveries[["striker_id", "striker_name"]].rename(
                columns={"striker_id": "player_id", "striker_name": "player_name"}
            ),
            deliveries[["bowler_id", "bowler_name"]].rename(
                columns={"bowler_id": "player_id", "bowler_name": "player_name"}
            ),
        ],
        ignore_index=True,
    ).dropna().drop_duplicates()
    player_rows["player_id"] = pd.to_numeric(
        player_rows["player_id"], errors="coerce"
    )
    player_rows = player_rows.dropna(subset=["player_id"])
    player_rows["player_id"] = player_rows["player_id"].astype("int64")
    normalized_question = f" {_normalize(question)} "
    found = {}
    explicit_ids = [
        int(value)
        for value in re.findall(
            r"\b(?:player\s*(?:id)?\s*#?\s*)(\d{1,8})\b",
            question,
            flags=re.IGNORECASE,
        )
    ]
    for player_id in explicit_ids:
        rows = player_rows.loc[player_rows["player_id"].eq(player_id)]
        if not rows.empty:
            found[player_id] = str(rows.iloc[0]["player_name"])
    full_matches = [
        row
        for row in player_rows.itertuples(index=False)
        if f" {_normalize(row.player_name)} " in normalized_question
    ]
    if full_matches:
        for row in full_matches:
            found[int(row.player_id)] = str(row.player_name)
    else:
        for row in player_rows.itertuples(index=False):
            name = str(row.player_name)
            normalized_name = _normalize(name)
            aliases = {normalized_name}
            tokens = normalized_name.split()
            if len(tokens) > 1:
                aliases.update({tokens[0], tokens[-1]})
                if len(tokens[-1]) >= 4:
                    aliases.add(" ".join([*(token[0] for token in tokens[:-1]), tokens[-1]]))
            if any(f" {alias} " in normalized_question for alias in aliases if alias):
                found.setdefault(int(row.player_id), name)
    return [(player_id, found[player_id]) for player_id in sorted(found)]


def _resolve_team(question, teams):
    if teams is None or teams.empty or "team_name" not in teams:
        return None
    normalized_question = f" {_normalize(question)} "
    names = sorted(teams["team_name"].dropna().astype(str).unique(), key=len, reverse=True)
    matches = [
        name for name in names
        if f" {_normalize(name)} " in normalized_question
    ]
    return matches[0] if matches else None


def parse_question(question, deliveries, teams=None):
    """Extract supported intent and filters; ask when the question is ambiguous."""
    text = str(question).strip()
    normalized = _normalize(text)
    players = tuple(resolve_players(text, deliveries))
    available_seasons = set(deliveries["season"].dropna().astype(str))
    requested_seasons = tuple(
        dict.fromkeys(
            year
            for year in re.findall(r"\b(?:19|20)\d{2}\b", text)
            if year in available_seasons
        )
    )
    is_format_comparison = "ipl" in normalized and "t20i" in normalized
    compare_seasons = (
        requested_seasons[:2]
        if len(requested_seasons) > 1
        and re.search(r"\b(compare|versus|vs\.?)\b", normalized)
        and not is_format_comparison
        else None
    )
    season = requested_seasons[0] if requested_seasons else None
    if compare_seasons:
        season = None
    has_year = re.search(r"\b(?:19|20)\d{2}\b", text)
    format_filter = None
    if re.search(r"\b(t20i|international)\b", normalized):
        format_filter = "T20I"
    elif re.search(r"\bipl\b", normalized):
        format_filter = "T20"
    if is_format_comparison:
        format_filter = None
    competition = None
    competitions = deliveries["comp_name"].dropna().astype(str).unique()
    for name in sorted(competitions, key=len, reverse=True):
        if _normalize(name) and f" {_normalize(name)} " in f" {normalized} ":
            competition = name
            break
    phase = None
    if re.search(r"\b(power ?play|powerplay|opening overs?)\b", normalized):
        phase = "powerplay"
    elif re.search(r"\b(death overs?|death-over|at the death)\b", normalized):
        phase = "death"
    elif re.search(r"\bmiddle overs?\b", normalized):
        phase = "middle"
    match_id_match = re.search(r"\bmatch\s*(?:id\s*)?#?\s*(\d{3,8})\b", text, re.I)
    match_id = int(match_id_match.group(1)) if match_id_match else None
    team = _resolve_team(text, teams)

    role = None
    if re.search(r"\b(bowler|bowlers|bowling|economy|wicket taker)\b", normalized):
        role = "bowler"
    if re.search(r"\b(batter|batters|batsman|batsmen|batting|strike rate)\b", normalized):
        if role is None:
            role = "batter"
    if role is None and re.search(r"\b(boundary|boundaries|runs|dismissal)\b", normalized):
        role = "batter"

    if re.search(r"\bindian\b|\bindia(n)? player\b", normalized):
        return Question(text, "ambiguous", role, players, season, format_filter, competition, phase, match_id, team)
    if SQL_COMMAND.search(text) or ";" in text or "--" in text:
        return Question(text, "unsupported", role, players, season, format_filter, competition, phase, match_id, team)

    if (
        is_format_comparison
        or (
            re.search(r"\b(compare|versus|vs\.?)\b", normalized)
            and (len(players) > 1 or compare_seasons)
        )
    ):
        if is_format_comparison:
            intent = "format_comparison"
        elif compare_seasons:
            intent = "season_comparison"
        else:
            intent = "player_comparison"
    elif match_id is not None or re.search(r"\bmatch[- ]level\b", normalized):
        intent = "match_analysis"
    elif re.search(r"\b(trend|over seasons|by season|each season|seasonal)\b", normalized):
        intent = "season_trend"
    elif team is not None and re.search(r"\b(team|for|players|analysis)\b", normalized):
        intent = "team_analysis"
    elif re.search(r"\b(why|explain|rank|ranking|spi)\b", normalized) and players:
        intent = "player_explanation"
    elif re.search(r"\b(consistent|consistency|reliable|reliability)\b", normalized):
        intent = "consistency" if "consistent" in normalized or "consistency" in normalized else "reliability"
    elif re.search(r"\b(sample size|opportunities|eligibility|eligible|exposure)\b", normalized):
        intent = "sample_analysis"
    elif re.search(r"\b(highest|best|top|most|rank|ranking|who leads)\b", normalized):
        intent = "ranking"
    elif players:
        intent = "player_profile"
    else:
        intent = "unsupported"

    ranking_comparison = None
    ranking_metric = None
    start_rank = 1
    result_count = 1
    ranking_terms = re.search(
        r"\b(difference|gap|ahead|better|top\s*(?:two|three|2|3)|"
        r"first\s+and\s+second|second\s+(?:best|most)|third\s+(?:best|most)|"
        r"average|overall|rank(?:s|ed|ing)?\s+first|top[- ]ranked)\b|"
        r"\bwhy\b.*\b(first|top|rank(?:ed|ing)?)\b",
        normalized,
    )
    if ranking_terms and not players and not is_format_comparison and not compare_seasons:
        intent = "ranking_comparison"
        ranking_metric = (
            "reliability"
            if re.search(r"\breliab(?:le|ility)\b", normalized)
            else "consistency"
            if re.search(r"\bconsistent|consistency\b", normalized)
            else "spi"
        )
        if re.search(r"\baverage\b", normalized):
            ranking_comparison = "top_vs_average"
            result_count = 1
        elif re.search(r"\b(difference|gap|ahead|better|first\s+and\s+second)\b", normalized):
            ranking_comparison = "top_gap"
            result_count = 2
        else:
            ranking_comparison = "top_n"
            ordinal = re.search(r"\b(second|2nd|third|3rd)\b", normalized)
            if ordinal:
                start_rank = 3 if ordinal.group(1) in {"third", "3rd"} else 2
            top_count = re.search(r"\btop\s*(two|three|2|3)\b", normalized)
            result_count = (
                {"two": 2, "2": 2, "three": 3, "3": 3}[top_count.group(1)]
                if top_count
                else 1
            )
            if ordinal and not top_count:
                result_count = 1
    elif (
        intent == "ranking"
        and role is None
        and re.search(r"\bpressure\b|\bunder pressure\b|\boverall\b", normalized)
    ):
        intent = "ranking_comparison"
        ranking_metric = "spi"
        ranking_comparison = "top_n"

    if has_year and season is None and not compare_seasons:
        intent = "ranking"
    if intent == "ranking" and role is None:
        return Question(text, "ambiguous", role, players, season, format_filter, competition, phase, match_id, team)
    if intent in {"player_comparison"} and len(players) != 2:
        return Question(text, "ambiguous", role, players, season, format_filter, competition, phase, match_id, team)
    if intent in {"player_profile", "player_explanation"} and len(players) != 1:
        if len(players) > 1:
            intent = "player_comparison"
            if len(players) != 2:
                intent = "ambiguous"
        else:
            intent = "ambiguous"
    if intent == "player_comparison" and role is None:
        intent = "ambiguous"
    if role is None and len(players) == 1:
        player_id = players[0][0]
        is_batter = pd.to_numeric(deliveries["striker_id"], errors="coerce").eq(player_id).any()
        is_bowler = pd.to_numeric(deliveries["bowler_id"], errors="coerce").eq(player_id).any()
        if is_batter != is_bowler:
            role = "batter" if is_batter else "bowler"
        elif intent in {"player_profile", "player_explanation"}:
            intent = "ambiguous"
    if intent in {"consistency", "reliability", "sample_analysis", "season_trend", "season_comparison", "team_analysis"} and role is None:
        return Question(text, "ambiguous", role, players, season, format_filter, competition, phase, match_id, team)
    if not any(term in normalized for term in ("pressure", "spi", "strike rate", "economy", "consistent", "reliability", "death", "powerplay")) and intent == "ranking":
        return Question(text, "ambiguous", role, players, season, format_filter, competition, phase, match_id, team)
    return Question(
        text,
        intent,
        role,
        players,
        season,
        format_filter,
        competition,
        phase,
        match_id,
        team,
        compare_seasons,
        ranking_metric,
        ranking_comparison,
        start_rank,
        result_count,
    )


def _filter_scope(question, deliveries, teams):
    scoped = deliveries
    normalized_text = _normalize(question.text)
    if "ipl" in normalized_text and "t20i" in normalized_text:
        scoped = scoped.loc[
            (
                scoped["match_format"].eq("T20")
                & scoped["comp_name"].astype(str).str.startswith("IPL")
            )
            | scoped["match_format"].eq("T20I")
        ]
    elif question.format:
        if question.format == "T20":
            scoped = scoped.loc[
                scoped["match_format"].eq("T20")
                & scoped["comp_name"].astype(str).str.startswith("IPL")
            ]
        else:
            scoped = scoped.loc[scoped["match_format"].eq(question.format)]
    if question.competition:
        scoped = scoped.loc[scoped["comp_name"].eq(question.competition)]
    if question.season is not None:
        scoped = scoped.loc[scoped["season"].astype(str).eq(question.season)]
    if question.phase:
        scoped = scoped.loc[scoped["innings_phase"].astype(str).str.casefold().eq(question.phase)]
    if question.team and teams is not None:
        pairs = teams.loc[
            teams["team_name"].astype(str).map(_normalize).eq(_normalize(question.team)),
            ["comp_id", "team_id"],
        ].drop_duplicates()
        if question.role == "bowler":
            team_key = "bowling_team_id"
        else:
            team_key = "batting_team_id"
        scoped = scoped.merge(
            pairs.rename(columns={"team_id": team_key}),
            on=["comp_id", team_key],
            how="inner",
            validate="many_to_one",
        )
    if question.match_id is not None:
        scoped = scoped.loc[scoped["match_id"].eq(question.match_id)]
    return scoped


def _safe_records(frame, limit=EVIDENCE_LIMIT):
    if frame is None or frame.empty:
        return []
    records = frame.head(limit).replace({np.nan: None}).to_dict("records")
    for row in records:
        for key, value in row.items():
            if isinstance(value, np.generic):
                row[key] = value.item()
    return records


def _role_columns(role):
    if role == "batter":
        return {
            "id": "striker_id",
            "name": "striker_name",
            "performance": "pressure_strike_rate",
            "normal": "normal_strike_rate",
            "runs": "pressure_runs",
            "opportunities": "pressure_opportunities",
            "match_evidence": "batter_matches",
        }
    return {
        "id": "bowler_id",
        "name": "bowler_name",
        "performance": "pressure_economy",
        "normal": "normal_economy",
        "runs": "pressure_runs",
        "opportunities": "pressure_opportunities",
        "match_evidence": "bowler_matches",
    }


def _verification(role, metrics_rows, evidence_rows, scoped):
    columns = _role_columns(role)
    id_column = columns["id"]
    valid_ids = set(
        pd.to_numeric(scoped[id_column], errors="coerce").dropna().astype(int)
    )
    valid_matches = set(scoped["match_id"].dropna().astype(int))
    if any(int(row["player_id"]) not in valid_ids for row in metrics_rows):
        return False, "A returned player ID is absent from the filtered source deliveries."
    if any(int(row["match_id"]) not in valid_matches for row in evidence_rows):
        return False, "An evidence match ID is absent from the filtered source deliveries."
    for row in evidence_rows:
        if row.get(id_column) is not None and int(row[id_column]) not in valid_ids:
            return False, "An evidence player ID is absent from the filtered source deliveries."
    for row in metrics_rows:
        player = scoped.loc[pd.to_numeric(scoped[id_column], errors="coerce").eq(int(row["player_id"]))]
        if role == "batter":
            pressure = player["is_batting_pressure"].fillna(False).astype(bool)
            faced = player["is_batter_ball_faced"].fillna(False).astype(bool)
            pressure_runs = player.loc[pressure, "batter_runs"].sum()
            pressure_balls = (pressure & faced).sum()
            normal = ~pressure & faced
            normal_runs = player.loc[normal, "batter_runs"].sum()
            normal_balls = normal.sum()
            performance = 100 * pressure_runs / pressure_balls if pressure_balls else np.nan
            baseline = 100 * normal_runs / normal_balls if normal_balls else np.nan
        else:
            pressure = player["is_bowling_pressure"].fillna(False).astype(bool)
            legal = player["is_legal_ball"].fillna(False).astype(bool)
            pressure_balls = (pressure & legal).sum()
            pressure_runs = player.loc[pressure, "bowler_conceded_runs"].sum()
            normal = ~pressure & legal
            normal_runs = player.loc[~pressure, "bowler_conceded_runs"].sum()
            normal_balls = normal.sum()
            performance = 6 * pressure_runs / pressure_balls if pressure_balls else np.nan
            baseline = 6 * normal_runs / normal_balls if normal_balls else np.nan
        if pd.notna(row.get("performance")) and not np.isclose(
            float(row["performance"]), performance, rtol=1e-8, atol=1e-8
        ):
            return False, f"Pressure performance verification failed for player ID {row['player_id']}."
        if pd.notna(row.get("normal_baseline")) and not np.isclose(
            float(row["normal_baseline"]), baseline, rtol=1e-8, atol=1e-8
        ):
            return False, f"Normal baseline verification failed for player ID {row['player_id']}."
    return True, "Player IDs, match evidence, pressure rates, and normal baselines match filtered deliveries."


def _metric_rows(metrics, role, question):
    role_data = metrics["batters" if role == "batter" else "bowlers"].copy()
    columns = _role_columns(role)
    if question.intent == "sample_analysis":
        if question.players:
            role_data = role_data.loc[
                role_data[columns["id"]].isin(
                    [player_id for player_id, _ in question.players]
                )
            ]
        role_data["eligible"] = (
            role_data["pressure_matches"].ge(MIN_MATCHES)
            & role_data["pressure_opportunities"].ge(MIN_PRESSURE_OPPORTUNITIES)
        )
        role_data = role_data.sort_values(
            ["pressure_opportunities", "pressure_matches"],
            ascending=[False, False],
            kind="stable",
        ).head(10)
        role_data["rank"] = np.arange(1, len(role_data) + 1)
        return role_data
    if question.intent in {
        "ranking",
        "consistency",
        "reliability",
        "ranking_comparison",
        "sample_analysis",
        "player_explanation",
        "player_comparison",
    }:
        if question.intent == "player_explanation" and question.players:
            pass
        ranked = rank_players(metrics, role)
        custom_order = False
        if question.intent == "consistency":
            ranked = ranked.sort_values("consistency", ascending=False, kind="stable")
            custom_order = True
        elif question.intent == "reliability":
            ranked = ranked.sort_values("reliability", ascending=False, kind="stable")
            custom_order = True
        elif question.intent == "ranking":
            query = _normalize(question.text)
            if role == "batter" and "strike rate" in query:
                ranked = ranked.sort_values("pressure_strike_rate", ascending=False)
                custom_order = True
            elif role == "bowler" and "economy" in query:
                ascending = "highest" not in query
                ranked = ranked.sort_values("pressure_economy", ascending=ascending)
                custom_order = True
        if question.players:
            ranked = ranked.loc[ranked["player_id"].isin([player[0] for player in question.players])]
        ranked = ranked.head(10).copy()
        if custom_order:
            ranked["rank"] = np.arange(1, len(ranked) + 1)
        return ranked

    if question.players:
        role_data = role_data.loc[
            role_data[columns["id"]].isin([player_id for player_id, _ in question.players])
        ]
    return role_data.sort_values(
        ["pressure_opportunities", columns["performance"]],
        ascending=[False, role == "bowler"],
        kind="stable",
        na_position="last",
    ).head(10)


def _validated_interpretation(
    parsed, question_text, deliveries, teams, candidates, baseline
):
    if not isinstance(parsed, dict):
        return None
    valid_intents = {
        "ranking",
        "player_profile",
        "player_explanation",
        "player_comparison",
        "format_comparison",
        "season_comparison",
        "season_trend",
        "team_analysis",
        "consistency",
        "reliability",
        "sample_analysis",
        "match_analysis",
        "ambiguous",
        "unsupported",
    }
    intent = parsed.get("intent")
    role = parsed.get("role")
    if intent not in valid_intents or role not in {None, "batter", "bowler"}:
        return None
    if baseline.role is not None and role != baseline.role:
        return None
    candidate_ids = {player_id: name for player_id, name in candidates}
    player_ids = parsed.get("player_ids", [])
    if not isinstance(player_ids, list) or any(
        isinstance(player_id, bool)
        or not isinstance(player_id, int)
        or player_id not in candidate_ids
        for player_id in player_ids
    ):
        return None
    players = tuple((player_id, candidate_ids[player_id]) for player_id in player_ids)
    if baseline.players and set(player_ids) != {
        player_id for player_id, _ in baseline.players
    }:
        return None
    if intent in {"player_profile", "player_explanation"} and len(players) != 1:
        return None
    if intent == "player_comparison" and (len(players) != 2 or role is None):
        return None
    if intent == "ranking" and role is None:
        return None
    if intent in {
        "season_trend",
        "season_comparison",
        "team_analysis",
        "consistency",
        "reliability",
        "sample_analysis",
    } and role is None:
        return None

    seasons = set(deliveries["season"].dropna().astype(str))
    season = parsed.get("season")
    if season is not None and str(season) not in seasons:
        return None
    if (str(season) if season is not None else None) != baseline.season:
        return None
    season = str(season) if season is not None else None
    compare_seasons = parsed.get("compare_seasons")
    if compare_seasons is not None:
        if (
            not isinstance(compare_seasons, list)
            or any(str(value) not in seasons for value in compare_seasons)
        ):
            return None
        compare_seasons = tuple(str(value) for value in compare_seasons)
    if compare_seasons != baseline.compare_seasons:
        return None
    if compare_seasons and intent != "season_comparison":
        return None
    available_formats = set(deliveries["match_format"].dropna().astype(str))
    format_name = parsed.get("format")
    if format_name is not None and format_name not in available_formats:
        return None
    if format_name != baseline.format:
        return None
    phase = parsed.get("phase")
    if phase not in {None, "powerplay", "middle", "death"}:
        return None
    if phase != baseline.phase:
        return None
    competitions = set(deliveries["comp_name"].dropna().astype(str))
    competition = parsed.get("competition")
    if competition is not None and competition not in competitions:
        return None
    if competition != baseline.competition:
        return None
    match_id = parsed.get("match_id")
    if match_id is not None:
        if isinstance(match_id, bool) or not isinstance(match_id, int):
            return None
        if not deliveries["match_id"].eq(match_id).any():
            return None
    if match_id != baseline.match_id:
        return None
    team = parsed.get("team")
    if team is not None:
        known_teams = (
            set(teams["team_name"].dropna().astype(str))
            if teams is not None and "team_name" in teams
            else set()
        )
        if team not in known_teams:
            return None
    if team != baseline.team:
        return None
    return Question(
        text=question_text,
        intent=intent,
        role=role,
        players=players,
        season=season,
        format=format_name,
        competition=competition,
        phase=phase,
        match_id=match_id,
        team=team,
        compare_seasons=compare_seasons,
    )


def analyze_question(question_text, deliveries, teams=None, provider=None):
    """Calculate an answer from filtered curated rows; return traceable evidence."""
    if deliveries.empty:
        return {
            "status": "insufficient",
            "intent": "unsupported",
            "question": question_text,
            "answer": "The historical delivery dataset is empty, so this question cannot be answered.",
            "scope": {},
            "metrics": [],
            "evidence": [],
            "limitations": ["No source delivery rows were provided."],
        }
    question = parse_question(question_text, deliveries, teams)
    if (
        provider is not None
        and question.intent not in {"ambiguous"}
        and not re.search(r"\bindian\b", _normalize(question_text))
        and not SQL_COMMAND.search(str(question_text))
        and ";" not in str(question_text)
        and "--" not in str(question_text)
    ):
        candidates = resolve_players(question_text, deliveries)
        context = {
            "allowed_intents": [
                "ranking", "player_profile", "player_explanation",
                "player_comparison", "format_comparison", "season_comparison", "season_trend",
                "team_analysis", "consistency", "reliability", "sample_analysis",
                "ranking_comparison",
                "match_analysis", "ambiguous", "unsupported",
            ],
            "allowed_roles": ["batter", "bowler", None],
            "allowed_seasons": sorted(deliveries["season"].dropna().astype(str).unique()),
            "compare_seasons": question.compare_seasons,
            "allowed_formats": sorted(deliveries["match_format"].dropna().astype(str).unique()),
            "allowed_competitions": sorted(deliveries["comp_name"].dropna().astype(str).unique()),
            "allowed_phases": ["powerplay", "middle", "death", None],
            "allowed_teams": (
                sorted(teams["team_name"].dropna().astype(str).unique())
                if teams is not None and "team_name" in teams
                else []
            ),
            "candidate_players": [
                {"player_id": player_id, "player_name": name}
                for player_id, name in candidates
            ],
        }
        interpreted = provider.interpret_question(question_text, context)
        validated = _validated_interpretation(
            interpreted, question_text, deliveries, teams, candidates, question
        )
        if validated is not None:
            question = validated
    if question.intent == "ambiguous":
        if re.search(r"\bindian\b", _normalize(question.text)):
            options = [
                "Indian players in the supplied competitions",
                "Players in IPL 2025",
                "Players in T20I matches during 2025",
                "Matches held in India",
            ]
        elif question.role is None:
            options = [
                "Best overall performance",
                "Best pressure performance",
                "Highest pressure strike rate / best pressure economy",
                "Most consistent or most reliable",
            ]
        elif len(question.players) != 2 and re.search(r"\b(compare|versus|vs)\b", _normalize(question.text)):
            options = ["Provide exactly two player names or IDs to compare"]
        elif len(question.players) == 2:
            options = ["Compare batting performance", "Compare bowling performance"]
        else:
            options = ["Specify the role (batter or bowler) and the metric to optimize"]
        return {
            "status": "clarification",
            "intent": question.intent,
            "question": question_text,
            "answer": "I need one clarification before calculating a result.",
            "clarification_options": options,
            "scope": {},
            "metrics": [],
            "evidence": [],
            "limitations": ["No ranking was calculated for an ambiguous request."],
        }
    if question.intent == "unsupported":
        return {
            "status": "unsupported",
            "intent": question.intent,
            "question": question_text,
            "answer": (
                "This request is not supported by the read-only cricket analytics. "
                "No SQL or database command was executed."
            ),
            "scope": {},
            "metrics": [],
            "evidence": [],
            "limitations": ["The analyst supports only documented historical metrics and filters."],
        }

    scoped = _filter_scope(question, deliveries, teams)
    if scoped.empty:
        return {
            "status": "insufficient",
            "intent": question.intent,
            "question": question_text,
            "answer": "No source records match the requested competition, season, phase, team, player, or match.",
            "scope": {
                "season": question.season,
                "format": question.format,
                "competition": question.competition,
                "phase": question.phase,
                "match_id": question.match_id,
            },
            "metrics": [],
            "evidence": [],
            "limitations": ["No matching historical source rows exist in the supplied dataset."],
        }
    scope = {
        "season": question.season,
        "format": question.format,
        "competition": question.competition,
        "phase": question.phase,
        "team": question.team,
        "match_id": question.match_id,
        "matches": int(scoped["match_id"].nunique()),
        "deliveries": int(len(scoped)),
        "competitions": sorted(scoped["comp_name"].dropna().astype(str).unique().tolist()),
        "seasons": sorted(scoped["season"].dropna().astype(str).unique().tolist()),
    }

    comparison_results = None
    if question.intent == "ranking_comparison":
        roles = [question.role] if question.role else ["batter", "bowler"]
        sort_by = question.ranking_metric or "spi"
        comparison_type = question.ranking_comparison or "top_n"
        start_rank = question.start_rank
        count = question.result_count
        if comparison_type == "top_gap":
            start_rank, count = 1, 2
        elif comparison_type == "top_vs_average":
            start_rank, count = 1, 1
        metric_rows = []
        evidence_rows = []
        comparisons = {}
        role_limitations = []
        verification_notes = []
        for role in roles:
            calculated = calculate_player_metrics(scoped)
            eligible = rank_players(calculated, role)
            if eligible.empty:
                role_limitations.append(
                    f"No {role} in this scope satisfies the existing pressure-match "
                    "and opportunity eligibility rules."
                )
                comparisons[role] = {
                    "status": "insufficient",
                    "eligible_count": 0,
                    "players": [],
                    "comparison": None,
                }
                continue
            ranked = eligible.sort_values(
                [sort_by, "rank"],
                ascending=[False, True],
                kind="stable",
            ).copy()
            ranked["rank"] = np.arange(1, len(ranked) + 1)
            selected = ranked.iloc[start_rank - 1 : start_rank - 1 + count].copy()
            columns = _role_columns(role)
            players = []
            verification_rows = []
            for row in selected.to_dict("records"):
                player_id = int(row[columns["id"]])
                player_record = {
                    "role": role,
                    "rank": int(row["rank"]),
                    "player_id": player_id,
                    "player_name": str(row[columns["name"]]),
                    "SPI": row.get("spi"),
                    "ranking_metric": sort_by,
                    "ranking_score": row.get(sort_by),
                    "performance_component": row.get("performance_component"),
                    "consistency": row.get("consistency"),
                    "reliability": row.get("reliability"),
                    "pressure_performance": row.get(columns["performance"]),
                    "normal_baseline": row.get(columns["normal"]),
                    "competition_adjusted_difference": row.get(
                        "competition_adjusted_difference"
                    ),
                    "pressure_matches": row.get("pressure_matches"),
                    "pressure_opportunities": row.get("pressure_opportunities"),
                    "matches": row.get("matches"),
                    "uncertainty_indicator": row.get("uncertainty_indicator"),
                }
                players.append(player_record)
                verification_rows.append(
                    {
                        "player_id": player_id,
                        "performance": row.get(columns["performance"]),
                        "normal_baseline": row.get(columns["normal"]),
                    }
                )
            player_ids = [row["player_id"] for row in players]
            role_evidence = calculated[columns["match_evidence"]]
            role_evidence = role_evidence.loc[
                role_evidence[columns["id"]].isin(player_ids)
            ]
            role_evidence_records = _safe_records(role_evidence)
            verified, verification_note = _verification(
                role, verification_rows, role_evidence_records, scoped
            )
            if not verified:
                return {
                    "status": "verification_failed",
                    "intent": question.intent,
                    "question": question_text,
                    "answer": "The ranking comparison failed source-record verification and is withheld.",
                    "scope": scope,
                    "metrics": [],
                    "evidence": [],
                    "limitations": [verification_note],
                }
            verification_notes.append(verification_note)
            evidence_rows.extend(role_evidence_records)
            if comparison_type == "top_gap":
                difference = (
                    players[0]["ranking_score"] - players[1]["ranking_score"]
                    if len(players) > 1
                    else None
                )
                comparison = {
                    "metric": sort_by,
                    "first_minus_second": difference,
                    "component_differences": (
                        {
                            metric: (
                                players[0][metric] - players[1][metric]
                                if players[0][metric] is not None
                                and players[1][metric] is not None
                                else None
                            )
                            for metric in (
                                "performance_component",
                                "consistency",
                                "reliability",
                            )
                        }
                        if len(players) > 1
                        else None
                    ),
                    "interpretation": (
                        "Descriptive score difference only; this is not a statistical "
                        "significance test."
                    ),
                }
            elif comparison_type == "top_vs_average":
                average = float(ranked[sort_by].mean())
                comparison = {
                    "metric": sort_by,
                    "eligible_player_average": average,
                    "first_minus_average": (
                        players[0]["ranking_score"] - average if players else None
                    ),
                    "eligible_player_count": int(len(ranked)),
                }
            else:
                comparison = {
                    "metric": sort_by,
                    "adjacent_score_gaps": [
                        {
                            "higher_rank": first["rank"],
                            "lower_rank": second["rank"],
                            "difference": first["ranking_score"] - second["ranking_score"],
                        }
                        for first, second in zip(players, players[1:])
                    ],
                }
            comparisons[role] = {
                "status": "answer" if len(players) == count else "insufficient",
                "eligible_count": int(len(ranked)),
                "players": players,
                "comparison": comparison,
                "sample_support": {
                    "mean_reliability": (
                        float(np.mean([row["reliability"] for row in players]))
                        if players
                        else None
                    ),
                    "combined_pressure_opportunities": int(
                        sum(row["pressure_opportunities"] for row in players)
                    ),
                    "minimum_pressure_matches": (
                        int(min(row["pressure_matches"] for row in players))
                        if players
                        else None
                    ),
                    "maximum_uncertainty_indicator": (
                        float(max(row["uncertainty_indicator"] for row in players))
                        if players
                        else None
                    ),
                },
            }
            metric_rows.extend(players)
            if len(players) < count:
                role_limitations.append(
                    f"Only {len(players)} eligible {role}(s) are available for the requested ranking."
                )

        supported_roles = [
            (role, data.get("sample_support", {}).get("mean_reliability"))
            for role, data in comparisons.items()
            if data.get("sample_support", {}).get("mean_reliability") is not None
        ]
        more_supported_role = (
            max(supported_roles, key=lambda item: item[1])[0]
            if len(supported_roles) > 1
            else None
        )
        comparisons["relative_comparison_support"] = {
            "more_supported_role": more_supported_role,
            "basis": (
                "Higher mean existing sample-reliability score across selected "
                "players; descriptive exposure support, not a formal confidence "
                "or significance test."
            ),
        }
        return {
            "status": "answer" if metric_rows else "insufficient",
            "intent": question.intent,
            "question": question_text,
            "answer": (
                "Rankings use the existing eligible pressure SPI and are calculated "
                "separately for batters and bowlers. Score gaps are descriptive, not "
                "statistical significance tests."
                if metric_rows
                else "No eligible players were found for the requested ranking."
            ),
            "scope": {
                **scope,
                "ranking_metric": sort_by,
                "ranking_comparison": comparison_type,
                "roles_ranked_separately": True,
            },
            "metrics": _safe_records(pd.DataFrame(metric_rows), 20),
            "comparison_results": comparisons,
            "evidence": evidence_rows[:EVIDENCE_LIMIT],
            "verification": " ".join(dict.fromkeys(verification_notes)),
            "limitations": [
                "Existing pressure labels, SPI formula, and eligibility rules are unchanged and remain provisional.",
                *(
                    ["A score gap is descriptive; the available methodology does not define a statistical significance test."]
                    if comparison_type == "top_gap"
                    else []
                ),
                *role_limitations,
            ],
        }
    elif question.intent == "format_comparison":
        if question.role is None:
            return {
                "status": "clarification",
                "intent": question.intent,
                "question": question_text,
                "answer": "Should the IPL-versus-T20I comparison focus on batters or bowlers?",
                "clarification_options": ["Batters", "Bowlers"],
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": [],
            }
        format_frames = []
        evidence_frames = []
        format_limitations = []
        for format_name, format_frame in scoped.groupby("match_format"):
            calculated = calculate_player_metrics(format_frame)
            role_columns = _role_columns(question.role)
            ranked = rank_players(calculated, question.role)
            if ranked.empty:
                format_label = (
                    "IPL"
                    if format_name == "T20"
                    and format_frame["comp_name"].astype(str).str.startswith("IPL").all()
                    else format_name
                )
                format_limitations.append(
                    f"No {question.role} in {format_label} satisfies the existing SPI "
                    "eligibility rules for this scope."
                )
                continue
            ranked = ranked.head(10)
            ranked["format"] = format_name
            ranked["player_id"] = ranked[role_columns["id"]].astype("int64")
            ranked["player_name"] = ranked[role_columns["name"]].astype(str)
            ranked["performance"] = ranked[role_columns["performance"]]
            ranked["normal_baseline"] = ranked[role_columns["normal"]]
            format_frames.append(
                ranked[
                    [
                        column for column in (
                            "format", "rank", "player_id", "player_name", "SPI", "spi",
                            "performance", "normal_baseline", "pressure_opportunities",
                            "pressure_matches", "reliability", "competition_coverage",
                        ) if column in ranked
                    ]
                ]
            )
            evidence_frame = calculated[role_columns["match_evidence"]]
            selected = ranked["player_id"].dropna().astype(int).unique().tolist()
            evidence_frames.append(
                evidence_frame.loc[evidence_frame[role_columns["id"]].isin(selected)]
                .assign(format=format_name)
            )
        metric_rows = pd.concat(format_frames, ignore_index=True) if format_frames else pd.DataFrame()
        evidence = _safe_records(
            pd.concat(evidence_frames, ignore_index=True) if evidence_frames else pd.DataFrame()
        )
        if metric_rows.empty:
            return {
                "status": "insufficient",
                "intent": question.intent,
                "question": question_text,
                "answer": (
                    "The requested format-specific ranking cannot be calculated "
                    "because no players meet the existing eligibility rules."
                ),
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": [
                    "Eligibility thresholds and SPI methodology were not changed.",
                    *format_limitations,
                ],
            }
        answer = (
            f"Compared {question.role} rankings separately across the eligible "
            "format-specific records. Player results are not pooled across formats."
        )
        metric_records = _safe_records(metric_rows, 20)
        evidence_records = evidence
        verification_notes = []
        for format_name in metric_rows["format"].dropna().unique():
            verified, note = _verification(
                question.role,
                [row for row in metric_records if row.get("format") == format_name],
                [row for row in evidence_records if row.get("format") == format_name],
                scoped.loc[scoped["match_format"].eq(format_name)],
            )
            if not verified:
                return {
                    "status": "verification_failed",
                    "intent": question.intent,
                    "question": question_text,
                    "answer": "The format comparison did not pass source-record verification and is withheld.",
                    "scope": scope,
                    "metrics": [],
                    "evidence": [],
                    "limitations": [note],
                }
            verification_notes.append(note)
        verification_note = " ".join(dict.fromkeys(verification_notes))
        if re.search(r"\b(difference|gap|ahead|better)\b", _normalize(question.text)):
            leaders = metric_rows.sort_values("rank", kind="stable").drop_duplicates("format")
            leaders = leaders.set_index("format")
            if (
                "T20" in leaders.index
                and "T20I" in leaders.index
                and pd.notna(leaders.loc["T20", "spi"])
                and pd.notna(leaders.loc["T20I", "spi"])
            ):
                difference = float(leaders.loc["T20", "spi"] - leaders.loc["T20I", "spi"])
                comparison_results = {
                    "ranking_metric": "spi",
                    "IPL_leader": {
                        "player_id": int(leaders.loc["T20", "player_id"]),
                        "player_name": leaders.loc["T20", "player_name"],
                        "SPI": float(leaders.loc["T20", "spi"]),
                    },
                    "T20I_leader": {
                        "player_id": int(leaders.loc["T20I", "player_id"]),
                        "player_name": leaders.loc["T20I", "player_name"],
                        "SPI": float(leaders.loc["T20I", "spi"]),
                    },
                    "IPL_minus_T20I_SPI": difference,
                    "interpretation": (
                        "Descriptive difference between each format's eligible "
                        "leader; format-specific leaderboards are not pooled."
                    ),
                }
    elif question.intent == "season_comparison":
        if question.role is None:
            return {
                "status": "clarification",
                "intent": question.intent,
                "question": question_text,
                "answer": "Should the season comparison focus on batting or bowling?",
                "clarification_options": ["Batters", "Bowlers"],
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": [],
            }
        role_columns = _role_columns(question.role)
        season_rows = []
        evidence_frames = []
        verification_notes = []
        for season in question.compare_seasons or ():
            season_frame = scoped.loc[scoped["season"].astype(str).eq(season)]
            if season_frame.empty:
                continue
            calculated = calculate_player_metrics(season_frame)
            raw = calculated["batters" if question.role == "batter" else "bowlers"]
            ranked = rank_players(calculated, question.role)
            if question.players:
                selected_ids = [player_id for player_id, _ in question.players]
                selected = raw.loc[raw[role_columns["id"]].isin(selected_ids)].copy()
                rank_columns = [
                    column
                    for column in (
                        "player_id", "rank", "spi", "reliability",
                        "uncertainty_indicator",
                    )
                    if column in ranked
                ]
                if len(rank_columns) > 1:
                    selected = selected.merge(
                        ranked[rank_columns].drop_duplicates("player_id"),
                        left_on=role_columns["id"],
                        right_on="player_id",
                        how="left",
                        validate="many_to_one",
                    )
            elif ranked.empty:
                selected = raw.sort_values(
                    [role_columns["performance"], "pressure_opportunities"],
                    ascending=[question.role == "bowler", False],
                    kind="stable",
                    na_position="last",
                ).head(10).copy()
            else:
                selected = ranked.head(10).copy()
            ids = selected[role_columns["id"]].dropna().astype(int).unique().tolist()
            for _, row in selected.iterrows():
                eligible = (
                    row["pressure_matches"] >= MIN_MATCHES
                    and row["pressure_opportunities"] >= MIN_PRESSURE_OPPORTUNITIES
                )
                season_rows.append(
                    {
                        "season": season,
                        "rank": row.get("rank"),
                        "player_id": int(row[role_columns["id"]]),
                        "player_name": str(row[role_columns["name"]]),
                        "performance": row[role_columns["performance"]],
                        "normal_baseline": row[role_columns["normal"]],
                        "pressure_opportunities": int(row["pressure_opportunities"]),
                        "pressure_matches": int(row["pressure_matches"]),
                        "SPI": row.get("spi"),
                        "reliability": row.get("reliability"),
                        "eligible": bool(eligible),
                    }
                )
            evidence_frame = calculated[role_columns["match_evidence"]]
            season_evidence = evidence_frame.loc[
                evidence_frame[role_columns["id"]].isin(ids)
            ].assign(season=season)
            evidence_records = _safe_records(season_evidence)
            season_metric_records = [
                row for row in season_rows if row["season"] == season
            ]
            verified, note = _verification(
                question.role, season_metric_records, evidence_records, season_frame
            )
            if not verified:
                return {
                    "status": "verification_failed",
                    "intent": question.intent,
                    "question": question_text,
                    "answer": "The season comparison did not pass source-record verification and is withheld.",
                    "scope": scope,
                    "metrics": [],
                    "evidence": [],
                    "limitations": [note],
                }
            verification_notes.append(note)
            evidence_frames.append(season_evidence)
        metric_rows = pd.DataFrame(season_rows)
        if metric_rows.empty:
            return {
                "status": "insufficient",
                "intent": question.intent,
                "question": question_text,
                "answer": "No source records match the requested seasons and filters.",
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": ["One or both requested seasons have no matching observations."],
            }
        evidence = _safe_records(
            pd.concat(evidence_frames, ignore_index=True) if evidence_frames else pd.DataFrame()
        )
        verification_note = " ".join(dict.fromkeys(verification_notes))
        answer = (
            f"Compared {question.role} pressure performance across "
            f"{' and '.join(question.compare_seasons or ())}. Each season is "
            "calculated independently; a missing or ineligible sample is not "
            "treated as a final ranking."
        )
    elif question.intent == "match_analysis":
        if question.match_id is None:
            return {
                "status": "clarification",
                "intent": question.intent,
                "question": question_text,
                "answer": "Provide a match ID from the supplied archive.",
                "clarification_options": ["Example: match 34429"],
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": [],
            }
        pressure_column = "batting_pressure" if question.role != "bowler" else "bowling_pressure"
        pressure_flag = "is_batting_pressure" if question.role != "bowler" else "is_bowling_pressure"
        metric_rows = scoped.sort_values(pressure_column, ascending=False).head(20).copy()
        metric_rows["pressure_role"] = "batting" if question.role != "bowler" else "bowling"
        metric_rows["player_id"] = (
            metric_rows["striker_id"] if question.role != "bowler" else metric_rows["bowler_id"]
        )
        metric_rows["player_name"] = (
            metric_rows["striker_name"] if question.role != "bowler" else metric_rows["bowler_name"]
        )
        metric_rows["pressure_score"] = metric_rows[pressure_column]
        metric_rows["pressure_event"] = metric_rows[pressure_flag]
        evidence = metric_rows[
            [
                "match_id", "innings", "innings_ball_num", "comp_name", "season",
                "player_id", "player_name", "score_before", "wickets_before",
                "balls_remaining", "target", "required_run_rate", "pressure_score",
                "pressure_event",
            ]
        ].to_dict("records")
        metric_rows = metric_rows[
            [
                "match_id", "innings", "innings_ball_num", "player_id", "player_name",
                "score_before", "wickets_before", "balls_remaining", "target",
                "required_run_rate", "pressure_score", "pressure_event",
            ]
        ]
        answer = (
            f"Match {question.match_id} has {len(scoped):,} recorded deliveries. "
            "The table lists the highest-scoring pre-delivery pressure states; "
            "both the score and pressure-event flag are shown."
        )
        return {
            "status": "answer",
            "intent": question.intent,
            "question": question_text,
            "answer": answer,
            "scope": scope,
            "metrics": _safe_records(metric_rows, 20),
            "evidence": _safe_records(pd.DataFrame(evidence), 20),
            "metric_columns": list(metric_rows.columns),
            "evidence_columns": list(pd.DataFrame(evidence).columns),
            "limitations": [
                "Match pressure scores are provisional heuristics, not win probabilities."
            ],
        }
    elif question.intent == "season_trend":
        if question.role is None:
            return {
                "status": "clarification",
                "intent": question.intent,
                "question": question_text,
                "answer": "Should the season trend focus on batting or bowling?",
                "clarification_options": ["Batters", "Bowlers"],
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": [],
            }
        role_columns = _role_columns(question.role)
        trend_rows = []
        evidence_frames = []
        for season, season_frame in scoped.groupby("season", dropna=True):
            calculated = calculate_player_metrics(season_frame)
            summary = rank_players(calculated, question.role).head(1)
            if summary.empty:
                summary = calculated["batters" if question.role == "batter" else "bowlers"]
                summary = summary.sort_values(
                    [role_columns["performance"], "pressure_opportunities"],
                    ascending=[question.role == "bowler", False],
                    kind="stable",
                    na_position="last",
                ).head(1)
            if not summary.empty:
                row = summary.iloc[0]
                trend_rows.append(
                    {
                        "season": str(season),
                        "player_id": int(row[role_columns["id"]]),
                        "player_name": str(row[role_columns["name"]]),
                        "performance": row[role_columns["performance"]],
                        "pressure_performance": row[role_columns["performance"]],
                        "normal_baseline": row[role_columns["normal"]],
                        "pressure_opportunities": int(row["pressure_opportunities"]),
                        "pressure_matches": int(row["pressure_matches"]),
                        "SPI": row.get("spi"),
                        "reliability": row.get("reliability"),
                    }
                )
                match_frame = calculated[role_columns["match_evidence"]]
                evidence_frames.append(
                    match_frame.loc[
                        match_frame[role_columns["id"]].eq(row[role_columns["id"]])
                    ].assign(season=str(season))
                )
        metric_rows = pd.DataFrame(trend_rows)
        evidence = _safe_records(
            pd.concat(evidence_frames, ignore_index=True) if evidence_frames else pd.DataFrame()
        )
        verification_notes = []
        for season in metric_rows["season"].dropna().unique():
            verified, note = _verification(
                question.role,
                [
                    row
                    for row in _safe_records(metric_rows, 20)
                    if row.get("season") == season
                ],
                [row for row in evidence if row.get("season") == season],
                scoped.loc[scoped["season"].astype(str).eq(str(season))],
            )
            if not verified:
                return {
                    "status": "verification_failed",
                    "intent": question.intent,
                    "question": question_text,
                    "answer": "The season trend did not pass source-record verification and is withheld.",
                    "scope": scope,
                    "metrics": [],
                    "evidence": [],
                    "limitations": [note],
                }
            verification_notes.append(note)
        verification_note = " ".join(dict.fromkeys(verification_notes))
        answer = (
            f"Season-by-season {question.role} leaders are calculated from each "
            "season's filtered delivery rows. This is a descriptive trend, not a "
            "same-player longitudinal comparison."
        )
    else:
        metrics = calculate_player_metrics(scoped)
        role_columns = _role_columns(question.role)
        metric_frame = _metric_rows(metrics, question.role, question)
        if metric_frame.empty:
            return {
                "status": "insufficient",
                "intent": question.intent,
                "question": question_text,
                "answer": "No players satisfy the requested filters and the documented minimum sample for this calculation.",
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": [
                    f"Rankings require at least {MIN_MATCHES} pressure matches and "
                    f"{MIN_PRESSURE_OPPORTUNITIES} role-specific pressure balls."
                ],
            }
        metric_rows = metric_frame.copy()
        if role_columns["id"] in metric_rows:
            metric_rows["player_id"] = metric_rows[role_columns["id"]].astype("int64")
            metric_rows["player_name"] = metric_rows[role_columns["name"]].astype(str)
        if "spi" in metric_rows:
            metric_rows["SPI"] = metric_rows["spi"]
        metric_rows["performance"] = metric_rows[role_columns["performance"]]
        metric_rows["normal_baseline"] = metric_rows[role_columns["normal"]]
        if "reliability" not in metric_rows and "player_id" in metric_rows:
            eligible_rankings = rank_players(metrics, question.role)
            additional = (
                ["player_id"]
                + [
                    column
                    for column in (
                        "rank",
                        "spi",
                        "reliability",
                        "uncertainty_indicator",
                    )
                    if column in eligible_rankings and column not in metric_rows
                ]
            )
            if len(additional) > 1 and "player_id" in eligible_rankings:
                metric_rows = metric_rows.merge(
                    eligible_rankings[additional].drop_duplicates("player_id"),
                    on="player_id",
                    how="left",
                    validate="many_to_one",
                )
                metric_rows["SPI"] = metric_rows["spi"]
        if question.players:
            wanted_ids = [player_id for player_id, _ in question.players]
            metric_rows = metric_rows.loc[metric_rows["player_id"].isin(wanted_ids)]
        if question.intent == "player_comparison" and len(metric_rows) < 2:
            return {
                "status": "insufficient",
                "intent": question.intent,
                "question": question_text,
                "answer": "Both requested players must have measurable opportunities in this scope.",
                "scope": scope,
                "metrics": _safe_records(metric_rows),
                "evidence": [],
                "limitations": ["One or both players have no role-specific observations in the filtered records."],
            }
        evidence_frame = metrics[role_columns["match_evidence"]]
        evidence_id = role_columns["id"]
        selected_ids = metric_rows["player_id"].dropna().astype(int).unique().tolist()
        evidence_frame = evidence_frame.loc[evidence_frame[evidence_id].isin(selected_ids)]
        evidence = _safe_records(evidence_frame.sort_values("match_id"), EVIDENCE_LIMIT)
        metrics_records = _safe_records(metric_rows, 10)
        verified, verification_note = _verification(
            question.role, metrics_records, evidence, scoped
        )
        if not verified:
            return {
                "status": "verification_failed",
                "intent": question.intent,
                "question": question_text,
                "answer": "The analytics result did not pass source-record verification and is withheld.",
                "scope": scope,
                "metrics": [],
                "evidence": [],
                "limitations": [verification_note],
            }
        names = ", ".join(row["player_name"] for row in metrics_records[:3])
        if question.intent in {"ranking", "consistency", "reliability", "sample_analysis"}:
            answer = (
                f"The leading {question.role} result(s) in this scope are {names}. "
                "Ranked metrics, sample counts and source-backed match evidence follow."
            )
        elif question.intent == "player_explanation":
            row = metrics_records[0]
            answer = (
                f"{row['player_name']} (ID {row['player_id']}) is ranked "
                f"{row.get('rank', 'unranked')} in the filtered {question.role} list. "
                "The metrics table shows pressure performance, normal baseline, "
                "sample size, reliability and SPI where eligible."
            )
        else:
            answer = (
                f"Calculated {question.role} pressure and normal metrics for {names} "
                "from the filtered delivery records."
            )
        metric_rows = pd.DataFrame(metrics_records)
        limitations = [
            "Pressure labels and SPI remain provisional and have not received domain approval.",
            "Competition and season filters restrict the delivered historical archive; missing source context is not inferred.",
        ]
        evidence_columns = list(evidence_frame.columns)
        metric_columns = list(metric_rows.columns)
        result = {
            "status": "answer",
            "intent": question.intent,
            "question": question_text,
            "answer": answer,
            "scope": scope,
            "metrics": metrics_records,
            "evidence": evidence,
            "metric_columns": metric_columns,
            "evidence_columns": evidence_columns,
            "verification": verification_note,
            "limitations": limitations,
        }
        return result

    return {
        "status": "answer",
        "intent": question.intent,
        "question": question_text,
        "answer": answer,
        "scope": scope,
        "metrics": _safe_records(metric_rows, 20),
        "evidence": evidence,
        "metric_columns": list(metric_rows.columns) if isinstance(metric_rows, pd.DataFrame) else [],
        "evidence_columns": [],
        "verification": verification_note,
        **(
            {"comparison_results": comparison_results}
            if comparison_results is not None
            else {}
        ),
        "limitations": [
            "Values are calculated from the supplied historical archive; missing context is not inferred.",
            "Rankings and pressure methodology remain provisional.",
            *(
                format_limitations
                if question.intent == "format_comparison"
                else []
            ),
        ],
    }


class LLMProviderError(RuntimeError):
    """An optional provider could not safely return explanatory commentary."""


class OpenAICompatibleProvider:
    """Optional OpenAI-compatible chat-completions provider using stdlib HTTP."""

    def __init__(self, api_key, model, base_url="https://api.openai.com/v1", timeout=15):
        if not api_key or not model:
            raise ValueError("An API key and model name are required.")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat_with_tools(self, messages, tools):
        """Request one OpenAI-compatible function/tool-calling turn."""
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"******",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw_response = response.read(1_000_001)
            if len(raw_response) > 1_000_000:
                raise LLMProviderError(
                    "LLM provider response exceeded the size limit; local analytics remain available."
                )
            payload = json.loads(raw_response.decode("utf-8"))
            message = payload["choices"][0]["message"]
        except urllib.error.HTTPError as error:
            raise LLMProviderError(
                f"LLM provider returned HTTP {error.code}; local analytics remain available."
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise LLMProviderError(
                "LLM provider is unavailable; local analytics remain available."
            ) from error
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise LLMProviderError(
                "LLM provider returned an invalid tool-calling response; local analytics remain available."
            ) from error
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise LLMProviderError("LLM provider returned invalid response text.")
        tool_calls = message.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            raise LLMProviderError("LLM provider returned an invalid tool-call list.")
        if len(tool_calls) > 4:
            raise LLMProviderError(
                "LLM provider exceeded the per-turn tool-call limit; local analytics remain available."
            )
        return {"content": content or "", "tool_calls": tool_calls}

    def interpret_question(self, question, allowed_context):
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Classify the cricket question only; do not answer it and "
                            "do not generate SQL. Return one JSON object with exactly "
                            "these keys: intent, role, player_ids, season, compare_seasons, "
                            "format, competition, phase, match_id, team. Use only allowed values "
                            "from the supplied context. Choose intent=ambiguous when "
                            "the role or meaning is unclear, and intent=unsupported if "
                            "the archive cannot answer the request. player_ids must be "
                            "IDs from candidate_players only. Use null for absent filters."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "allowed_context": allowed_context,
                            }
                        ),
                    },
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except urllib.error.HTTPError as error:
            raise LLMProviderError(
                f"LLM provider returned HTTP {error.code}; local question parsing remains available."
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise LLMProviderError(
                "LLM provider is unavailable; local question parsing remains available."
            ) from error
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise LLMProviderError(
                "LLM provider returned an invalid question interpretation; local parsing remains available."
            ) from error
        if not isinstance(parsed, dict):
            raise LLMProviderError(
                "LLM provider interpretation must be a JSON object; local parsing remains available."
            )
        return parsed

    def explain(self, verified_summary):
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Explain the provided verified cricket result in one "
                            "short qualitative sentence. Do not include numbers, "
                            "player names, rankings, or new factual claims. The "
                            "application renders all names and statistics itself."
                        ),
                    },
                    {"role": "user", "content": json.dumps(verified_summary)},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise LLMProviderError(
                f"LLM provider returned HTTP {error.code}; verified analytics remain available."
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise LLMProviderError(
                "LLM provider is unavailable; verified analytics remain available."
            ) from error
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise LLMProviderError(
                "LLM provider returned an invalid response; verified analytics remain available."
            ) from error
        try:
            return str(payload["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as error:
            raise LLMProviderError(
                "LLM provider response has no commentary; verified analytics remain available."
            ) from error


def provider_from_environment():
    """Return no provider by default; never reveal or log a configured secret."""
    api_key = os.environ.get("SUPERR_LLM_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("SUPERR_LLM_MODEL")
    if not model:
        raise LLMProviderError(
            "SUPERR_LLM_API_KEY is set but SUPERR_LLM_MODEL is missing."
        )
    base_url = os.environ.get("SUPERR_LLM_BASE_URL", "https://api.openai.com/v1")
    return OpenAICompatibleProvider(api_key, model, base_url)


def generate_commentary(provider, result):
    """Request prose only; reject numeric output so the model cannot alter stats."""
    summary = {
        "intent": result["intent"],
        "verified_answer_type": result["status"],
        "scope": result["scope"],
        "verified_metrics": result["metrics"][:10],
        "verified_calculation_note": (
            "These rows were calculated and source-verified by the application. "
            "Do not repeat or modify their numerical values."
        ),
    }
    commentary = provider.explain(summary)
    if re.search(r"\d", commentary):
        raise LLMProviderError(
            "LLM commentary contained numeric claims and was rejected; verified statistics are unchanged."
        )
    return commentary
