"""
Predictor module — Linear Regression for commodity price forecasting.
Uses only Python stdlib so no extra packages required.
"""


def linear_regression(x_vals, y_vals):
    """Returns (slope, intercept) for the given x/y lists."""
    n = len(x_vals)
    if n < 2:
        return 0.0, y_vals[0] if y_vals else 0.0
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n
    num   = sum((x_vals[i] - x_mean) * (y_vals[i] - y_mean) for i in range(n))
    denom = sum((x_vals[i] - x_mean) ** 2 for i in range(n)) or 1.0
    slope     = num / denom
    intercept = y_mean - slope * x_mean
    return slope, intercept


def predict_next_prices(prices: list, steps: int = 4) -> list:
    """
    Given a list of historical prices, predict `steps` future values.
    Returns a list of predicted prices.
    """
    x = list(range(len(prices)))
    slope, intercept = linear_regression(x, prices)
    n = len(prices)
    return [
        max(intercept + slope * (n + s), prices[-1] * 0.5)
        for s in range(steps)
    ]


def r_squared(y_actual: list, y_predicted: list) -> float:
    """Coefficient of determination (R²)."""
    y_mean = sum(y_actual) / len(y_actual)
    ss_res = sum((y_actual[i] - y_predicted[i]) ** 2 for i in range(len(y_actual)))
    ss_tot = sum((y - y_mean) ** 2 for y in y_actual) or 1.0
    return round(1 - ss_res / ss_tot, 4)
