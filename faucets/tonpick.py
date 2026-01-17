from faucets.pick_base import PickFaucetBase

class TonPickBot(PickFaucetBase):
    def __init__(self, settings, page, action_lock=None):
        super().__init__(settings, page, action_lock)
        self.faucet_name = "TonPick"
        self.base_url = "https://tonpick.io"
