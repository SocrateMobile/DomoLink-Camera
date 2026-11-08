#!/usr/bin/env python3
"""Generate high-resolution branding assets (icon, icon@2x, logo, logo@2x, SVG) for DomoLink Camera."""

import os
import shutil
import subprocess

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070c18" />
      <stop offset="50%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#16223f" />
    </linearGradient>

    <!-- Neon Cyan Filter -->
    <filter id="neonGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="6" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    <!-- Red Rec Glow Filter -->
    <filter id="redGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="5" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    <!-- Lens Bezel Gradient -->
    <linearGradient id="lensBezelGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8" />
      <stop offset="50%" stop-color="#0284c7" />
      <stop offset="100%" stop-color="#2563eb" />
    </linearGradient>

    <!-- Lens Glass Gradient -->
    <radialGradient id="lensGlassGrad" cx="38%" cy="32%" r="68%">
      <stop offset="0%" stop-color="#38bdf8" />
      <stop offset="22%" stop-color="#0284c7" />
      <stop offset="60%" stop-color="#0c4a6e" />
      <stop offset="100%" stop-color="#020617" />
    </radialGradient>

    <!-- Metallic Rim Gradient -->
    <linearGradient id="metalRim" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#334155" />
      <stop offset="50%" stop-color="#1e293b" />
      <stop offset="100%" stop-color="#0f172a" />
    </linearGradient>
  </defs>

  <!-- Squircle Container -->
  <rect x="16" y="16" width="480" height="480" rx="108" fill="url(#bgGrad)" stroke="rgba(56, 189, 248, 0.4)" stroke-width="4" />

  <!-- Cyber Surveillance Grid & Concentric Targeting Rings -->
  <g stroke="rgba(56, 189, 248, 0.08)" stroke-width="1.5">
    <circle cx="256" cy="270" r="190" fill="none" stroke-dasharray="6,6" />
    <circle cx="256" cy="270" r="145" fill="none" stroke-dasharray="4,4" />
    <circle cx="256" cy="270" r="105" fill="none" />
    
    <!-- Crosshair Axis Lines -->
    <line x1="256" y1="40" x2="256" y2="70" stroke="rgba(56, 189, 248, 0.35)" stroke-width="2.5" />
    <line x1="256" y1="470" x2="256" y2="500" stroke="rgba(56, 189, 248, 0.35)" stroke-width="2.5" />
    <line x1="40" y1="270" x2="70" y2="270" stroke="rgba(56, 189, 248, 0.35)" stroke-width="2.5" />
    <line x1="442" y1="270" x2="472" y2="270" stroke="rgba(56, 189, 248, 0.35)" stroke-width="2.5" />
  </g>

  <!-- HUD Viewfinder Corner Brackets -->
  <g stroke="#38bdf8" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.85">
    <path d="M 68 115 L 68 76 A 8 8 0 0 1 76 68 L 115 68" />
    <path d="M 397 68 L 436 68 A 8 8 0 0 1 444 76 L 444 115" />
    <path d="M 68 397 L 68 436 A 8 8 0 0 0 76 444 L 115 444" />
    <path d="M 397 444 L 436 444 A 8 8 0 0 0 444 436 L 444 397" />
  </g>

  <!-- Wi-Fi / PPPP Transmission Waves (Top) -->
  <g fill="none" stroke-linecap="round">
    <circle cx="256" cy="115" r="5" fill="#38bdf8" filter="url(#neonGlow)" />
    <path d="M 230 96 A 35 35 0 0 1 282 96" stroke="#38bdf8" stroke-width="3.5" filter="url(#neonGlow)" />
    <path d="M 212 78 A 60 60 0 0 1 300 78" stroke="#0284c7" stroke-width="3.5" />
    <path d="M 194 60 A 85 85 0 0 1 318 60" stroke="#0284c7" stroke-width="3" opacity="0.6" />
  </g>

  <!-- Camera Body & Mounting Base -->
  <g id="cameraBody">
    <!-- Camera Mount Arm -->
    <path d="M 236 128 L 276 128 L 270 165 L 242 165 Z" fill="#1e293b" stroke="#38bdf8" stroke-width="2" />
    <circle cx="256" cy="138" r="3" fill="#64748b" />

    <!-- Outer Spherical Dome Housing (Drop Shadow & Shell) -->
    <circle cx="256" cy="270" r="128" fill="url(#metalRim)" stroke="rgba(56, 189, 248, 0.3)" stroke-width="3" />
    
    <!-- Outer Shield Bezel Ring -->
    <circle cx="256" cy="270" r="116" fill="#0b1329" stroke="url(#lensBezelGrad)" stroke-width="5" filter="url(#neonGlow)" />
    
    <!-- Stepped Optical Barrel -->
    <circle cx="256" cy="270" r="92" fill="#0f172a" stroke="#1e293b" stroke-width="4" />
    <circle cx="256" cy="270" r="76" fill="#020617" stroke="rgba(56, 189, 248, 0.4)" stroke-width="2.5" />

    <!-- Sapphire Lens Glass Element -->
    <circle cx="256" cy="270" r="64" fill="url(#lensGlassGrad)" />

    <!-- Aperture Core / Sensor Pupil -->
    <circle cx="256" cy="270" r="26" fill="#020617" stroke="#0284c7" stroke-width="1.5" />
    <circle cx="256" cy="270" r="12" fill="#0f172a" />

    <!-- Lens Specular Glare (Glass Reflections) -->
    <path d="M 218 240 A 50 50 0 0 1 278 224" fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round" opacity="0.55" />
    <circle cx="244" cy="254" r="5" fill="#38bdf8" opacity="0.9" filter="url(#neonGlow)" />
    <circle cx="238" cy="248" r="2" fill="#ffffff" opacity="0.95" />

    <!-- Infrared Night-Vision Diodes (4 Points) -->
    <circle cx="256" cy="192" r="4" fill="#06b6d4" opacity="0.8" />
    <circle cx="256" cy="348" r="4" fill="#06b6d4" opacity="0.8" />
    <circle cx="178" cy="270" r="4" fill="#06b6d4" opacity="0.8" />
    <circle cx="334" cy="270" r="4" fill="#06b6d4" opacity="0.8" />

    <!-- Active Recording Indicator LED (Top Right with Red Glow) -->
    <circle cx="328" cy="198" r="6.5" fill="#ef4444" filter="url(#redGlow)" />
    <circle cx="328" cy="198" r="3" fill="#ffffff" />
    <text x="340" y="202" font-family="-apple-system, BlinkMacSystemFont, 'SF Mono', monospace" font-size="10" font-weight="800" fill="#f87171" letter-spacing="1">REC</text>
  </g>
