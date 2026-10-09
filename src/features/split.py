"""
src/features/split.py
Population-structure-aware cross-validation partitioning.
1. Patterson-standardized PCA (Patterson, Price, & Reich 2006).
2. Subpopulation clustering with cluster-size imbalance guardrails.
3. Multi-environment cross-validation splits (within-env CV2 and across-env CV1).
"""
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.model_selection import StratifiedKFold, GroupKFold, KFold


def patterson_scaling(dosage_matrix: np.ndarray, ploidy: int = 2) -> np.ndarray:
    """
    Patterson-style allele-frequency standardization:
    Z_ij = (X_ij - ploidy * p_j) / sqrt(ploidy * p_j * (1 - p_j))
    Parameters:
        dosage_matrix: (N samples x M markers) array of imputed dosages in [0, ploidy]
        ploidy: Organism ploidy (default 2)
    Returns:
        (N samples x M markers) standardized matrix Z
    """
    N, M = dosage_matrix.shape
    # Estimated allele frequency per marker
    p = np.mean(dosage_matrix, axis=0) / float(ploidy)  # shape (M,)

    # Variance term: ploidy * p * (1 - p)
    denom = np.sqrt(ploidy * p * (1.0 - p))  # shape (M,)

    # Numerical stability: mask monomorphic or near-monomorphic markers
    zero_denom_mask = (denom < 1e-6) | np.isnan(denom)
    denom[zero_denom_mask] = 1.0

    centered = dosage_matrix - (ploidy * p)
    Z = centered / denom
    Z[:, zero_denom_mask] = 0.0
    return Z


def compute_population_clusters(
    dosage_matrix: pd.DataFrame,
    n_clusters: int = 5,
    n_pcs: int = 10,
    ploidy: int = 2,
    min_cluster_size: int = 15,
    random_state: int = 42,
) -> pd.Series:
    """
    Perform Patterson-scaled PCA followed by clustering with size-imbalance guardrails.
    Returns:
        pd.Series of cluster labels indexed by sample_id
    """
    sample_ids = dosage_matrix.index
    X = dosage_matrix.values

    # Step 1: Patterson Standardization
    Z = patterson_scaling(X, ploidy=ploidy)

    # Step 2: PCA on standardized matrix
    actual_pcs = min(n_pcs, X.shape[0] - 1, X.shape[1])
    pca = PCA(n_components=actual_pcs, random_state=random_state)
    pcs = pca.fit_transform(Z)

    # Step 3: K-Means Clustering
    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = kmeans.fit_predict(pcs)

    # Step 4: Cluster balance check
    unique_labels, counts = np.unique(labels, return_counts=True)
    min_count = counts.min()

    if min_count < min_cluster_size and len(sample_ids) >= (n_clusters * min_cluster_size):
        # Fall back to Agglomerative Clustering with Ward linkage for more balanced clusters
        agg = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
        labels = agg.fit_predict(pcs)
        _, counts = np.unique(labels, return_counts=True)
        min_count = counts.min()

    return pd.Series(labels, index=sample_ids, name="subpopulation_cluster")


def build_cv_splits(
    sample_ids: pd.Index | list,
    clusters: pd.Series | None = None,
    environments: pd.Series | None = None,
    n_folds: int = 5,
    cv_type: str = "within_environment",
    random_state: int = 42,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Build cross-validation fold index splits.
    Parameters:
        sample_ids: Index or array of sample identifiers
        clusters: Subpopulation cluster labels for each sample
        environments: Environment string for each observation (for multi-environment trials)
        n_folds: Number of folds
        cv_type: 'within_environment' (predict new genotypes across observed environments)
                 or 'across_environment' (leave-one-environment-out)
    Returns:
        List of (train_indices, test_indices)
    """
    n_samples = len(sample_ids)
    indices = np.arange(n_samples)

    if cv_type == "across_environment" and environments is not None:
        # Leave-one-environment-out CV
        unique_envs = environments.unique()
        splits = []
        for test_env in unique_envs:
            test_mask = (environments == test_env).values
            train_idx = indices[~test_mask]
            test_idx = indices[test_mask]
            splits.append((train_idx, test_idx))
        return splits

    # Within-environment / population-structure-aware CV:
    if clusters is not None:
        cluster_vals = clusters.values
        # Use StratifiedKFold on subpopulation clusters to ensure every fold
        # is representative of all subpopulations and no fold is degenerate
        try:
            skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=random_state)
            splits = list(skf.split(indices, cluster_vals))
            return splits
        except ValueError:
            # Fallback if a cluster has fewer than n_folds members
            pass

    # Standard K-Fold fallback
    kf = KFold(n_splits=n_folds, shuffle=True, random_state=random_state)
    return list(kf.split(indices))
