"""
BoboCalc chart builder — matplotlib (static PNG/SVG) + plotly (interactive HTML).
Bar, Line, Pie, Scatter, Heatmap, Radar. Output usable in BoboWrite/BoboPresent.
"""
import os


def build(kind: str, labels, series, out_path: str, title: str = "") -> bool:
    """series = list of numbers (single) or list of (name, values) for multi."""
    ext = os.path.splitext(out_path)[1].lower()
    if ext == ".html":
        return _plotly(kind, labels, series, out_path, title)
    return _matplotlib(kind, labels, series, out_path, title)


def _norm_series(series):
    if series and isinstance(series[0], (list, tuple)) and len(series[0]) == 2:
        return series  # [(name, values), ...]
    return [("Serie 1", series)]


def _matplotlib(kind, labels, series, out_path, title):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        series = _norm_series(series)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        colors = ["#4a9eff", "#4ade80", "#ffb454", "#ff5d5d", "#bd93f9"]
        if kind == "pie":
            ax.pie(series[0][1], labels=labels, autopct="%1.0f%%",
                   colors=colors[:len(labels)])
        elif kind == "line":
            for i, (name, vals) in enumerate(series):
                ax.plot(labels, vals, marker="o", label=name, color=colors[i % 5])
            ax.legend()
        elif kind == "scatter":
            for i, (name, vals) in enumerate(series):
                ax.scatter(range(len(vals)), vals, label=name, color=colors[i % 5])
            ax.legend()
        elif kind == "heatmap":
            data = np.array([v for _, v in series])
            im = ax.imshow(data, cmap="Blues", aspect="auto")
            ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels)
            fig.colorbar(im)
        elif kind == "radar":
            ang = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
            ang += ang[:1]
            ax = plt.subplot(polar=True)
            for i, (name, vals) in enumerate(series):
                vv = list(vals) + [vals[0]]
                ax.plot(ang, vv, label=name, color=colors[i % 5]); ax.fill(ang, vv, alpha=0.1)
            ax.set_xticks(ang[:-1]); ax.set_xticklabels(labels); ax.legend()
        else:  # bar
            x = np.arange(len(labels)); w = 0.8 / max(1, len(series))
            for i, (name, vals) in enumerate(series):
                ax.bar(x + i * w, vals, w, label=name, color=colors[i % 5])
            ax.set_xticks(x + w * (len(series) - 1) / 2); ax.set_xticklabels(labels)
            if len(series) > 1:
                ax.legend()
        if title:
            ax.set_title(title)
        fig.tight_layout(); fig.savefig(out_path, dpi=120); plt.close(fig)
        return True
    except Exception as e:
        print("[chart_builder] %s" % e); return False


def _plotly(kind, labels, series, out_path, title):
    try:
        import plotly.graph_objects as go
        series = _norm_series(series)
        fig = go.Figure()
        if kind == "pie":
            fig.add_trace(go.Pie(labels=labels, values=series[0][1]))
        elif kind == "line":
            for name, vals in series:
                fig.add_trace(go.Scatter(x=labels, y=vals, mode="lines+markers", name=name))
        else:
            for name, vals in series:
                fig.add_trace(go.Bar(x=labels, y=vals, name=name))
        fig.update_layout(title=title, template="plotly_dark")
        fig.write_html(out_path)
        return True
    except Exception as e:
        print("[plotly] %s" % e)
        return _matplotlib(kind, labels, series, out_path.replace(".html", ".png"), title)