</svg>
"""

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 320" width="1000" height="320">
  <defs>
    <!-- Background Gradient -->
    <linearGradient id="logoBgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#070c18" />
      <stop offset="50%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#16223f" />
    </linearGradient>

    <!-- Neon Glow Filter -->
    <filter id="neonGlowLogo" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="5" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    <filter id="redGlowLogo" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="4" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    <!-- Lens Bezel Gradient -->
    <linearGradient id="lensBezelLogo" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8" />
      <stop offset="50%" stop-color="#0284c7" />
      <stop offset="100%" stop-color="#2563eb" />
    </linearGradient>

    <!-- Lens Glass Gradient -->
    <radialGradient id="lensGlassLogo" cx="38%" cy="32%" r="68%">
      <stop offset="0%" stop-color="#38bdf8" />
      <stop offset="22%" stop-color="#0284c7" />
      <stop offset="60%" stop-color="#0c4a6e" />
      <stop offset="100%" stop-color="#020617" />
    </radialGradient>
  </defs>

  <!-- Banner Background Container -->
  <rect width="1000" height="320" rx="28" fill="url(#logoBgGrad)" stroke="rgba(56, 189, 248, 0.35)" stroke-width="3" />

  <!-- Subtle Blueprint & Targeting Grid -->
  <g stroke="rgba(56, 189, 248, 0.05)" stroke-width="1.2">
    <line x1="0" y1="80" x2="1000" y2="80" />
    <line x1="0" y1="160" x2="1000" y2="160" />
    <line x1="0" y1="240" x2="1000" y2="240" />
    <line x1="160" y1="0" x2="160" y2="320" />
    <line x1="320" y1="0" x2="320" y2="320" />
    <line x1="480" y1="0" x2="480" y2="320" />
    <line x1="640" y1="0" x2="640" y2="320" />
    <line x1="800" y1="0" x2="800" y2="320" />
  </g>

  <!-- Left Side: Camera Emblem -->
  <g transform="translate(45, 10) scale(0.58)">
    <!-- Wi-Fi Broadcast Waves -->
    <g fill="none" stroke-linecap="round">
      <circle cx="256" cy="115" r="6" fill="#38bdf8" filter="url(#neonGlowLogo)" />
      <path d="M 230 96 A 35 35 0 0 1 282 96" stroke="#38bdf8" stroke-width="4" filter="url(#neonGlowLogo)" />
      <path d="M 212 78 A 60 60 0 0 1 300 78" stroke="#0284c7" stroke-width="4" />
      <path d="M 194 60 A 85 85 0 0 1 318 60" stroke="#0284c7" stroke-width="3.5" opacity="0.6" />
    </g>

    <!-- Mount Arm -->
    <path d="M 236 128 L 276 128 L 270 165 L 242 165 Z" fill="#1e293b" stroke="#38bdf8" stroke-width="2" />

    <!-- Housing & Bezel -->
    <circle cx="256" cy="270" r="128" fill="#1e293b" stroke="rgba(56, 189, 248, 0.3)" stroke-width="3" />
    <circle cx="256" cy="270" r="116" fill="#0b1329" stroke="url(#lensBezelLogo)" stroke-width="6" filter="url(#neonGlowLogo)" />
    <circle cx="256" cy="270" r="92" fill="#0f172a" stroke="#1e293b" stroke-width="4" />
    <circle cx="256" cy="270" r="76" fill="#020617" stroke="rgba(56, 189, 248, 0.4)" stroke-width="2.5" />
    <circle cx="256" cy="270" r="64" fill="url(#lensGlassLogo)" />
    <circle cx="256" cy="270" r="26" fill="#020617" stroke="#0284c7" stroke-width="1.5" />

    <!-- Lens Specular Glare -->
    <path d="M 218 240 A 50 50 0 0 1 278 224" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round" opacity="0.6" />
    <circle cx="244" cy="254" r="5" fill="#38bdf8" opacity="0.9" filter="url(#neonGlowLogo)" />

    <!-- Recording Indicator -->
    <circle cx="328" cy="198" r="7" fill="#ef4444" filter="url(#redGlowLogo)" />
    <circle cx="328" cy="198" r="3" fill="#ffffff" />
    <text x="340" y="202" font-family="-apple-system, BlinkMacSystemFont, 'SF Mono', monospace" font-size="11" font-weight="800" fill="#f87171" letter-spacing="1">REC</text>

    <!-- Corner Brackets -->
    <g stroke="#38bdf8" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.75">
      <path d="M 68 115 L 68 76 A 8 8 0 0 1 76 68 L 115 68" />
      <path d="M 397 68 L 436 68 A 8 8 0 0 1 444 76 L 444 115" />
      <path d="M 68 397 L 68 436 A 8 8 0 0 0 76 444 L 115 444" />
      <path d="M 397 444 L 436 444 A 8 8 0 0 0 444 436 L 444 397" />
    </g>
  </g>

  <!-- Right Side: Brand Typography & Tech Pills -->
  <g transform="translate(365, 125)">
    <!-- Main Title -->
    <text x="0" y="0" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="64" font-weight="800" fill="#f8fafc" letter-spacing="-1">
      Domo<tspan fill="#38bdf8">Link</tspan> <tspan fill="#60a5fa" font-weight="600">Camera</tspan>
    </text>

    <!-- Subtitle -->
    <text x="5" y="44" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="20" font-weight="500" fill="#94a3b8" letter-spacing="0.3">
      Smart Video &amp; Wi-Fi Surveillance for Home Assistant
    </text>

    <!-- Feature Pills Row -->
    <g transform="translate(5, 78)">
      <!-- Pill 1: RTSP / PPPP -->
      <rect x="0" y="0" width="135" height="32" rx="16" fill="rgba(56, 189, 248, 0.15)" stroke="rgba(56, 189, 248, 0.4)" stroke-width="1.5" />
      <text x="67" y="20" font-family="-apple-system, BlinkMacSystemFont, 'SF Mono', monospace" font-size="12" font-weight="700" fill="#38bdf8" text-anchor="middle">RTSP • PPPP</text>

      <!-- Pill 2: Direct Live -->
      <rect x="150" y="0" width="130" height="32" rx="16" fill="rgba(16, 185, 129, 0.15)" stroke="rgba(16, 185, 129, 0.4)" stroke-width="1.5" />
      <text x="215" y="20" font-family="-apple-system, BlinkMacSystemFont, 'SF Mono', monospace" font-size="12" font-weight="700" fill="#34d399" text-anchor="middle">DIRECT LIVE</text>

      <!-- Pill 3: Freebox TV -->
      <rect x="295" y="0" width="130" height="32" rx="16" fill="rgba(168, 85, 247, 0.15)" stroke="rgba(168, 85, 247, 0.4)" stroke-width="1.5" />
      <text x="360" y="20" font-family="-apple-system, BlinkMacSystemFont, 'SF Mono', monospace" font-size="12" font-weight="700" fill="#c084fc" text-anchor="middle">FREEBOX TV</text>

      <!-- Pill 4: HACS -->
      <rect x="440" y="0" width="95" height="32" rx="16" fill="rgba(245, 158, 11, 0.15)" stroke="rgba(245, 158, 11, 0.4)" stroke-width="1.5" />
      <text x="487" y="20" font-family="-apple-system, BlinkMacSystemFont, 'SF Mono', monospace" font-size="12" font-weight="700" fill="#fbbf24" text-anchor="middle">HACS</text>
    </g>
  </g>
</svg>
"""

