import json
import requests


# retrieve json files from websites
class gameStat:
    def __init__(self):
        self.queues = []
        self.summoner = []
        self.runesReforged = []
        self.tft_item = {}
        self.tft_trait = {}
        self.tft_queues = {}
        self.tft_tactician = {}
        self.tft_champion = {}
        self.version = "13.6.1"
        self._get_data()

    # private methods
    # extract queues data from json file
    def _get_data(self):
        url_base = f"http://ddragon.leagueoflegends.com/cdn/{self.version}/data/en_US/"
        with open('data/queues.json') as json_file:
            self.queues = json.load(json_file)

        self.summonerSpell = requests.get(url_base + "summoner.json").json()
        self.runes = requests.get(url_base + "runesReforged.json").json()

        self.tft_item = requests.get(url_base + "tft-item.json").json()
        self.tft_trait = requests.get(url_base + "tft-trait.json").json()
        self.tft_queues = requests.get(url_base + "tft-queues.json").json()
        self.tft_tactician = requests.get(url_base + "tft-tactician.json").json()
        self.tft_champion = requests.get(url_base + "tft-champion.json").json()

    # public methods
    # change the version of data searched
    def change_version(self, version):
        self.version = version
        self._get_data()

    # return description of queue given queueID
    def identify_queue(self, queueID):
        for queue in self.queues:
            if queue['queueId'] == queueID:
                return queue['description']

    # return image path of summoner spell given spellKey
    def identify_Summoner_spell(self, spellKey):
        for i in self.summonerSpell['data'].values():
            if i['key'] == str(spellKey):
                return i["image"]['full']

    # return runes path given runeId
    def identify_runes(self, runeId):
        if runeId == 8369:
            return "perk-images/Styles/Inspiration/FirstStrike/FirstStrike.png"
        for i in self.runes:
            if i['id'] == runeId:
                return i['icon']
            for j in i['slots'][0]['runes']:
                if j['id'] == runeId:
                    return j["icon"]

    # return queue name given queueID
    def identify_tft_queue(self, queueID):
        return self.tft_queues['data'][str(queueID)]['name']

    # return trait image path given trait name
    def identify_tft_trait(self, traitName):
        return self.tft_trait['data'][traitName]['image']['full']

    # return trait image path given item name
    def identify_tft_item(self, itemName):
        if itemName.split("_")[0] == "TFT5":
            itemName = "Set5_RadiantItems/" + itemName
        elif itemName.split("_")[0] == "TFT7":
            itemName = "TFT7_ShimmerscaleItems/" + itemName
        elif itemName.split("_")[0] == "TFT8" and itemName.split("_")[-1] == "GenAE":
            itemName = "TFT8_GenAEItems/" + itemName
        elif itemName.split("_")[0] == "TFT8":
            itemName = "TFT8_EmblemItems/" + itemName

        return self.tft_item['data'][itemName]['image']['full']

    # return augment image path given augment name
    def identify_tft_champion(self, augmentName):
        champ = self.tft_champion['data'][augmentName]['image']['full']
        if champ == "TFT8_WuKong.TFT_Set8.png":
            return "TFT8_Wukong.TFT_Set8.png"
        elif champ.split(".")[-2] == "TFT_Set8_Stage2":
            split_s = champ.split('.')
            split_s[0] = split_s[0] + "_Square"
            champ = '.'.join(split_s)
        return champ

    # return tactician image path given tactician ID
    def identify_tft_tactician(self, tacticianID):
        return self.tft_tactician['data'][str(tacticianID)]['image']['full']
