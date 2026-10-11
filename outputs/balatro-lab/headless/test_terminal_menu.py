import unittest
from terminal_menu import validate_terminal

class TerminalMenuTests(unittest.TestCase):
    def test_completed_win_allowed(self):
        validate_terminal({'status':'win','terminal':True,'ante':9},{'won':True,'overlay':'win','ante_num':9})
    def test_active_game_rejected(self):
        with self.assertRaises(ValueError):validate_terminal({'status':'win','terminal':True,'ante':9},{'won':False,'state':'SHOP','ante_num':5})
    def test_missing_persisted_win_rejected(self):
        with self.assertRaises(ValueError):validate_terminal({'status':'error','terminal':False},{'won':True,'overlay':'win','ante_num':9})

if __name__=='__main__':unittest.main()