def generate_assets():
    images_dir = os.path.join(ROOT_DIR, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    icon_svg_path = os.path.join(images_dir, "icon.svg")
    logo_svg_path = os.path.join(images_dir, "logo.svg")

    with open(icon_svg_path, "w", encoding="utf-8") as f:
        f.write(ICON_SVG.strip())
    print(f"Generated: {icon_svg_path}")

    with open(logo_svg_path, "w", encoding="utf-8") as f:
        f.write(LOGO_SVG.strip())
    print(f"Generated: {logo_svg_path}")

    tmp_dir = "/tmp/domolink_cam_render"
    os.makedirs(tmp_dir, exist_ok=True)

    # Render Icon SVG to 512x512 PNG
    icon_tmp = os.path.join(tmp_dir, "icon_render.svg")
    shutil.copyfile(icon_svg_path, icon_tmp)
    subprocess.run(["qlmanage", "-t", "-s", "512", "-o", tmp_dir, icon_tmp], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rendered_icon_512 = os.path.join(tmp_dir, "icon_render.svg.png")

    # Render Logo SVG to 1000x320 PNG (rendered at 1000)
    logo_tmp = os.path.join(tmp_dir, "logo_render.svg")
    shutil.copyfile(logo_svg_path, logo_tmp)
    subprocess.run(["qlmanage", "-t", "-s", "1000", "-o", tmp_dir, logo_tmp], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rendered_logo = os.path.join(tmp_dir, "logo_render.svg.png")

    # Target destinations in repository
    icon_256_path = os.path.join(images_dir, "icon.png")
    icon_512_path = os.path.join(images_dir, "icon@2x.png")
    logo_256_path = os.path.join(images_dir, "logo.png")
    logo_512_path = os.path.join(images_dir, "logo@2x.png")

    # 1. icon@2x.png (512x512)
    subprocess.run(["sips", "-z", "512", "512", rendered_icon_512, "--out", icon_512_path], check=True, stdout=subprocess.DEVNULL)
    # 2. icon.png (256x256)
    subprocess.run(["sips", "-z", "256", "256", rendered_icon_512, "--out", icon_256_path], check=True, stdout=subprocess.DEVNULL)

    # 3. Square Logo variant for integration brand listings
    subprocess.run(["sips", "-z", "512", "512", rendered_icon_512, "--out", logo_512_path], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["sips", "-z", "256", "256", rendered_icon_512, "--out", logo_256_path], check=True, stdout=subprocess.DEVNULL)

    # 4. Wide Banner Logo for README / GitHub / HACS Repo Page
    banner_png = os.path.join(images_dir, "banner_logo.png")
    subprocess.run(["sips", "-z", "320", "1000", rendered_logo, "--out", banner_png], check=True, stdout=subprocess.DEVNULL)

    print("Created base images in images/:")
    for f in [icon_256_path, icon_512_path, logo_256_path, logo_512_path, banner_png]:
        print("  -", f)

    # Replicate across all standard HA and HACS discovery directories:
    dest_dirs = [
        ROOT_DIR,                                                         # Root repo
        os.path.join(ROOT_DIR, ".github"),                               # GitHub previews
        os.path.join(ROOT_DIR, "custom_components", "domolink_camera"),   # Component root
        os.path.join(ROOT_DIR, "custom_components", "domolink_camera", "brand"), # Home Assistant Brand
    ]

    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        shutil.copyfile(icon_256_path, os.path.join(d, "icon.png"))
        shutil.copyfile(icon_512_path, os.path.join(d, "icon@2x.png"))
        shutil.copyfile(logo_256_path, os.path.join(d, "logo.png"))
        shutil.copyfile(logo_512_path, os.path.join(d, "logo@2x.png"))
        print(f"Copied brand assets -> {d}/")

    print("\n🎉 All branding formats successfully generated and deployed!")

if __name__ == "__main__":
    generate_assets()
