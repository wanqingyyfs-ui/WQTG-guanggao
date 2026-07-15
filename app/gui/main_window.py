from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from app.core.context import AppContext
from app.gui.account_pages import AccountsPage, DashboardPage, ProxyGroupsPage
from app.gui.automation_pages import LocatorPage, ProfileMaintenancePage, SettingsDiagnosticsPage
from app.gui.browser_pages import BrowserWorkbenchPage, GroupsPage
from app.gui.content_pages import RecordsPage, TasksPage, TemplatesPage


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self.setWindowTitle("WQTG 浏览器原生工作台 2.0")
        self.resize(1500, 900)
        central = QWidget()
        layout = QHBoxLayout(central)
        self.navigation = QListWidget()
        self.navigation.setMaximumWidth(230)
        self.stack = QStackedWidget()
        self.pages = [
            ("运行总控", DashboardPage(context)),
            ("账号中心", AccountsPage(context)),
            ("账号组与静态IP", ProxyGroupsPage(context)),
            ("浏览器工作台", BrowserWorkbenchPage(context)),
            ("群组管理", GroupsPage(context)),
            ("素材与模板", TemplatesPage(context)),
            ("广告任务", TasksPage(context)),
            ("执行记录", RecordsPage(context)),
            ("账号资料维护", ProfileMaintenancePage(context)),
            ("自动化定位", LocatorPage(context)),
            ("系统设置与诊断", SettingsDiagnosticsPage(context)),
        ]
        self.workbench = self.pages[3][1]
        for title, page in self.pages:
            self.navigation.addItem(title)
            self.stack.addWidget(page)
        self.navigation.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_browser_events)
        self.timer.start(150)

    def poll_browser_events(self) -> None:
        for event in self.context.browsers.poll_events():
            self.workbench.handle_event(event)

    def closeEvent(self, event) -> None:
        self.context.browsers.stop_all()
        super().closeEvent(event)
