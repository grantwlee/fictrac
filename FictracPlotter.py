import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DEFAULT_RADIUS_CM = 9.5
COLUMN_NAMES = [
    "frame counter",
    "cam delta rotation vector x",
    "cam delta rotation vector y",
    "cam delta rotation vector z",
    "delta rotation error score",
    "lab delta rotation vector x",
    "lab delta rotation vector y",
    "lab delta rotation vector z",
    "cam absolute rotation vector x",
    "cam absolute rotation vector y",
    "cam absolute rotation vector z",
    "lab absolute rotation vector x",
    "lab absolute rotation vector y",
    "lab absolute rotation vector z",
    "lab integrated x position",
    "lab integrated y position",
    "integrated animal heading",
    "animal direction movement",
    "animal movement speed",
    "integrated forward motion",
    "integrated side motion",
    "timestamp",
    "sequence counter",
    "delta timestamp",
    "alt. timestamp",
]


def file_management():
    try:
        from tkinter import Tk, filedialog
    except ImportError as exc:
        raise RuntimeError("Tkinter is required for interactive file selection.") from exc

    cur_date = datetime.now().strftime("%m-%d-%Y_%H-%M-%S")
    default_fname = f"{cur_date}.html"
    root = Tk()
    root.withdraw()
    input_path = filedialog.askopenfilename(
        title="Select Fictrac .Dat File",
        filetypes=[
            ("dat files", "*.dat"),
            ("csv files", "*.csv"),
            ("all files", "*.*"),
        ],
    )
    output_path = filedialog.asksaveasfilename(
        title="Save File",
        defaultextension=".html",
        initialfile=default_fname,
    )
    root.destroy()

    if not input_path:
        raise RuntimeError("No input file selected.")
    if not output_path:
        raise RuntimeError("No output file selected.")

    return input_path, output_path


def process_data(fname, radius_cm):
    if radius_cm <= 0:
        raise ValueError("radius_cm must be greater than 0.")

    try:
        df = pd.read_csv(fname, names=COLUMN_NAMES)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Input data file not found: {fname}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"Input data file is empty: {fname}") from exc

    if df.empty:
        raise ValueError(f"Input data file contains no rows: {fname}")

    df = df.drop(
        columns=[
            "lab integrated x position",
            "lab integrated y position",
            "integrated animal heading",
            "animal direction movement",
            "cam absolute rotation vector x",
            "cam absolute rotation vector y",
            "cam absolute rotation vector z",
            "lab absolute rotation vector x",
            "lab absolute rotation vector y",
            "lab absolute rotation vector z",
            "cam delta rotation vector x",
            "cam delta rotation vector y",
            "cam delta rotation vector z",
            "lab delta rotation vector x",
            "lab delta rotation vector y",
            "lab delta rotation vector z",
        ]
    )

    df["integrated forward motion"] *= radius_cm
    df["integrated side motion"] *= radius_cm
    df["animal movement speed"] *= radius_cm

    df["timestamp"] = df["timestamp"] - df["timestamp"].iloc[0]
    df["timestamp"] = df["timestamp"] / 1000
    df["delta timestamp"] = df["delta timestamp"] / 1000

    delta_seconds = df["delta timestamp"].replace(0, np.nan)
    df["animal movement speed"] = (
        df["animal movement speed"] / delta_seconds
    ).replace([np.inf, -np.inf], np.nan).fillna(0)

    delta_v = df["animal movement speed"].diff()
    delta_t = df["timestamp"].diff().replace(0, np.nan)
    df["acceleration"] = (delta_v / delta_t).replace([np.inf, -np.inf], np.nan).fillna(0)

    avgvel = df["animal movement speed"].mean()

    df["x per frame"] = df["integrated side motion"].diff().fillna(0)
    df["y per frame"] = df["integrated forward motion"].diff().fillna(0)
    df["dist per frame"] = np.sqrt((df["x per frame"]) ** 2 + (df["y per frame"]) ** 2)

    df["angular orientation"] = np.degrees(
        np.arctan2(df["y per frame"], df["x per frame"])
    ).fillna(0)
    df["angular orientation"] = df["angular orientation"] - 90
    df["angular orientation"] = ((df["angular orientation"] + 180) % 360 - 180) * -1

    final_x, final_y = df[["integrated side motion", "integrated forward motion"]].iloc[-1]
    final_angle = np.degrees(np.arctan2(final_y, final_x))
    final_angle = final_angle - 90
    final_angle = ((final_angle + 180) % 360 - 180) * -1

    towards = df[
        (df["angular orientation"] <= 60) & (df["angular orientation"] >= -60)
    ]["dist per frame"].sum()
    away = df[
        (df["angular orientation"] > 60) | (df["angular orientation"] < -60)
    ]["dist per frame"].sum()
    total = towards + away

    return df, avgvel, towards, away, total, final_angle


