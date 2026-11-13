"""Build a supported player-match network and compute supplementary PageRank."""

import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import spearmanr

from analytics.cricket_metrics import rank_players


ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
OUTPUT = ROOT / "reports" / "graph"


def build_player_match_graph(deliveries):
    """Create a directed bipartite graph from observed delivery participants."""
    required = {
        "match_id",
        "striker_id",
        "striker_name",
        "bowler_id",
        "bowler_name",
        "pressure_batter_ball",
        "pressure_bowler_ball",
    }
    missing = required.difference(deliveries.columns)
    if missing:
        raise ValueError(f"Missing graph source columns: {sorted(missing)}")
    batter = deliveries[
        ["match_id", "striker_id", "striker_name", "pressure_batter_ball"]
    ].rename(
        columns={
            "striker_id": "player_id",
            "striker_name": "player_name",
            "pressure_batter_ball": "pressure_opportunity",
        }
    )
    bowler = deliveries[
        ["match_id", "bowler_id", "bowler_name", "pressure_bowler_ball"]
    ].rename(
        columns={
            "bowler_id": "player_id",
            "bowler_name": "player_name",
            "pressure_bowler_ball": "pressure_opportunity",
        }
    )
    participation = pd.concat([batter, bowler], ignore_index=True)
    participation = participation.dropna(subset=["match_id", "player_id"])
    participation["pressure_opportunity"] = (
        participation["pressure_opportunity"].fillna(False).astype(int)
    )
    participation = (
        participation.groupby(
            ["match_id", "player_id", "player_name"], as_index=False, dropna=False
        )
        .agg(
            deliveries=("player_id", "size"),
            pressure_opportunities=("pressure_opportunity", "sum"),
        )
    )
    graph = nx.DiGraph()
    for row in participation.itertuples(index=False):
        player_node = f"player:{int(row.player_id)}"
        match_node = f"match:{int(row.match_id)}"
        graph.add_node(
            player_node,
            node_type="player",
            player_id=int(row.player_id),
            label=str(row.player_name),
        )
        graph.add_node(
            match_node,
            node_type="match",
            match_id=int(row.match_id),
            label=f"Match {int(row.match_id)}",
        )
        graph.add_edge(
            player_node,
            match_node,
            weight=1.0,
            deliveries=int(row.deliveries),
            pressure_opportunities=int(row.pressure_opportunities),
        )
        graph.add_edge(
            match_node,
            player_node,
            weight=float(row.deliveries),
            deliveries=int(row.deliveries),
            pressure_opportunities=int(row.pressure_opportunities),
        )
    return graph


def _draw_graph(graph, rankings, output):
    selected_players = {
        f"player:{int(player_id)}"
        for player_id in rankings.head(15)["player_id"].tolist()
    }
    selected_matches = set()
    for player in selected_players:
        matches = sorted(
            graph.successors(player),
            key=lambda match: graph[player][match]["deliveries"],
            reverse=True,
        )
        selected_matches.update(matches[:4])
    nodes = selected_players | selected_matches
    view = graph.subgraph(nodes).copy()
    positions = nx.spring_layout(view, seed=42, k=0.8, iterations=80, weight="weight")
    edge_x, edge_y = [], []
    for source, target in view.edges:
        edge_x.extend([positions[source][0], positions[target][0], None])
        edge_y.extend([positions[source][1], positions[target][1], None])
    edges = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line={"width": 0.6, "color": "rgba(36,107,206,.25)"},
        hoverinfo="skip",
    )
    player_nodes = [node for node in view.nodes if view.nodes[node]["node_type"] == "player"]
    match_nodes = [node for node in view.nodes if view.nodes[node]["node_type"] == "match"]
    player_values = [
        {
            "node": node,
            "x": positions[node][0],
            "y": positions[node][1],
            "label": view.nodes[node]["label"],
            "pagerank": graph.nodes[node].get("pagerank", 0.0),
        }
        for node in player_nodes
    ]
    match_values = [
        {
            "node": node,
            "x": positions[node][0],
            "y": positions[node][1],
            "label": view.nodes[node]["label"],
        }
        for node in match_nodes
    ]
    figure = go.Figure(
        [
            edges,
            go.Scatter(
                x=[item["x"] for item in match_values],
                y=[item["y"] for item in match_values],
                mode="markers",
                name="Matches",
                text=[item["label"] for item in match_values],
                marker={"size": 8, "color": "#246BCE", "symbol": "square"},
            ),
            go.Scatter(
                x=[item["x"] for item in player_values],
                y=[item["y"] for item in player_values],
                mode="markers+text",
                name="Players",
                text=[item["label"] for item in player_values],
                textposition="top center",
                customdata=[[item["pagerank"]] for item in player_values],
                hovertemplate="%{text}<br>PageRank: %{customdata[0]:.6g}<extra></extra>",
                marker={"size": 10, "color": "#EA1A85"},
            ),
        ]
    )
    figure.update_layout(
        title="Observed player-match participation network",
        showlegend=True,
        xaxis={"visible": False},
        yaxis={"visible": False},
        paper_bgcolor="#071B3A",
        plot_bgcolor="#071B3A",
        font={"color": "#F7F5FC"},
    )
    figure.write_html(output, include_plotlyjs="cdn", full_html=True)


