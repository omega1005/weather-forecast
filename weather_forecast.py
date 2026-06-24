import requests, pytz, argparse
from datetime import datetime, timedelta
from typing import Any
import pandas as pd
from geopy.geocoders import Nominatim



class WeatherForecast:
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"

    directions_cardinal = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW", "N"]

    WEATHER_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light Drizzle",
        53: "Moderate Drizzle",
        55: "Dense Drizzle",
        56: "Light Freezing drizzle",
        57: "Dense Freezing drizzle",
        61: "Slight Rain",
        63: "Moderate Rain",
        65: "Heavy Rain",
        66: "Light Freezing rain",
        67: "Heavy Freezing rain",
        71: "Slight Snow fall",
        73: "Moderate Snow fall",
        75: "Heavy Snow fall",
        77: "Snow grains",
        80: "Slight Rain showers",
        81: "Moderate Rain showers",
        82: "Violent Rain showers",
        85: "Slight Snow showers",
        86: "Heavy Snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail"
    }

    def __init__(self, location: str) -> None:
        self.location = location
        self.latitude = None
        self.longitude = None
        self.timezone = None
        self.session = requests.Session()

    def _deg_to_cardinal(self, deg):
        idx = int((deg % 360) / 22.5 + 0.5)
        return self.directions_cardinal[idx]

    def _weather_description(self, code: int) -> str:
        return self.WEATHER_CODES.get(code, "Unknown")

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    def _base_params(self) -> dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": "auto"
        }

    def _get_lat_long_1(self) -> bool:
        params = {"name": self.location, "count": 1, "format": "json"}
        data = self._request(self.GEOCODING_URL, params)

        if "results" not in data or not data["results"]:
            return False

        loc = data["results"][0]
        self.latitude = float(loc["latitude"])
        self.longitude = float(loc["longitude"])
        self.timezone = loc["timezone"]
        
        return True

    def _get_lat_long_2(self):
        geolocator = Nominatim(timeout=10, user_agent="my_python_projet_alpha")
        loc = geolocator.geocode(self.location)
        if loc:
            raw_data = loc.raw
            latitude = raw_data.get("lat", None)
            longitude = raw_data.get("lon", None)

            if latitude is not None and longitude is not None:
                self.latitude = float(latitude)
                self.longitude = float(longitude)

    def get_lat_long(self) -> None:
        if not self._get_lat_long_1():
            self._get_lat_long_2()

    def forecast(self) -> dict[str, pd.DataFrame]:
        self.get_lat_long()

        params = {
            **self._base_params(),
            "forecast_minutely_15": 24,
            "forecast_hours": 48,
            "forecast_days": 14,
            "minutely_15": [
                "weather_code",
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m",
                "wind_direction_10m"
            ],
            "hourly": [
                "weather_code",
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "precipitation_probability",
                "wind_speed_10m",
                "wind_direction_10m"
            ],
            "daily": [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max",
                "wind_direction_10m_dominant"
            ],
        }

        data = self._request(self.FORECAST_URL, params)
        
        if self.timezone is not None:
            current_time = int(datetime.now(pytz.timezone(f'{self.timezone}')).hour)
        else:
            current_time = int(datetime.now(pytz.timezone('Europe/Brussels')).hour)

        # # # minutely_15 # # #
        minutely_15 = data["minutely_15"]
        minutely_15_df = pd.DataFrame({
            "time": minutely_15["time"],
            "weather": [self._weather_description(code) for code in minutely_15["weather_code"]],
            "temperature_C": minutely_15["temperature_2m"],
            "feels_like_C": minutely_15["apparent_temperature"],
            "humidity_%": minutely_15["relative_humidity_2m"],
            "rain_mm": minutely_15["precipitation"],
            "wind_kmh": minutely_15["wind_speed_10m"],
            "wind_direction": minutely_15["wind_direction_10m"]
        })
        
        minutely_15_df["time"] = pd.to_datetime(minutely_15_df["time"]).dt.strftime("%Y-%m-%d %H:%M")
        minutely_15_df["wind_direction"] = minutely_15_df["wind_direction"].apply(self._deg_to_cardinal)

        # # # HOURLY # # #
        hourly = data["hourly"]
        hourly_df = pd.DataFrame({
            "time": hourly["time"][:-current_time],
            "weather": [self._weather_description(code) for code in hourly["weather_code"][:-current_time]],
            "temperature_C": hourly["temperature_2m"][:-current_time],
            "feels_like_C": hourly["apparent_temperature"][:-current_time],
            "humidity_%": hourly["relative_humidity_2m"][:-current_time],
            "rain_mm": hourly["precipitation"][:-current_time],
            "rain_probability_%": hourly["precipitation_probability"][:-current_time],
            "wind_kmh": hourly["wind_speed_10m"][:-current_time],
            "wind_direction": hourly["wind_direction_10m"][:-current_time]
        })
        
        hourly_df["time"] = pd.to_datetime(hourly_df["time"]).dt.strftime("%Y-%m-%d %H:%M")
        hourly_df["wind_direction"] = hourly_df["wind_direction"].apply(self._deg_to_cardinal)
        
        # # # DAILY # # #
        daily = data["daily"]
        daily_df = pd.DataFrame({
            "date": daily["time"],
            "weather": [self._weather_description(code) for code in daily["weather_code"]],
            "max_temp_C": daily["temperature_2m_max"],
            "min_temp_C": daily["temperature_2m_min"],
            "rain_mm": daily["precipitation_sum"],
            "max_wind_kmh": daily["wind_speed_10m_max"],
            "wind_direction": daily["wind_direction_10m_dominant"]
        })

        daily_df["wind_direction"] = daily_df["wind_direction"].apply(self._deg_to_cardinal)

        return {"minutely_15": minutely_15_df, "hourly": hourly_df, "daily": daily_df}

    def historical(self, days_back: int = 7) -> dict[str, pd.DataFrame]:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days_back)

        params = {
            **self._base_params(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "wind_speed_10m"
            ],
            "daily": [
                "temperature_2m_mean",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max"
            ]
        }

        data = self._request(self.HISTORICAL_URL, params)

        hourly = data["hourly"]
        hourly_df = pd.DataFrame({
            "time": hourly["time"],
            "temperature_C": hourly["temperature_2m"],
            "feels_like_C": hourly["apparent_temperature"],
            "humidity_%": hourly["relative_humidity_2m"],
            "rain_mm": hourly["precipitation"],
            "wind_kmh": hourly["wind_speed_10m"]
        })

        daily = data["daily"]
        daily_df = pd.DataFrame({
            "date": daily["time"],
            "mean_temp_C": daily["temperature_2m_mean"],
            "max_temp_C": daily["temperature_2m_max"],
            "min_temp_C": daily["temperature_2m_min"],
            "rain_mm": daily["precipitation_sum"],
            "max_wind_kmh": daily["wind_speed_10m_max"]
        })

        return {"hourly": hourly_df, "daily": daily_df}


def main() -> None:
    parser = argparse.ArgumentParser(description="Weather forecast CLI")
    parser.add_argument("location", type=str, nargs="?", default="Namur", help="Location to forecast (default: Namur)")
    args = parser.parse_args()
    weather = WeatherForecast(args.location)
    forecast = weather.forecast()

    print(f"\n📍 {args.location} - Weather Forecast")
    print("\n--- 15min WEATHER ---")
    print(forecast["minutely_15"].to_markdown(headers='keys', tablefmt='psql', index=False))

    print("\n--- NEXT HOURS WEATHER ---")
    print(forecast["hourly"].to_markdown(headers='keys', tablefmt='psql', index=False))

    print("\n--- NEXT DAY WEATHER ---")
    print(forecast["daily"].to_markdown(headers='keys', tablefmt='psql', index=False))


if __name__ == "__main__":
    main()



