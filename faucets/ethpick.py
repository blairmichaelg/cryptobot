from faucets.pick_base import PickFaucetBase

class EthPickBot(PickFaucetBase):
    def __init__(self, settings, page, action_lock=None):
        super().__init__(settings, page, action_lock)
        self.faucet_name = "EthPick"
        self.base_url = "https://ethpick.io"
