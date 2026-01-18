#!/usr/bin/env bash
set -euo pipefail

REALM="HOME.LAN"
DOMAIN="home.lan"
WORKGROUP="HOME"

DC_IP_DEFAULT="192.168.1.240"
DNS_DEFAULT="192.168.1.86"
KIDSCONTROL_DEFAULT="http://kids-control.home.lan"

KIDS_GROUP_DN_DEFAULT="CN=kinder,OU=Groups,DC=home,DC=lan"

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Bitte als root ausführen: sudo $0"
    exit 1
  fi
}

pause() { read -r -p "${1:-Weiter mit Enter...}"; }

detect_iface() {
  IFACE="$(ip route | awk '/default/{print $5; exit}')"
  IFACE="${IFACE:-enp34s0}"
}

detect_nm_conn() {
  if command -v nmcli >/dev/null 2>&1; then
    nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null | awk -F: '$2!=""{print $1; exit}'
  fi
}

current_dns_servers() {
  if command -v resolvectl >/dev/null 2>&1; then
    resolvectl status "${IFACE}" 2>/dev/null | awk '/DNS Servers:/{flag=1;next}/DNS Domain:/{flag=0}flag{print}' | xargs
  else
    awk '/^nameserver /{print $2}' /etc/resolv.conf | xargs
  fi
}

set_dns_adguard() {
  local dns="${DNS_DEFAULT}"
  local domain="${DOMAIN}"
  echo "[DNS] Prüfe DNS für Interface ${IFACE}..."
  local cur
  cur="$(current_dns_servers || true)"
  echo "[DNS] Aktuell: ${cur:-"(unbekannt)"}"

  if echo " ${cur} " | grep -q " ${dns} "; then
    echo "[DNS] OK: ${dns} ist bereits gesetzt."
    return 0
  fi

  echo "[DNS] Setze DNS auf ${dns} + Search-Domain ${domain}..."

  local nm_conn
  nm_conn="$(detect_nm_conn || true)"
  if [[ -n "${nm_conn}" ]]; then
    echo "[DNS] NetworkManager aktiv, Connection: ${nm_conn}"
    nmcli connection modify "${nm_conn}" ipv4.ignore-auto-dns yes
    nmcli connection modify "${nm_conn}" ipv4.dns "${dns}"
    nmcli connection modify "${nm_conn}" ipv4.dns-search "${domain}"
    nmcli connection up "${nm_conn}" >/dev/null
    echo "[DNS] NM: gesetzt."
    return 0
  fi

  if command -v resolvectl >/dev/null 2>&1; then
    echo "[DNS] Fallback: resolvectl (ggf. nur bis reboot)"
    resolvectl dns "${IFACE}" "${dns}" || true
    resolvectl domain "${IFACE}" "${domain}" || true
    echo "[DNS] resolvectl: gesetzt."
    return 0
  fi

  echo "[DNS] WARN: Konnte DNS nicht automatisiert setzen (kein nmcli/resolvectl)."
  echo "[DNS] Bitte manuell DNS auf ${dns} setzen."
}

install_pkgs() {
  echo "[1/9] Pakete installieren (CachyOS/Arch)..."
  pacman -Syu --noconfirm --needed \
    samba sssd krb5 openldap cifs-utils \
    netcat jq \
    sed grep coreutils
}

write_krb5() {
  echo "[2/9] /etc/krb5.conf schreiben..."
  cat > /etc/krb5.conf <<EOF
[libdefaults]
  default_realm = ${REALM}
  dns_lookup_realm = false
  dns_lookup_kdc = true
  rdns = false
  ticket_lifetime = 24h
  forwardable = true

[realms]
  ${REALM} = {
    default_domain = ${DOMAIN}
  }

[domain_realm]
  .${DOMAIN} = ${REALM}
  ${DOMAIN} = ${REALM}
EOF
}

write_samba_member_conf() {
  echo "[3/9] /etc/samba/smb.conf (Member) schreiben..."
  mkdir -p /etc/samba
  cat > /etc/samba/smb.conf <<EOF
[global]
  workgroup = ${WORKGROUP}
  security = ADS
  realm = ${REALM}
  kerberos method = secrets and keytab

  idmap config * : backend = tdb
  idmap config * : range = 3000-7999

  dns proxy = no
  log file = /var/log/samba/%m.log
  log level = 1
EOF
}

