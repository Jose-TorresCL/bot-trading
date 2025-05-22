import logging

def sincronizar_prices_con_features(prices, features):
    if len(prices) > len(features):
        logging.warning("⚠️ Más precios que features, recortando precios.")
        prices = prices[-len(features):]
    elif len(prices) < len(features):
        logging.warning("⚠️ Más features que precios, recortando features.")
        features = features[-len(prices):]
    return prices, features