def make_graph(
    df,
    filepath,
    avgvel,
    towards,
    away,
    total,
    final_angle,
    radius_cm,
    show_graph=False,
):
    day = datetime.now().strftime("%m/%d/%Y")
    top25thresh = df["acceleration"].quantile(0.75)
    top50thresh = df["acceleration"].quantile(0.50)
    dftop25 = df[df["acceleration"] >= top25thresh]
    dftop50 = df[df["acceleration"] >= top50thresh]

    size = df[["integrated forward motion", "integrated side motion"]].abs().max().max().round()
    size = size + (size * 0.1)

    px_graph = px.line(
        df,
        x="integrated side motion",
        y="integrated forward motion",
        labels={
            "integrated side motion": "",
            "integrated forward motion": "",
        },
        hover_data={
            "acceleration": False,
            "integrated side motion": False,
            "integrated forward motion": False,
        },
        range_x=[-size, size],
        range_y=[-size, size],
    )

    px_graph.update_traces(
        customdata=df[["timestamp", "acceleration", "animal movement speed", "angular orientation"]],
        hovertemplate="<b>Timestamp: %{customdata[0]:.2f} s</b><br>"
        + "<b>Speed: %{customdata[2]:.2f} cm/s</b><br>"
        + "<b>Acceleration: %{customdata[1]:.2f} cm/s^2</b><br>"
        + "<b>Angular orientation: %{customdata[3]:.2f} deg</b><br>"
        + "<extra></extra>",
    )

    px_graph.add_trace(
        go.Scatter(
            x=dftop25["integrated side motion"],
            y=dftop25["integrated forward motion"],
            mode="markers",
            marker=dict(
                size=6,
                color="red",
                opacity=0.6,
                line=dict(width=1, color="black"),
            ),
            name="Top 25% Acceleration",
            visible=False,
            customdata=dftop25[["timestamp", "acceleration", "animal movement speed", "angular orientation"]],
            hovertemplate="<b>Timestamp: %{customdata[0]:.2f} s</b><br>"
            + "<b>Speed: %{customdata[2]:.2f} cm/s</b><br>"
            + "<b>Acceleration: %{customdata[1]:.2f} cm/s^2</b><br>"
            + "<b>Angular orientation: %{customdata[3]:.2f} deg</b><br>"
            + "<extra></extra>",
        )
    )

    px_graph.add_trace(
        go.Scatter(
            x=dftop50["integrated side motion"],
            y=dftop50["integrated forward motion"],
            mode="markers",
            marker=dict(
                size=6,
                color="orange",
                opacity=0.6,
                line=dict(width=1, color="black"),
            ),
            name="Top 50% Acceleration",
            visible=False,
            customdata=dftop50[["timestamp", "acceleration", "animal movement speed", "angular orientation"]],
            hovertemplate="<b>Timestamp: %{customdata[0]:.2f} s</b><br>"
            + "<b>Speed: %{customdata[2]:.2f} cm/s</b><br>"
            + "<b>Acceleration: %{customdata[1]:.2f} cm/s^2</b><br>"
            + "<b>Angular orientation: %{customdata[3]:.2f} deg</b><br>"
            + "<extra></extra>",
        )
    )

    px_graph.add_annotation(
        text=f"Total path length: {total:.2f} cm",
        xref="paper",
        yref="paper",
        x=1.04,
        y=0.95,
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor="left",
    )

    px_graph.add_annotation(
        text=f"Towards speaker: {towards:.2f} cm",
        xref="paper",
        yref="paper",
        x=1.04,
        y=0.9,
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor="left",
    )

    px_graph.add_annotation(
        text=f"Away from speaker: {away:.2f} cm",
        xref="paper",
        yref="paper",
        x=1.04,
        y=0.85,
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor="left",
    )

    px_graph.add_annotation(
        text=f"Final angular orientation: {final_angle:.2f} deg",
        xref="paper",
        yref="paper",
        x=1.04,
        y=0.8,
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor="left",
    )

    px_graph.add_annotation(
        text=f"Average velocity: {avgvel:.2f} cm/s",
        xref="paper",
        yref="paper",
        x=1.04,
        y=0.75,
        showarrow=False,
        font=dict(size=14, color="black"),
        bgcolor="lightgray",
        bordercolor="black",
        borderwidth=1,
        xanchor="left",
    )

    px_graph.add_annotation(
        text=f"Trackball size: {radius_cm:.2f} cm",
        xref="paper",
        yref="paper",
        x=1.04,
        y=0,
        showarrow=False,
        font=dict(size=14, color="black"),
        xanchor="left",
    )

    px_graph.update_layout(
        autosize=True,
        yaxis_scaleanchor="x",
        margin=dict(t=50, r=350),
        xaxis_title="x position (cm)",
        yaxis_title="y position (cm)",
        title={
            "text": f"Fictive Path of Animal<br><sup>Date: {day}</sup>",
            "x": 0.062,
            "y": 0.962,
            "xanchor": "left",
            "yanchor": "top",
            "font": {"size": 22},
        },
    )

    px_graph.update_layout(
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=1.0,
                y=1.06,
                xanchor="right",
                showactive=True,
                buttons=[
                    dict(
                        label="Path only",
                        method="update",
                        args=[{"visible": [True, False, False]}],
                    ),
                    dict(
                        label="Top 25% Accel values",
                        method="update",
                        args=[{"visible": [True, True, False]}],
                    ),
                    dict(
                        label="Top 50% Accel values",
                        method="update",
                        args=[{"visible": [True, False, True]}],
                    ),
                ],
            )
        ]
    )

    output_path = Path(filepath)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    px_graph.write_html(output_path)
    if show_graph:
        px_graph.show()

    return output_path


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Convert FicTrac .dat output into an HTML plot.")
    parser.add_argument("--input", dest="input_path", help="Path to the FicTrac .dat file.")
    parser.add_argument("--output", dest="output_path", help="Path to the HTML file to write.")
    parser.add_argument(
        "--radius-cm",
        dest="radius_cm",
        type=float,
        help="Trackball radius in centimeters used to scale the FicTrac output.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open the generated plot in a browser after writing the HTML file.",
    )

    args = parser.parse_args(argv)
    cli_mode = any(
        value is not None
        for value in (args.input_path, args.output_path, args.radius_cm)
    ) or args.show

    if cli_mode:
        missing = []
        if not args.input_path:
            missing.append("--input")
        if not args.output_path:
            missing.append("--output")
        if args.radius_cm is None:
            missing.append("--radius-cm")
        if missing:
            parser.error("CLI mode requires " + ", ".join(missing))

    return args, cli_mode


def main(argv=None):
    args, cli_mode = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        if cli_mode:
            input_path = args.input_path
            output_path = args.output_path
            radius_cm = args.radius_cm
            show_graph = args.show
        else:
            input_path, output_path = file_management()
            radius_cm = DEFAULT_RADIUS_CM
            show_graph = True

        df, avgvel, towards, away, total, final_angle = process_data(input_path, radius_cm)
        make_graph(
            df,
            output_path,
            avgvel,
            towards,
            away,
            total,
            final_angle,
            radius_cm,
            show_graph=show_graph,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

