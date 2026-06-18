import sys
import os
import json
import subprocess
import ctypes
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTabWidget, 
                             QTextEdit, QLineEdit, QListWidget, QComboBox, 
                             QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QVariantAnimation
from PyQt6.QtGui import QIcon, QColor

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010

DARK_THEME_QSS = """
QMainWindow { background-color: #1e1e2e; }
QLabel { color: #cdd6f4; font-size: 14px; }
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover { background-color: #b4befe; }
QPushButton#btn_delete { background-color: #f38ba8; }
QPushButton#btn_delete:hover { background-color: #eba0ac; }
QPushButton#btn_browse { background-color: #a6e3a1; color: #1e1e2e; }
QPushButton#btn_browse:hover { background-color: #94e2d5; }
QPushButton#btn_service { background-color: #f9e2af; color: #1e1e2e; }
QPushButton#btn_service:hover { background-color: #fae3b0; }
QTabWidget::pane { border: 1px solid #313244; background-color: #1e1e2e; border-radius: 6px; }
QTabBar::tab { background-color: #313244; color: #cdd6f4; padding: 8px 20px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background-color: #89b4fa; color: #1e1e2e; }
QLineEdit, QListWidget, QTextEdit { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 6px; }
QComboBox { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; padding: 6px; }
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView { background-color: #313244; color: #cdd6f4; selection-background-color: #89b4fa; selection-color: #1e1e2e; }
"""

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class BigToggleButton(QPushButton):
    """Custom animated button for service state toggle."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(250, 65)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.color_start = QColor("#89b4fa")
        self.color_stop = QColor("#f38ba8")
        self._current_color = self.color_start
        
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(300)
        self.anim.valueChanged.connect(self._on_color_change)
        
        self.update_style(self._current_color, "START ZAPRET")
        
    def _on_color_change(self, color):
        self._current_color = color
        text = "STOP ZAPRET" if self.anim.endValue() == self.color_stop else "START ZAPRET"
        self.update_style(color, text)
        
    def update_style(self, color, text):
        self.setText(text)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color.name()};
                color: #1e1e2e;
                border-radius: 32px;
                font-weight: bold;
                font-size: 22px;
                border: none;
            }}
            QPushButton:hover {{
                border: 3px solid #cdd6f4;
            }}
        """)
        
    def set_active(self, active):
        self.anim.stop()
        self.anim.setStartValue(self._current_color)
        if active:
            self.anim.setEndValue(self.color_stop)
        else:
            self.anim.setEndValue(self.color_start)
        self.anim.start()


class ProcessOutputReader(QThread):
    """Asynchronous reader for sub-process stdout streaming."""
    new_log = pyqtSignal(str)

    def __init__(self, process):
        super().__init__()
        self.process = process

    def run(self):
        if self.process and self.process.stdout:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.new_log.emit(line.strip())
            self.process.stdout.close()


