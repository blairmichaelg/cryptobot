from faucets.pick_base import PickFaucetBase

class DashPickBot(PickFaucetBase):
    def __init__(self, settings, page, action_lock=None):
        super().__init__(settings, page, action_lock)
        self.faucet_name = "DashPick"
        self.base_url = "https://dashpick.io"