def run_graph_analysis(curated_dir=CURATED, output_dir=OUTPUT):
    curated_dir, output_dir = Path(curated_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    deliveries = pd.read_parquet(
        curated_dir / "pressure_deliveries.parquet",
        columns=[
            "match_id",
            "striker_id",
            "striker_name",
            "bowler_id",
            "bowler_name",
            "pressure_batter_ball",
            "pressure_bowler_ball",
        ],
    )
    graph = build_player_match_graph(deliveries)
    if graph.number_of_nodes() == 0:
        raise ValueError("The player-match graph has no observed player-match edges.")
    centrality = nx.pagerank(graph, alpha=0.85, weight="weight")
    player_rows = []
    for node, score in centrality.items():
        attributes = graph.nodes[node]
        if attributes["node_type"] != "player":
            continue
        involvement = [data for _, _, data in graph.out_edges(node, data=True)]
        player_rows.append(
            {
                "player_id": attributes["player_id"],
                "player_name": attributes["label"],
                "pagerank": score,
                "matches": len(involvement),
                "deliveries": sum(item["deliveries"] for item in involvement),
                "pressure_opportunities": sum(
                    item["pressure_opportunities"] for item in involvement
                ),
            }
        )
    rankings = pd.DataFrame(player_rows).sort_values(
        ["pagerank", "player_id"], ascending=[False, True], kind="stable"
    )
    rankings.insert(0, "rank", np.arange(1, len(rankings) + 1))
    rankings.to_csv(output_dir / "pagerank_players.csv", index=False)
    for node, score in centrality.items():
        graph.nodes[node]["pagerank"] = float(score)

    metrics = {
        "batters": pd.read_parquet(curated_dir / "batter_metrics.parquet"),
        "bowlers": pd.read_parquet(curated_dir / "bowler_metrics.parquet"),
    }
    role_rankings = [
        rank_players(metrics, role)
        for role in ("batter", "bowler")
    ]
    spi = pd.concat(
        [
            ranked[["player_id", "spi", "pressure_opportunities"]]
            for ranked in role_rankings
        ],
        ignore_index=True,
    )
    spi = spi.groupby("player_id", as_index=False).agg(
        spi=("spi", "max"),
        pressure_opportunities=("pressure_opportunities", "sum"),
    )
    compared = rankings.merge(spi, on="player_id", how="inner", suffixes=("", "_spi"))
    correlations = {
        "pagerank_vs_spi_spearman": float(
            spearmanr(compared["pagerank"], compared["spi"]).statistic
        ),
        "pagerank_vs_pressure_opportunities_spearman": float(
            spearmanr(compared["pagerank"], compared["pressure_opportunities_spi"]).statistic
        ),
        "players_compared": int(len(compared)),
    }
    summary = {
        "status": "supplementary",
        "graph_semantics": (
            "Bipartite directed player-match graph from observed batter and "
            "bowler deliveries. Player-to-match edges have unit weight; "
            "match-to-player edges are weighted by delivery involvement."
        ),
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "player_nodes": sum(data["node_type"] == "player" for _, data in graph.nodes(data=True)),
        "match_nodes": sum(data["node_type"] == "match" for _, data in graph.nodes(data=True)),
        "pagerank_spi_comparison": correlations,
        "interpretation": (
            "PageRank mainly reflects recorded network participation under "
            "these edge weights; it is not a measure of pressure skill and is "
            "not used in SPI or official rankings."
        ),
        "outputs": {
            "player_pagerank": "reports/graph/pagerank_players.csv",
            "visualization": "reports/graph/player_match_graph.html",
        },
    }
    (output_dir / "graph_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    _draw_graph(graph, rankings, output_dir / "player_match_graph.html")
    return summary


def main():
    summary = run_graph_analysis()
    print(
        f"Graph: {summary['nodes']} nodes, {summary['edges']} edges; "
        f"PageRank/SPI n={summary['pagerank_spi_comparison']['players_compared']}"
    )


if __name__ == "__main__":
    main()
