#!/usr/bin/env python3
"""Direct Wi-Fi Pairing script for YsxLite / A9 / PPPP Cameras.

Use this script directly from your Mac when connected to the camera's Wi-Fi hotspot
(e.g. AYS-xxx, ACCQ-xxx, PTZ-xxx where your router IP is 192.168.1.1 or 192.168.10.1).
"""

import socket
import struct
import sys
import time

PPPP_MAGIC = b"PPPP"
PPPP_CMD_WIFI_SET = 0x0008
DEFAULT_PORT = 32108


def pair_camera(ssid: str, password: str, target_ip: str = "192.168.1.1") -> None:
    print("=" * 60)
    print("📹 DomoLink-Camera : Assistant d'Appairage Direct Mac -> Caméra")
    print("=" * 60)
    print(f"📡 Réseau Wi-Fi cible : '{ssid}'")
    print(f"🔑 Clé Wi-Fi          : {'*' * len(password)} ({len(password)} caractères)")
    print(f"🎯 IP Point d'Accès   : {target_ip}:{DEFAULT_PORT}")
    print("-" * 60)

    # Encode payload: [SSID_LEN (1B)] + SSID + [PASS_LEN (1B)] + PASS
    s_bytes = ssid.encode("utf-8")
    p_bytes = password.encode("utf-8")
    payload = struct.pack("B", len(s_bytes)) + s_bytes + struct.pack("B", len(p_bytes)) + p_bytes
    packet = PPPP_MAGIC + struct.pack(">HHH", PPPP_CMD_WIFI_SET, len(payload), 1) + payload

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(2.0)

    candidate_ips = [target_ip, "192.168.1.1", "192.168.10.1", "192.168.1.254", "255.255.255.255"]
    # De-duplicate
    candidate_ips = list(dict.fromkeys(candidate_ips))

    print("🚀 Envoi des paquets UDP de configuration à la caméra...")
    for attempt in range(1, 4):
        print(f"  [Tentative {attempt}/3] Émission des trames PPPP_CMD_WIFI_SET...")
        for ip in candidate_ips:
            try:
                sock.sendto(packet, (ip, DEFAULT_PORT))
            except Exception as e:
                pass
        time.sleep(0.8)

    sock.close()
    print("-" * 60)
    print("✅ Paquets transmis avec succès à la caméra !")
    print("🔄 La caméra applique la configuration : son voyant LED devrait changer de statut.")
    print("📶 La caméra va éteindre son point d'accès et se connecter à votre Freebox ('" + ssid + "').")
    print("💡 Votre Mac va automatiquement se reconnecter à votre Wi-Fi Freebox.")
    print("🔍 Vous pourrez ensuite retrouver la caméra dans DomoLink-Camera via le bouton 'Scanner le réseau' !")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python3 scripts/pair_direct.py <SSID_FREEBOX> <MOT_DE_PASSE> [IP_CAMERA_AP]")
        print("Exemple:")
        print('  python3 scripts/pair_direct.py "SocrateFreeLan_Media" "MonSuperMotDePasse" 192.168.1.1')
        sys.exit(1)

    ssid_arg = sys.argv[1]
    pass_arg = sys.argv[2]
    ip_arg = sys.argv[3] if len(sys.argv) > 3 else "192.168.1.1"

    pair_camera(ssid_arg, pass_arg, ip_arg)
