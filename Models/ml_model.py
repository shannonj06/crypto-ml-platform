from feature_engineering import train_df, ticker_X_cols
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, classification_report, precision_score, recall_score, f1_score
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier
import numpy as np


MODELS = {
    "logistic": LogisticRegression(random_state=42, max_iter=1000),
    "tree": DecisionTreeClassifier(random_state=42, max_depth=5),
    "forest": RandomForestClassifier(random_state=42, n_estimators=200, max_depth=5),
    "gradient_boost": GradientBoostingClassifier(random_state=42, n_estimators=200, max_depth=5),
    "knn": KNeighborsClassifier(n_neighbors=5),
    "svc": SVC(kernel="rbf", random_state=42, probability=True),
    "gaussian": GaussianNB(),
    "mlp": MLPClassifier(random_state=42, max_iter=1000)
}

def run_ml(x_vals, y_vals, train_percent, ticker):
    train_size = int(len(x_vals[ticker]) * train_percent)
    x_train = x_vals[ticker][:train_size]
    x_test =  x_vals[ticker][train_size:]
    y_train = y_vals[ticker][:train_size]
    y_test = y_vals[ticker][train_size:]
    #this is to put all the features on the same scale
    scaler = StandardScaler()

    x_train_scaled =scaler.fit_transform(x_train)
    x_test_scaled = scaler.transform(x_test)
    for name, model in MODELS.items():
        model.fit(x_train_scaled, y_train)
        y_pred = model.predict(x_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        score = model.score(x_test_scaled, y_test)
        report = classification_report(y_test, y_pred)
        baseline = y_test.mean()
        recall = recall_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred)

        print(f"{name} model for {ticker} results:")
        print()
        print(f"Accuracy: {accuracy}")
        print(f"Model Score: {score}")
        print(f"Baseline: {baseline}")
        print(f"Recall: {recall}")
        print(f"F1: {f1}")
        print(f"Precision: {precision}")
        print(report)

VOL_MODELS = {
    "ridge":         Ridge(),
    "forest":        RandomForestRegressor(random_state=42, n_estimators=200, max_depth=5),
    "gradient_boost": GradientBoostingRegressor(random_state=42, n_estimators=200, max_depth=5),
}

def run_vol_ml(x_vals, y_vol, train_percent, ticker, horizon=7):
    """
    Regression model for forward realized volatility.

    x_vals : {ticker: DataFrame} of input features (same as run_ml)
    y_vol  : {ticker: Series}    of forward realized vol target
    """
    X_all = x_vals[ticker]
    y_all = y_vol[ticker].reindex(X_all.index).dropna()
    X_all = X_all.loc[y_all.index]

    train_size   = int(len(X_all) * train_percent)
    X_train, X_test = X_all.iloc[:train_size], X_all.iloc[train_size:]
    y_train, y_test = y_all.iloc[:train_size], y_all.iloc[train_size:]

    scaler      = StandardScaler()
    X_train_s   = scaler.fit_transform(X_train)
    X_test_s    = scaler.transform(X_test)

    for name, model in VOL_MODELS.items():
        model.fit(X_train_s, y_train)
        y_pred = model.predict(X_test_s)

        mae   = mean_absolute_error(y_test, y_pred)
        rmse  = np.sqrt(mean_squared_error(y_test, y_pred))
        # QLIKE penalises underestimation of vol more than overestimation
        y_safe = np.maximum(y_pred, 1e-8)
        qlike  = float(np.mean(np.log(y_safe ** 2) + np.array(y_test) ** 2 / y_safe ** 2))

        print(f"{name} vol model for {ticker} ({horizon}d horizon):")
        print(f"  MAE={mae:.4f}  RMSE={rmse:.4f}  QLIKE={qlike:.4f}")
        print()


if __name__ == "__main__":
    from volatility_model import add_parkinson_fwd_vol, get_log_returns
    from feature_engineering import feature_df, crypto_data

    # --- Directional models ---
    UP_TARGETS = ["target_1d_up", "target_5d_up", "target_20d_up"]
    x_vals = {t: train_df[ticker_X_cols[t]] for t in ["btc", "sol", "eth"]}



    # --- Volatility regression models ---
    get_log_returns()
    HORIZONS = [7, 20]
    for horizon in HORIZONS:
        vol_df = feature_df.copy()
        for ticker in ["btc", "sol", "eth"]:
            vol_df = add_parkinson_fwd_vol(vol_df, crypto_data, ticker, horizon=horizon)

        y_vol = {t: vol_df[f"{t}_fwd_park_vol_{horizon}d"].reindex(train_df.index)
                 for t in ["btc", "sol", "eth"]}

        for ticker in ["btc", "sol", "eth"]:
            run_vol_ml(x_vals, y_vol, 0.8, ticker, horizon=horizon)