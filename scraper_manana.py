"""
Scraper de Partidos de Mañana de BetPlay (Sin Esports)
=====================================================
Módulo optimizado de compatibilidad hacia atrás que delega en el motor unificado
`scraper_betplay_cuotas.py`.
- Extrae la totalidad de partidos de mañana en BetPlay.
- Filtra permanentemente Esports y Cyber.
- Clasifica las cuotas en las 9 categorías canónicas y almacena en SQLite / JSON.
- Recalcula automáticamente el Radar de Valor.
"""

import sys
import argparse
from scraper_betplay_cuotas import ejecutar_scraper_cuotas


def ejecutar_scraper_manana(fecha_filtro: str = None, workers: int = 8):
    if fecha_filtro:
        ejecutar_scraper_cuotas(modo="fecha", fecha_especifica=fecha_filtro, workers=workers)
    else:
        ejecutar_scraper_cuotas(modo="manana", workers=workers)


def main():
    parser = argparse.ArgumentParser(description="Scraper de cuotas de partidos de mañana en BetPlay (sin Esports).")
    parser.add_argument("--fecha", help="Fecha objetivo en formato YYYY-MM-DD (por defecto mañana)")
    parser.add_argument("--workers", type=int, default=8, help="Número de hilos concurrentes (por defecto 8)")
    args = parser.parse_args()
    ejecutar_scraper_manana(fecha_filtro=args.fecha, workers=args.workers)


if __name__ == "__main__":
    main()
