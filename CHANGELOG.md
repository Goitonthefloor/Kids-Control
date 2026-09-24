# Changelog

## Unreleased

- Each child card can block a program or give it a daily minute quota; the agent stops the program when the quota is used up
- The child PC warns once each when a running program has 5, 2, or 1 minute of quota left
- `python -m kidscontrol_agent --settings` chooses whether those warnings are a message window or a toast; the choice is stored next to `client.env`

## 1.6.0

- The install address opens a form that asks which child the PC belongs to and creates that device
- The installer then exchanges hostname, system, and keys with the server
- The browser lists each confirmation as the PC reports it

## 1.5.0

- Each child page shows an address. Open it in a browser on the child PC and KidsControl downloads the installer for Windows, macOS, or Linux
- The same address, requested without a browser, returns a script that detects the system and runs the matching installer

## 1.4.0

- The installer shows a clear notice: the child account must not be an administrator
- Daily screen time counts 30-second polls, and overnight time windows wrap past midnight
- Enrollment codes work once; parents can create a new code on the child page
- Remote updates stay pending until the agent confirms, and stalled updates are queued again
- Setup is only accepted from the server machine, session cookies are SameSite, and weak secrets are rejected
- SSH pins the host key reported by the client and refuses unsafe package names
- Login and enrollment attempts are throttled; notifications no longer build shell commands from app names

## 1.3.0

- The child-PC agent installs as a system service: root on Linux and macOS, SYSTEM on Windows
- Setup refuses to run as the child account
- The service does not stop itself or pid 1 when an app block matches

## 1.2.0

- One-click server setup: `setup-server.sh`, `setup-server.command`, `setup-server.cmd`
- One-click client downloads on the child page (Linux, macOS, Windows) with server URL and enrollment token
- Agent bundles at `/setup/agent.tgz` and `/setup/agent.zip`
- Linux root install also enables the `kidscontrol-agent` systemd service
- UI and docs spell out parent password vs household client-setup password vs per-child enrollment code

## 1.1.0

- German and English UI and README
- Editable app blocks
- Child enrollment token, OpenSSH install, SSH key upload

## 1.0.0

- Cross-platform parent hub: screen time, app blocks, software inventory, remote updates, SSH
