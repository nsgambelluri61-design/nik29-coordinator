import aiohttp
import asyncio
from typing import Dict, Any

async def meteo(city: str) -> dict:
    """
    Recupera il meteo attuale di una citta italiana usando Open-Meteo API
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Geocoding per ottenere latitudine e longitudine
            geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=it&format=json"
            async with session.get(geocode_url, timeout=10) as resp:
                if resp.status != 200:
                    raise Exception(f"Errore geocoding: status {resp.status}")
                geocode_data = await resp.json()
            if not geocode_data.get("results"):
                raise Exception("Città non trovata")
            lat = geocode_data["results"][0]["latitude"]
            lon = geocode_data["results"][0]["longitude"]
            # Step 2: Chiamata al meteo attuale
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current_weather=true&timezone=Europe%2FRome"
            )
            async with session.get(weather_url, timeout=10) as resp:
                if resp.status != 200:
                    raise Exception(f"Errore meteo: status {resp.status}")
                weather_data = await resp.json()
            current_weather = weather_data.get("current_weather")
            if not current_weather:
                raise Exception("Dati meteo non disponibili")
            result: Dict[str, Any] = {
                "city": geocode_data["results"][0]["name"],
                "latitude": lat,
                "longitude": lon,
                "temperature": current_weather.get("temperature"),
                "windspeed": current_weather.get("windspeed"),
                "winddirection": current_weather.get("winddirection"),
                "weathercode": current_weather.get("weathercode"),
                "time": current_weather.get("time"),
                "unit_temperature": weather_data.get("current_weather_units", {}).get("temperature", "°C"),
                "unit_windspeed": weather_data.get("current_weather_units", {}).get("windspeed", "km/h")
            }
            return {"result": result, "success": True}
    except Exception as e:
        return {"result": None, "success": False, "error": str(e)}

# Esempio di chiamata corretta:
# asyncio.run(meteo(city="Roma"))