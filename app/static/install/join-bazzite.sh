#!/usr/bin/env bash
set -euo pipefail

DOMAIN_FQDN="home.lan"
DOMAIN_UPPER="HOME.LAN"
DC_IP="192.168.1.240"
DNS_IP="192.168.1.86"

log() { printf "\n[%s] %s\n" "$(date +'%F %T')" "$*"; }

need_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Bitte als root ausführen: sudo $0"
    exit 1
  fi
}

set_dns_nm() {
  log "DNS auf ${DNS_IP} setzen (NetworkManager)…"
  if command -v nmcli >/dev/null 2>&1; then
    # aktives Interface ermitteln (best effort)
    ACTIVE_CON=$(nmcli -t -f NAME,DEVICE con show --active | head -n1 | cut -d: -f1 || true)
    if [[ -n "${ACTIVE_CON}" ]]; then
      nmcli con mod "${ACTIVE_CON}" ipv4.dns "${DNS_IP}" ipv4.ignore-auto-dns yes || true
      nmcli con up "${ACTIVE_CON}" || true
    fi
  fi
}

install_pkgs() {
  log "Pakete installieren (sssd, samba, krb5)…"
  if command -v rpm-ostree >/dev/null 2>&1; then
    rpm-ostree install -y sssd realmd adcli krb5-workstation samba-common-tools openldap-clients || true
    log "Wenn rpm-ostree etwas installiert hat, kann ein Reboot nötig sein."
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y sssd realmd adcli krb5-workstation samba-common-tools openldap-clients || true
  else
    echo "Weder rpm-ostree noch dnf gefunden. Abbruch."
    exit 1
  fi
}

write_krb5() {
  log "/etc/krb5.conf schreiben..."
  cat > /etc/krb5.conf <<EOF
[libdefaults]
  default_realm = ${DOMAIN_UPPER}
  dns_lookup_realm = true
  dns_lookup_kdc = true
  rdns = false

[realms]
  ${DOMAIN_UPPER} = {
    kdc = ${DC_IP}
    admin_server = ${DC_IP}
  }

[domain_realm]
  .${DOMAIN_FQDN} = ${DOMAIN_UPPER}
  ${DOMAIN_FQDN} = ${DOMAIN_UPPER}
EOF
}

write_sssd() {
  log "/etc/sssd/sssd.conf schreiben..."
  mkdir -p /etc/sssd
  cat > /etc/sssd/sssd.conf <<EOF
[sssd]
domains = ${DOMAIN_FQDN}
config_file_version = 2
services = nss, pam

[domain/${DOMAIN_FQDN}]
id_provider = ad
access_provider = ad
ad_domain = ${DOMAIN_FQDN}
krb5_realm = ${DOMAIN_UPPER}
ad_server = ${DC_IP}

use_fully_qualified_names = false
fallback_homedir = /home/%u
default_shell = /bin/bash

cache_credentials = true
ldap_id_mapping = true
dyndns_update = false
EOF
  chmod 600 /etc/sssd/sssd.conf
}

enable_services() {
  log "SSSD aktivieren…"
  systemctl enable --now sssd || true
}

join_domain() {
  log "Kerberos Ticket holen und joinen…"
  read -rp "AD Admin User (z.B. administrator): " ADMIN_USER
  echo "Passwort für ${ADMIN_USER}@${DOMAIN_UPPER}:"
  kdestroy || true
  kinit "${ADMIN_USER}@${DOMAIN_UPPER}"

  # realmd wäre nicer, aber net ads ist robust
  if command -v net >/dev/null 2>&1; then
    net ads join -k
  else
    echo "'net' nicht gefunden. Installiere samba-common-tools und versuche erneut."
    exit 1
  fi
}

pam_mkhomedir() {
  log "Home-Dir Auto-Erstellung aktivieren (authselect/pam)…"
  # Fedora: authselect ist üblich
  if command -v authselect >/dev/null 2>&1; then
    authselect select sssd with-mkhomedir --force || true
  fi
}

verify() {
  log "Verification:"
  dig _ldap._tcp.${DOMAIN_FQDN} SRV +short || true
  getent passwd leonard || true
  systemctl status sssd --no-pager || true
  log "Fertig."
}

main() {
  need_root
  set_dns_nm
  install_pkgs
  write_krb5
  write_sssd
  enable_services
  join_domain
  pam_mkhomedir
  verify
}

main "$@"