time_sync() {
  echo "[4/9] Zeit-Sync aktivieren..."
  systemctl enable --now systemd-timesyncd >/dev/null 2>&1 || true
  timedatectl set-ntp true >/dev/null 2>&1 || true
}

domain_join() {
  echo "[5/9] Domain-Join..."
  read -r -p "DC IPv4 [${DC_IP_DEFAULT}]: " DC_IP
  DC_IP="${DC_IP:-$DC_IP_DEFAULT}"

  echo "Test: TCP 389 zu ${DC_IP}..."
  nc -vz -w 2 "${DC_IP}" 389 || {
    echo "FEHLER: Port 389/LDAP auf ${DC_IP} nicht erreichbar."
    exit 1
  }

  echo
  read -r -p "Domain-Admin Benutzer [administrator]: " ADMIN_USER
  ADMIN_USER="${ADMIN_USER:-administrator}"

  echo "Passwort folgt jetzt für ${WORKGROUP}\\${ADMIN_USER}:"
  net ads join -S "${DC_IP}" -U "${ADMIN_USER}"
  echo "✅ Join erfolgreich."
}

write_sssd() {
  echo "[6/9] SSSD konfigurieren..."
  mkdir -p /etc/sssd
  chmod 700 /etc/sssd

  read -r -p "Kinder-Gruppen-DN [${KIDS_GROUP_DN_DEFAULT}]: " KIDS_GROUP_DN
  KIDS_GROUP_DN="${KIDS_GROUP_DN:-$KIDS_GROUP_DN_DEFAULT}"

  cat > /etc/sssd/sssd.conf <<EOF
[sssd]
services = nss, pam
config_file_version = 2
domains = ${DOMAIN}

[nss]
filter_users = root
filter_groups = root

[pam]

[domain/${DOMAIN}]
id_provider = ad
auth_provider = ad
access_provider = ad

ad_domain = ${DOMAIN}
krb5_realm = ${REALM}

use_fully_qualified_names = False
fallback_homedir = /home/%u
default_shell = /bin/bash

ldap_id_mapping = True
cache_credentials = True
enumerate = False

# Zugriff nur für Gruppe "kinder"
ad_access_filter = (memberOf=${KIDS_GROUP_DN})
EOF

  chmod 600 /etc/sssd/sssd.conf
}

patch_nsswitch() {
  echo "[7/9] /etc/nsswitch.conf anpassen (sss hinzufügen)..."
  cp -a /etc/nsswitch.conf "/etc/nsswitch.conf.bak.$(date +%s)"
  for k in passwd group shadow; do
    if grep -qE "^${k}:" /etc/nsswitch.conf; then
      if ! grep -qE "^${k}:.*\bsss\b" /etc/nsswitch.conf; then
        sed -i -E "s/^(${k}:\s*.*)$/\1 sss/" /etc/nsswitch.conf
      fi
    fi
  done
}

patch_pam() {
  echo "[8/9] PAM anpassen (/etc/pam.d/system-auth)..."
  local f="/etc/pam.d/system-auth"
  [[ -f "$f" ]] || { echo "FEHLER: $f nicht gefunden."; exit 1; }
  cp -a "$f" "${f}.bak.$(date +%s)"

  if ! grep -q "pam_sss.so" "$f"; then
    sed -i -E \
      -e '/^auth\s+.*pam_unix\.so/ a auth       sufficient   pam_sss.so forward_pass' \
      -e '/^account\s+.*pam_unix\.so/ a account    \[default=bad success=ok user_unknown=ignore\] pam_sss.so' \
      -e '/^password\s+.*pam_unix\.so/ a password   sufficient   pam_sss.so use_authtok' \
      -e '/^session\s+.*pam_unix\.so/ a session    optional     pam_sss.so' \
      "$f"
  fi
}

enable_services() {
  echo "[9/9] Services aktivieren..."
  systemctl enable --now sssd
  systemctl enable --now smb >/dev/null 2>&1 || true
  systemctl enable --now nmb >/dev/null 2>&1 || true
  sleep 2
}

list_local_users() {
  awk -F: '($3>=1000)&&($1!="nobody")&&($6 ~ /^\/home\//){print $1 " " $6}' /etc/passwd
}

