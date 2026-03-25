"""Shared interaction feedback helpers for buttons."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QPushButton, QWidget


class ButtonFeedbackController(QObject):
    """Add a short press-and-release highlight to buttons."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)

    def register_buttons(self, root: QWidget) -> None:
        for button in root.findChildren(QPushButton):
            if button.property("feedbackInstalled"):
                continue
            button.setProperty("feedbackInstalled", True)
            button.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QPushButton):
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress and watched.isEnabled():
            watched.setProperty("feedbackPressed", True)
            watched.style().unpolish(watched)
            watched.style().polish(watched)
        elif event.type() == QEvent.Type.MouseButtonRelease:
            QTimer.singleShot(120, lambda btn=watched: self._clear_pressed_state(btn))
        elif event.type() == QEvent.Type.Leave and not watched.isDown():
            self._clear_pressed_state(watched)
        return super().eventFilter(watched, event)

    @staticmethod
    def _clear_pressed_state(button: QPushButton) -> None:
        if button is None:
            return
        button.setProperty("feedbackPressed", False)
        button.style().unpolish(button)
        button.style().polish(button)


def install_button_feedback(root: QWidget) -> None:
    controller = getattr(root, "_button_feedback_controller", None)
    if controller is None:
        controller = ButtonFeedbackController(root)
        setattr(root, "_button_feedback_controller", controller)
    controller.register_buttons(root)
