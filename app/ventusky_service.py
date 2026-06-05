import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from typing import Any, Dict, List
from collections import Counter


class VentuskyService:
    HORARIOS = ["02:00", "05:00", "08:00", "11:00", "14:00", "17:00", "20:00", "23:00"]
    TRAMOS = {
        "madrugada": ["02:00", "05:00"],
        "mañana": ["08:00", "11:00"],
        "tarde": ["14:00", "17:00"],
        "noche": ["20:00", "23:00"]
    }

    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon
        self.raw_forecast = None
        self.note = None
        self.astro_dates = None
        self.organized_days = None

    async def fetch_html(self) -> str:
        url = f"https://www.ventusky.com/es/{self.lat:.3f};{self.lon:.3f}"
        headers = {"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"}
        async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.text

    @staticmethod
    def extract_page_note(soup: BeautifulSoup) -> Dict[str, Any]:
        note = soup.find("p", class_="note p-0")
        if not note:
            return {}
        text = note.get_text(strip=True)
        pattern = r"([0-9]+°[0-9]+'[NS]) / ([0-9]+°[0-9]+'[EW]) / Altitud (\d+) m / (\d{2}:\d{2} \d{2}/\d{2}/\d{4})"
        match = re.search(pattern, text)
        if not match:
            return {}

        lat_str, lon_str, alt, dt_str = match.groups()

        def dms_to_decimal(dms: str) -> float:
            deg, min_dir = dms.split("°")
            minutes = int(min_dir[:-1].replace("'", ""))
            direction = min_dir[-1]
            decimal = int(deg) + minutes / 60
            if direction in "SW":
                decimal *= -1
            return decimal

        return {
            "lat": dms_to_decimal(lat_str),
            "lon": dms_to_decimal(lon_str),
            "altitud_m": int(alt),
            "fecha_hora": datetime.strptime(dt_str, "%H:%M %d/%m/%Y").isoformat()
        }

    @staticmethod
    def extract_astro_dates(soup: BeautifulSoup) -> List[str]:
        select = soup.find("select", id="date_selector")
        if not select:
            return []
        return [opt.get_text(strip=True) for opt in select.find_all("option")]

    @staticmethod
    def parse_forecast_html(html: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        custom = soup.find("custom-forecast")
        if not custom or not custom.has_attr("data-forecast"):
            return {"error": "No se encontró el pronóstico."}
        forecast = json.loads(custom["data-forecast"])
        note = VentuskyService.extract_page_note(soup)
        dates = VentuskyService.extract_astro_dates(soup)
        return {
            "forecast": forecast,
            "note": note,
            "astro_dates": dates
        }

    async def load_forecast(self):
        html = await self.fetch_html()
        parsed = self.parse_forecast_html(html)
        if "error" in parsed:
            raise Exception(parsed["error"])

        self.raw_forecast = parsed["forecast"]
        self.note = parsed["note"]
        self.astro_dates = parsed["astro_dates"]

        self.organized_days = []
        for idx, key in enumerate(sorted(self.raw_forecast.keys())):
            if not key.startswith("d_"):
                continue
            day = self.raw_forecast[key]
            day_info = {
                "id": key,
                "fecha": self.astro_dates[idx] if idx < len(self.astro_dates) else None,
                "horarios": []
            }
            for i, hora in enumerate(self.HORARIOS):
                hora_info = {
                    "h": hora,
                    "td": day.get("td", [None])[i] if "td" in day else None,
                    "sr": day.get("sr", [0])[i] if "sr" in day else 0,
                    "rp": day.get("rp", [None])[i] if "rp" in day else None,
                    "vdId": day.get("vdId", [None])[i] if "vdId" in day else None,
                    "vd45": day.get("vd45", [None])[i] if "vd45" in day else None,
                    "vsd": day.get("vsd", [None])[i] if "vsd" in day else None,
                    "vg": day.get("vg", [None])[i] if "vg" in day else None,
                }
                day_info["horarios"].append(hora_info)
            self.organized_days.append(day_info)

    def get_forecast_hourly(self) -> List[Dict[str, Any]]:
        return self.organized_days

    def get_forecast_daily(self) -> List[Dict[str, Any]]:
        daily_summary = []
        for dia in self.organized_days:
            horas = dia["horarios"]
            if not horas:
                continue
            total_mm = sum([h["sr"] or 0 for h in horas])
            temperaturas = [h["td"] for h in horas if h["td"] is not None]
            probs = [h["rp"] for h in horas if h["rp"] is not None]
            velocidades = [h["vsd"] for h in horas if h["vsd"] is not None]
            rafaga = [h["vg"] for h in horas if h["vg"] is not None]

            dirs = [h["vdId"] for h in horas if h["vdId"] is not None]
            direccion_viento = Counter(dirs).most_common(1)[0][0] if dirs else None

            dirs45 = [h["vd45"] for h in horas if h["vd45"] is not None]
            direccion_viento_45 = Counter(dirs45).most_common(1)[0][0] if dirs45 else None

            daily_summary.append({
                "fecha": dia["fecha"],
                "sr": total_mm,
                "td_min": min(temperaturas) if temperaturas else None,
                "td_max": max(temperaturas) if temperaturas else None,
                "vsd": sum(velocidades) / len(velocidades) if velocidades else None,
                "vg": max(rafaga) if rafaga else None,
                "vdId": direccion_viento,
                "vd45": direccion_viento_45
            })
        return daily_summary

    def get_forecast_by_tramos(self) -> List[Dict[str, Any]]:
        tramo_summary = []
        for dia in self.organized_days:
            resumen_dia = {"fecha": dia["fecha"]}
            for tramo, horas_tramo in self.TRAMOS.items():
                horas = [h for h in dia["horarios"] if h["h"] in horas_tramo]
                if not horas:
                    continue

                total_mm = sum([h["sr"] or 0 for h in horas])
                temperaturas = [h["td"] for h in horas if h["td"] is not None]
                velocidades = [h["vsd"] for h in horas if h["vsd"] is not None]
                rafaga = [h["vg"] for h in horas if h["vg"] is not None]

                dirs = [h["vdId"] for h in horas if h["vdId"] is not None]
                direccion_viento = Counter(dirs).most_common(1)[0][0] if dirs else None

                dirs45 = [h["vd45"] for h in horas if h["vd45"] is not None]
                direccion_viento_45 = Counter(dirs45).most_common(1)[0][0] if dirs45 else None

                resumen_dia[tramo] = {
                    "sr": total_mm,
                    "td_min": min(temperaturas) if temperaturas else None,
                    "td_max": max(temperaturas) if temperaturas else None,
                    "vsd": sum(velocidades) / len(velocidades) if velocidades else None,
                    "vg": max(rafaga) if rafaga else None,
                    "vdId": direccion_viento,
                    "vd45": direccion_viento_45
                }
            tramo_summary.append(resumen_dia)
        return tramo_summary
