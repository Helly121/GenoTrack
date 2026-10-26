"""
src/models/gxe.py
Core Genotype-by-Environment (GxE) modeling architecture.
Decomposes phenotype into:
  y_hat_ij = mu + E_j + g(X_i) + ge(X_i, E_j)
where:
  mu: global mean
  E_j: environmental main effect
  g(X_i): main genetic effect (additive marker value)
  ge(X_i, E_j): genotype x environment interaction effect
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import RidgeCV
import xgboost as xgb


class GxERidgeModel(BaseEstimator, RegressorMixin):
    """
    GxE-aware Ridge Regression baseline (approximating multi-environment GBLUP).
    """
    def __init__(self, alphas: list[float] | None = None):
        self.alphas = alphas if alphas is not None else [0.1, 1.0, 10.0, 100.0, 1000.0]
        self.global_mean_ = 0.0
        self.env_effects_ = {}
        self.genetic_model_ = None
        self.env_interaction_models_ = {}
        self.environments_ = []

    def fit(self, X_geno: np.ndarray, envs: np.ndarray, y: np.ndarray):
        y = np.asarray(y, dtype=np.float32)
        X_geno = np.asarray(X_geno, dtype=np.float32)
        envs = np.asarray(envs, dtype=str)

        self.global_mean_ = float(np.mean(y))
        self.environments_ = sorted(list(np.unique(envs)))

        # 1. Environmental main effects
        for env in self.environments_:
            mask = (envs == env)
            env_mean = float(np.mean(y[mask])) if np.any(mask) else self.global_mean_
            self.env_effects_[env] = env_mean - self.global_mean_

        # Environmental adjustment
        env_adjustments = np.array([self.env_effects_.get(e, 0.0) for e in envs])
        y_adjusted = y - (self.global_mean_ + env_adjustments)

        # 2. Main genetic effect g(X)
        from sklearn.linear_model import Ridge
        self.genetic_model_ = Ridge(alpha=100.0, solver="auto")
        self.genetic_model_.fit(X_geno, y_adjusted)

        # 3. GxE Interaction effects per environment
        genetic_preds = self.genetic_model_.predict(X_geno)
        residuals = y_adjusted - genetic_preds

        for env in self.environments_:
            mask = (envs == env)
            if np.sum(mask) >= 10:
                env_ridge = Ridge(alpha=100.0, solver="auto")
                env_ridge.fit(X_geno[mask], residuals[mask])
                self.env_interaction_models_[env] = env_ridge

        return self

    def predict(self, X_geno: np.ndarray, envs: np.ndarray | str) -> np.ndarray:
        X_geno = np.asarray(X_geno, dtype=np.float32)
        single_env = isinstance(envs, str)
        if single_env:
            envs = np.full(X_geno.shape[0], envs)
        else:
            envs = np.asarray(envs, dtype=str)

        # Main genetic value
        g_pred = self.genetic_model_.predict(X_geno)

        preds = np.zeros(X_geno.shape[0], dtype=float)
        for i, env in enumerate(envs):
            if env in self.env_effects_:
                env_eff = self.env_effects_[env]
                ge_eff = 0.0
                if env in self.env_interaction_models_:
                    ge_eff = float(self.env_interaction_models_[env].predict(X_geno[i : i + 1])[0])
                preds[i] = self.global_mean_ + env_eff + g_pred[i] + ge_eff
            else:
                matching_effs = [
                    eff for e_name, eff in self.env_effects_.items()
                    if ("_DS" in str(env) and "_DS" in str(e_name)) or ("_WS" in str(env) and "_WS" in str(e_name))
                ]
                env_eff = float(np.mean(matching_effs)) if matching_effs else 0.0
                preds[i] = self.global_mean_ + env_eff + g_pred[i]

        return preds


class GxEXGBoostModel(BaseEstimator, RegressorMixin):
    """
    GxE-aware XGBoost challenger model with joint genetic and environmental interaction learning.
    """
    def __init__(self, n_estimators: int = 100, max_depth: int = 4, learning_rate: float = 0.05, random_state: int = 42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.random_state = random_state
        self.global_mean_ = 0.0
        self.env_effects_ = {}
        self.environments_ = []
        self.model_ = None
        self.feature_names_ = None

    def fit(self, X_geno: np.ndarray, envs: np.ndarray, y: np.ndarray):
        y = np.asarray(y, dtype=np.float32)
        X_geno = np.asarray(X_geno, dtype=np.float32)
        envs = np.asarray(envs, dtype=str)

        self.global_mean_ = float(np.mean(y))
        self.environments_ = sorted(list(np.unique(envs)))

        # Environmental main effects
        for env in self.environments_:
            mask = (envs == env)
            env_mean = float(np.mean(y[mask])) if np.any(mask) else self.global_mean_
            self.env_effects_[env] = env_mean - self.global_mean_

        # One-hot encode environments for joint interaction modeling
        env_one_hot = np.zeros((len(envs), len(self.environments_)), dtype=np.float32)
        for j, env_name in enumerate(self.environments_):
            env_one_hot[envs == env_name, j] = 1.0

        # Feature matrix: [Genotype Markers | One-Hot Environments]
        X_joint = np.hstack([X_geno, env_one_hot])

        self.model_ = xgb.XGBRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            learning_rate=self.learning_rate,
            random_state=self.random_state,
            tree_method="hist",
            max_bin=64,
            subsample=0.8,
            colsample_bytree=0.2,
            n_jobs=4,
        )
        self.model_.fit(X_joint, y)
        return self

    def predict(self, X_geno: np.ndarray, envs: np.ndarray | str) -> np.ndarray:
        X_geno = np.asarray(X_geno, dtype=np.float32)
        single_env = isinstance(envs, str)
        if single_env:
            env_name = envs
            if env_name in self.environments_:
                env_one_hot = np.zeros((X_geno.shape[0], len(self.environments_)), dtype=np.float32)
                j = self.environments_.index(env_name)
                env_one_hot[:, j] = 1.0
                return self.model_.predict(np.hstack([X_geno, env_one_hot]))
            else:
                matching_envs = [
                    e for e in self.environments_
                    if ("_DS" in str(env_name) and "_DS" in str(e)) or ("_WS" in str(env_name) and "_WS" in str(e))
                ]
                if matching_envs:
                    preds_list = [self.predict(X_geno, e) for e in matching_envs]
                    return np.mean(preds_list, axis=0)
                else:
                    env_one_hot = np.full((X_geno.shape[0], len(self.environments_)), 1.0 / len(self.environments_), dtype=np.float32)
                    return self.model_.predict(np.hstack([X_geno, env_one_hot]))
        else:
            envs = np.asarray(envs, dtype=str)
            preds = np.zeros(X_geno.shape[0], dtype=np.float32)
            for i, env_name in enumerate(envs):
                preds[i : i + 1] = self.predict(X_geno[i : i + 1], str(env_name))
            return preds

