#!/usr/bin/env python3

import os
import argparse
import pandas as pd
import subprocess
import tempfile


# ============================================================
# ARGUMENTOS
# ============================================================

parser = argparse.ArgumentParser(
    description=(
        "Gera um vídeo a partir dos frames PNG usando "
        "os timestamps do CSV."
    )
)

parser.add_argument(
    "--csv",
    default="dados.csv",
    help="Arquivo CSV com latitude, longitude e timestamp."
)

parser.add_argument(
    "--frames",
    default="frames",
    help="Diretório contendo os frames PNG."
)

parser.add_argument(
    "--output",
    default="video_deslocamento.mp4",
    help="Arquivo MP4 de saída."
)

parser.add_argument(
    "--speed",
    type=float,
    default=10,
    help="Velocidade do vídeo. 10 = 10x mais rápido."
)

parser.add_argument(
    "--min-duration",
    type=float,
    default=0.02,
    help="Duração mínima de um frame em segundos."
)

parser.add_argument(
    "--start-delay",
    type=float,
    default=0,
    help="Tempo inicial em segundos."
)

parser.add_argument(
    "--end-delay",
    type=float,
    default=0,
    help="Tempo final em segundos."
)

parser.add_argument(
    "--fps",
    type=float,
    default=25,
    help="FPS do vídeo final."
)

args = parser.parse_args()


# ============================================================
# VALIDAÇÕES
# ============================================================

if args.speed <= 0:
    parser.error("--speed deve ser maior que zero.")

if args.min_duration <= 0:
    parser.error("--min-duration deve ser maior que zero.")

if args.start_delay < 0:
    parser.error("--start-delay não pode ser negativo.")

if args.end_delay < 0:
    parser.error("--end-delay não pode ser negativo.")

if args.fps <= 0:
    parser.error("--fps deve ser maior que zero.")

if not os.path.isfile(args.csv):
    raise FileNotFoundError(
        f"CSV não encontrado: {args.csv}"
    )

if not os.path.isdir(args.frames):
    raise FileNotFoundError(
        f"Diretório de frames não encontrado: {args.frames}"
    )


# ============================================================
# CARREGA CSV
# ============================================================

df = pd.read_csv(args.csv)

if "timestamp" not in df.columns:
    raise ValueError(
        "O CSV precisa possuir a coluna 'timestamp'."
    )

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    errors="coerce"
)

df = (
    df
    .dropna(subset=["timestamp"])
    .sort_values("timestamp")
    .reset_index(drop=True)
)

num_frames = len(df)

if num_frames == 0:
    raise ValueError(
        "Nenhum timestamp válido encontrado."
    )


# ============================================================
# VERIFICA FRAMES
# ============================================================

frame_paths = []

for i in range(num_frames):

    path = os.path.abspath(
        os.path.join(
            args.frames,
            f"frame_{i:04d}.png"
        )
    )

    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Frame não encontrado: {path}"
        )

    frame_paths.append(path)


# ============================================================
# TEMPO REAL DA VIAGEM
# ============================================================

if num_frames > 1:

    real_total = (
        df["timestamp"].iloc[-1]
        - df["timestamp"].iloc[0]
    ).total_seconds()

else:

    real_total = 0.0


if real_total < 0:
    raise ValueError(
        "Os timestamps estão inválidos."
    )


# ============================================================
# CALCULA INTERVALOS
# ============================================================

durations = []

for i in range(num_frames - 1):

    delta = (
        df["timestamp"].iloc[i + 1]
        - df["timestamp"].iloc[i]
    ).total_seconds()

    if delta < 0:
        raise ValueError(
            f"Timestamp inválido entre os frames "
            f"{i} e {i + 1}."
        )

    duration = delta / args.speed

    duration = max(
        duration,
        args.min_duration
    )

    durations.append(duration)


# ============================================================
# DURAÇÃO DO DESLOCAMENTO
# ============================================================

movement_duration = (
    real_total / args.speed
)


# ============================================================
# DURAÇÃO TOTAL ESPERADA
# ============================================================

expected_duration = (
    args.start_delay
    + movement_duration
    + args.end_delay
)


# ============================================================
# CRIA ARQUIVO CONCAT
# ============================================================
#
# IMPORTANTE:
#
# O primeiro frame recebe:
#
#     start-delay + intervalo até o próximo ponto
#
# Os frames intermediários recebem:
#
#     intervalo até o próximo ponto
#
# O último frame recebe SOMENTE:
#
#     end-delay
#
# Assim o intervalo anterior não é repetido no último frame.
#
# ============================================================

concat_file = tempfile.NamedTemporaryFile(
    mode="w",
    suffix=".txt",
    delete=False,
    encoding="utf-8"
)

concat_path = concat_file.name


