import httpx
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from collections import Counter
from zoneinfo import ZoneInfo

class VentuskyService:
    HORARIOS = ["02:00", "05:00", "08:00", "11:00", "14:00", "17:00", "20:00", "23:00"]
    TRAMOS = {
        "madrugada": ["02:00", "05:00"],
        "mañana": ["08:00", "11:00"],
        "tarde": ["14:00", "17:00"],
        "noche": ["20:00", "23:00"]
    }
    TRAMOS_RANGOS = {
        "madrugada": range(0, 6),
        "mañana": range(6, 12),
        "tarde": range(12, 18),
        "noche": range(18, 24),
    }

    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon
        self.raw_forecast: Optional[Dict[str, Any]] = None
        self.note: Optional[Dict[str, Any]] = None
        self.astro_dates: Optional[List[str]] = None
        self.organized_days: Optional[List[Dict[str, Any]]] = None
        self.next_24h: Optional[List[Dict[str, Any]]] = None

        # Cache precalculado en load_forecast() para evitar recomputar en cada getter
        self.hoy_horas: List[Dict[str, Any]] = []
        self.fecha_hoy: Optional[str] = None

    async def fetch_html(self) -> str:
        url = f"https://www.ventusky.com/es/{self.lat:.3f};{self.lon:.3f}"
        headers = {"User-Agent": "Mozilla/5.0 Chrome/120 Safari/537.36"}
        async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r.text

    # ------------------------------------------------------------------
    # Helpers de agregación
    # ------------------------------------------------------------------
    @staticmethod
    def _aggregate_bloque(horas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Agrega una lista de horas (formato next_24h) en un resumen tipo daily/tramo."""
        total_mm = sum([h["precipitacion_mm"] or 0 for h in horas])
        temperaturas = [h["temperatura_c"] for h in horas if h["temperatura_c"] is not None]
        velocidades = [h["velocidad_viento_kmh"] for h in horas if h["velocidad_viento_kmh"] is not None]
        rafaga = [h["rafaga_kmh"] for h in horas if h["rafaga_kmh"] is not None]

        dirs = [h["direccion_viento"] for h in horas if h["direccion_viento"] is not None]
        direccion_viento = Counter(dirs).most_common(1)[0][0] if dirs else None

        dirs_grados = [h["direccion_grados"] for h in horas if h["direccion_grados"] is not None]
        direccion_grados = Counter(dirs_grados).most_common(1)[0][0] if dirs_grados else None

        return {
            "sr": total_mm,
            "td_min": min(temperaturas) if temperaturas else None,
            "td_max": max(temperaturas) if temperaturas else None,
            "vsd": round(sum(velocidades) / len(velocidades), 1) if velocidades else None,
            "vg": max(rafaga) if rafaga else 0,
            "vdId": direccion_viento,
            "vd45": direccion_grados,
        }

    @staticmethod
    def _aggregate_bloque_json(horas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Igual que _aggregate_bloque pero para horas en formato organized_days (claves cortas)."""
        total_mm = sum([h["sr"] or 0 for h in horas])
        temperaturas = [h["td"] for h in horas if h["td"] is not None]
        velocidades = [h["vsd"] for h in horas if h["vsd"] is not None]
        rafaga = [h["vg"] for h in horas if h["vg"] is not None]

        dirs = [h["vdId"] for h in horas if h["vdId"] is not None]
        direccion_viento = Counter(dirs).most_common(1)[0][0] if dirs else None

        dirs45 = [h["vd45"] for h in horas if h["vd45"] is not None]
        direccion_viento_45 = Counter(dirs45).most_common(1)[0][0] if dirs45 else None

        return {
            "sr": total_mm,
            "td_min": min(temperaturas) if temperaturas else None,
            "td_max": max(temperaturas) if temperaturas else None,
            "vsd": round(sum(velocidades) / len(velocidades), 1) if velocidades else None,
            "vg": max(rafaga) if rafaga else None,
            "vdId": direccion_viento,
            "vd45": direccion_viento_45,
        }

    # ------------------------------------------------------------------
    # Extracción "próximas 24 horas" (tabla HTML)
    # ------------------------------------------------------------------
    @staticmethod
    def extract_next_24h(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        block = soup.find("div", class_="forecast_block")
        if not block:
            return []
        table = block.find("table", class_="mesto-predpoved")
        if not table:
            return []

        thead = table.find("thead")
        headers = []
        if thead:
            for th in thead.find_all("th"):
                span = th.find("span")
                dia_relativo = span.get_text(strip=True) if span else "hoy"
                # Texto directo del th (antes del span), sin mutar el árbol
                hora_node = th.find(string=True, recursive=False)
                hora = hora_node.strip() if hora_node else th.get_text(strip=True)
                headers.append({"hora": hora, "dia_relativo": dia_relativo})

        tbody = table.find("tbody")
        if not tbody:
            return []
        row = tbody.find("tr")
        if not row:
            return []
        celdas = row.find_all("td")

        resultado = []
        for i, td in enumerate(celdas):
            img = td.find("img")
            condicion = img.get("alt") if img else None

            temp_div = td.find("div", class_=lambda c: c and "temperature_line" in c)
            temperatura = None
            if temp_div:
                m = re.search(r"(-?\d+)", temp_div.get_text(strip=True))
                if m:
                    temperatura = int(m.group(1))

            # Spans directos del td: [0] = mm de lluvia, el que tiene class "prob-line" = probabilidad
            direct_spans = td.find_all("span", recursive=False)
            precip_span = direct_spans[0] if direct_spans else None
            precipitacion_mm = None
            if precip_span:
                m = re.search(r"([\d.]+)", precip_span.get_text(strip=True))
                if m:
                    precipitacion_mm = float(m.group(1))

            prob_span = td.find("span", class_="prob-line")
            probabilidad = None
            if prob_span:
                m = re.search(r"(\d+)", prob_span.get_text(strip=True))
                if m:
                    probabilidad = int(m.group(1))

            wind_div = td.find("div", class_=lambda c: c and "wind_ico" in c)
            direccion_viento = None
            direccion_grados = None
            if wind_div:
                direccion_viento = wind_div.get_text(strip=True)
                for c in wind_div.get("class", []):
                    if c.startswith("arrow_"):
                        direccion_grados = int(c.replace("arrow_", ""))

            velocidad_viento = None
            rafaga = None
            for d in td.find_all("div"):
                classes = d.get("class") or []
                if "wind_ico" in classes or any("temperature_line" in c for c in classes):
                    continue
                texto = d.get_text(strip=True)
                if "Ráfaga" in texto:
                    m = re.search(r"(\d+)", texto)
                    if m:
                        rafaga = int(m.group(1))
                elif "km/h" in texto and velocidad_viento is None:
                    m = re.search(r"(\d+)", texto)
                    if m:
                        velocidad_viento = int(m.group(1))

            header = headers[i] if i < len(headers) else {}
            resultado.append({
                "hora": header.get("hora"),
                "dia_relativo": header.get("dia_relativo"),
                "condicion": condicion,
                "temperatura_c": temperatura,
                "precipitacion_mm": precipitacion_mm,
                "probabilidad_precipitacion": probabilidad,
                "direccion_viento": direccion_viento,
                "direccion_grados": direccion_grados,
                "velocidad_viento_kmh": velocidad_viento,
                "rafaga_kmh": rafaga,
            })
        return resultado

    # ------------------------------------------------------------------
    # Extracción de metadata / fechas
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Carga principal
    # ------------------------------------------------------------------
    async def load_forecast(self):
        html = await self.fetch_html()
        soup = BeautifulSoup(html, "html.parser")
        parsed = self.parse_forecast_html(html)
        if "error" in parsed:
            raise Exception(parsed["error"])

        self.raw_forecast = parsed["forecast"]
        self.note = parsed["note"]
        self.astro_dates = parsed["astro_dates"]
        self.next_24h = self.extract_next_24h(soup)

        # Hora actual de Bolivia
        ahora_bo = datetime.now(ZoneInfo("America/La_Paz"))

        # Cache: horas restantes de "hoy" y fecha de hoy, calculado una sola vez
        self.hoy_horas = [h for h in self.next_24h if h.get("dia_relativo") == "hoy"]
        self.fecha_hoy = ahora_bo.strftime("%d/%m/%Y")

        # --- FIX: orden numérico real de las keys (d_0, d_1, ..., d_10, d_11) ---
        # sorted() por defecto ordena como string y desalinea d_10/d_11 antes que d_2, d_3...
        self.organized_days = []
        dias_keys = [k for k in self.raw_forecast.keys() if k.startswith("d_")]
        dias_keys.sort(key=lambda k: int(k.split("_")[1]))

        for idx, key in enumerate(dias_keys):
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

    # ------------------------------------------------------------------
    # Getters públicos
    # ------------------------------------------------------------------
    def get_forecast_next_24h(self) -> List[Dict[str, Any]]:
        return self.next_24h or []

    def get_forecast_hourly(self) -> List[Dict[str, Any]]:
        """
        Devuelve el pronóstico hora a hora. El primer bloque ("hoy") viene de la
        tabla de próximas 24h (granularidad de 1h, solo lo que resta del día).
        Los bloques siguientes (mañana en adelante) vienen del JSON data-forecast
        (granularidad de 3h: 02:00, 05:00, 08:00...).
        """
        resultado = []

        if self.hoy_horas:
            resultado.append({
                "id": "hoy",
                "fecha": self.fecha_hoy,
                "granularidad_horas": 1,
                "horarios": [
                    {
                        "h": h["hora"],
                        "td": h["temperatura_c"],
                        "sr": h["precipitacion_mm"],
                        "rp": h["probabilidad_precipitacion"],
                        "vdId": h["direccion_viento"],
                        "vd45": h["direccion_grados"],
                        "vsd": h["velocidad_viento_kmh"],
                        "vg": h["rafaga_kmh"],
                    }
                    for h in self.hoy_horas
                ]
            })

        for dia in (self.organized_days or []):
            dia_con_granularidad = {**dia, "granularidad_horas": 3}
            resultado.append(dia_con_granularidad)

        return resultado

    def get_forecast_daily(self) -> List[Dict[str, Any]]:
        daily_summary = []

        # Hoy
        if self.hoy_horas:
            resumen_hoy = self._aggregate_bloque(self.hoy_horas)
            daily_summary.append({
                "fecha": self.fecha_hoy,
                **resumen_hoy
            })

        # Días siguientes
        for dia in (self.organized_days or []):
            horas = dia["horarios"]
            if not horas:
                continue

            resumen = self._aggregate_bloque_json(horas)
            daily_summary.append({
                "fecha": dia["fecha"],
                **resumen
            })

        return daily_summary

    def get_forecast_by_tramos(self) -> List[Dict[str, Any]]:
        tramo_summary = []

        # "Hoy" reconstruido, agrupado por rango horario real (no por lista fija)
        if self.hoy_horas:
            resumen_hoy = {"fecha": self.fecha_hoy}
            for tramo, rango in self.TRAMOS_RANGOS.items():
                horas_tramo = [
                    h for h in self.hoy_horas
                    if h.get("hora") and int(h["hora"].split(":")[0]) in rango
                ]
                if not horas_tramo:
                    continue
                resumen_hoy[tramo] = self._aggregate_bloque(horas_tramo)
            tramo_summary.append(resumen_hoy)

        for dia in (self.organized_days or []):
            resumen_dia = {"fecha": dia["fecha"]}
            for tramo, horas_tramo in self.TRAMOS.items():
                horas = [h for h in dia["horarios"] if h["h"] in horas_tramo]
                if not horas:
                    continue
                resumen_dia[tramo] = self._aggregate_bloque_json(horas)
            tramo_summary.append(resumen_dia)

        return tramo_summary