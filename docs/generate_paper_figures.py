"""Generate figures and architectural diagrams for the GesturePilot research paper."""
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from pathlib import Path

OUT_DIR = Path(r"D:\Development\Projects\MY PERSONAAL WORKS\VirtualMouse_Handoff_v003\VirtualMouse\docs\research_paper_assets")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 1. Pipeline Architecture Diagram
def generate_pipeline_diagram():
    fig, ax = plt.subplots(figsize=(10.5, 3.0), dpi=300)
    ax.axis("off")

    stages = [
        ("Webcam Capture\n(Threaded Grabber)", "#2b5c8f"),
        ("Hand Detector\n(MediaPipe Tasks)", "#1f77b4"),
        ("Safety Controller\n(Streak & Gate)", "#d62728"),
        ("Gesture Engine\n(Mutually Exclusive)", "#2ca02c"),
        ("Coordinate Mapper\n& One Euro Filter", "#9467bd"),
        ("Mouse Controller\n(Safety Guard)", "#ff7f0e"),
        ("OS Mouse Backend\n(PyAutoGUI / Win32)", "#8c564b"),
    ]

    x_step = 1.48
    box_w = 1.25
    box_h = 1.1
    y = 0.8

    for i, (text, color) in enumerate(stages):
        x = i * x_step
        rect = patches.FancyBboxPatch(
            (x, y), box_w, box_h,
            boxstyle="round,pad=0.08,rounding_size=0.12",
            facecolor=color, edgecolor="#111111", linewidth=1.5, alpha=0.95
        )
        ax.add_patch(rect)
        ax.text(x + box_w/2, y + box_h/2, text, color="white", weight="bold",
                fontsize=8.0, ha="center", va="center", multialignment="center")

        if i < len(stages) - 1:
            ax.annotate("", xy=((i + 1) * x_step - 0.05, y + box_h/2),
                        xytext=(x + box_w + 0.02, y + box_h/2),
                        arrowprops=dict(arrowstyle="-|>", color="#222222", lw=2.0, mutation_scale=12))

    ax.set_xlim(-0.15, len(stages) * x_step - 0.1)
    ax.set_ylim(0.2, 2.4)
    plt.title("Figure 1: GesturePilot Modular End-to-End Execution Pipeline", fontsize=11, weight="bold", pad=12)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "fig1_pipeline.png", bbox_inches="tight")
    plt.close()

# 2. Gesture Vocabulary Matrix / Hand Poses
def generate_gesture_poses_diagram():
    fig, axes = plt.subplots(1, 6, figsize=(12.5, 2.6), dpi=300)
    poses = [
        ("PAUSE", "Open Palm\n(All 5 Extended)", "#17becf"),
        ("POINTER", "Index Only\n(Others Curled)", "#1f77b4"),
        ("LEFT CLICK", "Two Fingers\n(Stationary 0.22s)", "#2ca02c"),
        ("RIGHT CLICK", "Three Fingers\n(Stationary 0.22s)", "#ff7f0e"),
        ("DOUBLE CLICK", "Thumb + Index\n(Pinch Closed)", "#d62728"),
        ("SCROLLING", "2/3 Fingers\n(Vertical Motion)", "#9467bd"),
    ]

    for ax, (title, desc, col) in zip(axes, poses):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        
        rect = patches.FancyBboxPatch((0.05, 0.05), 0.9, 0.9,
                                      boxstyle="round,pad=0.05,rounding_size=0.1",
                                      facecolor="#fcfcfc", edgecolor=col, linewidth=2.2)
        ax.add_patch(rect)
        
        badge = patches.FancyBboxPatch((0.08, 0.70), 0.84, 0.22,
                                       boxstyle="round,pad=0.02,rounding_size=0.05",
                                       facecolor=col, edgecolor="none")
        ax.add_patch(badge)
        ax.text(0.5, 0.81, title, color="white", weight="bold", fontsize=8.5, ha="center", va="center")
        ax.text(0.5, 0.38, desc, color="#222222", fontsize=8.0, ha="center", va="center", multialignment="center")

    plt.suptitle("Figure 2: GesturePilot v005 Mutually Exclusive Interaction Vocabulary", fontsize=11, weight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "fig2_gesture_matrix.png", bbox_inches="tight")
    plt.close()

