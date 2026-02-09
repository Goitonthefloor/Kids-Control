#!/usr/bin/env python3
"""
Kids-Control Windows 11 Client
Monitors and enforces screen time limits and app restrictions.

Features:
- Checks server for allowed time and app restrictions
- Blocks unauthorized apps
- Shows warnings before time expires
- System tray integration
- Auto-start with Windows
"""

import sys
import os
import json
import time
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path
import winreg
import psutil
import pystray
from PIL import Image, ImageDraw
from threading import Thread, Event
import win32gui
import win32con
import win32process
import ctypes
from ctypes import wintypes

# Configuration
CONFIG_FILE = Path.home() / ".kidscontrol" / "config.json"
LOG_FILE = Path.home() / ".kidscontrol" / "client.log"

class KidsControlClient:
    def __init__(self):
        self.config = self.load_config()
        self.server_url = self.config.get("server_url", "http://localhost:8000")
        self.username = self.config.get("username", os.getlogin())
        self.check_interval = self.config.get("check_interval", 60)  # seconds
        self.blocked_apps = set()
        self.allowed_time = True
        self.warning_shown = False
        self.stop_event = Event()
        self.icon = None
        self.monitored_processes = {}
        
    def load_config(self):
        """Load configuration from file or create default."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        else:
            default_config = {
                "server_url": "http://192.168.1.100:8000",
                "username": os.getlogin(),
                "check_interval": 60,
                "auto_start": True
            }
            self.save_config(default_config)
            return default_config
    
    def save_config(self, config):
        """Save configuration to file."""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    
    def log(self, message):
        """Write log message to file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}\n"
        
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_msg)
        
        print(log_msg.strip())
    
    def check_server_status(self):
        """Query server for current status and restrictions."""
        try:
            response = requests.get(
                f"{self.server_url}/api/check/{self.username}",
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Update allowed time status
                self.allowed_time = data.get("allowed", False)
                
                # Update blocked apps list
                self.blocked_apps = set(data.get("blocked_apps", []))
                
                # Check for warning
                remaining = data.get("remaining_minutes", 0)
                if remaining <= 10 and remaining > 0 and not self.warning_shown:
                    self.show_warning(remaining)
                    self.warning_shown = True
                elif remaining > 10:
                    self.warning_shown = False
                
                return data
            else:
                self.log(f"Server error: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.log(f"Connection error: {e}")
            return None
    
    def get_running_processes(self):
        """Get list of currently running processes."""
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                info = proc.info
                if info['exe']:
                    processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'exe': info['exe'].lower()
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes
    
    def is_app_blocked(self, app_path):
        """Check if an app is in the blocked list."""
        app_path = app_path.lower()
        
        for blocked in self.blocked_apps:
            blocked = blocked.lower()
            if blocked in app_path or Path(app_path).name == blocked:
                return True
        return False
    
    def kill_process(self, pid):
        """Terminate a process by PID."""
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=3)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            try:
                proc.kill()
                return True
            except:
                return False
        except Exception as e:
            self.log(f"Failed to kill process {pid}: {e}")
            return False
    
    def enforce_restrictions(self):
        """Check running processes and enforce restrictions."""
        if not self.allowed_time:
            # Time expired - block everything except system apps
            self.show_time_expired_message()
            self.lock_screen()
            return
        
        # Check for blocked apps
        running = self.get_running_processes()
        
        for proc in running:
            if self.is_app_blocked(proc['exe']):
                self.log(f"Blocking app: {proc['name']} (PID: {proc['pid']})")
                self.show_blocked_app_message(proc['name'])
                self.kill_process(proc['pid'])
    
    def show_warning(self, remaining_minutes):
        """Show warning that time is running out."""
        message = f"Warnung: Noch {remaining_minutes} Minuten verfügbar!"
        self.show_notification("Kids-Control", message)
        self.log(f"Warning shown: {remaining_minutes} minutes remaining")
    
    def show_blocked_app_message(self, app_name):
        """Show message when blocking an app."""
        message = f"Die App '{app_name}' ist gesperrt."
        self.show_notification("Kids-Control - App gesperrt", message)
    
    def show_time_expired_message(self):
        """Show message when time has expired."""
        message = "Deine Bildschirmzeit ist abgelaufen. Bitte melde dich ab."
        self.show_notification("Kids-Control - Zeit abgelaufen", message)
    
    def show_notification(self, title, message):
        """Show Windows notification."""
        if self.icon:
            self.icon.notify(message, title)
    
    def lock_screen(self):
        """Lock Windows screen when time expires."""
        try:
            ctypes.windll.user32.LockWorkStation()
            self.log("Screen locked due to time expiry")
        except Exception as e:
            self.log(f"Failed to lock screen: {e}")
    
    def create_tray_icon(self):
        """Create system tray icon."""
        # Create a simple icon image
        def create_image():
            width = 64
            height = 64
            image = Image.new('RGB', (width, height), 'white')
            dc = ImageDraw.Draw(image)
            dc.rectangle([0, 0, width, height], fill='blue')
            dc.text((10, 20), 'KC', fill='white')
            return image
        
        icon_image = create_image()
        
        menu = pystray.Menu(
            pystray.MenuItem('Status', self.show_status),
            pystray.MenuItem('Konfiguration', self.show_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Beenden', self.quit_app)
        )
        
        self.icon = pystray.Icon('KidsControl', icon_image, 'Kids-Control Client', menu)
    
    def show_status(self):
        """Show current status window."""
        status = "Erlaubt" if self.allowed_time else "Gesperrt"
        blocked = ", ".join(self.blocked_apps) if self.blocked_apps else "Keine"
        
        message = f"Status: {status}\nGesperrte Apps: {blocked}"
        self.show_notification("Kids-Control Status", message)
    
    def show_config(self):
        """Show configuration window (placeholder)."""
        message = f"Server: {self.server_url}\nBenutzer: {self.username}"
        self.show_notification("Kids-Control Konfiguration", message)
    
    def quit_app(self):
        """Stop the application."""
        self.log("Application shutdown requested")
        self.stop_event.set()
        if self.icon:
            self.icon.stop()
    
    def monitor_loop(self):
        """Main monitoring loop."""
        self.log(f"Monitoring started for user: {self.username}")
        
        while not self.stop_event.is_set():
            try:
                # Check server status
                status = self.check_server_status()
                
                if status:
                    # Enforce restrictions
                    self.enforce_restrictions()
                
                # Wait before next check
                self.stop_event.wait(self.check_interval)
                
            except Exception as e:
                self.log(f"Error in monitoring loop: {e}")
                self.stop_event.wait(self.check_interval)
    
    def setup_autostart(self):
        """Add application to Windows startup."""
        if not self.config.get("auto_start", True):
            return
        
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            
            app_path = sys.executable
            script_path = os.path.abspath(__file__)
            startup_cmd = f'"{app_path}" "{script_path}"'
            
            winreg.SetValueEx(key, "KidsControlClient", 0, winreg.REG_SZ, startup_cmd)
            winreg.CloseKey(key)
            
            self.log("Autostart configured")
        except Exception as e:
            self.log(f"Failed to setup autostart: {e}")
    
    def run(self):
        """Start the client application."""
        self.log("Kids-Control Client starting...")
        
        # Setup autostart
        self.setup_autostart()
        
        # Create system tray icon
        self.create_tray_icon()
        
        # Start monitoring in background thread
        monitor_thread = Thread(target=self.monitor_loop, daemon=True)
        monitor_thread.start()
        
        # Run system tray (blocks until quit)
        self.icon.run()
        
        # Wait for monitoring thread to finish
        self.stop_event.set()
        monitor_thread.join(timeout=5)
        
        self.log("Kids-Control Client stopped")

def main():
    """Main entry point."""
    # Check if running as admin (required for some features)
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except:
        is_admin = False
    
    if not is_admin:
        print("Warning: Running without administrator privileges.")
        print("Some features may not work correctly.")
    
    # Create and run client
    client = KidsControlClient()
    client.run()

if __name__ == "__main__":
    main()
