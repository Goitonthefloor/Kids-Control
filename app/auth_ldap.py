import os
import ssl
from ldap3 import Server, Connection, SUBTREE, Tls

LDAP_URI = os.getenv("LDAP_URI", "ldap://dc01.home.lan")
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "DC=home,DC=lan")
LDAP_REALM = os.getenv("LDAP_REALM", "HOME.LAN")
LDAP_PARENT_GROUP_CN = os.getenv("LDAP_PARENT_GROUP_CN", "eltern")

# Homelab: Zertifikat-Validierung aus (schnell & pragmatisch).
# Wenn du es "richtig" willst: CA importieren + validate=ssl.CERT_REQUIRED
tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)

def authenticate_parent(login: str, password: str) -> bool:
    login = login.strip()
    if not login or not password:
        return False

    upn = f"{login}@{LDAP_REALM}"

    server = Server(LDAP_URI, use_ssl=False, tls=tls_config, get_info=None)
    conn = Connection(server, user=upn, password=password, auto_bind=False)

    if not conn.start_tls():
        return False
    if not conn.bind():
        return False

    search_filter = f"(&(objectClass=user)(sAMAccountName={login}))"
    ok = conn.search(
        search_base=LDAP_BASE_DN,
        search_filter=search_filter,
        search_scope=SUBTREE,
        attributes=["memberOf"]
    )
    if not ok or not conn.entries:
        conn.unbind()
        return False

    entry = conn.entries[0]
    member_of = entry.memberOf.values if "memberOf" in entry else []
    needle = f"CN={LDAP_PARENT_GROUP_CN},"
    is_parent = any(str(g).startswith(needle) for g in member_of)

    conn.unbind()
    return is_parent
