import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import winreg
from datetime import datetime
from pathlib import Path

from launcher_auth import verify_launcher_token as verify_hmac_launcher_token

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "PT Studio"

USERS_URL = (
    "https://raw.githubusercontent.com/"
    "PhamThangbn/PT_Studio/main/users.json"
)

SESSION_SECONDS = 24 * 60 * 60


APP_STYLE = """
QMainWindow, QDialog, QWidget {
    background-color: #f3f5f8;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #0b1220;
}

QLabel {
    background: transparent;
}

QLabel#LogoBadge {
    background-color: #2f80ed;
    color: #ffffff;
    border-radius: 18px;
    font-size: 15px;
    font-weight: 800;
}

QLabel#TitleLabel {
    background: transparent;
    font-size: 28px;
    font-weight: 800;
    color: #0b1220;
}

QLabel#SubTitleLabel {
    background: transparent;
    font-size: 13px;
    color: #64748b;
}

QLabel#SectionLabel {
    background: transparent;
    font-size: 12px;
    font-weight: 700;
    color: #334155;
}

QLabel#HintLabel {
    background: transparent;
    font-size: 11px;
    color: #94a3b8;
}

QFrame#Card {
    background-color: #ffffff;
    border: 1px solid #dbe2ea;
    border-radius: 18px;
}

QFrame#MachineBox {
    background-color: #f8fafc;
    border: 1px solid #dbe2ea;
    border-radius: 12px;
}

QLabel#MachineText {
    background: transparent;
    color: #0f172a;
    font-family: Consolas, "Courier New", monospace;
    font-size: 14px;
    font-weight: 700;
}

QLineEdit {
    background-color: #ffffff;
    border: 1.5px solid #cfd6df;
    border-radius: 10px;
    padding: 9px 12px;
    color: #0b1220;
    font-size: 14px;
    selection-background-color: #2f80ed;
}

QLineEdit:focus {
    border-color: #2f80ed;
    background-color: #ffffff;
}

QPushButton {
    background-color: #2f80ed;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 14px;
    font-weight: 700;
    min-height: 34px;
}

QPushButton:hover {
    background-color: #246fdb;
}

QPushButton:pressed {
    background-color: #1f5db8;
}

QPushButton#CopyButton {
    background-color: #eef5ff;
    color: #2f80ed;
    border: 1px solid #b9d3f5;
    border-radius: 9px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 700;
    min-height: 26px;
}

QPushButton#CopyButton:hover {
    background-color: #dbeafe;
}

QPushButton#FreeButton {
    background-color: #27ae60;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 700;
    padding: 10px 18px;
}

QPushButton#FreeButton:hover {
    background-color: #219150;
}
"""


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_base_dir()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = DATA_DIR / "session_token.json"


def run_cmd(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd,
            shell=True,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0,
        ).strip()
    except Exception:
        return ""


def get_wmic_value(cmd: str) -> str:
    output = run_cmd(cmd)
    lines = [x.strip() for x in output.splitlines() if x.strip()]
    return lines[1] if len(lines) >= 2 else ""


def normalize(value: str) -> str:
    return (
        str(value)
        .strip()
        .upper()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace(".", "")
        .replace(":", "")
        .replace("/", "")
        .replace("\\", "")
    )


def _qv(cmd: str) -> str:
    return get_wmic_value(cmd)


def _node_a() -> str:
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography"
        )
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return value
    except Exception:
        return ""


def _node_b() -> str:
    return _qv("wmic csproduct get UUID")


def _node_c() -> str:
    return _qv("wmic bios get serialnumber")


def _build_seed() -> bytes:
    parts = [
        b"PT",
        b"_ST",
        b"UD",
        b"IO",
        b"_NODE",
        b"_V4",
        b"_2026",
        b"_X9",
        b"K2",
    ]
    return b"".join(parts)


def _mix_round(data: str, seed: bytes, rounds: int = 220_000) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        data.encode("utf-8"),
        seed,
        rounds
    ).hex().upper()


def get_machine_hash() -> str:
    nodes = [
        normalize(_node_a()),
        normalize(_node_b()),
        normalize(_node_c()),
    ]

    raw = "|".join(nodes)

    if raw.replace("|", "") == "":
        raw = normalize(os.environ.get("COMPUTERNAME", "")) + "|" + normalize(os.environ.get("USERNAME", ""))

    digest1 = _mix_round(raw, _build_seed(), 220_000)

    digest2 = hashlib.sha256(
        (digest1[::-1] + "|PT_DEVICE_LAYER_2").encode("utf-8")
    ).hexdigest().upper()

    return digest2


