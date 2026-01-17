from faucets.pick_base import PickFaucetBase

class UsdPickBot(PickFaucetBase):
    def __init__(self, settings, page, action_lock=None):
        super().__init__(settings, page, action_lock)
        self.faucet_name = "UsdPick"
        self.base_url = "https://usdpick.io"
