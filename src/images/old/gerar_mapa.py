#!/usr/bin/env python3

import os
import math
import argparse

import pandas as pd
import staticmaps
from PIL import Image, ImageDraw


# ============================================================
# PROJEÇÃO WEB MERCATOR
# ============================================================

def project(lat, lon, zoom):
    tile_size = 256
    scale = tile_size * (2 ** zoom)

    lat = max(min(lat, 85.05112878), -85.05112878)

    x = (lon + 180.0) / 360.0 * scale

    lat_rad = math.radians(lat)

    y = (
        (1.0 - math.asinh(math.tan(lat_rad)) / math.pi)
        / 2.0
        * scale
    )

    return x, y


def latlon_to_pixel(
    latitude,
    longitude,
    center_lat,
    center_lon,
    zoom,
    width,
    height
):
    scale = 256 * (2 ** zoom)

    x, y = project(latitude, longitude, zoom)
    cx, cy = project(center_lat, center_lon, zoom)

    dx = x - cx

    # Corrige passagem pela linha internacional de data
    if dx > scale / 2:
        dx -= scale
    elif dx < -scale / 2:
        dx += scale

    px = dx + width / 2
    py = y - cy + height / 2

    return px, py


# ============================================================
# ZOOM DO TRAJETO INTEIRO
# ============================================================

