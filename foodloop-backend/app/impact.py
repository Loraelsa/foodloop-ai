"""Impact formulas (all factors are cited in the report, Chapter 7)."""
KG_PER_MEAL = 0.42     # WRAP meal equivalent
CO2_PER_KG = 2.5       # FAO food-wastage footprint, kg CO2e per kg food
CO2_PER_KM = 0.2521    # average diesel van, kg CO2e per km (Energy Saving Trust table based on UK DESNZ 2025 conversion factors)


def impact(kg, km=0.0):
    gross = kg * CO2_PER_KG
    transport = km * CO2_PER_KM
    return {"kg": round(kg, 2), "meals": round(kg / KG_PER_MEAL), "co2_gross": round(gross, 2),
            "co2_transport": round(transport, 2), "co2_net": round(gross - transport, 2)}