# 3. One Euro Filter vs Raw Jitter Simulation
def generate_filter_comparison_graph():
    np.random.seed(42)
    t = np.linspace(0, 4, 300)
    true_signal = np.piecewise(t, [t < 1.0, (t >= 1.0) & (t < 2.5), t >= 2.5],
                               [lambda x: 400.0,
                                lambda x: 400.0 + 300.0 * (0.5 - 0.5 * np.cos(np.pi * (x - 1.0) / 1.5)),
                                lambda x: 700.0])
    noise = np.random.normal(0, 8.5, size=len(t))
    raw_signal = true_signal + noise

    filtered_signal = np.zeros_like(raw_signal)
    filtered_signal[0] = raw_signal[0]
    for i in range(1, len(t)):
        dt = t[i] - t[i-1]
        dx = (raw_signal[i] - filtered_signal[i-1]) / dt
        speed = abs(dx)
        cutoff = 0.8 + 0.015 * speed
        alpha = 1.0 / (1.0 + (1.0 / (2 * np.pi * cutoff * dt)))
        filtered_signal[i] = alpha * raw_signal[i] + (1 - alpha) * filtered_signal[i-1]

    plt.figure(figsize=(8.5, 3.4), dpi=300)
    plt.plot(t, raw_signal, label="Raw Coordinates (Tremor & Landmark Jitter)", color="#d62728", alpha=0.5, lw=1.1)
    plt.plot(t, filtered_signal, label="One Euro Filter (Virtual Mouse Cursor)", color="#1f77b4", lw=2.2)
    plt.plot(t, true_signal, label="Intentional Motor Trajectory", color="#2ca02c", linestyle="--", lw=1.5)
    
    plt.xlabel("Time (seconds)", fontsize=9, weight="bold")
    plt.ylabel("Screen Coordinate X (pixels)", fontsize=9, weight="bold")
    plt.title("Figure 3: Adaptive One Euro Filtering (Stationary Stability vs. Fast Saccade Tracking)", fontsize=10.5, weight="bold")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="upper left", fontsize=8.0, framealpha=0.95)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "fig3_one_euro_filter.png", bbox_inches="tight")
    plt.close()

# 4. State Machine Transition Diagram
def generate_state_machine_diagram():
    fig, ax = plt.subplots(figsize=(8.8, 3.8), dpi=300)
    ax.axis("off")

    nodes = {
        "TRACKING_LOST": (1.0, 2.9, "#7f7f7f", "TRACKING_LOST\n(Safety Freeze)"),
        "PAUSED": (1.0, 1.0, "#17becf", "PAUSED\n(Open Palm 5F)"),
        "POINTER": (4.4, 1.9, "#1f77b4", "POINTER MODE\n(Index Only)"),
        "TWO_FINGER": (7.8, 2.9, "#2ca02c", "2-FINGER PENDING\n(Left Click / Scroll)"),
        "THREE_FINGER": (7.8, 0.9, "#ff7f0e", "3-FINGER PENDING\n(Right Click / Scroll)"),
        "SCROLLING": (7.8, 1.9, "#9467bd", "SCROLLING\n(Vertical Delta Ticks)"),
        "PINCH": (4.4, 0.3, "#d62728", "PINCH PENDING\n(Double Click)"),
    }

    for k, (x, y, col, label) in nodes.items():
        box = patches.FancyBboxPatch(
            (x - 0.85, y - 0.35), 1.7, 0.7,
            boxstyle="round,pad=0.08,rounding_size=0.1",
            facecolor=col, edgecolor="#222222", linewidth=1.4, alpha=0.92
        )
        ax.add_patch(box)
        ax.text(x, y, label, color="white", weight="bold", fontsize=7.5, ha="center", va="center", multialignment="center")

    def draw_edge(n1, n2, txt="", rad=0.0):
        x1, y1 = nodes[n1][0], nodes[n1][1]
        x2, y2 = nodes[n2][0], nodes[n2][1]
        ax.annotate(txt, xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color="#333333", lw=1.4,
                                    mutation_scale=10, connectionstyle=f"arc3,rad={rad}"),
                    fontsize=7.0, color="#111111", ha="center", va="center")

    draw_edge("POINTER", "TWO_FINGER", "2 fingers", rad=0.12)
    draw_edge("TWO_FINGER", "POINTER", "click emitted", rad=0.12)
    draw_edge("TWO_FINGER", "SCROLLING", "motion > 0.025", rad=0.0)
    draw_edge("THREE_FINGER", "SCROLLING", "motion > 0.025", rad=0.0)
    draw_edge("POINTER", "THREE_FINGER", "3 fingers", rad=-0.12)
    draw_edge("THREE_FINGER", "POINTER", "right click", rad=-0.12)
    draw_edge("SCROLLING", "POINTER", "return to pointer (0.10s)", rad=0.18)
    draw_edge("POINTER", "PAUSED", "open palm", rad=0.12)
    draw_edge("PAUSED", "POINTER", "index only", rad=0.12)
    draw_edge("POINTER", "PINCH", "pinch", rad=0.12)
    draw_edge("PINCH", "POINTER", "release", rad=0.12)
    draw_edge("TRACKING_LOST", "POINTER", "streak >= 3", rad=0.12)

    ax.set_xlim(-0.4, 9.5)
    ax.set_ylim(-0.2, 3.6)
    plt.title("Figure 4: Mutually Exclusive Centralized Interaction State Machine", fontsize=10.5, weight="bold")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "fig4_state_machine.png", bbox_inches="tight")
    plt.close()

if __name__ == "__main__":
    generate_pipeline_diagram()
    generate_gesture_poses_diagram()
    generate_filter_comparison_graph()
    generate_state_machine_diagram()
    print("All research paper figures generated successfully.")