def calcular_zoom(
    latitudes,
    longitudes,
    width,
    height,
    padding=0.10
):
    min_lat = min(latitudes)
    max_lat = max(latitudes)
    min_lon = min(longitudes)
    max_lon = max(longitudes)

    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    if max_lat == min_lat:
        max_lat += 0.001
        min_lat -= 0.001

    if max_lon == min_lon:
        max_lon += 0.001
        min_lon -= 0.001

    usable_width = width * (1 - padding * 2)
    usable_height = height * (1 - padding * 2)

    for zoom in range(20, -1, -1):

        x1, y1 = project(min_lat, min_lon, zoom)
        x2, y2 = project(max_lat, max_lon, zoom)

        map_width = abs(x2 - x1)
        map_height = abs(y2 - y1)

        if (
            map_width <= usable_width
            and map_height <= usable_height
        ):
            return zoom, center_lat, center_lon

    return 0, center_lat, center_lon


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Gera frames de um percurso com enquadramento "
            "static ou dynamic."
        )
    )

    parser.add_argument(
        "--csv",
        default="dados.csv",
        help="Arquivo CSV de entrada."
    )

    parser.add_argument(
        "--frames",
        default="frames",
        help="Diretório onde os frames serão gravados."
    )

    parser.add_argument(
        "--width",
        type=int,
        default=960
    )

    parser.add_argument(
        "--height",
        type=int,
        default=540
    )

    parser.add_argument(
        "--marker-size",
        type=int,
        default=12,
        help="Tamanho da gota azul."
    )

    parser.add_argument(
        "--point-size",
        type=int,
        default=6,
        help="Diâmetro dos pontos em pixels."
    )

    parser.add_argument(
        "--line-width",
        type=int,
        default=4,
        help="Espessura da rota."
    )

    parser.add_argument(
        "--show-route",
        action="store_true",
        default=False,
        help="Mostra a rota COMPLETA durante todo o vídeo."
    )

    parser.add_argument(
        "--view",
        choices=["static", "dynamic"],
        default="static",
        help=(
            "static = trajeto inteiro fixo; "
            "dynamic = acompanha o ponto atual."
        )
    )

    parser.add_argument(
        "--zoom",
        type=int,
        default=None,
        help=(
            "Zoom manual no modo static. "
            "Se omitido, calcula automaticamente."
        )
    )

    parser.add_argument(
        "--dynamic-zoom",
        type=int,
        default=14,
        help=(
            "Zoom fixo no modo dynamic. "
            "Padrão: 14."
        )
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # VERIFICAÇÕES
    # --------------------------------------------------------

    if not os.path.isfile(args.csv):
        print(
            f"ERRO: arquivo não encontrado: "
            f"{args.csv}"
        )
        return

    os.makedirs(args.frames, exist_ok=True)

    df = pd.read_csv(args.csv)

    required = [
        "latitude",
        "longitude",
        "timestamp"
    ]

    for column in required:
        if column not in df.columns:
            print(
                f"ERRO: coluna '{column}' "
                f"não encontrada."
            )
            return

    if len(df) == 0:
        print("ERRO: CSV vazio.")
        return

    # --------------------------------------------------------
    # TIMESTAMPS
    # --------------------------------------------------------

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    if not df["timestamp"].is_monotonic_increasing:

        print(
            "Timestamps fora de ordem. Ordenando..."
        )

        df = (
            df
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    # --------------------------------------------------------
    # COORDENADAS
    # --------------------------------------------------------

    latitudes = (
        df["latitude"]
        .astype(float)
        .tolist()
    )

    longitudes = (
        df["longitude"]
        .astype(float)
        .tolist()
    )

    all_coords = [
        staticmaps.create_latlng(lat, lon)
        for lat, lon in zip(
            latitudes,
            longitudes
        )
    ]

    # --------------------------------------------------------
    # CONFIGURAÇÃO DO MODO STATIC
    # --------------------------------------------------------

    if args.view == "static":

        if args.zoom is None:

            zoom, center_lat, center_lon = (
                calcular_zoom(
                    latitudes,
                    longitudes,
                    args.width,
                    args.height
                )
            )

        else:

            zoom = args.zoom

            center_lat = (
                min(latitudes) +
                max(latitudes)
            ) / 2

            center_lon = (
                min(longitudes) +
                max(longitudes)
            ) / 2

    # --------------------------------------------------------
    # CONFIGURAÇÃO DO MODO DYNAMIC
    # --------------------------------------------------------

    else:

        zoom = args.dynamic_zoom

    # --------------------------------------------------------
    # INFORMAÇÕES
    # --------------------------------------------------------

    print()
    print("========================================")
    print("       GERAÇÃO DOS FRAMES")
    print("========================================")
    print()

    print(f"CSV              : {args.csv}")
    print(f"Frames           : {args.frames}")

    print(
        f"Resolução        : "
        f"{args.width}x{args.height}"
    )

    print(
        f"Modo             : "
        f"{args.view}"
    )

    if args.view == "static":

        print(
            f"Zoom             : "
            f"{zoom}"
        )

        print(
            f"Centro           : "
            f"{center_lat:.6f}, "
            f"{center_lon:.6f}"
        )

    else:

        print(
            f"Zoom dinâmico    : "
            f"{args.dynamic_zoom}"
        )

        print(
            "Centro           : "
            "ponto atual"
        )

    print(
        f"Coordenadas      : "
        f"{len(all_coords)}"
    )

    print(
        f"Pontos           : "
        f"{args.point_size}px"
    )

    print(
        f"Rota completa    : "
        f"{'SIM' if args.show_route else 'NÃO'}"
    )

    print()

    # ========================================================
    # GERAÇÃO DOS FRAMES
    # ========================================================

    for i in range(len(df)):

        print(
            f"Gerando frame "
            f"{i + 1}/{len(df)}...",
            end="\r"
        )

        # ----------------------------------------------------
        # ENQUADRAMENTO
        # ----------------------------------------------------

        if args.view == "static":

            frame_center_lat = center_lat
            frame_center_lon = center_lon
            frame_zoom = zoom

        else:

            # Dynamic:
            # o centro é SEMPRE o ponto atual.

            frame_center_lat = latitudes[i]
            frame_center_lon = longitudes[i]
            frame_zoom = args.dynamic_zoom

        # ----------------------------------------------------
        # RENDERIZA MAPA
        # ----------------------------------------------------

        context = staticmaps.Context()

        context.set_tile_provider(
            staticmaps.tile_provider_OSM
        )

        context.set_center(
            staticmaps.create_latlng(
                frame_center_lat,
                frame_center_lon
            )
        )

        context.set_zoom(frame_zoom)

        # ----------------------------------------------------
        # ROTA COMPLETA
        # ----------------------------------------------------

        if args.show_route:

            context.add_object(
                staticmaps.Line(
                    all_coords,
                    color=staticmaps.RED,
                    width=args.line_width
                )
            )

        # ----------------------------------------------------
        # GOTA AZUL ATUAL
        # ----------------------------------------------------

        context.add_object(
            staticmaps.Marker(
                all_coords[i],
                color=staticmaps.BLUE,
                size=args.marker_size
            )
        )

        # ----------------------------------------------------
        # RENDER
        # ----------------------------------------------------

        rendered = context.render_cairo(
            args.width,
            args.height
        )

        temp_path = os.path.join(
            args.frames,
            ".frame_temp.png"
        )

        rendered.write_to_png(temp_path)

        frame = Image.open(
            temp_path
        ).convert("RGBA")

        draw = ImageDraw.Draw(frame)

        # ----------------------------------------------------
        # PONTOS VERDES E VERMELHOS
        # ----------------------------------------------------

        radius = args.point_size / 2

        for j in range(len(df)):

            # Não desenha ponto sobre a gota atual
            if j == i:
                continue

            px, py = latlon_to_pixel(
                latitudes[j],
                longitudes[j],
                frame_center_lat,
                frame_center_lon,
                frame_zoom,
                args.width,
                args.height
            )

            # Ponto já percorrido
            if j < i:

                color = (
                    0,
                    180,
                    0,
                    255
                )

            # Ponto futuro
            else:

                color = (
                    220,
                    0,
                    0,
                    255
                )

            draw.ellipse(
                (
                    px - radius,
                    py - radius,
                    px + radius,
                    py + radius
                ),
                fill=color
            )

        # ----------------------------------------------------
        # SALVA FRAME
        # ----------------------------------------------------

        filename = os.path.join(
            args.frames,
            f"frame_{i:04d}.png"
        )

        frame.convert("RGB").save(
            filename,
            "PNG"
        )

    # --------------------------------------------------------
    # REMOVE TEMPORÁRIO
    # --------------------------------------------------------

    try:
        os.remove(
            os.path.join(
                args.frames,
                ".frame_temp.png"
            )
        )
    except OSError:
        pass

    print()
    print()
    print("Frames gerados com sucesso!")
    print()

    print(
        f"Diretório : "
        f"{os.path.abspath(args.frames)}"
    )

    print(
        f"Quantidade: "
        f"{len(df)}"
    )


if __name__ == "__main__":
    main()

