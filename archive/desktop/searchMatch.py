"""Compatibility adapter for the original Qt UI using the shared service."""
from backend.match_service import fetch_page
from backend.riot_client import ApiError


class SearchMatch:
    def __init__(self, region, gameType, summonerName):
        self.region_name = region
        self.gameType = gameType
        self.requested_name = summonerName
        self.summonerName = summonerName
        self.region = region
        self.routingRegion = None
        self.searchComplete = False
        self.errorCase = ""
        self.match_details = []
        self.rankedInfo = []
        self.me = {}
        self.nextStart = None
        self.hasMore = False
        self.asOf = None
        self._load(0, 20)

    def _load(self, start, count):
        from backend.match_service import region_codes

        try:
            page = fetch_page(self.gameType, self.region_name, self.requested_name,
                              start, count, self.asOf)
        except ApiError as error:
            self.errorCase = str(error)
            self.searchComplete = False
            return False
        self.region, self.routingRegion = region_codes(self.region_name)
        self.me = page["summoner"]
        self.summonerName = self.me["name"]
        self.rankedInfo = page["ranked"]
        self.match_details = page["rawMatches"]
        self.nextStart = page["pagination"]["nextStart"]
        self.hasMore = page["pagination"]["hasMore"]
        self.asOf = page["pagination"]["asOf"]
        self.searchComplete = True
        self.errorCase = ""
        return True

    def lol_view_more(self, start_index=None):
        return self._view_more()

    def tft_view_more(self, start_index=None):
        return self._view_more()

    def _view_more(self):
        if not self.hasMore:
            self.match_details = []
            return False
        return self._load(self.nextStart, 10)