def get_machine_id() -> str:
    pepper = "|".join(["P", "T", "S", "FINAL", "NODE", "2026"])
    final = hashlib.sha256(
        (get_machine_hash() + "|" + pepper).encode("utf-8")
    ).hexdigest().upper()

    code = final[:16]
    return f"PT-{code[:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"


def parse_launcher_args():
    launcher_token = None
    argv = sys.argv[1:]

    for i, arg in enumerate(argv):
        if arg == "--launcher-token" and i + 1 < len(argv):
            launcher_token = argv[i + 1]

    return launcher_token


def verify_launcher_token() -> bool:
    launcher_token = parse_launcher_args()

    if not launcher_token:
        return False

    return verify_hmac_launcher_token(
        token=launcher_token,
        machine_id=get_machine_id()
    )

def load_users_from_github(parent=None):
    try:
        with urllib.request.urlopen(USERS_URL, timeout=10) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw)
            return data.get("users", [])
    except Exception as e:
        QMessageBox.warning(
            parent,
            "Không tải được dữ liệu VIP",
            "Không thể tải users.json từ GitHub.\n\n"
            "Bạn vẫn có thể đăng nhập Free.\n\n"
            f"Lỗi: {e}"
        )
        return []


def is_not_expired(expires: str) -> bool:
    if not expires:
        return True

    try:
        today = datetime.now().date()
        exp_date = datetime.strptime(expires, "%Y-%m-%d").date()
        return today <= exp_date
    except Exception:
        return False


def check_vip_login(username: str, machine_id: str, parent=None) -> dict:
    users = load_users_from_github(parent=parent)
    username = username.strip().upper()

    for user in users:
        db_username = str(user.get("username", "")).strip().upper()
        db_machine_id = str(user.get("machine_id", "")).strip().upper()
        active = bool(user.get("active", False))
        role = str(user.get("role", "FREE")).strip().upper()
        expires = user.get("expires", "")

        if (
            db_username == username
            and db_machine_id == machine_id.upper()
            and active is True
            and role == "VIP"
            and is_not_expired(expires)
        ):
            return {
                "success": True,
                "username": username,
                "role": "VIP",
                "expires": expires or "Không giới hạn"
            }

    return {
        "success": False,
        "username": username,
        "role": "FREE",
        "expires": ""
    }


def create_session_token(username: str, role: str) -> str:
    machine_id = get_machine_id()
    now = int(time.time())

    raw = f"{username}|{role}|{machine_id}|{now}|PT_STUDIO_SESSION"
    token = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    data = {
        "session_token": token,
        "username": username,
        "role": role,
        "machine_id": machine_id,
        "created_at": now,
        "expires_at": now + SESSION_SECONDS
    }

    SESSION_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return token


def add_shadow(widget, blur=30, y=10, opacity=28):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y)
    shadow.setColor(QColor(15, 23, 42, opacity))
    shadow.setEnabled(True)
    widget.setGraphicsEffect(shadow)


def make_card():
    card = QFrame()
    card.setObjectName("Card")
    card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    add_shadow(card)
    return card


class MainWindow(QMainWindow):
    def __init__(self, username: str, role: str, session_token: str):
        super().__init__()
        self.username = username
        self.role = role
        self.session_token = session_token

        self.setWindowTitle(f"{APP_NAME} - MainUI")
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        self.resize(900, 560)
        self.setMinimumSize(860, 520)

        root = QWidget()
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("PT Studio MainUI")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Phiên làm việc hợp lệ. Module được load theo quyền Free/VIP.")
        subtitle.setObjectName("SubTitleLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        badge = QLabel("VIP" if role == "VIP" else "FREE")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(90, 34)
        badge.setStyleSheet(
            "background:#eef5ff; color:#2f80ed; border:1px solid #b9d3f5; "
            "border-radius:17px; font-weight:800;"
            if role == "VIP"
            else
            "background:#f1f5f9; color:#475569; border:1px solid #cbd5e1; "
            "border-radius:17px; font-weight:800;"
        )
        header.addWidget(badge)

        layout.addLayout(header)

        card = make_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 26)
        card_layout.setSpacing(16)

        ok_label = QLabel("Đăng nhập thành công")
        ok_label.setStyleSheet("font-size:24px; font-weight:800; color:#0b1220;")
        card_layout.addWidget(ok_label)

        info = QLabel(
            f"Tài khoản: {username}\n"
            f"Quyền: {role}\n"
            f"Mã máy: {get_machine_id()}\n"
            f"Session: {session_token[:18]}..."
        )
        info.setStyleSheet(
            "font-family:Consolas, monospace; font-size:15px; color:#334155; "
            "background:#f8fafc; border:1px solid #dbe2ea; border-radius:12px; padding:14px;"
        )
        card_layout.addWidget(info)

        module_text = QLabel(
            "Đã load FULL MODULE VIP" if role == "VIP" else "Đang dùng BẢN MIỄN PHÍ"
        )
        module_text.setStyleSheet(
            "font-size:18px; font-weight:800; color:#2f80ed;"
            if role == "VIP"
            else
            "font-size:18px; font-weight:800; color:#64748b;"
        )
        card_layout.addWidget(module_text)

        card_layout.addStretch()
        layout.addWidget(card, 1)


class LoginWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.main_window = None

        self.setWindowTitle(f"{APP_NAME} - Đăng nhập")
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        self.resize(600, 500)
        self.setMinimumSize(560, 470)

        self.machine_id = get_machine_id()

        self.build_ui()

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(34, 28, 34, 28)
        root.setSpacing(18)

        root.addStretch()

        header = QHBoxLayout()
        header.setSpacing(12)

        logo = QLabel("PT")
        logo.setObjectName("LogoBadge")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(36, 36)
        header.addWidget(logo)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel("PT Studio")
        title.setObjectName("TitleLabel")

        subtitle = QLabel("Đăng nhập tài khoản hoặc tiếp tục bản miễn phí.")
        subtitle.setObjectName("SubTitleLabel")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        root.addLayout(header)

        card = make_card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 24)
        card_layout.setSpacing(14)

        machine_title = QLabel("Mã định danh thiết bị v2")
        machine_title.setObjectName("SectionLabel")
        card_layout.addWidget(machine_title)

        machine_frame = QFrame()
        machine_frame.setObjectName("MachineBox")
        machine_frame.setFixedHeight(54)

        machine_layout = QHBoxLayout(machine_frame)
        machine_layout.setContentsMargins(14, 8, 8, 8)
        machine_layout.setSpacing(10)

        self.machine_label = QLabel(self.machine_id)
        self.machine_label.setObjectName("MachineText")
        self.machine_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        machine_layout.addWidget(self.machine_label, 1)

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("CopyButton")
        copy_btn.setFixedSize(76, 34)
        copy_btn.clicked.connect(self.copy_machine_id)
        machine_layout.addWidget(copy_btn)

        card_layout.addWidget(machine_frame)

        username_title = QLabel("Tài khoản VIP")
        username_title.setObjectName("SectionLabel")
        card_layout.addWidget(username_title)

        self.username_entry = QLineEdit()
        self.username_entry.setPlaceholderText("Nhập Username VIP")
        self.username_entry.setFixedHeight(44)
        self.username_entry.returnPressed.connect(self.login_vip)
        card_layout.addWidget(self.username_entry)

        login_btn = QPushButton("Đăng nhập VIP")
        login_btn.setFixedHeight(46)
        login_btn.clicked.connect(self.login_vip)
        card_layout.addWidget(login_btn)

        free_btn = QPushButton("Đăng nhập miễn phí")
        free_btn.setObjectName("FreeButton")
        free_btn.setFixedHeight(46)
        free_btn.clicked.connect(self.login_free)
        card_layout.addWidget(free_btn)

        hint = QLabel("Gửi mã thiết bị cho admin để cấp quyền VIP trên server.")
        hint.setObjectName("HintLabel")
        hint.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(hint)

        root.addWidget(card)

        root.addStretch()

    def copy_machine_id(self):
        QApplication.clipboard().setText(self.machine_id)
        QMessageBox.information(self, "Đã copy", f"Đã copy mã máy:\n{self.machine_id}")

    def login_free(self):
        self.open_main_app(role="FREE", username="FREE")

    def login_vip(self):
        username = self.username_entry.text().strip().upper()
        machine_id = get_machine_id()

        if not username:
            QMessageBox.warning(self, "Thiếu Username", "Vui lòng nhập Username VIP.")
            return

        QApplication.processEvents()

        result = check_vip_login(username=username, machine_id=machine_id, parent=self)

        if result["success"]:
            self.open_main_app(role="VIP", username=username)
        else:
            QMessageBox.critical(
                self,
                "Đăng nhập VIP thất bại",
                "Username hoặc mã máy không hợp lệ.\n\n"
                f"Username: {username}\n"
                f"Mã máy hiện tại:\n{machine_id}\n\n"
                "Bạn có thể chọn 'Tiếp tục với bản miễn phí'."
            )

    def open_main_app(self, role: str, username: str):
        session_token = create_session_token(username=username, role=role)

        self.main_window = MainWindow(username=username, role=role, session_token=session_token)
        self.main_window.show()
        self.hide()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    app.setFont(QFont("Segoe UI", 10))

    if not verify_launcher_token():
        QMessageBox.critical(
            None,
            "Launcher Token Invalid",
            "Vui lòng mở phần mềm bằng PT_SUB.exe."
        )
        sys.exit(1)

    win = LoginWindow()
    win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
