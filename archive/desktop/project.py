import time

import requests
from PyQt5 import QtCore, QtGui, QtWidgets

import chart_test
import gameStat
import searchMatch
from backend.match_service import participant_name
from basicUI import Ui_MainWindow


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.lineEdit.setPlaceholderText("GameName#TagLine")
        self.lineEdit_2.setPlaceholderText("GameName#TagLine")
        self.gameStat = gameStat.gameStat()
        self.groupBoxes = []
        self.tft_view_more.clicked.connect(self.tft_view_more_history)
        self.lol_view_more.clicked.connect(self.lol_view_more_history)
        self.pushButton_15.clicked.connect(self.search_lol_name)
        self.pushButton_40.clicked.connect(self.search_lol_name)
        self.pushButton_16.clicked.connect(self.search_tft_name)
        self.pushButton_366.clicked.connect(self.search_tft_name)

    # LOL Match History page

    # retrieve information for two input bar to create searchMatch based on given information
    # require input from text bar of lol page
    # set self.Summoner and decide whether it needs to call to generate_lol_groupbox
    def search_lol_name(self):

        # Get the search query from the search bar
        lol_query = self.lineEdit.text()
        lol_region_text = self.comboBox_3.currentText()
        if lol_query == "":
            print("False")
            self.label_200.setText("Enter a Riot ID: GameName#TagLine")
            self.label_200.show()
            QtCore.QTimer.singleShot(3000, self.label_200.hide)
        else:
            self.Summoner = searchMatch.SearchMatch(lol_region_text, 'lol', lol_query)
            # if error occur during search process show error message
            if not self.Summoner.searchComplete:
                self.label_200.setText(self.Summoner.errorCase)
                self.label_200.show()
                QtCore.QTimer.singleShot(3000, self.label_200.hide)
                print("wrong name entered")
            else:
                # delete all existing match groupBox
                for i in self.groupBoxes:
                    i.deleteLater()
                self.groupBoxes = []
                # generate win rate graph
                self.win_rate_count()
                # generate static data of Summoner
                self.lol_stat()
                # generate at most 20 match group boxes
                self.lol_generate_boxes(20)
                self.stackedWidget.setCurrentIndex(2)
                print("right name entered")

    # view more history function
    def lol_view_more_history(self):
        num_match = len(self.groupBoxes)
        # change the match details of the Summoner to new match data
        if not self.Summoner.lol_view_more(num_match):
            self.label_200.setText(self.Summoner.errorCase)
            self.label_200.show()
            return
        # generate 10 boxes and append to the scroll widget
        self.lol_generate_boxes(10)
        self.stackedWidget.setCurrentIndex(2)

    # generate groupboxes and attach to the main windows
    def lol_generate_boxes(self, num):
        # remove the view more button if the button exist
        try:
            self.verticalLayout_9.removeWidget(self.lol_view_more)
            self.lol_view_more.hide()
        except AttributeError:
            pass
        box_start = len(self.groupBoxes)
        self.viewCheck = True  # check if error caught in the range
        # create groupboxes and layout for each match
        for i in range(len(self.Summoner.match_details)):
            groupBox = QtWidgets.QGroupBox(self.scrollAreaWidgetContents)
            groupBox.setMinimumSize(QtCore.QSize(941, 191))
            self.groupBoxes.append(groupBox)
            self.lol_groupBox(box_start, i)
        if self.Summoner.hasMore and self.viewCheck:
            self.verticalLayout_9.addWidget(self.lol_view_more)
            self.lol_view_more.show()

    # create a match groupbox
    def lol_groupBox(self, start, index):
        self_Participant = self.Summoner.match_details[index]['info']['participants'][self.find_self_participant(index)]
        # groupBox set
        lol_parentBoxes = []
        # set vertical layout for first 2 frames ----- [0, 1]
        layoutWidget = QtWidgets.QWidget(self.groupBoxes[start + index])
        layoutWidget.setGeometry(QtCore.QRect(10, 20, 191, 161))
        lol_parentBoxes.append(layoutWidget)
        verticalLayout = QtWidgets.QVBoxLayout(layoutWidget)
        verticalLayout.setContentsMargins(0, 0, 0, 0)
        lol_parentBoxes.append(verticalLayout)
        # set vertical layout for middle 2 frames ----- [2, 3]
        layoutWidget = QtWidgets.QWidget(self.groupBoxes[start + index])
        layoutWidget.setGeometry(QtCore.QRect(250, 20, 371, 180))
        lol_parentBoxes.append(layoutWidget)
        verticalLayout = QtWidgets.QVBoxLayout(layoutWidget)
        verticalLayout.setContentsMargins(0, 0, 0, 0)
        lol_parentBoxes.append(verticalLayout)
        # set groupBox for all champ display groupbox ----- [4, 5]
        frame = QtWidgets.QFrame(self.groupBoxes[start + index])
        frame.setGeometry(QtCore.QRect(649, 20, 281, 161))
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setFrameShadow(QtWidgets.QFrame.Raised)
        lol_parentBoxes.append(frame)
        horizontalLayout = QtWidgets.QHBoxLayout(frame)
        horizontalLayout.setContentsMargins(0, 0, 0, 0)
        lol_parentBoxes.append(horizontalLayout)

        # frame set
        lol_info_frames = []
        for i in range(2):
            frame = QtWidgets.QFrame(lol_parentBoxes[0])
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            frame.setFrameShadow(QtWidgets.QFrame.Raised)
            lol_parentBoxes[1].addWidget(frame)
            lol_info_frames.append(frame)
        # rank solo and game history time frame
        lol_info_frames[0].setGeometry(QtCore.QRect(1, 1, 189, 75))
        # game time and win/lose frame
        lol_info_frames[1].setGeometry(QtCore.QRect(1, 85, 189, 75))

        # frame set
        lol_Summoner_frame = []
        for i in range(2):
            frame = QtWidgets.QFrame(lol_parentBoxes[2])
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            frame.setFrameShadow(QtWidgets.QFrame.Raised)
            lol_parentBoxes[3].addWidget(frame)
            lol_Summoner_frame.append(frame)
        # champion image part
        lol_Summoner_frame[0].setGeometry(QtCore.QRect(1, 1, 369, 96))
        # item frame
        lol_Summoner_frame[1].setGeometry(QtCore.QRect(1, 110, 369, 57))

        # frame set
        lol_Participants_frame = []
        for i in range(2):
            frame = QtWidgets.QFrame(lol_parentBoxes[4])
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            frame.setFrameShadow(QtWidgets.QFrame.Raised)
            lol_parentBoxes[5].addWidget(frame)
            lol_Participants_frame.append(frame)
        # left part summoners frame
        lol_Participants_frame[0].setGeometry(QtCore.QRect(1, 1, 135, 159))
        # right part summoners frame
        lol_Participants_frame[1].setGeometry(QtCore.QRect(145, 1, 135, 159))

        # label set in frame[0]
        # label of one frame
        lol_matchInfo = []
        for i in range(2):
            info = QtWidgets.QLabel(lol_info_frames[0])
            lol_matchInfo.append(info)

        font = QtGui.QFont()
        font.setPointSize(9)
        font.setWeight(75)

        lol_matchInfo[0].setGeometry(QtCore.QRect(10, 10, 111, 18))
        lol_matchInfo[0].setFont(font)
        # set Queue name
        lol_matchInfo[0].setText(self.gameStat.identify_queue(self.Summoner.match_details[index]['info']['queueId']))

        # xxx hours ago label
        lol_matchInfo[1].setGeometry(QtCore.QRect(10, 40, 181, 31))
        lol_matchInfo[1].setFont(font)
        # set how many time passed
        lol_matchInfo[1].setText(
            f"{self.time_previous(self.Summoner.match_details[index]['info']['gameEndTimestamp'])}")

        # label set in frame[1]
        # label of one frame
        # win/lose and game time info
        lol_GameTime = []
        for i in range(2):
            info = QtWidgets.QLabel(lol_info_frames[1])
            lol_GameTime.append(info)

        font = QtGui.QFont()
        font.setPointSize(9)
        font.setWeight(75)

        lol_GameTime[0].setGeometry(QtCore.QRect(10, 10, 70, 18))
        lol_GameTime[0].setFont(font)
        # set the text for Victory or Lost
        lol_GameTime[0].setText("win" if self_Participant['win'] else "Defeat")
        # set background color for the groupbox based on win or lose of the game
        if self_Participant['win']:
            self.groupBoxes[start + index].setStyleSheet("background-color: rgb(137, 194, 255);")
        else:
            self.groupBoxes[start + index].setStyleSheet("background-color: rgb(255, 103, 89);")

        lol_GameTime[1].setGeometry(QtCore.QRect(10, 40, 70, 18))
        lol_GameTime[1].setFont(font)
        # set game duration
        lol_GameTime[1].setText(
            f"{int(self.Summoner.match_details[index]['info']['gameDuration'] / 60)}m {self.Summoner.match_details[index]['info']['gameDuration'] % 60}s")

        # pushButtons and labels in frame[2]
        # Champ icon pushButton
        lol_match_champ = QtWidgets.QPushButton(lol_Summoner_frame[0])
        lol_match_champ.setGeometry(QtCore.QRect(30, 0, 61, 61))
        lol_match_champ.setIconSize(QtCore.QSize(70, 70))

        # summoner Spell
        lol_Spell = []
        for i in range(2):
            lolSpell_icon = QtWidgets.QPushButton(lol_Summoner_frame[0])
            lolSpell_icon.setGeometry(QtCore.QRect(100, i * 30, 31, 34))
            lolSpell_icon.setIconSize(QtCore.QSize(30, 30))
            lol_Spell.append(lolSpell_icon)

        # text labels setting in frame[2]
        lol_frame2Text = []
        for i in range(3):
            info = QtWidgets.QLabel(lol_Summoner_frame[0])
            lol_frame2Text.append(info)

        # level label
        lol_frame2Text[0].setGeometry(QtCore.QRect(30, 70, 61, 20))
        lol_frame2Text[0].setFont(font)
        # set champion level of the summoner
        lol_frame2Text[0].setText(f"lv:{self_Participant['champLevel']}")

        # Kill/Death/Assist label
        font1 = QtGui.QFont()
        font1.setFamily("Bodoni MT Black")
        font1.setPointSize(10)
        font1.setBold(True)
        font1.setWeight(75)

        lol_frame2Text[1].setGeometry(QtCore.QRect(230, 20, 131, 20))
        lol_frame2Text[1].setFont(font1)
        # set KDA of the Summoner
        lol_frame2Text[1].setText(
            f"{self_Participant['kills']} / {self_Participant['deaths']} / {self_Participant['assists']}")

        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setBold(False)
        font.setWeight(50)
        # total kda count
        lol_frame2Text[2].setGeometry(QtCore.QRect(240, 60, 121, 20))
        lol_frame2Text[2].setFont(font)
        # Set total KDA of the summoner
        lol_frame2Text[2].setText(
            f"{self.cal_KDA(self_Participant['kills'], self_Participant['deaths'], self_Participant['assists'])} KDA")

        # Runes pushButtons
        lol_Runes = []
        for i in range(2):
            lolRune_icon = QtWidgets.QPushButton(lol_Summoner_frame[0])
            lolRune_icon.setGeometry(QtCore.QRect(140, i * 30, 31, 34))
            lolRune_icon.setIconSize(QtCore.QSize(30, 30))
            lol_Runes.append(lolRune_icon)

        # frame[3]
        # item pushButtons in frame[3]
        lol_items = []
        # 9 item icon pushButtons
        for i in range(7):
            lolItem_icon = QtWidgets.QPushButton(lol_Summoner_frame[1])
            lolItem_icon.setGeometry(QtCore.QRect(30 + 40 * i, 10, 41, 41))
            lolItem_icon.setIconSize(QtCore.QSize(30, 30))
            lol_items.append(lolItem_icon)
        lol_items[-1].setStyleSheet("    QPushButton {\n"
                                    "        border-radius: 16px;\n"
                                    "        \n"
                                    "        \n"
                                    "    background-color: rgb(0, 170, 255);\n"
                                    "    }")
        # frame[4]
        # left side summoner name and icon pushButtons and labels
        # summoner icon pushbutton
        lol_left_SummonerIcon = []
        # 5 player icon pushButtons
        for i in range(5):
            lolSummoner_icon = QtWidgets.QPushButton(lol_Participants_frame[0])
            lolSummoner_icon.setGeometry(QtCore.QRect(0, 30 * i, 31, 31))
            lolSummoner_icon.setIconSize(QtCore.QSize(25, 25))
            lol_left_SummonerIcon.append(lolSummoner_icon)

        # summoner name text label
        lol_left_SummonerLabel = []
        # 5 player icon pushButtons
        for i in range(5):
            lolSummoner_name = QtWidgets.QLabel(lol_Participants_frame[0])
            lolSummoner_name.setGeometry(QtCore.QRect(40, 10 + 30 * i, 90, 18))
            lolSummoner_name.setFont(font)
            lol_left_SummonerLabel.append(lolSummoner_name)

        # frame[5]
        # right side summoner name and icon pushButtons and labels
        # summoner icon pushbuttons
        lol_right_SummonerIcon = []
        # 5 player icon pushButtons
        for i in range(5):
            lolSummoner2_icon = QtWidgets.QPushButton(lol_Participants_frame[1])
            lolSummoner2_icon.setGeometry(QtCore.QRect(0, 30 * i, 31, 31))
            lolSummoner2_icon.setIconSize(QtCore.QSize(25, 25))
            lol_right_SummonerIcon.append(lolSummoner2_icon)

        # summoner name text label
        lol_right_SummonerLabel = []
        # 5 player icon pushButtons
        for i in range(5):
            lolSummoner_name = QtWidgets.QLabel(lol_Participants_frame[1])
            lolSummoner_name.setGeometry(QtCore.QRect(40, 10 + 30 * i, 90, 18))
            lolSummoner_name.setFont(font)
            lol_right_SummonerLabel.append(lolSummoner_name)

        # add groupbox to vertical layout
        self.verticalLayout_9.addWidget(self.groupBoxes[start + index])

        # Summoner match info img display
        # items img display
        for i in range(7):
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(f"item/{self_Participant[f'item{i}']}.png"), QtGui.QIcon.Normal,
                           QtGui.QIcon.Off)
            lol_items[i].setIcon(icon)

            # summoner champ icon display
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(f"champion-icon/{self_Participant['championId']}.png"), QtGui.QIcon.Normal,
                           QtGui.QIcon.Off)
            lol_match_champ.setIcon(icon)

        # summoner Spell display
        for i in range(2):
            summonerSpell = QtGui.QIcon()
            summonerSpell.addPixmap(
                QtGui.QPixmap(
                    f"summonerSpell/{self.gameStat.identify_Summoner_spell(self_Participant[f'summoner{i + 1}Id'])}"),
                QtGui.QIcon.Normal,
                QtGui.QIcon.Off)
            lol_Spell[i].setIcon(summonerSpell)

        # summoner Rune display
        runeUrlPath = 'https://ddragon.canisback.com/img/'
        rune = QtGui.QIcon()
        primaryRunePath = self.gameStat.identify_runes(
            self_Participant['perks']['styles'][0]['selections'][0]['perk'])
        primaryRuneimg = QtGui.QImage()
        primaryRuneimg.loadFromData(requests.get(runeUrlPath + primaryRunePath).content)
        rune.addPixmap(QtGui.QPixmap(primaryRuneimg),
                       QtGui.QIcon.Normal,
                       QtGui.QIcon.Off)
        lol_Runes[0].setIcon(rune)

        rune2 = QtGui.QIcon()
        subRunePath = self.gameStat.identify_runes(
            self_Participant['perks']['styles'][1]['style'])
        subRuneimg = QtGui.QImage()
        subRuneimg.loadFromData(requests.get(runeUrlPath + subRunePath).content)
        rune2.addPixmap(QtGui.QPixmap(subRuneimg),
                        QtGui.QIcon.Normal,
                        QtGui.QIcon.Off)
        lol_Runes[1].setIcon(rune2)

        # participants name display
        for i in range(5):
            lol_left_SummonerLabel[i].setText(
                participant_name(self.Summoner.match_details[index]['info']['participants'][i]))
            lol_right_SummonerLabel[i].setText(
                participant_name(self.Summoner.match_details[index]['info']['participants'][5 + i]))
        # participants champion img display
        for i in range(5):
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(
                f"champion-icon/{self.Summoner.match_details[index]['info']['participants'][i]['championId']}.png"),
                QtGui.QIcon.Normal, QtGui.QIcon.Off)
            lol_left_SummonerIcon[i].setIcon(icon)
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(
                f"champion-icon/{self.Summoner.match_details[index]['info']['participants'][5 + i]['championId']}.png"),
                QtGui.QIcon.Normal, QtGui.QIcon.Off)
            lol_right_SummonerIcon[i].setIcon(icon)
        print(f"match {index} completed")

    # fill lol match history page statics
    def lol_stat(self):
        # set win rate graph display
        win_rate_graph = QtGui.QIcon()
        win_rate_graph.addPixmap(
            QtGui.QPixmap("win_rate.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off)
        self.pushButton_42.setIcon(win_rate_graph)

        # display profile icon
        icon17 = QtGui.QIcon()
        icon17.addPixmap(QtGui.QPixmap(f"profileicon/{self.Summoner.me['profileIconId']}.png"), QtGui.QIcon.Normal,
                         QtGui.QIcon.Off)
        self.pushButton_17.setIcon(icon17)

        # display ranked emblem image of summoner
        if len(self.Summoner.rankedInfo) != 0:
            icon18 = QtGui.QIcon()
            icon18.addPixmap(QtGui.QPixmap(f"ranked-emblem/emblem-{self.Summoner.rankedInfo[0]['tier']}.png"),
                             QtGui.QIcon.Normal,
                             QtGui.QIcon.Off)
            self.pushButton_41.setIcon(icon18)
        else:

            self.pushButton_41.setIcon(QtGui.QIcon("items/7050.png"))

        _translate = QtCore.QCoreApplication.translate
        # set level of summoner
        self.label_18.setText(_translate("MainWindow", f"lv : {self.Summoner.me['summonerLevel']}"))
        # set the summoner name display
        self.label_19.setText(_translate("MainWindow", f"{self.Summoner.summonerName}"))
        # set the ranked text
        try:
            self.label_20.setText(_translate("MainWindow", f"{self.Summoner.rankedInfo[0]['tier']}"))
        except IndexError:
            self.label_20.setText(_translate("MainWindow", "N/A"))

    # LOL Helper Functions

    # return the index of the in-match data of the summoner being searched
    def find_self_participant(self, index):
        participants_list = self.Summoner.match_details[index]['info']['participants']
        # find index of summoner in lol game
        if self.Summoner.gameType == 'lol':
            for participant in participants_list:
                if participant.get('puuid') == self.Summoner.me['puuid']:
                    return participants_list.index(participant)
        # find index of summoner in tft games
        elif self.Summoner.gameType == 'tft':
            for participant in participants_list:
                if participant['puuid'] == self.Summoner.me['puuid']:
                    return participants_list.index(participant)

    # helper function to determine how long since the indicated game finished
    def time_previous(self, gameTime):
        currentTime = time.time()
        timeDiff = int(currentTime) - int(gameTime / 1000)
        if timeDiff < 3600:
            return f"{int(timeDiff / 60)} minutes ago"
        elif 3600 < timeDiff < 86400:
            return f"{int(timeDiff / 3600)} hours ago"
        elif timeDiff > 86400:
            return f"{int(timeDiff / 86400)} days ago"

    # calculate the KDA given kill death assists
    def cal_KDA(self, kill, death, assist):
        if death == 0:
            return "Perfect KDA"
        else:
            return round((kill + assist) / death, 1)

    # calculate the win rate of the summoner then graph the win rate graph using function from chart_test
    def win_rate_count(self):
        win_count = 0
        for index, match in enumerate(self.Summoner.match_details):
            if match['info']['participants'][self.find_self_participant(index)]['win']:
                win_count += 1
        if len(self.Summoner.match_details) == 0:
            return "No available match"
        graph = chart_test.WinLoseCircleGraph(round(win_count / len(self.Summoner.match_details), 2))

    # TFT Match History Page

    # retrieve information for two input bar to create searchMatch based on given information
    def search_tft_name(self):
        # search function for tft
        tft_query = self.lineEdit_2.text()
        tft_region_text = self.comboBox_2.currentText()
        if tft_query == "":
            print("False")
            self.label_201.setText("Enter a Riot ID: GameName#TagLine")
            self.label_201.show()
            QtCore.QTimer.singleShot(3000, self.label_201.hide)
        else:
            self.Summoner = searchMatch.SearchMatch(tft_region_text, 'tft', tft_query)
            if not self.Summoner.searchComplete:
                self.label_201.setText(self.Summoner.errorCase)
                self.label_201.show()
                QtCore.QTimer.singleShot(3000, self.label_201.hide)
                print("wrong name entered")
            else:
                # delete all existing match groupBox
                for i in self.groupBoxes:
                    i.deleteLater()
                self.groupBoxes = []

                # generate 20 boxes and append to the scroll widget
                self.tft_generate_boxes(20)
                self.stackedWidget.setCurrentIndex(3)
                print("right name entered")

    # view more history function
    def tft_view_more_history(self):
        num_match = len(self.groupBoxes)
        # change the match details of the Summoner to new match data
        if not self.Summoner.tft_view_more(num_match):
            self.label_201.setText(self.Summoner.errorCase)
            self.label_201.show()
            return
        # generate 10 boxes and append to the scroll widget
        self.tft_generate_boxes(10)
        self.stackedWidget.setCurrentIndex(3)

    # generate groupboxes and attach to the main windows
    def tft_generate_boxes(self, num):
        # remove the view more button if the button exist
        try:
            self.verticalLayout_8.removeWidget(self.tft_view_more)
            self.tft_view_more.hide()
        except AttributeError:
            pass
        box_start = len(self.groupBoxes)
        self.viewCheck = True  # check if error caught in the range
        # create groupboxes and layout for each match
        for i in range(len(self.Summoner.match_details)):
            groupBox = QtWidgets.QGroupBox(self.scrollAreaWidgetContents_2)
            groupBox.setMinimumSize(QtCore.QSize(0, 230))
            groupBox.setMaximumSize(QtCore.QSize(1000, 16777215))
            self.groupBoxes.append(groupBox)
            try:
                self.tft_groupBox(box_start, i)
            except KeyError:
                self.gameStat.change_version("13.4.1")
                try:
                    self.tft_groupBox(box_start, i)
                except KeyError:
                    groupBox.hide()
                    self.viewCheck = False
                    break
        self.gameStat.change_version("13.6.1")
        if self.Summoner.hasMore and self.viewCheck:
            self.verticalLayout_8.addWidget(self.tft_view_more)
            self.tft_view_more.show()

    # create a match groupbox
    def tft_groupBox(self, start, index):
        # groupBox set
        # frame set
        self.tft_frames = []
        for i in range(3):
            frame = QtWidgets.QFrame(self.groupBoxes[start + index])
            frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
            frame.setFrameShadow(QtWidgets.QFrame.Raised)
            self.tft_frames.append(frame)
        self.tft_frames[0].setGeometry(QtCore.QRect(10, 40, 241, 161))
        self.tft_frames[1].setGeometry(QtCore.QRect(260, 10, 711, 141))
        self.tft_frames[2].setGeometry(QtCore.QRect(310, 160, 621, 71))

        # label set
        # label of 1 frame
        self.matchInfo = []
        for i in range(3):
            info = QtWidgets.QLabel(self.tft_frames[0])
            self.matchInfo.append(info)
        font = QtGui.QFont()
        font.setFamily("Bodoni MT Black")
        font.setPointSize(11)
        font.setBold(True)
        font.setWeight(75)
        # match placement of summoner
        self.matchInfo[0].setGeometry(QtCore.QRect(10, 10, 141, 41))
        self.matchInfo[0].setFont(font)
        self.matchInfo[0].setText(self.placement_trans(
            self.Summoner.match_details[index]['info']['participants'][self.find_self_participant(index)]['placement']))
        # game queue name
        self.matchInfo[1].setGeometry(QtCore.QRect(10, 60, 181, 41))
        font.setPointSize(10)
        self.matchInfo[1].setFont(font)
        self.matchInfo[1].setText(self.gameStat.identify_tft_queue(
            self.Summoner.match_details[index]['info']['queue_id']))
        # game time period
        self.matchInfo[2].setText(
            self.time_previous(self.Summoner.match_details[index]['info']['game_datetime']))
        self.matchInfo[2].setGeometry(QtCore.QRect(10, 100, 191, 41))
        self.matchInfo[2].setFont(font)
        # rank place text
        try:
            self.label_236.setText(f"{self.Summoner.rankedInfo[0]['tier']}")
        except KeyError:
            self.label_236.setText("N/A")
        except IndexError:
            self.label_236.setText("N/A")
        # summoner Name
        self.label_237.setText(f"{self.Summoner.summonerName}")
        # traits are labels for 3 frame
        # traits level
        self.traitLevels = []
        font = QtGui.QFont()
        font.setFamily("Bodoni MT Black")
        for i in range(9):
            traitLevel = QtWidgets.QLabel(self.tft_frames[2])
            traitLevel.setGeometry(QtCore.QRect(40 + i * 60, 40, 31, 21))
            traitLevel.setFont(font)
            self.traitLevels.append(traitLevel)

        # push button for 2 frame
        # tactics icon setting
        self.tac_icons = []
        for i in range(9):
            tac_icon = QtWidgets.QPushButton(self.tft_frames[1])
            tac_icon.setGeometry(QtCore.QRect(i * 80, 30, 69, 69))
            tac_icon.setIconSize(QtCore.QSize(60, 60))
            self.tac_icons.append(tac_icon)

        # items buttons
        self.tac_items = []
        for i in range(27):
            tac_item = QtWidgets.QPushButton(self.tft_frames[1])
            tac_item.setGeometry(QtCore.QRect(i * 20 + int(i / 3) * 20, 100, 21, 21))
            tac_item.setIconSize(QtCore.QSize(35, 35))
            self.tac_items.append(tac_item)

        # stars buttons
        self.tac_stars = []
        for i in range(9):
            star = QtWidgets.QPushButton(self.tft_frames[1])
            star.setGeometry(QtCore.QRect(20 + i * 80, 0, 31, 31))
            star.setIconSize(QtCore.QSize(35, 35))
            self.tac_stars.append(star)

        # pushButtons for 3 frame
        # 9 buttons
        self.traits = []
        for i in range(9):
            trait = QtWidgets.QPushButton(self.tft_frames[2])
            trait.setGeometry(QtCore.QRect(30 + (i * 60), 0, 47, 41))
            trait.setStyleSheet("background-color: rgb(0, 0, 0);")
            self.traits.append(trait)

        # add groupbox to vertical layout
        self.verticalLayout_8.addWidget(self.groupBoxes[start + index])

        # settings for images
        self_Participant = self.Summoner.match_details[index]['info']['participants'][self.find_self_participant(index)]
        imageurl = f"https://ddragon.leagueoflegends.com/cdn/{self.gameStat.version}/img/"
        numUnit = len(self_Participant['units'])
        item_count = 0
        # display image of champion and items
        for i in range(numUnit if numUnit < 10 else 9):
            champIcon = QtGui.QIcon()
            unitImg = QtGui.QImage()
            champ = self_Participant['units'][i]['character_id']
            if champ == "TFT8_Zac":
                unitImg.loadFromData(requests.get(
                    'https://ddragon.leagueoflegends.com/cdn/13.4.1/img/tft-hero-augment/TFT8_Zac.TFT_Set8.png').content)
            else:
                unitImg.loadFromData(requests.get(
                    imageurl + "tft-hero-augment/" + self.gameStat.identify_tft_champion(champ)).content)
            champIcon.addPixmap(QtGui.QPixmap(unitImg), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.tac_icons[i].setIcon(champIcon)

            # display star image
            starIcon = QtGui.QIcon()
            starIcon.addPixmap(QtGui.QPixmap(self._star_trans(self_Participant['units'][i]['tier'])),
                               QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.tac_stars[i].setIcon(starIcon)
            for j in range(len(self_Participant['units'][i]['itemNames'])):
                itemIcon = QtGui.QIcon()
                itemImg = QtGui.QImage()
                itemName = self_Participant['units'][i]['itemNames'][j]
                itemImg.loadFromData(
                    requests.get(imageurl + "tft-item/" + self.gameStat.identify_tft_item(itemName)).content)
                itemIcon.addPixmap(QtGui.QPixmap(itemImg), QtGui.QIcon.Normal, QtGui.QIcon.Off)
                self.tac_items[item_count + j].setIcon(itemIcon)
            item_count += 3

        active_traits = []
        for i in self_Participant['traits']:
            if i['tier_current'] != 0:
                active_traits.append(i)
        active_traits = sorted(active_traits, key=lambda d: d['tier_current'], reverse=True)
        for i in range(len(active_traits) if len(active_traits) < len(self.traits) else len(self.traits)):
            trait_icon = QtGui.QIcon()
            traitImg = QtGui.QImage()
            traitImg.loadFromData(requests.get(
                imageurl + "tft-trait/" + self.gameStat.identify_tft_trait(
                    active_traits[i]['name'])).content)
            trait_icon.addPixmap(QtGui.QPixmap(traitImg), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.traits[i].setIcon(trait_icon)

            # display trait level text
            self.traitLevels[i].setText(f"{active_traits[i]['num_units']}")
        # display ranked emblem image of summoner
        if len(self.Summoner.rankedInfo) != 0:
            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(self._trans_rank()), QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.pushButton_365.setIcon(icon)
        else:
            self.pushButton_365.setIcon(QtGui.QIcon("items/7050.png"))
        print(f"Match {index} finished")

    # TFT helper functions

    # translate the level from integer to file location
    def _star_trans(self, level):
        # based on the level of the given champion level produce the name of different star picture
        if level == 1:
            return "picture/bronze.png"
        elif level == 2:
            return "picture/silver.png"
        elif level == 3:
            return "picture/gold.png"

    # translate TFT rank given by api to fileName
    def _trans_rank(self):
        # try to get the ranked info of the summoner, if None then return address to empty picture for output
        try:
            rank = self.Summoner.rankedInfo[0]['tier']
        except KeyError:
            return "items/7050.png"
        # translate from rank given to address to file
        trans = rank[0]
        trans += rank[1:].lower()
        return f"tft-regalia/TFT_Regalia_{trans}.png"

    # translate number placement to numeric
    def placement_trans(self, placement):
        # translate
        if placement < 1:
            return "N/A"
        elif placement == 1:
            return "1st place"
        elif placement == 2:
            return "2nd place"
        elif placement == 3:
            return "3rd place"
        else:
            return f"{placement}th place"


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
