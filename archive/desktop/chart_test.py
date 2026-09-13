import pyqtgraph as pg
from PyQt5.QtWidgets import QGraphicsEllipseItem
from PyQt5.QtGui import QBrush, QColor, QPen
import pyqtgraph.exporters


# create win rate graph and export to win_rate.png
class WinLoseCircleGraph:
    def __init__(self, win_rate):
        self.win_rate = win_rate
        self.lose_rate = 1 - win_rate
        self.plot_widget = pg.PlotWidget()
        self.initUI()

    def initUI(self):
        # Create the circle graph
        angle = 0
        items = []
        # for win, lose in zip(self.win_rate, self.lose_rate):
        # Calculate the size of the win sector
        win_size = int(self.win_rate * 360)

        # hide axis on both sides
        self.plot_widget.hideAxis('left')
        self.plot_widget.hideAxis('bottom')

        # Create a win sector item
        win_sector_item = QGraphicsEllipseItem(-50, -50, 100, 100)
        win_sector_item.setStartAngle(angle * 16)
        win_sector_item.setSpanAngle(win_size * 16)
        win_sector_item.setBrush(QBrush(QColor('cyan')))  # Set the color of the win sector
        win_sector_item.setPen(QPen(QColor(255, 255, 255)))  # Set the color of the border
        items.append(win_sector_item)

        # Calculate the size of the lose sector
        lose_size = int(self.lose_rate * 360)

        # Create a lose sector item
        lose_sector_item = QGraphicsEllipseItem(-50, -50, 100, 100)
        lose_sector_item.setStartAngle((angle + win_size) * 16)
        lose_sector_item.setSpanAngle(lose_size * 16)
        lose_sector_item.setBrush(QBrush(QColor('red')))  # Set the color of the lose sector
        lose_sector_item.setPen(QPen(QColor(255, 255, 255)))  # Set the color of the border
        items.append(lose_sector_item)

        # Update the angle for the next sector
        angle += win_size + lose_size

        # Create a group item to hold all the sector items
        group_item = pg.QtWidgets.QGraphicsItemGroup()
        for item in items:
            group_item.addToGroup(item)

        # Add the group item to the plot widget
        self.plot_widget.addItem(group_item)
        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.export("win_rate.png")

