"""Generate PNG figures for the UNO Q manuscript from executable code."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
SOFTWARE_ROOT = SCRIPT_DIR.parent
MANUSCRIPT_ROOT = SOFTWARE_ROOT.parent
FIGURE_DIR = MANUSCRIPT_ROOT / "figures"
FIGURE_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(SOFTWARE_ROOT / "python"))

from unoq_lorenz.lorenz import lorenz_trajectory
from unoq_lorenz.nonce import NonceSequence
from unoq_lorenz.packet import RoiProtector
from unoq_lorenz.pipeline import protect_frame, recover_frame


def save_architecture(language: str) -> None:
    text = {
        "en": {
            "smartphone_title": "Smartphone",
            "smartphone_body": "IoT Remote\nconsented video",
            "linux_title": "QRB2210 / Debian",
            "linux_body": "App Lab face model\nROI extraction\nLorenz transform\nChaCha20-Poly1305\nCSV metrics",
            "packet_title": "Protected packet",
            "packet_body": "nonce + AAD +\nciphertext + tag",
            "store_title": "Packet store",
            "store_body": "Atomic JSON bundle\nbefore preview",
            "mcu_title": "STM32U585",
            "mcu_body": "Forwarded Linux\ntiming/mode status",
            "checks_title": "Reviewer checks",
            "checks_body": "exact recovery\ntag rejection\nnonce/replay\nlatency/FPS",
            "boundary": "Security boundary: standard AEAD",
            "note": "Lorenz is a measured preprocessing variable, not the source of the security claim.",
        },
        "es": {
            "smartphone_title": "Teléfono",
            "smartphone_body": "IoT Remote\nvideo consentido",
            "linux_title": "QRB2210 / Debian",
            "linux_body": "modelo facial App Lab\nextracción de ROI\ntransformación Lorenz\nChaCha20-Poly1305\nmétricas CSV",
            "packet_title": "Paquete protegido",
            "packet_body": "nonce + AAD +\ntexto cifrado + tag",
            "store_title": "Almacén de paquetes",
            "store_body": "JSON atómico\nantes del preview",
            "mcu_title": "STM32U585",
            "mcu_body": "Estado de tiempo/modo\nreenviado por Linux",
            "checks_title": "Verificación",
            "checks_body": "recuperación exacta\nrechazo de tag\nnonce/replay\nlatencia/FPS",
            "boundary": "Frontera de seguridad: AEAD estándar",
            "note": "Lorenz es una variable de preprocesamiento medible, no la fuente de la seguridad.",
        },
    }[language]

    fig, ax = plt.subplots(figsize=(11.6, 4.8))
    ax.set_xlim(0, 11.6)
    ax.set_ylim(0, 5)
    ax.axis("off")

    def box(x, y, w, h, title, body, color):
        patch = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.04,rounding_size=0.08",
            facecolor=color,
            edgecolor="#243746",
            linewidth=1.4,
        )
        ax.add_patch(patch)
        ax.text(x + 0.15, y + h - 0.25, title, fontsize=10.5, weight="bold", va="top")
        ax.text(x + 0.15, y + h - 0.75, body, fontsize=8.6, va="top", linespacing=1.25)

    primary_y = 1.55
    primary_h = 2.20
    box(0.20, primary_y, 1.70, primary_h, text["smartphone_title"], text["smartphone_body"], "#e8f1f8")
    box(2.25, primary_y, 2.35, primary_h, text["linux_title"], text["linux_body"], "#d9eef2")
    box(4.95, primary_y, 1.85, primary_h, text["packet_title"], text["packet_body"], "#f8e8bf")
    box(7.15, primary_y, 1.85, primary_h, text["store_title"], text["store_body"], "#ece7f6")
    box(9.35, primary_y, 2.05, primary_h, text["checks_title"], text["checks_body"], "#f4e2e2")
    box(2.375, 0.05, 2.10, 1.05, text["mcu_title"], text["mcu_body"], "#e9f3dd")

    arrows = [
        ((1.90, 2.65), (2.25, 2.65)),
        ((4.60, 2.65), (4.95, 2.65)),
        ((6.80, 2.65), (7.15, 2.65)),
        ((9.00, 2.65), (9.35, 2.65)),
        ((3.425, 1.55), (3.425, 1.10)),
    ]
    for start, end in arrows:
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=13, linewidth=1.4, color="#243746"))

    ax.text(5.80, 4.55, text["boundary"], fontsize=11, weight="bold", color="#8c2f1b", ha="center")
    ax.text(5.80, 4.22, text["note"], fontsize=9.2, ha="center")
    fig.tight_layout()
    output = FIGURE_DIR / f"unoq_lorenz_architecture_{language}.png"
    fig.savefig(output, dpi=300, bbox_inches="tight")
    if language == "en":
        fig.savefig(FIGURE_DIR / "unoq_lorenz_architecture.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_lorenz_dynamics(language: str) -> None:
    labels = {
        "en": {
            "trajectory": "Lorenz trajectory: sigma=10, rho=28, beta=8/3",
            "time": "Integration time",
            "separation": "State separation",
            "sensitivity": "Sensitivity to a 1e-9 perturbation",
        },
        "es": {
            "trajectory": "Trayectoria de Lorenz: sigma=10, rho=28, beta=8/3",
            "time": "Tiempo de integración",
            "separation": "Separación entre estados",
            "sensitivity": "Sensibilidad a una perturbación de 1e-9",
        },
    }[language]
    samples = 6_000
    first = lorenz_trajectory((1.0, 1.0, 1.0), samples, burn_in=2_048)
    second = lorenz_trajectory((1.0 + 1e-9, 1.0, 1.0), samples, burn_in=2_048)
    separation = np.linalg.norm(first - second, axis=1)

    fig = plt.figure(figsize=(10.5, 4.2))
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax1.plot(first[:, 0], first[:, 1], first[:, 2], linewidth=0.45, color="#1261a0")
    ax1.set_xlabel("x")
    ax1.set_ylabel("y")
    ax1.set_zlabel("z")
    ax1.set_title(labels["trajectory"])

    ax2 = fig.add_subplot(1, 2, 2)
    ax2.semilogy(np.arange(samples) * 0.005, np.maximum(separation, 1e-16), color="#b33a3a")
    ax2.set_xlabel(labels["time"])
    ax2.set_ylabel(labels["separation"])
    ax2.set_title(labels["sensitivity"])
    ax2.grid(alpha=0.25)
    fig.tight_layout()
    output = FIGURE_DIR / f"lorenz_attractor_sensitivity_{language}.png"
    fig.savefig(output, dpi=300, bbox_inches="tight")
    if language == "en":
        fig.savefig(FIGURE_DIR / "lorenz_attractor_sensitivity.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _synthetic_frame() -> tuple[np.ndarray, tuple[int, int, int, int]]:
    image = np.full((240, 360, 3), 238, dtype=np.uint8)
    cv2.rectangle(image, (0, 0), (359, 239), (225, 235, 242), -1)
    center = (180, 118)
    cv2.ellipse(image, center, (72, 88), 0, 0, 360, (170, 205, 235), -1)
    cv2.circle(image, (155, 100), 8, (45, 55, 70), -1)
    cv2.circle(image, (205, 100), 8, (45, 55, 70), -1)
    cv2.ellipse(image, (180, 145), (28, 14), 0, 0, 180, (55, 75, 95), 4)
    cv2.putText(image, "SYNTHETIC", (112, 225), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (60, 70, 80), 2, cv2.LINE_AA)
    return image, (104, 30, 256, 206)


def save_round_trip(language: str) -> None:
    image, box = _synthetic_frame()
    protector = RoiProtector(bytes(range(32)))
    protected = protect_frame(
        image,
        [box],
        run_id="figure-v2",
        frame_id=0,
        protector=protector,
        nonces=NonceSequence(b"FIG12026"),
        use_lorenz=True,
    )
    recovered = recover_frame(protected.preview, protected.packets, protector=protector)
    exact = np.array_equal(image, recovered)

    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2))
    titles = {
        "en": ("Synthetic input", "Authenticated protected ROI", f"Recovered: exact={exact}"),
        "es": ("Entrada sintética", "ROI protegida y autenticada", f"Recuperada: exacta={exact}"),
    }[language]
    for ax, frame, title in zip(
        axes,
        (image, protected.preview, recovered),
        titles,
    ):
        ax.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        ax.set_title(title, fontsize=10)
        ax.axis("off")
    fig.tight_layout()
    output = FIGURE_DIR / f"synthetic_roi_roundtrip_{language}.png"
    fig.savefig(output, dpi=300, bbox_inches="tight")
    if language == "en":
        fig.savefig(FIGURE_DIR / "synthetic_roi_roundtrip.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    for language in ("en", "es"):
        save_architecture(language)
        save_lorenz_dynamics(language)
        save_round_trip(language)
    for path in sorted(FIGURE_DIR.glob("*.png")):
        print(path)


if __name__ == "__main__":
    main()