class ZapretController(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zapret Simple Launcher")
        self.setFixedSize(550, 480)
        
        icon_path = resource_path("logo.ico")
        self.setWindowIcon(QIcon(icon_path))
        
        self.current_process = None
        self.output_reader = None
        self.is_running = False
        
        app_data_dir = os.path.join(os.getenv('APPDATA', os.path.expanduser("~")), "ZapretManager")
        os.makedirs(app_data_dir, exist_ok=True)
        self.settings_file = os.path.join(app_data_dir, "settings.json")
        
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        self.tabs = QTabWidget()
        self.tab_dashboard = QWidget()
        self.tab_services = QWidget()
        self.tab_routing = QWidget()
        self.tab_logs = QWidget()

        self.tabs.addTab(self.tab_dashboard, "Dashboard")
        self.tabs.addTab(self.tab_services, "Services")
        self.tabs.addTab(self.tab_routing, "Routing")
        self.tabs.addTab(self.tab_logs, "Logs")
        
        self.main_layout.addWidget(self.tabs)

        self.setup_dashboard_tab()
        self.setup_services_tab()
        self.setup_routing_tab()
        self.setup_logs_tab()

    def setup_dashboard_tab(self):
        layout = QVBoxLayout(self.tab_dashboard)

        top_layout = QHBoxLayout()
        lbl_select_bat = QLabel("Select manual .bat:")
        self.combo_bat_files = QComboBox()
        self.combo_bat_files.addItem("Please select Zapret folder first...")
        self.combo_bat_files.currentTextChanged.connect(self.save_settings)
        
        top_layout.addWidget(lbl_select_bat)
        top_layout.addWidget(self.combo_bat_files, stretch=1)
        layout.addLayout(top_layout)

        layout.addStretch()

        middle_layout = QVBoxLayout()
        middle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_status = QLabel("Service Status: STOPPED")
        self.lbl_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #f38ba8;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        middle_layout.addWidget(self.lbl_status)
        
        middle_layout.addSpacing(15)

        self.btn_toggle = BigToggleButton()
        self.btn_toggle.clicked.connect(self.on_toggle_clicked)
        middle_layout.addWidget(self.btn_toggle, alignment=Qt.AlignmentFlag.AlignCenter)
        
        layout.addLayout(middle_layout)

        layout.addStretch()

        self.lbl_github = QLabel('<a href="https://github.com/flowseal/zapret-discord-youtube/releases" style="color: #89b4fa; text-decoration: none;">📥 Скачать последнюю версию Zapret (GitHub)</a>')
        self.lbl_github.setOpenExternalLinks(True)
        self.lbl_github.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_github.setStyleSheet("font-size: 12px;")
        self.lbl_github.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.lbl_github)
        
        layout.addSpacing(5)

        bottom_layout = QHBoxLayout()
        self.input_folder_path = QLineEdit()
        self.input_folder_path.setReadOnly(True)
        self.input_folder_path.setPlaceholderText("Path to downloaded zapret folder...")
        
        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setObjectName("btn_browse")
        self.btn_browse.clicked.connect(self.browse_folder)

        bottom_layout.addWidget(self.input_folder_path, stretch=1)
        bottom_layout.addWidget(self.btn_browse)
        layout.addLayout(bottom_layout)

    def setup_services_tab(self):
        layout = QVBoxLayout(self.tab_services)
        
        info_lbl = QLabel(
            "Background Services Management\n\n"
            "Here you can install or remove Zapret as a Windows Background Service.\n"
            "Scripts will open in a new console window requiring your confirmation."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(info_lbl)

        layout.addSpacing(20)

        lbl_select_svc = QLabel("Select service script:")
        layout.addWidget(lbl_select_svc)

        self.combo_service_bats = QComboBox()
        self.combo_service_bats.addItem("No folder selected...")
        layout.addWidget(self.combo_service_bats)

        self.btn_run_service = QPushButton("Execute Service Script")
        self.btn_run_service.setObjectName("btn_service")
        self.btn_run_service.clicked.connect(self.run_service_script)
        layout.addWidget(self.btn_run_service)

        layout.addStretch()

    def setup_routing_tab(self):
        layout = QVBoxLayout(self.tab_routing)
        self.lbl_routing = QLabel("Domain/IP Exclusion List:")
        layout.addWidget(self.lbl_routing)
        self.list_domains = QListWidget()
        layout.addWidget(self.list_domains)

        actions_layout = QHBoxLayout()
        self.input_new_domain = QLineEdit()
        self.input_new_domain.setPlaceholderText("Enter domain...")
        self.input_new_domain.returnPressed.connect(self.add_domain)
        
        self.btn_add_domain = QPushButton("Add")
        self.btn_add_domain.clicked.connect(self.add_domain)

        self.btn_delete_domain = QPushButton("Delete Selected")
        self.btn_delete_domain.setObjectName("btn_delete")
        self.btn_delete_domain.clicked.connect(self.delete_domain)

        actions_layout.addWidget(self.input_new_domain, stretch=1)
        actions_layout.addWidget(self.btn_add_domain)
        actions_layout.addWidget(self.btn_delete_domain)
        layout.addLayout(actions_layout)

    def setup_logs_tab(self):
        layout = QVBoxLayout(self.tab_logs)
        self.text_logs = QTextEdit()
        self.text_logs.setReadOnly(True)
        self.text_logs.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; background-color: #11111b;")
        layout.addWidget(self.text_logs)

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    folder_path = settings.get("folder_path", "")
                    saved_bat = settings.get("selected_bat", "")

                    if folder_path and os.path.isdir(folder_path):
                        self.input_folder_path.setText(folder_path)
                        self.scan_for_bat_files(folder_path)
                        
                        index = self.combo_bat_files.findText(saved_bat)
                        if index >= 0:
                            self.combo_bat_files.setCurrentIndex(index)
                        
                        self.log_message("[System] Settings loaded from AppData.")
            except Exception as e:
                self.log_message(f"[System] Error loading settings: {str(e)}")

    def save_settings(self, _=None):
        settings = {
            "folder_path": self.input_folder_path.text(),
            "selected_bat": self.combo_bat_files.currentText()
        }
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            self.log_message(f"[System] Error saving settings: {str(e)}")

    def browse_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Zapret Directory")
        if folder_path:
            self.input_folder_path.setText(folder_path)
            self.scan_for_bat_files(folder_path)
            self.save_settings()
            self.log_message(f"[System] Selected folder: {folder_path}")

    def scan_for_bat_files(self, folder_path):
        self.combo_bat_files.blockSignals(True)
        self.combo_bat_files.clear()
        self.combo_service_bats.clear()
        
        try:
            bat_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.bat')]
            general_bats = []
            service_bats = []
            
            for bat in bat_files:
                if "service" in bat.lower():
                    service_bats.append(bat)
                else:
                    general_bats.append(bat)
                    
            if general_bats:
                self.combo_bat_files.addItems(general_bats)
            else:
                self.combo_bat_files.addItem("No general .bat files found")
                
            if service_bats:
                self.combo_service_bats.addItems(service_bats)
            else:
                self.combo_service_bats.addItem("No service .bat files found")
                
        except Exception as e:
            self.log_message(f"[System] Error reading directory: {str(e)}")
        finally:
            self.combo_bat_files.blockSignals(False)

    def on_toggle_clicked(self):
        if not self.is_running:
            if self.start_manual_service():
                self.is_running = True
                self.btn_toggle.set_active(True)
        else:
            self.stop_manual_service()

    def start_manual_service(self):
        selected_bat = self.combo_bat_files.currentText()
        folder_path = self.input_folder_path.text()

        if not selected_bat or "No general" in selected_bat or "Please select" in selected_bat:
            self.log_message("[System] Error: Invalid .bat file.")
            return False

        bat_full_path = os.path.join(folder_path, selected_bat)

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 

            self.current_process = subprocess.Popen(
                ["cmd.exe", "/c", bat_full_path], 
                cwd=folder_path, 
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=CREATE_NO_WINDOW
            )
            
            self.output_reader = ProcessOutputReader(self.current_process)
            self.output_reader.new_log.connect(self.log_message)
            self.output_reader.start()
            
            self.lbl_status.setText(f"Status: RUNNING ({selected_bat})")
            self.lbl_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #a6e3a1;")
            self.log_message(f"[System] Started manual bypass in STEALTH mode: {selected_bat}")
            
            self.tabs.setCurrentIndex(3)
            return True 
            
        except Exception as e:
            self.log_message(f"[System] Execution Error: {str(e)}")
            self.lbl_status.setText("Status: ERROR")
            self.lbl_status.setStyleSheet("color: #f38ba8;")
            return False

    def stop_manual_service(self):
        try:
            if self.current_process:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.current_process.pid)], 
                    capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
                )
                self.current_process.terminate()
                self.current_process = None
                
            subprocess.run(
                ["taskkill", "/F", "/IM", "winws.exe"], 
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
            )
                
            if self.output_reader:
                self.output_reader.quit()
                self.output_reader = None

            self.lbl_status.setText("Service Status: STOPPED")
            self.lbl_status.setStyleSheet("font-size: 18px; font-weight: bold; color: #f38ba8;")
            self.log_message("[System] Manual bypass completely stopped.")
            
        except Exception as e:
            self.log_message(f"[System] Stop Error: {str(e)}")
        finally:
            self.is_running = False
            self.btn_toggle.set_active(False)

    def run_service_script(self):
        selected_bat = self.combo_service_bats.currentText()
        folder_path = self.input_folder_path.text()

        if not selected_bat or "No service" in selected_bat:
            return

        bat_full_path = os.path.join(folder_path, selected_bat)

        try:
            subprocess.Popen(
                bat_full_path, 
                cwd=folder_path, 
                shell=True,
                creationflags=CREATE_NEW_CONSOLE
            )
            self.log_message(f"[System] Launched service setup script: {selected_bat}")
        except Exception as e:
            self.log_message(f"[System] Service Setup Error: {str(e)}")

    def add_domain(self):
        domain = self.input_new_domain.text().strip()
        if domain:
            self.list_domains.addItem(domain)
            self.log_message(f"[System] Added {domain} to routing list.")
            self.input_new_domain.clear()

    def delete_domain(self):
        selected_items = self.list_domains.selectedItems()
        if not selected_items:
            return
            
        reply = QMessageBox.question(
            self, 'Confirm Deletion', 
            f"Are you sure you want to delete '{selected_items[0].text()}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for item in selected_items:
                self.list_domains.takeItem(self.list_domains.row(item))
                self.log_message(f"[System] Deleted {item.text()} from routing list.")

    def log_message(self, message):
        self.text_logs.append(message)
        scroll_bar = self.text_logs.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def closeEvent(self, event):
        self.stop_manual_service()
        event.accept()


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if __name__ == "__main__":
    if is_admin():
        app = QApplication(sys.argv)
        app.setStyleSheet(DARK_THEME_QSS)
        window = ZapretController()
        window.show()
        sys.exit(app.exec())
    else:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()