choose_local_user() {
  local prompt="$1"
  mapfile -t USERS < <(list_local_users)
  [[ "${#USERS[@]}" -gt 0 ]] || { echo "FEHLER: keine lokalen /home User gefunden."; exit 1; }

  echo
  echo "${prompt}"
  local i=1
  for u in "${USERS[@]}"; do
    echo "[$i] $u"
    i=$((i+1))
  done
  echo "[0] Abbrechen"

  local choice
  while true; do
    read -r -p "Auswahl (Zahl): " choice
    [[ "$choice" =~ ^[0-9]+$ ]] || { echo "Bitte Zahl eingeben."; continue; }
    [[ "$choice" -ne 0 ]] || { echo "Abbruch."; exit 1; }
    if [[ "$choice" -ge 1 && "$choice" -le "${#USERS[@]}" ]]; then
      echo "${USERS[$((choice-1))]}"
      return 0
    fi
    echo "Ungültige Auswahl."
  done
}

fetch_kids() {
  read -r -p "KidsControl Base-URL [${KIDSCONTROL_DEFAULT}] (du kannst auch http://192.168.1.81 eingeben): " KC
  KC="${KC:-$KIDSCONTROL_DEFAULT}"

  echo "Hole Kinderliste von: ${KC}/api/client/kids"
  local json
  json="$(curl -fsS "${KC}/api/client/kids")" || {
    echo "FEHLER: Konnte KidsControl nicht erreichen."
    echo "Tipp: nimm http://192.168.1.81 als Base-URL oder prüfe DNS."
    exit 1
  }

  # Validieren
  echo "$json" | jq -e 'type=="array"' >/dev/null || {
    echo "FEHLER: Unerwartete Antwort:"
    echo "$json"
    exit 1
  }

  echo "$json"
}

map_kid_to_home() {
  local ad_user="$1"
  local local_user="$2"
  local local_home="$3"

  # AD-User muss sichtbar sein
  if ! getent passwd "${ad_user}" >/dev/null; then
    systemctl restart sssd
    sleep 2
  fi
  getent passwd "${ad_user}" >/dev/null || {
    echo "FEHLER: AD-User '${ad_user}' wird nicht aufgelöst (SSSD)."
    exit 1
  }

  # Homedir Override
  if command -v sss_override >/dev/null 2>&1; then
    sss_override user-add "${ad_user}" -h "${local_home}" -s /bin/bash || true
  fi
  systemctl restart sssd
  sleep 1

  echo "Setze Besitzrechte auf ${ad_user}:${ad_user} für ${local_home}..."
  chown -R "${ad_user}:${ad_user}" "${local_home}"

  echo "✅ Mapping: ${ad_user} -> ${local_home} (lokal: ${local_user})"
}

main() {
  need_root
  detect_iface
  echo "=== KidsControl Client Join (CachyOS) ==="
  echo "Interface: ${IFACE}"
  echo "Realm: ${REALM} | Domain: ${DOMAIN} | Workgroup: ${WORKGROUP}"
  echo

  install_pkgs
  set_dns_adguard

  echo "[DNS] SRV-Test via AdGuard (${DNS_DEFAULT}) (nur Info):"
  dig @"${DNS_DEFAULT}" _ldap._tcp.${DOMAIN} SRV +short || true
  echo

  write_krb5
  write_samba_member_conf
  time_sync
  domain_join
  write_sssd
  patch_nsswitch
  patch_pam
  enable_services

  echo
  echo "Lade Kinderliste automatisch vom KidsControl-Server..."
  kids_json="$(fetch_kids)"

  echo
  echo "Gefundene Kinder (aus KidsControl DB):"
  echo "$kids_json" | jq -r '.[] | "- \(.username) (\(.display))"'
  echo

  # Für jedes Kind: lokalen User auswählen, dann mapping
  echo "$kids_json" | jq -r '.[].username' | while read -r kid; do
    sel="$(choose_local_user "Lokalen Benutzer für AD-Kind '${kid}' auswählen:")"
    local_user="$(awk '{print $1}' <<<"$sel")"
    local_home="$(awk '{print $2}' <<<"$sel")"
    map_kid_to_home "$kid" "$local_user" "$local_home"
  done

  echo
  echo "✅ Fertig. Tests:"
  echo "  id leonard"
  echo "  id ferdinand"
  echo "Login-Test: an der Konsole mit AD-User + AD-Passwort."
}

main "$@"