try:

    if num_frames == 1:

        total = (
            args.start_delay
            + args.end_delay
        )

        if total <= 0:
            total = 1.0

        concat_file.write(
            f"file '{frame_paths[0]}'\n"
        )

        concat_file.write(
            f"duration {total:.9f}\n"
        )

    else:

        # ----------------------------------------------------
        # PRIMEIRO FRAME
        # ----------------------------------------------------

        first_duration = (
            args.start_delay
            + durations[0]
        )

        concat_file.write(
            f"file '{frame_paths[0]}'\n"
        )

        concat_file.write(
            f"duration {first_duration:.9f}\n"
        )

        # ----------------------------------------------------
        # FRAMES INTERMEDIÁRIOS
        # ----------------------------------------------------

        for i in range(1, num_frames - 1):

            concat_file.write(
                f"file '{frame_paths[i]}'\n"
            )

            concat_file.write(
                f"duration {durations[i]:.9f}\n"
            )

        # ----------------------------------------------------
        # ÚLTIMO FRAME
        # ----------------------------------------------------
        #
        # O concat demuxer precisa de uma entrada seguinte
        # para fechar corretamente a duração da entrada anterior.
        #
        # Sem a repetição abaixo, o FFmpeg pode reutilizar
        # a duração do intervalo anterior para o último frame.
        #
        # ----------------------------------------------------

        last_frame = frame_paths[-1]

        if args.end_delay > 0:

            # Último frame durante o end-delay
            concat_file.write(
                f"file '{last_frame}'\n"
            )

            concat_file.write(
                f"duration {args.end_delay:.9f}\n"
            )

            # Repetição necessária para que o FFmpeg
            # respeite a duração acima.
            concat_file.write(
                f"file '{last_frame}'\n"
            )

        else:

            # Sem end-delay, ainda repetimos o último frame
            # para evitar que o FFmpeg herde a duração
            # do intervalo anterior.
            concat_file.write(
                f"file '{last_frame}'\n"
            )

            concat_file.write(
                f"duration {args.min_duration:.9f}\n"
            )

            concat_file.write(
                f"file '{last_frame}'\n"
            )


    concat_file.close()


    # ========================================================
    # RESUMO
    # ========================================================

    print()
    print("=" * 70)
    print("CONFIGURAÇÃO DO VÍDEO")
    print("=" * 70)

    print(f"CSV:                  {args.csv}")
    print(f"Frames:               {args.frames}")
    print(f"Saída:                {args.output}")
    print(f"Velocidade:           {args.speed:g}x")
    print(f"FPS:                  {args.fps:g}")
    print(
        f"Duração mínima:       "
        f"{args.min_duration:g} s"
    )
    print(
        f"Delay inicial:        "
        f"{args.start_delay:g} s"
    )
    print(
        f"Delay final:          "
        f"{args.end_delay:g} s"
    )
    print(
        f"Quantidade de frames: "
        f"{num_frames}"
    )

    print()
    print(
        f"Tempo real viagem:    "
        f"{real_total:.2f} s"
    )

    print(
        f"Deslocamento vídeo:   "
        f"{movement_duration:.2f} s"
    )

    print(
        f"Tempo total esperado: "
        f"{expected_duration:.2f} s"
    )

    print()
    print(
        f"Tempo real:            "
        f"{real_total / 3600:.2f} horas"
    )

    print(
        f"Tempo vídeo esperado:  "
        f"{expected_duration / 60:.2f} minutos"
    )

    print()
    print("Gerando vídeo com FFmpeg...")
    print()


    # ========================================================
    # FFMPEG
    # ========================================================

    command = [
        "ffmpeg",
        "-y",

        # Entrada concat
        "-f", "concat",
        "-safe", "0",
        "-i", concat_path,

        # FPS constante
        "-fps_mode", "cfr",
        "-r", str(args.fps),

        # Codec
        "-c:v", "libx264",

        # Compatibilidade
        "-pix_fmt", "yuv420p",

        # Timebase convencional
        "-video_track_timescale", "90000",

        # Evita metadata desnecessária
        "-map_metadata", "-1",

        args.output
    ]

    subprocess.run(
        command,
        check=True
    )


finally:

    # ========================================================
    # REMOVE TEMPORÁRIO
    # ========================================================

    try:
        os.unlink(concat_path)
    except OSError:
        pass


# ============================================================
# FINAL
# ============================================================

print()
print("=" * 70)
print("VÍDEO GERADO COM SUCESSO")
print("=" * 70)

print(
    f"Arquivo:              {args.output}"
)

print(
    f"Velocidade:           {args.speed:g}x"
)

print(
    f"FPS:                  {args.fps:g}"
)

print(
    f"Delay inicial:        {args.start_delay:g} s"
)

print(
    f"Delay final:          {args.end_delay:g} s"
)

print(
    f"Duração esperada:     "
    f"{expected_duration:.2f} s"
)

print("=" * 70)

