"""Train reproducible exploratory models on curated cricket analytics."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
from sklearn.cluster import KMeans
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
CURATED = ROOT / "data" / "curated"
OUTPUT = ROOT / "reports" / "machine_learning"
BOUNDARY_FEATURES = [
    "innings",
    "score_before",
    "wickets_before",
    "legal_balls_before",
    "balls_remaining",
    "wickets_remaining",
    "innings_progress",
    "current_run_rate",
    "required_run_rate",
    "reference_run_rate",
]
PLAYER_FEATURES = {
    "batters": [
        "pressure_strike_rate",
        "pressure_boundary_percentage",
        "pressure_dot_ball_percentage",
        "consistency",
        "pressure_opportunities",
    ],
    "bowlers": [
        "pressure_economy",
        "pressure_wickets",
        "pressure_dots",
        "pressure_boundaries",
        "pressure_opportunities",
        "consistency",
    ],
}


def _classification_metrics(model, x_test, y_test):
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, 1]
    return {
        "test_rows": int(len(y_test)),
        "boundary_prevalence": float(y_test.mean()),
        "majority_class_accuracy": float(max(y_test.mean(), 1 - y_test.mean())),
        "accuracy": float(accuracy_score(y_test, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(y_test, predictions)),
        "precision_boundary": float(precision_score(y_test, predictions, zero_division=0)),
        "recall_boundary": float(recall_score(y_test, predictions, zero_division=0)),
        "f1_boundary": float(f1_score(y_test, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, probabilities)),
        "confusion_matrix_labels_0_1": confusion_matrix(
            y_test, predictions, labels=[0, 1]
        ).tolist(),
    }


def train_boundary_models(deliveries, output_dir=OUTPUT):
    """Predict a delivery boundary using only its pre-delivery match state."""
    required = set(BOUNDARY_FEATURES) | {
        "match_id",
        "is_four",
        "is_six",
    }
    missing = required.difference(deliveries.columns)
    if missing:
        raise ValueError(f"Missing delivery model columns: {sorted(missing)}")
    frame = deliveries[list(required)].copy()
    frame = frame.dropna(subset=["match_id"])
    frame["target_boundary"] = (
        frame["is_four"].fillna(False).astype(bool)
        | frame["is_six"].fillna(False).astype(bool)
    ).astype("int8")
    x = frame[BOUNDARY_FEATURES].replace([np.inf, -np.inf], np.nan)
    y = frame["target_boundary"]
    groups = frame["match_id"]
    if y.nunique() != 2 or groups.nunique() < 2:
        raise ValueError("Boundary modelling requires both classes and multiple matches.")
    split = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_idx, test_idx = next(split.split(x, y, groups))
    if y.iloc[train_idx].nunique() != 2 or y.iloc[test_idx].nunique() != 2:
        raise ValueError("The match-held-out split must contain both target classes.")
    x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    models = {
        "decision_tree": DecisionTreeClassifier(
            max_depth=8, min_samples_leaf=50, class_weight="balanced", random_state=42
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=120,
            max_depth=12,
            min_samples_leaf=20,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        ),
    }
    result = {
        "objective": "Predict whether the current delivery is a four or six.",
        "target": "is_four OR is_six from the current delivery; excluded from features.",
        "features": BOUNDARY_FEATURES,
        "split": {
            "method": "GroupShuffleSplit by match_id",
            "test_fraction": 0.25,
            "random_state": 42,
            "train_matches": int(groups.iloc[train_idx].nunique()),
            "test_matches": int(groups.iloc[test_idx].nunique()),
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "match_overlap": int(
                len(
                    set(groups.iloc[train_idx].unique())
                    & set(groups.iloc[test_idx].unique())
                )
            ),
        },
        "models": {},
        "limitations": [
            "This is an exploratory delivery-event classifier, not a player-selection model.",
            "A match-held-out random split prevents same-match leakage but is not a chronological future-season test.",
            "The supplied archive is observational; feature importance is association, not causal impact.",
            "A majority-class baseline is reported because boundary events are a minority class.",
        ],
    }
    for name, estimator in models.items():
        model = make_pipeline(SimpleImputer(strategy="median"), estimator)
        model.fit(x_train, y_train)
        scores = _classification_metrics(model, x_test, y_test)
        result["models"][name] = scores
        joblib.dump(model, output_dir / f"{name}.joblib")
        importances = pd.DataFrame(
            {"feature": BOUNDARY_FEATURES, "importance": estimator.feature_importances_}
        ).sort_values("importance", ascending=False)
        importances.to_csv(output_dir / f"{name}_feature_importance.csv", index=False)
    result["model_comparison"] = {
        "best_balanced_accuracy": max(
            result["models"], key=lambda model: result["models"][model]["balanced_accuracy"]
        ),
        "decision_tree_vs_random_forest_balanced_accuracy": (
            result["models"]["random_forest"]["balanced_accuracy"]
            - result["models"]["decision_tree"]["balanced_accuracy"]
        ),
    }
    return result


def cluster_players(metrics, role, output_dir=OUTPUT):
    """Cluster pressure-performance profiles using standardized role metrics."""
    if role not in PLAYER_FEATURES:
        raise ValueError("role must be 'batters' or 'bowlers'")
    features = PLAYER_FEATURES[role]
    required = set(features)
    player_id = "striker_id" if role == "batters" else "bowler_id"
    player_name = "striker_name" if role == "batters" else "bowler_name"
    required.update({player_id, player_name})
    missing = required.difference(metrics.columns)
    if missing:
        raise ValueError(f"Missing {role} clustering columns: {sorted(missing)}")
    frame = metrics.dropna(subset=[player_id, *features]).copy()
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=features)
    if len(frame) < 3:
        raise ValueError(f"At least three complete {role} records are required.")
    x = StandardScaler().fit_transform(frame[features])
    max_k = min(6, len(frame) - 1)
    candidates = []
    for k in range(2, max_k + 1):
        labels = KMeans(n_clusters=k, n_init=20, random_state=42).fit_predict(x)
        score = silhouette_score(
            x,
            labels,
            sample_size=min(5000, len(frame)),
            random_state=42,
        )
        candidates.append((float(score), k))
    silhouette, selected_k = max(candidates)
    clusterer = KMeans(n_clusters=selected_k, n_init=20, random_state=42)
    frame["cluster"] = clusterer.fit_predict(x)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / f"{role}_clusters.csv", index=False)
    profile = frame.groupby("cluster")[features].agg(["count", "mean", "median"])
    profile.to_csv(output_dir / f"{role}_cluster_profiles.csv")
    if len(features) >= 2:
        figure = px.scatter(
            frame,
            x=features[0],
            y=features[1],
            color=frame["cluster"].astype(str),
            hover_name=player_name,
            hover_data=[player_id, *features[2:]],
            title=f"{role.title()} pressure-profile clusters (K={selected_k})",
            labels={"color": "Cluster"},
        )
        figure.write_html(
            output_dir / f"{role}_clusters.html",
            include_plotlyjs="cdn",
            full_html=True,
        )
    return {
        "role": role,
        "features": features,
        "selected_k": selected_k,
        "silhouette_score": silhouette,
        "candidate_scores": [
            {"k": k, "silhouette_score": score} for score, k in candidates
        ],
        "cluster_sizes": {
            str(cluster): int(count)
            for cluster, count in frame["cluster"].value_counts().sort_index().items()
        },
        "interpretation_note": (
            "Clusters group standardized observed pressure metrics; cluster IDs "
            "are arbitrary and do not imply player quality or causal style."
        ),
    }


def run_models(curated_dir=CURATED, output_dir=OUTPUT):
    curated_dir, output_dir = Path(curated_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    deliveries = pd.read_parquet(
        curated_dir / "pressure_deliveries.parquet",
        columns=[*BOUNDARY_FEATURES, "match_id", "is_four", "is_six"],
    )
    model_results = train_boundary_models(deliveries, output_dir)
    clusters = {}
    for role, filename in [
        ("batters", "batter_metrics.parquet"),
        ("bowlers", "bowler_metrics.parquet"),
    ]:
        metrics = pd.read_parquet(curated_dir / filename)
        clusters[role] = cluster_players(metrics, role, output_dir)
    result = {
        "status": "exploratory",
        "random_state": 42,
        "classification": model_results,
        "clustering": clusters,
        "spi_integration": False,
    }
    (output_dir / "evaluation.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    _write_report(result, output_dir / "README.md")
    return result


def _write_report(result, path):
    classification = result["classification"]
    lines = [
        "# Exploratory Cricket Machine Learning",
        "",
        "> These analyses are separate from SPI and are not used in the player rankings.",
        "",
        f"Classification objective: {classification['objective']}",
        "",
        f"Features: {', '.join(classification['features'])}.",
        "",
        f"Validation: {classification['split']}.",
        "",
        "| Model | Accuracy | Balanced accuracy | Precision | Recall | F1 | ROC AUC |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, scores in classification["models"].items():
        lines.append(
            f"| {name} | {scores['accuracy']:.4f} | {scores['balanced_accuracy']:.4f} "
            f"| {scores['precision_boundary']:.4f} | {scores['recall_boundary']:.4f} "
            f"| {scores['f1_boundary']:.4f} | {scores['roc_auc']:.4f} |"
        )
    lines.extend(["", "## Player clustering", ""])
    for role, cluster in result["clustering"].items():
        lines.extend(
            [
                f"### {role.title()}",
                "",
                f"- Features: {', '.join(cluster['features'])}",
                f"- Selected K: {cluster['selected_k']} (best silhouette "
                f"{cluster['silhouette_score']:.4f} across K=2–{max(item['k'] for item in cluster['candidate_scores'])})",
                f"- Cluster sizes: `{cluster['cluster_sizes']}`",
                f"- Interpretation: {cluster['interpretation_note']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Limitations",
            "",
            *[f"- {limitation}" for limitation in classification["limitations"]],
            "- K-means is exploratory, sensitive to scaling and selected K; clusters are not rankings.",
            "- Historical dataset coverage and source-field ambiguities limit external validity.",
            "",
            "Run with `.venv/bin/python -m machine_learning.run_models` from the project root.",
        ]
    )
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    result = run_models()
    print("Classification held-out matches:", result["classification"]["split"]["test_matches"])
    for name, score in result["classification"]["models"].items():
        print(f"{name}: balanced accuracy {score['balanced_accuracy']:.4f}, F1 {score['f1_boundary']:.4f}")
    for role, cluster in result["clustering"].items():
        print(f"{role}: K={cluster['selected_k']}, silhouette {cluster['silhouette_score']:.4f}")


if __name__ == "__main__":
    main()
